from django.shortcuts import render, redirect
from base.decorators import faculty_required, admin_required
from base.forms import TwoFactorToggleForm
from django.contrib import messages
from base.utils.faculty_data import get_faculty_data
# Create your views here.

@faculty_required
def home(request):
    data = get_faculty_data(request)
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
            messages.success(request, "2FA setting updated.")
            return redirect("faculty:faculty_2fa")
    else:
        form = TwoFactorToggleForm(instance=user)

    return render(request, "faculty/faculty_2fa.html", {"form": form})



from django.db.models import Sum, Q
from django.utils import timezone

@faculty_required
def faculty_documents_view(request):
    faculty_profile = request.user.faculty_profile
    documents = faculty_profile.documents.order_by("-uploaded_at")  # or paginate as needed

    total_documents = documents.count()
    pending_documents = documents.filter(status="Pending").count()
    total_storage_bytes = documents.aggregate(total=Sum("file_size"))["total"] or 0

    def filesizeformat(num):
        # You can use Django's default 'filesizeformat' on the template for this.
        # This is just for reference if you want to format in Python.
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



from django.forms import formset_factory, BaseFormSet
from django.shortcuts import render, redirect
from django.contrib import messages
from base.forms import FacultyDocumentUploadForm
from services.google_drive_service import CentralGoogleDriveService
from .models import FacultyDocument
import io
from googleapiclient.http import MediaIoBaseUpload

def faculty_document_upload(request):
    data = get_faculty_data(request)

    account = request.user
    faculty = getattr(account, "faculty_profile", None)
    if not faculty:
        messages.error(request, "Only faculty can upload documents.")
        return redirect('faculty:home')

    # --- CHANGED: custom formset to pass index to form
    class IndexedFormSet(BaseFormSet):
        def add_fields(self, form, index):
            super().add_fields(form, index)
            form.index = index  # store index for template/debug if needed

        def _construct_form(self, i, **kwargs):
            kwargs['index'] = i  # <-- inject index for form
            kwargs['faculty'] = faculty
            return super()._construct_form(i, **kwargs)

    DocumentFormSet = formset_factory(FacultyDocumentUploadForm, formset=IndexedFormSet, extra=1, max_num=10, validate_max=True)

    if request.method == 'POST':
        formset = DocumentFormSet(request.POST, request.FILES)
        if formset.is_valid():
            service = CentralGoogleDriveService()
            success_count = 0

            for form in formset:
                if not form.cleaned_data:
                    continue  # skip empty rows
                file = form.cleaned_data["file"]
                name = form.cleaned_data["document_name"]
                category = form.cleaned_data["document_category"]
                expiry = form.cleaned_data.get("expiry_date")

                try:
                    media = MediaIoBaseUpload(
                        io.BytesIO(file.read()),  # wrap file in a stream
                        mimetype=file.content_type,
                        resumable=False
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
                    print(e)
                    messages.error(request, f"Failed to upload '{name}'.")

            if success_count:
                messages.success(request, f"{success_count} document(s) uploaded successfully.")
            return redirect("faculty:faculty_documents")
        else:
            messages.error(request, "One or more documents are invalid.")
    else:
        formset = DocumentFormSet()

    context = {**data, "formset": formset}
    return render(request, "faculty/faculty_document_upload.html", context)







from django.shortcuts import render
from django.utils import timezone
from adminhub.models import Announcement, AnnouncementViewLog
from base.models import Account  # if not already imported
from django.db.models import Q



@faculty_required
def faculty_announcements_view(request):
    data = get_faculty_data(request)

    user = request.user
    today = timezone.now().date()

    # Get all announcements where user role is included in visible_to_roles
    announcements = Announcement.objects.filter(
        visible_to_roles__contains=[user.role]
    ).filter(
        start_date__lte=today
    ).filter(
        Q(end_date__gte=today) | Q(end_date__isnull=True)
    ).order_by('-created_at')

    # Get UUIDs of announcements the user has already seen
    seen_ids = AnnouncementViewLog.objects.filter(user=user).values_list('announcement__uuid', flat=True)

    return render(request,  'faculty/faculty_announcements.html',  {
        **data,
        'announcements': announcements,
        'seen_ids': list(seen_ids),
    })





from django.http import JsonResponse, Http404

@faculty_required
def view_announcement_ajax(request, uuid):
    user = request.user
    try:
        announcement = Announcement.objects.get(uuid=uuid)
    except Announcement.DoesNotExist:
        raise Http404("Announcement not found")

    # Check if user is allowed to see this announcement
    if user.role not in announcement.visible_to_roles:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    # Mark as seen if not already logged
    AnnouncementViewLog.objects.get_or_create(user=user, announcement=announcement)

    data = {
        'title': announcement.title,
        'content': announcement.content,
        'attachment_link': announcement.attachment_link,
    }

    return JsonResponse(data)




from django.utils import timezone
from faculty.models import Deliverable, FacultyDocument, Semester
from base.utils.faculty_data import get_faculty_data
from django.shortcuts import render
from base.decorators import faculty_required

@faculty_required
def faculty_deliverables_view(request):
    data = get_faculty_data(request)
    faculty = request.user.faculty_profile
    today = timezone.now().date()

    semester = Semester.objects.filter(
        is_active=True,
        start_date__lte=today,
        end_date__gte=today
    ).first()

    if semester is None:
        data['semester'] = None
        data['deliverables_status'] = []
        data['can_request_clearance'] = False
        return render(request, 'faculty/faculty_deliverables.html', data)

    deliverables = Deliverable.objects.filter(
        semester=semester
    ).select_related('document_category')

    uploaded_docs = FacultyDocument.objects.filter(
        faculty=faculty,
        semester=semester,
    )

    deliverables_status = []
    all_approved = True

    for d in deliverables:
        doc = uploaded_docs.filter(deliverable=d).first()

        # Fallback if deliverable isn't linked in old uploads
        if not doc:
            doc = uploaded_docs.filter(document_category=d.document_category).first()

        # Checklist tracking
        if not doc or doc.status != "Approved":
            all_approved = False

        deliverables_status.append({
            'deliverable': d,
            'document': doc,
            'status': doc.status if doc else "Not Uploaded"
        })

    data.update({
        "semester": semester,
        "deliverables_status": deliverables_status,
        "can_request_clearance": all_approved and deliverables.exists()
    })

    return render(request, 'faculty/faculty_deliverables.html', data)








from django.forms import formset_factory
from django.shortcuts import render, redirect
from django.contrib import messages
from base.forms import FacultyDeliverableUploadForm
from .models import FacultyDocument, Deliverable
from services.google_drive_service import CentralGoogleDriveService
from base.utils.faculty_data import get_faculty_data
import io
from googleapiclient.http import MediaIoBaseUpload
from base.forms import FacultyDeliverableUploadForm, IndexedFormSet



@faculty_required
def faculty_deliverable_upload(request):
    data = get_faculty_data(request)
    account = request.user
    faculty = getattr(account, "faculty_profile", None)

    DocumentFormSet = formset_factory(
        FacultyDeliverableUploadForm,
        formset=IndexedFormSet,
        extra=1,
        max_num=10,
        validate_max=True
    )

    if request.method == "POST":
        formset = DocumentFormSet(request.POST, request.FILES, form_kwargs={'faculty': faculty})
        if formset.is_valid():
            service = CentralGoogleDriveService()
            success_count = 0

            for form in formset:
                if not form.cleaned_data:
                    continue

                deliverable = form.cleaned_data["deliverable"]
                file = form.cleaned_data["file"]

                try:
                    category = deliverable.document_category
                    media = MediaIoBaseUpload(
                        io.BytesIO(file.read()),
                        mimetype=file.content_type,
                        resumable=False
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
                        document_name=category.name,
                        document_category=category,
                        file_path=upload["webViewLink"],
                        google_drive_id=upload["id"],
                        file_size=file.size,
                        expiry_date=None,
                        status="Pending",
                        semester=deliverable.semester,
                        deliverable=deliverable
                    )
                    success_count += 1

                except Exception as e:
                    print("Upload error:", e)
                    messages.error(request, f"Failed to upload file for {deliverable}.")
            
            if success_count:
                messages.success(request, f"{success_count} deliverable(s) uploaded successfully.")
            return redirect("faculty:faculty_deliverables")

        else:
            messages.error(request, "Please fix errors before uploading.")

    else:
        formset = DocumentFormSet(form_kwargs={'faculty': faculty})

    data["formset"] = formset
    return render(request, "faculty/faculty_deliverables_upload.html", data)




from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from faculty.models import FacultyRequest, RequestType
from base.forms import RequestTypeForm, FacultyRequestForm, AdminFacultyRequestForm



@faculty_required
def faculty_request_list_view(request):
    requests = FacultyRequest.objects.filter(faculty=request.user.faculty_profile).order_by("-created_at")
    return render(request, "faculty/faculty_request_list.html", {"requests": requests})


@faculty_required
def faculty_request_create_view(request):
    if request.method == "POST":
        form = FacultyRequestForm(request.POST)
        if form.is_valid():
            faculty_request = form.save(commit=False)
            faculty_request.faculty = request.user.faculty_profile
            faculty_request.save()
            messages.success(request, "Your request has been submitted.")
            return redirect("faculty:faculty_request_list")
    else:
        form = FacultyRequestForm()

    return render(request, "faculty/faculty_request_form.html", {"form": form})

