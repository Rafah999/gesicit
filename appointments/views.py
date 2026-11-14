from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST, require_http_methods
from uuid import UUID

from .forms import PatientRegistrationForm, RequestStatusForm
from .models import (
    AppointmentAssignment,
    AppointmentRequest,
    Notification,
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
    context = {
        "users": users,
        "total_users": users.count(),
        "patient_count": users.filter(is_staff=False, is_superuser=False).count(),
        "admin_count": users.filter(is_staff=True, is_superuser=False).count(),
        "superuser_count": users.filter(is_superuser=True).count(),
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
    if target.is_superuser:
        messages.error(request, "Los permisos de una cuenta superusuario no se modifican desde esta pantalla.")
        return redirect("admin_dashboard")
    if new_role not in {"admin", "superuser"}:
        messages.error(request, "Selecciona un rol válido.")
        return redirect("admin_dashboard")

    with transaction.atomic():
        target.is_staff = True
        target.is_superuser = new_role == "superuser"
        target.save(update_fields=("is_staff", "is_superuser"))
        profile, _ = UserProfile.objects.get_or_create(user=target)
        profile.role = (
            UserProfile.Role.ADMINISTRATOR
            if target.is_superuser
            else UserProfile.Role.ADMIN_STAFF
        )
        profile.save(update_fields=("role",))

    role_name = "superusuario" if target.is_superuser else "administrador"
    messages.success(request, f"{target.get_username()} ahora tiene el rol de {role_name}.")
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
    target.delete()
    messages.success(request, f"Se eliminó la cuenta {username} y sus registros asociados.")
    return redirect("admin_dashboard")


@user_passes_test(lambda user: user.is_active and user.is_staff)
def appointment_requests(request):
    all_requests = AppointmentRequest.objects.select_related(
        "user", "user__gesecit_profile", "service", "preferred_institution"
    ).prefetch_related(
        "assignments__slot__institution",
        "assignments__slot__professional",
        "assignments__slot__service",
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
        "total_requests": all_requests.count(),
        "pending_count": all_requests.filter(status=AppointmentRequest.Status.PENDING).count(),
        "review_count": all_requests.filter(status=AppointmentRequest.Status.IN_REVIEW).count(),
        "approved_count": all_requests.filter(status=AppointmentRequest.Status.APPROVED).count(),
        "rejected_count": all_requests.filter(status=AppointmentRequest.Status.REJECTED).count(),
        "recent_activity": RequestStatusHistory.objects.select_related(
            "request", "request__user", "changed_by"
        )[:5],
    }
    return render(request, "appointments/appointment_requests.html", context)


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

    if request.method == "POST":
        form = RequestStatusForm(request.POST, instance=appointment_request)
        old_status = appointment_request.status
        if form.is_valid():
            new_status = form.cleaned_data["status"]
            if new_status != old_status:
                if (
                    appointment_request.active_assignment
                    and new_status != AppointmentRequest.Status.APPROVED
                ):
                    messages.error(
                        request,
                        "Cancela la asignación vigente antes de cambiar el estado de esta solicitud.",
                    )
                else:
                    with transaction.atomic():
                        updated_request = form.save()
                        RequestStatusHistory.objects.create(
                            request=updated_request,
                            previous_status=old_status,
                            new_status=new_status,
                            note=form.cleaned_data["note"],
                            changed_by=request.user,
                        )
                        Notification.objects.create(
                            user=updated_request.user,
                            request=updated_request,
                            kind=Notification.Kind.REQUEST_UPDATED,
                            title="Actualización de solicitud",
                            body=(
                                f"Tu solicitud de {updated_request.service.name} cambió a "
                                f"{updated_request.get_status_display()}."
                            ),
                        )
                    messages.success(request, "Se actualizó el estado y quedó en el historial.")
                    return redirect("manage_appointment_request", reference=reference)
            else:
                messages.info(request, "La solicitud conserva el mismo estado.")
                return redirect("manage_appointment_request", reference=reference)
    else:
        form = RequestStatusForm(instance=appointment_request)

    return render(
        request,
        "appointments/manage_appointment_request.html",
        {
            "appointment_request": appointment_request,
            "patient_profile": UserProfile.objects.filter(user=appointment_request.user).first(),
            "form": form,
        },
    )
