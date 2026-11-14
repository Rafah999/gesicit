from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_gesecit_profile(sender, instance, created, **kwargs):
    if created:
        if instance.is_superuser:
            role = UserProfile.Role.ADMINISTRATOR
        elif instance.is_staff:
            role = UserProfile.Role.ADMIN_STAFF
        else:
            role = UserProfile.Role.AFFILIATE
        UserProfile.objects.get_or_create(user=instance, defaults={"role": role})

# Entregar al paciente la observación sin alterar la gestión administrativa.
from .models import RequestStatusHistory, Notification

@receiver(post_save, sender=RequestStatusHistory)
def notify_patient_observation(sender, instance, created, raw=False, **kwargs):
    if created and not raw and instance.note.strip():
        Notification.objects.create(
            user_id=instance.request.user_id, request_id=instance.request_id,
            kind=Notification.Kind.REQUEST_UPDATED,
            title="Observación sobre tu solicitud",
            body=instance.note,
        )
