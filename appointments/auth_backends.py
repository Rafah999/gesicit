from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Permite iniciar sesión con nombre de usuario o correo único."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        identifier = username or kwargs.get(User.USERNAME_FIELD)
        if identifier and "@" in identifier:
            matches = User._default_manager.filter(email__iexact=identifier)
            if matches.count() != 1:
                return None
            identifier = matches.first().get_username()
        return super().authenticate(request, username=identifier, password=password, **kwargs)
