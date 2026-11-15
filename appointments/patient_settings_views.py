import json
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from .patient_preferences import DEFAULTS, PatientPreferencesForm, preferences_for, preferences_cookie_name

@login_required
@require_http_methods(['GET', 'POST'])
def patient_settings(request):
    if request.user.is_staff or request.user.is_superuser:
        return HttpResponseForbidden('Configuración disponible solo para pacientes.')
    preferences = preferences_for(request)
    preferences_form = PatientPreferencesForm(initial=preferences)
    password_form = PasswordChangeForm(request.user)
    saved = ''
    settings_errors = False
    write_preferences = False
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'preferences':
            preferences_form = PatientPreferencesForm(request.POST)
            if preferences_form.is_valid():
                preferences = dict(preferences_form.cleaned_data)
                write_preferences = True
                saved = 'Tus preferencias se guardaron en este navegador.'
        elif action == 'reset':
            preferences = dict(DEFAULTS)
            preferences_form = PatientPreferencesForm(initial=preferences)
            write_preferences = True
            saved = 'Se restauraron las preferencias predeterminadas.'
        elif action == 'password':
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                password_form = PasswordChangeForm(user)
                saved = 'Tu contraseña se actualizó. Esta sesión continúa abierta; las otras sesiones deberán iniciar sesión nuevamente.'
        else:
            return HttpResponseBadRequest('Acción de configuración no válida.')
    settings_errors = bool(preferences_form.errors or password_form.errors)
    response = render(request, 'appointments/patient/settings.html', {
        'preferences_form': preferences_form, 'password_form': password_form,
        'preferences': preferences, 'settings_saved': saved, 'settings_errors':settings_errors,
    })
    response['Cache-Control'] = 'no-store'
    if write_preferences:
        response.set_signed_cookie(preferences_cookie_name(request.user), json.dumps(preferences),
            salt=f'patient-settings-{request.user.pk}', max_age=31536000,
            secure=request.is_secure(), httponly=True, samesite='Lax')
    return response
