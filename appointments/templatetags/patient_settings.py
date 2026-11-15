from django import template
from appointments.patient_preferences import preferences_for
register = template.Library()

@register.simple_tag(takes_context=True)
def patient_preferences(context):
    return preferences_for(context['request'])
