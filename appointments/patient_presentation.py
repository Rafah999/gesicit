from .models import AppointmentRequest, AppointmentAssignment

def patient_requests(user):
    return AppointmentRequest.objects.filter(user=user).select_related('service', 'preferred_institution').prefetch_related(
        'status_history', 'assignments__slot__institution', 'assignments__slot__professional')

def present_request(item):
    assignments = list(item.assignments.all())
    item.scheduled_appointment = next((a for a in assignments if a.state == AppointmentAssignment.State.ACTIVE), None)
    item.last_cancelled_appointment = next(
        (a for a in assignments if a.state == AppointmentAssignment.State.CANCELLED),
        None,
    )
    changes = list(item.status_history.all())
    item.latest_observation = next((h for h in reversed(changes) if h.note.strip()), None)
    return item

def present_notification(item):
    if item.request_id:
        present_request(item.request)
        changes = list(item.request.status_history.all())
        item.observation = next((h for h in reversed(changes) if h.note.strip() and h.changed_at <= item.created_at), None)
    return item
