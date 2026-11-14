from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

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


class RequestStatusForm(forms.ModelForm):
    note = forms.CharField(
        label="Observación (opcional)",
        max_length=200,
        required=False,
    )

    class Meta:
        model = AppointmentRequest
        fields = ("status",)
        labels = {"status": "Nuevo estado"}


class AppointmentSlotChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, slot):
        return (
            f"{slot.starts_at:%d/%m/%Y %H:%M} · {slot.professional.full_name} · "
            f"{slot.institution.name}"
        )


class AppointmentAssignmentForm(forms.Form):
    slot = AppointmentSlotChoiceField(
        queryset=AvailabilitySlot.objects.none(),
        label="Horario disponible",
        empty_label="Selecciona fecha, hora e IPS",
    )

    def __init__(self, *args, appointment_request=None, **kwargs):
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
        self.fields["slot"].queryset = slots.order_by("starts_at")

    def clean(self):
        cleaned_data = super().clean()
        appointment_request = getattr(self, "appointment_request", None)
        slot = cleaned_data.get("slot")
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

class AvailabilitySlotForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        label="Fecha y hora",
        input_formats=("%Y-%m-%dT%H:%M",),
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = AvailabilitySlot
        fields = ("service", "institution", "professional", "starts_at")
        labels = {
            "service": "Servicio",
            "institution": "IPS",
            "professional": "Profesional",
        }
        widgets = {
            "service": forms.Select(attrs={"class": "form-control"}),
            "institution": forms.Select(attrs={"class": "form-control"}),
            "professional": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = MedicalService.objects.filter(is_active=True).order_by("name")
        self.fields["institution"].queryset = Institution.objects.filter(is_active=True).order_by("name")
        self.fields["professional"].queryset = Professional.objects.filter(is_active=True).order_by("full_name")

    def clean_starts_at(self):
        starts_at = self.cleaned_data["starts_at"]
        if starts_at <= timezone.now():
            raise forms.ValidationError("El horario debe estar en el futuro.")
        return starts_at


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
