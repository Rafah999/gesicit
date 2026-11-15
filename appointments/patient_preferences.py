"""Preferencias firmadas por cuenta y navegador, sin alterar el esquema de datos."""
from django import forms

DEFAULTS = {'theme': 'light', 'text_size': 'normal', 'high_contrast': False,
            'reduce_motion': False, 'unread_only': False, 'notification_order': 'newest'}

def preferences_for(request):
    import json
    value = request.get_signed_cookie(preferences_cookie_name(request.user), default='', salt=f'patient-settings-{request.user.pk}', max_age=31536000)
    if not value:
        value = request.get_signed_cookie('patient_preferences', default='', salt=f'patient-settings-{request.user.pk}', max_age=31536000)
    try:
        data = json.loads(value)
        if not isinstance(data, dict):
            return dict(DEFAULTS)
        form = PatientPreferencesForm(data)
        if form.is_valid():
            return dict(form.cleaned_data)
    except (TypeError, ValueError):
        pass
    return dict(DEFAULTS)

class PatientPreferencesForm(forms.Form):
    theme = forms.ChoiceField(label='Tema de la interfaz', choices=[('light', 'Claro'), ('dark', 'Oscuro'), ('system', 'Usar el tema del dispositivo')])
    text_size = forms.ChoiceField(label='Tamaño del texto', choices=[('normal', 'Estándar'), ('large', 'Grande')])
    high_contrast = forms.BooleanField(label='Aumentar el contraste', required=False)
    reduce_motion = forms.BooleanField(label='Reducir animaciones y movimiento', required=False)
    unread_only = forms.BooleanField(label='Mostrar solo notificaciones sin leer', required=False)
    notification_order = forms.ChoiceField(label='Orden de las notificaciones', choices=[('newest', 'Más recientes primero'), ('oldest', 'Más antiguas primero')])


def preferences_cookie_name(user):
    return f'patient_preferences_{user.pk}'
