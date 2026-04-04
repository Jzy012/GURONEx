# Standard Library Imports
import calendar
import datetime
import io
import json
import logging
import mimetypes
import os
import re
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

# Django Imports
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.forms import modelformset_factory
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.timezone import localtime
from django.utils.translation import gettext as _
from django.utils.translation import gettext as gettext_func
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# Third-party Imports (ReportLab)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

# Third-party Imports (Google API)
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# Local Imports
from adminhub.models import Announcement, DocumentTemplate, PUPSite, DocumentCategory, CreatedAccountLog
from adminhub.tasks import (
    DEFAULT_ANNOUNCEMENT_ROLES,
    publish_due_scheduled_announcements_task,
    publish_scheduled_announcement_task,
    send_announcement_email_task,
)
from applicant.models import Applicant, ApplicantDocument, ApplicantRequiredDocument
from base.decorators import admin_required, faculty_required
from base.forms import (
    AnnouncementForm,
    AcademicYearForm,
    ApplicantRequiredDocumentForm,
    AssignDeliverablesForm,
    BackgroundUploadForm,
    BaseSemesterFormSet,
    DeliverableTemplateForm,
    DocumentCategoryForm,
    DocumentTemplateForm,
    DTRLogEditForm,
    EmploymentStatusForm,
    FacultyCreationForm,
    FacultyEditForm,
    ManualAttendanceLogForm,
    SemesterForm,
    TeachingAssignmentBulkUploadForm,
    TeachingAssignmentForm,
    TwoFactorToggleForm,
    PUPSiteForm
)
from base.models import Account, GoogleStorageAccount, LandingAppearance
from base.utils.admin_data import get_admin_data, get_all_faculty_data
from base.utils.dtr_workinghours import calculate_total_working_hours
from base.utils.email import (
    send_applicant_status_email,
    send_applicant_status_rescheduled_email,
    send_html_email,
)
from base.utils.teaching_assignment import (
    get_all_faculty_list,
    get_all_semesters,
    read_file_to_rows,
)
from faculty.models import (
    AcademicYear,
    Deliverable,
    DeliverableTemplate,
    EmploymentStatus,
    FacultyDocument,
    FacultyProfile,
    FacultyRequest,
    FileType,
    Semester,
    TeachingAssignment,
)
from rfid.models import AttendanceLog, RFIDTag
from rfid.views import format_log
from services.dtr_service import DTRCalculator
from services.google_drive_service import CentralGoogleDriveService, get_google_drive_status

# Logger Setup
logger = logging.getLogger(__name__)




@admin_required
def home(request):
    # Stats cards
    data = get_admin_data(request) if 'get_admin_data' in globals() else {}

    total_applicants = Applicant.objects.count()
    total_faculty = FacultyProfile.objects.count()
    total_pending_docs = FacultyDocument.objects.filter(status='Pending', is_archived=False).count()
    total_requests = FacultyRequest.objects.count()
    total_storage_bytes = FacultyDocument.objects.filter(is_archived=False).aggregate(total_size=Sum('file_size'))['total_size'] or 0

    def format_storage(size_bytes):
        if size_bytes >= 1024**3:
            return f"{size_bytes / (1024**3):.2f} GB"
        elif size_bytes >= 1024**2:
            return f"{size_bytes / (1024**2):.2f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.2f} KB"
        return f"{size_bytes} bytes"
    total_storage = format_storage(total_storage_bytes)

    # Recent announcements
    recent_announcements = Announcement.objects.order_by('-created_at')[:3]

    # Google Drive Status
    status = get_google_drive_status()

    context = {
        'total_applicants': total_applicants,
        'total_faculty': total_faculty,
        'total_pending_docs': total_pending_docs,
        'total_requests': total_requests,
        'total_storage': total_storage,
        'recent_announcements': recent_announcements,
        'status': status,
    }
    if data:
        context = {**data, **context}

    return render(request, 'admin/admin_home.html', context)



@admin_required
def documents(request):
    search_query = request.GET.get('q', '')
    category_id = request.GET.get('category')
    status_filter = request.GET.get('status')

    documents = FacultyDocument.objects.select_related('faculty__account', 'document_category').filter(is_archived=False)

    if search_query:
        documents = documents.filter(
            Q(document_name__icontains=search_query) |
            Q(faculty__account__first_name__icontains=search_query) |
            Q(faculty__account__last_name__icontains=search_query) |
            Q(faculty__account__email__icontains=search_query)
        )

    if category_id:
        documents = documents.filter(document_category_id=category_id)

    if status_filter:
        documents = documents.filter(status=status_filter)

    documents = documents.order_by('-uploaded_at')

    # 📊 Stats
    total_documents = documents.count()
    total_storage_bytes = documents.aggregate(total_size=Sum('file_size'))['total_size'] or 0
    pending_documents = documents.filter(status='Pending').count()

    def format_storage(size_bytes):
        if size_bytes >= 1024**3:
            return f"{size_bytes / (1024**3):.2f} GB"
        elif size_bytes >= 1024**2:
            return f"{size_bytes / (1024**2):.2f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.2f} KB"
        return f"{size_bytes} bytes"

    total_storage_human = format_storage(total_storage_bytes)

    # 📊 Per-category breakdown
    categories = (
        DocumentCategory.objects
        .annotate(
            total_docs=Count('documents', filter=Q(documents__is_archived=False)),
            total_storage_bytes=Sum('documents__file_size', filter=Q(documents__is_archived=False)),
            pending_count=Count('documents', filter=Q(documents__status='Pending', documents__is_archived=False))
        )
        .order_by('name')
    )

    # Convert storage to human-readable format
    for cat in categories:
        cat.total_storage = format_storage(cat.total_storage_bytes or 0)

    # Convert each document's file size to human-readable format
    for doc in documents:
        doc.size_human = format_storage(doc.file_size or 0)


    # Pagination
    paginator = Paginator(documents, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    context = {
        'page_obj': page_obj,
        'paginator': paginator,
        'categories': categories,
        'search_query': search_query,
        'selected_category': category_id,
        'selected_status': status_filter,

        # 📊 Stats
        'total_documents': total_documents,
        'total_storage': total_storage_human,
        'pending_documents': pending_documents,

        'querystring': querystring,
    }

    return render(request, 'admin/admin_documents_storage.html', context)


@admin_required
@require_POST
def change_document_status(request, uid):
    try:
        doc = FacultyDocument.objects.get(uid=uid)
    except FacultyDocument.DoesNotExist:
        return JsonResponse({"error": "Document not found"}, status=404)

    new_status = request.POST.get('status')
    remarks = request.POST.get('remarks', '')  # could be empty

    if new_status not in ['Approved', 'Rejected', 'Pending']:
        return JsonResponse({"error": "Invalid status"}, status=400)

    if doc.is_archived:
        return JsonResponse({"error": "Archived documents cannot be updated."}, status=400)

    doc.status = new_status
    doc.admin_remarks = remarks
    doc.save(update_fields=['status', 'admin_remarks'])

    # You could also send back some info for updating the row
    return JsonResponse({
        "success": True,
        "status": doc.status,
        "admin_remarks": doc.admin_remarks,
    })


def _redirect_back(request, fallback_url_name='adminhub:documents'):
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER')
    if next_url:
        return redirect(next_url)
    return redirect(fallback_url_name)


@admin_required
@require_POST
def archive_document(request, uid):
    doc = get_object_or_404(FacultyDocument, uid=uid)
    if doc.is_archived:
        messages.info(request, "Document is already archived.")
        return _redirect_back(request)

    doc.archive(by_user=request.user)
    messages.success(request, "Document archived successfully.")
    return _redirect_back(request)


@admin_required
@require_POST
def restore_document(request, uid):
    doc = get_object_or_404(FacultyDocument, uid=uid)
    if not doc.is_archived:
        messages.info(request, "Document is already active.")
        return _redirect_back(request)

    doc.restore(by_user=request.user)
    messages.success(request, "Document restored successfully.")
    return _redirect_back(request)


@admin_required
@require_POST
def archive_faculty_document(request, pk):
    doc = get_object_or_404(FacultyDocument, pk=pk)
    if doc.is_archived:
        messages.info(request, "Document is already archived.")
        return _redirect_back(request)

    doc.archive(by_user=request.user)
    messages.success(request, "Faculty document archived successfully.")
    return _redirect_back(request)


@admin_required
@require_POST
def restore_faculty_document(request, pk):
    doc = get_object_or_404(FacultyDocument, pk=pk)
    if not doc.is_archived:
        messages.info(request, "Document is already active.")
        return _redirect_back(request)

    doc.restore(by_user=request.user)
    messages.success(request, "Faculty document restored successfully.")
    return _redirect_back(request)


@admin_required
@require_POST
def archive_applicant_document(request, pk):
    doc = get_object_or_404(ApplicantDocument, pk=pk)
    if doc.is_archived:
        messages.info(request, "Document is already archived.")
        return _redirect_back(request)

    doc.archive(by_user=request.user)
    messages.success(request, "Applicant document archived successfully.")
    return _redirect_back(request, fallback_url_name='adminhub:applicant_list')


@admin_required
@require_POST
def restore_applicant_document(request, pk):
    doc = get_object_or_404(ApplicantDocument, pk=pk)
    if not doc.is_archived:
        messages.info(request, "Document is already active.")
        return _redirect_back(request)

    doc.restore(by_user=request.user)
    messages.success(request, "Applicant document restored successfully.")
    return _redirect_back(request, fallback_url_name='adminhub:applicant_list')


@admin_required
@require_POST
def delete_faculty_document_permanently(request, pk):
    doc = get_object_or_404(FacultyDocument, pk=pk)
    if not doc.is_archived:
        messages.error(request, "Only archived documents can be permanently deleted.")
        return _redirect_back(request, fallback_url_name='adminhub:archived_documents')

    doc.delete()
    messages.success(request, "Faculty document deleted permanently.")
    return _redirect_back(request, fallback_url_name='adminhub:archived_documents')


@admin_required
@require_POST
def delete_applicant_document_permanently(request, pk):
    doc = get_object_or_404(ApplicantDocument, pk=pk)
    if not doc.is_archived:
        messages.error(request, "Only archived documents can be permanently deleted.")
        return _redirect_back(request, fallback_url_name='adminhub:archived_documents')

    doc.delete()
    messages.success(request, "Applicant document deleted permanently.")
    return _redirect_back(request, fallback_url_name='adminhub:archived_documents')


def _get_filtered_archived_docs(doc_type, search_query, category_id, status_filter):
    faculty_docs = FacultyDocument.objects.filter(is_archived=True).select_related(
        'faculty__account', 'document_category', 'archived_by'
    )
    applicant_docs = ApplicantDocument.objects.filter(is_archived=True).select_related(
        'applicant', 'document_category', 'archived_by'
    )

    if search_query:
        faculty_docs = faculty_docs.filter(
            Q(document_name__icontains=search_query)
            | Q(faculty__name__icontains=search_query)
            | Q(faculty__account__email__icontains=search_query)
        )
        applicant_docs = applicant_docs.filter(
            Q(document_category__name__icontains=search_query)
            | Q(applicant__first_name__icontains=search_query)
            | Q(applicant__last_name__icontains=search_query)
            | Q(applicant__email__icontains=search_query)
        )

    if category_id:
        faculty_docs = faculty_docs.filter(document_category_id=category_id)
        applicant_docs = applicant_docs.filter(document_category_id=category_id)

    if status_filter:
        faculty_docs = faculty_docs.filter(status=status_filter)
        applicant_docs = applicant_docs.filter(status=status_filter)

    if doc_type == 'faculty':
        applicant_docs = ApplicantDocument.objects.none()
    elif doc_type == 'applicant':
        faculty_docs = FacultyDocument.objects.none()

    return faculty_docs, applicant_docs


@admin_required
@require_POST
def archived_documents_bulk_action(request):
    action = (request.POST.get('bulk_action') or '').strip()
    doc_type = request.POST.get('type', 'all')
    search_query = (request.POST.get('q') or '').strip()
    category_id = (request.POST.get('category') or '').strip()
    status_filter = (request.POST.get('status') or '').strip()

    selected_docs = request.POST.getlist('selected_docs') + request.POST.getlist('selected_docs_mobile')
    selected_docs = list(dict.fromkeys(selected_docs))

    faculty_docs, applicant_docs = _get_filtered_archived_docs(doc_type, search_query, category_id, status_filter)

    restored_count = 0
    deleted_count = 0

    if action in ('restore_selected', 'delete_selected') and not selected_docs:
        messages.warning(request, "Please select at least one document.")
    elif action == 'restore_all':
        restored_count += faculty_docs.update(is_archived=False, restored_at=timezone.now(), restored_by=request.user)
        restored_count += applicant_docs.update(is_archived=False, restored_at=timezone.now(), restored_by=request.user)
        messages.success(request, f"Restored {restored_count} document(s).")
    elif action == 'delete_all':
        deleted_count += faculty_docs.count()
        faculty_docs.delete()
        deleted_count += applicant_docs.count()
        applicant_docs.delete()
        messages.success(request, f"Deleted {deleted_count} document(s) permanently.")
    elif action in ('restore_selected', 'delete_selected'):
        faculty_ids = []
        applicant_ids = []

        for item in selected_docs:
            try:
                item_type, item_id = item.split(':', 1)
                item_id = int(item_id)
            except (ValueError, AttributeError):
                continue

            if item_type == 'faculty':
                faculty_ids.append(item_id)
            elif item_type == 'applicant':
                applicant_ids.append(item_id)

        selected_faculty_qs = faculty_docs.filter(pk__in=faculty_ids)
        selected_applicant_qs = applicant_docs.filter(pk__in=applicant_ids)

        if action == 'restore_selected':
            restored_count += selected_faculty_qs.update(is_archived=False, restored_at=timezone.now(), restored_by=request.user)
            restored_count += selected_applicant_qs.update(is_archived=False, restored_at=timezone.now(), restored_by=request.user)
            messages.success(request, f"Restored {restored_count} selected document(s).")
        else:
            deleted_count += selected_faculty_qs.count()
            selected_faculty_qs.delete()
            deleted_count += selected_applicant_qs.count()
            selected_applicant_qs.delete()
            messages.success(request, f"Deleted {deleted_count} selected document(s) permanently.")
    else:
        messages.error(request, "Invalid bulk action.")

    params = []
    if doc_type:
        params.append(f"type={doc_type}")
    if search_query:
        params.append(f"q={search_query}")
    if category_id:
        params.append(f"category={category_id}")
    if status_filter:
        params.append(f"status={status_filter}")

    query = ('?' + '&'.join(params)) if params else ''
    return redirect(reverse('adminhub:archived_documents') + query)


@admin_required
def archived_documents(request):
    doc_type = request.GET.get('type', 'all')
    search_query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category', '').strip()
    status_filter = request.GET.get('status', '').strip()

    faculty_docs, applicant_docs = _get_filtered_archived_docs(
        doc_type=doc_type,
        search_query=search_query,
        category_id=category_id,
        status_filter=status_filter,
    )

    rows = []
    if doc_type in ('all', 'faculty'):
        for doc in faculty_docs:
            rows.append({
                'type': 'faculty',
                'id': doc.pk,
                'uid': doc.uid,
                'owner_name': doc.faculty.name,
                'owner_email': doc.faculty.account.email,
                'document_name': doc.document_name,
                'category_name': doc.document_category.name if doc.document_category else 'N/A',
                'status': doc.status,
                'uploaded_at': doc.uploaded_at,
                'archived_at': doc.archived_at,
                'archived_by': doc.archived_by.email if doc.archived_by else 'N/A',
                'view_url': reverse('adminhub:download_document', args=[doc.uid]) + '?inline=1',
                'restore_url': reverse('adminhub:restore_faculty_document', args=[doc.pk]),
                'delete_url': reverse('adminhub:delete_faculty_document_permanently', args=[doc.pk]),
            })

    if doc_type in ('all', 'applicant'):
        for doc in applicant_docs:
            owner_name = f"{doc.applicant.first_name} {doc.applicant.last_name}".strip()
            rows.append({
                'type': 'applicant',
                'id': doc.pk,
                'uid': None,
                'owner_name': owner_name,
                'owner_email': doc.applicant.email,
                'document_name': doc.document_category.name if doc.document_category else 'Applicant Document',
                'category_name': doc.document_category.name if doc.document_category else 'N/A',
                'status': doc.status,
                'uploaded_at': doc.submitted_at,
                'archived_at': doc.archived_at,
                'archived_by': doc.archived_by.email if doc.archived_by else 'N/A',
                'view_url': reverse('adminhub:download_applicant_document', args=[doc.pk]) + '?inline=1',
                'restore_url': reverse('adminhub:restore_applicant_document', args=[doc.pk]),
                'delete_url': reverse('adminhub:delete_applicant_document_permanently', args=[doc.pk]),
            })

    rows.sort(key=lambda item: item['archived_at'].timestamp() if item['archived_at'] else 0, reverse=True)

    paginator = Paginator(rows, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    return render(request, 'admin/admin_archived_documents.html', {
        'page_obj': page_obj,
        'paginator': paginator,
        'categories': DocumentCategory.objects.order_by('name'),
        'selected_type': doc_type,
        'search_query': search_query,
        'selected_category': category_id,
        'selected_status': status_filter,
        'querystring': querystring,
    })


def view_document(request, uid):
    """
    Optional preview page (kept for compatibility).
    Lookup by uid (UUID) instead of numeric id.
    """
    doc = get_object_or_404(FacultyDocument, uid=uid)
    name_on_drive = doc.document_name or f"document_{doc.id}"
    ext = name_on_drive.split('.')[-1].lower() if '.' in name_on_drive else ''
    is_pdf = ext == 'pdf'
    is_image = ext in ('jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp')

    # Build absolute download URL using uid
    download_path = reverse('adminhub:download_document', args=[doc.uid])
    download_url = request.build_absolute_uri(download_path)
    preview_url = f"{download_url}?inline=1"

    context = {
        'doc': doc,
        'is_pdf': is_pdf,
        'is_image': is_image,
        'download_url': download_url,
        'preview_url': preview_url,
    }
    return render(request, 'admin/admin_document_view.html', context)


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

    # Get metadata
    try:
        meta = drive.service.files().get(fileId=file_id, fields='mimeType, name, size').execute()
        mime_type = meta.get('mimeType')
        name_on_drive = meta.get('name') or doc.document_name or f'document_{doc.id}'
    except Exception:
        raise Http404("Could not retrieve file metadata from Google Drive.")

    def _finalize_response(resp: HttpResponse):
        resp['X-Frame-Options'] = 'SAMEORIGIN'
        resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    # Google-native types -> export to PDF
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


@admin_required
def faculty_list_view(request):
    search = request.GET.get('search', '')
    status_id = request.GET.get('status', '')

    faculty_qs = FacultyProfile.objects.all().select_related('status').order_by('name')
    if search:
        faculty_qs = faculty_qs.filter(name__icontains=search)
    if status_id:
        faculty_qs = faculty_qs.filter(status_id=status_id)

    # Annotate with pending document counts
    faculty_qs = faculty_qs.annotate(
        pending_documents=Count('documents', filter=Q(documents__status='Pending', documents__is_archived=False))
    )

    total_faculty = FacultyProfile.objects.count()
    total_pending_docs = FacultyDocument.objects.filter(status='Pending', is_archived=False).count()
    statuses = EmploymentStatus.objects.filter(is_active=True)

    # Pagination (same as in documents view)
    paginator = Paginator(faculty_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Preserve other GET params for pagination links
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    return render(request, 'admin/admin_faculty_list.html', {
        'page_obj': page_obj,
        'paginator': paginator,
        'statuses': statuses,
        'total_faculty': total_faculty,
        'total_pending_docs': total_pending_docs,
        'search': search,
        'status_id': status_id,
        'querystring': querystring,
    })




@admin_required
def admin_settings(request):
    return render(request, 'admin/admin_settings.html') 


@admin_required
def admin_2fa(request):
    user = request.user

    if request.method == 'POST':
        form = TwoFactorToggleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "2FA setting updated." , extra_tags="2fa")
            return redirect("adminhub:admin_2fa")
    else:
        form = TwoFactorToggleForm(instance=user)

    return render(request, "admin/admin_2fa.html", {"form": form})




@admin_required
def faculty_detail_view(request, faculty_uuid):
    faculty = get_object_or_404(
        FacultyProfile.objects.select_related('account', 'status'),
        uuid=faculty_uuid
    )

    # Last 10 attendance logs, most recent first
    attendance_logs = (
        AttendanceLog.objects
        .filter(faculty=faculty)
        .prefetch_related('teaching_assignments')
        .order_by('-date', '-time_in')[:10]
    )

    documents = (
        faculty.documents
        .filter(is_archived=False)
        .select_related('document_category')
        .order_by('-uploaded_at')
    )

    form = FacultyEditForm(instance=faculty, account_instance=faculty.account)

    context = {
        'faculty': faculty,
        'documents': documents,
        'attendance_logs': attendance_logs,
        'form': form,
    }

    return render(request, 'admin/admin_faculty_detail.html', context)



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


@admin_required
def download_faculty_document(request, pk):
    """
    Streams or returns bytes for a faculty document stored on Google Drive.
    Uses pk (FacultyDocument primary key).
    Query param inline=1 requests inline preview (only honored for PDF/images).
    """
    doc = get_object_or_404(FacultyDocument, pk=pk)
    file_id = doc.google_drive_id

    drive = CentralGoogleDriveService()
    want_inline = request.GET.get('inline', '0').lower() in ('1', 'true', 'yes')

    # Get metadata
    try:
        meta = drive.service.files().get(fileId=file_id, fields='mimeType, name, size').execute()
        mime_type = meta.get('mimeType')
        name_on_drive = meta.get('name') or doc.document_name or f'document_{doc.id}'
    except Exception:
        raise Http404("Could not retrieve file metadata from Google Drive.")

    def _finalize_response(resp: HttpResponse):
        resp['X-Frame-Options'] = 'SAMEORIGIN'
        resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    # Google-native types -> export to PDF
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


@admin_required
@require_POST
def change_faculty_document_status(request, pk):
    """
    Change status (Pending / Approved / Rejected) of a faculty document via AJAX.
    """
    doc = get_object_or_404(FacultyDocument, pk=pk)

    new_status = request.POST.get('status')
    remarks = request.POST.get('remarks', '')

    if new_status not in ['Approved', 'Rejected', 'Pending']:
        return JsonResponse({"error": "Invalid status"}, status=400)

    if doc.is_archived:
        return JsonResponse({"error": "Archived documents cannot be updated."}, status=400)

    with transaction.atomic():
        doc.status = new_status
        doc.admin_remarks = remarks
        doc.save(update_fields=['status', 'admin_remarks'])

    return JsonResponse({
        "success": True,
        "status": doc.status,
        "admin_remarks": doc.admin_remarks or "",
    })








@admin_required
def create_faculty_view(request):
    if request.method == "POST":
        form = FacultyCreationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            password = data['password'] or form.generate_random_password()

            try:
                with transaction.atomic():
                    # 1. Create account
                    account = Account.objects.create_user(
                        email=data['email'],
                        password=password,
                        role='faculty'
                    )

                    # 2. Create faculty profile
                    faculty = FacultyProfile.objects.create(
                        account=account,
                        faculty_code=data.get("faculty_code"),
                        first_name=data.get("first_name"),
                        middle_name=data.get("middle_name"),
                        last_name=data.get("last_name"),
                        suffix=data.get("suffix"),
                        department=data.get("department"),
                        birth_date=data.get("birth_date"),
                        contact_number=data.get("contact_number"),
                        status=data.get("status"),
                    )


                    # 3. Attempt to create Drive folder
                    try:
                        drive = CentralGoogleDriveService()
                        folder_id = drive.create_faculty_folder(faculty)
                        faculty.gdrive_folder_id = folder_id
                        faculty.save()
                        messages.success(request, f"✅ Faculty created. Folder ID: {folder_id}")
                    except Exception as e:
                        messages.warning(
                            request,
                            f"⚠️ Faculty saved but Drive folder creation failed: {str(e)}"
                        )

                    # 4. Queue credentials email after transaction commits
                    def _send_credentials_email():
                        try:
                            login_url = request.build_absolute_uri(reverse('login'))  # adjust if your route differs
                            send_html_email(
                                subject="[LINANG] Faculty Account Credentials",
                                to_emails=account.email,
                                template_name="emails/faculty_welcome_credentials.html",
                                context={
                                    "name": faculty.name,
                                    "email": account.email,
                                    "password": password,
                                    "faculty_code": faculty.faculty_code,
                                    "department": faculty.department,
                                    "login_url": login_url,
                                },
                            )
                            logger.info("Sent credentials email to %s", account.email)
                        except Exception as e:
                            logger.exception("Failed to send credentials email: %s", e)

                    transaction.on_commit(_send_credentials_email)

                    if not data['password']:
                        messages.info(request, f"🛡️ Auto-generated password: {password}")

                    messages.success(request, "📧 Credentials will be emailed to the faculty. Please remind them to change their password immediately after logging in.")
                    return redirect('adminhub:faculty_list')

            except Exception as e:
                messages.error(request, f"❌ Error: {str(e)}")
    else:
        form = FacultyCreationForm()

    return render(request, 'admin/admin_faculty_creation.html', {'form': form})



@admin_required
def edit_faculty_view(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    account = faculty.account

    if request.method == "POST":
        form = FacultyEditForm(request.POST, instance=faculty, account_instance=account)
        if form.is_valid():
            email = form.cleaned_data['email']

            # Check email uniqueness for other accounts
            if Account.objects.filter(email=email).exclude(pk=account.pk).exists():
                form.add_error('email', "This email is already in use.")
            else:
                form.save()
                account.email = email
                account.save()
                messages.success(request, "✅ Faculty details updated successfully.")
                return redirect('adminhub:faculty_detail', faculty_uuid=faculty.uuid)
    else:
        form = FacultyEditForm(instance=faculty, account_instance=account)
    
    
    return render(request, 'admin/admin_faculty_edit.html', {'form': form, 'faculty': faculty})





@admin_required
def announcements_view(request):
    today = date.today()
    selected_year = request.GET.get('year', '')

    try:
        # Self-heal missed schedules in the background whenever this tab is opened.
        publish_due_scheduled_announcements_task.delay(limit=20)
    except Exception:
        logger.exception("Failed to queue scheduled announcement catch-up task")

    announcements = Announcement.objects.order_by('-created_at')
    if selected_year:
        try:
            announcements = announcements.filter(created_at__year=int(selected_year))
        except (TypeError, ValueError):
            selected_year = ''

    years = [item.year for item in Announcement.objects.dates('created_at', 'year', order='DESC')]

    return render(request, 'admin/admin_announcements.html', {
        'announcements': announcements,
        'today': today,
        'years': years,
        'selected_year': selected_year,
        'now': timezone.now(),
    })



@admin_required
def create_announcement_view(request):
    if request.user.role != 'admin':
        messages.error(request, "You are not authorized to create announcements.")
        return redirect('admin_home')  # or any fallback route

    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.creator = request.user
            announcement.visible_to_roles = DEFAULT_ANNOUNCEMENT_ROLES
            scheduled_publish_at = form.cleaned_data.get('scheduled_publish_at')
            now = timezone.now()

            if scheduled_publish_at:
                announcement.start_date = scheduled_publish_at.date()
                announcement.is_active = False
                announcement.published_at = None
                announcement.email_status = 'scheduled' if announcement.send_email else 'not_requested'
                announcement.email_queued_at = None
                announcement.email_processed_at = None
                announcement.email_attempted_count = 0
                announcement.email_sent_count = 0
                announcement.email_failed_count = 0
                announcement.email_last_error = ''
            else:
                announcement.start_date = now.date()
                announcement.is_active = True
                announcement.published_at = now

                if announcement.send_email:
                    announcement.email_status = 'queued'
                    announcement.email_queued_at = now
                    announcement.email_processed_at = None
                    announcement.email_attempted_count = 0
                    announcement.email_sent_count = 0
                    announcement.email_failed_count = 0
                    announcement.email_last_error = ''
                else:
                    announcement.email_status = 'not_requested'
                    announcement.email_queued_at = None
                    announcement.email_processed_at = now
                    announcement.email_attempted_count = 0
                    announcement.email_sent_count = 0
                    announcement.email_failed_count = 0
                    announcement.email_last_error = ''

            announcement.save()

            def _queue_announcement_job():
                try:
                    if scheduled_publish_at:
                        publish_scheduled_announcement_task.apply_async(
                            args=[announcement.id],
                            eta=scheduled_publish_at,
                        )
                    elif announcement.send_email:
                        send_announcement_email_task.delay(announcement.id)
                except Exception:
                    logger.exception("Failed to queue announcement job for announcement %s", announcement.id)

            transaction.on_commit(_queue_announcement_job)

            if scheduled_publish_at:
                messages.success(request, "Announcement scheduled successfully.")
            elif announcement.send_email:
                messages.success(request, "Announcement posted successfully. Email notifications were queued in the background.")
            else:
                messages.success(request, "Announcement posted successfully.")

            return redirect('adminhub:announcements')
        else:
            messages.error(request, "There was an error in your submission.")
    else:
        form = AnnouncementForm()

    return render(request, 'admin/admin_create_announcement.html', {'form': form})




@admin_required
def edit_announcement_view(request, uuid):
    announcement = get_object_or_404(Announcement, uuid=uuid)

    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.visible_to_roles = DEFAULT_ANNOUNCEMENT_ROLES

            scheduled_publish_at = form.cleaned_data.get('scheduled_publish_at')
            now = timezone.now()
            if scheduled_publish_at:
                updated.start_date = scheduled_publish_at.date()
                updated.is_active = False
                updated.published_at = None
                updated.email_status = 'scheduled' if updated.send_email else 'not_requested'
                updated.email_queued_at = None
                updated.email_processed_at = None
                updated.email_attempted_count = 0
                updated.email_sent_count = 0
                updated.email_failed_count = 0
                updated.email_last_error = ''
            else:
                updated.start_date = now.date()
                updated.is_active = True
                if updated.published_at is None:
                    updated.published_at = now

            updated.save()

            def _queue_updated_announcement_job():
                try:
                    if scheduled_publish_at:
                        publish_scheduled_announcement_task.apply_async(
                            args=[updated.id],
                            eta=scheduled_publish_at,
                        )
                except Exception:
                    logger.exception("Failed to queue updated announcement job for announcement %s", updated.id)

            transaction.on_commit(_queue_updated_announcement_job)

            if scheduled_publish_at:
                messages.success(request, "Announcement schedule updated successfully.")
            else:
                messages.success(request, "Announcement updated successfully.")
            return redirect('adminhub:announcements')
    else:
        form = AnnouncementForm(instance=announcement)

    return render(request, 'admin/admin_edit_announcement.html', {'form': form, 'announcement': announcement})





@require_POST
@admin_required
def delete_announcement_view(request, uuid):
    announcement = get_object_or_404(Announcement, uuid=uuid)
    title = announcement.title
    announcement.delete()
    messages.success(request, f"'{title}' has been permanently deleted.")
    return redirect('adminhub:announcements')





@admin_required
def deliverables_view(request):
    today = timezone.localdate()

    # Grab the active semester (by flag)
    semester = Semester.objects.filter(
        is_active=True
    ).select_related('academic_year').first()

    semester_date_mismatch = False
    if semester:
        # Extra rule: ensure the active semester contains today's date
        if not (semester.start_date <= today <= semester.end_date):
            semester_date_mismatch = True
    else:
        semester = None

    total_faculty = FacultyProfile.objects.count()

    completed_submissions = 0          # number of fully-complete faculty
    pending_submissions = 0            # total number of pending document slots
    deliverables_list = []
    academic_year_str = ""
    semester_str = ""

    # --- Search, filter, and pagination params ---
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "")
    page_number = request.GET.get("page")
    page_size = 10

    faculty_statuses_raw = []

    if semester:
        academic_year = semester.academic_year
        academic_year_str = str(academic_year)
        semester_str = semester.get_semester_type_display()

        # All deliverables for this semester
        deliverables = Deliverable.objects.filter(
            semester=semester
        ).select_related('document_category')

        deliverable_ids = list(deliverables.values_list('id', flat=True))
        deliverable_count = len(deliverable_ids)

        # For the "Active Deliverables" list
        deliverables_list = [
            {
                "name": d.document_category.name,
                "deadline": d.deadline,
            } for d in deliverables
        ]

        # Faculty base queryset, with status preloaded
        faculty_qs = FacultyProfile.objects.select_related('account', 'status').all()
        if search:
            faculty_qs = faculty_qs.filter(
                Q(name__icontains=search) | Q(account__email__icontains=search)
            )

        total_pending_docs_global = 0

        for faculty in faculty_qs:
            # How many teaching assignments this faculty has in this semester
            ta_count = TeachingAssignment.objects.filter(
                faculty=faculty,
                semester=semester,
            ).count()

            # Total required documents = (#deliverables * #teaching_assignments)
            total_required = deliverable_count * ta_count

            # How many documents are already approved for this faculty in this semester
            if total_required > 0:
                approved_count = FacultyDocument.objects.filter(
                    faculty=faculty,
                    semester=semester,
                    deliverable_id__in=deliverable_ids,
                    status="Approved",
                ).count()
            else:
                approved_count = 0

            # Pending docs for this faculty (document-level)
            faculty_pending_docs = max(total_required - approved_count, 0)
            total_pending_docs_global += faculty_pending_docs

            faculty_status = {
                "name": faculty.name,
                "email": faculty.account.email,
                "approved_count": approved_count,
                "total_required": total_required,
                "pending_docs": faculty_pending_docs,  
                "faculty_uuid": faculty.uuid,
                # Employment status info
                "status_label": faculty.status.name if faculty.status else None,
                "status_id": faculty.status_id,
            }

            # Filter by faculty-level completion if requested
            if status_filter == "completed" and (
                approved_count != total_required or total_required == 0
            ):
                continue
            if status_filter == "pending" and (
                approved_count == total_required and total_required > 0
            ):
                continue

            faculty_statuses_raw.append(faculty_status)

        # completed_submissions: number of fully complete faculty
        completed_submissions = sum(
            1 for f in faculty_statuses_raw
            if f["approved_count"] == f["total_required"] and f["total_required"] > 0
        )
        # pending_submissions: total pending docs across all faculty
        pending_submissions = total_pending_docs_global
    else:
        completed_submissions = 0
        pending_submissions = 0

    # Pagination of faculty_statuses_raw
    paginator = Paginator(faculty_statuses_raw, page_size)
    page_obj = paginator.get_page(page_number)

    # Preserve other GET params for pagination links
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    context = {
        'total_faculty': total_faculty,
        'completed_submissions': completed_submissions,
        'pending_submissions': pending_submissions,  # now doc-level count
        'page_obj': page_obj,
        'paginator': paginator,
        'deliverables_list': deliverables_list,
        'academic_year_str': academic_year_str,
        'semester_str': semester_str,
        'search': search,
        'status_filter': status_filter,
        'querystring': querystring,
        'semester_date_mismatch': semester_date_mismatch,
    }
    return render(request, 'admin/admin_deliverables.html', context)


@admin_required
def assign_deliverables_view(request):
    if request.method == 'POST':
        form = AssignDeliverablesForm(request.POST)
        if form.is_valid():
            semester = form.cleaned_data['semester']
            template = form.cleaned_data['template']
            deadline = form.cleaned_data['deadline']

            count = 0
            for doc_category in template.document_categories.all():
                if not Deliverable.objects.filter(
                    semester=semester,
                    document_category=doc_category
                ).exists():
                    Deliverable.objects.create(
                        semester=semester,
                        document_category=doc_category,
                        deadline=deadline
                    )
                    count += 1

            messages.success(request, f"{count} deliverables assigned to {semester}.")
            return redirect('adminhub:deliverables')  # Adjust to your dashboard/redirect
    else:
        form = AssignDeliverablesForm()

    return render(request, 'admin/admin_assign_deliverables.html', {'form': form})




@admin_required
def deliverable_templates_view(request):
    templates = DeliverableTemplate.objects.all()
    return render(request, 'admin/admin_deliverable_templates.html', {'templates': templates})


@admin_required
def create_deliverable_template_view(request):
    if request.method == 'POST':
        form = DeliverableTemplateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Deliverable template created.")
            return redirect('adminhub:deliverable_template')
    else:
        form = DeliverableTemplateForm()

    return render(request, 'admin/admin_create_deliverable_template.html', {'form': form})


@admin_required
def edit_deliverable_template_view(request, pk):
    template = get_object_or_404(DeliverableTemplate, pk=pk)

    if request.method == "POST":
        form = DeliverableTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, "Deliverable template updated successfully.")
            return redirect("adminhub:deliverable_template")
        messages.error(request, "There was an error in your submission.")
    else:
        form = DeliverableTemplateForm(instance=template)

    # Reuse the create template
    return render(request, "admin/admin_create_deliverable_template.html", {
        "form": form,
        "template": template,
        "page_title": "Edit Deliverable Template",
        "submit_label": "Update Template",
    })


@require_POST
@admin_required
def delete_deliverable_template_view(request, pk):
    template = get_object_or_404(DeliverableTemplate, pk=pk)
    name = template.name
    template.delete()
    messages.success(request, f"'{name}' has been permanently deleted.")
    return redirect("adminhub:deliverable_template")


@admin_required
def faculty_deliverables(request, faculty_uuid):
    today = timezone.localdate()

    # Active semester by flag, with date check
    semester = Semester.objects.filter(
        is_active=True
    ).select_related('academic_year').first()

    semester_date_mismatch = False
    if semester and not (semester.start_date <= today <= semester.end_date):
        semester_date_mismatch = True

    faculty = get_object_or_404(
        FacultyProfile.objects.select_related('account'),
        uuid=faculty_uuid
    )

    # Teaching assignments for this faculty in this semester
    assignments = TeachingAssignment.objects.filter(
        faculty=faculty,
        semester=semester
    ).order_by('day_of_week', 'start_time')

    # Deliverables for this semester
    deliverables = Deliverable.objects.filter(
        semester=semester
    ).select_related('document_category')

    total_required_per_assignment = deliverables.count()

    assignment_rows = []
    for ta in assignments:
        docs_qs = FacultyDocument.objects.filter(
            faculty=faculty,
            semester=semester,
            teaching_assignment=ta,
            deliverable__in=deliverables,
        ).select_related('deliverable', 'document_category')

        approved_count = docs_qs.filter(status='Approved').count()
        submitted_count = docs_qs.exclude(status='Rejected').count()  # tweak if needed

        # Build a list of (deliverable, doc) pairs for the template
        deliverable_rows = []
        for d in deliverables:
            doc = docs_qs.filter(deliverable=d).order_by('-uploaded_at').first()
            deliverable_rows.append({
                'deliverable': d,
                'doc': doc,
            })

        assignment_rows.append({
            'ta': ta,
            'approved_count': approved_count,
            'submitted_count': submitted_count,
            'total_required': total_required_per_assignment,
            'deliverable_rows': deliverable_rows,
        })

    academic_year_str = semester.academic_year if semester else ""
    semester_str = semester.get_semester_type_display() if semester else ""

    context = {
        'faculty': faculty,
        'semester': semester,
        'academic_year_str': academic_year_str,
        'semester_str': semester_str,
        'semester_date_mismatch': semester_date_mismatch,
        'assignment_rows': assignment_rows,
        'deliverables': deliverables,  # still useful for headers, counts, etc.
    }
    return render(request, 'admin/admin_faculty_deliverables.html', context)





@admin_required
def academic_years_view(request):
    academic_years = AcademicYear.objects.all()
    return render(request, 'admin/admin_academic_years.html', {'academic_years': academic_years})




@admin_required
def create_academic_year_view(request):
    SemesterFormSet = modelformset_factory(
        Semester,
        form=SemesterForm,
        formset=BaseSemesterFormSet,
        extra=3,
        can_delete=False
    )

    if request.method == 'POST':
        year_form = AcademicYearForm(request.POST)
        formset = SemesterFormSet(request.POST, queryset=Semester.objects.none())

        if year_form.is_valid() and formset.is_valid():
            # 1) Save academic year
            academic_year = year_form.save()

            # 2) Save semesters attached to this academic year
            for form in formset:
                if not hasattr(form, "cleaned_data") or form.errors:
                    continue
                semester = form.save(commit=False)
                semester.academic_year = academic_year
                semester.save()

            # 3) After saving, update active year & semester based on today's date
            today = timezone.localdate()
            AcademicYear.update_active_years(ref_date=today)
            Semester.update_active_semesters(ref_date=today)

            messages.success(request, "Academic year and semesters created.")
            return redirect('adminhub:create_academic_year')

    else:
        year_form = AcademicYearForm()
        formset = SemesterFormSet(
            queryset=Semester.objects.none(),
            initial=[
                {'semester_type': '1st'},
                {'semester_type': '2nd'},
                {'semester_type': 'summer'},
            ]
        )

    return render(request, 'admin/admin_create_academic_year.html', {
        'year_form': year_form,
        'formset': formset,
    })




@admin_required
def applicant_list_view(request):
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')

    # 1. Queryset: Applicant list, filtered by search and status
    applicant_qs = Applicant.objects.all().order_by('-created_at')
    if search:
        applicant_qs = applicant_qs.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    if status:
        applicant_qs = applicant_qs.filter(status=status)

    # 2. Annotate pending/missing documents (optional, if you want it in list)
    # applicant_qs = applicant_qs.annotate(
    #     pending_documents=Count('documents', filter=Q(documents__status='Pending'))
    # )

    # 3. Stats for dashboard cards
    total_applicants = Applicant.objects.count()
    total_hired = Applicant.objects.filter(status='hired').count()
    total_failed = Applicant.objects.filter(status='failed').count()
    total_pending = Applicant.objects.filter(status='pending').count()

    # 4. Pagination
    paginator = Paginator(applicant_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 5. For status filter dropdown
    status_choices = Applicant._meta.get_field('status').choices

    # 6. Preserve filters for pagination links
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    return render(request, 'admin/admin_applicant_list.html', {
        'page_obj': page_obj,
        'paginator': paginator,
        'status_choices': status_choices,
        'total_applicants': total_applicants,
        'total_hired': total_hired,
        'total_failed': total_failed,
        'total_pending': total_pending,
        'search': search,
        'status': status,
        'querystring': querystring,
    })




# Statuses in order for the stepper visualization
STEPPER_STATUSES = [
    ('pending', "Pending"),
    ('demo_scheduled', "Demo Scheduled"),
    ('for_interview', "For Interview"),
    ('psych_test', "Psych Test"),
    ('hired', "Hired"),
    ('failed', "Failed"),
]

STEPPER_DATE_FIELDS = {
    'demo_scheduled': 'demo_scheduled_date',
    'for_interview': 'for_interview_date',
    'psych_test': 'psych_test_date',
    'hired': 'hired_date',
    'failed': 'failed_date',
}

REQUIRED_STATUS_DATES = {
    'demo_scheduled',
    'for_interview',
    'psych_test',
}


def _get_next_status(current_status: str):
    values = [value for value, _label in STEPPER_STATUSES]
    try:
        idx = values.index(current_status)
    except ValueError:
        return None
    if idx + 1 >= len(values):
        return None
    return values[idx + 1]


def _get_status_date(applicant: Applicant, status_value: str):
    field_name = STEPPER_DATE_FIELDS.get(status_value)
    if not field_name:
        return None
    return getattr(applicant, field_name, None)


def _parse_input_date(date_raw: str):
    if not date_raw:
        return None
    return datetime.datetime.strptime(date_raw, "%Y-%m-%d").date()

@admin_required
def applicant_detail_view(request, uuid):
    applicant = get_object_or_404(Applicant, uuid=uuid)
    documents = ApplicantDocument.objects.filter(applicant=applicant, is_archived=False)

    status_labels = dict(STEPPER_STATUSES)
    current_status_label = status_labels.get(applicant.status, applicant.status)
    current_status_date = _get_status_date(applicant, applicant.status)
    can_reschedule_current_step = bool(STEPPER_DATE_FIELDS.get(applicant.status))

    next_status = _get_next_status(applicant.status)
    transition_choices = []
    if next_status:
        transition_choices.append((next_status, status_labels.get(next_status, next_status)))

    next_status_requires_date = bool(next_status and next_status in REQUIRED_STATUS_DATES)

    if request.method == "POST":
        action = (request.POST.get("action") or "advance").strip()

        if action == "reschedule":
            if not can_reschedule_current_step:
                messages.error(request, "Current step has no schedulable date.")
                return redirect('adminhub:applicant_detail', uuid=applicant.uuid)

            reschedule_date_raw = (request.POST.get("reschedule_date") or "").strip()
            if not reschedule_date_raw:
                messages.error(request, "Please provide a new date to reschedule.")
                return redirect('adminhub:applicant_detail', uuid=applicant.uuid)

            try:
                reschedule_date = _parse_input_date(reschedule_date_raw)
            except ValueError:
                messages.error(request, "Invalid reschedule date format. Please use YYYY-MM-DD.")
                return redirect('adminhub:applicant_detail', uuid=applicant.uuid)

            with transaction.atomic():
                current_date_field = STEPPER_DATE_FIELDS[applicant.status]
                setattr(applicant, current_date_field, reschedule_date)
                applicant.save(update_fields=[current_date_field])
                send_applicant_status_rescheduled_email(applicant, current_status_label, reschedule_date)
                messages.success(request, "Step date rescheduled and applicant notified.")

            return redirect('adminhub:applicant_detail', uuid=applicant.uuid)

        else:
            new_status = (request.POST.get("status") or "").strip()
            status_date_raw = (request.POST.get("status_date") or "").strip()

            if not new_status:
                messages.warning(request, "Please choose a status.")
            elif new_status == applicant.status:
                messages.warning(request, "No status change detected.")
            elif new_status != next_status:
                messages.error(request, "You can only move to the next immediate step.")
            else:
                status_date = None
                if status_date_raw:
                    try:
                        status_date = _parse_input_date(status_date_raw)
                    except ValueError:
                        messages.error(request, "Invalid date format. Please use YYYY-MM-DD.")
                        return redirect('adminhub:applicant_detail', uuid=applicant.uuid)

                if new_status in REQUIRED_STATUS_DATES and not status_date:
                    messages.error(request, "A date is required for this step.")
                else:
                    with transaction.atomic():
                        update_fields = ['status']
                        applicant.status = new_status

                        status_date_field = STEPPER_DATE_FIELDS.get(new_status)
                        if status_date_field and status_date:
                            setattr(applicant, status_date_field, status_date)
                            update_fields.append(status_date_field)

                        applicant.save(update_fields=update_fields)
                        send_applicant_status_email(applicant, new_status, status_date=status_date)
                        messages.success(request, "Status updated.")
                    return redirect('adminhub:applicant_detail', uuid=applicant.uuid)

    # For stepper: build steps with current progress
    status_values = [value for value, _label in STEPPER_STATUSES]
    try:
        current_idx = status_values.index(applicant.status)
    except ValueError:
        current_idx = -1

    stepper = []
    for idx, (value, label) in enumerate(STEPPER_STATUSES):
        is_active = applicant.status == value
        step_date = _get_status_date(applicant, value)
        if value == 'pending':
            step_date = applicant.created_at.date()

        stepper.append({
            "value": value,
            "label": label,
            "completed": idx < current_idx,
            "active": is_active,
            "date": step_date,
        })

    return render(request, 'admin/admin_applicant_detail.html', {
        'applicant': applicant,
        'documents': documents,
        'current_status_label': current_status_label,
        'current_status_date': current_status_date,
        'can_reschedule_current_step': can_reschedule_current_step,
        'transition_choices': transition_choices,
        'next_status': next_status,
        'next_status_requires_date': next_status_requires_date,
        'stepper': stepper,
    })




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


@admin_required
def download_applicant_document(request, pk):
    """
    Streams or returns bytes for an applicant document stored on Google Drive.
    Uses pk (ApplicantDocument primary key).
    Query param inline=1 requests inline preview (only honored for PDF/images).
    """
    doc = get_object_or_404(ApplicantDocument, pk=pk)
    file_id = doc.google_drive_id

    drive = CentralGoogleDriveService()
    want_inline = request.GET.get('inline', '0').lower() in ('1', 'true', 'yes')

    # Get metadata
    try:
        meta = drive.service.files().get(fileId=file_id, fields='mimeType, name, size').execute()
        mime_type = meta.get('mimeType')
        name_on_drive = meta.get('name') or doc.document_category.name or f'document_{doc.id}'
    except Exception:
        raise Http404("Could not retrieve file metadata from Google Drive.")

    def _finalize_response(resp: HttpResponse):
        resp['X-Frame-Options'] = 'SAMEORIGIN'
        resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    # Google-native types -> export to PDF
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


@admin_required
@require_POST
def change_applicant_document_status(request, pk):
    """
    Change status (Pending / Approved / Rejected) of an applicant document via AJAX.
    """
    doc = get_object_or_404(ApplicantDocument, pk=pk)

    new_status = request.POST.get('status')
    remarks = request.POST.get('remarks', '')

    if new_status not in ['Approved', 'Rejected', 'Pending']:
        return JsonResponse({"error": "Invalid status"}, status=400)

    if doc.is_archived:
        return JsonResponse({"error": "Archived documents cannot be updated."}, status=400)

    with transaction.atomic():
        doc.status = new_status
        doc.admin_remarks = remarks
        doc.save(update_fields=['status', 'admin_remarks'])

    return JsonResponse({
        "success": True,
        "status": doc.status,
        "admin_remarks": doc.admin_remarks or "",
    })







@admin_required
def account_creation_view(request):
    hired_applicants = Applicant.objects.filter(
        status='hired', account_created=False
    ).order_by('last_name', 'first_name')

    employment_statuses = EmploymentStatus.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        selected_uuids = request.POST.getlist('selected')
        status_id = request.POST.get('employment_status')
        errors = []
        created = []

        if not status_id:
            messages.error(request, "Employment status is required.")
            return redirect('adminhub:account_creation')

        try:
            emp_status = EmploymentStatus.objects.get(pk=status_id)
        except EmploymentStatus.DoesNotExist:
            messages.error(request, "Selected employment status does not exist.")
            return redirect('adminhub:account_creation')

        for applicant_uuid in selected_uuids:
            email = request.POST.get(f'faculty_email_{applicant_uuid}', '').strip()
            password = request.POST.get(f'faculty_password_{applicant_uuid}', '').strip()
            if not email:
                errors.append(f"Applicant {applicant_uuid}: Faculty email is required.")
                continue
            if Account.objects.filter(email=email).exists():
                errors.append(f"{email}: Email already exists.")
                continue
            if not password:
                password = get_random_string(8)
            try:
                with transaction.atomic():
                    applicant = Applicant.objects.get(uuid=applicant_uuid)
                    account = Account.objects.create_user(
                        email=email,
                        password=password,
                        role='faculty'
                    )
                    faculty = FacultyProfile.objects.create(
                        account=account,
                        name=f"{applicant.first_name} {applicant.last_name}",
                        department=getattr(applicant, "department", ""),
                        birth_date=applicant.birth_date,
                        contact_number=applicant.contact_number,
                        status=emp_status,
                    )
                    # Create Drive folder for the faculty
                    try:
                        drive = CentralGoogleDriveService()
                        folder_id = drive.create_faculty_folder(faculty)
                        faculty.gdrive_folder_id = folder_id
                        faculty.save()
                    except Exception as e:
                        errors.append(f"{email}: Drive folder error: {e}")
                    # Copy applicant docs to faculty and Drive
                    for doc in ApplicantDocument.objects.filter(applicant=applicant):
                        doc_name = f"{applicant.first_name} {applicant.last_name}"
                        if applicant.suffix:
                            doc_name += f" {applicant.suffix}"
                        doc_name += f" - {doc.document_category.name}"
                        try:
                            # Copy the file in Google Drive from applicant to faculty folder
                            new_file_id, new_file_link = drive.copy_file_to_folder(
                                doc.google_drive_id,
                                folder_id,
                                new_name=doc_name
                            )
                        except Exception as e:
                            errors.append(f"{email}: Failed to copy file for document '{doc_name}': {e}")
                            continue  # skip this doc but process others
                        FacultyDocument.objects.create(
                            faculty=faculty,
                            document_name=doc_name,
                            document_category=doc.document_category,
                            file_path=new_file_link,
                            google_drive_id=new_file_id,
                            file_size=doc.file_size,
                            expiry_date=doc.expiry_date,
                            status=doc.status,
                            admin_remarks=doc.admin_remarks,
                            # uploaded_by is skipped (nullable)
                        )
                    # Mark applicant as converted
                    applicant.account_created = True
                    applicant.save()
                    # Log created account
                    CreatedAccountLog.objects.create(
                        faculty_email=email,
                        password=password,
                        applicant=applicant,
                        applicant_name=f"{applicant.first_name} {applicant.last_name}",
                        applicant_email=applicant.email,
                        applicant_id_snapshot=applicant.applicant_id
                    )
                    # Email notification to old applicant email
                    send_mail(
                        subject="[FEMS] Your Faculty Account Has Been Created",
                        message=(
                            f"Hello {applicant.first_name},\n\n"
                            f"Your faculty account has been created.\n"
                            f"Login Email: {email}\n"
                            f"Temporary Password: {password}\n\n"
                            "Please log in and change your password immediately. "
                            "If you have any questions, contact the admin.\n\n"
                            "This is an automated message from FEMS."
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[applicant.email],
                        fail_silently=True,
                    )
                    created.append(email)
            except Exception as e:
                errors.append(f"{email}: {str(e)}")

        if created:
            messages.success(request, f"✅ Created accounts: {', '.join(created)}")
        if errors:
            for err in errors:
                messages.error(request, f"❌ {err}")
        return redirect('adminhub:account_creation')

    return render(request, 'admin/admin_account_creation.html', {
        'hired_applicants': hired_applicants,
        'employment_statuses': employment_statuses
    })





@admin_required
def created_account_log_view(request):
    logs = CreatedAccountLog.objects.select_related("applicant").order_by("-created_at")
    return render(request, "admin/admin_account_creation_log.html", {
        "logs": logs
    })



@admin_required
def attendance_logs_view(request):
    faculty_id = request.GET.get('faculty_id')
    month = int(request.GET.get('month', timezone.now().month))
    year = int(request.GET.get('year', timezone.now().year))

    faculties = FacultyProfile.objects.all().order_by('name')
    logs_qs = AttendanceLog.objects.select_related("faculty").order_by("-date", "-time_in")

    if faculty_id:
        logs_qs = logs_qs.filter(faculty__uuid=faculty_id)
    if month:
        logs_qs = logs_qs.filter(date__month=month)
    if year:
        logs_qs = logs_qs.filter(date__year=year)

    # Pagination
    paginator = Paginator(logs_qs, 20)  # 20 logs per page (adjust as needed)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Querystring without 'page'
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "logs": [format_log(log) for log in page_obj.object_list],
        "faculties": faculties,
        "selected_faculty_id": faculty_id if faculty_id else None,
        "selected_month": month,
        "selected_year": year,
        "month_range": [(i, calendar.month_name[i]) for i in range(1, 13)],
        "years": range(2020, timezone.now().year + 2),
        "querystring": querystring,
        "logs_total": logs_qs.count(),
    }
    return render(request, "admin/admin_attendance_logs.html", context)





def normalize_uid_from_admin(rfid_uid_raw: str):
    """
    Normalize an RFID UID string from the admin form to match ESP32's UID.

    It handles two cases:
    - USB reader outputs DECIMAL (e.g. '3828859619'): convert to 4-byte int,
      reverse bytes, return hex (e.g. '4773C366').
    - On confirm POST, the form may contain HEX we already normalized
      (e.g. '4773C366'): accept it as canonical and return uppercase hex.

    For 4-byte UIDs.
    """
    if not rfid_uid_raw:
        return None

    cleaned = rfid_uid_raw.strip()
    if not cleaned:
        return None

    # Case 1: purely decimal (first POST from USB reader)
    if cleaned.isdigit():
        try:
            value = int(cleaned)
        except ValueError:
            return None

        try:
            # interpret as 4-byte big-endian
            usb_bytes = value.to_bytes(4, byteorder='big', signed=False)
        except OverflowError:
            # not a 32-bit value
            return None

        # reverse bytes to match ESP32
        esp32_bytes = usb_bytes[::-1]
        return esp32_bytes.hex().upper()

    # Case 2: looks like hex (confirm POST or someone typed hex)
    cleaned_no_space = "".join(cleaned.split())
    if all(c in "0123456789ABCDEFabcdef" for c in cleaned_no_space):
        # accept as canonical hex; just uppercase
        return cleaned_no_space.upper()

    # Otherwise invalid
    return None



@admin_required
def pair_rfid(request):
    faculties_qs = FacultyProfile.objects.all().order_by('-created_at')
    rfid_map = {tag.faculty_id: tag.uid for tag in RFIDTag.objects.exclude(faculty=None).filter(is_active=True)}
    faculties = []
    newest_faculty = faculties_qs.first() if faculties_qs else None

    for f in faculties_qs:
        pk = f.pk
        is_unpaired = pk not in rfid_map
        is_new = newest_faculty and (f.pk == newest_faculty.pk)
        faculties.append({
            "uuid": str(f.uuid),
            "pk": pk,
            "name": f.name,
            "is_new": is_new,
            "is_unpaired": is_unpaired,
        })

    faculties.sort(
        key=lambda x: (
            not x['is_new'],
            not x['is_unpaired'],
            x['name'].lower(),
        )
    )

    message = None
    message_class = ""
    show_confirm_modal = False
    confirm_context = {}

    if request.method == 'POST':
        faculty_id = request.POST.get('faculty_id')
        rfid_uid_raw = request.POST.get('rfid_uid', '')


        normalized_uid = normalize_uid_from_admin(rfid_uid_raw)

        confirm_pair = request.POST.get('confirm_pair')

        faculty = next((f for f in faculties if f['uuid'] == faculty_id), None)

        # --- VALIDATION: Check errors first ---
        if not (faculty_id and rfid_uid_raw):
            message = "Faculty and RFID UID are required."
            message_class = "bg-red-100 text-red-800"
        elif normalized_uid is None:
            message = f"Invalid UID format: {rfid_uid_raw!r}. Only hex or decimal digits are allowed."
            message_class = "bg-red-100 text-red-800"
        elif not faculty:
            message = "Faculty not found."
            message_class = "bg-red-100 text-red-800"
        else:
            try:
                with transaction.atomic():
                    faculty_obj = FacultyProfile.objects.get(pk=faculty['pk'])

                    # Use normalized UID (canonical hex) for DB
                    rfid_uid = normalized_uid
                    tag, created = RFIDTag.objects.get_or_create(uid=rfid_uid)

                    # Block if this RFID is already active for another faculty
                    if tag.faculty and tag.faculty != faculty_obj and tag.is_active:
                        message = (
                            f"RFID <b>{rfid_uid}</b> is already actively paired to "
                            f"<b>{tag.faculty.name}</b>. Unpair it there before pairing it here."
                        )
                        message_class = "bg-red-100 text-red-800"

                    # --- PASSED VALIDATION: Ready for confirmation modal ---
                    else:
                        existing_active = RFIDTag.objects.filter(
                            faculty=faculty_obj, is_active=True
                        ).exclude(uid=rfid_uid).first()
                        if not confirm_pair:
                            show_confirm_modal = True
                            confirm_context = {
                                'faculty_id': faculty_id,
                                'faculty_name': faculty_obj.name,
                                # Show canonical hex in confirm modal
                                'rfid_uid': rfid_uid,
                                'has_previous': bool(existing_active),
                                'prev_uid': existing_active.uid if existing_active else None,
                            }
                        else:
                            # Actually execute pairing
                            RFIDTag.objects.filter(
                                faculty=faculty_obj, is_active=True
                            ).exclude(uid=rfid_uid).update(is_active=False)
                            tag.faculty = faculty_obj
                            tag.is_active = True
                            tag.save()
                            rfid_map[faculty_obj.pk] = tag.uid
                            if created or not tag.is_active:
                                message = (
                                    f"RFID <b>{rfid_uid}</b> successfully paired to "
                                    f"<b>{faculty_obj.name}</b>!"
                                )
                            else:
                                message = (
                                    f"RFID <b>{rfid_uid}</b> is now set as the active card for "
                                    f"<b>{faculty_obj.name}</b>."
                                )
                            message_class = "bg-green-100 text-green-800"
            except Exception as exc:
                message = f"An unexpected error occurred: {exc}"
                message_class = "bg-red-100 text-red-800"

    return render(request, 'admin/admin_pair_rfid.html', {
        'faculties': faculties,
        'rfid_map': rfid_map,
        'message': message,
        'message_class': message_class,
        'show_confirm_modal': show_confirm_modal,
        'confirm_context': confirm_context,
    })



def rfid_pairing_tap_api(request):
    uid = cache.get('last_rfid_uid')
    return JsonResponse({"uid": uid if uid else ""})








@admin_required
def manual_attendance_log_view(request):
    faculties_qs = FacultyProfile.objects.all().order_by('name')
    faculties = [
        {'uuid': str(faculty.uuid), 'name': faculty.name, 'pk': faculty.pk}
        for faculty in faculties_qs
    ]
    rfid_map = {str(tag.faculty.uuid): tag.uid for tag in RFIDTag.objects.select_related("faculty") if tag.faculty_id}

    message = ""
    message_class = ""
    initial = {
        'date': timezone.localdate()
    }

    if request.method == "POST":
        faculty_id = request.POST.get('faculty', None)
        faculty_obj = FacultyProfile.objects.filter(pk=faculty_id).first() if faculty_id else None
        form = ManualAttendanceLogForm(request.POST, faculty=faculty_obj)
        if form.is_valid():
            cleaned = form.cleaned_data
            attendance = form.save(commit=False)
            date = cleaned['date']
            time_in = cleaned['time_in']
            time_out = cleaned['time_out']
            tz = timezone.get_current_timezone()
            attendance.time_in = datetime.datetime.combine(date, time_in, tzinfo=tz)
            attendance.time_out = datetime.datetime.combine(date, time_out, tzinfo=tz)
            attendance.uid = request.POST.get('uid', '')  # capture UID if present (adjust as needed)
            attendance.is_manual = True                   # <-- SET MANUAL FLAG
            attendance.save()
            form.save_m2m()
            messages.success(request, "Attendance log created successfully.")
            return redirect(reverse('adminhub:attendance_logs'))
        else:
            # --- Error formatting: no '__all__' or keys, clear user output ---
            error_msgs = []
            # Non-field errors
            for error in form.non_field_errors():
                error_msgs.append(f"{error}")
            # Field errors
            for field in form:
                for error in field.errors:
                    error_msgs.append(f"{field.label}: {error}")
            message = "<br>".join(error_msgs)
            message_class = "bg-red-100 text-red-800"
            initial.update({
                'faculty': request.POST.get('faculty', ''),
                'uid': request.POST.get('uid', ''),
                'date': request.POST.get('date', ''),
                'time_in': request.POST.get('time_in', ''),
                'time_out': request.POST.get('time_out', ''),
            })
    else:
        form = ManualAttendanceLogForm(initial={'date': timezone.localdate()})

    # Get all assignments for all faculties for the active semester
    active_sem = Semester.objects.filter(is_active=True).first()
    teaching_assignments = []
    if active_sem:
        tas = TeachingAssignment.objects.filter(semester=active_sem).select_related("faculty")
        for ta in tas:
            start_12 = ta.start_time.strftime('%I:%M %p').lstrip('0')
            end_12 = ta.end_time.strftime('%I:%M %p').lstrip('0')
            display = (
                f"{ta.faculty} - {ta.subject_code} ({ta.get_day_of_week_display()} {start_12} - {end_12}"
            )
            if ta.room:
                display += f" - {ta.room}"
            display += ")"
            teaching_assignments.append({
                'id': ta.id,
                'faculty_pk': str(ta.faculty.pk),
                'subject_code': ta.subject_code,
                'subject_description': ta.subject_description,
                'year_section': ta.year_section,
                'start_time': ta.start_time.strftime('%H:%M'),
                'end_time': ta.end_time.strftime('%H:%M'),
                'day_of_week': ta.day_of_week,
                'room': ta.room,
                'display': display,
            })

    return render(request, 'admin/admin_manual_attendance_log.html', {
        'faculties': faculties,
        'rfid_map': rfid_map,
        'teaching_assignments': teaching_assignments,
        'message': message,
        'message_class': message_class,
        **initial,
    })




@admin_required
def teaching_assignment_view(request):
    search_query = request.GET.get('search', '').strip()
    faculty_qs = FacultyProfile.objects.all()
    if search_query:
        faculty_qs = faculty_qs.filter(
            Q(name__icontains=search_query) | Q(account__email__icontains=search_query)
        )
    paginator = Paginator(faculty_qs, 15)  # Show 15 per page
    page_number = request.GET.get('page')
    faculty_list = paginator.get_page(page_number)
    return render(request, 'admin/admin_teaching_assignments.html', {
        'faculty_list': faculty_list,
        'paginator': paginator,
        'page_obj': faculty_list,
    })




@admin_required
def teaching_assignment_list(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    assignments = TeachingAssignment.objects.filter(faculty=faculty)
    return render(request, 'admin/admin_faculty_teaching_assignment.html', {'faculty': faculty, 'assignments': assignments})




logger = logging.getLogger(__name__)
SESSION_KEY = 'ta_bulk_upload_rows'

# (Upload view unchanged)
@admin_required
def teaching_assignment_bulk_upload(request):
    form = TeachingAssignmentBulkUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        logger.debug("Bulk upload POST: FILES keys=%s", list(request.FILES.keys()))
        uploaded_files = request.FILES.getlist('files')

        if not uploaded_files:
            form.add_error(None, "No files uploaded. Please select one or more files.")
        else:
            all_rows = []
            errors = []
            for f in uploaded_files:
                name = f.name.lower()
                if not (name.endswith('.csv') or name.endswith('.xls') or name.endswith('.xlsx')):
                    errors.append(f"Unsupported file type: {f.name}")
                    continue
                try:
                    rows = read_file_to_rows(f)
                    all_rows.extend(rows)
                except Exception as e:
                    logger.exception("Error reading upload file %s", f.name)
                    errors.append(f"{f.name}: {e}")

            for e in errors:
                messages.error(request, e)

            if not all_rows:
                messages.error(request, _("No valid rows parsed from uploaded file(s). Please check the file(s) and the required columns."))
            else:
                for row in all_rows:
                    row['default_faculty_uuid'] = None
                    name = (row.get('faculty_name') or '').strip()
                    if name:
                        f_obj = (FacultyProfile.objects.filter(name__iexact=name).first()
                                 or FacultyProfile.objects.filter(name__icontains=name).first())
                        if f_obj:
                            row['default_faculty_uuid'] = str(f_obj.uuid)

                request.session[SESSION_KEY] = all_rows
                request.session.modified = True
                messages.success(request, _(f"Parsed {len(all_rows)} rows from uploaded file(s). Please review and assign faculty on the next page."))
                return redirect('adminhub:teaching_assignment_bulk_confirm')

    return render(request, 'admin/admin_teaching_assignment_upload.html', {'form': form})


def clean_uuid_string(s: str) -> str:
    """
    Clean a posted UUID-like string that may contain surrounding quotes,
    curly quotes, or literal backslash-unicode escapes like '\\u002D'.
    Returns a cleaned plain ASCII UUID string (with hyphens) if possible.
    """
    if not s:
        return s
    if not isinstance(s, str):
        s = str(s)

    # Replace common Unicode curly quotes with straight quotes
    s = s.replace('\u201c', '"').replace('\u201d', '"').replace('\u2018', "'").replace('\u2019', "'")

    # If the string contains literal backslash-u sequences (e.g. "\\u002D"),
    # decode those escape sequences to actual characters.
    if '\\u' in s or '\\x' in s:
        try:
            s = bytes(s, 'utf-8').decode('unicode_escape')
        except Exception:
            pass

    # Strip whitespace
    s = s.strip()

    # Remove surrounding straight or curly quotes if present
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    if (s.startswith('“') and s.endswith('”')) or (s.startswith('‘') and s.endswith('’')):
        s = s[1:-1].strip()

    return s


@admin_required
def teaching_assignment_bulk_confirm(request):
    original_rows = request.session.get(SESSION_KEY)
    if not original_rows:
        messages.error(request, gettext_func("No parsed upload data found. Please upload files first."))
        return redirect('adminhub:teaching_assignment_bulk_upload')

    # Build UI lists and JSON payloads
    faculty_list = get_all_faculty_list()
    semester_list = get_all_semesters()

    def normalize_faculties(fac_list):
        out = []
        for f in fac_list:
            if isinstance(f, dict):
                uuid = f.get('uuid') or f.get('id') or ''
                display = f.get('display') or f.get('name') or f.get('label') or ''
            else:
                uuid = getattr(f, 'uuid', '') or getattr(f, 'id', '')
                display = getattr(f, 'display', '') or getattr(f, 'name', '')
            out.append({'uuid': str(uuid), 'display': display})
        return out

    def normalize_semesters(s_list):
        out = []
        for s in s_list:
            if isinstance(s, dict):
                sid = s.get('id') or s.get('pk') or ''
                display = s.get('display') or s.get('name') or ''
            else:
                sid = getattr(s, 'id', '')
                display = getattr(s, 'display', '') or getattr(s, 'name', '')
            out.append({'id': sid, 'display': display})
        return out

    faculty_list_norm = normalize_faculties(faculty_list)
    semester_list_norm = normalize_semesters(semester_list)
    faculty_list_json = json.dumps(faculty_list_norm)
    semester_list_json = json.dumps(semester_list_norm)

    active_sem = Semester.objects.filter(is_active=True).order_by('-academic_year__year_start').first()

    def parse_time_string(value):
        v = (value or '').strip()
        if not v:
            return None
        try:
            parts = v.split(':')
            if len(parts) == 2:
                h, m = int(parts[0]), int(parts[1])
                return datetime.time(hour=h, minute=m)
            elif len(parts) >= 3:
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime.time(hour=h, minute=m, second=s)
        except Exception:
            pass
        try:
            return datetime.time.fromisoformat(v)
        except Exception:
            return None

    def db_overlap_exists(faculty, semester, day_of_week, start_time, end_time):
        return TeachingAssignment.objects.filter(
            faculty=faculty,
            semester=semester,
            day_of_week=day_of_week,
            start_time__lt=end_time,
            end_time__gt=start_time
        ).exists()

    if request.method == 'POST':
        # Determine submitted row indexes from POST keys (supports user-added rows)
        submitted_indexes = set()
        idx_re = re.compile(r'_(\d+)$')
        for key in request.POST.keys():
            m = idx_re.search(key)
            if m:
                try:
                    submitted_indexes.add(int(m.group(1)))
                except Exception:
                    pass
        # Fallback: if none found, use original rows indices
        if not submitted_indexes:
            submitted_indexes = set(range(len(original_rows)))

        # If user removed all rows, handle that early (consider only submitted indexes)
        included_any = False
        for idx in sorted(submitted_indexes):
            if request.POST.get(f'include_{idx}', '1') == '1':
                included_any = True
                break
        if not included_any:
            try:
                del request.session[SESSION_KEY]
            except KeyError:
                pass
            messages.info(request, gettext_func("No rows selected; upload cancelled."))
            return redirect('adminhub:teaching_assignment_bulk_upload')

        enriched = []
        batch_index = {}

        # First pass: parse and basic validation; respect include_{idx} flag
        for idx in sorted(submitted_indexes):
            include_flag = request.POST.get(f'include_{idx}', '1')
            # merge with original row if exists
            original = original_rows[idx] if (isinstance(original_rows, (list, tuple)) and idx < len(original_rows)) else {}
            row_num = original.get('row_num') or (idx + 1)

            # If removed, preserve values for display but mark removed
            if include_flag != '1':
                raw_faculty_choice = request.POST.get(f'assign_{idx}', '') or original.get('default_faculty_uuid') or ''
                cleaned_faculty_choice = clean_uuid_string(raw_faculty_choice)
                enriched.append({
                    'row_num': row_num,
                    'index': idx,
                    'removed': True,
                    'errors': [],
                    'subject_code': request.POST.get(f'subject_code_{idx}', '') or original.get('subject_code', '') or '',
                    'subject_description': request.POST.get(f'subject_description_{idx}', '') or original.get('subject_description', '') or '',
                    'year_section': request.POST.get(f'year_section_{idx}', '') or original.get('year_section', '') or '',
                    'day_of_week': request.POST.get(f'day_{idx}', '') or original.get('day_of_week', '') or '',
                    'start_raw': request.POST.get(f'start_time_{idx}', '') or (original.get('start_time') or ''),
                    'end_raw': request.POST.get(f'end_time_{idx}', '') or (original.get('end_time') or ''),
                    'room': request.POST.get(f'room_{idx}', '') or (original.get('room') or ''),
                    'faculty_choice': cleaned_faculty_choice,
                    'semester_choice': request.POST.get(f'semester_{idx}', '') or original.get('semester_id') or '',
                    'faculty_uuid': cleaned_faculty_choice,
                    'semester_id': (request.POST.get(f'semester_{idx}', '') or original.get('semester_id') or ''),
                    'start_time': None,
                    'end_time': None,
                    'faculty_obj': None,
                    'semester_obj': None,
                })
                continue

            # included row - validate; read POST first then fallback to original
            data = {
                'row_num': row_num,
                'index': idx,
                'original': original,
                'errors': [],
                'removed': False,
                'faculty_uuid': None,
                'semester_id': None,
                'subject_code': (request.POST.get(f'subject_code_{idx}', '') or original.get('subject_code', '') or '').strip(),
                'subject_description': (request.POST.get(f'subject_description_{idx}', '') or original.get('subject_description', '') or '').strip(),
                'year_section': (request.POST.get(f'year_section_{idx}', '') or original.get('year_section', '') or '').strip(),
                'day_of_week': (request.POST.get(f'day_{idx}', '') or original.get('day_of_week', '') or '').strip(),
                'start_raw': request.POST.get(f'start_time_{idx}', '') or (original.get('start_time') or ''),
                'end_raw': request.POST.get(f'end_time_{idx}', '') or (original.get('end_time') or ''),
                'room': request.POST.get(f'room_{idx}', '') or (original.get('room') or ''),
                'faculty_choice': request.POST.get(f'assign_{idx}', '') or original.get('default_faculty_uuid') or '',
                'semester_choice': request.POST.get(f'semester_{idx}', '') or original.get('semester_id') or '',
                'start_time': None,
                'end_time': None,
                'faculty_obj': None,
                'semester_obj': None,
            }

            # Resolve faculty (sanitize posted value first)
            raw_choice = data.get('faculty_choice', '') or ''
            clean_choice = clean_uuid_string(raw_choice)
            data['faculty_choice'] = clean_choice

            if clean_choice in ('', 'skip'):
                data['errors'].append("Faculty is required.")
            else:
                try:
                    # Attempt lookup safely; catch validation errors raised when field expects UUID
                    try:
                        f_obj = FacultyProfile.objects.get(uuid=clean_choice)
                    except (ValueError, TypeError, DjangoValidationError):
                        f_obj = None

                    if f_obj is None:
                        # tolerant fallback by stripping unusual characters
                        alt = clean_choice.replace('\u2013', '-').replace('\u2014', '-').strip(' "\'')
                        if alt and alt != clean_choice:
                            try:
                                f_obj = FacultyProfile.objects.get(uuid=alt)
                            except Exception:
                                f_obj = None

                    if f_obj is None:
                        raise FacultyProfile.DoesNotExist()

                    data['faculty_obj'] = f_obj
                    data['faculty_uuid'] = str(f_obj.uuid)
                    data['faculty_choice'] = str(f_obj.uuid)
                except FacultyProfile.DoesNotExist:
                    data['errors'].append("Selected faculty not found.")

            # Resolve semester
            if not data['semester_choice']:
                data['errors'].append("Semester is required.")
            else:
                try:
                    sem_obj = Semester.objects.get(id=int(data['semester_choice']))
                    data['semester_obj'] = sem_obj
                    data['semester_id'] = sem_obj.id
                except Exception:
                    data['errors'].append("Selected semester not found.")

            # Times parsing
            start_t = parse_time_string(data['start_raw'])
            end_t = parse_time_string(data['end_raw'])
            data['start_time'] = start_t
            data['end_time'] = end_t

            if data['start_raw'] and not start_t:
                data['errors'].append("Invalid Start Time format.")
            if data['end_raw'] and not end_t:
                data['errors'].append("Invalid End Time format.")

            # Required fields besides faculty/semester/time
            if not data['subject_code']:
                data['errors'].append("Subject Code is required.")
            if not data['subject_description']:
                data['errors'].append("Subject Description is required.")
            if not data['year_section']:
                data['errors'].append("Year/Section is required.")
            if not data['day_of_week']:
                data['errors'].append("Day of Week is required.")
            if data['start_time'] and data['end_time'] and data['start_time'] >= data['end_time']:
                data['errors'].append("End Time must be after Start Time.")

            enriched.append(data)

        # Second pass: duplicate and DB-overlap detection for included & structurally valid rows
        for data in enriched:
            if data.get('removed') or data['errors']:
                continue
            f_obj = data['faculty_obj']
            sem_obj = data['semester_obj']
            day = data['day_of_week']
            st = data['start_time']
            et = data['end_time']

            duplicate_exists = TeachingAssignment.objects.filter(
                faculty=f_obj,
                subject_code__iexact=data['subject_code'],
                year_section__iexact=data['year_section'],
                day_of_week=day,
                start_time=st,
                end_time=et,
                semester=sem_obj
            ).exists()
            if duplicate_exists:
                data['errors'].append("Duplicate of an existing assignment (exact match).")
                continue

            if db_overlap_exists(f_obj, sem_obj, day, st, et):
                data['errors'].append(
                    f"Overlaps existing assignment ({st.strftime('%H:%M')}–{et.strftime('%H:%M')} {day})."
                )

        # Third pass: intra-batch overlaps (mark both rows)
        for data in enriched:
            if data.get('removed') or data['errors']:
                continue
            key = (data['faculty_obj'].id, data['semester_obj'].id, data['day_of_week'])
            batch_index.setdefault(key, []).append(data)

        for key, rows_group in batch_index.items():
            rows_group.sort(key=lambda r: r['start_time'])
            for i in range(len(rows_group)):
                for j in range(i + 1, len(rows_group)):
                    r1 = rows_group[i]
                    r2 = rows_group[j]
                    if r1['start_time'] < r2['end_time'] and r1['end_time'] > r2['start_time']:
                        msg1 = (
                            f"Overlaps row {r2['row_num']} ({r2['start_time'].strftime('%H:%M')}–{r2['end_time'].strftime('%H:%M')} {r2['day_of_week']})."
                        )
                        msg2 = (
                            f"Overlaps row {r1['row_num']} ({r1['start_time'].strftime('%H:%M')}–{r1['end_time'].strftime('%H:%M')} {r1['day_of_week']})."
                        )
                        r1['errors'].append(msg1)
                        r2['errors'].append(msg2)

        any_errors = any(d['errors'] for d in enriched if not d.get('removed'))
        if any_errors:
            # Re-render with enriched rows and inline errors; always pass the JSON and normalized lists
            return render(
                request,
                'admin/admin_teaching_assignment_upload_confirm.html',
                {
                    'rows': enriched,
                    'faculty_list': faculty_list_norm,
                    'semester_list': semester_list_norm,
                    'faculty_list_json': faculty_list_json,
                    'semester_list_json': semester_list_json,
                    'has_errors': True,
                }
            )

        # No errors: create only included rows (skip removed)
        to_create = []
        for data in enriched:
            if data.get('removed'):
                continue
            ta = TeachingAssignment(
                faculty=data['faculty_obj'],
                subject_code=data['subject_code'],
                subject_description=data['subject_description'],
                year_section=data['year_section'],
                day_of_week=data['day_of_week'],
                start_time=data['start_time'],
                end_time=data['end_time'],
                semester=data['semester_obj'],
                room=(data['room'].strip() or None)
            )
            to_create.append(ta)

        try:
            TeachingAssignment.objects.bulk_create(to_create, batch_size=200)
        except Exception as e:
            # On DB error, re-render with general error and preserve rows for correction
            return render(
                request,
                'admin/admin_teaching_assignment_upload_confirm.html',
                {
                    'rows': enriched,
                    'faculty_list': faculty_list_norm,
                    'semester_list': semester_list_norm,
                    'faculty_list_json': faculty_list_json,
                    'semester_list_json': semester_list_json,
                    'has_errors': True,
                    'general_error': str(e),
                }
            )

        # Success: clear session and redirect
        try:
            del request.session[SESSION_KEY]
        except KeyError:
            pass

        messages.success(request, gettext_func(f"Successfully created {len(to_create)} teaching assignments."))
        return redirect('adminhub:teaching_assignment')

    # GET: build display rows for initial page render
    display_rows = []
    for idx, row in enumerate(original_rows):
        row_num = row.get('row_num') or (idx + 1)
        display_rows.append({
            'row_num': row_num,
            'index': idx,
            'errors': [],
            'removed': False,
            'subject_code': row.get('subject_code') or '',
            'subject_description': row.get('subject_description') or '',
            'year_section': row.get('year_section') or '',
            'day_of_week': row.get('day_of_week') or '',
            'start_raw': row.get('start_time') or '',
            'end_raw': row.get('end_time') or '',
            'room': row.get('room') or '',
            'faculty_uuid': row.get('default_faculty_uuid') or '',
            'semester_id': row.get('semester_id') or (active_sem.id if active_sem else ''),
            'faculty_choice': row.get('default_faculty_uuid') or '',
            'semester_choice': row.get('semester_id') or (active_sem.id if active_sem else ''),
        })

    return render(
        request,
        'admin/admin_teaching_assignment_upload_confirm.html',
        {
            'rows': display_rows,
            'faculty_list': faculty_list_norm,
            'semester_list': semester_list_norm,
            'faculty_list_json': faculty_list_json,
            'semester_list_json': semester_list_json,
            'has_errors': False,
        }
    )


@admin_required
def teaching_assignment_create(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    if request.method == 'POST':
        form = TeachingAssignmentForm(request.POST, faculty=faculty)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.faculty = faculty  # reinforce
            assignment.save()
            messages.success(request, "Teaching assignment created.")
            return redirect('adminhub:teaching_assignment_list', faculty_uuid=faculty.uuid)
    else:
        form = TeachingAssignmentForm(faculty=faculty)
    return render(request, 'admin/admin_teaching_assignment_create.html', {'form': form, 'faculty': faculty})


@admin_required
def teaching_assignment_update(request, faculty_uuid, pk):
    assignment = get_object_or_404(TeachingAssignment, pk=pk, faculty__uuid=faculty_uuid)
    if request.method == 'POST':
        form = TeachingAssignmentForm(request.POST, instance=assignment, faculty=assignment.faculty)
        if form.is_valid():
            form.save()
            messages.success(request, "Teaching assignment updated.")
            return redirect('adminhub:teaching_assignment_list', faculty_uuid=assignment.faculty.uuid)
    else:
        form = TeachingAssignmentForm(instance=assignment, faculty=assignment.faculty)
    return render(request, 'admin/admin_teaching_assignment_create.html', {'form': form, 'faculty': assignment.faculty})


@admin_required
def teaching_assignment_delete(request, faculty_uuid, pk):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    assignment = get_object_or_404(TeachingAssignment, pk=pk, faculty=faculty)

    if request.method == 'POST':
        assignment.delete()
        messages.success(request, f"Deleted assignment: {assignment.subject_code} – {assignment.subject_description}")
        return redirect('adminhub:teaching_assignment_list', faculty_uuid=faculty.uuid)

    messages.warning(request, "Deletion must be confirmed via modal.")
    return redirect('adminhub:teaching_assignment_list', faculty_uuid=faculty.uuid)





@admin_required
def dtr_tab_view(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    today = date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    day_of_week = request.GET.get('day', '')  # '' means show all

    # Get DTR data (per assignment per day)
    dtr = DTRCalculator.get_dtr_for_month(faculty, year, month)

    # Get all logs by date for the month
    from calendar import monthrange
    days_in_month = monthrange(year, month)[1]
    logs_by_date = {}
    for day_num in range(1, days_in_month + 1):
        current_date = date(year, month, day_num)
        logs_by_date[current_date] = list(
            AttendanceLog.objects.filter(faculty=faculty, date=current_date).order_by('time_in')
        )

    # Post-process DTR rows so every attendance log is shown, even unmatched ones
    for row in dtr:
        day_logs = logs_by_date.get(row['date'], [])
        assignment_status_logs = set(
            status['attendance_log'].id
            for status in row['statuses']
            if status['attendance_log']
        )
        # Add logs that aren't matched to any assignment
        for log in day_logs:
            if log.id not in assignment_status_logs:
                row['statuses'].append({
                    'assignment': None,
                    'attendance_log': log,
                    'status': 'has log',
                })
        # If there are logs but no assignment and no status yet, add a status for each log
        if not row['statuses'] and day_logs:
            for log in day_logs:
                row['statuses'].append({
                    'assignment': None,
                    'attendance_log': log,
                    'status': 'has log',
                })
        # If still no statuses (no assignment, no log), keep 'no assignment'
        elif not row['statuses']:
            row['statuses'].append({
                'assignment': None,
                'attendance_log': None,
                'status': 'no assignment',
            })

    # ==== Handle Filtering ====
    if day_of_week:
        dtr = [
            row for row in dtr
            if row['date'].strftime('%a').lower()[:3] == day_of_week
        ]

    # For year dropdown, show last 3 years and next year
    year_choices = [today.year-1, today.year, today.year+1]
    months = [(i, calendar.month_name[i]) for i in range(1, 13)]
    day_choices = [
        ('', 'All Days'), ('mon', 'Monday'), ('tue', 'Tuesday'), ('wed', 'Wednesday'),
        ('thu', 'Thursday'), ('fri', 'Friday'), ('sat', 'Saturday')
    ]

    # --- Modal form handling for edit and delete ---
    edit_errors = {}
    edit_old = {}

    if request.method == "POST":
        if 'edit_log_id' in request.POST:
            log_id = request.POST['edit_log_id']
            log = get_object_or_404(AttendanceLog, pk=log_id, faculty=faculty)
            form = DTRLogEditForm(request.POST, instance=log)
            if form.is_valid():
                form.save()
                from django.contrib import messages
                messages.success(request, "Attendance log updated.")
                return redirect(request.path + '?' + request.GET.urlencode())
            else:
                edit_errors[log_id] = {field: '; '.join([e for e in errs]) for field, errs in form.errors.items()}
                edit_old[log_id] = {
                    'time_in': request.POST.get('time_in', ''),
                    'time_out': request.POST.get('time_out', '')
                }
        elif 'delete_log_id' in request.POST:
            log_id = request.POST['delete_log_id']
            log = get_object_or_404(AttendanceLog, pk=log_id, faculty=faculty)
            log.delete()
            from django.contrib import messages
            messages.success(request, "Attendance log deleted.")
            return redirect(request.path + '?' + request.GET.urlencode())

    context = {
        'faculty': faculty,
        'dtr': dtr,
        'month': month,
        'year': year,
        'year_choices': year_choices,
        'months': months,
        'day_of_week': day_of_week,
        'day_choices': day_choices,
        'edit_errors': edit_errors,
        'edit_old': edit_old,
    }
    return render(request, 'admin/admin_dtr.html', context)







@admin_required
def admin_dtr_export_preview(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    today = date.today()
    months = [(i, calendar.month_name[i]) for i in range(1, 13)]
    year_choices = [today.year-1, today.year, today.year+1]

    # Get selected or current month/year
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    days_in_month = calendar.monthrange(year, month)[1]
    month_label = calendar.month_name[month]

    dtr = DTRCalculator.get_dtr_for_month(faculty, year, month)
    # Build rows: [{day, am_in, am_out, pm_in, pm_out}]
    rows = []
    for day_num in range(1, days_in_month + 1):
        am_in = am_out = pm_in = pm_out = ""
        logs = [status['attendance_log'] for status in dtr[day_num-1]['statuses'] if status['attendance_log']]
        if logs:
            log = logs[0]
            if log.time_in:
                t_in = localtime(log.time_in)
                if t_in.hour < 12:
                    am_in = t_in.strftime('%I:%M %p').lstrip('0')
                else:
                    pm_in = t_in.strftime('%I:%M %p').lstrip('0')
            if log.time_out:
                t_out = localtime(log.time_out)
                if t_out.hour < 12:
                    am_out = t_out.strftime('%I:%M %p').lstrip('0')
                else:
                    pm_out = t_out.strftime('%I:%M %p').lstrip('0')
        rows.append({
            'day': day_num,
            'am_in': am_in,
            'am_out': am_out,
            'pm_in': pm_in,
            'pm_out': pm_out,
        })

    total_working_hours = calculate_total_working_hours(rows)

    context = {
        'faculty': faculty,
        'month': month,
        'year': year,
        'month_label': month_label,
        'rows': rows,
        'months': months,
        'year_choices': year_choices,
        'status_label': faculty.status.name.upper() if getattr(faculty, "status", None) and getattr(faculty.status, "name", None) else "---",
        'total_working_hours': total_working_hours,
    }
    return render(request, 'admin/admin_dtr_export_preview.html', context)




@admin_required
def admin_dtr_export_view(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    today = date.today()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    days_in_month = calendar.monthrange(year, month)[1]
    month_label = calendar.month_name[month]

    dtr = DTRCalculator.get_dtr_for_month(faculty, year, month)
    rows = []
    for day_num in range(1, days_in_month + 1):
        am_in = am_out = pm_in = pm_out = ""
        logs = [status['attendance_log'] for status in dtr[day_num-1]['statuses'] if status['attendance_log']]
        if logs:
            log = logs[0]
            if log.time_in:
                t_in = localtime(log.time_in)
                if t_in.hour < 12:
                    am_in = t_in.strftime('%I:%M %p').lstrip('0')
                else:
                    pm_in = t_in.strftime('%I:%M %p').lstrip('0')
            if log.time_out:
                t_out = localtime(log.time_out)
                if t_out.hour < 12:
                    am_out = t_out.strftime('%I:%M %p').lstrip('0')
                else:
                    pm_out = t_out.strftime('%I:%M %p').lstrip('0')
        rows.append([str(day_num), am_in, am_out, pm_in, pm_out])

    rows_dicts = [{'am_in': am_in, 'am_out': am_out, 'pm_in': pm_in, 'pm_out': pm_out}
                  for (_, am_in, am_out, pm_in, pm_out) in rows]
    total_working_hours = calculate_total_working_hours(rows_dicts)
    status_label = faculty.status.name.upper() if getattr(faculty, "status", None) and getattr(faculty.status, "name", None) else "---"

    buffer = BytesIO()
    # MINIMUM margins (to maximize printable area)
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=0.7*cm, rightMargin=0.7*cm, topMargin=0.7*cm, bottomMargin=0.7*cm
    )
    width, height = A4
    styles = getSampleStyleSheet()
    # Used for table cells and header text (small, Arial/Helvetica, centered)
    cell_style = ParagraphStyle('cell', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, alignment=1, spaceAfter=0, spaceBefore=0)
    head_style = ParagraphStyle('head', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.3, alignment=1, spaceAfter=0, spaceBefore=0)
    document_title_style = ParagraphStyle('documenttitle',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=12,alignment=1,spaceAfter=0,spaceBefore=0,)
    bold_style = ParagraphStyle('boldcell', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.7, alignment=1, spaceAfter=0, spaceBefore=0)
    note_style = ParagraphStyle('note', parent=styles['Normal'], fontName='Helvetica', fontSize=7.3, alignment=1, textColor=colors.HexColor('#222'), leading=8.5)
    sign_style = ParagraphStyle('sign', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)
    small_left = ParagraphStyle('small_left', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=6.8, alignment=0, textColor=colors.HexColor('#888888'))

    # Table width calculation (uses nearly the full page, with small left col for "Day")
    avail_width = width - doc.leftMargin - doc.rightMargin
    w_day = 1.18*cm
    w_other = (avail_width-w_day)/4
    col_widths = [w_day, w_other, w_other, w_other, w_other]

    # Table data; HEADERS
    data = [
        [
            Paragraph('Civil Service Form No. 48', ParagraphStyle('left', fontName='Helvetica-Oblique', fontSize=9, alignment=0)),
            '', '', '', 
            Paragraph(status_label, ParagraphStyle('right', fontName='Helvetica-Oblique', fontSize=10, alignment=2))
        ],
        [
            Paragraph('<b>DAILY TIME RECORD</b>', document_title_style), '', '', '', ''
        ],
        [
            Paragraph(f"<b>{faculty.name.upper()}</b>", head_style), '', '', '', ''
        ],
        [
            Paragraph(f'For the month of <b>{month_label.upper()} {year}</b>', cell_style), '', '', '', ''
        ],
        [
            Paragraph(f'Official Hours Of: <b>{total_working_hours}</b>', cell_style), '', '', '', ''
        ],
        # Table top 2-row headers:
        [
            Paragraph('<b>Day</b>', head_style),
            Paragraph('<b>A.M.</b>', head_style), '',
            Paragraph('<b>P.M.</b>', head_style), ''
        ],
        [
            '', 
            Paragraph('<b>Arrival</b>', head_style), Paragraph('<b>Departure</b>', head_style),
            Paragraph('<b>Arrival</b>', head_style), Paragraph('<b>Departure</b>', head_style)
        ]
    ]
    # Add day rows:
    for row in rows:
        data.append([Paragraph(row[0], bold_style)] + [Paragraph(cell, cell_style) for cell in row[1:]])
    # Add total row:
    data.append([
        Paragraph('<b>TOTAL — Working Hours:</b>', bold_style), '', '', '',
        Paragraph(f"<b>{total_working_hours}</b>", bold_style)
    ])
    # Certification row, signature, verified (all placed inside table to prevent breaking)
    data.append([Paragraph(
        "I certify on my honor that the above is true and correct report of the hours of work performed, record of which was made daily at the time of arrival and departure from office.",
        note_style), '', '', '', ''])
    data.append([Paragraph(f'<b>{faculty.name.upper()}</b>', sign_style), '', '', '', ''])
    data.append([Paragraph('VERIFIED as to the prescribed office hours', small_left), '', '', '', ''])

    # Table and style
    t = Table(data, colWidths=col_widths, repeatRows=0)
    t.setStyle(TableStyle([
        # HEADER ROW SPANS!
        ('SPAN', (0,0), (3,0)),  # left header
        ('SPAN', (4,0), (4,0)),  # right header
        ('SPAN', (0,1), (4,1)),  # Title full row
        ('SPAN', (0,2), (4,2)),  # Name full row
        ('SPAN', (0,3), (4,3)),  # Month full row
        ('SPAN', (0,4), (4,4)),  # Official hours full row
        # Table col/row header spans
        ('SPAN', (0,5), (0,6)),  # Day header, rowspan=2
        ('SPAN', (1,5), (2,5)),  # AM header, colspan=2
        ('SPAN', (3,5), (4,5)),  # PM header, colspan=2
        # Data rows: no span
        ('SPAN', (0, -4), (3, -4)), # Total label+cells span for "TOTAL — Working Hours"
        ('SPAN', (0, -3), (4, -3)), # Cert text full row
        ('SPAN', (0, -2), (4, -2)), # Signature full row
        ('SPAN', (0, -1), (4, -1)), # Verified full row
        # Borders
        ('GRID', (0,5), (-1,-5), 0.5, colors.HexColor('#444444')),  # table grid only (skips headers above)
        ('BOX', (0,5), (-1,-5), 1, colors.HexColor('#444444')),     # outline
        ('BOX', (0, -4), (-1, -4), 1, colors.HexColor('#444444')),  # <-- ADDED LINE
        # Background on 2-row table header and total row
        ('BACKGROUND', (0,5), (-1,6), colors.HexColor('#f3f4f6')), # table 2-row header
        ('BACKGROUND', (0,-4), (-1,-4), colors.HexColor('#f3f4f6')), # total row
        # Center all data
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        # BOLD day col in data
        ('FONTNAME', (0,7), (0,-5), 'Helvetica-Bold'),
        ('FONTSIZE', (0,7), (-1,-5), 7.6),
        # Certification, signature, verified text bottom: no border, added padding
        ('BOTTOMPADDING', (0,-3), (0,-1), 5),
        ('TOPPADDING', (0,-3), (0,-3), 3),
        ('TOPPADDING', (0,-2), (0,-2), 2),
        ('TOPPADDING', (0,-1), (0,-1), 0),
        # Remove borders from header/signature rows
        ('LINEBELOW', (0,2), (4,2), 0.7, colors.HexColor("#111")), # underline for signature row
        ('LINEBELOW', (0,-2), (4,-2), 0.7, colors.HexColor("#111")), # underline for signature
    ]))

    doc.build([t])
    pdf_data = buffer.getvalue()
    buffer.close()
    filename = f"{faculty.name}_{status_label}_{month_label}_{year}.pdf"
    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response




@admin_required
def pup_sites_admin_list(request):
    """
    Admin management page with table + modals.
    """
    sites = PUPSite.objects.all()  # ordering via Meta.ordering
    form = PUPSiteForm()
    return render(request, "admin/pup_sites_admin_list.html", {
        "sites": sites,
        "form": form,
    })


@admin_required
def pup_site_create(request):
    """
    Handles POST from the 'Add' modal.
    """
    if request.method != "POST":
        return redirect("adminhub:pup_sites_admin_list")

    form = PUPSiteForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, "PUP site added successfully.")
    else:
        messages.error(request, "Failed to add PUP site. Please check the form input.")

    return redirect("adminhub:pup_sites_admin_list")


@admin_required
def pup_site_update(request, uid):
    """
    Handles POST from the 'Edit' modal.
    """
    if request.method != "POST":
        return redirect("adminhub:pup_sites_admin_list")

    site = get_object_or_404(PUPSite, uid=uid)
    form = PUPSiteForm(request.POST, instance=site)

    if form.is_valid():
        form.save()
        messages.success(request, "PUP site updated successfully.")
    else:
        messages.error(request, "Failed to update PUP site. Please check the form input.")

    return redirect("adminhub:pup_sites_admin_list")


@admin_required
def pup_site_delete(request, uid):
    """
    Handles POST from the 'Delete' confirmation modal.
    """
    if request.method != "POST":
        return redirect("adminhub:pup_sites_admin_list")

    site = get_object_or_404(PUPSite, uid=uid)
    site.delete()
    messages.success(request, "PUP site deleted successfully.")
    return redirect("adminhub:pup_sites_admin_list")








@admin_required
def landing_background_settings(request):
    target_dir = Path(settings.MEDIA_ROOT) / "backgrounds"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "landing-bg.jpg"

    print(">>> [view] MEDIA_ROOT:", settings.MEDIA_ROOT)
    print(">>> [view] target_path BEFORE:", target_path, "exists:", target_path.exists())

    appearance = LandingAppearance.get_solo()

    if request.method == "POST":
        print(">>> [view] POST /admin/settings/landing-background/")
        print(">>> [view] POST keys:", list(request.POST.keys()))
        print(">>> [view] FILES keys:", list(request.FILES.keys()))

        if "remove_background" in request.POST:
            print(">>> [view] remove_background in POST")
            if target_path.exists():
                print(">>> [view] Removing file at:", target_path)
                target_path.unlink()
            else:
                print(">>> [view] File did not exist at remove:", target_path)
            appearance.use_background_image = False
            appearance.save()
            messages.success(request, "Background image removed. The gradient will be used instead.")
            return redirect("adminhub:landing_background_settings")

        form = BackgroundUploadForm(request.POST, request.FILES)
        if form.is_valid():
            print(">>> [view] form is valid")
            appearance.use_background_image = form.cleaned_data.get("use_background_image", False)
            appearance.overlay_style = form.cleaned_data.get("overlay_style", LandingAppearance.OVERLAY_DARK)

            img = form.cleaned_data.get("file")
            print(">>> [view] cleaned_data['file']:", img)

            if img:
                print(">>> [view] Writing uploaded file to:", target_path)
                with open(target_path, "wb+") as dest:
                    for chunk in img.chunks():
                        dest.write(chunk)
                print(">>> [view] After write, target_path exists:", target_path.exists())

                if "use_background_image" not in request.POST:
                    appearance.use_background_image = True
                    print(">>> [view] use_background_image not in POST -> forced True")

            appearance.save()
            print(">>> [view] Saved appearance: use_background_image=",
                  appearance.use_background_image,
                  "overlay_style=", appearance.overlay_style)
            messages.success(request, "Landing background settings have been updated.")
            return redirect("adminhub:landing_background_settings")
        else:
            print(">>> [view] form invalid, errors:", form.errors)
            messages.error(request, "Please correct the errors below.")
    else:
        print(">>> [view] GET /admin/settings/landing-background/")

        form = BackgroundUploadForm()

    file_exists = target_path.exists()
    bg_url = settings.MEDIA_URL + "backgrounds/landing-bg.jpg"
    print(">>> [view] Rendering admin page with file_exists=", file_exists, "bg_url=", bg_url)

    return render(request, "admin/landing_background_settings.html", {
        "form": form,
        "file_exists": file_exists,
        "bg_url": bg_url,
        "appearance": appearance,
    })






# adminhub/views.py

@admin_required
def document_templates(request):
    """
    Admin page:
    - Filter/search document templates
    - Upload new template (one per category)
    """
    search = request.GET.get("q", "")
    category_id = request.GET.get("category")

    templates = (
        DocumentTemplate.objects
        .filter(is_active=True)
        .select_related("document_category", "uploaded_by")
    )

    if search:
        templates = templates.filter(
            Q(name__icontains=search) |
            Q(document_category__name__icontains=search)
        )

    if category_id:
        templates = templates.filter(document_category_id=category_id)

    templates = templates.order_by("document_category__name", "name")

    # Helper to format sizes like "1.23 MB"
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

    # Attach human-readable size to each template
    for t in templates:
        t.size_human = format_storage(t.file_size or 0)

    paginator = Paginator(templates, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # For filter dropdown
    categories = DocumentCategory.objects.all().order_by("name")

    if request.method == "POST":
        form = DocumentTemplateForm(request.POST, request.FILES)
        if form.is_valid():
            category = form.cleaned_data["document_category"]
            name = form.cleaned_data["name"]
            file = form.cleaned_data["file"]

            try:
                drive = CentralGoogleDriveService()
                # Single shared folder (created if missing)
                folder_id = drive.get_or_create_folder_path("FEMS/Document Templates")

                media = MediaIoBaseUpload(
                    io.BytesIO(file.read()),
                    mimetype=file.content_type,
                    resumable=False,
                )

                uploaded = drive.service.files().create(
                    body={
                        "name": file.name,
                        "parents": [folder_id],
                    },
                    media_body=media,
                    fields="id, webViewLink, mimeType, size"
                ).execute()

                template = DocumentTemplate.objects.create(
                    name=name,
                    document_category=category,
                    file_path=uploaded.get("webViewLink"),
                    google_drive_id=uploaded["id"],
                    mime_type=uploaded.get("mimeType"),
                    file_size=int(uploaded.get("size") or 0),
                    uploaded_by=request.user,
                )

                messages.success(request, f"Template '{template.name}' uploaded successfully.")
                return redirect("adminhub:document_templates")

            except Exception as e:
                print("Template upload error:", e)
                messages.error(request, "Failed to upload template. Please try again.")
        else:
            messages.error(request, "Please fix the errors in the form.")
    else:
        form = DocumentTemplateForm()

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "categories": categories,
        "selected_category": category_id,
        "search_query": search,
        "form": form,
    }
    return render(request, "admin/admin_document_templates.html", context)



def _finalize_response(resp: HttpResponse):
    resp['X-Frame-Options'] = 'SAMEORIGIN'
    resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@admin_required  # OR remove this if you want faculty to call it too
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




@admin_required
@require_POST
def delete_document_template(request, uid):
    """
    Permanently delete the template row and its file on Google Drive.
    """
    template = get_object_or_404(DocumentTemplate, uid=uid)

    name = template.name  # keep for message

    # Delete from Google Drive
    try:
        if template.google_drive_id:
            drive = CentralGoogleDriveService()
            drive.delete_file(template.google_drive_id)
    except Exception as e:
        # Log but don't block deletion in DB
        print("Google Drive delete error:", e)

    # Hard delete in DB
    template.delete()

    messages.success(request, f"Template '{name}' has been removed.")
    return redirect("adminhub:document_templates")





@admin_required
def document_category_list(request):
    """List and search for Document Categories."""
    search_query = request.GET.get("q", "")
    categories = DocumentCategory.objects.all()

    if search_query:
        categories = categories.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )

    categories = categories.order_by("name")
    paginator = Paginator(categories, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Fetch all file types for the modal
    file_types = FileType.objects.all()

    return render(
        request,
        "admin/document_category_list.html",
        {
            "page_obj": page_obj,
            "search_query": search_query,
            "filetypes": file_types,
        },
    )


@admin_required
def document_category_create_or_edit(request, id=None):
    """
    Handle both creating and editing of Document Categories via AJAX.
    Expects an AJAX POST and returns JSON.
    """
    if id:
        category = get_object_or_404(DocumentCategory, id=id)
        success_message = f"Document category '{category.name}' updated successfully!"
    else:
        category = None
        success_message = "Document category created successfully!"

    if request.method == "POST":
        form = DocumentCategoryForm(request.POST, instance=category)
        if form.is_valid():
            saved_category = form.save()
            messages.success(request, success_message)
            return JsonResponse(
                {
                    "success": True,
                    "id": saved_category.id,
                    "name": saved_category.name,
                }
            )
        else:
            # Respond with validation errors
            return JsonResponse({"success": False, "errors": form.errors}, status=400)

    # Non-POST or non-AJAX access
    return JsonResponse(
        {"success": False, "error": "Invalid request method or non-AJAX access."},
        status=405,
    )


@admin_required
def document_category_delete(request, id):
    """
    Handle deleting a Document Category via AJAX.
    """
    category = get_object_or_404(DocumentCategory, id=id)

    if request.method == "POST":
        category_name = category.name
        category.delete()
        return JsonResponse(
            {
                "success": True,
                "message": f"Category '{category_name}' has been deleted.",
            }
        )

    return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)






from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q

from applicant.models import Applicant, ApplicantRequiredDocument
from faculty.models import DocumentCategory
from base.decorators import admin_required  # or wherever your admin_required is
from base.forms import DocumentCategoryForm  # already used in your doc category views
from base.forms import ApplicantRequiredDocumentForm





@admin_required
def applicant_required_document_list_view(request):
    """
    Global configuration for applicant required documents (all applicants).
    Renders a page with a table and modals, uses AJAX for create/edit/delete.
    """
    search_query = request.GET.get("q", "")
    qs = ApplicantRequiredDocument.objects.select_related("document_category")

    if search_query:
        qs = qs.filter(
            Q(document_category__name__icontains=search_query) |
            Q(document_category__description__icontains=search_query)
        )

    qs = qs.order_by("document_category__name")
    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    all_document_categories = DocumentCategory.objects.all().order_by("name")

    return render(
        request,
        "admin/admin_applicant_required_documents.html",
        {
            "page_obj": page_obj,
            "search_query": search_query,
            "all_document_categories": all_document_categories,
        },
    )


@admin_required
def applicant_required_document_create_or_edit_view(request, pk=None):
    """
    AJAX create/edit for ApplicantRequiredDocument (used by modal).
    """
    if request.method != "POST" or request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    if pk:
        instance = get_object_or_404(ApplicantRequiredDocument, pk=pk)
        success_message = "Required document updated."
    else:
        instance = None
        success_message = "Required document created."

    form = ApplicantRequiredDocumentForm(request.POST, instance=instance)
    if form.is_valid():
        saved = form.save()
        return JsonResponse(
            {
                "success": True,
                "id": saved.pk,
                "document_category": saved.document_category.name,
                "document_category_id": saved.document_category.id,
                "is_required": saved.is_required,
                "validity_days": saved.validity_days,
                "category_is_required": saved.document_category.is_required,
                "message": success_message,
            }
        )
    return JsonResponse({"success": False, "errors": form.errors}, status=400)


@admin_required
def applicant_required_document_delete_view(request, pk):
    """
    AJAX delete for ApplicantRequiredDocument (used by modal).
    """
    if request.method != "POST" or request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    req_doc = get_object_or_404(ApplicantRequiredDocument, pk=pk)
    req_doc.delete()
    return JsonResponse({"success": True, "message": "Required document configuration deleted."})






from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q

from faculty.models import EmploymentStatus
from base.forms import EmploymentStatusForm
from base.decorators import admin_required  # whatever you already use







@admin_required
def employment_status_list_view(request):
    """
    List/search EmploymentStatus entries.
    The template uses modals + AJAX for create/edit/delete.
    """
    search_query = request.GET.get("q", "")
    qs = EmploymentStatus.objects.all()

    if search_query:
        qs = qs.filter(name__icontains=search_query)

    qs = qs.order_by("name")
    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "admin/employment_status_list.html",
        {
            "page_obj": page_obj,
            "search_query": search_query,
        },
    )


@admin_required
def employment_status_create_or_edit_view(request, pk=None):
    """
    AJAX create/edit for EmploymentStatus.
    """
    if request.method != "POST" or request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    if pk:
        instance = get_object_or_404(EmploymentStatus, pk=pk)
        success_message = "Employment status updated successfully."
    else:
        instance = None
        success_message = "Employment status created successfully."

    form = EmploymentStatusForm(request.POST, instance=instance)
    if form.is_valid():
        status_obj = form.save()
        return JsonResponse(
            {
                "success": True,
                "id": status_obj.id,
                "name": status_obj.name,
                "is_active": status_obj.is_active,
                "message": success_message,
            }
        )
    return JsonResponse({"success": False, "errors": form.errors}, status=400)


@admin_required
def employment_status_delete_view(request, pk):
    """
    AJAX delete for EmploymentStatus.
    """
    if request.method != "POST" or request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    status_obj = get_object_or_404(EmploymentStatus, pk=pk)
    status_obj.delete()
    return JsonResponse(
        {
            "success": True,
            "message": "Employment status deleted successfully.",
        }
    )

    