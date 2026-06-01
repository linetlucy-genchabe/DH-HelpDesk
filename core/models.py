from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


# ─── GEOGRAPHY ────────────────────────────────────────────────────────────────

class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "Countries"

class County(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='counties')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "Counties"

class SubCounty(models.Model):
    county = models.ForeignKey(County, on_delete=models.CASCADE, related_name='subcounties')
    name = models.CharField(max_length=100)
    def __str__(self): return f"{self.name} ({self.county.name})"
    class Meta: verbose_name_plural = "SubCounties"

class Ward(models.Model):
    subcounty = models.ForeignKey(SubCounty, on_delete=models.CASCADE, related_name='wards')
    name = models.CharField(max_length=100)
    def __str__(self): return f"{self.name} ({self.subcounty.name})"

class CHU(models.Model):
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name='chus')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True)
    def __str__(self): return self.name
    class Meta: verbose_name = "CHU"


# ─── USER ─────────────────────────────────────────────────────────────────────

class User(AbstractUser):
    ROLE_CHOICES = [
        ('superuser', 'Superuser'),
        ('tech_team', 'Tech Team'),
        ('country', 'Country User'),
        ('county', 'County User'),
        ('subcounty', 'SubCounty User'),
        ('cha', 'CHA'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cha')
    phone = models.CharField(max_length=20, blank=True)
    temp_password = models.CharField(max_length=100, blank=True)
    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.SET_NULL, related_name='users')
    county = models.ForeignKey(County, null=True, blank=True, on_delete=models.SET_NULL, related_name='users')
    subcounty = models.ForeignKey(SubCounty, null=True, blank=True, on_delete=models.SET_NULL, related_name='users')
    ward = models.ForeignKey(Ward, null=True, blank=True, on_delete=models.SET_NULL, related_name='users')
    chus = models.ManyToManyField(CHU, blank=True, related_name='users')
    must_change_password = models.BooleanField(default=False)

    def __str__(self): return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_superuser_or_tech(self): return self.role in ('superuser', 'tech_team')
    @property
    def can_manage_users(self): return self.role in ('superuser', 'tech_team', 'country', 'county', 'subcounty')
    @property
    def can_bulk_upload(self): return self.role in ('superuser', 'tech_team', 'country', 'county', 'subcounty')
    @property
    def can_add_devices(self): return self.role in ('superuser', 'tech_team', 'country', 'county', 'subcounty')
    @property
    def can_delete(self): return self.role in ('superuser', 'tech_team', 'country', 'county')

    def get_scope_chus(self):
        if self.role in ('superuser', 'tech_team'): return CHU.objects.all()
        elif self.role == 'country': return CHU.objects.filter(ward__subcounty__county__country=self.country)
        elif self.role == 'county': return CHU.objects.filter(ward__subcounty__county=self.county)
        elif self.role == 'subcounty': return CHU.objects.filter(ward__subcounty=self.subcounty)
        elif self.role == 'cha': return self.chus.all()
        return CHU.objects.none()

    def get_scope_label(self):
        if self.role in ('superuser', 'tech_team'): return "All Regions"
        elif self.role == 'country': return str(self.country) if self.country else "Country"
        elif self.role == 'county': return str(self.county) if self.county else "County"
        elif self.role == 'subcounty': return str(self.subcounty) if self.subcounty else "SubCounty"
        elif self.role == 'cha':
            chus = self.chus.all()
            return ", ".join(c.name for c in chus[:2]) + ("..." if chus.count() > 2 else "")
        return ""


# ─── ASSETS ───────────────────────────────────────────────────────────────────

class Device(models.Model):
    DEVICE_TYPES = [('phone', 'Phone'), ('tablet', 'Tablet'), ('laptop', 'Laptop')]
    STATUS = [('active', 'Active'), ('damaged', 'Damaged'), ('under_repair', 'Under Repair'), ('lost', 'Lost')]
    ROLES = [('chp', 'CHP'), ('cha', 'CHA'), ('focal_person', 'Focal Person')]

    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES)
    assigned_to_name = models.CharField(max_length=150)
    assigned_to_role = models.CharField(max_length=20, choices=ROLES)
    chu = models.ForeignKey(CHU, on_delete=models.CASCADE, related_name='devices')
    phone_model = models.CharField(max_length=100, blank=True)
    imei = models.CharField(max_length=50, blank=True, verbose_name="IMEI")
    serial_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='active')
    date_assigned = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self): return f"{self.get_device_type_display()} — {self.assigned_to_name}"

    @property
    def status_color(self):
        return {'active': 'success', 'damaged': 'danger', 'under_repair': 'warning', 'lost': 'secondary'}[self.status]


# ─── CREDENTIALS ──────────────────────────────────────────────────────────────

SYSTEM_CHOICES = [
    ('echis', 'eCHIS'),
    ('dashboard', 'Dashboard'),
    ('registry', 'Registry'),
    ('dhhd', 'This App (DHHD)'),
    ('other', 'Other'),
]

class CHPProfile(models.Model):
    """CHP — Community Health Promoter. Has eCHIS credentials only."""
    name = models.CharField(max_length=150)
    chu = models.ForeignKey(CHU, on_delete=models.CASCADE, related_name='chp_profiles')
    phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    # eCHIS credentials stored directly — CHPs only use eCHIS
    echis_username = models.CharField(max_length=150, blank=True)
    echis_password = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def __str__(self): return f"{self.name} ({self.chu})"


class CHAProfile(models.Model):
    """CHA — Community Health Assistant. Has eCHIS, Dashboard, and Registry credentials."""
    name = models.CharField(max_length=150)
    subcounty = models.ForeignKey(SubCounty, on_delete=models.CASCADE, related_name='cha_profiles')
    chus = models.ManyToManyField(CHU, blank=True, related_name='cha_profiles')
    phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    # eCHIS
    echis_username = models.CharField(max_length=150, blank=True)
    echis_password = models.CharField(max_length=255, blank=True)
    # Dashboard (formerly Dashboard + Power BI)
    dashboard_username = models.CharField(max_length=150, blank=True)
    dashboard_password = models.CharField(max_length=255, blank=True)
    # Registry
    registry_username = models.CharField(max_length=150, blank=True)
    registry_password = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def __str__(self): return f"{self.name} ({self.subcounty})"

    @property
    def chu_list(self):
        return ", ".join(c.name for c in self.chus.all())


# Keep StoredCredential for backward compat / other uses
class StoredCredential(models.Model):
    chp = models.ForeignKey(CHPProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='credentials')
    chu = models.ForeignKey(CHU, on_delete=models.SET_NULL, null=True, blank=True)
    system = models.CharField(max_length=20, choices=SYSTEM_CHOICES)
    system_other = models.CharField(max_length=100, blank=True)
    username = models.CharField(max_length=150)
    password = models.CharField(max_length=255)
    last_updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    last_updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    def __str__(self): return f"{self.chp.name if self.chp else '?'} — {self.get_system_display()}"

    @property
    def system_label(self):
        return self.system_other if self.system == 'other' else self.get_system_display()


# ─── INCIDENTS ────────────────────────────────────────────────────────────────

class IncidentCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "Incident Categories"

class Incident(models.Model):
    STATUS = [('open', 'Open'), ('in_progress', 'In Progress'), ('escalated', 'Escalated'), ('resolved', 'Resolved'), ('closed', 'Closed')]
    PRIORITY = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')]

    incident_number = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(IncidentCategory, on_delete=models.SET_NULL, null=True)
    chu = models.ForeignKey(CHU, on_delete=models.SET_NULL, null=True, related_name='incidents')
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='incidents_raised')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='incidents_assigned')
    status = models.CharField(max_length=20, choices=STATUS, default='open')
    priority = models.CharField(max_length=10, choices=PRIORITY, default='medium')
    attachment = models.FileField(upload_to='incidents/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self): return f"{self.incident_number} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.incident_number:
            last = Incident.objects.order_by('-id').first()
            self.incident_number = f"INC-{((last.id if last else 0) + 1):04d}"
        super().save(*args, **kwargs)

    @property
    def status_color(self):
        return {'open': 'danger', 'in_progress': 'warning', 'escalated': 'orange', 'resolved': 'success', 'closed': 'secondary'}[self.status]

    @property
    def priority_color(self):
        return {'low': 'success', 'medium': 'info', 'high': 'warning', 'critical': 'danger'}[self.priority]

class IncidentUpdate(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='updates')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    comment = models.TextField()
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['timestamp']


# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=300)
    link_type = models.CharField(max_length=30, blank=True)
    link_id = models.IntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']


# ─── AUDIT ────────────────────────────────────────────────────────────────────

class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)
    object_type = models.CharField(max_length=50, blank=True)
    object_id = models.IntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    extra = models.TextField(blank=True)
    class Meta: ordering = ['-timestamp']