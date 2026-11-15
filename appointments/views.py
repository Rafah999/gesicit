from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from datetime import datetime, timedelta
from uuid import UUID

from .forms import (
    AppointmentAssignmentForm,
    AvailabilityRangeForm,
    InstitutionForm,
    MedicalServiceForm,
    PatientRegistrationForm,
    ProfessionalForm,
)
from .constants import (
    APPOINTMENT_SLOT_MINUTES,
    BUSINESS_DAYS,
    BUSINESS_END_TIME,
    BUSINESS_START_TIME,
)
from .models import (
    AppointmentAssignment,
    AppointmentRequest,
    AssignmentHistory,
    AvailabilitySlot,
    Institution,
    MedicalService,
    Notification,
    Professional,
    RequestStatusHistory,
    UserProfile,
)

User = get_user_model()


@require_http_methods(["GET", "HEAD"])
def health_check(request):
    """Minimal public endpoint for external uptime monitors."""
    return HttpResponse("ok", content_type="text/plain")


class RoleBasedLoginView(LoginView):
    def get_success_url(self):
        if self.request.user.is_superuser:
            return reverse("admin_dashboard")
        if self.request.user.is_staff:
            return reverse("admin_requests")
        return super().get_success_url()


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = PatientRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="appointments.auth_backends.EmailOrUsernameBackend")
        messages.success(request, "Tu cuenta quedó creada correctamente.")
        return redirect("home")

    return render(request, "registration/register.html", {"form": form})


@login_required
def home(request):
    if request.user.is_superuser:
        return redirect("admin_dashboard")
    if request.user.is_staff:
        return redirect("admin_requests")
    return render(request, "appointments/home.html")


@user_passes_test(lambda user: user.is_active and user.is_superuser)
def admin_dashboard(request):
    users = User.objects.order_by("-date_joined", "username")
    query = request.GET.get("q", "").strip()
    role = request.GET.get("rol", "")
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(gesecit_profile__demo_member_code__icontains=query)
        )
    if role == "patient":
        users = users.filter(is_staff=False, is_superuser=False)
    elif role == "admin":
        users = users.filter(is_staff=True, is_superuser=False)
    elif role == "superuser":
        users = users.filter(is_superuser=True)
    elif role == "inactive":
        users = users.filter(is_active=False)
    context = {
        "users": users,
        "total_users": User.objects.count(),
        "patient_count": User.objects.filter(is_staff=False, is_superuser=False).count(),
        "admin_count": User.objects.filter(is_staff=True, is_superuser=False).count(),
        "superuser_count": User.objects.filter(is_superuser=True).count(),
        "active_count": User.objects.filter(is_active=True).count(),
        "query": query,
        "selected_role": role,
    }
    return render(request, "appointments/admin_dashboard.html", context)


@user_passes_test(lambda user: user.is_active and user.is_superuser)
@require_POST
def change_user_role(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    new_role = request.POST.get("role")
    if target.pk == request.user.pk:
        messages.error(request, "No puedes cambiar tus propios permisos desde esta pantalla.")
        return redirect("admin_dashboard")
    if new_role not in {"patient", "admin", "superuser"}:
        messages.error(request, "Selecciona un rol válido.")
        return redirect("admin_dashboard")
    if target.is_superuser and new_role != "superuser":
        active_superusers = User.objects.filter(is_superuser=True, is_active=True).count()
        if target.is_active and active_superusers <= 1:
            messages.error(request, "No se puede quitar el rol al único superusuario activo.")
            return redirect("admin_dashboard")

    with transaction.atomic():
        target.is_staff = new_role in {"admin", "superuser"}
        target.is_superuser = new_role == "superuser"
        target.save(update_fields=("is_staff", "is_superuser"))
        profile, _ = UserProfile.objects.get_or_create(user=target)
        profile.role = (
            UserProfile.Role.ADMINISTRATOR
            if new_role == "superuser"
            else UserProfile.Role.ADMIN_STAFF
            if new_role == "admin"
            else UserProfile.Role.AFFILIATE
        )
        profile.save(update_fields=("role",))

    role_name = {"patient": "paciente", "admin": "administrador", "superuser": "superusuario"}[new_role]
    messages.success(request, f"{target.get_username()} ahora tiene el rol de {role_name}.")
    return redirect("admin_dashboard")


@user_passes_test(lambda user: user.is_active and user.is_superuser)
@require_POST
def toggle_user_active(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "No puedes desactivar la cuenta de tu sesión actual.")
        return redirect("admin_dashboard")
    if target.is_superuser and target.is_active:
        active_superusers = User.objects.filter(is_superuser=True, is_active=True).count()
        if active_superusers <= 1:
            messages.error(request, "No se puede desactivar el único superusuario activo.")
            return redirect("admin_dashboard")
    target.is_active = not target.is_active
    target.save(update_fields=("is_active",))
    state = "activada" if target.is_active else "desactivada"
    messages.success(request, f"La cuenta {target.get_username()} quedó {state}.")
    return redirect("admin_dashboard")


@user_passes_test(lambda user: user.is_active and user.is_superuser)
@require_POST
def delete_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "No puedes eliminar la cuenta con la que tienes la sesión abierta.")
        return redirect("admin_dashboard")
    if target.is_superuser and User.objects.filter(is_superuser=True).count() <= 1:
        messages.error(request, "No se puede eliminar el último superusuario.")
        return redirect("admin_dashboard")

    username = target.get_username()
    with transaction.atomic():
        # Remove assignments first because their request FK intentionally protects audit history.
        AppointmentAssignment.objects.filter(request__user=target).delete()
        target.delete()
    messages.success(request, f"Se eliminó la cuenta {username} y sus registros asociados.")
    return redirect("admin_dashboard")


CATALOG_TYPES = {
    "servicios": (MedicalService, MedicalServiceForm, "Servicios médicos"),
    "ips": (Institution, InstitutionForm, "Instituciones prestadoras"),
    "profesionales": (Professional, ProfessionalForm, "Profesionales"),
}


@user_passes_test(lambda user: user.is_active and user.is_staff)
@require_http_methods(["GET", "POST"])
def admin_catalog(request):
    catalog_forms = {
        "servicios": MedicalServiceForm(prefix="servicios"),
        "ips": InstitutionForm(prefix="ips"),
        "profesionales": ProfessionalForm(prefix="profesionales"),
    }
    if request.method == "POST":
        kind = request.POST.get("kind", "")
        config = CATALOG_TYPES.get(kind)
        if not config:
            messages.error(request, "Selecciona un tipo de registro válido.")
            return redirect("admin_catalog")
        model, form_class, _ = config
        form = form_class(request.POST, prefix=kind)
        if form.is_valid():
            form.save()
            messages.success(request, "El registro del catálogo quedó guardado.")
            return redirect("admin_catalog")
        catalog_forms[kind] = form

    return render(
        request,
        "appointments/admin_catalog.html",
        {
            "catalog_forms": catalog_forms,
            "services": MedicalService.objects.order_by("name"),
            "institutions": Institution.objects.order_by("name"),
            "professionals": Professional.objects.prefetch_related("services").order_by("full_name"),
        },
    )


@user_passes_test(lambda user: user.is_active and user.is_staff)
@require_http_methods(["GET", "POST"])
def edit_catalog_item(request, kind, object_id):
    config = CATALOG_TYPES.get(kind)
    if not config:
        messages.error(request, "Tipo de catálogo no válido.")
        return redirect("admin_catalog")
    model, form_class, label = config
    item = get_object_or_404(model, pk=object_id)
    form = form_class(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{label}: cambios guardados.")
        return redirect("admin_catalog")
    return render(
        request,
        "appointments/admin_catalog_edit.html",
        {"form": form, "item": item, "label": label},
    )


@user_passes_test(lambda user: user.is_active and user.is_staff)
@require_POST
def toggle_catalog_item(request, kind, object_id):
    config = CATALOG_TYPES.get(kind)
    if not config:
        messages.error(request, "Tipo de catálogo no válido.")
        return redirect("admin_catalog")
    model, _, label = config
    item = get_object_or_404(model, pk=object_id)
    item.is_active = not item.is_active
    item.save(update_fields=("is_active",))
    state = "activado" if item.is_active else "desactivado"
    messages.success(request, f"{label}: registro {state} para nuevas solicitudes.")
    return redirect("admin_catalog")


@user_passes_test(lambda user: user.is_active and user.is_staff)
@require_http_methods(["GET", "POST"])
def admin_schedule(request):
    selected_date = parse_date(request.GET.get("fecha", "")) or timezone.localdate()
    slot_form = AvailabilityRangeForm(initial={"appointment_date": selected_date})
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_range":
            slot_form = AvailabilityRangeForm(request.POST)
            selected_date = parse_date(request.POST.get("appointment_date", "")) or selected_date
            if slot_form.is_valid():
                data = slot_form.cleaned_data
                local_start = datetime.combine(data["appointment_date"], data["start_time"])
                local_end = datetime.combine(data["appointment_date"], data["end_time"])
                created_count = 0
                existing_count = 0
                with transaction.atomic():
                    starts_at = timezone.make_aware(local_start, timezone.get_current_timezone())
                    end_at = timezone.make_aware(local_end, timezone.get_current_timezone())
                    while starts_at < end_at:
                        _, created = AvailabilitySlot.objects.get_or_create(
                            professional=data["professional"],
                            starts_at=starts_at,
                            defaults={
                                "service": data["service"],
                                "institution": data["institution"],
                                "is_available": True,
                            },
                        )
                        created_count += int(created)
                        existing_count += int(not created)
                        starts_at += timedelta(minutes=APPOINTMENT_SLOT_MINUTES)
                if created_count:
                    messages.success(
                        request,
                        f"Se agregaron {created_count} bloques de 30 minutos a la agenda.",
                    )
                if existing_count:
                    messages.warning(
                        request,
                        f"Se omitieron {existing_count} bloques que ya existían para ese profesional.",
                    )
                return redirect(f"{reverse('admin_schedule')}?fecha={data['appointment_date'].isoformat()}")
        elif action == "toggle_slot":
            slot = get_object_or_404(
                AvailabilitySlot.objects.select_related("service", "institution", "professional"),
                pk=request.POST.get("slot_id"),
            )
            if AppointmentAssignment.objects.filter(slot=slot, state=AppointmentAssignment.State.ACTIVE).exists():
                messages.error(request, "Ese horario tiene una cita asignada. Cancela o reprograma la cita antes de cambiarlo.")
            elif slot.starts_at <= timezone.now() and not slot.is_available:
                messages.error(request, "No se puede volver a habilitar un horario que ya pasó.")
            elif not slot.is_available and not (
                slot.service.is_active and slot.institution.is_active and slot.professional.is_active
            ):
                messages.error(request, "Activa el servicio, la IPS y el profesional en Catálogo antes de habilitar este horario.")
            else:
                slot.is_available = not slot.is_available
                slot.save(update_fields=("is_available",))
                messages.success(request, "Se actualizó la disponibilidad del horario.")
            return redirect(f"{reverse('admin_schedule')}?fecha={selected_date.isoformat()}")
        else:
            messages.error(request, "Acción de agenda no válida.")
            return redirect(f"{reverse('admin_schedule')}?fecha={selected_date.isoformat()}")

    slots = AvailabilitySlot.objects.select_related(
        "service", "institution", "professional"
    ).annotate(
        active_assignment_count=Count(
            "assignments",
            filter=Q(assignments__state=AppointmentAssignment.State.ACTIVE),
            distinct=True,
        )
    ).prefetch_related(
        Prefetch(
            "assignments",
            queryset=AppointmentAssignment.objects.filter(
                state=AppointmentAssignment.State.ACTIVE
            ).select_related("request", "request__user"),
            to_attr="active_assignments",
        )
    )
    status_filter = request.GET.get("estado", "")
    if status_filter == "disponible":
        slots = slots.filter(
            is_available=True,
            starts_at__gte=timezone.now(),
            active_assignment_count=0,
            service__is_active=True,
            institution__is_active=True,
            professional__is_active=True,
        )
    elif status_filter == "asignado":
        slots = slots.filter(active_assignment_count__gt=0)
    elif status_filter == "deshabilitado":
        slots = slots.filter(is_available=False, active_assignment_count=0)
    slots = slots.filter(starts_at__date=selected_date)
    date_filter = selected_date.isoformat()
    query = request.GET.get("q", "").strip()
    if query:
        slots = slots.filter(
            Q(service__name__icontains=query)
            | Q(institution__name__icontains=query)
            | Q(professional__full_name__icontains=query)
            | Q(assignments__request__user__username__icontains=query)
        ).distinct()
    slot_list = list(slots.order_by("starts_at"))
    for slot in slot_list:
        slot.active_assignment = next(iter(slot.active_assignments), None)
        slot.is_past = slot.starts_at <= timezone.now()

    all_slots = AvailabilitySlot.objects.all()
    context = {
        "slot_form": slot_form,
        "slots": slot_list,
        "total_slots": all_slots.count(),
        "available_slots": all_slots.filter(
            is_available=True,
            starts_at__gte=timezone.now(),
            service__is_active=True,
            institution__is_active=True,
            professional__is_active=True,
        ).count(),
        "assigned_slots": AppointmentAssignment.objects.filter(state=AppointmentAssignment.State.ACTIVE).count(),
        "disabled_slots": all_slots.filter(is_available=False).count(),
        "selected_status": status_filter,
        "selected_date": date_filter,
        "selected_date_display": selected_date.strftime("%d/%m/%Y"),
        "previous_date": (selected_date - timedelta(days=1)).isoformat(),
        "next_date": (selected_date + timedelta(days=1)).isoformat(),
        "query": query,
    }
    return render(request, "appointments/admin_schedule.html", context)


@user_passes_test(lambda user: user.is_active and user.is_staff)
def appointment_requests(request):
    active_assignments = AppointmentAssignment.objects.filter(
        request_id=OuterRef("pk"), state=AppointmentAssignment.State.ACTIVE
    )
    all_requests = AppointmentRequest.objects.select_related(
        "user", "user__gesecit_profile", "service", "preferred_institution"
    ).prefetch_related(
        "assignments__slot__institution",
        "assignments__slot__professional",
        "assignments__slot__service",
    ).annotate(
        has_active_assignment=Exists(active_assignments),
        unread_patient_messages=Count(
            "communication_messages",
            filter=Q(
                communication_messages__from_staff=False,
                communication_messages__read_at__isnull=True,
            ),
            distinct=True,
        ),
    )
    request_items = all_requests

    selected_status = request.GET.get("estado", "")
    query = request.GET.get("q", "").strip()
    if selected_status in AppointmentRequest.Status.values:
        request_items = request_items.filter(status=selected_status)
    if query:
        search = (
            Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(user__gesecit_profile__demo_member_code__icontains=query)
            | Q(service__name__icontains=query)
        )
        try:
            search |= Q(reference=UUID(query))
        except ValueError:
            pass
        request_items = request_items.filter(search)

    selected_date = request.GET.get("fecha", "")
    parsed_date = parse_date(selected_date)
    if parsed_date:
        request_items = request_items.filter(created_at__date=parsed_date)

    appointment_date = request.GET.get("fecha_cita", "")
    parsed_appointment_date = parse_date(appointment_date)
    if parsed_appointment_date:
        request_items = request_items.filter(
            assignments__state=AppointmentAssignment.State.ACTIVE,
            assignments__slot__starts_at__date=parsed_appointment_date,
        )
    assignment_filter = request.GET.get("agenda", "")
    if assignment_filter == "programada":
        request_items = request_items.filter(has_active_assignment=True)
    elif assignment_filter == "pendiente":
        request_items = request_items.filter(has_active_assignment=False)

    for item in request_items:
        item.active_assignment = next(
            (
                assignment
                for assignment in item.assignments.all()
                if assignment.state == AppointmentAssignment.State.ACTIVE
            ),
            None,
        )

    context = {
        "requests": request_items,
        "status_choices": AppointmentRequest.Status.choices,
        "selected_status": selected_status,
        "query": query,
        "selected_date": selected_date,
        "selected_appointment_date": appointment_date,
        "selected_assignment_filter": assignment_filter,
        "total_requests": all_requests.count(),
        "pending_count": all_requests.filter(status=AppointmentRequest.Status.PENDING).count(),
        "review_count": all_requests.filter(status=AppointmentRequest.Status.IN_REVIEW).count(),
        "approved_count": all_requests.filter(status=AppointmentRequest.Status.APPROVED).count(),
        "rejected_count": all_requests.filter(status=AppointmentRequest.Status.REJECTED).count(),
        "scheduled_count": all_requests.filter(has_active_assignment=True).count(),
        "recent_activity": RequestStatusHistory.objects.select_related(
            "request", "request__user", "changed_by"
        )[:5],
    }
    return render(request, "appointments/appointment_requests.html", context)


@user_passes_test(lambda user: user.is_active and user.is_staff)
@require_POST
def request_availability(request, reference):
    appointment_request = get_object_or_404(
        AppointmentRequest.objects.select_related("service", "preferred_institution"),
        reference=reference,
    )
    selected_date = parse_date(request.POST.get("fecha", ""))
    if not selected_date:
        return JsonResponse({"error": "Selecciona una fecha válida."}, status=400)

    date_label = selected_date.strftime("%d/%m/%Y")
    business_hours = "Lunes a viernes · 08:00 a 17:00"
    if selected_date.weekday() not in BUSINESS_DAYS:
        return JsonResponse({
            "date": selected_date.isoformat(),
            "date_label": date_label,
            "business_hours": business_hours,
            "closed": True,
            "times": [],
        })

    professionals = list(
        Professional.objects.filter(
            is_active=True,
            services=appointment_request.service,
        ).order_by("full_name")
    )
    if appointment_request.preferred_institution_id:
        institutions = (
            [appointment_request.preferred_institution]
            if appointment_request.preferred_institution.is_active
            else []
        )
    else:
        first_institution = Institution.objects.filter(is_active=True).order_by("name").first()
        institutions = [first_institution] if first_institution else []

    notice = "Las horas libres se habilitan automáticamente; las citas reservadas aparecen como ocupadas."
    if not appointment_request.service.is_active:
        notice = "Este servicio está inactivo en Catálogo; actívalo antes de agendar."
    elif not professionals:
        notice = "No hay profesionales activos asociados a esta especialidad en Catálogo."
    elif not institutions:
        notice = "No hay una IPS activa disponible para esta solicitud."

    now = timezone.now()
    if appointment_request.service.is_active and professionals and institutions:
        with transaction.atomic():
            current = datetime.combine(selected_date, BUSINESS_START_TIME)
            end = datetime.combine(selected_date, BUSINESS_END_TIME)
            while current < end:
                starts_at = timezone.make_aware(current, timezone.get_current_timezone())
                if starts_at > now:
                    for professional in professionals:
                        AvailabilitySlot.objects.get_or_create(
                            professional=professional,
                            starts_at=starts_at,
                            defaults={
                                "service": appointment_request.service,
                                "institution": institutions[0],
                                "is_available": True,
                            },
                        )
                current += timedelta(minutes=APPOINTMENT_SLOT_MINUTES)

    slots = AvailabilitySlot.objects.filter(
        starts_at__date=selected_date,
    ).select_related("service", "institution", "professional").prefetch_related(
        Prefetch(
            "assignments",
            queryset=AppointmentAssignment.objects.filter(
                state=AppointmentAssignment.State.ACTIVE
            ),
            to_attr="active_assignments",
        )
    )
    slots_by_time = {}
    for slot in slots.order_by("starts_at", "professional__full_name"):
        slot_time = timezone.localtime(slot.starts_at).strftime("%H:%M")
        active_assignment = next(iter(slot.active_assignments), None)
        if active_assignment:
            state, state_label = "occupied", "Ocupado"
        elif slot.service_id != appointment_request.service_id or (
            appointment_request.preferred_institution_id
            and slot.institution_id != appointment_request.preferred_institution_id
        ):
            state, state_label = "unavailable", "No disponible para esta solicitud"
        elif slot.starts_at <= now:
            state, state_label = "past", "Hora pasada"
        elif slot.is_bookable:
            state, state_label = "available", "Disponible"
        else:
            state, state_label = "unavailable", "No disponible"
        slots_by_time.setdefault(slot_time, []).append({
            "state": state,
            "state_label": state_label,
            "slot_id": slot.pk if state == "available" else None,
            "label": f"{slot.professional.full_name} · {slot.institution.name}",
        })

    times = []
    current = datetime.combine(selected_date, BUSINESS_START_TIME)
    end = datetime.combine(selected_date, BUSINESS_END_TIME)
    while current < end:
        label = current.strftime("%H:%M")
        empty_state = "past" if timezone.make_aware(
            current, timezone.get_current_timezone()
        ) <= now else "empty"
        times.append({
            "time": label,
            "items": slots_by_time.get(label) or [{
                "state": empty_state,
                "state_label": "Hora pasada" if empty_state == "past" else "Sin cupo publicado",
                "slot_id": None,
                "label": "",
            }],
        })
        current += timedelta(minutes=APPOINTMENT_SLOT_MINUTES)

    return JsonResponse({
        "date": selected_date.isoformat(),
        "date_label": date_label,
        "business_hours": business_hours,
        "notice": notice,
        "closed": False,
        "times": times,
    })


@user_passes_test(lambda user: user.is_active and user.is_staff)
@require_http_methods(["GET", "POST"])
def manage_appointment_request(request, reference):
    appointment_request = get_object_or_404(
        AppointmentRequest.objects.select_related(
            "user", "user__gesecit_profile", "service", "preferred_institution"
        ).prefetch_related(
            "status_history__changed_by",
            "assignments__slot__institution",
            "assignments__slot__professional",
            "assignments__slot__service",
            "assignments__history__changed_by",
        ),
        reference=reference,
    )
    appointment_request.active_assignment = next(
        (
            assignment
            for assignment in appointment_request.assignments.all()
            if assignment.state == AppointmentAssignment.State.ACTIVE
        ),
        None,
    )
    selected_appointment_date = (
        parse_date(request.GET.get("fecha_cita", ""))
        or parse_date(request.POST.get("appointment_date", ""))
        or (
            timezone.localtime(appointment_request.active_assignment.slot.starts_at).date()
            if appointment_request.active_assignment
            else appointment_request.preferred_date
        )
        or timezone.localdate()
    )
    assignment_form = AppointmentAssignmentForm(
        appointment_request=appointment_request,
        selected_date=selected_appointment_date,
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "assign_slot":
            assignment_form = AppointmentAssignmentForm(
                request.POST,
                appointment_request=appointment_request,
                selected_date=selected_appointment_date,
            )
            if assignment_form.is_valid():
                try:
                    with transaction.atomic():
                        locked_request = AppointmentRequest.objects.select_for_update().get(pk=reference)
                        slot = AvailabilitySlot.objects.select_for_update().select_related(
                            "service", "institution", "professional"
                        ).get(pk=assignment_form.cleaned_data["slot"].pk)
                        if not slot.is_available or slot.starts_at <= timezone.now():
                            raise ValidationError("Ese horario ya no está disponible. Actualiza la página y selecciona otro.")
                        if slot.service_id != locked_request.service_id:
                            raise ValidationError("El horario debe corresponder al servicio solicitado.")
                        if locked_request.preferred_institution_id and slot.institution_id != locked_request.preferred_institution_id:
                            raise ValidationError("El horario no corresponde a la IPS preferida.")

                        previous_status = locked_request.status
                        locked_request.status = AppointmentRequest.Status.APPROVED
                        locked_request.save(update_fields=("status", "updated_at"))

                        previous = AppointmentAssignment.objects.select_for_update().filter(
                            request=locked_request, state=AppointmentAssignment.State.ACTIVE
                        ).select_related("slot").first()
                        if previous and previous.slot_id == slot.pk:
                            raise ValidationError("Ese horario ya está asignado a esta solicitud.")
                        if previous:
                            previous_slot = previous.slot
                            previous.state = AppointmentAssignment.State.REPLACED
                            previous.closed_at = timezone.now()
                            previous.save(update_fields=("state", "closed_at"))
                            if previous_slot.starts_at > timezone.now():
                                previous_slot.is_available = True
                                previous_slot.save(update_fields=("is_available",))
                            AssignmentHistory.objects.create(
                                assignment=previous,
                                event=AssignmentHistory.Event.RESCHEDULED,
                                detail=f"Reprogramada para {timezone.localtime(slot.starts_at):%d/%m/%Y %H:%M}.",
                                changed_by=request.user,
                            )

                        assignment = AppointmentAssignment(
                            request=locked_request,
                            slot=slot,
                            state=AppointmentAssignment.State.ACTIVE,
                            created_by=request.user,
                        )
                        assignment.full_clean()
                        assignment.save()
                        slot.is_available = False
                        slot.save(update_fields=("is_available",))
                        locked_request.save(update_fields=("updated_at",))
                        AssignmentHistory.objects.create(
                            assignment=assignment,
                            event=(
                                AssignmentHistory.Event.RESCHEDULED
                                if previous
                                else AssignmentHistory.Event.ASSIGNED
                            ),
                            detail=f"Cita asignada para {timezone.localtime(slot.starts_at):%d/%m/%Y %H:%M}.",
                            changed_by=request.user,
                        )
                        if previous_status != AppointmentRequest.Status.APPROVED:
                            RequestStatusHistory.objects.create(
                                request=locked_request,
                                previous_status=previous_status,
                                new_status=AppointmentRequest.Status.APPROVED,
                                note=(
                                    "Cita aprobada y agendada para "
                                    f"{timezone.localtime(slot.starts_at):%d/%m/%Y %H:%M}."
                                ),
                                changed_by=request.user,
                            )
                        Notification.objects.create(
                            user=locked_request.user,
                            request=locked_request,
                            assignment=assignment,
                            kind=Notification.Kind.ASSIGNMENT_CREATED,
                            title="Cita simulada agendada" if not previous else "Cita simulada reprogramada",
                            body=(
                                f"{locked_request.service.name}: "
                                f"{timezone.localtime(slot.starts_at):%d/%m/%Y %H:%M}, "
                                f"{slot.institution.name}, profesional {slot.professional.full_name}."
                            )[:240],
                        )
                    messages.success(
                        request,
                        "La solicitud quedó aprobada, la fecha y hora se registraron y el horario se reservó."
                        if not previous
                        else "La nueva fecha y hora quedaron registradas y el horario anterior se liberó.",
                    )
                    return redirect("manage_appointment_request", reference=reference)
                except ValidationError as error:
                    messages.error(request, " ".join(error.messages))
                except IntegrityError:
                    messages.error(request, "Ese horario acaba de ser asignado a otra solicitud.")
        elif action == "cancel_assignment":
            try:
                with transaction.atomic():
                    locked_request = AppointmentRequest.objects.select_for_update().get(pk=reference)
                    active = AppointmentAssignment.objects.select_for_update().filter(
                        request=locked_request, state=AppointmentAssignment.State.ACTIVE
                    ).select_related("slot").first()
                    if not active:
                        raise ValidationError("La solicitud no tiene una cita vigente que cancelar.")
                    active.state = AppointmentAssignment.State.CANCELLED
                    active.closed_at = timezone.now()
                    active.save(update_fields=("state", "closed_at"))
                    if active.slot.starts_at > timezone.now():
                        active.slot.is_available = True
                        active.slot.save(update_fields=("is_available",))
                    locked_request.save(update_fields=("updated_at",))
                    AssignmentHistory.objects.create(
                        assignment=active,
                        event=AssignmentHistory.Event.CANCELLED,
                        detail="Cita cancelada por administración.",
                        changed_by=request.user,
                    )
                    Notification.objects.create(
                        user=locked_request.user,
                        request=locked_request,
                        assignment=active,
                        kind=Notification.Kind.ASSIGNMENT_CANCELLED,
                        title="Cita simulada cancelada",
                        body=(
                            f"Se canceló la cita de {locked_request.service.name} del "
                            f"{timezone.localtime(active.slot.starts_at):%d/%m/%Y %H:%M}."
                        )[:240],
                    )
                messages.success(request, "La cita se canceló; el horario futuro volvió a estar disponible.")
                return redirect("manage_appointment_request", reference=reference)
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
        else:
            messages.error(request, "Acción no válida. Usa la agenda para gestionar la cita.")
            return redirect("manage_appointment_request", reference=reference)
    return render(
        request,
        "appointments/manage_appointment_request.html",
        {
            "appointment_request": appointment_request,
            "patient_profile": UserProfile.objects.filter(user=appointment_request.user).first(),
            "assignment_form": assignment_form,
            "selected_appointment_date": selected_appointment_date.isoformat(),
            "today_iso": timezone.localdate().isoformat(),
        },
    )
