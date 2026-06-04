from django.conf import settings
from .models import Notification

def notifications_context(request):
    if request.user.is_authenticated:
        return {
            'unread_notifications': Notification.objects.filter(user=request.user, is_read=False).count(),
            'recent_notifications': Notification.objects.filter(user=request.user)[:5],
            'VAPID_PUBLIC_KEY': getattr(settings, 'VAPID_PUBLIC_KEY', ''),
        }
    return {'unread_notifications': 0, 'recent_notifications': [], 'VAPID_PUBLIC_KEY': ''}