from datetime import datetime, timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from django.utils.dateparse import parse_date

from .constants import (
    APPOINTMENT_SLOT_MINUTES,
    BUSINESS_DAYS,
    BUSINESS_END_TIME,
    BUSINESS_START_TIME,
)
from .models import (
    AppointmentRequest,
    AvailabilitySlot,
    Institution,
    MedicalService,
    Professional,
    UserProfile,
)

User = get_user_model()


class PatientRegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="Nombres", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo electrónico")
    phone = forms.CharField(label="Teléfono de contacto", max_length=24)
    demo_member_code = forms.CharField(
        label="Código de afiliado (opcional; ficticio para el prototipo)",
        max_length=24,
        required=False,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "email", "username")
        labels = {
            "first_name": "Nombres",
            "last_name": "Apellidos",
            "username": "Nombre de usuario",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "Lo usarás para iniciar sesión si no ingresas con tu correo."
        self.fields["password1"].label = "Contraseña"
        self.fields["password2"].label = "Confirmar contraseña"
        for name, autocomplete in {
            "first_name": "given-name",
            "last_name": "family-name",
            "email": "email",
            "phone": "tel",
            "demo_member_code": "off",
            "username": "username",
            "password1": "new-password",
            "password2": "new-password",
        }.items():
            self.fields[name].widget.attrs["autocomplete"] = autocomplete
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con ese correo electrónico.")
        return email

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "phone": self.cleaned_data["phone"].strip(),
                    "demo_member_code": self.cleaned_data["demo_member_code"].strip(),
                },
            )
        return user


class PatientProfileForm(forms.ModelForm):
    first_name = forms.CharField(label="Nombres", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo electrónico")
    phone = forms.CharField(label="Teléfono de contacto", max_length=24)
    demo_member_code = forms.CharField(
        label="Código de afiliado (opcional; ficticio para el prototipo)",
        max_length=24,
        required=False,
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        labels = {
            "first_name": "Nombres",
            "last_name": "Apellidos",
            "email": "Correo electrónico",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile, _ = UserProfile.objects.get_or_create(user=self.instance)
        self.fields["phone"].initial = profile.phone
        self.fields["demo_member_code"].initial = profile.demo_member_code

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una cuenta con ese correo electrónico.")
        return email

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "phone": self.cleaned_data["phone"].strip(),
                    "demo_member_code": self.cleaned_data["demo_member_code"].strip(),
                },
            )
        return user


class AppointmentSlotChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, slot):
        return (
            f"{timezone.localtime(slot.starts_at):%H:%M} · {slot.professional.full_name} · "
            f"{slot.institution.name}"
        )


class AppointmentAssignmentForm(forms.Form):
    appointment_date = forms.DateField(widget=forms.HiddenInput())
    slot = AppointmentSlotChoiceField(
        queryset=AvailabilitySlot.objects.none(),
        label="Horarios de 30 minutos disponibles",
        empty_label=None,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, appointment_request=None, selected_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        slots = AvailabilitySlot.objects.filter(
            is_available=True,
            starts_at__gte=timezone.now(),
            service__is_active=True,
            institution__is_active=True,
            professional__is_active=True,
        ).select_related("service", "institution", "professional")
        if appointment_request is not None:
            slots = slots.filter(service=appointment_request.service)
            if appointment_request.preferred_institution_id:
                slots = slots.filter(institution=appointment_request.preferred_institution)
            self.appointment_request = appointment_request
            if appointment_request.preferred_date:
                self.fields["alternative_date_confirmed"] = forms.BooleanField(
                    label="Confirmé con el paciente una fecha distinta a su preferencia",
                    required=False,
                    widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
                )
        requested_date = parse_date(str(self.data.get("appointment_date", ""))) if self.is_bound else None
        self.selected_date = requested_date or selected_date
        if self.selected_date is None and appointment_request and appointment_request.preferred_date:
            self.selected_date = appointment_request.preferred_date
        if self.selected_date is None:
            first_slot = slots.order_by("starts_at").values_list("starts_at", flat=True).first()
            self.selected_date = (
                timezone.localtime(first_slot).date() if first_slot else timezone.localdate()
            )
        self.initial.setdefault("appointment_date", self.selected_date)
        slots = slots.filter(starts_at__date=self.selected_date)
        self.fields["slot"].queryset = slots.order_by("starts_at")

    def clean(self):
        cleaned_data = super().clean()
        appointment_request = getattr(self, "appointment_request", None)
        slot = cleaned_data.get("slot")
        selected_date = cleaned_data.get("appointment_date")
        if slot and selected_date and timezone.localtime(slot.starts_at).date() != selected_date:
            self.add_error("slot", "Selecciona un horario del día elegido en el calendario.")
        if appointment_request and appointment_request.preferred_date and slot:
            selected_date = timezone.localtime(slot.starts_at).date()
            if (
                selected_date != appointment_request.preferred_date
                and not cleaned_data.get("alternative_date_confirmed")
            ):
                self.add_error(
                    "alternative_date_confirmed",
                    "Confirma que el paciente aceptó cambiar la fecha preferida antes de asignar este horario.",
                )
        return cleaned_data

class AvailabilityRangeForm(forms.Form):
    service = forms.ModelChoiceField(
        queryset=MedicalService.objects.none(),
        label="Servicio",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    institution = forms.ModelChoiceField(
        queryset=Institution.objects.none(),
        label="IPS",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    professional = forms.ModelChoiceField(
        queryset=Professional.objects.none(),
        label="Profesional",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    appointment_date = forms.DateField(
        label="Día",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    start_time = forms.TimeField(
        label="Desde",
        widget=forms.TimeInput(attrs={"type": "time", "step": "1800", "class": "form-control"}),
    )
    end_time = forms.TimeField(
        label="Hasta (sin incluir)",
        widget=forms.TimeInput(attrs={"type": "time", "step": "1800", "class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = MedicalService.objects.filter(is_active=True).order_by("name")
        self.fields["institution"].queryset = Institution.objects.filter(is_active=True).order_by("name")
        self.fields["professional"].queryset = Professional.objects.filter(is_active=True).order_by("full_name")

    def clean(self):
        cleaned_data = super().clean()
        appointment_date = cleaned_data.get("appointment_date")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        professional = cleaned_data.get("professional")
        service = cleaned_data.get("service")

        if start_time and (start_time.minute not in (0, 30) or start_time.second or start_time.microsecond):
            self.add_error("start_time", "Usa horas en intervalos de media hora, por ejemplo 08:00 o 08:30.")
        if end_time and (end_time.minute not in (0, 30) or end_time.second or end_time.microsecond):
            self.add_error("end_time", "Usa horas en intervalos de media hora, por ejemplo 16:00 o 16:30.")
        if appointment_date and appointment_date.weekday() not in BUSINESS_DAYS:
            self.add_error("appointment_date", "La atención está configurada de lunes a viernes.")
        if start_time and start_time < BUSINESS_START_TIME:
            self.add_error("start_time", "El horario laboral comienza a las 08:00.")
        if end_time and end_time > BUSINESS_END_TIME:
            self.add_error("end_time", "El horario laboral termina a las 17:00.")
        if start_time and end_time:
            start_dt = datetime.combine(appointment_date or timezone.localdate(), start_time)
            end_dt = datetime.combine(appointment_date or timezone.localdate(), end_time)
            duration = end_dt - start_dt
            if duration <= timedelta(0):
                self.add_error("end_time", "La hora final debe ser posterior a la hora inicial.")
            elif duration.total_seconds() % (APPOINTMENT_SLOT_MINUTES * 60):
                self.add_error("end_time", "El rango debe cerrar en un bloque de 30 minutos.")
        if appointment_date and start_time:
            local_start = timezone.make_aware(
                datetime.combine(appointment_date, start_time),
                timezone.get_current_timezone(),
            )
            if local_start <= timezone.now():
                self.add_error("start_time", "La disponibilidad debe empezar en el futuro.")
        if professional and service and not professional.services.filter(pk=service.pk).exists():
            self.add_error("professional", "Ese profesional no está asociado al servicio seleccionado.")
        return cleaned_data


class MedicalServiceForm(forms.ModelForm):
    class Meta:
        model = MedicalService
        fields = ("name", "description", "is_active")
        labels = {
            "name": "Nombre del servicio",
            "description": "Descripción",
            "is_active": "Activo para nuevas solicitudes",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ("name", "city", "address", "is_active")
        labels = {
            "name": "Nombre de la IPS",
            "city": "Ciudad",
            "address": "Dirección",
            "is_active": "Activa para nuevas solicitudes",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ProfessionalForm(forms.ModelForm):
    class Meta:
        model = Professional
        fields = ("full_name", "services", "is_active")
        labels = {
            "full_name": "Nombre del profesional",
            "services": "Servicios que atiende",
            "is_active": "Activo para nuevas solicitudes",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "services": forms.SelectMultiple(attrs={"class": "form-control", "size": 5}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["services"].queryset = MedicalService.objects.all().order_by("name")
