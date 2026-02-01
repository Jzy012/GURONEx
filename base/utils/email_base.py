from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
import logging

import brevo_python
from brevo_python.rest import ApiException

logger = logging.getLogger(__name__)


def send_html_email(
    subject: str,
    to_emails,
    template_name: str,
    context: dict | None = None,
    from_email: str | None = None,
    from_name: str | None = None,   # 👈 added
) -> None:
    """
    Generic HTML email sender for LINANG using Brevo HTTP API.

    - subject: email subject line
    - to_emails: string or list of strings
    - template_name: Django template path (e.g., 'emails/password_reset_otp.html')
    - context: dict of template vars
    - from_email: override settings.DEFAULT_FROM_EMAIL if needed
    - from_name: override sender display name (e.g. "LINANG Support")
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
    sender_name = from_name or getattr(settings, "DEFAULT_FROM_NAME", "LINANG System")

    send_email = brevo_python.SendSmtpEmail(
        to=to_list,
        sender={
            "email": sender_email,
            "name": "LINANG",  # 👈 display name here
        },
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )

    try:
        api_instance.send_transac_email(send_email)
    except ApiException as e:
        logger.exception("Error sending email via Brevo API: %s", e)
