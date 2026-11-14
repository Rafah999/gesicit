from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import AvailabilitySlot, Institution, MedicalService, Professional


class Command(BaseCommand):
    help = "Carga catálogo y horarios completamente ficticios para la demostración académica."

    def handle(self, *args, **options):
        institution, _ = Institution.objects.update_or_create(
            name="IPS Académica Demo Cartagena (Ficticia)",
            defaults={"city": "Cartagena", "address": "Ubicación simulada", "is_active": True},
        )

        services = {}
        professional_names = {
            "Medicina general": "Profesional Demo 01 (Ficticio)",
            "Odontología general": "Profesional Demo 02 (Ficticio)",
            "Medicina interna": "Profesional Demo 03 (Ficticio)",
            "Ginecología": "Profesional Demo 04 (Ficticio)",
            "Pediatría": "Profesional Demo 05 (Ficticio)",
        }
        for service_name, professional_name in professional_names.items():
            service, _ = MedicalService.objects.update_or_create(
                name=service_name,
                defaults={"description": "Servicio de demostración académica", "is_active": True},
            )
            professional, _ = Professional.objects.update_or_create(
                full_name=professional_name,
                defaults={"is_active": True},
            )
            professional.services.set([service])
            services[service_name] = (service, professional)

            for day_offset, hour in ((3, 8), (4, 10), (6, 14)):
                slot_day = timezone.localdate() + timedelta(days=day_offset)
                naive_start = datetime.combine(slot_day, time(hour, 0))
                starts_at = timezone.make_aware(naive_start, timezone.get_current_timezone())
                AvailabilitySlot.objects.get_or_create(
                    professional=professional,
                    starts_at=starts_at,
                    defaults={
                        "institution": institution,
                        "service": service,
                        "is_available": True,
                    },
                )

        self.stdout.write(self.style.SUCCESS(
            f"Catálogo ficticio listo: {len(services)} servicios, {len(services)} profesionales y horarios simulados."
        ))
