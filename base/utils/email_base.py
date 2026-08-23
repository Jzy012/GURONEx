from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
import logging

import brevo_python
from brevo_python.rest import ApiException

logger = logging.getLogger(__name__)


def build_recipient_list(primary_email, *extra_emails):
    """
    Return a de-duplicated list of recipients, preserving order.

    - Skips empty / whitespace-only values.
    - De-duplicates case-insensitively, keeping the first occurrence.

    Use this so emails can consistently support multiple recipients (e.g. a
    primary address plus a personal/secondary address) without sending
    duplicate notifications when the addresses are identical.
    """
    recipients = []
    seen = set()
    for email in (primary_email, *extra_emails):
        cleaned = (email or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        recipients.append(cleaned)
    return recipients


def get_faculty_notification_recipients(account):
    """
    Recipients for a faculty notification: institutional email + personal email.

    FacultyProfile.personal_email is the secondary address faculty are notified
    on. Blank, missing, and identical-to-primary values are handled by
    build_recipient_list, so callers never send duplicates.

    Accounts without a faculty profile (admins) simply resolve to their own
    email, which keeps behaviour unchanged for other roles.

    Note: this is deliberately NOT used for OTP, 2FA, or password-reset codes.
    Those stay on the institutional email only, so control of a secondary inbox
    is never enough to take over an account.
    """
    if account is None:
        return []

    profile = getattr(account, "faculty_profile", None)
    personal_email = getattr(profile, "personal_email", None) if profile else None

    return build_recipient_list(getattr(account, "email", None), personal_email)


def send_html_email(
    subject: str,
    to_emails,
    template_name: str,
    context: dict | None = None,
    from_email: str | None = None,
    from_name: str | None = None,   # 👈 added
) -> None:
    """
    Generic HTML email sender for GURONEx using Brevo HTTP API.

    - subject: email subject line
    - to_emails: string or list of strings
    - template_name: Django template path (e.g., 'emails/password_reset_otp.html')
    - context: dict of template vars
    - from_email: override settings.DEFAULT_FROM_EMAIL if needed
    - from_name: override sender display name (e.g. "GURONEx Support")
    """
    if context is None:
        context = {}

    if isinstance(to_emails, str):
        to_emails = [to_emails]

    ctx = {
        "subject": subject,
        "year": timezone.now().year,
        **context,
    }

    html_content = render_to_string(template_name, ctx)
    text_content = strip_tags(html_content)

    # --- Brevo API sending starts here ---

    api_key = getattr(settings, "BREVO_API_KEY", None)
    if not api_key:
        logger.error("BREVO_API_KEY is not configured")
        return

    configuration = brevo_python.Configuration()
    configuration.api_key["api-key"] = api_key

    api_client = brevo_python.ApiClient(configuration)
    api_instance = brevo_python.TransactionalEmailsApi(api_client)

    # Prepare recipients
    to_list = [{"email": email} for email in to_emails]

    # Sender (can be your personal email, but must be a verified Brevo sender)
    sender_email = from_email or settings.DEFAULT_FROM_EMAIL
    sender_name = from_name or getattr(settings, "DEFAULT_FROM_NAME", "GURONEx System")

    send_email = brevo_python.SendSmtpEmail(
        to=to_list,
        sender={
            "email": sender_email,
            "name": "GURONEx",  # 👈 display name here
        },
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )

    try:
        api_instance.send_transac_email(send_email)
    except ApiException as e:
        logger.exception("Error sending email via Brevo API: %s", e)
