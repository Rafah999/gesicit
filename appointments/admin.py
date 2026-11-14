from django.contrib import admin

from .models import (
    AppointmentAssignment,
    AppointmentRequest,
    AssignmentHistory,
    AvailabilitySlot,
    Institution,
    MedicalService,
    Notification,
    Professional,
    RequestStatusHistory,
    UserProfile,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "demo_member_code")
    list_filter = ("role",)
    search_fields = ("user__username", "user__first_name", "user__last_name", "demo_member_code")


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "is_active")
    list_filter = ("is_active", "city")
    search_fields = ("name", "city")


@admin.register(MedicalService)
class MedicalServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Professional)
class ProfessionalAdmin(admin.ModelAdmin):
    list_display = ("full_name", "is_active")
    list_filter = ("is_active", "services")
    search_fields = ("full_name",)
    filter_horizontal = ("services",)


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ("starts_at", "service", "institution", "professional", "is_available")
    list_filter = ("is_available", "service", "institution", "starts_at")
    search_fields = ("professional__full_name", "service__name", "institution__name")
    date_hierarchy = "starts_at"


class RequestStatusHistoryInline(admin.TabularInline):
    model = RequestStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ("previous_status", "new_status", "note", "changed_by", "changed_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AppointmentRequest)
class AppointmentRequestAdmin(admin.ModelAdmin):
    list_display = ("short_reference", "user", "service", "preferred_institution", "status", "preferred_date", "created_at")
    list_filter = ("status", "service", "preferred_institution", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "=reference")
    readonly_fields = ("reference", "created_at", "updated_at")
    inlines = (RequestStatusHistoryInline,)

    @admin.display(description="Código", ordering="reference")
    def short_reference(self, obj):
        return str(obj.reference)[:8].upper()

    def save_model(self, request, obj, form, change):
        old_status = AppointmentRequest.objects.get(pk=obj.pk).status if change else None
        super().save_model(request, obj, form, change)
        if old_status is None or old_status != obj.status:
            RequestStatusHistory.objects.create(
                request=obj,
                previous_status=old_status or "",
                new_status=obj.status,
                changed_by=request.user,
            )


@admin.register(RequestStatusHistory)
class RequestStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("request", "previous_status", "new_status", "changed_by", "changed_at")
    list_filter = ("new_status", "changed_at")
    readonly_fields = ("request", "previous_status", "new_status", "changed_by", "changed_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AppointmentAssignment)
class AppointmentAssignmentAdmin(admin.ModelAdmin):
    list_display = ("request", "slot", "state", "created_by", "created_at", "closed_at")
    list_filter = ("state", "created_at", "slot__service", "slot__institution")
    search_fields = ("request__reference", "request__user__username", "slot__professional__full_name")
    readonly_fields = ("created_at",)


@admin.register(AssignmentHistory)
class AssignmentHistoryAdmin(admin.ModelAdmin):
    list_display = ("assignment", "event", "detail", "changed_by", "created_at")
    list_filter = ("event", "created_at")
    readonly_fields = ("assignment", "event", "detail", "changed_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("user__username", "title", "body")
