import io
import mimetypes

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.forms import formset_factory, BaseFormSet
from django.db import transaction
from django.http import HttpResponse, StreamingHttpResponse, Http404
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

from .models import Applicant, ApplicantDocument, ApplicantRequiredDocument, ApplicantTimeline
from .decorators import applicant_login_required
from base.forms import ApplicantLoginForm
from .forms_upload import ApplicantRequiredOnlyDocumentUploadForm

from base.forms import ApplicantForm, ApplicantDocumentUploadForm
from base.utils.email import send_applicant_submission_receipt

from faculty.models import DocumentCategory
from services.google_drive_service import CentralGoogleDriveService
from services.applicant_document_service import process_applicant_documents_sync
from applicant.tasks import process_applicant_documents_task



def applicant_home(request):
    return render(request, "applicants/applicant_home.html")



def applicant_apply(request):
    required_docs = ApplicantRequiredDocument.objects.all()
    doc_categories = [doc.document_category for doc in required_docs]

    if request.method == "POST":
        basic_form = ApplicantForm(request.POST)
        forms = [
            ApplicantDocumentUploadForm(
                request.POST,
                request.FILES,
                prefix=f"doc{idx}",
                fixed_document_category=doc_cat,
                index=idx,
            )
            for idx, doc_cat in enumerate(doc_categories)
        ]
        valid = all(form.is_valid() for form in forms) and basic_form.is_valid()
        if valid:
            with transaction.atomic():
                applicant = basic_form.save()

                docs_payload = []
                for form, category in zip(forms, doc_categories):
                    file = form.cleaned_data["file"]
                    expiry = form.cleaned_data.get("expiry_date")
                    remarks = form.cleaned_data.get("remarks", "")

                    if file:
                        docs_payload.append(
                            {
                                "name": file.name,
                                "content": file.read(),          # bytes
                                "content_type": file.content_type,
                                "size": file.size,
                                "document_category_id": category.id,
                                "expiry_date": expiry,
                                "remarks": remarks,
                            }
                        )

                ApplicantTimeline.objects.create(
                    applicant=applicant,
                    action="Submitted application",
                    note="Initial application and document upload.",
                )

            try:
                process_applicant_documents_task.delay(applicant.id, docs_payload)
            except Exception:
                process_applicant_documents_sync(applicant.id, docs_payload)

            try:
                send_applicant_submission_receipt(applicant)
            except Exception:
                pass

            messages.success(
                request,
                "Application submitted! A copy has been sent to your email. "
                "Please keep your Applicant ID for future status checks.",
            )
            return redirect("applicants:registration_confirmed")
        else:
            messages.error(request, "Please correct errors in your form(s).")
    else:
        basic_form = ApplicantForm()
        forms = [
            ApplicantDocumentUploadForm(
                prefix=f"doc{idx}",
                fixed_document_category=doc_cat,
                index=idx,
            )
            for idx, doc_cat in enumerate(doc_categories)
        ]

    context = {
        "basic_form": basic_form,
        "forms": forms,
        "required_docs": required_docs,
    }
    return render(request, "applicants/applicant_apply.html", context)



def applicant_registration_confirmed(request):
    return render(request, "applicants/applicant_registration_confirmed.html")



def applicant_login(request):
    if request.method == "POST":
        form = ApplicantLoginForm(request.POST)
        if form.is_valid():
            applicant_id = form.cleaned_data["applicant_id"].strip()
            email = form.cleaned_data["email"].strip()
            try:
                applicant = Applicant.objects.get(applicant_id=applicant_id, email=email)
            except Applicant.DoesNotExist:
                messages.error(request, "Applicant not found. Please check your Applicant ID and email.")
            else:
                request.session["applicant_pk"] = applicant.pk
                request.session.cycle_key()
                return redirect("applicants:dashboard")
    else:
        form = ApplicantLoginForm()

    return render(request, "applicants/applicant_check_status.html", {"form": form})



def applicant_logout(request):
    request.session.pop("applicant_pk", None)
    messages.success(request, "Logged out.")
    return redirect("applicants:check_status")



@applicant_login_required
def applicant_dashboard(request):
    applicant = get_object_or_404(Applicant, pk=request.session["applicant_pk"])
    docs = applicant.documents.select_related("document_category").order_by("-submitted_at")
    required_docs = ApplicantRequiredDocument.objects.select_related("document_category").all()
    timeline = applicant.timeline.order_by("timestamp")

    STEPPER_STATUSES = [
        ("pending", "Pending"),
        ("demo_scheduled", "Demo Scheduled"),
        ("for_interview", "For Interview"),
        ("psych_test", "Psych Test"),
        ("hired", "Hired"),
        ("failed", "Failed"),
    ]
    stepper = []
    found_active = False
    for value, label in STEPPER_STATUSES:
        is_active = (applicant.status == value)
        stepper.append({
            "value": value,
            "label": label,
            "completed": (not found_active and not is_active),
            "active": is_active,
        })
        if is_active:
            found_active = True

    return render(request, "applicants/applicant_dashboard.html", {
        "applicant": applicant,
        "documents": docs,
        "required_docs": required_docs,
        "timeline": timeline,
        "stepper": stepper,
    })



class IndexedFormSet(BaseFormSet):
    def _construct_form(self, i, **kwargs):
        kwargs["index"] = i
        return super()._construct_form(i, **kwargs)



@applicant_login_required
def applicant_upload_documents(request):
    applicant = get_object_or_404(Applicant, pk=request.session["applicant_pk"])

    if applicant.status in ["hired", "failed"]:
        messages.error(request, "Cannot upload documents at this stage.")
        return redirect("applicants:dashboard")

    DocumentFormSet = formset_factory(
        ApplicantRequiredOnlyDocumentUploadForm,
        formset=IndexedFormSet,
        extra=1,
        max_num=10,
        validate_max=True,
    )

    if request.method == "POST":
        formset = DocumentFormSet(request.POST, request.FILES)

        if formset.is_valid():
            non_empty = 0
            for form in formset:
                cd = form.cleaned_data
                if cd.get("document_category") or cd.get("file") or cd.get("expiry_date") or cd.get("remarks"):
                    non_empty += 1

            if non_empty == 0:
                formset._non_form_errors = formset.error_class(
                    ["Please fill out at least one document card before submitting."]
                )
                return render(request, "applicants/applicant_upload_documents.html", {
                    "applicant": applicant,
                    "formset": formset,
                })

            service = CentralGoogleDriveService()
            success_count = 0

            for form in formset:
                cd = form.cleaned_data
                category = cd.get("document_category")
                file = cd.get("file")
                expiry = cd.get("expiry_date")
                remarks = cd.get("remarks", "")

                if not category and not file and not expiry and not remarks:
                    continue

                media = MediaIoBaseUpload(
                    io.BytesIO(file.read()),
                    mimetype=file.content_type,
                    resumable=False,
                )
                upload = service.service.files().create(
                    body={"name": file.name, "parents": [applicant.google_drive_folder_id]},
                    media_body=media,
                    fields="id,webViewLink",
                ).execute()

                ApplicantDocument.objects.create(
                    applicant=applicant,
                    document_category=category,
                    file_path=upload["webViewLink"],
                    google_drive_id=upload["id"],
                    file_size=file.size,
                    expiry_date=expiry,
                    remarks=remarks,
                    status="Pending",
                )
                ApplicantTimeline.objects.create(
                    applicant=applicant,
                    action="Uploaded document",
                    note=f"Uploaded document: {category.name}",
                )
                success_count += 1

            messages.success(request, f"{success_count} document(s) uploaded successfully.")
            return redirect("applicants:dashboard")

        messages.error(request, "Please fix the errors in the form before uploading.")
    else:
        formset = DocumentFormSet()

    return render(request, "applicants/applicant_upload_documents.html", {
        "applicant": applicant,
        "formset": formset,
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


@applicant_login_required
def applicant_download_document(request, pk):
    """
    Streams an applicant document stored on Google Drive.
    Access is restricted to the logged-in applicant via session.
    Query param inline=1 allows inline view for PDF/images.
    """
    doc = get_object_or_404(ApplicantDocument, pk=pk)

    applicant_pk = request.session.get("applicant_pk")
    if doc.applicant_id != applicant_pk:
        raise Http404("Document not found.")

    file_id = doc.google_drive_id
    drive = CentralGoogleDriveService()
    want_inline = request.GET.get('inline', '0').lower() in ('1', 'true', 'yes')

    try:
        meta = drive.service.files().get(fileId=file_id, fields='mimeType, name, size').execute()
        mime_type = meta.get('mimeType')
        name_on_drive = meta.get('name') or f'document_{doc.id}'
    except Exception:
        raise Http404("Could not retrieve file metadata from Google Drive.")

    def _finalize_response(resp: HttpResponse):
        resp['X-Frame-Options'] = 'SAMEORIGIN'
        resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

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
