from django.conf import settings
from django.urls import reverse
from base.utils.email_base import send_html_email  # Brevo helper
from applicant.models import Applicant
from datetime import date
from typing import Optional, List

def send_applicant_status_email(applicant: Applicant, new_status: str, status_date: Optional[date] = None) -> None:
    """
    Sends an HTML status update email using the Brevo helper.
    Ensures the status is shown in human-readable form.
    """

    # Convert internal value -> Label ("psych_test" → "Psych Test")
    display_status = applicant.get_status_display()

    subject = f"[LINANG] Application Status Update: {display_status}"

    # Build status check URL
    status_path = reverse("applicants:check_status")
    base_url = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
    status_url = f"{base_url}{status_path}" if base_url else status_path

    # Build full name (same structure as your submission email)
    name_parts = [applicant.first_name]
    if getattr(applicant, "middle_name", None):
        name_parts.append(applicant.middle_name)
    name_parts.append(applicant.last_name)
    if getattr(applicant, "suffix", None):
        name_parts.append(applicant.suffix)
    full_name = " ".join(name_parts)

    context = {
        "applicant": applicant,
        "full_name": full_name,
        "new_status": display_status,  # 👈 USE DISPLAY VERSION HERE
        "status_date": status_date,
        "status_url": status_url,
        "support_email": getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL),
    }

    send_html_email(
        subject=subject,
        to_emails=applicant.email,
        template_name="emails/applicant_status_update.html",
        context=context,
        # Optional:
        # from_name="PUP-SPC LINANG",
    )


def send_applicant_status_rescheduled_email(applicant: Applicant, status_label: str, rescheduled_date: date) -> None:
    """
    Sends an email when the date of the current applicant step is rescheduled.
    """
    subject = f"[LINANG] Schedule Updated: {status_label}"

    status_path = reverse("applicants:check_status")
    base_url = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
    status_url = f"{base_url}{status_path}" if base_url else status_path

    name_parts = [applicant.first_name]
    if getattr(applicant, "middle_name", None):
        name_parts.append(applicant.middle_name)
    name_parts.append(applicant.last_name)
    if getattr(applicant, "suffix", None):
        name_parts.append(applicant.suffix)
    full_name = " ".join(name_parts)

    context = {
        "applicant": applicant,
        "full_name": full_name,
        "status_label": status_label,
        "rescheduled_date": rescheduled_date,
        "status_url": status_url,
        "support_email": getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL),
    }

    send_html_email(
        subject=subject,
        to_emails=applicant.email,
        template_name="emails/applicant_status_rescheduled.html",
        context=context,
    )


def send_applicant_submission_receipt(applicant: Applicant) -> None:
    """
    Sends a receipt email to the applicant with their name and Applicant ID,
    using the Brevo HTML email helper.
    """
    subject = "[LINANG] Application Received"

    # Build full name with middle + suffix
    name_parts = [applicant.first_name]
    if getattr(applicant, "middle_name", None):
        name_parts.append(applicant.middle_name)
    name_parts.append(applicant.last_name)
    if getattr(applicant, "suffix", None):
        name_parts.append(applicant.suffix)
    full_name = " ".join(name_parts)

    # # URL where they can check status (if you still want to include it as a link)
    # status_url = reverse("applicants:check_status")

    context = {
        "applicant": applicant,
        "full_name": full_name,
        "applicant_id": applicant.applicant_id,
        # "status_url": status_url,
        "support_email": getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL),
    }

    send_html_email(
        subject=subject,
        to_emails=applicant.email,
        template_name="emails/applicant_submission_receipt.html",
        context=context,
    )


def _build_full_name(applicant: Applicant) -> str:
    parts = [applicant.first_name]
    if getattr(applicant, "middle_name", None):
        parts.append(applicant.middle_name)
    parts.append(applicant.last_name)
    if getattr(applicant, "suffix", None):
        parts.append(applicant.suffix)
    return " ".join(parts)


def _build_status_url() -> str:
    path = reverse("applicants:check_status")
    base = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
    return f"{base}{path}" if base else path


def _base_context(applicant: Applicant) -> dict:
    return {
        "applicant": applicant,
        "full_name": _build_full_name(applicant),
        "status_url": _build_status_url(),
        "support_email": getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL),
    }


# ---------------------------------------------------------------------------
# Step 1 / 2 – Demo Scheduled / For Interview
# ---------------------------------------------------------------------------

def send_interview_step_email(
    applicant: Applicant,
    step_label: str,
    scheduled_date: Optional[date],
    instructions: str = "",
) -> None:
    ctx = _base_context(applicant)
    ctx.update({
        "step_label": step_label,
        "scheduled_date": scheduled_date,
        "instructions": instructions,
    })
    send_html_email(
        subject=f"[LINANG] {step_label} Scheduled",
        to_emails=applicant.email,
        template_name="emails/applicant_interview_scheduled.html",
        context=ctx,
    )


def send_reschedule_approved_email(
    applicant: Applicant,
    step_label: str,
    old_date: Optional[date],
    new_date: Optional[date],
    admin_note: str = "",
) -> None:
    ctx = _base_context(applicant)
    ctx.update({
        "step_label": step_label,
        "old_date": old_date,
        "new_date": new_date,
        "admin_note": admin_note,
    })
    send_html_email(
        subject=f"[LINANG] Schedule Updated: {step_label}",
        to_emails=applicant.email,
        template_name="emails/applicant_reschedule_approved.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# Step 3 – Psych Test
# ---------------------------------------------------------------------------

def send_psych_test_step_email(
    applicant: Applicant,
    deadline: Optional[date] = None,
) -> None:
    ctx = _base_context(applicant)
    ctx["deadline"] = deadline
    send_html_email(
        subject="[LINANG] Action Required: Psych Test Document Upload",
        to_emails=applicant.email,
        template_name="emails/applicant_psych_test.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# Step 4 – Contract of Service
# ---------------------------------------------------------------------------

def send_contract_of_service_email(
    applicant: Applicant,
    deadline: Optional[date] = None,
) -> None:
    ctx = _base_context(applicant)
    ctx["deadline"] = deadline
    send_html_email(
        subject="[LINANG] Action Required: Sign and Return Your Contract of Service",
        to_emails=applicant.email,
        template_name="emails/applicant_contract_of_service.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# Step 5 – First Salary Requirements
# ---------------------------------------------------------------------------

def send_first_salary_requirements_email(
    applicant: Applicant,
    required_categories: List[str],
    deadline: Optional[date] = None,
) -> None:
    ctx = _base_context(applicant)
    ctx.update({
        "required_categories": required_categories,
        "deadline": deadline,
    })
    send_html_email(
        subject="[LINANG] Action Required: Submit First Salary Requirements",
        to_emails=applicant.email,
        template_name="emails/applicant_first_salary_requirements.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# Step 6 – Hired
# ---------------------------------------------------------------------------

def send_hired_email(applicant: Applicant) -> None:
    ctx = _base_context(applicant)
    send_html_email(
        subject="[LINANG] Congratulations – You Have Been Hired!",
        to_emails=applicant.email,
        template_name="emails/applicant_hired.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# Rejection with custom message
# ---------------------------------------------------------------------------

def send_rejection_email(applicant: Applicant, rejection_message: str = "") -> None:
    ctx = _base_context(applicant)
    ctx["rejection_message"] = rejection_message
    send_html_email(
        subject="[LINANG] Application Status Update",
        to_emails=applicant.email,
        template_name="emails/applicant_rejected.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# Availability confirmed (applicant confirms attendance)
# ---------------------------------------------------------------------------

def send_availability_confirmed_email(
    applicant: Applicant,
    step_label: str,
    event_date,
) -> None:
    ctx = _base_context(applicant)
    ctx.update({
        "step_label": step_label,
        "event_date": event_date,
    })
    send_html_email(
        subject=f"[LINANG] Availability Confirmed: {step_label}",
        to_emails=applicant.email,
        template_name="emails/applicant_availability_confirmed.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# Application withdrawn (applicant cancels)
# ---------------------------------------------------------------------------

def send_application_withdrawn_email(
    applicant: Applicant,
    cancellation_reason: str = "",
) -> None:
    ctx = _base_context(applicant)
    ctx["cancellation_reason"] = cancellation_reason
    send_html_email(
        subject="[LINANG] Application Withdrawn",
        to_emails=applicant.email,
        template_name="emails/applicant_application_withdrawn.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# Evaluation step emails
# ---------------------------------------------------------------------------

def send_evaluation_step_email(applicant: Applicant, deadline=None) -> None:
    """Notify the applicant that they have entered the Evaluation step."""
    ctx = _base_context(applicant)
    ctx["deadline"] = deadline
    send_html_email(
        subject="[LINANG] Application Status Update: Evaluation",
        to_emails=applicant.email,
        template_name="emails/applicant_evaluation_step.html",
        context=ctx,
    )


def send_evaluation_invite_email(evaluator_name: str, evaluator_email: str,
                                  applicant: Applicant, evaluation_url: str,
                                  expires_at, submission_deadline=None) -> None:
    """Send the tokenized evaluation link to a faculty evaluator."""
    send_html_email(
        subject=f"[LINANG] Evaluation Request: {applicant.full_name}",
        to_emails=evaluator_email,
        template_name="emails/evaluation_invite.html",
        context={
            "evaluator_name": evaluator_name,
            "applicant": applicant,
            "applicant_name": applicant.full_name,
            "evaluation_url": evaluation_url,
            "expires_at": expires_at,
            "submission_deadline": submission_deadline,
        },
    )


def send_evaluation_submitted_email_to_admin(admin_emails, evaluator_name: str,
                                              applicant: Applicant,
                                              admin_url: str) -> None:
    """Notify admins that an evaluator has submitted their evaluation form."""
    send_html_email(
        subject=f"[LINANG] Evaluation Submitted: {applicant.full_name}",
        to_emails=admin_emails,
        template_name="emails/evaluation_submitted_admin.html",
        context={
            "evaluator_name": evaluator_name,
            "applicant": applicant,
            "applicant_name": applicant.full_name,
            "admin_url": admin_url,
        },
    )


def send_evaluation_complete_email_to_applicant(applicant: Applicant) -> None:
    """Notify the applicant that all evaluations have been submitted."""
    ctx = _base_context(applicant)
    send_html_email(
        subject="[LINANG] Application Update: Evaluation Phase Complete",
        to_emails=applicant.email,
        template_name="emails/evaluation_complete_applicant.html",
        context=ctx,
    )