import random, string, json
from django.core.mail import send_mail
from django.conf import settings
from .models import AuditLog, Notification


def log_action(request, action, object_type='', object_id=None, extra=''):
    user = request.user if request.user.is_authenticated else None
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    AuditLog.objects.create(
        user=user, action=action, object_type=object_type,
        object_id=object_id, ip_address=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:300], extra=extra
    )


def notify(user, message, link_type='', link_id=None):
    """Create in-app notification, send email, and send push notification."""
    if not user:
        return

    # 1. In-app notification
    Notification.objects.create(user=user, message=message, link_type=link_type, link_id=link_id)

    # 2. Email notification
    if user.email:
        try:
            import threading
            url = ''
            if link_type == 'incident' and link_id:
                url = f"\n\nView it here: {getattr(settings, 'SITE_URL', 'https://dh-helpdesk.up.railway.app')}/incidents/{link_id}/"
            def send_email():
                try:
                    send_mail(
                        subject=f"[DHHD] {message}",
                        message=f"{message}{url}\n\n— Digital Health Help Desk",
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@dhhd.app'),
                        recipient_list=[user.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass
            threading.Thread(target=send_email, daemon=True).start()
        except Exception:
            pass

    # 3. Push notification
    try:
        _send_push(user, message, link_type, link_id)
    except Exception:
        pass


def _send_push(user, message, link_type='', link_id=None):
    """Send Web Push notification to all user's subscribed devices."""
    try:
        from .models import PushSubscription
        from pywebpush import webpush, WebPushException

        vapid_private_key = getattr(settings, 'VAPID_PRIVATE_KEY', '')
        vapid_claims = {"sub": f"mailto:{getattr(settings, 'VAPID_ADMIN_EMAIL', 'admin@dhhd.app')}"}

        if not vapid_private_key:
            return

        url = '/'
        if link_type == 'incident' and link_id:
            url = f"/incidents/{link_id}/"

        unread_count = Notification.objects.filter(user=user, is_read=False).count()

        payload = json.dumps({
            "title": "DHHD Alert",
            "body": message,
            "url": url,
            "icon": "/static/icons/icon-192.png",
            "count": unread_count,
        })

        subscriptions = PushSubscription.objects.filter(user=user)
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                )
            except WebPushException as e:
                if '410' in str(e) or '404' in str(e):
                    sub.delete()
    except Exception:
        pass


def generate_username(first_name, last_name):
    from .models import User
    base = f"{first_name.lower()}.{last_name.lower()}".replace(' ', '')
    username, counter = base, 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{counter}"
        counter += 1
    return username


def generate_password(length=8):
    lower = random.choice(string.ascii_lowercase)
    upper = random.choice(string.ascii_uppercase)
    digit = random.choice(string.digits)
    special = random.choice('#$%@&*')
    remaining = [random.choice(string.ascii_letters + string.digits + '#$%@&*') for _ in range(length - 4)]
    pwd = list(lower + upper + digit + special) + remaining
    random.shuffle(pwd)
    return ''.join(pwd)