import calendar
import datetime
import io
import json
import mimetypes
from datetime import date
from io import BytesIO

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, Sum
from django.forms import BaseFormSet, formset_factory
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localtime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from adminhub.models import Announcement, AnnouncementViewLog, AttendanceFeatureSetting, DocumentTemplate
from adminhub.tasks import publish_due_scheduled_announcements_task
from base.decorators import faculty_required
from base.forms import (
    FacultyDeliverableUploadForm,
    FacultyDocumentUploadForm,
    ManualAttendanceLogForm,
    FacultyPublicSignupForm,
    IndexedFormSet as BaseIndexedFormSet,
    TwoFactorToggleForm,
)
from base.utils.dtr_workinghours import calculate_total_working_hours
from base.utils.faculty_data import get_faculty_data
from faculty.models import (
    Deliverable,
    DocumentCategory,
    FacultyClearanceRequest,
    FacultyDocument,
    FacultyProfile,
    FacultyRequest,
    Semester,
    TeachingAssignment,
)
from notifications.services import ROLE_ADMIN_GROUP, log_activity, notify_role
from rfid.models import AttendanceLog
from rfid.views import format_log
from services.dtr_service import DTRCalculator
from services.faculty_clearance_service import (
    build_clearance_number,
    build_clearance_pdf_response,
    evaluate_faculty_clearance_eligibility,
)
from services.google_drive_service import CentralGoogleDriveService

# Create your views here.


@never_cache
def faculty_signup_view(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('adminhub:home')
        if request.user.role == 'faculty':
            return redirect('faculty:home')

    if request.method == 'POST':
        form = FacultyPublicSignupForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            User = get_user_model()

            try:
                with transaction.atomic():
                    account = User.objects.create_user(
                        email=data['email'],
                        password=data['password'],
                        role='faculty',
                        is_active=False,
                    )

                    faculty_profile = FacultyProfile.objects.create(
                        account=account,
                        first_name=data.get('first_name'),
                        middle_name=data.get('middle_name'),
                        last_name=data.get('last_name'),
                        suffix=data.get('suffix'),
                        faculty_code=data.get('faculty_code'),
                        status=data.get('status'),
                        birth_date=data.get('birth_date'),
                        contact_number=data.get('contact_number'),
                    )

                try:
                    notify_role(
                        roles=ROLE_ADMIN_GROUP,
                        actor=account,
                        notification_type='faculty_approval_request',
                        title='New faculty account approval request',
                        message=f"{faculty_profile.name or account.email} submitted a faculty signup request.",
                        url=reverse('adminhub:faculty_pending_approvals'),
                        related_type='FacultyProfile',
                        related_id=str(faculty_profile.uuid),
                        aggregate_key=f"faculty_signup_pending:{account.id}",
                    )
                    log_activity(
                        actor=account,
                        action='faculty_signup_submitted',
                        target_type='FacultyProfile',
                        target_id=str(faculty_profile.uuid),
                        details={
                            'target_name': faculty_profile.name or account.email,
                            'email': account.email,
                        },
                    )
                except Exception:
                    pass

                messages.success(
                    request,
                    'Your registration was submitted. Please wait for admin approval before logging in.',
                    extra_tags='login',
                )
                return redirect('login')
            except Exception:
                messages.error(
                    request,
                    'Unable to submit your registration right now. Please try again later.',
                )
    else:
        form = FacultyPublicSignupForm()

    return render(request, 'faculty/faculty_signup.html', {'form': form})


@faculty_required
def home(request):
    data = get_faculty_data(request)
    faculty = request.user.faculty_profile
    today = timezone.localdate()

    pending_documents = FacultyDocument.objects.filter(
        faculty=faculty,
        status="Pending",
        is_archived=False,
    ).count()

    pending_requests = FacultyRequest.objects.filter(
        faculty=faculty,
        status__in=["Pending", "Open"] 
    ).count()

    semester = Semester.objects.filter(
        is_active=True,
        start_date__lte=today,
        end_date__gte=today
    ).first()

    pending_deliverables = 0
    if semester:
        deliverables = Deliverable.objects.filter(
            semester=semester
        )
        deliverable_ids = list(deliverables.values_list('id', flat=True))
        deliverable_count = len(deliverable_ids)

        ta_count = TeachingAssignment.objects.filter(
            faculty=faculty,
            semester=semester,
        ).count()

        total_required = deliverable_count * ta_count

        if total_required > 0:
            approved_count = FacultyDocument.objects.filter(
                faculty=faculty,
                semester=semester,
                deliverable_id__in=deliverable_ids,
                status="Approved",
                is_archived=False,
            ).count()
        else:
            approved_count = 0

        pending_deliverables = max(total_required - approved_count, 0)

    try:
        publish_due_scheduled_announcements_task.delay(limit=20)
    except Exception:
        pass

    recent_announcements = Announcement.objects.filter(
        visible_to_roles__contains=[request.user.role],
        is_active=True,
        start_date__lte=today,
    ).filter(
        Q(end_date__gte=today) | Q(end_date__isnull=True)
    ).filter(
        Q(scheduled_publish_at__isnull=True) | Q(published_at__isnull=False)
    ).order_by('-created_at')[:3]

    faculty_profile = faculty

    teaching_assignments_qs = TeachingAssignment.objects.filter(
        faculty=faculty
    )
    if semester:
        teaching_assignments_qs = teaching_assignments_qs.filter(semester=semester)

    teaching_assignments = teaching_assignments_qs.order_by(
        'day_of_week',
        'start_time'
    )

    DAYS_ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat']
    schedule_by_day = {d: [] for d in DAYS_ORDER}
    for ta in teaching_assignments:
        if ta.day_of_week in schedule_by_day:
            schedule_by_day[ta.day_of_week].append(ta)

    DAYS_META = [
        ('mon', 'Monday'),
        ('tue', 'Tuesday'),
        ('wed', 'Wednesday'),
        ('thu', 'Thursday'),
        ('fri', 'Friday'),
        ('sat', 'Saturday'),
    ]
    weekly_schedule = [
        {
            'code': code,
            'label': label,
            'assignments': schedule_by_day.get(code, []),
        }
        for code, label in DAYS_META
    ]

    data.update({
        'pending_documents': pending_documents,
        'pending_requests': pending_requests,
        'pending_deliverables': pending_deliverables,
        'recent_announcements': recent_announcements,

        'faculty_profile': faculty_profile,
        'teaching_assignments': teaching_assignments,
        'weekly_schedule': weekly_schedule,
        'active_semester': semester,
    })

    return render(request, 'faculty/faculty_home.html', data)

@faculty_required
def faculty_settings_view(request):
    return render(request, 'faculty/faculty_settings.html')


@faculty_required
def faculty_2fa(request):
    user = request.user

    if request.method == 'POST':
        form = TwoFactorToggleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "2FA setting updated.", extra_tags="2fa")
            return redirect("faculty:faculty_2fa")
    else:
        form = TwoFactorToggleForm(instance=user)

    return render(request, "faculty/faculty_2fa.html", {"form": form})



@faculty_required
def faculty_documents_view(request):
    faculty_profile = request.user.faculty_profile
    documents = (
        faculty_profile.documents
        .filter(is_archived=False)
        .filter(FacultyDocument.documents_tab_filter())
        .order_by("-uploaded_at")
    )

    total_documents = documents.count()
    pending_documents = documents.filter(status="Pending").count()
    total_storage_bytes = documents.aggregate(total=Sum("file_size"))["total"] or 0

    def filesizeformat(num):
        for unit in ['bytes','KB','MB','GB','TB']:
            if num < 1024.0:
                return "%3.1f %s" % (num, unit)
            num /= 1024.0
        return "%3.1f %s" % (num, 'PB')

    context = {
        "faculty_profile": faculty_profile,
        "documents": documents,
        "total_documents": total_documents,
        "pending_documents": pending_documents,
        "total_storage": filesizeformat(total_storage_bytes),
    }
    return render(request, "faculty/faculty_documents.html", context)


def _stream_drive_media(drive_service: CentralGoogleDriveService, file_id: str, chunk_size: int = 1024 * 256):
    request = drive_service.service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request, chunksize=chunk_size)
    done = False
    last_pos = 0
    while not done:
        status, done = downloader.next_chunk()
        data = fh.getvalue()[last_pos:]
        if data:
            yield data
            last_pos = len(fh.getvalue())
    remaining = fh.getvalue()[last_pos:]
    if remaining:
        yield remaining


def _finalize_response(resp: HttpResponse):
    resp['X-Frame-Options'] = 'SAMEORIGIN'
    resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


def download_document(request, uid):
    """
    Streams or returns bytes for a document stored on Google Drive.
    Uses uid (UUID) to lookup document.
    Query param inline=1 requests inline preview (only honored for PDF/images).
    """
    doc = get_object_or_404(FacultyDocument, uid=uid)
    file_id = doc.google_drive_id

    drive = CentralGoogleDriveService()
    want_inline = request.GET.get('inline', '0').lower() in ('1', 'true', 'yes')

    try:
        meta = drive.service.files().get(fileId=file_id, fields='mimeType, name, size').execute()
        mime_type = meta.get('mimeType')
        name_on_drive = meta.get('name') or doc.document_name or f'document_{doc.id}'
    except Exception:
        raise Http404("Could not retrieve file metadata from Google Drive.")

    if mime_type and mime_type.startswith('application/vnd.google-apps.'):
        export_mime = 'application/pdf'
        try:
            exported_bytes = drive.service.files().export(fileId=file_id, mimeType=export_mime).execute()
        except Exception:
            raise Http404("File could not be exported from Google Drive.")

        content_type = export_mime
        disposition = 'inline' if (want_inline and content_type == 'application/pdf') else 'attachment'
        resp = HttpResponse(exported_bytes, content_type=content_type)
        resp['Content-Disposition'] = f'{disposition}; filename="{name_on_drive}"'
        resp['Content-Length'] = str(len(exported_bytes))
        return _finalize_response(resp)

    content_type = mime_type or mimetypes.guess_type(name_on_drive)[0] or 'application/octet-stream'
    inline_allowed = (content_type == 'application/pdf') or content_type.startswith('image/')

    if want_inline and inline_allowed:
        response = StreamingHttpResponse(_stream_drive_media(drive, file_id), content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{name_on_drive}"'
        return _finalize_response(response)

    response = StreamingHttpResponse(_stream_drive_media(drive, file_id), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{name_on_drive}"'
    return _finalize_response(response)


class IndexedFormSet(BaseFormSet):
    """
    Same pattern as your deliverables IndexedFormSet: inject index so each
    form can have unique file input ids.
    """
    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.index = index

    def _construct_form(self, i, **kwargs):
        kwargs['index'] = i
        return super()._construct_form(i, **kwargs)


@faculty_required
def faculty_document_upload(request):
    data = get_faculty_data(request)

    account = request.user
    faculty = getattr(account, "faculty_profile", None)
    if not faculty:
        messages.error(request, "Only faculty can upload documents.")
        return redirect('faculty:home')

    DocumentFormSet = formset_factory(
        FacultyDocumentUploadForm,
        formset=IndexedFormSet,
        extra=1,
        max_num=10,
        validate_max=True,
    )

    form_kwargs = {
        "faculty": faculty,
    }

    if request.method == 'POST':
        formset = DocumentFormSet(
            request.POST,
            request.FILES,
            form_kwargs=form_kwargs,
        )

        if formset.is_valid():
            non_empty_count = 0
            for form in formset:
                cd = form.cleaned_data
                category = cd.get("document_category")
                name = cd.get("document_name")
                file = cd.get("file")
                expiry = cd.get("expiry_date")

                if category or name or file or expiry:
                    non_empty_count += 1

            if non_empty_count == 0:
                formset._non_form_errors = formset.error_class(
                    ["Please fill out at least one document card before submitting."]
                )
                messages.error(
                    request, "Please fill out at least one document card before submitting."
                )
                data["formset"] = formset
                return render(request, "faculty/faculty_document_upload.html", data)

            service = CentralGoogleDriveService()
            success_count = 0

            for form in formset:
                cd = form.cleaned_data
                category = cd.get("document_category")
                name = cd.get("document_name")
                file = cd.get("file")
                expiry = cd.get("expiry_date")

                if not category and not name and not file and not expiry:
                    continue

                try:
                    media = MediaIoBaseUpload(
                        io.BytesIO(file.read()),
                        mimetype=file.content_type,
                        resumable=False,
                    )

                    upload = service.service.files().create(
                        body={
                            "name": file.name,
                            "parents": [faculty.gdrive_folder_id],
                        },
                        media_body=media,
                        fields="id,webViewLink"
                    ).execute()

                    FacultyDocument.objects.create(
                        faculty=faculty,
                        uploaded_by=account,
                        document_name=name,
                        document_category=category,
                        file_path=upload["webViewLink"],
                        google_drive_id=upload["id"],
                        file_size=file.size,
                        expiry_date=expiry,
                        status="Pending",
                    )
                    success_count += 1

                except Exception as e:
                    print("Document upload error:", e)
                    messages.error(request, f"Failed to upload '{name}'.")

            if success_count:
                notify_role(
                    roles=ROLE_ADMIN_GROUP,
                    actor=account,
                    notification_type='faculty_document_uploaded',
                    title='New faculty document upload',
                    message=f"{faculty.name or account.email} uploaded {success_count} document(s) for review.",
                    url=reverse('adminhub:documents'),
                    related_type='FacultyProfile',
                    related_id=str(faculty.uuid),
                    aggregate_key=f"faculty_document_upload:{account.id}",
                )
                log_activity(
                    actor=account,
                    action='faculty_document_uploaded',
                    target_type='FacultyProfile',
                    target_id=str(faculty.uuid),
                    details={
                        'target_name': faculty.name or account.email,
                        'count': success_count,
                    },
                )
                messages.success(
                    request, f"{success_count} document(s) uploaded successfully."
                )
            return redirect("faculty:faculty_documents")

        else:
            messages.error(request, "Please fix the errors in the form before uploading.")
    else:
        formset = DocumentFormSet(form_kwargs=form_kwargs)

    data["formset"] = formset
    return render(request, "faculty/faculty_document_upload.html", data)







@faculty_required
def faculty_attendance_logs_view(request):
    attendance_feature_settings = AttendanceFeatureSetting.get_solo()
    faculty = request.user.faculty_profile
    month = int(request.GET.get('month', timezone.now().month))
    year = int(request.GET.get('year', timezone.now().year))

    logs_qs = AttendanceLog.objects.filter(faculty=faculty).order_by("-date", "-time_in")

    if month:
        logs_qs = logs_qs.filter(date__month=month)
    if year:
        logs_qs = logs_qs.filter(date__year=year)

    paginator = Paginator(logs_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "logs": [format_log(log) for log in page_obj.object_list],
        "selected_month": month,
        "selected_year": year,
        "month_range": [(i, calendar.month_name[i]) for i in range(1, 13)],
        "years": range(2020, timezone.now().year + 2),
        "querystring": querystring,
        "logs_total": logs_qs.count(),
        "enable_faculty_manual_attendance": attendance_feature_settings.enable_faculty_manual_attendance,
    }
    return render(request, "faculty/faculty_attendance_logs.html", context)


@faculty_required
def faculty_manual_attendance_log_view(request):
    attendance_feature_settings = AttendanceFeatureSetting.get_solo()
    if not attendance_feature_settings.enable_faculty_manual_attendance:
        messages.error(request, "Faculty manual attendance is currently disabled by the administrator.")
        return redirect('faculty:faculty_attendance_logs')

    faculty = request.user.faculty_profile
    today = timezone.localdate()
    message = ""
    message_class = ""
    initial = {
        'date': today,
        'time_in': '',
        'time_out': '',
        'selected_assignments': [],
    }

    if request.method == "POST":
        mutable_post = request.POST.copy()
        mutable_post["faculty"] = str(faculty.pk)
        initial.update({
            'date': request.POST.get('date', today),
            'time_in': request.POST.get('time_in', ''),
            'time_out': request.POST.get('time_out', ''),
            'selected_assignments': [str(v) for v in request.POST.getlist('teaching_assignments')],
        })

        form = ManualAttendanceLogForm(mutable_post, faculty=faculty)
        if form.is_valid():
            cleaned = form.cleaned_data
            if cleaned['date'] != today:
                form.add_error('date', "Faculty manual attendance can only be logged for today.")
            else:
                attendance = form.save(commit=False)
                attendance.faculty = faculty
                attendance.time_in = datetime.datetime.combine(cleaned['date'], cleaned['time_in'], tzinfo=timezone.get_current_timezone())
                attendance.time_out = datetime.datetime.combine(cleaned['date'], cleaned['time_out'], tzinfo=timezone.get_current_timezone())
                attendance.uid = request.POST.get('uid', '')
                attendance.is_manual = True
                attendance.save()
                form.save_m2m()
                messages.success(request, "Manual attendance logged successfully.")
                return redirect('faculty:faculty_attendance_logs')

        if form.errors:
            error_msgs = []
            for error in form.non_field_errors():
                error_msgs.append(f"{error}")
            for field in form:
                for error in field.errors:
                    error_msgs.append(f"{field.label}: {error}")
            message = "<br>".join(error_msgs)
            message_class = "bg-red-100 text-red-800"
    else:
        form = ManualAttendanceLogForm(initial={'faculty': faculty.pk, 'date': today}, faculty=faculty)

    active_sem = Semester.objects.filter(is_active=True).first()
    teaching_assignments = []
    assignments_qs = TeachingAssignment.objects.filter(faculty=faculty)
    if active_sem:
        assignments_qs = assignments_qs.filter(semester=active_sem)

    for ta in assignments_qs:
        start_12 = ta.start_time.strftime('%I:%M %p').lstrip('0')
        end_12 = ta.end_time.strftime('%I:%M %p').lstrip('0')
        display = f"{ta.subject_code} ({ta.get_day_of_week_display()} {start_12} - {end_12}"
        if ta.room:
            display += f" - {ta.room}"
        display += ")"
        teaching_assignments.append({
            'id': ta.id,
            'faculty_pk': str(faculty.pk),
            'subject_code': ta.subject_code,
            'subject_description': ta.subject_description,
            'year_section': ta.year_section,
            'start_time': ta.start_time.strftime('%H:%M'),
            'end_time': ta.end_time.strftime('%H:%M'),
            'day_of_week': ta.day_of_week,
            'room': ta.room,
            'display': display,
        })

    return render(request, 'faculty/faculty_manual_attendance_log.html', {
        'today': today,
        'teaching_assignments': teaching_assignments,
        'message': message,
        'message_class': message_class,
        **initial,
    })



@faculty_required
def faculty_teaching_assignment_dtr_view(request):
    faculty = request.user.faculty_profile
    today = date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    day_of_week = request.GET.get('day', '')  

    assignments = (
        TeachingAssignment.objects
        .filter(faculty=faculty)
        .select_related('semester')
        .order_by('semester', 'day_of_week', 'start_time')
    )

    dtr = DTRCalculator.get_dtr_for_month(faculty, year, month)

    days_in_month = calendar.monthrange(year, month)[1]
    logs_by_date = {}
    for day_num in range(1, days_in_month + 1):
        current_date = date(year, month, day_num)
        logs_by_date[current_date] = list(
            AttendanceLog.objects
            .filter(faculty=faculty, date=current_date)
            .order_by('time_in')
        )

    for row in dtr:
        day_logs = logs_by_date.get(row['date'], [])
        assignment_status_logs = set(
            status['attendance_log'].id
            for status in row['statuses']
            if status['attendance_log']
        )
        for log in day_logs:
            if log.id not in assignment_status_logs:
                row['statuses'].append({
                    'assignment': None,
                    'attendance_log': log,
                    'status': 'has log',
                })
        if not row['statuses'] and day_logs:
            for log in day_logs:
                row['statuses'].append({
                    'assignment': None,
                    'attendance_log': log,
                    'status': 'has log',
                })
        elif not row['statuses']:
            row['statuses'].append({
                'assignment': None,
                'attendance_log': None,
                'status': 'no assignment',
            })

    if day_of_week:
        dtr = [
            row for row in dtr
            if row['date'].strftime('%a').lower()[:3] == day_of_week
        ]

    year_choices = [today.year - 1, today.year, today.year + 1]

    months = [(i, calendar.month_name[i]) for i in range(1, 13)]
    day_choices = [
        ('', 'All Days'), ('mon', 'Monday'), ('tue', 'Tuesday'), ('wed', 'Wednesday'),
        ('thu', 'Thursday'), ('fri', 'Friday'), ('sat', 'Saturday')
    ]

    context = {
        'faculty': faculty,
        'assignments': assignments,
        'dtr': dtr,
        'month': month,
        'year': year,
        'year_choices': year_choices,
        'months': months,
        'day_of_week': day_of_week,
        'day_choices': day_choices,
    }
    return render(request, 'faculty/faculty_teaching_assignment_dtr.html', context)











@faculty_required
def faculty_dtr_export_preview(request):
    faculty: FacultyProfile = request.user.faculty_profile
    today = date.today()

    months = [(i, calendar.month_name[i]) for i in range(1, 13)]
    year_choices = [today.year - 1, today.year, today.year + 1]

    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))
    days_in_month = calendar.monthrange(year, month)[1]
    month_label = calendar.month_name[month]

    dtr = DTRCalculator.get_dtr_for_month(faculty, year, month)

    rows = []
    for day_num in range(1, days_in_month + 1):
        am_in = am_out = pm_in = pm_out = ""
        logs = [
            status["attendance_log"]
            for status in dtr[day_num - 1]["statuses"]
            if status["attendance_log"]
        ]
        if logs:
            log = logs[0]
            if log.time_in:
                t_in = localtime(log.time_in)
                if t_in.hour < 12:
                    am_in = t_in.strftime("%I:%M %p").lstrip("0")
                else:
                    pm_in = t_in.strftime("%I:%M %p").lstrip("0")
            if log.time_out:
                t_out = localtime(log.time_out)
                if t_out.hour < 12:
                    am_out = t_out.strftime("%I:%M %p").lstrip("0")
                else:
                    pm_out = t_out.strftime("%I:%M %p").lstrip("0")

        rows.append(
            {
                "day": day_num,
                "am_in": am_in,
                "am_out": am_out,
                "pm_in": pm_in,
                "pm_out": pm_out,
            }
        )

    total_working_hours = calculate_total_working_hours(rows)
    status_label = (
        faculty.status.name.upper()
        if getattr(faculty, "status", None) and getattr(faculty.status, "name", None)
        else "---"
    )

    context = {
        "faculty": faculty,
        "month": month,
        "year": year,
        "month_label": month_label,
        "rows": rows,
        "months": months,
        "year_choices": year_choices,
        "status_label": status_label,
        "total_working_hours": total_working_hours,
    }
    return render(request, "faculty/faculty_dtr_export_preview.html", context)


@faculty_required
def faculty_dtr_export_view(request):
    faculty: FacultyProfile = request.user.faculty_profile
    today = date.today()
    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))
    days_in_month = calendar.monthrange(year, month)[1]
    month_label = calendar.month_name[month]

    dtr = DTRCalculator.get_dtr_for_month(faculty, year, month)

    rows = []
    for day_num in range(1, days_in_month + 1):
        am_in = am_out = pm_in = pm_out = ""
        logs = [
            status["attendance_log"]
            for status in dtr[day_num - 1]["statuses"]
            if status["attendance_log"]
        ]
        if logs:
            log = logs[0]
            if log.time_in:
                t_in = localtime(log.time_in)
                if t_in.hour < 12:
                    am_in = t_in.strftime("%I:%M %p").lstrip("0")
                else:
                    pm_in = t_in.strftime("%I:%M %p").lstrip("0")
            if log.time_out:
                t_out = localtime(log.time_out)
                if t_out.hour < 12:
                    am_out = t_out.strftime("%I:%M %p").lstrip("0")
                else:
                    pm_out = t_out.strftime("%I:%M %p").lstrip("0")

        rows.append([str(day_num), am_in, am_out, pm_in, pm_out])

    rows_dicts = [
        {"am_in": am_in, "am_out": am_out, "pm_in": pm_in, "pm_out": pm_out}
        for (_, am_in, am_out, pm_in, pm_out) in rows
    ]
    total_working_hours = calculate_total_working_hours(rows_dicts)
    status_label = (
        faculty.status.name.upper()
        if getattr(faculty, "status", None) and getattr(faculty.status, "name", None)
        else "---"
    )

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=0.7 * cm,
        rightMargin=0.7 * cm,
        topMargin=0.7 * cm,
        bottomMargin=0.7 * cm,
    )
    width, height = A4
    styles = getSampleStyleSheet()

    cell_style = ParagraphStyle(
        "cell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        alignment=1,
        spaceAfter=0,
        spaceBefore=0,
    )
    head_style = ParagraphStyle(
        "head",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.3,
        alignment=1,
        spaceAfter=0,
        spaceBefore=0,
    )
    document_title_style = ParagraphStyle(
        "documenttitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        alignment=1,
        spaceAfter=0,
        spaceBefore=0,
    )
    bold_style = ParagraphStyle(
        "boldcell",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.7,
        alignment=1,
        spaceAfter=0,
        spaceBefore=0,
    )
    note_style = ParagraphStyle(
        "note",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.3,
        alignment=1,
        textColor=colors.HexColor("#222"),
        leading=8.5,
    )
    sign_style = ParagraphStyle(
        "sign",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        alignment=1,
    )
    small_left = ParagraphStyle(
        "small_left",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=6.8,
        alignment=0,
        textColor=colors.HexColor("#888888"),
    )

    avail_width = width - doc.leftMargin - doc.rightMargin
    w_day = 1.18 * cm
    w_other = (avail_width - w_day) / 4
    col_widths = [w_day, w_other, w_other, w_other, w_other]

    data = [
        [
            Paragraph(
                "Civil Service Form No. 48",
                ParagraphStyle(
                    "left",
                    fontName="Helvetica-Oblique",
                    fontSize=9,
                    alignment=0,
                ),
            ),
            "",
            "",
            "",
            Paragraph(
                status_label,
                ParagraphStyle(
                    "right",
                    fontName="Helvetica-Oblique",
                    fontSize=10,
                    alignment=2,
                ),
            ),
        ],
        [Paragraph("<b>DAILY TIME RECORD</b>", document_title_style), "", "", "", ""],
        [Paragraph(f"<b>{faculty.name.upper()}</b>", head_style), "", "", "", ""],
        [
            Paragraph(
                f"For the month of <b>{month_label.upper()} {year}</b>", cell_style
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph(
                f"Official Hours Of: <b>{total_working_hours}</b>", cell_style
            ),
            "",
            "",
            "",
            "",
        ],
        [
            Paragraph("<b>Day</b>", head_style),
            Paragraph("<b>A.M.</b>", head_style),
            "",
            Paragraph("<b>P.M.</b>", head_style),
            "",
        ],
        [
            "",
            Paragraph("<b>Arrival</b>", head_style),
            Paragraph("<b>Departure</b>", head_style),
            Paragraph("<b>Arrival</b>", head_style),
            Paragraph("<b>Departure</b>", head_style),
        ],
    ]

    # Day rows
    for row in rows:
        data.append(
            [Paragraph(row[0], bold_style)]
            + [Paragraph(cell, cell_style) for cell in row[1:]]
        )

    # Total row
    data.append(
        [
            Paragraph("<b>TOTAL — Working Hours:</b>", bold_style),
            "",
            "",
            "",
            Paragraph(f"<b>{total_working_hours}</b>", bold_style),
        ]
    )

    # Certification/signature/verified
    data.append(
        [
            Paragraph(
                "I certify on my honor that the above is true and correct report of the hours of work performed, record of which was made daily at the time of arrival and departure from office.",
                note_style,
            ),
            "",
            "",
            "",
            "",
        ]
    )
    data.append([Paragraph(f"<b>{faculty.name.upper()}</b>", sign_style), "", "", "", ""])
    data.append(
        [
            Paragraph(
                "VERIFIED as to the prescribed office hours", small_left
            ),
            "",
            "",
            "",
            "",
        ]
    )

    t = Table(data, colWidths=col_widths, repeatRows=0)
    t.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (3, 0)),
                ("SPAN", (4, 0), (4, 0)),
                ("SPAN", (0, 1), (4, 1)),
                ("SPAN", (0, 2), (4, 2)),
                ("SPAN", (0, 3), (4, 3)),
                ("SPAN", (0, 4), (4, 4)),
                ("SPAN", (0, 5), (0, 6)),
                ("SPAN", (1, 5), (2, 5)),
                ("SPAN", (3, 5), (4, 5)),
                ("SPAN", (0, -4), (3, -4)),
                ("SPAN", (0, -3), (4, -3)),
                ("SPAN", (0, -2), (4, -2)),
                ("SPAN", (0, -1), (4, -1)),
                ("GRID", (0, 5), (-1, -5), 0.5, colors.HexColor("#444444")),
                ("BOX", (0, 5), (-1, -5), 1, colors.HexColor("#444444")),
                ("BOX", (0, -4), (-1, -4), 1, colors.HexColor("#444444")),
                ("BACKGROUND", (0, 5), (-1, 6), colors.HexColor("#f3f4f6")),
                ("BACKGROUND", (0, -4), (-1, -4), colors.HexColor("#f3f4f6")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 7), (0, -5), "Helvetica-Bold"),
                ("FONTSIZE", (0, 7), (-1, -5), 7.6),
                ("BOTTOMPADDING", (0, -3), (0, -1), 5),
                ("TOPPADDING", (0, -3), (0, -3), 3),
                ("TOPPADDING", (0, -2), (0, -2), 2),
                ("TOPPADDING", (0, -1), (0, -1), 0),
                ("LINEBELOW", (0, 2), (4, 2), 0.7, colors.HexColor("#111")),
                ("LINEBELOW", (0, -2), (4, -2), 0.7, colors.HexColor("#111")),
            ]
        )
    )

    doc.build([t])
    pdf_data = buffer.getvalue()
    buffer.close()

    filename = f"{faculty.name}_{status_label}_{month_label}_{year}.pdf"
    response = HttpResponse(pdf_data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response



@faculty_required
def faculty_announcements_view(request):
    data = get_faculty_data(request)

    user = request.user
    today = timezone.now().date()
    selected_year = request.GET.get('year', '')

    try:
        publish_due_scheduled_announcements_task.delay(limit=20)
    except Exception:
        pass

    announcements = Announcement.objects.filter(
        visible_to_roles__contains=[user.role],
        is_active=True,
    ).filter(
        start_date__lte=today
    ).filter(
        Q(end_date__gte=today) | Q(end_date__isnull=True)
    ).filter(
        Q(scheduled_publish_at__isnull=True) | Q(published_at__isnull=False)
    ).order_by('-created_at')

    if selected_year:
        try:
            announcements = announcements.filter(created_at__year=int(selected_year))
        except (TypeError, ValueError):
            selected_year = ''

    years = [item.year for item in Announcement.objects.filter(visible_to_roles__contains=[user.role]).dates('created_at', 'year', order='DESC')]

    seen_ids = AnnouncementViewLog.objects.filter(user=user).values_list('announcement__uuid', flat=True)

    return render(request,  'faculty/faculty_announcements.html',  {
        **data,
        'announcements': announcements,
        'seen_ids': list(seen_ids),
        'years': years,
        'selected_year': selected_year,
    })





@faculty_required
def view_announcement_ajax(request, uuid):
    user = request.user
    try:
        announcement = Announcement.objects.get(uuid=uuid)
    except Announcement.DoesNotExist:
        raise Http404("Announcement not found")

    today = timezone.now().date()
    is_currently_publishable = (
        announcement.scheduled_publish_at is None or announcement.published_at is not None
    )

    if (
        user.role not in announcement.visible_to_roles
        or not announcement.is_active
        or not is_currently_publishable
        or announcement.start_date > today
        or (announcement.end_date is not None and announcement.end_date < today)
    ):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    AnnouncementViewLog.objects.get_or_create(user=user, announcement=announcement)

    data = {
        'title': announcement.title,
        'content': announcement.content,
        'attachment_link': announcement.attachment_link,
    }

    return JsonResponse(data)




@faculty_required
def faculty_deliverables_view(request):
    data = get_faculty_data(request)
    faculty = request.user.faculty_profile
    today = timezone.localdate()

    active_semester = (
        Semester.objects.filter(is_active=True)
        .select_related("academic_year")
        .order_by("-start_date")
        .first()
    )

    semester = active_semester

    if not semester:
        data.update({
            'semester': None,
            'academic_year_str': '',
            'semester_str': '',
            'assignment_rows': [],
            'total_pending_deliverables': 0,
            'can_request_clearance': False,
            'clearance_request': None,
            'clearance_eligibility': {
                'blocking_reasons': ["No semester with teaching assignments is available."],
            },
        })
        return render(request, 'faculty/faculty_deliverables.html', data)

    assignments = TeachingAssignment.objects.filter(
        faculty=faculty,
        semester=semester
    ).order_by('day_of_week', 'start_time')

    deliverables = Deliverable.objects.filter(
        semester=semester
    ).select_related('document_category')

    total_required_per_assignment = deliverables.count()

    assignment_rows = []
    all_assignments_complete = True 
    total_pending_deliverables = 0
    pending_slots = 0
    overdue_slots = 0

    for ta in assignments:
        docs_qs = FacultyDocument.objects.filter(
            faculty=faculty,
            semester=semester,
            teaching_assignment=ta,
            deliverable__in=deliverables,
            is_archived=False,
        ).select_related('deliverable', 'document_category')

        approved_count = docs_qs.filter(status='Approved').count()
        pending_count = max(total_required_per_assignment - approved_count, 0)
        total_pending_deliverables += pending_count

        deliverable_rows = []
        for d in deliverables:
            doc = docs_qs.filter(deliverable=d).order_by('-uploaded_at').first()
            if not (doc and doc.status == 'Approved'):
                pending_slots += 1
                if today > d.deadline:
                    overdue_slots += 1
            deliverable_rows.append({
                'deliverable': d,
                'doc': doc,
                'is_deadline_passed': today > d.deadline,
            })

        if total_required_per_assignment > 0:
            assignment_complete = (approved_count == total_required_per_assignment)
        else:
            assignment_complete = True 

        if not assignment_complete:
            all_assignments_complete = False

        assignment_rows.append({
            'ta': ta,
            'approved_count': approved_count,
            'total_required': total_required_per_assignment,
            'pending_count': pending_count,
            'has_pending_deliverables': pending_count > 0,
            'deliverable_rows': deliverable_rows,
            'is_complete': assignment_complete,
        })

    academic_year_str = str(semester.academic_year)
    semester_str = semester.get_semester_type_display()
    clearance_eligibility = evaluate_faculty_clearance_eligibility(faculty=faculty, semester=semester)
    clearance_request = FacultyClearanceRequest.objects.filter(
        faculty=faculty,
        semester=semester,
    ).first()

    data.update({
        'semester': semester,
        'academic_year_str': academic_year_str,
        'semester_str': semester_str,
        'assignment_rows': assignment_rows,
        'total_pending_deliverables': total_pending_deliverables,
        'can_request_clearance': (
            all_assignments_complete
            and assignments.exists()
            and deliverables.exists()
            and clearance_eligibility['is_eligible']
        ),
        'clearance_request': clearance_request,
        'clearance_eligibility': clearance_eligibility,
        'upload_blocked_due_deadline': pending_slots > 0 and pending_slots == overdue_slots,
    })

    return render(request, 'faculty/faculty_deliverables.html', data)









@faculty_required
@require_POST
def faculty_request_clearance_view(request):
    faculty = request.user.faculty_profile
    semester = (
        Semester.objects.filter(is_active=True)
        .select_related("academic_year")
        .order_by("-start_date")
        .first()
    )

    if not semester:
        messages.error(request, "No active semester is available for clearance request.")
        return redirect("faculty:faculty_deliverables")

    if not TeachingAssignment.objects.filter(faculty=faculty, semester=semester).exists():
        messages.error(request, "You have no teaching assignments for the active semester.")
        return redirect("faculty:faculty_deliverables")

    eligibility = evaluate_faculty_clearance_eligibility(faculty=faculty, semester=semester)
    if not eligibility["is_eligible"]:
        reason = " ".join(eligibility["blocking_reasons"]) or "All deliverables must be approved before requesting clearance."
        messages.error(request, reason)
        return redirect("faculty:faculty_deliverables")

    clearance_number = build_clearance_number(faculty=faculty, semester=semester)
    now = timezone.now()

    FacultyClearanceRequest.objects.update_or_create(
        faculty=faculty,
        semester=semester,
        defaults={
            "status": FacultyClearanceRequest.STATUS_APPROVED,
            "clearance_number": clearance_number,
            "approved_at": now,
            "rejected_at": None,
            "rejection_reason": "",
            "snapshot_total_required": eligibility["total_required"],
            "snapshot_total_approved": eligibility["approved_slots"],
            "snapshot_total_pending": eligibility["pending_slots"],
            "snapshot_total_rejected": eligibility["rejected_slots"],
            "snapshot_total_missing": eligibility["missing_slots"],
            "snapshot_total_overdue": eligibility["overdue_slots"],
        },
    )

    messages.success(request, f"Clearance auto-approved for {semester.get_semester_type_display()} {semester.academic_year}.")
    return redirect("faculty:faculty_deliverables")


@faculty_required
def faculty_download_clearance_view(request):
    faculty = request.user.faculty_profile
    semester_id = request.GET.get("semester", "")

    if not semester_id.isdigit():
        raise Http404("Semester is required.")

    clearance_request = get_object_or_404(
        FacultyClearanceRequest.objects.select_related("faculty__account", "semester__academic_year"),
        faculty=faculty,
        semester_id=int(semester_id),
        status=FacultyClearanceRequest.STATUS_APPROVED,
    )

    return build_clearance_pdf_response(clearance_request)


@faculty_required
def faculty_deliverable_upload(request):
    data = get_faculty_data(request)
    account = request.user
    faculty = getattr(account, "faculty_profile", None)

    DocumentFormSet = formset_factory(
        FacultyDeliverableUploadForm,
        formset=BaseIndexedFormSet,
        extra=1,
        max_num=10,
        validate_max=True,
    )

    form_kwargs = {
        "faculty": faculty,
        "request": request,
    }

    allowed_deliverables_map = {}
    deliverables_catalog = {}  # id -> display label
    active_semester = Semester.objects.filter(is_active=True).first()
    today = timezone.localdate()
    pending_slots = 0
    overdue_slots = 0
    if active_semester and faculty:
        assignments = TeachingAssignment.objects.filter(
            faculty=faculty,
            semester=active_semester,
        )
        deliverables = Deliverable.objects.filter(
            semester=active_semester,
        ).select_related("document_category")

        for d in deliverables:
            deliverables_catalog[d.id] = str(d)

        for ta in assignments:
            allowed_ids = []
            for d in deliverables:
                doc = (
                    FacultyDocument.objects.filter(
                        faculty=faculty,
                        semester=active_semester,
                        teaching_assignment=ta,
                        deliverable=d,
                    )
                    .order_by("-uploaded_at")
                    .first()
                )
                if doc and doc.status == "Approved":
                    continue

                pending_slots += 1
                if today > d.deadline:
                    overdue_slots += 1
                    continue

                if not doc or doc.status != "Approved":
                    allowed_ids.append(d.id)
            allowed_deliverables_map[ta.id] = allowed_ids

    upload_blocked_due_deadline = pending_slots > 0 and pending_slots == overdue_slots
    deadline_block_message = ""
    if upload_blocked_due_deadline:
        deadline_block_message = (
            "Upload is blocked because all pending deliverables are already past their deadline."
        )

    if request.method == "POST":
        formset = DocumentFormSet(request.POST, request.FILES, form_kwargs=form_kwargs)

        if formset.is_valid():
            non_empty_count = 0
            for form in formset:
                cd = form.cleaned_data
                ta = cd.get("teaching_assignment")
                d = cd.get("deliverable")
                f = cd.get("file")
                if ta or d or f:
                    non_empty_count += 1

            if non_empty_count == 0:
                formset._non_form_errors = formset.error_class(
                    ["Please fill out at least one upload card before submitting."]
                )
                messages.error(
                    request, "Please fill out at least one upload card before submitting."
                )
                data["formset"] = formset
                data["allowed_deliverables_json"] = json.dumps(
                    allowed_deliverables_map, cls=DjangoJSONEncoder
                )
                data["deliverables_catalog_json"] = json.dumps(
                    deliverables_catalog, cls=DjangoJSONEncoder
                )
                data["upload_blocked_due_deadline"] = upload_blocked_due_deadline
                data["deadline_block_message"] = deadline_block_message
                return render(request, "faculty/faculty_deliverables_upload.html", data)

            service = CentralGoogleDriveService()
            success_count = 0

            for form in formset:
                cd = form.cleaned_data
                teaching_assignment = cd.get("teaching_assignment")
                deliverable = cd.get("deliverable")
                file = cd.get("file")

                # Skip rows that are completely empty (per form.clean())
                if not teaching_assignment and not deliverable and not file:
                    continue

                try:
                    category = deliverable.document_category
                    document_name = FacultyDocument.classroom_document_name(category, deliverable.semester)

                    existing_docs = list(
                        FacultyDocument.objects.filter(
                            faculty=faculty,
                            semester=deliverable.semester,
                            teaching_assignment=teaching_assignment,
                            deliverable=deliverable,
                        )
                        .exclude(status="Approved")
                        .order_by("-uploaded_at")
                    )
                    existing_doc = existing_docs[0] if existing_docs else None

                    # Upload new file to Drive
                    media = MediaIoBaseUpload(
                        io.BytesIO(file.read()),
                        mimetype=file.content_type,
                        resumable=False,
                    )
                    upload = (
                        service.service.files()
                        .create(
                            body={
                                "name": file.name,
                                "parents": [faculty.gdrive_folder_id],
                            },
                            media_body=media,
                            fields="id,webViewLink",
                        )
                        .execute()
                    )

                    if existing_doc:
                        try:
                            service.service.files().delete(fileId=existing_doc.google_drive_id).execute()
                        except Exception as e:
                            print("Error deleting old Drive file:", e)

                        # Remove any older duplicate rows for this same assignment/deliverable.
                        for stale_doc in existing_docs[1:]:
                            try:
                                if stale_doc.google_drive_id:
                                    service.service.files().delete(fileId=stale_doc.google_drive_id).execute()
                            except Exception as e:
                                print("Error deleting stale Drive file:", e)
                            stale_doc.delete()

                        existing_doc.document_name = document_name
                        existing_doc.uploaded_by = account
                        existing_doc.document_category = category
                        existing_doc.file_path = upload["webViewLink"]
                        existing_doc.google_drive_id = upload["id"]
                        existing_doc.file_size = file.size
                        existing_doc.expiry_date = None
                        existing_doc.status = "Pending"
                        existing_doc.admin_remarks = ""
                        existing_doc.uploaded_at = timezone.now()
                        existing_doc.semester = deliverable.semester
                        existing_doc.deliverable = deliverable
                        existing_doc.teaching_assignment = teaching_assignment
                        existing_doc.save()
                    else:
                        FacultyDocument.objects.create(
                            faculty=faculty,
                            uploaded_by=account,
                            document_name=document_name,
                            document_category=category,
                            file_path=upload["webViewLink"],
                            google_drive_id=upload["id"],
                            file_size=file.size,
                            expiry_date=None,
                            status="Pending",
                            semester=deliverable.semester,
                            deliverable=deliverable,
                            teaching_assignment=teaching_assignment,
                        )

                    success_count += 1

                except Exception as e:
                    print("Upload error:", e)
                    messages.error(
                        request,
                        f"Failed to upload file for {deliverable} ({teaching_assignment}).",
                    )

            if success_count:
                notify_role(
                    roles=ROLE_ADMIN_GROUP,
                    actor=account,
                    notification_type='faculty_deliverable_uploaded',
                    title='New faculty deliverable upload',
                    message=f"{faculty.name or account.email} uploaded {success_count} deliverable file(s) for review.",
                    url=reverse('adminhub:deliverables'),
                    related_type='FacultyProfile',
                    related_id=str(faculty.uuid),
                    aggregate_key=f"faculty_deliverable_upload:{account.id}",
                )
                log_activity(
                    actor=account,
                    action='faculty_deliverable_uploaded',
                    target_type='FacultyProfile',
                    target_id=str(faculty.uuid),
                    details={
                        'target_name': faculty.name or account.email,
                        'count': success_count,
                    },
                )
                messages.success(
                    request, f"{success_count} deliverable(s) uploaded successfully."
                )
            return redirect("faculty:faculty_deliverables")

        else:
            messages.error(request, "Please fix the errors in the form before uploading.")
    else:
        formset = DocumentFormSet(form_kwargs=form_kwargs)

    data["formset"] = formset
    data["allowed_deliverables_json"] = json.dumps(
        allowed_deliverables_map, cls=DjangoJSONEncoder
    )
    data["deliverables_catalog_json"] = json.dumps(
        deliverables_catalog, cls=DjangoJSONEncoder
    )
    data["upload_blocked_due_deadline"] = upload_blocked_due_deadline
    data["deadline_block_message"] = deadline_block_message
    return render(request, "faculty/faculty_deliverables_upload.html", data)







@faculty_required
def faculty_document_templates(request):
    """
    Read-only list of document templates for faculty.
    Faculty can download/view templates and then upload completed documents via the existing upload flow.
    """
    search = request.GET.get("q", "")
    category_id = request.GET.get("category")

    templates = (
        DocumentTemplate.objects
        .filter(is_active=True)
        .select_related("document_category")
    )

    if search:
        templates = templates.filter(
            Q(name__icontains=search) |
            Q(document_category__name__icontains=search)
        )

    if category_id:
        templates = templates.filter(document_category_id=category_id)

    templates = templates.order_by("document_category__name", "name")

    # Helper to format sizes
    def format_storage(size_bytes):
        if not size_bytes:
            return "0 bytes"
        if size_bytes >= 1024 ** 3:
            return f"{size_bytes / (1024 ** 3):.2f} GB"
        elif size_bytes >= 1024 ** 2:
            return f"{size_bytes / (1024 ** 2):.2f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.2f} KB"
        return f"{size_bytes} bytes"

    for t in templates:
        t.size_human = format_storage(t.file_size or 0)

    paginator = Paginator(templates, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    categories = DocumentCategory.objects.all().order_by("name")

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "categories": categories,
        "selected_category": category_id,
        "search_query": search,
    }
    return render(request, "faculty/faculty_document_templates.html", context)




@faculty_required
def download_document_template(request, uid):
    """
    Streams or returns bytes for a document template stored on Google Drive.
    Uses uid (UUID) to lookup template.
    Query param inline=1 requests inline preview (only honored for PDF/images).
    """
    template = get_object_or_404(DocumentTemplate, uid=uid, is_active=True)
    file_id = template.google_drive_id

    drive = CentralGoogleDriveService()
    want_inline = request.GET.get('inline', '0').lower() in ('1', 'true', 'yes')

    # Get metadata
    try:
        meta = drive.service.files().get(fileId=file_id, fields='mimeType, name, size').execute()
        mime_type = meta.get('mimeType')
        name_on_drive = meta.get('name') or template.name or f'template_{template.uid}'
    except Exception:
        raise Http404("Could not retrieve template file metadata from Google Drive.")

    # Google-native types -> export to PDF
    if mime_type and mime_type.startswith('application/vnd.google-apps.'):
        export_mime = 'application/pdf'
        try:
            exported_bytes = drive.service.files().export(fileId=file_id, mimeType=export_mime).execute()
        except Exception:
            raise Http404("Template file could not be exported from Google Drive.")

        content_type = export_mime
        disposition = 'inline' if (want_inline and content_type == 'application/pdf') else 'attachment'
        resp = HttpResponse(exported_bytes, content_type=content_type)
        resp['Content-Disposition'] = f'{disposition}; filename="{name_on_drive}"'
        resp['Content-Length'] = str(len(exported_bytes))
        return _finalize_response(resp)

    # Binary files -> stream
    content_type = mime_type or mimetypes.guess_type(name_on_drive)[0] or 'application/octet-stream'
    inline_allowed = (content_type == 'application/pdf') or content_type.startswith('image/')

    if want_inline and inline_allowed:
        response = StreamingHttpResponse(_stream_drive_media(drive, file_id), content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{name_on_drive}"'
        return _finalize_response(response)

    response = StreamingHttpResponse(_stream_drive_media(drive, file_id), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{name_on_drive}"'
    return _finalize_response(response)
