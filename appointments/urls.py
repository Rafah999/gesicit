from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
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
