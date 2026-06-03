from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.change_password_view, name='change_password'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Users
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/reset-password/', views.user_reset_password, name='user_reset_password'),
    path('users/bulk-upload/', views.bulk_upload_users, name='bulk_upload_users'),
    path('users/template/', views.download_user_template, name='user_template'),

    # Assets
    path('assets/', views.device_list, name='device_list'),
    path('assets/create/', views.device_create, name='device_create'),
    path('assets/<int:pk>/edit/', views.device_edit, name='device_edit'),
    path('assets/<int:pk>/delete/', views.device_delete, name='device_delete'),
    path('assets/bulk-upload/', views.bulk_upload_devices, name='bulk_upload_devices'),
    path('assets/template/', views.download_device_template, name='device_template'),

    # Credentials — CHP tab
    path('credentials/', views.chp_list, name='chp_list'),
    path('credentials/chp/create/', views.chp_create, name='chp_create'),
    path('credentials/chp/<int:pk>/edit/', views.chp_edit, name='chp_edit'),
    path('credentials/chp/<int:pk>/delete/', views.chp_delete, name='chp_delete'),
    path('credentials/chp/bulk-upload/', views.bulk_upload_chps, name='bulk_upload_chps'),
    path('credentials/chp/template/', views.download_chp_template, name='chp_template'),

    # Credentials — CHA tab
    path('credentials/cha/', views.cha_list, name='cha_list'),
    path('credentials/cha/create/', views.cha_create, name='cha_create'),
    path('credentials/cha/<int:pk>/edit/', views.cha_edit, name='cha_edit'),
    path('credentials/cha/<int:pk>/delete/', views.cha_delete, name='cha_delete'),
    path('credentials/cha/bulk-upload/', views.bulk_upload_chas, name='bulk_upload_chas'),
    path('credentials/cha/template/', views.download_cha_template, name='cha_template'),

    # Incidents
    path('incidents/', views.incident_list, name='incident_list'),
    path('incidents/create/', views.incident_create, name='incident_create'),
    path('incidents/<int:pk>/', views.incident_detail, name='incident_detail'),
    path('incidents/<int:pk>/edit/', views.incident_edit, name='incident_edit'),
    path('incidents/analytics/', views.incident_analytics, name='incident_analytics'),
    path('incidents/categories/', views.category_list, name='category_list'),
    path('incidents/categories/create/', views.category_create, name='category_create'),
    path('incidents/bulk-upload/', views.bulk_upload_incidents, name='bulk_upload_incidents'),
    path('incidents/template/', views.download_incident_template, name='incident_template'),

    # Notifications
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/mark-read/', views.mark_all_read, name='mark_all_read'),

    # Audit
    path('audit/', views.audit_log, name='audit_log'),

    # Geography AJAX
    path('ajax/counties/', views.ajax_counties, name='ajax_counties'),
    path('ajax/subcounties/', views.ajax_subcounties, name='ajax_subcounties'),
    path('ajax/wards/', views.ajax_wards, name='ajax_wards'),
    path('ajax/chus/', views.ajax_chus, name='ajax_chus'),
    path('ajax/chus-by-subcounty/', views.ajax_chus_by_subcounty, name='ajax_chus_by_subcounty'),

    #admin tools
    path('admin-tools/upload-geography/', views.upload_geography, name='upload_geography'),
    path('admin-tools/download-geography-template/', views.download_geography_template, name='geography_template'),

    path('assets/export/', views.export_devices, name='export_devices'),
    path('credentials/chp/export/', views.export_chps, name='export_chps'),
    path('credentials/cha/export/', views.export_chas, name='export_chas'),
    path('incidents/export/', views.export_incidents, name='export_incidents'),
]