"""Registro guiado con identidad, preferencia de IPS real y confirmación explícita."""
import re
from datetime import datetime
from django.utils import timezone
from .chat_logic import normalize, welcome_message, _request_summary
from .institution_catalog import selectable_institutions
from .models import MedicalService, AppointmentRequest, RequestPatientDetails, RequestStatusHistory, Notification, AvailabilitySlot

DOCUMENT_OPTIONS = ['CC · Cédula de ciudadanía', 'TI · Tarjeta de identidad', 'CE · Cédula de extranjería']

def options_for_flow(user, flow):
    step = flow.get('step')
    if step == 'document_type': return DOCUMENT_OPTIONS
    if step == 'service': return list(MedicalService.objects.filter(is_active=True).order_by('name').values_list('name',flat=True)[:20])
    if step == 'institution': return list(selectable_institutions().values_list('name',flat=True)) + ['Sin preferencia']
    if step == 'preferred_date': return ['Sin preferencia de fecha']
    if step == 'confirmation': return ['Confirmar solicitud', 'Corregir datos', 'Cancelar']
    return []

def reply_to_message(user, message, flow=None):
    raw=message.strip(); text=normalize(raw); flow=dict(flow or {}); step=flow.get('step')
    if text in {'cancelar','salir','reiniciar'}:
        return 'Proceso cancelado. No se registró una nueva solicitud. Puedes empezar de nuevo cuando quieras.', {}
    if text == 'corregir datos':
        return 'Vamos a revisar los datos desde el inicio. ¿Qué tipo de documento tiene el paciente: CC, TI o CE?', {'step':'document_type'}
    if step in {'contact_phone', 'patient_name', 'guardian_name'}:

        return 'Actualizamos el formulario: selecciona CC, TI o CE; después te pediré únicamente el número del documento.', {'step':'document_type'}
    if step == 'document_type':
        aliases = {
            'CC': {'cc','cedula','cedula de ciudadania',normalize(DOCUMENT_OPTIONS[0])},
            'TI': {'ti','tarjeta de identidad',normalize(DOCUMENT_OPTIONS[1])},
            'CE': {'ce','cedula de extranjeria','extranjeria','extranjero',normalize(DOCUMENT_OPTIONS[2])},
        }
        doc = next((kind for kind, names in aliases.items() if text in names), None)
        if not doc:
            return 'Selecciona CC (cédula de ciudadanía), TI (tarjeta de identidad) o CE (cédula de extranjería).', flow
        return f'Escribe el número de {doc}, sin puntos ni espacios. Usa un número de prueba para esta demostración.', {'step':'document_number','document_type':doc}
    if step == 'document_number':
        if flow.get('document_type') not in {'CC','TI','CE'}:
            return 'Selecciona el tipo de documento: CC, TI o CE.', {'step':'document_type'}
        if not re.fullmatch(r'[0-9]{5,12}', raw):
            return 'Escribe entre 5 y 12 dígitos, sin letras, puntos ni espacios. Solo se valida el formato.', flow
        if not MedicalService.objects.filter(is_active=True).exists():
            return 'El catálogo aún no tiene especialidades activas. Intenta nuevamente cuando esté disponible.', {}
        return '¿Qué servicio o especialidad necesitas? Selecciona una opción.', {'step':'service','document_type':flow['document_type'],'document_number':raw}
    if step == 'service':
        service=next((s for s in MedicalService.objects.filter(is_active=True) if normalize(s.name)==text),None)
        if not service: return 'Selecciona una especialidad de las opciones disponibles.',flow
        return ('¿Qué IPS de Cartagena prefieres? Las instituciones del catálogo son reales. Se registra únicamente tu preferencia; administración debe validar el servicio y la cobertura. No se consulta su agenda ni se acredita convenio con tu EPS.',{**flow,'step':'institution','service_id':service.pk})
    if step == 'institution':
        institution=None
        if text not in {'sin preferencia','omitir','cualquiera'}:
            institution=next((i for i in selectable_institutions() if normalize(i.name)==text),None)
            if not institution: return 'Selecciona una IPS del catálogo o «Sin preferencia».',flow
        return '¿Qué fecha prefieres? Usa DD/MM/AAAA o AAAA-MM-DD, o selecciona «Sin preferencia de fecha». Esto no reserva un horario.',{**flow,'step':'preferred_date','institution_id':institution.pk if institution else None}
    if step == 'preferred_date':
        date=None
        if text not in {'sin preferencia de fecha','sin preferencia','omitir'}:
            for fmt in ('%d/%m/%Y','%Y-%m-%d'):
                try: date=datetime.strptime(raw,fmt).date();break
                except ValueError: pass
            if date is None or date < timezone.localdate(): return 'Ingresa una fecha de hoy o futura en DD/MM/AAAA o AAAA-MM-DD, o selecciona «Sin preferencia de fecha».',flow
        service=MedicalService.objects.filter(pk=flow.get('service_id'),is_active=True).first()
        institution=selectable_institutions().filter(pk=flow.get('institution_id')).first()
        if not service or not all(flow.get(k) for k in ('document_type','document_number')):
            return 'La solicitud anterior debe iniciarse de nuevo. Selecciona el tipo de documento: CC, TI o CE.',{'step':'document_type'}
        summary = (
            f"Revisa tu solicitud antes de enviarla:\nTipo de documento: {flow['document_type']}"
            f"\nNúmero de documento: {'•' * max(0, len(flow['document_number']) - 4) + flow['document_number'][-4:]}\nEspecialidad: {service.name}"
            f"\nIPS preferida: {institution.name if institution else 'Sin preferencia'}"
            f"\nFecha preferida: {date.strftime('%d/%m/%Y') if date else 'Sin preferencia'}"
        )
        return summary+'\n¿Confirmas el registro? Es una solicitud de demostración, no una cita oficial.',{**flow,'step':'confirmation','preferred_date':date.isoformat() if date else None}
    if step == 'confirmation':
        if text not in {'confirmar solicitud','confirmar','si'}: return 'Selecciona «Confirmar solicitud», «Corregir datos» o «Cancelar».',flow
        service=MedicalService.objects.filter(pk=flow.get('service_id'),is_active=True).first()
        institution=selectable_institutions().filter(pk=flow.get('institution_id')).first()
        if not service or (flow.get('institution_id') and not institution): return 'La especialidad o IPS cambió. Inicia nuevamente la solicitud.',{}
        if flow.get('document_type') not in {'CC','TI','CE'}: return 'Selecciona nuevamente el tipo de documento: CC, TI o CE.', {'step':'document_type'}
        if not all(flow.get(k) for k in ('document_type','document_number')): return 'Faltan datos de identificación. Inicia nuevamente la solicitud.',{}
        item=AppointmentRequest.objects.create(user=user,service=service,preferred_institution=institution,preferred_date=flow.get('preferred_date'))
        RequestPatientDetails.objects.create(request=item,document_type=flow['document_type'],document_number=flow['document_number'])
        RequestStatusHistory.objects.create(request=item,new_status=item.status,changed_by=user)
        Notification.objects.create(user=user,request=item,kind=Notification.Kind.REQUEST_CREATED,title='Solicitud registrada',body=f'Tu solicitud de {service.name} quedó pendiente de revisión.')
        return f'Solicitud {str(item.reference)[:8].upper()} registrada como «Pendiente». Administración la recibirá en su tabla. Puedes consultar el estado en Mis solicitudes. No es una cita oficial.',{}
    if any(w in text for w in ('mis solicitudes','estado','seguimiento','historial','mis citas')): return _request_summary(user),{}
    if any(w in text for w in ('disponibilidad','horario','cupos')): return _availability_summary(),{}
    if any(w in text for w in ('solicitar','agendar','necesito cita','quiero cita','cita medica')):
        return 'Vamos a registrar tu solicitud. Primero, ¿qué tipo de documento tiene el paciente? Selecciona CC, TI o CE. Usa datos de prueba para esta demostración.',{'step':'document_type'}
    if any(w in text for w in ('hola','ayuda','buenos dias','buenas tardes','buenas noches')):return welcome_message(),{}
    return 'Puedes solicitar una cita, consultar tus solicitudes, ver disponibilidad simulada o pedir ayuda.',{}


def _availability_summary():
    slots = AvailabilitySlot.objects.filter(institution__in=selectable_institutions(),
        service__is_active=True, professional__is_active=True, is_available=True,
        starts_at__gte=timezone.now()).select_related('service','institution').order_by('starts_at')[:8]
    if not slots:
        return 'No hay horarios simulados cargados para las IPS reales del catálogo. Puedes registrar una solicitud con IPS y fecha preferidas; administración revisará el caso. No se consulta la disponibilidad real de estas instituciones.'
    lines = ['Horarios de demostración (no son cupos oficiales de las IPS):']
    for slot in slots:
        local = timezone.localtime(slot.starts_at)
        lines.append(f'• {slot.service.name} — {local:%d/%m/%Y %I:%M %p} — {slot.institution.name}')
    return '\n'.join(lines)
