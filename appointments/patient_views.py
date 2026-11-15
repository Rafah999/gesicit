from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from .patient_preferences import preferences_for
from .patient_presentation import patient_requests, present_request, present_notification
from .chat_intake import reply_to_message, options_for_flow
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
    options = options_for_flow(request.user, flow)
    return JsonResponse({'reply': reply, 'options': options, 'step': flow.get('step', '')})

@login_required
def patient_section(request, section):
    if request.user.is_staff or request.user.is_superuser:
        return JsonResponse({'error': 'Acceso reservado para pacientes.'}, status=403)
    if section not in {'requests', 'notifications', 'help', 'profile'}:
        return JsonResponse({'error': 'Sección no encontrada.'}, status=404)
    context = {'section': section}
    if section == 'requests':
        context['items'] = [present_request(item) for item in patient_requests(request.user)]
    elif section == 'notifications':
        context['items'] = [present_notification(item) for item in Notification.objects.filter(user=request.user).select_related('request__service').prefetch_related('request__status_history', 'request__assignments__slot__institution', 'request__assignments__slot__professional')]
        if request.method == 'POST':
            Notification.objects.filter(user=request.user, pk=request.POST.get('notification_id')).update(is_read=True)
            for item in context['items']:
                if str(item.pk) == request.POST.get('notification_id'):
                    item.is_read = True
        preferences = preferences_for(request)
        if preferences['unread_only']:
            context['items'] = [item for item in context['items'] if not item.is_read]
        if preferences['notification_order'] == 'oldest':
            context['items'].reverse()
    elif section == 'profile':
        if request.method != 'GET':
            return JsonResponse({'error':'Utiliza la pantalla Editar perfil.'}, status=405)
        from .models import UserProfile
        context['profile'] = UserProfile.objects.filter(user=request.user).first()
    response = render(request, 'appointments/patient/section.html', context)
    response['Cache-Control'] = 'no-store'
    return response
