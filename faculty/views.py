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



@faculty_required
def faculty_documents_view(request):
    data = get_faculty_data(request)

    return render(request, "faculty/faculty_documents.html", data)




from django.forms import formset_factory
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

    DocumentFormSet = formset_factory(FacultyDocumentUploadForm, extra=3)

    if request.method == 'POST':
        formset = DocumentFormSet(request.POST, request.FILES, form_kwargs={'faculty': faculty})
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
        formset = DocumentFormSet(form_kwargs={'faculty': faculty})

    return render(request, "faculty/faculty_document_upload.html", data, {"formset": formset})






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

