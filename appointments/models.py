"""Esquema inicial inspirado en el modelo conceptual de GESECIT."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class UserProfile(models.Model):
    class Role(models.TextChoices):
        AFFILIATE = "affiliate", "Afiliado"
        ADMIN_STAFF = "admin_staff", "Personal administrativo"
        ADMINISTRATOR = "administrator", "Administrador"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gesecit_profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AFFILIATE)
    demo_member_code = models.CharField("código ficticio de afiliado", max_length=24, blank=True)
    phone = models.CharField("teléfono de contacto", max_length=24, blank=True)

    class Meta:
        verbose_name = "perfil de usuario"
        verbose_name_plural = "perfiles de usuario"

    def __str__(self):
        return f"{self.user.get_username()} · {self.get_role_display()}"


class Institution(models.Model):
    name = models.CharField("nombre de la IPS", max_length=120, unique=True)
    city = models.CharField("ciudad", max_length=80, blank=True)
    address = models.CharField("dirección simulada", max_length=160, blank=True)
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "IPS"
        verbose_name_plural = "IPS"

    def __str__(self):
        return self.name


class MedicalService(models.Model):
    name = models.CharField("servicio o especialidad", max_length=100, unique=True)
    description = models.CharField("descripción", max_length=240, blank=True)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "servicio médico"
        verbose_name_plural = "servicios médicos"

    def __str__(self):
        return self.name


class Professional(models.Model):
    full_name = models.CharField("nombre ficticio del profesional", max_length=120)
    services = models.ManyToManyField(MedicalService, related_name="professionals", verbose_name="servicios")
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("full_name",)
        verbose_name = "profesional"
        verbose_name_plural = "profesionales"

    def __str__(self):
        return self.full_name


class AvailabilitySlot(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name="availability_slots")
    service = models.ForeignKey(MedicalService, on_delete=models.PROTECT, related_name="availability_slots")
    professional = models.ForeignKey(Professional, on_delete=models.PROTECT, related_name="availability_slots")
    starts_at = models.DateTimeField("fecha y hora de inicio")
    is_available = models.BooleanField("disponible", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("starts_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("professional", "starts_at"),
                name="unique_professional_slot_time",
            ),
        ]
        verbose_name = "horario"
        verbose_name_plural = "horarios y disponibilidad"

    def __str__(self):
        return f"{self.service} · {self.starts_at:%d/%m/%Y %H:%M} · {self.institution} · {self.professional}"

    @property
    def is_bookable(self):
        return (
            self.is_available
            and self.starts_at > timezone.now()
            and self.service.is_active
            and self.institution.is_active
            and self.professional.is_active
        )

    def clean(self):
        super().clean()
        if self.professional_id and self.service_id:
            if not self.professional.services.filter(pk=self.service_id).exists():
                raise ValidationError({"professional": "El profesional debe estar asociado al servicio seleccionado."})


class AppointmentRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IN_REVIEW = "in_review", "En revisión"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"

    reference = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appointment_requests",
    )
    service = models.ForeignKey(MedicalService, on_delete=models.PROTECT, related_name="requests")
    preferred_institution = models.ForeignKey(
        Institution,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="requests",
    )
    preferred_date = models.DateField("fecha preferida", null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "solicitud de cita"
        verbose_name_plural = "solicitudes de cita"

    def __str__(self):
        return f"{self.service} · {str(self.reference)[:8]}"


class RequestStatusHistory(models.Model):
    request = models.ForeignKey(AppointmentRequest, on_delete=models.CASCADE, related_name="status_history")
    previous_status = models.CharField(max_length=16, blank=True)
    new_status = models.CharField(max_length=16, choices=AppointmentRequest.Status.choices)
    note = models.CharField("observación administrativa", max_length=200, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("changed_at",)
        verbose_name = "cambio de estado"
        verbose_name_plural = "historial de estados"

    def __str__(self):
        return f"{self.request} · {self.get_new_status_display()}"


class AppointmentAssignment(models.Model):
    class State(models.TextChoices):
        ACTIVE = "active", "Vigente"
        CANCELLED = "cancelled", "Cancelada"
        REPLACED = "replaced", "Reprogramada"

    request = models.ForeignKey(AppointmentRequest, on_delete=models.PROTECT, related_name="assignments")
    slot = models.ForeignKey(AvailabilitySlot, on_delete=models.PROTECT, related_name="assignments")
    state = models.CharField(max_length=12, choices=State.choices, default=State.ACTIVE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("request",),
                condition=Q(state="active"),
                name="one_active_assignment_per_request",
            ),
            models.UniqueConstraint(
                fields=("slot",),
                condition=Q(state="active"),
                name="one_active_assignment_per_slot",
            ),
        ]
        verbose_name = "asignación simulada"
        verbose_name_plural = "asignaciones simuladas"

    def __str__(self):
        return f"{self.request} · {self.get_state_display()}"

    def clean(self):
        super().clean()
        errors = {}
        if self.request_id and self.slot_id:
            if self.request.service_id != self.slot.service_id:
                errors["slot"] = "El horario debe corresponder al servicio de la solicitud."
            if self.request.preferred_institution_id and self.request.preferred_institution_id != self.slot.institution_id:
                errors["slot"] = "El horario no corresponde a la IPS preferida."
        if self.state == self.State.ACTIVE and self.request_id:
            if self.request.status != AppointmentRequest.Status.APPROVED:
                errors["state"] = "Solo se puede asignar una solicitud aprobada."
        if errors:
            raise ValidationError(errors)


class AssignmentHistory(models.Model):
    class Event(models.TextChoices):
        ASSIGNED = "assigned", "Asignación registrada"
        RESCHEDULED = "rescheduled", "Reprogramación"
        CANCELLED = "cancelled", "Cancelación"

    assignment = models.ForeignKey(AppointmentAssignment, on_delete=models.CASCADE, related_name="history")
    event = models.CharField(max_length=16, choices=Event.choices)
    detail = models.CharField("detalle", max_length=200, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        verbose_name = "evento de asignación"
        verbose_name_plural = "historial de asignaciones"


class Notification(models.Model):
    class Kind(models.TextChoices):
        REQUEST_CREATED = "request_created", "Solicitud registrada"
        REQUEST_UPDATED = "request_updated", "Actualización de solicitud"
        ASSIGNMENT_CREATED = "assignment_created", "Asignación simulada"
        ASSIGNMENT_CANCELLED = "assignment_cancelled", "Asignación cancelada"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gesecit_notifications")
    request = models.ForeignKey(
        AppointmentRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
    )
    assignment = models.ForeignKey(
        AppointmentAssignment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    title = models.CharField(max_length=100)
    body = models.CharField(max_length=240)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "notificación interna"
        verbose_name_plural = "notificaciones internas"

    def __str__(self):
        return self.title

# Mensajes administrativos asociados a una solicitud, sin alterar sus estados.
class RequestMessage(models.Model):
    request = models.ForeignKey(AppointmentRequest, on_delete=models.CASCADE, related_name="communication_messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="sent_request_messages")
    from_staff = models.BooleanField(default=False)
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return f"Mensaje de solicitud {self.request_id}"

class RequestPatientDetails(models.Model):
    request = models.OneToOneField(AppointmentRequest, on_delete=models.CASCADE, related_name="patient_details")
    full_name = models.CharField("nombre completo del paciente", max_length=150, blank=True)
    document_type = models.CharField("tipo de documento", max_length=2, choices=[("CC", "Cédula de ciudadanía"), ("TI", "Tarjeta de identidad"), ("CE", "Cédula de extranjería")])
    document_number = models.CharField("número de documento", max_length=12, blank=True)
    contact_phone = models.CharField("teléfono de contacto", max_length=24, blank=True)
    guardian_name = models.CharField("nombre del acudiente", max_length=150, blank=True)

    @property
    def masked_document(self):
        return "•" * max(0, len(self.document_number) - 4) + self.document_number[-4:]
