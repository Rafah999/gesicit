from django.urls import path

from . import views

urlpatterns = [
    path("registro/", views.register, name="register"),
    path("administracion/", views.admin_dashboard, name="admin_dashboard"),
    path("administracion/solicitudes/", views.appointment_requests, name="admin_requests"),
    path(
        "administracion/solicitudes/<uuid:reference>/",
        views.manage_appointment_request,
        name="manage_appointment_request",
    ),
    path("administracion/usuarios/<int:user_id>/rol/", views.change_user_role, name="change_user_role"),
    path("administracion/usuarios/<int:user_id>/eliminar/", views.delete_user, name="delete_user"),
    path("", views.home, name="home"),
]

# Rutas adicionales de la interfaz del paciente; administración permanece intacta.
from . import patient_views
urlpatterns += [
    path("paciente/chat/", patient_views.patient_chat, name="patient_chat"),
    path("paciente/seccion/<str:section>/", patient_views.patient_section, name="patient_section"),
]

# Conversación protegida entre el paciente y el personal autorizado.
from .communication_views import request_conversation
urlpatterns += [
    path("solicitudes/<uuid:reference>/mensajes/", request_conversation, name="request_conversation"),
]
