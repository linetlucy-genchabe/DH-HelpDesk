from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Country, County, SubCounty, Ward, CHU,
    User, Device, CHPProfile, CHAProfile, StoredCredential,
    IncidentCategory, Incident, IncidentUpdate,
    Notification, AuditLog,
)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'get_full_name', 'role', 'subcounty', 'is_active']
    list_filter = ['role', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Role & Scope', {'fields': ('role', 'phone', 'country', 'county', 'subcounty', 'ward', 'chus', 'must_change_password')}),
    )

@admin.register(CHPProfile)
class CHPProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'chu', 'echis_username', 'is_active']
    list_filter = ['is_active', 'chu__ward__subcounty']
    search_fields = ['name', 'echis_username']

@admin.register(CHAProfile)
class CHAProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'subcounty', 'echis_username', 'dashboard_username', 'is_active']
    list_filter = ['is_active', 'subcounty']
    search_fields = ['name', 'echis_username']

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['assigned_to_name', 'assigned_to_role', 'device_type', 'chu', 'status', 'updated_at']
    list_filter = ['status', 'device_type', 'assigned_to_role']
    search_fields = ['assigned_to_name', 'imei', 'serial_number']

@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ['incident_number', 'title', 'status', 'priority', 'chu', 'raised_by']
    list_filter = ['status', 'priority', 'category']

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'object_type', 'object_id', 'ip_address', 'timestamp']
    list_filter = ['action']
    readonly_fields = ['user', 'action', 'object_type', 'object_id', 'ip_address', 'user_agent', 'timestamp', 'extra']

admin.site.register(Country)
admin.site.register(County)
admin.site.register(SubCounty)
admin.site.register(Ward)
admin.site.register(CHU)
admin.site.register(IncidentCategory)
admin.site.register(IncidentUpdate)
admin.site.register(Notification)