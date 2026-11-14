from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from .models import AppointmentRequest, AvailabilitySlot, UserProfile

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


class AppointmentAssignmentForm(forms.Form):
    slot = forms.ModelChoiceField(
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
        self.fields["slot"].queryset = slots.order_by("starts_at")
