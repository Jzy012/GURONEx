import io
import mimetypes

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.forms import formset_factory, BaseFormSet
from django.db import transaction
from django.http import HttpResponse, StreamingHttpResponse, Http404, JsonResponse
from django.urls import reverse
from django.utils import timezone
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

from .models import (
    Applicant, ApplicantDocument, ApplicantRequiredDocument, ApplicantTimeline,
    ApplicantRescheduleRequest, ApplicantStepDocument, ApplicantSalaryRequirementConfig,
)
from .decorators import applicant_login_required
from base.forms import ApplicantLoginForm
from .forms_upload import ApplicantRequiredOnlyDocumentUploadForm

from base.forms import ApplicantForm, ApplicantDocumentUploadForm
from base.utils.email import send_applicant_submission_receipt

from faculty.models import DocumentCategory
from services.google_drive_service import CentralGoogleDriveService
from services.applicant_document_service import process_applicant_documents_sync
from applicant.tasks import process_applicant_documents_task
from notifications.services import ROLE_ADMIN_GROUP, log_activity, notify_role
from adminhub.models import CreatedAccountLog



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
                notify_role(
                    roles=ROLE_ADMIN_GROUP,
                    notification_type='applicant_submitted',
                    title='New applicant submission',
                    message=(
                        f"{applicant.first_name} {applicant.last_name} submitted a new application."
                    ),
                    url=reverse('adminhub:applicant_detail', kwargs={'uuid': applicant.uuid}),
                    related_type='Applicant',
                    related_id=str(applicant.uuid),
                    aggregate_key=f"applicant_submission:{applicant.uuid}",
                )
                log_activity(
                    action='applicant_submitted',
                    target_type='Applicant',
                    target_id=str(applicant.uuid),
                    details={
                        'target_name': applicant.full_name,
                        'applicant_id': applicant.applicant_id,
                        'email': applicant.email,
                    },
                )
            except Exception:
                pass

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
    docs = applicant.documents.filter(is_archived=False).select_related("document_category").order_by("-submitted_at")
    required_docs = ApplicantRequiredDocument.objects.select_related("document_category").all()
    timeline = applicant.timeline.order_by("timestamp")

    step_date_fields = {
        "demo_scheduled": "demo_scheduled_date",
        "psych_test": "psych_test_date",
        "hired": "hired_date",
        "rejected": "rejected_date",
    }

    required_status_dates = {
        "demo_scheduled",
        "psych_test",
    }

    STEPPER_STATUSES = [
        ("pending", "Pending"),
        ("demo_scheduled", "Demo & Interview"),
        ("psych_test", "Psych Test"),
        ("contract_of_service", "Contract of Service"),
        ("first_salary_requirements", "First Salary Requirements"),
        ("hired", "Hired"),
    ]

    # Normalise legacy for_interview → demo_scheduled for stepper display
    display_status = "demo_scheduled" if applicant.status == "for_interview" else applicant.status

    if display_status == "rejected":
        status_values = [value for value, _label in STEPPER_STATUSES if value != "rejected"]
        rejected_source_status = applicant.rejected_from_status or "pending"
        # Legacy: map for_interview to demo_scheduled
        if rejected_source_status == "for_interview":
            rejected_source_status = "demo_scheduled"
        try:
            reached_idx = status_values.index(rejected_source_status)
        except ValueError:
            reached_idx = 0

        STEPPER_STATUSES = STEPPER_STATUSES[:reached_idx + 1] + [("rejected", "Rejected")]

    stepper = []
    found_active = False
    for value, label in STEPPER_STATUSES:
        is_active = (display_status == value)
        step_date = None
        date_field_name = step_date_fields.get(value)
        if date_field_name:
            step_date = getattr(applicant, date_field_name, None)
        if value == "pending":
            step_date = applicant.created_at.date()
        stepper.append({
            "value": value,
            "label": label,
            "completed": (not found_active and not is_active),
            "active": is_active,
            "date": step_date,
            "requires_date": value in required_status_dates,
        })
        if is_active:
            found_active = True

    created_account_credentials = None
    if applicant.status == "hired" and applicant.account_created:
        latest_log = (
            CreatedAccountLog.objects
            .filter(applicant=applicant)
            .order_by("-created_at")
            .first()
        )
        if latest_log:
            created_account_credentials = {
                "faculty_email": latest_log.faculty_email,
                "password": latest_log.password,
            }

    step_ctx = _get_dashboard_step_context(applicant)

    return render(request, "applicants/applicant_dashboard.html", {
        "applicant": applicant,
        "documents": docs,
        "required_docs": required_docs,
        "timeline": timeline,
        "stepper": stepper,
        "created_account_credentials": created_account_credentials,
        **step_ctx,
    })



class IndexedFormSet(BaseFormSet):
    def _construct_form(self, i, **kwargs):
        kwargs["index"] = i
        return super()._construct_form(i, **kwargs)



@applicant_login_required
def applicant_upload_documents(request):
    applicant = get_object_or_404(Applicant, pk=request.session["applicant_pk"])

    if applicant.status in ["hired", "rejected"]:
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


# ---------------------------------------------------------------------------
# Updated dashboard – pass step-specific context
# ---------------------------------------------------------------------------

def _get_dashboard_step_context(applicant: Applicant) -> dict:
    """Builds the step-specific context injected into the applicant dashboard."""
    ctx: dict = {}
    status = applicant.status

    # Demo & Interview – show latest pending reschedule request
    if status in ('demo_scheduled', 'for_interview'):
        pending_reschedule = (
            applicant.reschedule_requests
            .filter(step__in=('demo_scheduled', 'for_interview'), status=ApplicantRescheduleRequest.STATUS_PENDING)
            .first()
        )
        ctx['pending_reschedule'] = pending_reschedule

    # Psych test – show uploaded doc + deadline
    if status == 'psych_test':
        psych_doc = (
            applicant.step_documents
            .filter(step_type=ApplicantStepDocument.STEP_PSYCH_TEST)
            .first()
        )
        ctx['psych_doc'] = psych_doc
        ctx['psych_test_deadline'] = applicant.psych_test_deadline

    # Contract of Service – show admin contract + signed contract
    if status == 'contract_of_service':
        admin_contract = (
            applicant.step_documents
            .filter(step_type=ApplicantStepDocument.STEP_CONTRACT_ADMIN)
            .order_by('-uploaded_at')
            .first()
        )
        signed_contract = (
            applicant.step_documents
            .filter(step_type=ApplicantStepDocument.STEP_CONTRACT_SIGNED)
            .order_by('-uploaded_at')
            .first()
        )
        ctx['admin_contract'] = admin_contract
        ctx['signed_contract'] = signed_contract
        ctx['contract_deadline'] = applicant.contract_of_service_deadline

    # First Salary Requirements – show config + per-requirement upload status
    if status == 'first_salary_requirements':
        configs = list(
            ApplicantSalaryRequirementConfig.objects
            .filter(applicant=applicant)
            .select_related('document_category')
        )
        uploaded_docs = {
            doc.document_category_id: doc
            for doc in applicant.step_documents.filter(
                step_type=ApplicantStepDocument.STEP_SALARY_REQUIREMENT
            ).order_by('-uploaded_at')
        }
        salary_checklist = [
            {
                'config': cfg,
                'uploaded_doc': uploaded_docs.get(cfg.document_category_id),
            }
            for cfg in configs
        ]
        ctx['salary_checklist'] = salary_checklist
        ctx['first_salary_deadline'] = applicant.first_salary_deadline
        ctx['all_salary_submitted'] = bool(configs) and all(
            uploaded_docs.get(c.document_category_id) for c in configs if c.is_required
        )

    return ctx


# ---------------------------------------------------------------------------
# Reschedule Request (Demo / Interview steps)
# ---------------------------------------------------------------------------

@applicant_login_required
def applicant_request_reschedule(request):
    if request.method != 'POST':
        return redirect('applicants:dashboard')

    applicant = get_object_or_404(Applicant, pk=request.session['applicant_pk'])

    RESCHEDULABLE_STEPS = ('demo_scheduled', 'for_interview')
    if applicant.status not in RESCHEDULABLE_STEPS:
        messages.error(request, "Reschedule requests are not available at your current step.")
        return redirect('applicants:dashboard')

    # Only one pending request at a time
    if applicant.reschedule_requests.filter(
        step__in=('demo_scheduled', 'for_interview'),
        status=ApplicantRescheduleRequest.STATUS_PENDING,
    ).exists():
        messages.warning(request, "You already have a pending reschedule request. Please wait for admin review.")
        return redirect('applicants:dashboard')

    reason = request.POST.get('reason', '').strip()
    preferred_date_raw = request.POST.get('preferred_date', '').strip()

    if not reason:
        messages.error(request, "Please provide a reason for your reschedule request.")
        return redirect('applicants:dashboard')

    preferred_date = None
    if preferred_date_raw:
        from datetime import datetime
        try:
            preferred_date = datetime.strptime(preferred_date_raw, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid preferred date format.")
            return redirect('applicants:dashboard')

    step_label = "Demo & Interview"

    ApplicantRescheduleRequest.objects.create(
        applicant=applicant,
        step=applicant.status,
        reason=reason,
        preferred_date=preferred_date,
    )

    ApplicantTimeline.objects.create(
        applicant=applicant,
        action="Requested reschedule",
        note=f"Reason: {reason[:200]}",
    )

    try:
        notify_role(
            roles=ROLE_ADMIN_GROUP,
            notification_type='applicant_reschedule_requested',
            title='Reschedule request submitted',
            message=(
                f"{applicant.first_name} {applicant.last_name} requested a reschedule "
                f"for {step_label}."
            ),
            url=reverse('adminhub:applicant_detail', kwargs={'uuid': applicant.uuid}),
            related_type='Applicant',
            related_id=str(applicant.uuid),
            aggregate_key=f"applicant_reschedule:{applicant.uuid}",
        )
    except Exception:
        pass

    messages.success(request, "Your reschedule request has been submitted. The admin will review it shortly.")
    return redirect('applicants:dashboard')


# ---------------------------------------------------------------------------
# Psych Test Upload
# ---------------------------------------------------------------------------

@applicant_login_required
def applicant_upload_psych_test(request):
    if request.method != 'POST':
        return redirect('applicants:dashboard')

    applicant = get_object_or_404(Applicant, pk=request.session['applicant_pk'])

    if applicant.status != 'psych_test':
        messages.error(request, "Psych test upload is not available at your current step.")
        return redirect('applicants:dashboard')

    existing = applicant.step_documents.filter(
        step_type=ApplicantStepDocument.STEP_PSYCH_TEST,
        status=ApplicantStepDocument.STATUS_PENDING,
    ).first()
    if existing:
        messages.warning(request, "You already have a psych test document pending review. Please wait for admin feedback.")
        return redirect('applicants:dashboard')

    file = request.FILES.get('psych_test_file')
    if not file:
        messages.error(request, "Please select a file to upload.")
        return redirect('applicants:dashboard')

    max_size = 15 * 1024 * 1024
    if file.size > max_size:
        messages.error(request, "File size must not exceed 15 MB.")
        return redirect('applicants:dashboard')

    allowed_types = {'application/pdf', 'image/jpeg', 'image/png'}
    if file.content_type not in allowed_types:
        messages.error(request, "Only PDF, JPG, or PNG files are allowed.")
        return redirect('applicants:dashboard')

    try:
        service = CentralGoogleDriveService()
        media = MediaIoBaseUpload(io.BytesIO(file.read()), mimetype=file.content_type, resumable=False)
        upload = service.service.files().create(
            body={'name': file.name, 'parents': [applicant.google_drive_folder_id]},
            media_body=media,
            fields='id,webViewLink',
        ).execute()

        ApplicantStepDocument.objects.create(
            applicant=applicant,
            step_type=ApplicantStepDocument.STEP_PSYCH_TEST,
            file_path=upload['webViewLink'],
            google_drive_id=upload['id'],
            file_size=file.size,
        )
        ApplicantTimeline.objects.create(
            applicant=applicant,
            action="Uploaded psych test document",
        )
    except Exception:
        messages.error(request, "Upload failed. Please try again.")
        return redirect('applicants:dashboard')

    try:
        notify_role(
            roles=ROLE_ADMIN_GROUP,
            notification_type='applicant_step_document_uploaded',
            title='Psych test document uploaded',
            message=f"{applicant.first_name} {applicant.last_name} uploaded their psych test document.",
            url=reverse('adminhub:applicant_detail', kwargs={'uuid': applicant.uuid}),
            related_type='Applicant',
            related_id=str(applicant.uuid),
            aggregate_key=f"applicant_psych_upload:{applicant.uuid}",
        )
    except Exception:
        pass

    messages.success(request, "Psych test document uploaded successfully. Please wait for admin review.")
    return redirect('applicants:dashboard')


# ---------------------------------------------------------------------------
# Contract – download admin contract + upload signed version
# ---------------------------------------------------------------------------

@applicant_login_required
def applicant_download_step_document(request, pk):
    """Streams a step document (e.g. admin-uploaded contract) to the applicant."""
    doc = get_object_or_404(ApplicantStepDocument, pk=pk)

    if doc.applicant_id != request.session.get('applicant_pk'):
        raise Http404("Document not found.")

    drive = CentralGoogleDriveService()
    want_inline = request.GET.get('inline', '0').lower() in ('1', 'true', 'yes')

    try:
        meta = drive.service.files().get(fileId=doc.google_drive_id, fields='mimeType, name').execute()
        mime_type = meta.get('mimeType')
        name_on_drive = meta.get('name') or f'document_{doc.pk}'
    except Exception:
        raise Http404("Could not retrieve file from Google Drive.")

    def _finalize(resp):
        resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp['X-Frame-Options'] = 'SAMEORIGIN'
        return resp

    if mime_type and mime_type.startswith('application/vnd.google-apps.'):
        exported = drive.service.files().export(fileId=doc.google_drive_id, mimeType='application/pdf').execute()
        disposition = 'inline' if want_inline else 'attachment'
        resp = HttpResponse(exported, content_type='application/pdf')
        resp['Content-Disposition'] = f'{disposition}; filename="{name_on_drive}"'
        return _finalize(resp)

    content_type = mime_type or 'application/octet-stream'
    inline_ok = (content_type == 'application/pdf') or content_type.startswith('image/')
    disposition = 'inline' if (want_inline and inline_ok) else 'attachment'

    response = StreamingHttpResponse(_stream_drive_media(drive, doc.google_drive_id), content_type=content_type)
    response['Content-Disposition'] = f'{disposition}; filename="{name_on_drive}"'
    return _finalize(response)


@applicant_login_required
def applicant_upload_signed_contract(request):
    if request.method != 'POST':
        return redirect('applicants:dashboard')

    applicant = get_object_or_404(Applicant, pk=request.session['applicant_pk'])

    if applicant.status != 'contract_of_service':
        messages.error(request, "Contract upload is not available at your current step.")
        return redirect('applicants:dashboard')

    existing = applicant.step_documents.filter(
        step_type=ApplicantStepDocument.STEP_CONTRACT_SIGNED,
        status=ApplicantStepDocument.STATUS_PENDING,
    ).first()
    if existing:
        messages.warning(request, "Your signed contract is already pending admin review.")
        return redirect('applicants:dashboard')

    file = request.FILES.get('signed_contract_file')
    if not file:
        messages.error(request, "Please select a file to upload.")
        return redirect('applicants:dashboard')

    if file.size > 15 * 1024 * 1024:
        messages.error(request, "File size must not exceed 15 MB.")
        return redirect('applicants:dashboard')

    if file.content_type not in {'application/pdf', 'image/jpeg', 'image/png'}:
        messages.error(request, "Only PDF, JPG, or PNG files are allowed.")
        return redirect('applicants:dashboard')

    try:
        service = CentralGoogleDriveService()
        media = MediaIoBaseUpload(io.BytesIO(file.read()), mimetype=file.content_type, resumable=False)
        upload = service.service.files().create(
            body={'name': file.name, 'parents': [applicant.google_drive_folder_id]},
            media_body=media,
            fields='id,webViewLink',
        ).execute()

        ApplicantStepDocument.objects.create(
            applicant=applicant,
            step_type=ApplicantStepDocument.STEP_CONTRACT_SIGNED,
            file_path=upload['webViewLink'],
            google_drive_id=upload['id'],
            file_size=file.size,
        )
        ApplicantTimeline.objects.create(
            applicant=applicant,
            action="Uploaded signed contract",
        )
    except Exception:
        messages.error(request, "Upload failed. Please try again.")
        return redirect('applicants:dashboard')

    try:
        notify_role(
            roles=ROLE_ADMIN_GROUP,
            notification_type='applicant_step_document_uploaded',
            title='Signed contract uploaded',
            message=f"{applicant.first_name} {applicant.last_name} uploaded their signed contract.",
            url=reverse('adminhub:applicant_detail', kwargs={'uuid': applicant.uuid}),
            related_type='Applicant',
            related_id=str(applicant.uuid),
            aggregate_key=f"applicant_contract_signed:{applicant.uuid}",
        )
    except Exception:
        pass

    messages.success(request, "Signed contract uploaded. The admin has been notified.")
    return redirect('applicants:dashboard')


# ---------------------------------------------------------------------------
# First Salary Requirements – per-requirement upload
# ---------------------------------------------------------------------------

@applicant_login_required
def applicant_upload_salary_requirement(request):
    if request.method != 'POST':
        return redirect('applicants:dashboard')

    applicant = get_object_or_404(Applicant, pk=request.session['applicant_pk'])

    if applicant.status != 'first_salary_requirements':
        messages.error(request, "Salary requirement upload is not available at your current step.")
        return redirect('applicants:dashboard')

    category_id = request.POST.get('document_category_id', '').strip()
    if not category_id:
        messages.error(request, "No document category specified.")
        return redirect('applicants:dashboard')

    config = get_object_or_404(
        ApplicantSalaryRequirementConfig,
        applicant=applicant,
        document_category_id=category_id,
    )

    existing = applicant.step_documents.filter(
        step_type=ApplicantStepDocument.STEP_SALARY_REQUIREMENT,
        document_category_id=category_id,
        status=ApplicantStepDocument.STATUS_PENDING,
    ).first()
    if existing:
        messages.warning(request, f"A document for '{config.document_category.name}' is already pending review.")
        return redirect('applicants:dashboard')

    file = request.FILES.get('salary_req_file')
    if not file:
        messages.error(request, "Please select a file to upload.")
        return redirect('applicants:dashboard')

    if file.size > 15 * 1024 * 1024:
        messages.error(request, "File size must not exceed 15 MB.")
        return redirect('applicants:dashboard')

    if file.content_type not in {'application/pdf', 'image/jpeg', 'image/png'}:
        messages.error(request, "Only PDF, JPG, or PNG files are allowed.")
        return redirect('applicants:dashboard')

    try:
        service = CentralGoogleDriveService()
        media = MediaIoBaseUpload(io.BytesIO(file.read()), mimetype=file.content_type, resumable=False)
        upload = service.service.files().create(
            body={'name': file.name, 'parents': [applicant.google_drive_folder_id]},
            media_body=media,
            fields='id,webViewLink',
        ).execute()

        ApplicantStepDocument.objects.create(
            applicant=applicant,
            step_type=ApplicantStepDocument.STEP_SALARY_REQUIREMENT,
            document_category=config.document_category,
            file_path=upload['webViewLink'],
            google_drive_id=upload['id'],
            file_size=file.size,
        )
        ApplicantTimeline.objects.create(
            applicant=applicant,
            action="Uploaded salary requirement document",
            note=f"Document: {config.document_category.name}",
        )
    except Exception:
        messages.error(request, "Upload failed. Please try again.")
        return redirect('applicants:dashboard')

    try:
        notify_role(
            roles=ROLE_ADMIN_GROUP,
            notification_type='applicant_step_document_uploaded',
            title='Salary requirement document uploaded',
            message=(
                f"{applicant.first_name} {applicant.last_name} uploaded "
                f"'{config.document_category.name}' for first salary requirements."
            ),
            url=reverse('adminhub:applicant_detail', kwargs={'uuid': applicant.uuid}),
            related_type='Applicant',
            related_id=str(applicant.uuid),
            aggregate_key=f"applicant_salary_upload:{applicant.uuid}",
        )
    except Exception:
        pass

    messages.success(request, f"'{config.document_category.name}' uploaded successfully.")
    return redirect('applicants:dashboard')
