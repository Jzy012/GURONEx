from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone


def send_html_email(
    subject: str,
    to_emails,
    template_name: str,
    context: dict | None = None,
    from_email: str | None = None,
) -> None:
    """
    Generic HTML email sender for LINANG.

    - subject: email subject line
    - to_emails: string or list of strings
    - template_name: Django template path (e.g., 'emails/password_reset_otp.html')
    - context: dict of template vars
    - from_email: override settings.DEFAULT_FROM_EMAIL if needed
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

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=to_emails,
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)