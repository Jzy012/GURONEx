from django.shortcuts import render, redirect, get_object_or_404
from base.decorators import admin_required, faculty_required
from base.forms import TwoFactorToggleForm
from django.contrib import messages
from base.utils.admin_data import get_admin_data, get_all_faculty_data



from django.shortcuts import render
from django.db.models import Q
from faculty.models import FacultyDocument, DocumentCategory
from faculty.models import FacultyProfile

# Create Faculty View
from django.contrib import messages
from base.models import Account
from base.forms import FacultyCreationForm
from services.google_drive_service import CentralGoogleDriveService
from django.db import transaction
from django.contrib.auth.decorators import login_required

from django.core.paginator import Paginator


from django.shortcuts import render
from base.decorators import admin_required
from base.utils.admin_data import get_admin_data
from applicant.models import Applicant
from faculty.models import FacultyProfile, FacultyDocument, FacultyRequest
from adminhub.models import Announcement
from django.db.models import Sum
from base.models import GoogleStorageAccount  # adjust import if needed
from django.utils import timezone

@admin_required
def home(request):
    # Stats cards
    data = get_admin_data(request) if 'get_admin_data' in globals() else {}

    total_applicants = Applicant.objects.count()
    total_faculty = FacultyProfile.objects.count()
    total_pending_docs = FacultyDocument.objects.filter(status='Pending').count()
    total_requests = FacultyRequest.objects.count()
    total_storage_bytes = FacultyDocument.objects.aggregate(total_size=Sum('file_size'))['total_size'] or 0

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
    account = GoogleStorageAccount.objects.filter(is_active=True).first()
    status = {
        "label": "Disconnected",
        "color": "bg-red-100 text-red-800",
        "message": "No active Google Drive account.",
    }
    if account:
        if account.token_expiry and account.token_expiry > timezone.now():
            status = {
                "label": "Connected",
                "color": "bg-green-100 text-green-800",
                "message": f"Active account: {account.email}",
            }
        else:
            status = {
                "label": "Expired",
                "color": "bg-yellow-100 text-yellow-800",
                "message": "Token expired — reauthentication required.",
            }

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

    

from django.db.models import Count, Sum, Q
from django.utils.functional import cached_property

@admin_required
def documents(request):
    search_query = request.GET.get('q', '')
    category_id = request.GET.get('category')
    status_filter = request.GET.get('status')

    documents = FacultyDocument.objects.select_related('faculty__account', 'document_category')

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
            total_docs=Count('documents'),
            total_storage_bytes=Sum('documents__file_size'),
            pending_count=Count('documents', filter=Q(documents__status='Pending'))
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


from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt   # Use csrf_protect in production

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

    doc.status = new_status
    doc.admin_remarks = remarks
    doc.save(update_fields=['status', 'admin_remarks'])

    # You could also send back some info for updating the row
    return JsonResponse({
        "success": True,
        "status": doc.status,
        "admin_remarks": doc.admin_remarks,
    })

from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse, StreamingHttpResponse, Http404
from django.urls import reverse
import mimetypes
import io

from faculty.models import FacultyDocument
from services.google_drive_service import CentralGoogleDriveService
from googleapiclient.http import MediaIoBaseDownload

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


from django.shortcuts import render
from django.db.models import Count, Q
from django.core.paginator import Paginator
from faculty.models import FacultyProfile, EmploymentStatus, FacultyDocument

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
        pending_documents=Count('documents', filter=Q(documents__status='Pending'))
    )

    total_faculty = FacultyProfile.objects.count()
    total_pending_docs = FacultyDocument.objects.filter(status='Pending').count()
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

    # Fetch related documents (optional: order/filter as needed)
    documents = faculty.documents.all().order_by('-uploaded_at')

    # Instantiate the form with the faculty instance and account_instance
    form = FacultyEditForm(instance=faculty, account_instance=faculty.account)

    context = {
        'faculty': faculty,
        'documents': documents,
        'form': form,  # <-- pass form to context!
    }

    return render(request, 'admin/admin_faculty_detail.html', context)





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
                        name=data['name'],
                        department=data['department'],
                        birth_date=data['birth_date'],
                        contact_number=data['contact_number'],
                        status=data['status'],
                    )

                    # 3. Attempt to create Drive folder
                    try:
                        drive = CentralGoogleDriveService()
                        folder_id = drive.create_faculty_folder(faculty)
                        faculty.gdrive_folder_id = folder_id
                        faculty.save()
                        messages.success(request, f"✅ Faculty created. Folder ID: {folder_id}")
                    except Exception as e:
                        messages.warning(request, f"⚠️ Faculty saved but Drive folder creation failed: {str(e)}")

                    # Optional: show password if auto-generated
                    if not data['password']:
                        messages.info(request, f"🛡️ Auto-generated password: {password}")

                    return redirect('adminhub:faculty_list')

            except Exception as e:
                messages.error(request, f"❌ Error: {str(e)}")
    else:
        form = FacultyCreationForm()

    return render(request, 'admin/admin_faculty_creation.html', {'form': form})



from base.forms import FacultyEditForm


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

#Announcements View



from datetime import date, datetime
from django.shortcuts import render
from django.contrib import messages

@admin_required
def announcements_view(request):
    today = date.today()
    announcements = Announcement.objects.order_by('-created_at')

    return render(request, 'admin/admin_announcements.html', {
        'announcements': announcements,
        'today': today
    })




from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from base.forms import AnnouncementForm
from .models import Announcement
from base.models import Account  # adjust as needed

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
            announcement.visible_to_roles = form.cleaned_data['visible_to_roles']
            announcement.save()
            messages.success(request, "Announcement posted successfully.")

            # (Optional) Handle email sending later

            return redirect('adminhub:announcements')  # you’ll create this soon
        else:
            messages.error(request, "There was an error in your submission.")
    else:
        form = AnnouncementForm()

    return render(request, 'admin/admin_create_announcement.html', {'form': form})




from django.shortcuts import get_object_or_404

@admin_required
def edit_announcement_view(request, uuid):
    announcement = get_object_or_404(Announcement, uuid=uuid)

    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.visible_to_roles = form.cleaned_data['visible_to_roles']
            updated.save()
            messages.success(request, "Announcement updated successfully.")
            return redirect('adminhub:announcements')
    else:
        form = AnnouncementForm(instance=announcement)
        # Convert JSON list back to choices
        form.fields['visible_to_roles'].initial = announcement.visible_to_roles

    return render(request, 'admin/admin_edit_announcement.html', {'form': form, 'announcement': announcement})





from django.shortcuts import get_object_or_404, redirect

@admin_required
def delete_announcement_view(request, uuid):
    announcement = get_object_or_404(Announcement, uuid=uuid)
    announcement.delete()
    messages.success(request, f"'{announcement.title}' has been permanently deleted.")
    return redirect('adminhub:announcements')






# views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from base.forms import AssignDeliverablesForm
from faculty.models import Deliverable, DeliverableTemplate
from django.utils import timezone


from django.db.models import Q
from faculty.models import FacultyProfile, FacultyDocument, Deliverable, Semester

from django.utils import timezone
from faculty.models import FacultyProfile, FacultyDocument, Deliverable, Semester

from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator
from faculty.models import FacultyProfile, FacultyDocument, Deliverable, Semester

@admin_required
def deliverables_view(request):
    today = timezone.now().date()
    semester = Semester.objects.filter(is_active=True, start_date__lte=today, end_date__gte=today).select_related('academic_year').first()
    total_faculty = FacultyProfile.objects.count()

    completed_submissions = 0
    pending_submissions = 0
    deliverables_list = []
    academic_year_str = ""
    semester_str = ""

    # --- Search, filter, and pagination params ---
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "")
    page_number = request.GET.get("page")
    page_size = 10  # You can adjust this

    faculty_statuses_raw = []

    if semester:
        academic_year = semester.academic_year
        academic_year_str = str(academic_year)
        semester_str = semester.get_semester_type_display()

        deliverables = Deliverable.objects.filter(semester=semester).select_related('document_category')
        deliverable_ids = list(deliverables.values_list('id', flat=True))
        deliverable_count = len(deliverable_ids)
        deliverables_list = [
            {
                "name": d.document_category.name,
                "deadline": d.deadline,
            } for d in deliverables
        ]

        faculty_qs = FacultyProfile.objects.select_related('account').all()
        if search:
            faculty_qs = faculty_qs.filter(
                Q(name__icontains=search) | Q(account__email__icontains=search)
            )

        for faculty in faculty_qs:
            approved_count = 0
            for d_id in deliverable_ids:
                doc = FacultyDocument.objects.filter(
                    faculty=faculty,
                    semester=semester,
                    deliverable_id=d_id,
                    status="Approved"
                ).first()
                if doc:
                    approved_count += 1

            faculty_status = {
                "name": faculty.name,
                "email": faculty.account.email,
                "approved_count": approved_count,
                "total_required": deliverable_count,
                "faculty_uuid": faculty.uuid,
            }

            # Filter by status if specified
            if status_filter == "completed" and (approved_count != deliverable_count or deliverable_count == 0):
                continue
            if status_filter == "pending" and (approved_count == deliverable_count and deliverable_count > 0):
                continue

            faculty_statuses_raw.append(faculty_status)

    # Pagination of faculty_statuses_raw
    paginator = Paginator(faculty_statuses_raw, page_size)
    page_obj = paginator.get_page(page_number)

    # Recompute completed/pending based on the unpaginated filtered queryset
    completed_submissions = sum(
        1 for f in faculty_statuses_raw if f["approved_count"] == f["total_required"] and f["total_required"] > 0
    )
    pending_submissions = len(faculty_statuses_raw) - completed_submissions

    # Preserve other GET params for pagination links
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    context = {
        'total_faculty': total_faculty,
        'completed_submissions': completed_submissions,
        'pending_submissions': pending_submissions,
        'page_obj': page_obj,
        'paginator': paginator,
        'deliverables_list': deliverables_list,
        'academic_year_str': academic_year_str,
        'semester_str': semester_str,
        'search': search,
        'status_filter': status_filter,
        'querystring': querystring,
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




from django.contrib import messages
from django.shortcuts import render, redirect
from base.forms import DeliverableTemplateForm


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
            return redirect('adminhub:deliverable_templates')
    else:
        form = DeliverableTemplateForm()

    return render(request, 'admin/admin_create_deliverable_template.html', {'form': form})




# views.py
from django.forms import modelformset_factory
from base.forms import AcademicYearForm, SemesterForm
from faculty.models import AcademicYear, Semester

@admin_required
def academic_years_view(request):
    academic_years = AcademicYear.objects.all()
    return render(request, 'admin/admin_academic_years.html', {'academic_years': academic_years})




@admin_required
def create_academic_year_view(request):
    SemesterFormSet = modelformset_factory(Semester, form=SemesterForm, extra=3, can_delete=False)

    if request.method == 'POST':
        year_form = AcademicYearForm(request.POST)
        formset = SemesterFormSet(request.POST)

        if year_form.is_valid() and formset.is_valid():
            academic_year = year_form.save()

            # Save all semester forms with this academic_year
            for form in formset:
                semester = form.save(commit=False)
                semester.academic_year = academic_year
                semester.save()

            messages.success(request, "Academic year and semesters created.")
            return redirect('adminhub:create_academic_year')

    else:
        year_form = AcademicYearForm()
        formset = SemesterFormSet(queryset=Semester.objects.none(), initial=[
            {'semester_type': '1st'},
            {'semester_type': '2nd'},
            {'semester_type': 'summer'},
        ])

    return render(request, 'admin/admin_create_academic_year.html', {
        'year_form': year_form,
        'formset': formset,
    })








from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count
from faculty.models import FacultyRequest, RequestType
from base.forms import RequestTypeForm, FacultyRequestForm, AdminFacultyRequestForm

@admin_required
def admin_request_list_view(request):
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    request_type_id = request.GET.get('request_type', '')

    # Base queryset
    requests_qs = FacultyRequest.objects.select_related("faculty", "request_type").order_by("-created_at")
    
    # Filtering
    if search:
        requests_qs = requests_qs.filter(
            Q(description__icontains=search) |
            Q(request_type__name__icontains=search) |
            Q(faculty__name__icontains=search)
        )
    if status:
        requests_qs = requests_qs.filter(status=status)
    if request_type_id:
        requests_qs = requests_qs.filter(request_type_id=request_type_id)

    # Stats
    total_requests = FacultyRequest.objects.count()
    total_pending = FacultyRequest.objects.filter(status="Pending").count()
    total_approved = FacultyRequest.objects.filter(status="Approved").count()
    total_rejected = FacultyRequest.objects.filter(status="Rejected").count()

    statuses = [
        {'id': 'Pending', 'name': 'Pending'},
        {'id': 'Approved', 'name': 'Approved'},
        {'id': 'Rejected', 'name': 'Rejected'},
    ]

    # For request type filter dropdown
    request_types = RequestType.objects.all()

    return render(request, "admin/admin_request_list.html", {
        "requests": requests_qs,
        "statuses": statuses,
        "request_types": request_types,
        "search": search,
        "status": status,
        "request_type_id": request_type_id,
        "total_requests": total_requests,
        "total_pending": total_pending,
        "total_approved": total_approved,
        "total_rejected": total_rejected,
    })


@admin_required
def admin_request_create_view(request):
    if request.method == "POST":
        form = AdminFacultyRequestForm(request.POST)
        if form.is_valid():
            faculty_request = form.save(commit=False)
            faculty_request.created_by_admin = True
            faculty_request.save()
            messages.success(request, "Request created successfully.")
            return redirect("admin_request_list")
    else:
        form = AdminFacultyRequestForm()

    return render(request, "admin/admin_request_form.html", {"form": form})


from django.views.decorators.http import require_POST

@admin_required
@require_POST
def admin_request_action_view(request, uuid):
    faculty_request = get_object_or_404(FacultyRequest, uuid=uuid)
    action = request.POST.get("action")
    remarks = request.POST.get("remarks", "")

    if action == "approve":
        faculty_request.status = "Approved"
        messages.success(request, "Request approved.")
    elif action == "reject":
        faculty_request.status = "Rejected"
        messages.success(request, "Request rejected.")
    else:
        messages.error(request, "Invalid action.")
        return redirect("admin_request_list")

    faculty_request.remarks = remarks
    faculty_request.save()
    return redirect("adminhub:request_list")




@admin_required
def request_type_list_view(request):
    types = RequestType.objects.all().order_by("name")
    return render(request, "admin/requests/request_type_list.html", {"types": types})


@admin_required
def request_type_create_view(request):
    if request.method == "POST":
        form = RequestTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Request type added successfully.")
            return redirect("request_type_list")
    else:
        form = RequestTypeForm()

    return render(request, "admin/requests/request_type_form.html", {"form": form})


@admin_required
def request_type_edit_view(request, pk):
    req_type = get_object_or_404(RequestType, pk=pk)
    if request.method == "POST":
        form = RequestTypeForm(request.POST, instance=req_type)
        if form.is_valid():
            form.save()
            messages.success(request, "Request type updated successfully.")
            return redirect("request_type_list")
    else:
        form = RequestTypeForm(instance=req_type)

    return render(request, "admin/requests/request_type_form.html", {"form": form})


@admin_required
def request_type_delete_view(request, pk):
    req_type = get_object_or_404(RequestType, pk=pk)
    req_type.delete()
    messages.success(request, "Request type deleted successfully.")
    return redirect("request_type_list")







from django.shortcuts import render
from django.core.paginator import Paginator
from applicant.models import Applicant

from django.db.models import Count, Q


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




from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from applicant.models import Applicant, ApplicantDocument
from django.db import transaction
from base.utils.email import send_applicant_status_email

# Statuses in order for the stepper visualization
STEPPER_STATUSES = [
    ('pending', "Pending"),
    ('demo_scheduled', "Demo Scheduled"),
    ('for_interview', "For Interview"),
    ('psych_test', "Psych Test"),
    ('hired', "Hired"),
    ('failed', "Failed"),
]

@admin_required
def applicant_detail_view(request, uuid):
    applicant = get_object_or_404(Applicant, uuid=uuid)
    documents = ApplicantDocument.objects.filter(applicant=applicant)
    status_choices = Applicant._meta.get_field('status').choices

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status and new_status != applicant.status:
            with transaction.atomic():
                applicant.status = new_status
                applicant.save()
                send_applicant_status_email(applicant, new_status)
                messages.success(request, "Status updated.")
            return redirect('adminhub:applicant_detail', uuid=applicant.uuid)
        else:
            messages.warning(request, "No status change detected.")

    # For stepper: build steps with current progress
    stepper = []
    found_active = False
    for value, label in STEPPER_STATUSES:
        is_active = (applicant.status == value)
        stepper.append({
            "value": value,
            "label": label,
            "completed": not found_active and not is_active,
            "active": is_active,
        })
        if is_active:
            found_active = True

    return render(request, 'admin/admin_applicant_detail.html', {
        'applicant': applicant,
        'documents': documents,
        'status_choices': status_choices,
        'stepper': stepper,
    })




from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from applicant.models import Applicant, ApplicantDocument
from faculty.models import FacultyProfile, EmploymentStatus, FacultyDocument
from base.models import Account
from .models import CreatedAccountLog
from services.google_drive_service import CentralGoogleDriveService
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings

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



from rfid.models import RFIDTag, AttendanceLog
from rfid.views import format_log
from django.utils import timezone
import calendar
from django.core.paginator import Paginator

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




from django.shortcuts import render
from faculty.models import FacultyProfile
from rfid.models import RFIDTag

@admin_required
def pair_rfid(request):
    faculties_qs = FacultyProfile.objects.all().order_by('-created_at')
    rfid_map = {tag.faculty_id: tag.uid for tag in RFIDTag.objects.exclude(faculty=None)}
    faculties = []

    # Identify the most recently created faculty (newest)
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

    # Sort: new and unpaired first, then other unpaired, then paired, then by name
    faculties.sort(
        key=lambda x: (
            not x['is_new'],         # False (new) sorts before True
            not x['is_unpaired'],    # False (unpaired) before True (paired)
            x['name'].lower(),
        )
    )

    message = None
    message_class = ""
    if request.method == 'POST':
        faculty_id = request.POST.get('faculty_id')
        rfid_uid = request.POST.get('rfid_uid', '').strip()
        faculty = next((f for f in faculties if f['uuid'] == faculty_id), None)
        if not faculty:
            message = "Faculty not found."
            message_class = "bg-red-100 text-red-800"
        else:
            faculty_obj = FacultyProfile.objects.get(pk=faculty['pk'])
            tag, created = RFIDTag.objects.get_or_create(uid=rfid_uid)
            if tag.faculty and tag.faculty != faculty_obj:
                message = f"RFID {rfid_uid} is already paired to {tag.faculty.name}."
                message_class = "bg-red-100 text-red-800"
            else:
                tag.faculty = faculty_obj
                tag.save()
                rfid_map[faculty_obj.pk] = tag.uid
                message = f"RFID <b>{rfid_uid}</b> successfully paired to <b>{faculty_obj.name}</b>!"
                message_class = "bg-green-100 text-green-800"
    return render(request, 'admin/admin_pair_rfid.html', {
        'faculties': faculties,      # now includes is_new and is_unpaired
        'rfid_map': rfid_map,
        'message': message,
        'message_class': message_class,
    })


from django.http import JsonResponse
from django.core.cache import cache

def rfid_pairing_tap_api(request):
    uid = cache.get('last_rfid_uid')
    return JsonResponse({"uid": uid if uid else ""})








from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from base.forms import ManualAttendanceLogForm
from rfid.models import  RFIDTag
from django.utils import timezone

from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from base.forms import ManualAttendanceLogForm
from rfid.models import FacultyProfile, RFIDTag, AttendanceLog
from django.utils import timezone
import datetime

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
    initial = {}

    if request.method == "POST":
        form = ManualAttendanceLogForm(request.POST)
        if form.is_valid():
            faculty = form.cleaned_data['faculty']
            uid = form.cleaned_data['uid']
            date = form.cleaned_data['date']
            time_in = form.cleaned_data['time_in']
            time_out = form.cleaned_data['time_out']

            # Store datetimes in the default Django way
            tz = timezone.get_current_timezone()
            time_in_dt = datetime.datetime.combine(date, time_in, tzinfo=tz)
            time_out_dt = datetime.datetime.combine(date, time_out, tzinfo=tz)

            AttendanceLog.objects.create(
                faculty=faculty,
                uid=uid,
                date=date,
                time_in=time_in_dt,
                time_out=time_out_dt
            )
            messages.success(request, "Attendance log created successfully.")
            return redirect(reverse('adminhub:attendance_logs'))
        else:
            # Show first error as the message
            message = form.errors.as_text().replace("* ", "").replace("\n", "<br>")
            message_class = "bg-red-100 text-red-800"
            initial = {
                'faculty': request.POST.get('faculty', ''),
                'uid': request.POST.get('uid', ''),
                'date': request.POST.get('date', ''),
                'time_in': request.POST.get('time_in', ''),
                'time_out': request.POST.get('time_out', ''),
            }
    else:
        form = ManualAttendanceLogForm()
        initial = {
            'date': timezone.localdate()
        }

    return render(request, 'admin/admin_manual_attendance_log.html', {
        'faculties': faculties,
        'rfid_map': rfid_map,
        'message': message,
        'message_class': message_class,
        **initial,
    })





from django.core.paginator import Paginator
from django.db.models import Q

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




from django.shortcuts import render, redirect, get_object_or_404
from faculty.models import TeachingAssignment, FacultyProfile
from base.forms import TeachingAssignmentForm, TeachingAssignmentBulkUploadForm

@admin_required
def teaching_assignment_list(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    assignments = TeachingAssignment.objects.filter(faculty=faculty)
    return render(request, 'admin/admin_faculty_teaching_assignment.html', {'faculty': faculty, 'assignments': assignments})


@admin_required
def teaching_assignment_create(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    if request.method == 'POST':
        form = TeachingAssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.faculty = faculty
            assignment.save()
            return redirect('adminhub:teaching_assignment_list', faculty_uuid=faculty.uuid)
    else:
        form = TeachingAssignmentForm(initial={'faculty': faculty})
    return render(request, 'admin/admin_teaching_assignment_create.html', {'form': form, 'faculty': faculty})


@admin_required
def teaching_assignment_update(request, faculty_uuid, pk):
    assignment = get_object_or_404(TeachingAssignment, pk=pk, faculty__uuid=faculty_uuid)
    if request.method == 'POST':
        form = TeachingAssignmentForm(request.POST, instance=assignment)
        if form.is_valid():
            form.save()
            return redirect('adminhub:teaching_assignment_list', faculty_uuid=assignment.faculty.uuid)
    else:
        form = TeachingAssignmentForm(instance=assignment)
    return render(request, 'admin/admin_teaching_assignment_create.html', {'form': form, 'faculty': assignment.faculty})


@admin_required
def teaching_assignment_delete(request, pk):
    assignment = get_object_or_404(TeachingAssignment, pk=pk)
    faculty_id = assignment.faculty.id
    if request.method == 'POST':
        assignment.delete()
        return redirect('teaching_assignment_list', faculty_id=faculty_id)
    return render(request, 'teaching_assignment/confirm_delete.html', {'assignment': assignment})




import pandas as pd 
from django.contrib import messages

@admin_required
def teaching_assignment_bulk_upload(request, faculty_id):
    faculty = get_object_or_404(FacultyProfile, id=faculty_id)
    if request.method == 'POST':
        form = TeachingAssignmentBulkUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            try:
                df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                for _, row in df.iterrows():
                    TeachingAssignment.objects.create(
                        faculty=faculty,
                        subject_code=row['subject_code'],
                        subject_description=row['subject_description'],
                        year_section=row['year_section'],
                        day_of_week=row['day_of_week'].lower()[:3],  # expects 'mon', 'tue', etc.
                        start_time=row['start_time'],
                        end_time=row['end_time'],
                        semester_id=row['semester_id'],  # assumes ID is provided
                    )
                messages.success(request, "Bulk upload successful.")
            except Exception as e:
                messages.error(request, f"Error: {e}")
            return redirect('teaching_assignment_list', faculty_id=faculty.id)
    else:
        form = TeachingAssignmentBulkUploadForm()
    return render(request, 'admin/admin_teaching_assignment/bulk_upload.html', {'form': form, 'faculty': faculty})





from django.shortcuts import render, get_object_or_404
from datetime import date
import calendar
from faculty.models import FacultyProfile
from rfid.models import AttendanceLog
from services.dtr_service import DTRCalculator

@admin_required
def dtr_tab_view(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    today = date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

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

    # For year dropdown, show last 3 years and next year
    year_choices = [today.year-1, today.year, today.year+1]
    months = [(i, calendar.month_name[i]) for i in range(1, 13)]

    context = {
        'faculty': faculty,
        'dtr': dtr,
        'month': month,
        'year': year,
        'year_choices': year_choices,
        'months': months,
    }
    return render(request, 'admin/admin_dtr.html', context)