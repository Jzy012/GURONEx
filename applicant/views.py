import io
import logging
import mimetypes

logger = logging.getLogger(__name__)

from django.conf import settings
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
    EvaluationAssignment, EvaluationSubmission, EvaluationScore, EvaluationCriteria,
)
from .decorators import applicant_login_required
from base.forms import ApplicantLoginForm
from .forms_upload import ApplicantRequiredOnlyDocumentUploadForm

from base.forms import ApplicantForm, ApplicantDocumentUploadForm
from base.utils.email import (
    send_applicant_submission_receipt,
    send_availability_confirmed_email,
    send_application_withdrawn_email,
    send_evaluation_submitted_email_to_admin,
    send_evaluation_complete_email_to_applicant,
)
from base.models import Account

from faculty.models import DocumentCategory
from services.google_drive_service import CentralGoogleDriveService
from services.applicant_document_service import process_applicant_documents_sync
from notifications.services import ROLE_ADMIN_GROUP, log_activity, notify_role
from adminhub.models import CreatedAccountLog



def applicant_home(request):
    return render(request, "applicants/applicant_home.html")



def applicant_apply(request):
    from adminhub.models import RegistrationSettings
    if not RegistrationSettings.get_solo().is_registration_open:
        return render(request, 'applicants/applicant_registration_closed.html')

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
            # Read file bytes before entering the transaction so InMemoryUploadedFile
            # objects are consumed while still in scope.
            docs_payload = []
            for form, category in zip(forms, doc_categories):
                file = form.cleaned_data["file"]
                if file:
                    docs_payload.append({
                        "name": file.name,
                        "content": file.read(),
                        "content_type": file.content_type,
                        "size": file.size,
                        "document_category_id": category.id,
                        "expiry_date": form.cleaned_data.get("expiry_date"),
                        "remarks": form.cleaned_data.get("remarks", ""),
                    })

            try:
                with transaction.atomic():
                    applicant = basic_form.save()

                    # Upload each document synchronously. Any Drive error raises here,
                    # rolling back the transaction so no orphaned records are created.
                    process_applicant_documents_sync(applicant.id, docs_payload)

                    ApplicantTimeline.objects.create(
                        applicant=applicant,
                        action="Submitted application",
                        note="Initial application and document upload.",
                    )
            except Exception:
                logger.exception(
                    "Registration failed during document upload for form data: "
                    "%s", basic_form.cleaned_data.get("email", "<unknown>")
                )
                context = {
                    "basic_form": basic_form,
                    "forms": forms,
                    "required_docs": required_docs,
                    "upload_error": (
                        "One or more documents could not be uploaded. "
                        "Please try again or contact support if the issue persists."
                    ),
                }
                return render(request, "applicants/applicant_apply.html", context)

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
                if applicant.is_archived:
                    return redirect("applicants:inactive")
                request.session["applicant_pk"] = applicant.pk
                request.session.cycle_key()
                return redirect("applicants:dashboard")
    else:
        form = ApplicantLoginForm()

    return render(request, "applicants/applicant_check_status.html", {"form": form, "support_email": getattr(settings, "SUPPORT_EMAIL", "")})



def applicant_logout(request):
    request.session.pop("applicant_pk", None)
    messages.success(request, "Logged out.")
    return redirect("applicants:check_status")



def applicant_inactive(request):
    return render(request, "applicants/applicant_inactive.html", {
        "support_email": getattr(settings, "SUPPORT_EMAIL", ""),
    })



@applicant_login_required
def applicant_dashboard(request):
    applicant = get_object_or_404(Applicant, pk=request.session["applicant_pk"])
    docs = applicant.documents.filter(is_archived=False).select_related("document_category").order_by("-submitted_at")
    required_docs = ApplicantRequiredDocument.objects.select_related("document_category").all()
    timeline = applicant.timeline.order_by("timestamp")

    step_date_fields = {
        "demo_scheduled": "demo_scheduled_date",
        "evaluation": "evaluation_date",
        "psych_test": "psych_test_date",
        "hired": "hired_date",
        "rejected": "rejected_date",
    }

    required_status_dates = {
        "demo_scheduled",
        "psych_test",
    }

    STEPPER_STATUSES = [
        ("pending", "Initial Review"),
        ("demo_scheduled", "Demo & Interview"),
        ("evaluation", "Evaluation"),
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

    if applicant.status in ["hired", "rejected", "withdrawn"]:
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
    from datetime import timedelta
    ctx: dict = {}
    status = applicant.status

    # Demo & Interview – show latest pending reschedule request + availability actions
    if status in ('demo_scheduled', 'for_interview'):
        pending_reschedule = (
            applicant.reschedule_requests
            .filter(step__in=('demo_scheduled', 'for_interview'), status=ApplicantRescheduleRequest.STATUS_PENDING)
            .first()
        )
        ctx['pending_reschedule'] = pending_reschedule

        event_date = applicant.demo_scheduled_date or applicant.for_interview_date
        ctx['event_date'] = event_date

        today = timezone.localdate()
        if event_date:
            days_until = (event_date - today).days
            ctx['days_until_event'] = days_until
            # Cancel is disabled within 2 days of the event (today >= event_date - 2 days)
            ctx['can_cancel'] = today < (event_date - timedelta(days=2))
        else:
            ctx['days_until_event'] = None
            ctx['can_cancel'] = True  # no date set yet, allow cancel

        ctx['can_confirm'] = not applicant.confirmed_by_applicant

    # Evaluation – show assignment/submission counts and aggregate score
    if status == 'evaluation':
        import random as _random
        assignments = list(
            applicant.evaluation_assignments
            .prefetch_related('submission__scores__criteria')
            .select_related('submission')
        )
        total_assigned = len(assignments)
        submitted_assignments = [a for a in assignments if a.is_submitted and hasattr(a, 'submission')]
        total_submitted = len(submitted_assignments)
        aggregate_score = sum(a.submission.total_score for a in submitted_assignments) if submitted_assignments else 0
        max_possible = sum(a.submission.max_score for a in submitted_assignments) if submitted_assignments else 0

        # Anonymized per-submission results — no evaluator identity, no comments
        anon_results = []
        for a in submitted_assignments:
            sub = a.submission
            anon_results.append({
                'total_score': sub.total_score,
                'max_score': sub.max_score,
                'percentage': round(sub.total_score / sub.max_score * 100) if sub.max_score else 0,
                'criteria_scores': [
                    {'label': score.criteria.label, 'rating': score.rating}
                    for score in sub.scores.order_by('criteria__order')
                ],
            })
        # Shuffle with deterministic seed so ordering can't be used to infer evaluator identity
        rng = _random.Random(applicant.pk)
        rng.shuffle(anon_results)
        for i, r in enumerate(anon_results):
            r['index'] = i + 1

        # Show earliest pending deadline to the applicant
        earliest_deadline = min(
            (a.submission_deadline for a in assignments
             if a.submission_deadline and not a.is_submitted),
            default=None,
        )

        ctx['eval_total_assigned'] = total_assigned
        ctx['eval_total_submitted'] = total_submitted
        ctx['eval_aggregate_score'] = aggregate_score
        ctx['eval_max_possible'] = max_possible
        ctx['eval_anonymous_results'] = anon_results
        ctx['evaluation_deadline'] = earliest_deadline

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
    preferred_time_raw = request.POST.get('preferred_time', '').strip()

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

    preferred_time = None
    if preferred_time_raw:
        from datetime import time as _time
        try:
            preferred_time = _time.fromisoformat(preferred_time_raw)
        except (ValueError, TypeError):
            pass

    step_label = "Demo & Interview"

    ApplicantRescheduleRequest.objects.create(
        applicant=applicant,
        step=applicant.status,
        reason=reason,
        preferred_date=preferred_date,
        preferred_time=preferred_time,
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


# ---------------------------------------------------------------------------
# Confirm Availability (Demo / Interview step)
# ---------------------------------------------------------------------------

@applicant_login_required
def applicant_confirm_availability(request):
    if request.method != 'POST':
        return redirect('applicants:dashboard')

    applicant = get_object_or_404(Applicant, pk=request.session['applicant_pk'])

    CONFIRMABLE_STEPS = ('demo_scheduled', 'for_interview')
    if applicant.status not in CONFIRMABLE_STEPS:
        messages.error(request, "Availability confirmation is not available at your current step.")
        return redirect('applicants:dashboard')

    if applicant.confirmed_by_applicant:
        messages.info(request, "You have already confirmed your availability.")
        return redirect('applicants:dashboard')

    event_date = applicant.demo_scheduled_date or applicant.for_interview_date
    if not event_date:
        messages.error(request, "No scheduled date found. Please contact the administrator.")
        return redirect('applicants:dashboard')

    applicant.confirmed_by_applicant = True
    applicant.confirmed_at = timezone.now()
    applicant.save(update_fields=['confirmed_by_applicant', 'confirmed_at'])

    ApplicantTimeline.objects.create(
        applicant=applicant,
        action="Confirmed availability",
        note=f"Applicant confirmed attendance for scheduled event on {event_date}.",
    )

    step_label = "Demo & Interview"

    try:
        send_availability_confirmed_email(applicant, step_label, event_date)
    except Exception:
        pass

    try:
        notify_role(
            roles=ROLE_ADMIN_GROUP,
            notification_type='applicant_availability_confirmed',
            title='Applicant confirmed availability',
            message=(
                f"{applicant.first_name} {applicant.last_name} confirmed availability "
                f"for {step_label} on {event_date}."
            ),
            url=reverse('adminhub:applicant_detail', kwargs={'uuid': applicant.uuid}),
            related_type='Applicant',
            related_id=str(applicant.uuid),
            aggregate_key=f"applicant_confirm:{applicant.uuid}",
        )
    except Exception:
        pass

    messages.success(request, "Your availability has been confirmed. The admin has been notified.")
    return redirect('applicants:dashboard')


# ---------------------------------------------------------------------------
# Cancel Application (Voluntary withdrawal)
# ---------------------------------------------------------------------------

@applicant_login_required
def applicant_cancel_application(request):
    if request.method != 'POST':
        return redirect('applicants:dashboard')

    applicant = get_object_or_404(Applicant, pk=request.session['applicant_pk'])

    TERMINAL_STATUSES = ('hired', 'rejected', 'withdrawn')
    if applicant.status in TERMINAL_STATUSES:
        messages.error(request, "Your application cannot be cancelled at this stage.")
        return redirect('applicants:dashboard')

    # Enforce 2-day restriction for scheduled steps
    SCHEDULED_STEPS = ('demo_scheduled', 'for_interview')
    if applicant.status in SCHEDULED_STEPS:
        from datetime import timedelta
        event_date = applicant.demo_scheduled_date or applicant.for_interview_date
        if event_date and timezone.localdate() >= (event_date - timedelta(days=2)):
            messages.error(
                request,
                "Application cancellation is no longer available within 2 days of the scheduled event. "
                "Please contact the administrator if you have concerns regarding your attendance.",
            )
            return redirect('applicants:dashboard')

    cancellation_reason = request.POST.get('cancellation_reason', '').strip()

    with transaction.atomic():
        applicant.withdrawn_from_status = applicant.status
        applicant.status = 'withdrawn'
        applicant.cancelled_by_applicant = True
        applicant.cancelled_at = timezone.now()
        applicant.cancellation_reason = cancellation_reason
        applicant.save(update_fields=[
            'status', 'withdrawn_from_status',
            'cancelled_by_applicant', 'cancelled_at', 'cancellation_reason',
        ])

        ApplicantTimeline.objects.create(
            applicant=applicant,
            action="Withdrew application",
            note=f"Reason: {cancellation_reason[:200]}" if cancellation_reason else "No reason provided.",
        )

    try:
        send_application_withdrawn_email(applicant, cancellation_reason)
    except Exception:
        pass

    try:
        notify_role(
            roles=ROLE_ADMIN_GROUP,
            notification_type='applicant_application_withdrawn',
            title='Applicant withdrew application',
            message=(
                f"{applicant.first_name} {applicant.last_name} withdrew their application."
                + (f" Reason: {cancellation_reason[:100]}" if cancellation_reason else "")
            ),
            url=reverse('adminhub:applicant_detail', kwargs={'uuid': applicant.uuid}),
            related_type='Applicant',
            related_id=str(applicant.uuid),
            aggregate_key=f"applicant_withdraw:{applicant.uuid}",
        )
    except Exception:
        pass

    messages.success(request, "Your application has been withdrawn. A confirmation email has been sent.")
    return redirect('applicants:dashboard')


# ---------------------------------------------------------------------------
# Public: Evaluator form (token-based, no authentication required)
# ---------------------------------------------------------------------------

def evaluate_form(request, token):
    assignment = get_object_or_404(EvaluationAssignment, token=token)

    if assignment.is_submitted:
        return render(request, 'evaluation/evaluate_form.html', {
            'done': True,
            'reason': 'already_submitted',
            'applicant': assignment.applicant,
            'evaluator_name': assignment.evaluator_display_name,
        })

    if assignment.is_expired:
        reason = 'deadline_passed' if assignment.is_deadline_passed else 'expired'
        return render(request, 'evaluation/evaluate_form.html', {
            'done': True,
            'reason': reason,
            'applicant': assignment.applicant,
            'evaluator_name': assignment.evaluator_display_name,
            'assignment': assignment,
        })

    applicant = assignment.applicant
    criteria = EvaluationCriteria.objects.filter(is_active=True).order_by('order', 'label')

    if request.method == 'POST':
        scores = {}
        rating_errors = []
        for criterion in criteria:
            rating_str = request.POST.get(f'rating_{criterion.pk}', '').strip()
            if not rating_str:
                rating_errors.append(criterion.label)
                continue
            try:
                rating = int(rating_str)
                if rating not in range(1, 6):
                    rating_errors.append(criterion.label)
                else:
                    scores[criterion.pk] = {
                        'rating': rating,
                        'comments': request.POST.get(f'comments_{criterion.pk}', '').strip(),
                    }
            except ValueError:
                rating_errors.append(criterion.label)

        if rating_errors:
            return render(request, 'evaluation/evaluate_form.html', {
                'assignment': assignment,
                'applicant': applicant,
                'criteria': criteria,
                'post': request.POST,
                'form_errors': [f"Please rate all criteria. Missing or invalid: {', '.join(rating_errors)}."],
            })

        with transaction.atomic():
            submission = EvaluationSubmission.objects.create(
                assignment=assignment,
                summary=request.POST.get('summary', '').strip(),
                justification=request.POST.get('justification', '').strip(),
            )
            for criterion_pk, data in scores.items():
                EvaluationScore.objects.create(
                    submission=submission,
                    criteria_id=criterion_pk,
                    rating=data['rating'],
                    comments=data['comments'],
                )
            assignment.is_submitted = True
            assignment.submitted_at = timezone.now()
            assignment.save(update_fields=['is_submitted', 'submitted_at'])

            ApplicantTimeline.objects.create(
                applicant=applicant,
                action=f"Evaluation submitted by {assignment.evaluator_display_name}",
            )

        evaluator_name = assignment.evaluator_display_name

        try:
            base_url = getattr(settings, 'SITE_BASE_URL', '').rstrip('/')
            admin_path = reverse('adminhub:applicant_detail', kwargs={'uuid': str(applicant.uuid)})
            admin_url = f"{base_url}{admin_path}" if base_url else request.build_absolute_uri(admin_path)
            admin_emails = list(
                Account.objects.filter(role__in=['admin', 'system_admin'], is_active=True)
                .values_list('email', flat=True)
            )
            send_evaluation_submitted_email_to_admin(admin_emails, evaluator_name, applicant, admin_url)
        except Exception:
            pass

        try:
            notify_role(
                roles=ROLE_ADMIN_GROUP,
                notification_type='evaluation_submitted',
                title=f"Evaluation submitted: {applicant.full_name}",
                message=f"{evaluator_name} submitted their evaluation for {applicant.full_name}.",
                url=reverse('adminhub:applicant_detail', kwargs={'uuid': str(applicant.uuid)}),
                related_type='EvaluationAssignment',
                related_id=str(assignment.pk),
            )
        except Exception:
            pass

        # Check if this was the last pending submission.
        # "Complete" = no assignment is still active (not submitted + not expired).
        _all_assignments = list(applicant.evaluation_assignments.all())
        _still_pending = [
            a for a in _all_assignments
            if not a.is_submitted and not a.is_expired
        ]
        _any_submitted = any(a.is_submitted for a in _all_assignments)
        if not _still_pending and _any_submitted:
            try:
                send_evaluation_complete_email_to_applicant(applicant)
            except Exception:
                logger.exception(
                    "Failed to send evaluation complete email to applicant %s",
                    applicant.applicant_id,
                )
            try:
                notify_role(
                    roles=ROLE_ADMIN_GROUP,
                    notification_type='evaluation_submitted',
                    title=f"Evaluation complete: {applicant.full_name}",
                    message=(
                        f"All evaluations for {applicant.full_name} have been submitted. "
                        "The applicant is ready to advance."
                    ),
                    url=reverse('adminhub:applicant_detail', kwargs={'uuid': str(applicant.uuid)}),
                    related_type='Applicant',
                    related_id=str(applicant.pk),
                )
            except Exception:
                pass

        return render(request, 'evaluation/evaluate_form.html', {
            'done': True,
            'reason': 'submitted_now',
            'applicant': applicant,
            'evaluator_name': evaluator_name,
        })

    return render(request, 'evaluation/evaluate_form.html', {
        'assignment': assignment,
        'applicant': applicant,
        'criteria': criteria,
    })
