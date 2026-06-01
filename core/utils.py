import random, string
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
    if user:
        Notification.objects.create(user=user, message=message, link_type=link_type, link_id=link_id)


def generate_username(first_name, last_name):
    from .models import User
    base = f"{first_name.lower()}.{last_name.lower()}".replace(' ', '')
    username, counter = base, 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{counter}"
        counter += 1
    return username


def generate_password(length=8):
    import random, string
    lower = random.choice(string.ascii_lowercase)
    upper = random.choice(string.ascii_uppercase)
    digit = random.choice(string.digits)
    special = random.choice('#$%@&*')
    remaining = [random.choice(string.ascii_letters + string.digits + '#$%@&*') for _ in range(length - 4)]
    pwd = list(lower + upper + digit + special) + remaining
    random.shuffle(pwd)
    return ''.join(pwd)