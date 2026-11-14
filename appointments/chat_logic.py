"""Intenciones predefinidas y conversación guiada; no usa IA generativa."""

import unicodedata
from datetime import datetime

from django.utils import timezone

from .models import (
    AppointmentRequest,
    AvailabilitySlot,
    Institution,
    MedicalService,
    Notification,
    RequestStatusHistory,
)


def normalize(value):
    value = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in value if not unicodedata.combining(char)).strip()


def welcome_message():
    return (
        "¡Hola! Soy GESECIT, un asistente digital académico basado en opciones y reglas. "
        "Puedo ayudarte a registrar una solicitud simulada, revisar su estado o ver horarios "
        "ficticios. Elige una opción o escribe lo que necesitas. No soy personal médico y "
        "no confirmo citas reales."
    )


def _request_summary(user):
    requests = AppointmentRequest.objects.filter(user=user).select_related("service")[:5]
    if not requests:
        return "Aún no tienes solicitudes registradas. Escribe «solicitar cita» para iniciar una."
    lines = ["Estas son tus solicitudes recientes:"]
    for item in requests:
        lines.append(
            f"• {str(item.reference)[:8].upper()} — {item.service.name} — "
            f"{item.get_status_display()}"
        )
    return "\n".join(lines)


def _catalog_options(queryset):
    values = list(queryset.values_list("name", flat=True)[:8])
    return ", ".join(values) if values else ""


def _find_named_record(queryset, message):
    value = normalize(message)
    for record in queryset:
        if normalize(record.name) == value:
            return record
    return None


def _availability_summary():
    slots = AvailabilitySlot.objects.filter(
        is_available=True,
        starts_at__gte=timezone.now(),
        service__is_active=True,
        institution__is_active=True,
        professional__is_active=True,
    ).select_related("service", "institution", "professional").order_by("starts_at")[:5]
    if not slots:
        return "Aún no hay horarios simulados disponibles en el catálogo. El personal autorizado puede cargarlos desde Administración."
    lines = ["Horarios ficticios próximos (no son cupos reales):"]
    for slot in slots:
        lines.append(
            f"• {slot.service.name} — {slot.starts_at:%d/%m/%Y %I:%M %p} — "
            f"{slot.institution.name} — {slot.professional.full_name}"
        )
    return "\n".join(lines)


def reply_to_message(user, message, flow=None):
    """Devuelve (respuesta, estado_del_flujo)."""
    raw = message.strip()
    text = normalize(raw)
    flow = flow or {}

    if text in {"cancelar", "salir", "reiniciar"}:
        return "Listo, cerré el paso actual. Puedes iniciar otra opción cuando quieras.", {}

    if flow.get("step") == "service":
        services = MedicalService.objects.filter(is_active=True).order_by("name")
        service = _find_named_record(services, raw)
        if not service:
            options = _catalog_options(services)
            if not options:
                return "Todavía no hay servicios cargados. El administrador debe registrar servicios ficticios antes de iniciar solicitudes.", {}
            return f"No encontré ese servicio. Elige uno de estos: {options}.", flow
        institutions = Institution.objects.filter(
            is_active=True,
            availability_slots__service=service,
            availability_slots__is_available=True,
            availability_slots__starts_at__gte=timezone.now(),
        ).distinct().order_by("name")
        options = _catalog_options(institutions)
        if options:
            return (
                f"Seleccionaste {service.name}. ¿Qué IPS prefieres? Opciones con disponibilidad simulada: {options}. "
                "También puedes escribir «omitir».",
                {"step": "institution", "service_id": service.pk},
            )
        return (
            f"Seleccionaste {service.name}. ¿Qué fecha prefieres? Escribe AAAA-MM-DD o «omitir». "
            "La fecha no reserva un horario.",
            {"step": "preferred_date", "service_id": service.pk},
        )

    if flow.get("step") == "institution":
        service = MedicalService.objects.filter(pk=flow.get("service_id"), is_active=True).first()
        if not service:
            return "No pude continuar esa solicitud. Escribe «solicitar cita» para empezar de nuevo.", {}
        institution_id = None
        if text not in {"omitir", "sin preferencia", "cualquiera"}:
            institutions = Institution.objects.filter(
                is_active=True,
                availability_slots__service=service,
                availability_slots__is_available=True,
                availability_slots__starts_at__gte=timezone.now(),
            ).distinct()
            institution = _find_named_record(institutions, raw)
            if not institution:
                options = _catalog_options(institutions)
                return f"No encontré esa IPS. Elige una de estas o escribe «omitir»: {options or 'no hay IPS disponibles'}.", flow
            institution_id = institution.pk
        institution_text = f" para {Institution.objects.get(pk=institution_id).name}" if institution_id else ""
        return (
            f"¿Qué fecha prefieres{institution_text}? Escribe AAAA-MM-DD o «omitir». "
            "Esto no reserva un horario.",
            {"step": "preferred_date", "service_id": service.pk, "institution_id": institution_id},
        )

    if flow.get("step") == "preferred_date":
        preferred_date = None
        if text not in {"omitir", "sin fecha", "no importa", "cualquiera"}:
            parsed = None
            for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    parsed = datetime.strptime(raw, date_format).date()
                    break
                except ValueError:
                    continue
            if parsed is None:
                return "No pude leer esa fecha. Usa AAAA-MM-DD, DD/MM/AAAA o escribe «omitir».", flow
            if parsed < timezone.localdate():
                return "La fecha no puede estar en el pasado. Intenta otra o escribe «omitir».", flow
            preferred_date = parsed

        service = MedicalService.objects.filter(pk=flow.get("service_id"), is_active=True).first()
        if not service:
            return "El servicio ya no está disponible. Escribe «solicitar cita» para empezar de nuevo.", {}
        institution = None
        if flow.get("institution_id"):
            institution = Institution.objects.filter(pk=flow["institution_id"], is_active=True).first()
        created_request = AppointmentRequest.objects.create(
            user=user,
            service=service,
            preferred_institution=institution,
            preferred_date=preferred_date,
        )
        RequestStatusHistory.objects.create(
            request=created_request,
            new_status=created_request.status,
            changed_by=user,
        )
        Notification.objects.create(
            user=user,
            request=created_request,
            kind=Notification.Kind.REQUEST_CREATED,
            title="Solicitud registrada",
            body=f"Tu solicitud de {service.name} quedó pendiente de revisión.",
        )
        date_text = f" Fecha preferida: {preferred_date:%d/%m/%Y}." if preferred_date else ""
        return (
            f"Solicitud {str(created_request.reference)[:8].upper()} registrada como «Pendiente»."
            f"{date_text} Es simulada; todavía no es una cita confirmada. Puedes consultar su estado aquí o escribir «mis solicitudes».",
            {},
        )

    if any(word in text for word in ("mis solicitudes", "estado", "seguimiento", "historial", "mis citas")):
        return _request_summary(user), {}

    if any(word in text for word in ("disponibilidad", "horario", "horarios", "cupo", "cupos", "ver disponibilidad")):
        return _availability_summary(), {}

    if any(word in text for word in ("solicitar", "agendar", "necesito cita", "quiero cita", "cita medica")):
        services = MedicalService.objects.filter(is_active=True).order_by("name")
        options = _catalog_options(services)
        if not options:
            return "Aún no hay servicios ficticios en el catálogo. Cuando se carguen, podrás iniciar la solicitud desde aquí.", {}
        return f"¿Qué servicio o especialidad necesitas? Opciones: {options}.", {"step": "service"}

    if any(word in text for word in ("ayuda", "hola", "buenos dias", "buenas tardes", "buenas noches")):
        return welcome_message(), {}

    return "No entendí esa opción. Puedes solicitar cita, consultar el estado, ver disponibilidad o pedir ayuda.", {}
