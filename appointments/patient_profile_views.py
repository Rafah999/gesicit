from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from .models import UserProfile
from .patient_profile_forms import PatientProfileEditForm

@login_required
@require_http_methods(['GET'])
def patient_profile(request):
    if request.user.is_staff or request.user.is_superuser:
        return HttpResponseForbidden('Solo disponible para pacientes.')
    response = render(request, 'appointments/patient/profile_page.html', {
        'patient_page': 'profile', 'profile': UserProfile.objects.filter(user=request.user).first(),
    })
    response['Cache-Control'] = 'no-store'
    return response

@login_required
@require_http_methods(['GET', 'POST'])
def edit_patient_profile(request):
    if request.user.is_staff or request.user.is_superuser:
        return HttpResponseForbidden('Solo disponible para pacientes.')
    form = PatientProfileEditForm(request.POST if request.method == 'POST' else None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, 'Tu perfil se actualizó correctamente.')
        return redirect('patient_profile')
    response = render(request, 'appointments/patient/profile_edit.html', {'patient_page':'profile_edit','profile_form':form})
    response['Cache-Control'] = 'no-store'
    return response
