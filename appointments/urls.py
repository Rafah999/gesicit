from django.urls import path

from . import views

urlpatterns = [
    path("registro/", views.register, name="register"),
    path("", views.chat, name="chat"),
    path("mi-perfil/", views.profile, name="profile"),
    path("mis-solicitudes/", views.my_requests, name="my_requests"),
    path("notificaciones/", views.notifications, name="notifications"),
    path("notificaciones/<int:notification_id>/leida/", views.mark_notification_read, name="mark_notification_read"),
    path("gestion/solicitudes/", views.staff_requests, name="staff_requests"),
    path(
        "gestion/solicitudes/<uuid:reference>/estado/",
        views.update_request_status,
        name="update_request_status",
    ),
    path("gestion/solicitudes/<uuid:reference>/asignar/", views.assign_slot, name="assign_slot"),
    path("gestion/asignaciones/<int:assignment_id>/cancelar/", views.cancel_assignment, name="cancel_assignment"),
]
