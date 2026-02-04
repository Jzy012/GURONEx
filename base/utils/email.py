from django.conf import settings
from django.urls import reverse
from base.utils.email_base import send_html_email  # Brevo helper
from applicant.models import Applicant

def send_applicant_status_email(applicant: Applicant, new_status: str) -> None:
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