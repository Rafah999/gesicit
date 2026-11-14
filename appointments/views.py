from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from uuid import UUID

from .chat_logic import reply_to_message, welcome_message
from .forms import (
    AppointmentAssignmentForm,
    PatientProfileForm,
    PatientRegistrationForm,
    RequestStatusForm,
)
from .models import (
    AppointmentAssignment,
    AppointmentRequest,
    AssignmentHistory,
    AvailabilitySlot,
    Notification,
    RequestStatusHistory,
)


def register(request):
    if request.user.is_authenticated:
        return redirect("chat")
    form = PatientRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="appointments.auth_backends.EmailOrUsernameBackend")
        messages.success(request, "Tu cuenta quedó creada. Ya puedes gestionar tus solicitudes de cita.")
        return redirect("chat")
    return render(request, "registration/register.html", {"form": form})


@login_required
def profile(request):
    form = PatientProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tus datos de contacto se actualizaron correctamente.")
        return redirect("profile")
    return render(request, "appointments/profile.html", {"form": form})


@login_required
def chat(request):
    session_key = "gesecit_chat_messages"
    flow_key = "gesecit_chat_flow"
    if request.method == "POST":
        action = request.POST.get("action", "message")
        if action == "reset":
            request.session.pop(flow_key, None)
            request.session[session_key] = [{"speaker": "assistant", "text": welcome_message()}]
        else:
            text = request.POST.get("message", "").strip()
            if text:
                history = request.session.get(session_key, [])
                history.append({"speaker": "user", "text": text[:500]})
                answer, flow = reply_to_message(
                    request.user,
                    text[:500],
                    request.session.get(flow_key, {}),
                )
                history.append({"speaker": "assistant", "text": answer})
                request.session[session_key] = history[-40:]
                request.session[flow_key] = flow
            else:
                messages.error(request, "Escribe un mensaje para continuar.")
        return redirect("chat")

    history = request.session.get(session_key)
    if not history:
        history = [{"speaker": "assistant", "text": welcome_message()}]
        request.session[session_key] = history
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return render(
        request,
        "appointments/chat.html",
        {"chat_messages": history, "unread_count": unread_count},
    )


@login_required
def my_requests(request):
    requests = AppointmentRequest.objects.filter(user=request.user).select_related(
        "service", "preferred_institution"
    ).prefetch_related("assignments__slot__institution", "assignments__slot__professional")
    return render(request, "appointments/my_requests.html", {"requests": requests})


@login_required
def notifications(request):
    items = Notification.objects.filter(user=request.user).select_related("request", "assignment")
    return render(request, "appointments/notifications.html", {"notifications": items})


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    item = get_object_or_404(Notification, pk=notification_id, user=request.user)
    item.is_read = True
    item.save(update_fields=("is_read",))
    return redirect("notifications")


@staff_member_required
def staff_requests(request):
    selected_status = request.GET.get("estado", "")
    query = request.GET.get("q", "").strip()
    requests = AppointmentRequest.objects.select_related(
        "user", "service", "preferred_institution"
    ).prefetch_related("assignments__slot__institution", "assignments__slot__professional")
    if selected_status in AppointmentRequest.Status.values:
        requests = requests.filter(status=selected_status)
    if query:
        search_filter = (
            Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
        )
        try:
            search_filter |= Q(reference=UUID(query))
        except ValueError:
            pass
        requests = requests.filter(search_filter)
    requested_date = parse_date(request.GET.get("fecha", ""))
    if requested_date:
        requests = requests.filter(created_at__date=requested_date)

    for item in requests:
        item.active_assignment = next(
            (assignment for assignment in item.assignments.all() if assignment.state == AppointmentAssignment.State.ACTIVE),
            None,
        )
        item.assignment_form = AppointmentAssignmentForm(appointment_request=item)
        item.assignment_form.fields["slot"].widget.attrs.update(
            {"id": f"slot-{item.reference}", "aria-label": f"Horario para solicitud {str(item.reference)[:8]}"}
        )

    counts = dict(
        AppointmentRequest.objects.values("status").annotate(total=Count("reference")).values_list("status", "total")
    )
    total_requests = sum(counts.values())
    context = {
        "requests": requests,
        "status_choices": AppointmentRequest.Status.choices,
        "selected_status": selected_status,
        "query": query,
        "total_requests": total_requests,
        "pending_count": counts.get(AppointmentRequest.Status.PENDING, 0),
        "review_count": counts.get(AppointmentRequest.Status.IN_REVIEW, 0),
        "approved_count": counts.get(AppointmentRequest.Status.APPROVED, 0),
        "rejected_count": counts.get(AppointmentRequest.Status.REJECTED, 0),
        "unread_notifications": Notification.objects.filter(is_read=False).count(),
        "recent_activity": RequestStatusHistory.objects.select_related("request", "changed_by").order_by("-changed_at")[:4],
    }
    return render(request, "appointments/staff_requests.html", context)


@staff_member_required
@require_POST
def update_request_status(request, reference):
    appointment_request = get_object_or_404(AppointmentRequest, reference=reference)
    form = RequestStatusForm(request.POST, instance=appointment_request)
    old_status = appointment_request.status
    if form.is_valid():
        new_status = form.cleaned_data["status"]
        if new_status != old_status and new_status != AppointmentRequest.Status.APPROVED:
            has_active_assignment = appointment_request.assignments.filter(
                state=AppointmentAssignment.State.ACTIVE
            ).exists()
            if has_active_assignment:
                messages.error(request, "Cancela la asignación simulada antes de cambiar el estado de la solicitud.")
                return redirect("staff_requests")
        updated_request = form.save()
        if updated_request.status != old_status:
            note = form.cleaned_data["note"]
            RequestStatusHistory.objects.create(
                request=updated_request,
                previous_status=old_status,
                new_status=updated_request.status,
                note=note,
                changed_by=request.user,
            )
            Notification.objects.create(
                user=updated_request.user,
                request=updated_request,
                kind=Notification.Kind.REQUEST_UPDATED,
                title="Actualización de solicitud",
                body=f"Tu solicitud de {updated_request.service.name} cambió a {updated_request.get_status_display()}.",
            )
            messages.success(request, "Se actualizó el estado y quedó en el historial.")
        else:
            messages.info(request, "La solicitud conserva el mismo estado.")
    else:
        messages.error(request, "No se pudo actualizar el estado.")
    return redirect("staff_requests")


@staff_member_required
@require_POST
def assign_slot(request, reference):
    appointment_request = get_object_or_404(
        AppointmentRequest.objects.select_related("service", "preferred_institution"),
        reference=reference,
    )
    if appointment_request.status != AppointmentRequest.Status.APPROVED:
        messages.error(request, "Primero debes aprobar la solicitud para registrar una asignación simulada.")
        return redirect("staff_requests")
    if appointment_request.assignments.filter(state=AppointmentAssignment.State.ACTIVE).exists():
        messages.error(request, "Esta solicitud ya tiene una asignación vigente. Cancélala antes de reprogramarla.")
        return redirect("staff_requests")

    form = AppointmentAssignmentForm(request.POST, appointment_request=appointment_request)
    if not form.is_valid():
        messages.error(request, "Selecciona un horario disponible para esa solicitud.")
        return redirect("staff_requests")

    try:
        with transaction.atomic():
            slot = AvailabilitySlot.objects.select_for_update().get(pk=form.cleaned_data["slot"].pk)
            if not slot.is_available or slot.starts_at < timezone.now():
                messages.error(request, "El horario ya no está disponible. Actualiza la página y selecciona otro.")
                return redirect("staff_requests")
            slot.is_available = False
            slot.save(update_fields=("is_available",))
            assignment = AppointmentAssignment.objects.create(
                request=appointment_request,
                slot=slot,
                state=AppointmentAssignment.State.ACTIVE,
                created_by=request.user,
            )
            AssignmentHistory.objects.create(
                assignment=assignment,
                event=AssignmentHistory.Event.ASSIGNED,
                changed_by=request.user,
            )
            Notification.objects.create(
                user=appointment_request.user,
                request=appointment_request,
                assignment=assignment,
                kind=Notification.Kind.ASSIGNMENT_CREATED,
                title="Asignación simulada registrada",
                body=f"Se registró una opción simulada para {slot.service.name} el {slot.starts_at:%d/%m/%Y %H:%M}.",
            )
    except (AvailabilitySlot.DoesNotExist, IntegrityError):
        messages.error(request, "No fue posible asignar el horario. Puede que otro proceso ya lo haya ocupado.")
        return redirect("staff_requests")

    messages.success(request, "La asignación simulada quedó registrada; no es una cita oficial.")
    return redirect("staff_requests")


@staff_member_required
@require_POST
def cancel_assignment(request, assignment_id):
    assignment = get_object_or_404(
        AppointmentAssignment.objects.select_related("request", "slot"),
        pk=assignment_id,
        state=AppointmentAssignment.State.ACTIVE,
    )
    with transaction.atomic():
        assignment.state = AppointmentAssignment.State.CANCELLED
        assignment.closed_at = timezone.now()
        assignment.save(update_fields=("state", "closed_at"))
        slot = AvailabilitySlot.objects.select_for_update().get(pk=assignment.slot_id)
        slot.is_available = True
        slot.save(update_fields=("is_available",))
        AssignmentHistory.objects.create(
            assignment=assignment,
            event=AssignmentHistory.Event.CANCELLED,
            detail="Cancelación registrada desde el panel administrativo.",
            changed_by=request.user,
        )
        Notification.objects.create(
            user=assignment.request.user,
            request=assignment.request,
            assignment=assignment,
            kind=Notification.Kind.ASSIGNMENT_CANCELLED,
            title="Asignación simulada cancelada",
            body=f"La opción simulada de {assignment.slot.service.name} fue cancelada.",
        )
    messages.success(request, "Se canceló la asignación simulada y el horario volvió a estar disponible.")
    return redirect("staff_requests")
