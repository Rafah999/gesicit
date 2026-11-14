from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from .chat_logic import reply_to_message
from .forms import PatientProfileForm
from .models import AppointmentRequest, Notification, MedicalService, Institution

@login_required
@require_POST
def patient_chat(request):
    if request.user.is_staff or request.user.is_superuser:
        return JsonResponse({'error': 'Esta interfaz es para pacientes.'}, status=403)
    message = request.POST.get('message', '').strip()
    if not message or len(message) > 1000:
        return JsonResponse({'error': 'Escribe un mensaje de hasta 1000 caracteres.'}, status=400)
    with transaction.atomic():
        reply, flow = reply_to_message(request.user, message, request.session.get('patient_chat_flow', {}))
    request.session['patient_chat_flow'] = flow
    options = []
    if flow.get('step') == 'service':
        options = list(MedicalService.objects.filter(is_active=True).order_by('name').values_list('name', flat=True)[:8])
    elif flow.get('step') == 'institution':
        from django.utils import timezone
        options = list(Institution.objects.filter(is_active=True, availability_slots__service_id=flow['service_id'], availability_slots__is_available=True, availability_slots__starts_at__gte=timezone.now()).distinct().order_by('name').values_list('name', flat=True)[:8]) + ['Omitir']
    elif flow.get('step') == 'preferred_date':
        options = ['Omitir']
    return JsonResponse({'reply': reply, 'options': options, 'step': flow.get('step', '')})

@login_required
def patient_section(request, section):
    if request.user.is_staff or request.user.is_superuser:
        return JsonResponse({'error': 'Acceso reservado para pacientes.'}, status=403)
    if section not in {'requests', 'notifications', 'help', 'profile'}:
        return JsonResponse({'error': 'Sección no encontrada.'}, status=404)
    context = {'section': section}
    if section == 'requests':
        context['items'] = AppointmentRequest.objects.filter(user=request.user).select_related('service', 'preferred_institution').prefetch_related('status_history')
    elif section == 'notifications':
        context['items'] = Notification.objects.filter(user=request.user)
        if request.method == 'POST':
            Notification.objects.filter(user=request.user, pk=request.POST.get('notification_id')).update(is_read=True)
    elif section == 'profile':
        form = PatientProfileForm(request.POST if request.method == 'POST' else None, instance=request.user)
        if request.method == 'POST' and form.is_valid():
            form.save()
            context['saved'] = True
        context['form'] = form
    return render(request, 'appointments/patient/section.html', context)
