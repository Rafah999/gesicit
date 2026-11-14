from django import forms
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .models import AppointmentRequest, Notification, RequestMessage
from .patient_presentation import present_request

class RequestMessageForm(forms.Form):
    body = forms.CharField(label="Mensaje", max_length=2000, strip=True,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Escribe un mensaje sobre esta solicitud…", "maxlength": 2000}))

@login_required
@require_http_methods(["GET", "POST"])
def request_conversation(request, reference):
    staff = request.user.is_active and (request.user.is_staff or request.user.is_superuser)
    allowed = AppointmentRequest.objects.select_related('user', 'service')
    if not staff:
        allowed = allowed.filter(user=request.user)
    appointment = get_object_or_404(allowed, reference=reference)
    if request.method == 'POST' and not staff:
        return HttpResponseForbidden('El paciente solo puede consultar las comunicaciones de su solicitud.')
    form = RequestMessageForm()
    if request.method == 'POST':
        if request.POST.get('action') == 'read':
            appointment.communication_messages.filter(from_staff=not staff, read_at__isnull=True).update(read_at=timezone.now())
            messages.success(request, 'Mensajes marcados como leídos.')
            return redirect('request_conversation', reference=reference)
        form = RequestMessageForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                RequestMessage.objects.create(request=appointment, sender=request.user, from_staff=staff, body=form.cleaned_data['body'])
                if staff:
                    recipients = get_user_model().objects.filter(pk=appointment.user_id, is_active=True)
                else:
                    from django.db.models import Q
                    recipients = get_user_model().objects.filter(Q(is_staff=True) | Q(is_superuser=True), is_active=True).exclude(pk=request.user.pk)
                short_reference = str(appointment.reference)[:8].upper()
                Notification.objects.bulk_create([
                    Notification(user=recipient, request=appointment, kind=Notification.Kind.REQUEST_UPDATED,
                        title='Nuevo mensaje de administración' if staff else 'Nuevo mensaje del paciente',
                        body=f'Solicitud {short_reference} · {appointment.service.name}: tienes un nuevo mensaje. Consulta el mensaje en tus notificaciones.'[:240])
                    for recipient in recipients
                ])
            messages.success(request, 'Mensaje enviado correctamente.')
            return redirect('request_conversation', reference=reference)
    if not staff:
        return render(request, 'appointments/patient/information.html', {
            'appointment': present_request(appointment),
            'received_messages': appointment.communication_messages.filter(from_staff=True).select_related('sender'),
            'patient_detail': True,
        })
    return render(request, 'appointments/communication/thread.html', {
        'appointment': appointment, 'thread_messages': appointment.communication_messages.select_related('sender'),
        'message_form': form, 'staff_view': staff,
        'parent_template': 'appointments/admin_base.html' if staff else 'appointments/base.html',
    })
