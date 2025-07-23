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
    
    return render(request, "faculty/faculty_documents.html")




from django.forms import formset_factory
from django.shortcuts import render, redirect
from django.contrib import messages
from base.forms import FacultyDocumentUploadForm
from services.google_drive_service import CentralGoogleDriveService
from .models import FacultyDocument
import io
from googleapiclient.http import MediaIoBaseUpload

def faculty_document_upload(request):
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

    return render(request, "faculty/faculty_document_upload.html", {"formset": formset})

