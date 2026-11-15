from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .models import Notification

@login_required
@require_GET
def patient_notification_feed(request):
    if request.user.is_staff or request.user.is_superuser:
        return JsonResponse({'error':'Solo disponible para pacientes.'},status=403)
    rows=Notification.objects.filter(user=request.user)
    newest=rows.order_by('-pk').values_list('pk',flat=True).first() or 0
    raw=request.GET.get('after')
    if raw is not None and (not raw.isascii() or not raw.isdigit() or len(raw)>19):
        return JsonResponse({'error':'Cursor inválido.'},status=400)
    cursor=int(raw) if raw is not None else None
    items=list(rows.filter(pk__gt=cursor).order_by('pk').values('id','title','body','is_read')[:25]) if cursor is not None else []
    response=JsonResponse({'items':items,'cursor':items[-1]['id'] if items else newest if cursor is None or cursor>newest else cursor,'unread_count':rows.filter(is_read=False).count(),'initial':cursor is None})
    response['Cache-Control']='no-store, private'
    return response
