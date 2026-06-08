from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Count
import csv, io

from .models import (
    User, Country, County, SubCounty, Ward, CHU,
    Device, CHPProfile, CHAProfile, StoredCredential, SYSTEM_CHOICES,
    Incident, IncidentCategory, IncidentUpdate,
    Notification, PushSubscription, AuditLog,
)
from .utils import log_action, notify, generate_username, generate_password


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        user = authenticate(request, username=request.POST.get('username'), password=request.POST.get('password'))
        if user:
            login(request, user)
            log_action(request, 'LOGIN', 'User', user.pk)
            return redirect('dashboard')
        error = "Invalid username or password."
    return render(request, 'accounts/login.html', {'error': error})


@login_required
def logout_view(request):
    log_action(request, 'LOGOUT', 'User', request.user.pk)
    logout(request)
    return redirect('login')


@login_required
def change_password_view(request):
    error = None
    if request.method == 'POST':
        pw1 = request.POST.get('new_password', '')
        pw2 = request.POST.get('confirm_password', '')
        if len(pw1) < 8:
            error = "Password must be at least 8 characters."
        elif pw1 != pw2:
            error = "Passwords do not match."
        else:
            request.user.set_password(pw1)
            request.user.must_change_password = False
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Password changed successfully.")
            return redirect('dashboard')
    return render(request, 'accounts/change_password.html', {'error': error, 'forced': False})


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def dashboard(request):
    from django.utils import timezone
    scope_chus = request.user.get_scope_chus()
    device_qs = Device.objects.filter(chu__in=scope_chus)
    inc_qs = Incident.objects.filter(chu__in=scope_chus)
    now = timezone.now()
    return render(request, 'dashboard/home.html', {
        'asset_counts': {s: device_qs.filter(status=s).count() for s in ['active', 'damaged', 'under_repair', 'lost']},
        'asset_total': device_qs.count(),
        'chp_count': CHPProfile.objects.filter(chu__in=scope_chus).count(),
        'cha_count': CHAProfile.objects.filter(
            subcounty__in=SubCounty.objects.filter(wards__chus__in=scope_chus).distinct()
        ).distinct().count(),
        'incident_counts': {s: inc_qs.filter(status=s).count() for s in ['open', 'in_progress', 'escalated', 'resolved', 'closed']},
        'my_incidents': Incident.objects.filter(assigned_to=request.user, status__in=['open', 'in_progress', 'escalated']).order_by('-created_at')[:5],
        'recent_incidents': inc_qs.order_by('-created_at')[:5],
        'scope_label': request.user.get_scope_label(),
        'chu_count': scope_chus.count(),
        'devices_needing_attention': device_qs.filter(status__in=['damaged', 'under_repair', 'lost']).count(),
        'chps_not_reporting': device_qs.filter(reporting_status__in=['using_personal', 'not_reporting']).count(),
        'incidents_resolved_month': inc_qs.filter(status='resolved', updated_at__year=now.year, updated_at__month=now.month).count(),
    })


# ══════════════════════════════════════════════════════════════════════════════
# USER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def user_list(request):
    if not request.user.can_manage_users:
        messages.error(request, "Access denied."); return redirect('dashboard')
    
    qs = User.objects.exclude(role='superuser').select_related('county', 'subcounty', 'ward').prefetch_related('chus')

    if request.user.role == 'superuser':
        pass  # sees all including tech_team

    elif request.user.role == 'tech_team':
        qs = qs.exclude(role='tech_team')  # sees all except superuser and tech_team

    elif request.user.role == 'country':
        qs = qs.exclude(role__in=['tech_team', 'country']).filter(country=request.user.country)

    elif request.user.role == 'county':
        qs = qs.exclude(role__in=['tech_team', 'country', 'county']).filter(county=request.user.county)

    elif request.user.role == 'subcounty':
        qs = qs.exclude(role__in=['tech_team', 'country', 'county', 'subcounty']).filter(subcounty=request.user.subcounty)

    else:
        qs = User.objects.none()

    return render(request, 'accounts/user_list.html', {'users': qs})

@login_required
def user_create(request):
    if not request.user.can_manage_users:
        messages.error(request, "Access denied."); return redirect('dashboard')
    if request.method == 'POST':
        fn = request.POST.get('first_name', '').strip()
        ln = request.POST.get('last_name', '').strip()
        if not fn or not ln:
            messages.error(request, "First and last name are required.")
        else:
            username = generate_username(fn, ln)
            plain_pw = generate_password()
            u = User(first_name=fn, last_name=ln,
                     role=request.POST.get('role', 'cha'),
                     email=request.POST.get('email', '').strip(),
                     phone=request.POST.get('phone', '').strip(),
                     username=username, must_change_password=False)
            county_id = request.POST.get('county') or None
            subcounty_id = request.POST.get('subcounty') or None
            if county_id: u.county_id = county_id
            if subcounty_id:
                u.subcounty_id = subcounty_id
                sc = SubCounty.objects.get(pk=subcounty_id)
                u.county = sc.county; u.country = sc.county.country
            ward_id = request.POST.get('ward') or None
            if ward_id: u.ward_id = ward_id
            u.set_password(plain_pw)
            u.temp_password = plain_pw
            u.save()
            chu_ids = request.POST.getlist('chus')
            if chu_ids: u.chus.set(chu_ids)
            log_action(request, 'CREATE', 'User', u.pk)
            messages.success(request, f"User created — Username: {username} | Password: {plain_pw}")
            return redirect('user_list')

    # Role choices trickle down — each level can only create roles below them
    if request.user.role == 'superuser':
        role_choices = [r for r in User.ROLE_CHOICES if r[0] != 'superuser']
    elif request.user.role == 'tech_team':
        role_choices = [r for r in User.ROLE_CHOICES if r[0] not in ('superuser', 'tech_team')]
    elif request.user.role == 'country':
        role_choices = [r for r in User.ROLE_CHOICES if r[0] not in ('superuser', 'tech_team', 'country')]
    elif request.user.role == 'county':
        role_choices = [r for r in User.ROLE_CHOICES if r[0] not in ('superuser', 'tech_team', 'country', 'county')]
    elif request.user.role == 'subcounty':
        role_choices = [r for r in User.ROLE_CHOICES if r[0] == 'cha']
    else:
        role_choices = []

    return render(request, 'accounts/user_form.html', {
        'title': 'Create User',
        'counties': County.objects.all(),
        'subcounties': SubCounty.objects.all(),
        'wards': Ward.objects.all(),
        'chus': request.user.get_scope_chus(),
        'role_choices': role_choices,
    })

@login_required
def user_edit(request, pk):
    if not request.user.can_manage_users:
        messages.error(request, "Access denied."); return redirect('dashboard')
    u = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        u.first_name = request.POST.get('first_name', u.first_name)
        u.last_name = request.POST.get('last_name', u.last_name)
        u.email = request.POST.get('email', u.email)
        u.phone = request.POST.get('phone', u.phone)
        u.role = request.POST.get('role', u.role)
        u.is_active = 'is_active' in request.POST
        u.county_id = request.POST.get('county') or None
        u.subcounty_id = request.POST.get('subcounty') or None
        u.ward_id = request.POST.get('ward') or None
        u.save()
        chu_ids = request.POST.getlist('chus')
        if chu_ids: u.chus.set(chu_ids)
        else: u.chus.clear()
        log_action(request, 'UPDATE', 'User', u.pk)
        messages.success(request, "User updated.")
        return redirect('user_list')
    return render(request, 'accounts/user_form.html', {
        'title': 'Edit User', 'obj': u,
        'counties': County.objects.all(),
        'subcounties': SubCounty.objects.all(),
        'wards': Ward.objects.all(),
        'chus': request.user.get_scope_chus(),
        'role_choices': [r for r in User.ROLE_CHOICES if r[0] != 'superuser'],
    })

@login_required
def user_reset_password(request, pk):
    if not request.user.can_manage_users:
        messages.error(request, "Access denied."); return redirect('dashboard')
    u = get_object_or_404(User, pk=pk)
    plain_pw = generate_password()
    u.set_password(plain_pw)
    u.must_change_password = False
    u.temp_password = plain_pw
    u.save()
    log_action(request, 'PASSWORD_RESET', 'User', u.pk)
    messages.success(request, f"Password reset for {u.get_full_name()} — New password: {plain_pw}")
    return redirect('user_list')

@login_required
def bulk_upload_users(request):
    if not request.user.can_bulk_upload:
        messages.error(request, "Access denied."); return redirect('user_list')
    if request.method == 'POST':
        f = request.FILES.get('csv_file')
        if not f:
            messages.error(request, "No file uploaded.")
            return render(request, 'accounts/bulk_upload.html', {'type': 'Users'})
        reader = csv.DictReader(io.StringIO(f.read().decode('utf-8')))
        created, errors = 0, []
        for i, row in enumerate(reader, 2):
            try:
                fn = row.get('first_name', '').strip()
                ln = row.get('last_name', '').strip()
                u = User(first_name=fn, last_name=ln,
                         role=row.get('role', 'cha').strip(),
                         email=row.get('email', '').strip(),
                         phone=row.get('phone', '').strip(),
                         username=generate_username(fn, ln),
                         must_change_password=False)
                sc_name = row.get('subcounty', '').strip()
                if sc_name:
                    sc = SubCounty.objects.filter(name__iexact=sc_name).first()
                    if sc: u.subcounty = sc; u.county = sc.county; u.country = sc.county.country
                u.set_password(generate_password())
                u.save()
                created += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")
        log_action(request, 'BULK_UPLOAD', 'User')
        messages.success(request, f"{created} users created." + (f" Errors: {'; '.join(errors[:5])}" if errors else ""))
        return redirect('user_list')
    return render(request, 'accounts/bulk_upload.html', {'type': 'Users'})


@login_required
def download_user_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="user_template.csv"'
    w = csv.writer(response)
    w.writerow(['first_name', 'last_name', 'email', 'phone', 'role', 'county', 'subcounty'])
    w.writerow(['Jane', 'Doe', 'jane@example.com', '0700000000', 'cha', 'Kisumu', 'Kisumu West'])
    return response


# ══════════════════════════════════════════════════════════════════════════════
# ASSETS
# ══════════════════════════════════════════════════════════════════════════════

def _starting_level(user):
    return {
        'superuser': 'countries', 'tech_team': 'countries',
        'country': 'counties', 'county': 'subcounties',
        'subcounty': 'chus', 'cha': 'devices',
    }.get(user.role, 'devices')


def _device_stats(chus):
    qs = Device.objects.filter(chu__in=chus)
    replaced_originals = qs.filter(status='replaced', replaced_by__isnull=False).count()
    return {
        'total': qs.count() - replaced_originals,
        'active': qs.filter(status='active').count(),
        'damaged': qs.filter(status='damaged').count(),
        'under_repair': qs.filter(status='under_repair').count(),
        'lost': qs.filter(status='lost').count() + replaced_originals,
        'replaced': replaced_originals,
    }


def _device_drill(request):
    user = request.user
    role = user.role
    level = request.GET.get('level', _starting_level(user))
    country_id = request.GET.get('country')
    county_id = request.GET.get('county')
    subcounty_id = request.GET.get('subcounty')
    chu_id = request.GET.get('chu')
    breadcrumb = [{'label': 'Assets', 'url': '/assets/'}]
    items = []

    if level == 'countries':
        for c in Country.objects.all():
            chus = CHU.objects.filter(ward__subcounty__county__country=c)
            items.append({'id': c.pk, 'name': c.name, 'sub_label': f"{c.counties.count()} counties",
                          'next_label': 'View counties', 'next_url': f'?level=counties&country={c.pk}',
                          **_device_stats(chus)})
        return level, items, breadcrumb, None, None

    if level == 'counties':
        if country_id:
            country = Country.objects.filter(pk=country_id).first()
            counties = County.objects.filter(country_id=country_id)
            if country: breadcrumb.append({'label': country.name, 'url': '/assets/?level=countries'})
        elif role == 'country' and user.country:
            counties = County.objects.filter(country=user.country)
        else:
            counties = County.objects.all()
        for c in counties:
            chus = CHU.objects.filter(ward__subcounty__county=c)
            items.append({'id': c.pk, 'name': c.name, 'sub_label': f"{c.subcounties.count()} sub-counties",
                          'next_label': 'View sub-counties', 'next_url': f'?level=subcounties&county={c.pk}',
                          **_device_stats(chus)})
        return level, items, breadcrumb, None, None

    if level == 'subcounties':
        if county_id:
            county = County.objects.filter(pk=county_id).first()
            subcounties = SubCounty.objects.filter(county_id=county_id)
            if county: breadcrumb.append({'label': county.name, 'url': f'/assets/?level=counties&country={county.country_id}'})
        elif role == 'county' and user.county:
            subcounties = SubCounty.objects.filter(county=user.county)
        else:
            subcounties = SubCounty.objects.all()
        for sc in subcounties:
            chus = CHU.objects.filter(ward__subcounty=sc)
            items.append({'id': sc.pk, 'name': sc.name, 'sub_label': f"{chus.count()} CHUs",
                          'next_label': 'View CHUs', 'next_url': f'?level=chus&subcounty={sc.pk}',
                          **_device_stats(chus)})
        return level, items, breadcrumb, None, None

    if level == 'chus':
        if subcounty_id:
            sc = SubCounty.objects.filter(pk=subcounty_id).first()
            chus = CHU.objects.filter(ward__subcounty_id=subcounty_id).select_related('ward')
            if sc: breadcrumb.append({'label': sc.name, 'url': f'/assets/?level=subcounties&county={sc.county_id}'})
        elif role == 'subcounty' and user.subcounty:
            chus = CHU.objects.filter(ward__subcounty=user.subcounty).select_related('ward')
        else:
            chus = user.get_scope_chus().select_related('ward')
        for chu in chus:
            items.append({'id': chu.pk, 'name': chu.name, 'sub_label': chu.ward.name,
                          'next_label': 'View devices', 'next_url': f'?level=devices&chu={chu.pk}',
                          **_device_stats([chu])})
        return level, items, breadcrumb, None, None

    # devices level
    if chu_id:
        chu = CHU.objects.filter(pk=chu_id).first()
        device_qs = Device.objects.filter(chu_id=chu_id).select_related('chu__ward__subcounty')
        if chu: breadcrumb.append({'label': chu.name, 'url': f'/assets/?level=chus&subcounty={chu.ward.subcounty_id}'})
        return 'devices', [], breadcrumb, device_qs, chu_id
    else:
        return 'devices', [], breadcrumb, Device.objects.filter(chu__in=user.get_scope_chus()).select_related('chu__ward__subcounty'), None


@login_required
def device_list(request):
    drill_level, items, breadcrumb, device_qs, chu_filter = _device_drill(request)
    status_f = request.GET.get('status', '')
    search = request.GET.get('q', '')
    reporting_f = request.GET.get('reporting', '')
    counts = {}
    devices = []
    scope_chus = request.user.get_scope_chus()

    if chu_filter:
        summary_chus = CHU.objects.filter(pk=chu_filter)
    elif request.GET.get('subcounty'):
        summary_chus = CHU.objects.filter(ward__subcounty_id=request.GET.get('subcounty'))
    elif request.GET.get('county'):
        summary_chus = CHU.objects.filter(ward__subcounty__county_id=request.GET.get('county'))
    elif request.GET.get('country'):
        summary_chus = CHU.objects.filter(ward__subcounty__county__country_id=request.GET.get('country'))
    else:
        summary_chus = scope_chus

    all_devices = Device.objects.filter(chu__in=summary_chus)
    replaced_originals = all_devices.filter(status='replaced', replaced_by__isnull=False).count()
    summary = {s: all_devices.filter(status=s).count() for s in ['active', 'damaged', 'under_repair', 'lost', 'replaced']}
    summary['total'] = all_devices.count() - replaced_originals
    summary['using_personal'] = all_devices.filter(reporting_status='using_personal').count()
    summary['not_reporting'] = all_devices.filter(reporting_status='not_reporting').count()

    if drill_level == 'devices' and device_qs is not None:
        if status_f: device_qs = device_qs.filter(status=status_f)
        if reporting_f: device_qs = device_qs.filter(reporting_status=reporting_f)
        if search: device_qs = device_qs.filter(
            Q(assigned_to_name__icontains=search) | Q(phone_model__icontains=search) |
            Q(imei__icontains=search) | Q(serial_number__icontains=search)
        )
        base_qs = Device.objects.filter(chu__in=summary_chus)
        base_replaced_originals = base_qs.filter(status='replaced', replaced_by__isnull=False).count()
        counts = {s: base_qs.filter(status=s).count() for s in ['active', 'damaged', 'under_repair', 'lost', 'replaced']}
        counts['total'] = base_qs.count() - base_replaced_originals
        counts['using_personal'] = base_qs.filter(reporting_status='using_personal').count()
        counts['not_reporting'] = base_qs.filter(reporting_status='not_reporting').count()
        devices = device_qs.select_related('replaced_by', 'replaces').order_by('assigned_to_name', 'created_at')

    return render(request, 'assets/device_list.html', {
        'drill_level': drill_level, 'items': items, 'breadcrumb': breadcrumb,
        'devices': devices, 'counts': counts, 'summary': summary,
        'status_f': status_f, 'search': search, 'chu_filter': chu_filter,
        'reporting_f': reporting_f,
    })


@login_required
def device_create(request):
    if not request.user.can_add_devices:
        messages.error(request, "Access denied."); return redirect('device_list')
    if request.method == 'POST':
        chu = get_object_or_404(CHU, pk=request.POST.get('chu'))
        Device.objects.create(
            device_type=request.POST.get('device_type', 'phone'),
            assigned_to_name=request.POST.get('assigned_to_name', '').strip(),
            assigned_to_role=request.POST.get('assigned_to_role', 'chp'),
            chu=chu, phone_model=request.POST.get('phone_model', '').strip(),
            imei=request.POST.get('imei', '').strip(),
            serial_number=request.POST.get('serial_number', '').strip(),
            status=request.POST.get('status', 'active'),
            date_assigned=request.POST.get('date_assigned') or None,
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user, updated_by=request.user,
        )
        log_action(request, 'CREATE', 'Device')
        messages.success(request, "Device added.")
        return redirect('device_list')
    return render(request, 'assets/device_form.html', {
        'title': 'Add Device', 'chus': request.user.get_scope_chus(),
        'device_types': Device.DEVICE_TYPES, 'roles': Device.ROLES, 'statuses': Device.STATUS,
        'reporting_statuses': Device.REPORTING_STATUS,
    })


@login_required
def device_edit(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if device.chu not in request.user.get_scope_chus():
        messages.error(request, "Access denied."); return redirect('device_list')
    if request.method == 'POST':
        new_status = request.POST.get('status', device.status)

        device.status = new_status
        device.notes = request.POST.get('notes', device.notes)
        device.incident_date = request.POST.get('incident_date') or None
        device.reporting_status = request.POST.get('reporting_status', 'normal')

        if new_status == 'active':
            device.reporting_status = 'normal'
            device.incident_date = None

        if request.user.role != 'cha':
            chu = get_object_or_404(CHU, pk=request.POST.get('chu'))
            device.device_type = request.POST.get('device_type', device.device_type)
            device.assigned_to_name = request.POST.get('assigned_to_name', device.assigned_to_name)
            device.assigned_to_role = request.POST.get('assigned_to_role', device.assigned_to_role)
            device.chu = chu
            device.phone_model = request.POST.get('phone_model', '')
            device.imei = request.POST.get('imei', '')
            device.serial_number = request.POST.get('serial_number', '')
            device.date_assigned = request.POST.get('date_assigned') or None

        device.updated_by = request.user
        device.save()

        if new_status == 'replaced' and request.POST.get('new_phone_model'):
            replacement = Device.objects.create(
                device_type=device.device_type,
                assigned_to_name=device.assigned_to_name,
                assigned_to_role=device.assigned_to_role,
                chu=device.chu,
                phone_model=request.POST.get('new_phone_model', '').strip(),
                imei=request.POST.get('new_imei', '').strip(),
                serial_number=request.POST.get('new_serial_number', '').strip(),
                status='active',
                date_assigned=request.POST.get('new_date_assigned') or None,
                reporting_status='normal',
                created_by=request.user, updated_by=request.user,
            )
            device.replaced_by = replacement
            device.save()
            messages.success(request, f"Device marked as replaced. New device record created for {device.assigned_to_name}.")
        else:
            messages.success(request, "Device updated.")

        log_action(request, 'UPDATE', 'Device', device.pk)
        return redirect('device_list')

    return render(request, 'assets/device_form.html', {
        'title': 'Edit Device', 'obj': device, 'chus': request.user.get_scope_chus(),
        'device_types': Device.DEVICE_TYPES, 'roles': Device.ROLES, 'statuses': Device.STATUS,
        'reporting_statuses': Device.REPORTING_STATUS,
        'status_only': request.user.role == 'cha',
    })


@login_required
def device_delete(request, pk):
    if not request.user.can_delete:
        messages.error(request, "Access denied."); return redirect('device_list')
    device = get_object_or_404(Device, pk=pk)
    if request.method == 'POST':
        log_action(request, 'DELETE', 'Device', device.pk)
        device.delete()
        messages.success(request, "Device deleted.")
    return redirect('device_list')


@login_required
def bulk_upload_devices(request):
    if not request.user.can_bulk_upload:
        messages.error(request, "Access denied."); return redirect('device_list')
    if request.method == 'POST':
        f = request.FILES.get('csv_file')
        if not f:
            messages.error(request, "No file.")
            return render(request, 'assets/bulk_upload.html', {'type': 'Devices'})
        reader = csv.DictReader(io.StringIO(f.read().decode('utf-8')))
        created, errors = 0, []
        for i, row in enumerate(reader, 2):
            try:
                chu_name = row.get('chu', '').strip()
                subcounty_name = row.get('subcounty', '').strip()
                if subcounty_name:
                    chu = CHU.objects.filter(name__iexact=chu_name, ward__subcounty__name__iexact=subcounty_name).first()
                else:
                    chu = CHU.objects.filter(name__iexact=chu_name).first()
                if not chu:
                    raise ValueError(f"CHU '{chu_name}' not found in subcounty '{subcounty_name}'")
                raw_status = row.get('status', '').strip().lower()
                if raw_status not in ('active', 'damaged', 'under_repair', 'lost'):
                    raw_status = 'active'
                Device.objects.create(
                    device_type=row.get('device_type', 'phone').strip() or 'phone',
                    assigned_to_name=row.get('assigned_to_name', '').strip(),
                    assigned_to_role=row.get('assigned_to_role', 'chp').strip() or 'chp',
                    chu=chu, phone_model=row.get('phone_model', '').strip(),
                    imei=row.get('imei', '').strip(),
                    serial_number=row.get('serial_number', '').strip(),
                    status=raw_status, created_by=request.user, updated_by=request.user,
                )
                created += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")
        log_action(request, 'BULK_UPLOAD', 'Device')
        messages.success(request, f"{created} devices imported." + (f" Errors: {'; '.join(errors[:5])}" if errors else ""))
        return redirect('device_list')
    return render(request, 'assets/bulk_upload.html', {'type': 'Devices'})


@login_required
def download_device_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="device_template.csv"'
    w = csv.writer(response)
    w.writerow(['county', 'subcounty', 'chu', 'assigned_to_name', 'assigned_to_role', 'phone_model', 'serial_number', 'imei', 'status', 'device_type'])
    w.writerow(['Kisumu', 'Kisumu West', 'Dago', 'John Mwangi', 'chp', 'Neon Ray Ultra', 'AM32ETYQ001', '356127310001', 'active', 'phone'])
    return response


# ══════════════════════════════════════════════════════════════════════════════
# CREDENTIALS — DRILL-DOWN HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _chp_stats(chus):
    chps = CHPProfile.objects.filter(chu__in=chus)
    return {
        'total': chps.count(),
        'cred_count': chps.filter(echis_username__gt='').count(),
    }


def _cred_drill(request):
    user = request.user
    role = user.role
    level = request.GET.get('level', _starting_level(user))
    country_id = request.GET.get('country')
    county_id = request.GET.get('county')
    subcounty_id = request.GET.get('subcounty')
    chu_id = request.GET.get('chu')
    breadcrumb = [{'label': 'Accounts', 'url': '/credentials/'}]
    items = []

    if level == 'countries':
        for c in Country.objects.all():
            chus = CHU.objects.filter(ward__subcounty__county__country=c)
            stats = _chp_stats(chus)
            items.append({'id': c.pk, 'name': c.name, 'sub_label': f"{c.counties.count()} counties",
                          'next_label': 'View counties', 'next_url': f'?level=counties&country={c.pk}', **stats})
        return level, items, breadcrumb, None, None

    if level == 'counties':
        if country_id:
            country = Country.objects.filter(pk=country_id).first()
            counties = County.objects.filter(country_id=country_id)
            if country: breadcrumb.append({'label': country.name, 'url': '/credentials/?level=countries'})
        elif role == 'country' and user.country:
            counties = County.objects.filter(country=user.country)
        else:
            counties = County.objects.all()
        for c in counties:
            chus = CHU.objects.filter(ward__subcounty__county=c)
            stats = _chp_stats(chus)
            items.append({'id': c.pk, 'name': c.name, 'sub_label': f"{c.subcounties.count()} sub-counties",
                          'next_label': 'View sub-counties', 'next_url': f'?level=subcounties&county={c.pk}', **stats})
        return level, items, breadcrumb, None, None

    if level == 'subcounties':
        if county_id:
            county = County.objects.filter(pk=county_id).first()
            subcounties = SubCounty.objects.filter(county_id=county_id)
            if county: breadcrumb.append({'label': county.name, 'url': f'/credentials/?level=counties&country={county.country_id}'})
        elif role == 'county' and user.county:
            subcounties = SubCounty.objects.filter(county=user.county)
        else:
            subcounties = SubCounty.objects.all()
        for sc in subcounties:
            chus = CHU.objects.filter(ward__subcounty=sc)
            stats = _chp_stats(chus)
            items.append({'id': sc.pk, 'name': sc.name, 'sub_label': f"{chus.count()} CHUs",
                          'next_label': 'View CHUs', 'next_url': f'?level=chus&subcounty={sc.pk}', **stats})
        return level, items, breadcrumb, None, None

    if level == 'chus':
        if subcounty_id:
            sc = SubCounty.objects.filter(pk=subcounty_id).first()
            chus = CHU.objects.filter(ward__subcounty_id=subcounty_id).select_related('ward')
            if sc: breadcrumb.append({'label': sc.name, 'url': f'/credentials/?level=subcounties&county={sc.county_id}'})
        elif role == 'subcounty' and user.subcounty:
            chus = CHU.objects.filter(ward__subcounty=user.subcounty).select_related('ward')
        else:
            chus = user.get_scope_chus().select_related('ward')
        for chu in chus:
            stats = _chp_stats([chu])
            items.append({'id': chu.pk, 'name': chu.name, 'sub_label': chu.ward.name,
                          'next_label': 'View CHPs', 'next_url': f'?level=chps&chu={chu.pk}', **stats})
        return level, items, breadcrumb, None, None

    if chu_id:
        chu = CHU.objects.filter(pk=chu_id).first()
        chp_qs = CHPProfile.objects.filter(chu_id=chu_id)
        if chu: breadcrumb.append({'label': chu.name, 'url': f'/credentials/?level=chus&subcounty={chu.ward.subcounty_id}'})
        return 'chps', [], breadcrumb, chp_qs, chu_id
    else:
        return 'chps', [], breadcrumb, CHPProfile.objects.filter(chu__in=user.get_scope_chus()), None


# ══════════════════════════════════════════════════════════════════════════════
# CHP CREDENTIALS (Tab 1)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def chp_list(request):
    drill_level, items, breadcrumb, chp_qs, chu_filter = _cred_drill(request)
    search = request.GET.get('q', '')
    profiles = []
    scope_chus = request.user.get_scope_chus()

    # Summary should reflect current drill level, not full scope
    if drill_level == 'chps' and chu_filter:
        summary_chus = CHU.objects.filter(pk=chu_filter)
    elif request.GET.get('subcounty'):
        summary_chus = CHU.objects.filter(ward__subcounty_id=request.GET.get('subcounty'))
    elif request.GET.get('county'):
        summary_chus = CHU.objects.filter(ward__subcounty__county_id=request.GET.get('county'))
    elif request.GET.get('country'):
        summary_chus = CHU.objects.filter(ward__subcounty__county__country_id=request.GET.get('country'))
    else:
        summary_chus = scope_chus

    all_chps = CHPProfile.objects.filter(chu__in=summary_chus)
    summary = {
        'total': all_chps.count(),
        'cred_count': all_chps.filter(echis_username__gt='').count(),
    }

    if drill_level == 'chps' and chp_qs is not None:
        if search: chp_qs = chp_qs.filter(name__icontains=search)
        profiles = chp_qs.select_related('chu__ward__subcounty')

    return render(request, 'credentials/chp_list.html', {
        'drill_level': drill_level, 'items': items, 'breadcrumb': breadcrumb,
        'profiles': profiles, 'summary': summary,
        'search': search, 'chu_filter': chu_filter,
        'active_tab': 'chp',
    })


@login_required
def chp_create(request):
    if request.method == 'POST':
        chu = get_object_or_404(CHU, pk=request.POST.get('chu'))
        CHPProfile.objects.create(
            name=request.POST.get('name', '').strip(), chu=chu,
            phone=request.POST.get('phone', '').strip(),
            echis_username=request.POST.get('echis_username', '').strip(),
            echis_password=request.POST.get('echis_password', '').strip(),
            is_active='is_active' in request.POST,
            updated_by=request.user,
        )
        log_action(request, 'CREATE', 'CHPProfile')
        messages.success(request, "CHP profile created.")
        return redirect('chp_list')
    return render(request, 'credentials/chp_form.html', {
        'title': 'Add CHP', 'chus': request.user.get_scope_chus(),
    })


@login_required
def chp_edit(request, pk):
    chp = get_object_or_404(CHPProfile, pk=pk)
    if chp.chu not in request.user.get_scope_chus():
        messages.error(request, "Access denied."); return redirect('chp_list')
    if request.method == 'POST':
        chp.name = request.POST.get('name', chp.name)
        chp.phone = request.POST.get('phone', chp.phone)
        chp.echis_username = request.POST.get('echis_username', chp.echis_username)
        chp.echis_password = request.POST.get('echis_password', chp.echis_password)
        chp.is_active = 'is_active' in request.POST
        chu_id = request.POST.get('chu')
        if chu_id: chp.chu_id = chu_id
        chp.updated_by = request.user
        chp.save()
        log_action(request, 'UPDATE', 'CHPProfile', chp.pk)
        messages.success(request, "CHP updated.")
        return redirect('chp_list')
    return render(request, 'credentials/chp_form.html', {
        'title': 'Edit CHP', 'obj': chp, 'chus': request.user.get_scope_chus(),
    })


@login_required
def chp_delete(request, pk):
    if not request.user.can_delete:
        messages.error(request, "Access denied."); return redirect('chp_list')
    chp = get_object_or_404(CHPProfile, pk=pk)
    if request.method == 'POST':
        log_action(request, 'DELETE', 'CHPProfile', chp.pk)
        chp.delete()
        messages.success(request, "CHP deleted.")
    return redirect('chp_list')


@login_required
def bulk_upload_chps(request):
    if not request.user.can_bulk_upload:
        messages.error(request, "Access denied."); return redirect('chp_list')
    if request.method == 'POST':
        f = request.FILES.get('csv_file')
        if not f:
            messages.error(request, "No file.")
            return render(request, 'credentials/bulk_upload_chp.html', {'type': 'CHP Credentials'})
        reader = csv.DictReader(io.StringIO(f.read().decode('utf-8')))
        created, updated, errors = 0, 0, []
        for i, row in enumerate(reader, 2):
            try:
                chu_name = row.get('chu', '').strip()
                subcounty_name = row.get('subcounty', '').strip()
                if subcounty_name:
                    chu = CHU.objects.filter(name__iexact=chu_name, ward__subcounty__name__iexact=subcounty_name).first()
                else:
                    chu = CHU.objects.filter(name__iexact=chu_name).first()
                if not chu:
                    raise ValueError(f"CHU '{chu_name}' not found")
                name = row.get('chp_name', '').strip()
                chp, was_created = CHPProfile.objects.get_or_create(name__iexact=name, chu=chu,
                    defaults={'name': name, 'chu': chu})
                chp.echis_username = row.get('echis_username', '').strip()
                chp.echis_password = row.get('echis_password', '').strip()
                chp.phone = row.get('phone', chp.phone).strip()
                chp.updated_by = request.user
                chp.save()
                if was_created: created += 1
                else: updated += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")
        log_action(request, 'BULK_UPLOAD', 'CHPProfile')
        messages.success(request, f"{created} created, {updated} updated." + (f" Errors: {'; '.join(errors[:5])}" if errors else ""))
        return redirect('chp_list')
    return render(request, 'credentials/bulk_upload_chp.html', {'type': 'CHP Credentials'})


@login_required
def download_chp_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="chp_credentials_template.csv"'
    w = csv.writer(response)
    w.writerow(['county', 'subcounty', 'chu', 'chp_name','echis_username', 'echis_password'])
    w.writerow(['Kisumu', 'Kisumu West', 'Dago', 'Jane Anyango', 'janyango2023', 'Pass@123'])
    return response


# ══════════════════════════════════════════════════════════════════════════════
# CHA CREDENTIALS (Tab 2)
# ══════════════════════════════════════════════════════════════════════════════

def _get_cha_scope(user):
    scope_chus = user.get_scope_chus()
    subcounties = SubCounty.objects.filter(wards__chus__in=scope_chus).distinct()
    return CHAProfile.objects.filter(subcounty__in=subcounties).prefetch_related('chus')


@login_required
def cha_list(request):
    search = request.GET.get('q', '')
    subcounty_f = request.GET.get('subcounty', '')
    qs = _get_cha_scope(request.user)
    if search: qs = qs.filter(name__icontains=search)
    if subcounty_f: qs = qs.filter(subcounty_id=subcounty_f)
    scope_chus = request.user.get_scope_chus()
    subcounties = SubCounty.objects.filter(wards__chus__in=scope_chus).distinct()
    summary = {
        'total': qs.count(),
        'with_echis': qs.filter(echis_username__gt='').count(),
        'with_dashboard': qs.filter(dashboard_username__gt='').count(),
        'with_registry': qs.filter(registry_username__gt='').count(),
    }
    return render(request, 'credentials/cha_list.html', {
        'profiles': qs.select_related('subcounty').order_by('subcounty__name', 'name'),
        'summary': summary,
        'subcounties': subcounties,
        'search': search,
        'subcounty_f': subcounty_f,
        'active_tab': 'cha',
    })


@login_required
def cha_create(request):
    scope_chus = request.user.get_scope_chus()
    subcounties = SubCounty.objects.filter(wards__chus__in=scope_chus).distinct()
    if request.method == 'POST':
        sc = get_object_or_404(SubCounty, pk=request.POST.get('subcounty'))
        cha = CHAProfile.objects.create(
            name=request.POST.get('name', '').strip(),
            subcounty=sc,
            phone=request.POST.get('phone', '').strip(),
            echis_username=request.POST.get('echis_username', '').strip(),
            echis_password=request.POST.get('echis_password', '').strip(),
            dashboard_username=request.POST.get('dashboard_username', '').strip(),
            dashboard_password=request.POST.get('dashboard_password', '').strip(),
            registry_username=request.POST.get('registry_username', '').strip(),
            registry_password=request.POST.get('registry_password', '').strip(),
            is_active='is_active' in request.POST,
            updated_by=request.user,
        )
        chu_ids = request.POST.getlist('chus')
        if chu_ids: cha.chus.set(chu_ids)
        log_action(request, 'CREATE', 'CHAProfile')
        messages.success(request, "CHA profile created.")
        return redirect('cha_list')
    return render(request, 'credentials/cha_form.html', {
        'title': 'Add CHA', 'subcounties': subcounties, 'chus': scope_chus,
    })


@login_required
def cha_edit(request, pk):
    cha = get_object_or_404(CHAProfile, pk=pk)
    scope_chus = request.user.get_scope_chus()
    subcounties = SubCounty.objects.filter(wards__chus__in=scope_chus).distinct()
    if request.method == 'POST':
        cha.name = request.POST.get('name', cha.name)
        cha.phone = request.POST.get('phone', cha.phone)
        sc_id = request.POST.get('subcounty')
        if sc_id: cha.subcounty_id = sc_id
        cha.echis_username = request.POST.get('echis_username', cha.echis_username)
        cha.echis_password = request.POST.get('echis_password', cha.echis_password)
        cha.dashboard_username = request.POST.get('dashboard_username', cha.dashboard_username)
        cha.dashboard_password = request.POST.get('dashboard_password', cha.dashboard_password)
        cha.registry_username = request.POST.get('registry_username', cha.registry_username)
        cha.registry_password = request.POST.get('registry_password', cha.registry_password)
        cha.is_active = 'is_active' in request.POST
        cha.updated_by = request.user
        cha.save()
        chu_ids = request.POST.getlist('chus')
        if chu_ids: cha.chus.set(chu_ids)
        else: cha.chus.clear()
        log_action(request, 'UPDATE', 'CHAProfile', cha.pk)
        messages.success(request, "CHA updated.")
        return redirect('cha_list')
    return render(request, 'credentials/cha_form.html', {
        'title': 'Edit CHA', 'obj': cha,
        'subcounties': subcounties, 'chus': scope_chus,
    })


@login_required
def cha_delete(request, pk):
    if not request.user.can_delete:
        messages.error(request, "Access denied."); return redirect('cha_list')
    cha = get_object_or_404(CHAProfile, pk=pk)
    if request.method == 'POST':
        log_action(request, 'DELETE', 'CHAProfile', cha.pk)
        cha.delete()
        messages.success(request, "CHA deleted.")
    return redirect('cha_list')


@login_required
def bulk_upload_chas(request):
    if not request.user.can_bulk_upload:
        messages.error(request, "Access denied."); return redirect('cha_list')
    if request.method == 'POST':
        f = request.FILES.get('csv_file')
        if not f:
            messages.error(request, "No file.")
            return render(request, 'credentials/bulk_upload_cha.html', {'type': 'CHA Credentials'})
        reader = csv.DictReader(io.StringIO(f.read().decode('utf-8')))
        created, updated, errors = 0, 0, []
        for i, row in enumerate(reader, 2):
            try:
                sc_name = row.get('subcounty', '').strip()
                county_name = row.get('county', '').strip()
                if county_name:
                    sc = SubCounty.objects.filter(name__iexact=sc_name, county__name__iexact=county_name).first()
                else:
                    sc = SubCounty.objects.filter(name__iexact=sc_name).first()
                if not sc:
                    raise ValueError(f"SubCounty '{sc_name}' not found")
                name = row.get('cha_name', '').strip()
                cha, was_created = CHAProfile.objects.get_or_create(
                    name__iexact=name, subcounty=sc,
                    defaults={'name': name, 'subcounty': sc}
                )
                cha.echis_username = row.get('echis_username', '').strip()
                cha.echis_password = row.get('echis_password', '').strip()
                cha.dashboard_username = row.get('dashboard_username', '').strip()
                cha.dashboard_password = row.get('dashboard_password', '').strip()
                cha.registry_username = row.get('registry_username', '').strip()
                cha.registry_password = row.get('registry_password', '').strip()
                cha.phone = row.get('phone', cha.phone).strip()
                cha.updated_by = request.user
                cha.save()
                # Assign CHUs if provided
                chu_names = row.get('chus', '').strip()
                if chu_names:
                    for cn in chu_names.split('|'):
                        chu = CHU.objects.filter(name__iexact=cn.strip(), ward__subcounty=sc).first()
                        if chu: cha.chus.add(chu)
                if was_created: created += 1
                else: updated += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")
        log_action(request, 'BULK_UPLOAD', 'CHAProfile')
        messages.success(request, f"{created} created, {updated} updated." + (f" Errors: {'; '.join(errors[:5])}" if errors else ""))
        return redirect('cha_list')
    return render(request, 'credentials/bulk_upload_cha.html', {'type': 'CHA Credentials'})


@login_required
def download_cha_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="cha_credentials_template.csv"'
    w = csv.writer(response)
    w.writerow(['county', 'subcounty', 'cha_name', 'chus',
                'echis_username', 'echis_password',
                'dashboard_username', 'dashboard_password',
                'registry_username', 'registry_password'])
    w.writerow(['Kisumu', 'Kisumu West', 'Rose Achieng', 'Dago|Manyatta B',
                'rachieng2023', 'Pass@123', 'rachieng_db', 'Pass@456', 'rachieng_reg', 'Pass@789'])
    return response


# ══════════════════════════════════════════════════════════════════════════════
# INCIDENTS
# ══════════════════════════════════════════════════════════════════════════════

def _inc_scope(user):
    """All incidents in user scope."""
    return Incident.objects.filter(
        chu__in=user.get_scope_chus()
    ).distinct().select_related('category', 'chu__ward__subcounty__county', 'raised_by', 'assigned_to')

@login_required
def incident_list(request):
    qs = _inc_scope(request.user)
    scope_chus = request.user.get_scope_chus()
    role = request.user.role

    status_f = request.GET.get('status', '')
    priority_f = request.GET.get('priority', '')
    cat_f = request.GET.get('category', '')
    search = request.GET.get('q', '')
    county_f = request.GET.get('county', '')
    subcounty_f = request.GET.get('subcounty', '')
    ward_f = request.GET.get('ward', '')
    chu_f = request.GET.get('chu', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    period_f = request.GET.get('period', '')

    if status_f: qs = qs.filter(status=status_f)
    if priority_f: qs = qs.filter(priority=priority_f)
    if cat_f: qs = qs.filter(category_id=cat_f)
    if search: qs = qs.filter(Q(title__icontains=search) | Q(incident_number__icontains=search) | Q(description__icontains=search))
    if county_f: qs = qs.filter(chu__ward__subcounty__county_id=county_f)
    if subcounty_f: qs = qs.filter(chu__ward__subcounty_id=subcounty_f)
    if ward_f: qs = qs.filter(chu__ward_id=ward_f)
    if chu_f: qs = qs.filter(chu_id=chu_f)

    # Period quick filters
    from django.utils import timezone
    today = timezone.now().date()
    if period_f == 'today':
        qs = qs.filter(created_at__date=today)
    elif period_f == 'week':
        week_start = today - timezone.timedelta(days=today.weekday())
        qs = qs.filter(created_at__date__gte=week_start)
    elif period_f == 'month':
        qs = qs.filter(created_at__year=today.year, created_at__month=today.month)
    elif period_f == 'last_month':
        last = today.replace(day=1) - timezone.timedelta(days=1)
        qs = qs.filter(created_at__year=last.year, created_at__month=last.month)

    # Custom date range
    if date_from: qs = qs.filter(created_at__date__gte=date_from)
    if date_to: qs = qs.filter(created_at__date__lte=date_to)

    # Counts reflect current filters
    counts = {s: qs.filter(status=s).count() for s in ['open', 'in_progress', 'escalated', 'resolved', 'closed']}

    # Also include incidents assigned to me outside scope
    assigned_to_me = Incident.objects.filter(
        assigned_to=request.user
    ).exclude(chu__in=scope_chus).select_related('category', 'chu__ward__subcounty__county', 'raised_by', 'assigned_to')

    all_incidents = list(qs.order_by('-created_at')) + list(assigned_to_me.order_by('-created_at'))

    # Geography filter dropdowns — cascade based on what's selected
    if role in ('superuser', 'tech_team'):
        filter_counties = County.objects.all()
        filter_subcounties = SubCounty.objects.filter(county_id=county_f) if county_f else SubCounty.objects.none()
        filter_wards = Ward.objects.filter(subcounty_id=subcounty_f) if subcounty_f else Ward.objects.none()
        filter_chus = (CHU.objects.filter(ward_id=ward_f) if ward_f else
                      CHU.objects.filter(ward__subcounty_id=subcounty_f) if subcounty_f else
                      CHU.objects.filter(ward__subcounty__county_id=county_f) if county_f else
                      CHU.objects.none())
    elif role == 'country':
        filter_counties = County.objects.filter(country=request.user.country)
        filter_subcounties = SubCounty.objects.filter(county_id=county_f) if county_f else SubCounty.objects.filter(county__country=request.user.country)
        filter_wards = Ward.objects.filter(subcounty_id=subcounty_f) if subcounty_f else Ward.objects.none()
        filter_chus = (CHU.objects.filter(ward_id=ward_f) if ward_f else
                      CHU.objects.filter(ward__subcounty_id=subcounty_f) if subcounty_f else
                      CHU.objects.filter(ward__subcounty__county_id=county_f) if county_f else
                      CHU.objects.none())
    elif role == 'county':
        filter_counties = County.objects.filter(pk=request.user.county_id)
        filter_subcounties = SubCounty.objects.filter(county=request.user.county)
        filter_wards = Ward.objects.filter(subcounty_id=subcounty_f) if subcounty_f else Ward.objects.none()
        filter_chus = (CHU.objects.filter(ward_id=ward_f) if ward_f else
                      CHU.objects.filter(ward__subcounty_id=subcounty_f) if subcounty_f else
                      scope_chus)
    elif role == 'subcounty':
        filter_counties = County.objects.none()
        filter_subcounties = SubCounty.objects.filter(pk=request.user.subcounty_id)
        filter_wards = Ward.objects.filter(subcounty=request.user.subcounty)
        filter_chus = CHU.objects.filter(ward_id=ward_f) if ward_f else scope_chus
    else:
        filter_counties = County.objects.none()
        filter_subcounties = SubCounty.objects.none()
        filter_wards = Ward.objects.none()
        filter_chus = scope_chus

    return render(request, 'incidents/incident_list.html', {
        'incidents': all_incidents, 'counts': counts,
        'categories': IncidentCategory.objects.filter(is_active=True),
        'status_f': status_f, 'priority_f': priority_f, 'cat_f': cat_f, 'search': search,
        'county_f': county_f, 'subcounty_f': subcounty_f, 'ward_f': ward_f, 'chu_f': chu_f,
        'date_from': date_from, 'date_to': date_to, 'period_f': period_f,
        'filter_counties': filter_counties,
        'filter_subcounties': filter_subcounties,
        'filter_wards': filter_wards,
        'filter_chus': filter_chus,
        'show_county_filter': role in ('superuser', 'tech_team', 'country'),
        'show_subcounty_filter': role in ('superuser', 'tech_team', 'country', 'county'),
        'show_ward_filter': role in ('subcounty', 'county', 'superuser', 'tech_team', 'country'),
        'show_chu_filter': True,
    })

@login_required
def incident_create(request):
    scope_chus = request.user.get_scope_chus()
    role = request.user.role

    show_county = role in ('superuser', 'tech_team', 'country')
    show_subcounty = role in ('superuser', 'tech_team', 'country', 'county')
    show_chu_direct = role in ('subcounty', 'cha')

    if role in ('superuser', 'tech_team'):
        counties = County.objects.all().select_related('country')
        subcounties = SubCounty.objects.none()
        chus = CHU.objects.none()
    elif role == 'country':
        counties = County.objects.filter(country=request.user.country)
        subcounties = SubCounty.objects.filter(county__country=request.user.country).select_related('county')
        chus = scope_chus
    elif role == 'county':
        counties = County.objects.filter(pk=request.user.county_id)
        subcounties = SubCounty.objects.filter(county=request.user.county).select_related('county')
        chus = scope_chus
    else:
        counties = County.objects.none()
        subcounties = SubCounty.objects.none()
        chus = scope_chus

    if request.method == 'POST':
        chu_id = request.POST.get('chu') or None
        chu = CHU.objects.filter(pk=chu_id).first() if chu_id else None
        inc = Incident(
            title=request.POST.get('title', '').strip(),
            description=request.POST.get('description', '').strip(),
            category_id=request.POST.get('category') or None,
            chu=chu,
            priority=request.POST.get('priority', 'medium'),
            raised_by=request.user, status='open',
        )
        if request.FILES.get('attachment'): inc.attachment = request.FILES['attachment']
        inc.assigned_to = request.user
        inc.save()
        log_action(request, 'CREATE', 'Incident', inc.pk)
        messages.success(request, f"Incident {inc.incident_number} raised.")
        return redirect('incident_detail', pk=inc.pk)

    return render(request, 'incidents/incident_form.html', {
        'title': 'Raise Incident',
        'chus': chus,
        'counties': counties,
        'subcounties': subcounties,
        'show_county': show_county,
        'show_subcounty': show_subcounty,
        'show_chu_direct': show_chu_direct,
        'selected_subcounty': '',
        'categories': IncidentCategory.objects.filter(is_active=True),
        'priorities': Incident.PRIORITY,
    })

@login_required
def incident_detail(request, pk):
    inc = get_object_or_404(Incident, pk=pk)
    if not request.user.get_scope_chus().filter(pk=inc.chu_id).exists() and inc.assigned_to != request.user:
        messages.error(request, "Access denied."); return redirect('incident_list')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'comment':
            comment = request.POST.get('comment', '').strip()
            if comment:
                IncidentUpdate.objects.create(incident=inc, author=request.user, comment=comment)
                messages.success(request, "Comment added.")
                if inc.raised_by and inc.raised_by != request.user:
                    notify(inc.raised_by, f"{request.user.get_full_name()} commented on {inc.incident_number}", 'incident', inc.pk)
                if inc.assigned_to and inc.assigned_to != request.user:
                    notify(inc.assigned_to, f"{request.user.get_full_name()} commented on {inc.incident_number}", 'incident', inc.pk)
        elif action == 'update_status':
            new_status = request.POST.get('status')
            if new_status and new_status != inc.status:
                IncidentUpdate.objects.create(
                    incident=inc, author=request.user,
                    comment=f"Status changed from {inc.get_status_display()} to {dict(Incident.STATUS)[new_status]}",
                    old_status=inc.status, new_status=new_status,
                )
                inc.status = new_status; inc.save()
                if inc.raised_by and inc.raised_by != request.user:
                    notify(inc.raised_by, f"{inc.incident_number} status updated to {new_status}", 'incident', inc.pk)
                if inc.assigned_to and inc.assigned_to != request.user:
                    notify(inc.assigned_to, f"{inc.incident_number} status updated to {new_status}", 'incident', inc.pk)
                messages.success(request, "Status updated.")
        elif action == 'assign':
            assignee_id = request.POST.get('assigned_to')
            if assignee_id:
                assignee = User.objects.filter(pk=assignee_id).first()
                if assignee:
                    inc.assigned_to = assignee; inc.save()
                    notify(assignee, f"{inc.incident_number} assigned to you", 'incident', inc.pk)
                    if inc.raised_by and inc.raised_by != assignee:
                        notify(inc.raised_by, f"{inc.incident_number} has been reassigned to {assignee.get_full_name()}", 'incident', inc.pk)
                    messages.success(request, f"Assigned to {assignee.get_full_name()}.")
        return redirect('incident_detail', pk=pk)

    assignable = User.objects.filter(
        role__in=['superuser', 'tech_team', 'country', 'county', 'subcounty']
    ).order_by('first_name')
    return render(request, 'incidents/incident_detail.html', {
        'incident': inc, 'assignable_users': assignable, 'status_choices': Incident.STATUS,
    })

@login_required
def incident_edit(request, pk):
    inc = get_object_or_404(Incident, pk=pk)
    if not request.user.get_scope_chus().filter(pk=inc.chu_id).exists() and inc.assigned_to != request.user:
        messages.error(request, "Access denied."); return redirect('incident_list')
    if request.method == 'POST':
        inc.title = request.POST.get('title', inc.title)
        inc.description = request.POST.get('description', inc.description)
        inc.priority = request.POST.get('priority', inc.priority)
        inc.category_id = request.POST.get('category') or None
        chu_id = request.POST.get('chu')
        if chu_id: inc.chu_id = chu_id
        if request.FILES.get('attachment'): inc.attachment = request.FILES['attachment']
        inc.save()
        log_action(request, 'UPDATE', 'Incident', inc.pk)
        messages.success(request, "Incident updated.")
        return redirect('incident_detail', pk=pk)

    scope_chus = request.user.get_scope_chus()
    role = request.user.role

    show_county = role in ('superuser', 'tech_team')
    show_subcounty = role in ('superuser', 'tech_team', 'country')
    show_chu_direct = role in ('subcounty', 'cha')

    if role in ('superuser', 'tech_team'):
        counties = County.objects.all().select_related('country')
        subcounties = SubCounty.objects.none()
    elif role == 'country':
        counties = County.objects.filter(country=request.user.country)
        subcounties = SubCounty.objects.none()
    elif role == 'county':
        counties = County.objects.filter(pk=request.user.county_id)
        subcounties = SubCounty.objects.filter(county=request.user.county).select_related('county')
    else:
        counties = County.objects.none()
        subcounties = SubCounty.objects.none()

    chus = scope_chus if show_chu_direct else CHU.objects.filter(pk=inc.chu_id)

    return render(request, 'incidents/incident_form.html', {
        'title': 'Edit Incident', 'obj': inc,
        'chus': chus,
        'counties': counties,
        'subcounties': subcounties,
        'show_county': show_county,
        'show_subcounty': show_subcounty,
        'show_chu_direct': show_chu_direct,
        'selected_subcounty': str(inc.chu.ward.subcounty_id) if inc.chu else '',
        'categories': IncidentCategory.objects.filter(is_active=True),
        'priorities': Incident.PRIORITY,
    })


@login_required
def incident_analytics(request):
    if request.user.role == 'cha':
        messages.error(request, "Access denied."); return redirect('incident_list')
    scope = _inc_scope(request.user)
    status_map = dict(Incident.STATUS)
    priority_map = dict(Incident.PRIORITY)
    return render(request, 'incidents/dashboard.html', {
        'by_status': [{'status': s, 'label': status_map.get(s, s), 'count': c} for s, c in scope.values_list('status').annotate(count=Count('id'))],
        'by_category': list(scope.values('category__name').annotate(count=Count('id')).order_by('-count')[:10]),
        'by_priority': [{'priority': p, 'label': priority_map.get(p, p), 'count': c} for p, c in scope.values_list('priority').annotate(count=Count('id'))],
        'by_cha': list(scope.values('raised_by__first_name', 'raised_by__last_name').annotate(count=Count('id')).order_by('-count')[:10]),
        'total': scope.count(),
    })


@login_required
def category_list(request):
    if not request.user.is_superuser_or_tech:
        messages.error(request, "Access denied."); return redirect('incident_list')
    return render(request, 'incidents/category_list.html', {'categories': IncidentCategory.objects.all()})


@login_required
def category_create(request):
    if not request.user.is_superuser_or_tech:
        messages.error(request, "Access denied."); return redirect('incident_list')
    if request.method == 'POST':
        IncidentCategory.objects.create(
            name=request.POST.get('name', '').strip(),
            description=request.POST.get('description', '').strip(),
            is_active='is_active' in request.POST, created_by=request.user,
        )
        messages.success(request, "Category created.")
        return redirect('category_list')
    return render(request, 'incidents/category_form.html', {'title': 'Add Category'})


@login_required
def bulk_upload_incidents(request):
    if not request.user.can_bulk_upload:
        messages.error(request, "Access denied."); return redirect('incident_list')
    if request.method == 'POST':
        f = request.FILES.get('csv_file')
        if not f:
            messages.error(request, "No file.")
            return render(request, 'incidents/bulk_upload.html', {'type': 'Incidents'})
        reader = csv.DictReader(io.StringIO(f.read().decode('utf-8')))
        created, errors = 0, []
        for i, row in enumerate(reader, 2):
            try:
                chu = CHU.objects.filter(name__iexact=row.get('chu', '').strip()).first()
                cat = IncidentCategory.objects.filter(name__iexact=row.get('category', '').strip()).first()
                Incident.objects.create(
                    title=row.get('title', '').strip(), description=row.get('description', '').strip(),
                    category=cat, chu=chu, priority=row.get('priority', 'medium').strip(),
                    raised_by=request.user, status='open',
                )
                created += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")
        messages.success(request, f"{created} incidents imported." + (f" Errors: {'; '.join(errors[:5])}" if errors else ""))
        return redirect('incident_list')
    return render(request, 'incidents/bulk_upload.html', {'type': 'Incidents'})


@login_required
def download_incident_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="incidents_template.csv"'
    w = csv.writer(response)
    w.writerow(['title', 'description', 'category', 'chu', 'priority'])
    w.writerow(['App logout issue', 'eCHIS keeps logging out', 'App Error', 'Dago', 'high'])
    return response


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def notification_list(request):
    notifs = Notification.objects.filter(user=request.user)
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'notifications/list.html', {'notifications': notifs})

@login_required
def push_subscribe(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        endpoint = data.get('endpoint', '')
        p256dh = data.get('keys', {}).get('p256dh', '')
        auth = data.get('keys', {}).get('auth', '')
        if endpoint and p256dh and auth:
            PushSubscription.objects.update_or_create(
                endpoint=endpoint,
                defaults={'user': request.user, 'p256dh': p256dh, 'auth': auth}
            )
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('notification_list')


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def audit_log(request):
    if request.user.role != 'superuser':
        messages.error(request, "Access denied."); return redirect('dashboard')
    return render(request, 'audit/log.html', {'logs': AuditLog.objects.select_related('user')[:500]})


# ══════════════════════════════════════════════════════════════════════════════
# GEOGRAPHY AJAX
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def ajax_counties(request):
    country_id = request.GET.get('country_id')
    qs = County.objects.filter(country_id=country_id) if country_id else County.objects.all()
    return JsonResponse(list(qs.values('id', 'name')), safe=False)

@login_required
def ajax_subcounties(request):
    county_id = request.GET.get('county_id')
    qs = SubCounty.objects.filter(county_id=county_id) if county_id else SubCounty.objects.all()
    return JsonResponse(list(qs.values('id', 'name')), safe=False)

@login_required
def ajax_wards(request):
    subcounty_id = request.GET.get('subcounty_id')
    qs = Ward.objects.filter(subcounty_id=subcounty_id) if subcounty_id else Ward.objects.all()
    return JsonResponse(list(qs.values('id', 'name')), safe=False)

@login_required
def ajax_chus(request):
    ward_id = request.GET.get('ward_id')
    qs = CHU.objects.filter(ward_id=ward_id) if ward_id else CHU.objects.all()
    return JsonResponse(list(qs.values('id', 'name')), safe=False)

@login_required
def ajax_chus_by_subcounty(request):
    subcounty_id = request.GET.get('subcounty_id')
    if not subcounty_id:
        return JsonResponse([], safe=False)
    scope_chus = request.user.get_scope_chus()
    qs = scope_chus.filter(ward__subcounty_id=subcounty_id).order_by('name')
    return JsonResponse(list(qs.values('id', 'name')), safe=False)

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN TOOLS — GEOGRAPHY UPLOAD
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def upload_geography(request):
    if not request.user.is_superuser_or_tech:
        messages.error(request, "Access denied."); return redirect('dashboard')

    results = None
    if request.method == 'POST':
        f = request.FILES.get('csv_file')
        if not f:
            messages.error(request, "No file uploaded.")
            return render(request, 'admin_tools/upload_geography.html')

        reader = csv.DictReader(io.StringIO(f.read().decode('utf-8')))
        created = {'county': 0, 'subcounty': 0, 'ward': 0, 'chu': 0}
        updated = {'county': 0, 'subcounty': 0, 'ward': 0, 'chu': 0}
        errors = []

        country, _ = Country.objects.get_or_create(name='Kenya', defaults={'code': 'KE'})

        for i, row in enumerate(reader, 2):
            try:
                county_name = row.get('county', '').strip()
                subcounty_name = row.get('subcounty', '').strip()
                ward_name = row.get('ward', '').strip()
                chu_name = row.get('chu_name', '').strip()
                chu_code = row.get('chu_code', '').strip()

                if not all([county_name, subcounty_name, ward_name, chu_name]):
                    errors.append(f"Row {i}: Missing required fields (county, subcounty, ward, chu_name)")
                    continue

                county, c = County.objects.get_or_create(
                    name__iexact=county_name, country=country,
                    defaults={'name': county_name}
                )
                if c: created['county'] += 1

                subcounty, c = SubCounty.objects.get_or_create(
                    name__iexact=subcounty_name, county=county,
                    defaults={'name': subcounty_name}
                )
                if c: created['subcounty'] += 1

                ward, c = Ward.objects.get_or_create(
                    name__iexact=ward_name, subcounty=subcounty,
                    defaults={'name': ward_name}
                )
                if c: created['ward'] += 1

                chu, c = CHU.objects.get_or_create(
                    name__iexact=chu_name, ward=ward,
                    defaults={'name': chu_name, 'code': chu_code}
                )
                if c:
                    created['chu'] += 1
                else:
                    if chu_code and not chu.code:
                        chu.code = chu_code
                        chu.save()
                    updated['chu'] += 1

            except Exception as e:
                errors.append(f"Row {i}: {e}")

        log_action(request, 'BULK_UPLOAD', 'Geography')
        results = {'created': created, 'updated': updated, 'errors': errors}

    return render(request, 'admin_tools/upload_geography.html', {'results': results})


@login_required
def download_geography_template(request):
    if not request.user.is_superuser_or_tech:
        messages.error(request, "Access denied."); return redirect('dashboard')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="geography_template.csv"'
    w = csv.writer(response)
    w.writerow(['county', 'subcounty', 'ward', 'chu_name'])
    w.writerow(['Kisumu', 'Kisumu West', 'Manyatta B', 'Manyatta B CHU'])
    w.writerow(['Kisumu', 'Kisumu West', 'Manyatta B', 'Kolwa CHU'])
    w.writerow(['Kisumu', 'Seme', 'West Seme', 'West Seme CHU A'])
    w.writerow(['Busia', 'Butula', 'Butula', 'Butula CHU'])
    return response

# ══════════════════════════════════════════════════════════════════════════════
# CSV EXPORTS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def export_devices(request):
    scope_chus = request.user.get_scope_chus()
    devices = Device.objects.filter(chu__in=scope_chus).select_related(
        'chu__ward__subcounty__county'
    ).order_by('chu__ward__subcounty__county__name', 'chu__name', 'assigned_to_name')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="devices_export.csv"'
    w = csv.writer(response)
    w.writerow(['county', 'subcounty', 'ward', 'chu', 'assigned_to_name', 'assigned_to_role',
                'device_type', 'phone_model', 'serial_number', 'imei', 'status',
                'incident_date', 'reporting_status', 'date_assigned', 'notes'])
    for d in devices:
        w.writerow([
            d.chu.ward.subcounty.county.name,
            d.chu.ward.subcounty.name,
            d.chu.ward.name,
            d.chu.name,
            d.assigned_to_name,
            d.get_assigned_to_role_display(),
            d.get_device_type_display(),
            d.phone_model,
            d.serial_number,
            d.imei,
            d.get_status_display(),
            d.incident_date or '',
            d.get_reporting_status_display(),
            d.date_assigned or '',
            d.notes,
        ])
    return response


@login_required
def export_chps(request):
    scope_chus = request.user.get_scope_chus()
    chps = CHPProfile.objects.filter(chu__in=scope_chus).select_related(
        'chu__ward__subcounty__county'
    ).order_by('chu__ward__subcounty__county__name', 'chu__name', 'name')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="chp_credentials_export.csv"'
    w = csv.writer(response)
    w.writerow(['county', 'subcounty', 'ward', 'chu', 'chp_name',
                'echis_username', 'echis_password', 'is_active'])
    for chp in chps:
        w.writerow([
            chp.chu.ward.subcounty.county.name,
            chp.chu.ward.subcounty.name,
            chp.chu.ward.name,
            chp.chu.name,
            chp.name,
            chp.echis_username,
            chp.echis_password,
            'Yes' if chp.is_active else 'No',
        ])
    return response


@login_required
def export_chas(request):
    scope_chus = request.user.get_scope_chus()
    subcounties = SubCounty.objects.filter(wards__chus__in=scope_chus).distinct()
    chas = CHAProfile.objects.filter(subcounty__in=subcounties).select_related(
        'subcounty__county'
    ).prefetch_related('chus').order_by('subcounty__county__name', 'subcounty__name', 'name')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="cha_credentials_export.csv"'
    w = csv.writer(response)
    w.writerow(['county', 'subcounty', 'cha_name', 'assigned_chus',
                'echis_username', 'echis_password',
                'dashboard_username', 'dashboard_password',
                'registry_username', 'registry_password', 'is_active'])
    for cha in chas:
        w.writerow([
            cha.subcounty.county.name,
            cha.subcounty.name,
            cha.name,
            cha.chu_list,
            cha.echis_username,
            cha.echis_password,
            cha.dashboard_username,
            cha.dashboard_password,
            cha.registry_username,
            cha.registry_password,
            'Yes' if cha.is_active else 'No',
        ])
    return response


@login_required
def export_incidents(request):
    incidents = _inc_scope(request.user).order_by('-created_at')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="incidents_export.csv"'
    w = csv.writer(response)
    w.writerow(['incident_number', 'title', 'category', 'chu', 'ward', 'subcounty', 'county',
                'priority', 'status', 'raised_by', 'assigned_to', 'created_at', 'description'])
    for inc in incidents:
        w.writerow([
            inc.incident_number,
            inc.title,
            inc.category.name if inc.category else '',
            inc.chu.name if inc.chu else '',
            inc.chu.ward.name if inc.chu else '',
            inc.chu.ward.subcounty.name if inc.chu else '',
            inc.chu.ward.subcounty.county.name if inc.chu else '',
            inc.get_priority_display(),
            inc.get_status_display(),
            inc.raised_by.get_full_name() if inc.raised_by else '',
            inc.assigned_to.get_full_name() if inc.assigned_to else '',
            inc.created_at.strftime('%Y-%m-%d %H:%M'),
            inc.description,
        ])
    return response