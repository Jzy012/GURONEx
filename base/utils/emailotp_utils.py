# base/utils/emailotp_utils.py
from django.conf import settings
from .email_base import send_html_email  # existing util, signature uses to_emails=...


def send_otp_email(
    to_email: str,
    otp: str,
    purpose: str = "password_reset",
    expiry_minutes: int | None = None,
) -> None:
    """
    Sends an OTP email using HTML templates and the configured SMTP provider.
    Supports different purposes like password_reset, login_2fa, etc.
    """

    # Default expiry if not provided
    if expiry_minutes is None:
        if purpose == "password_reset":
            expiry_minutes = 10
        elif purpose == "login_2fa":
            expiry_minutes = 5
        else:
            expiry_minutes = 10

    # Choose subject + template per purpose
    if purpose == "password_reset":
        subject = " [GURONEx] Password Reset Code"
        template_name = "emails/password_reset_otp.html"
    elif purpose == "login_2fa":
        subject = " [GURONEx] Login Verification Code"
        template_name = "emails/login_2fa_otp.html"  # make sure this exists
    else:
        subject = "Your One-Time Password"
        template_name = "emails/password_reset_otp.html"  # or generic_otp.html later

    context = {
        "email": to_email,
        "otp": otp,
        "expiry_minutes": expiry_minutes,
    }

    # IMPORTANT: use to_emails= (plural) to match your send_html_email signature
    send_html_email(
        subject=subject,
        to_emails=to_email,              # <— changed from to_email= to to_emails=
        template_name=template_name,
        context=context,
        from_email=settings.DEFAULT_FROM_EMAIL,
    )