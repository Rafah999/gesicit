from django import forms
from .forms import PatientProfileForm

class PatientProfileEditForm(PatientProfileForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, autocomplete in {'first_name':'given-name','last_name':'family-name','email':'email','phone':'tel','demo_member_code':'off'}.items():
            self.fields[name].widget.attrs.update({'autocomplete':autocomplete})
        self.fields['email'].widget = forms.EmailInput(attrs={'autocomplete':'email'})
        self.fields['phone'].widget = forms.TextInput(attrs={'type':'tel','autocomplete':'tel','inputmode':'tel'})

    def clean_phone(self):
        import re
        value = self.cleaned_data['phone'].strip()
        digits = re.sub(r'\D', '', value)
        if not re.fullmatch(r'\+?[0-9 ()\-]+', value) or not 7 <= len(digits) <= 15:
            raise forms.ValidationError('Ingresa un teléfono de 7 a 15 dígitos. Puedes incluir prefijo, espacios y guiones.')
        return value
