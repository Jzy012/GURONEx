from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse


def send_applicant_status_email(applicant, new_status):
    subject = f"[LINANG] Application Status Update: {new_status}"
    # Build status check URL (relative); you can prepend domain in settings if needed
    status_url = reverse('applicants:check_status')
    message = (
        f"Hello {applicant.first_name},\n\n"
        f"Your application status has changed to: {new_status}.\n"
        f"You can check your status any time at: {status_url}\n\n"
        f"If you have any questions, please reply to this email.\n\n"
        f"Regards,\nLINANG Team"
    )
    from_email = settings.DEFAULT_FROM_EMAIL
    send_mail(
        subject,
        message,
        from_email,
        [applicant.email],
        fail_silently=False,
    )


from django.conf import settings
from django.urls import reverse
from base.utils.email_base import send_html_email  # your Brevo helper
from applicant.models import Applicant


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