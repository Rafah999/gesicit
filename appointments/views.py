from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import PatientRegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = PatientRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="appointments.auth_backends.EmailOrUsernameBackend")
        messages.success(request, "Tu cuenta quedó creada correctamente.")
        return redirect("home")

    return render(request, "registration/register.html", {"form": form})


@login_required
def home(request):
    return render(request, "appointments/home.html")
