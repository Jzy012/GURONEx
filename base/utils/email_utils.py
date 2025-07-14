from django.core.mail import send_mail
from django.conf import settings

def send_otp_email(to_email, otp, provider="gmail"):
    """
    Sends an OTP email using the configured SMTP provider.
    Currently supports Gmail. Extend for other providers as needed.
    """
    subject = "Your Password Reset OTP"
    message = f"Your OTP for password reset is: {otp}\nThis code will expire in 5-10 minutes."
    from_email = settings.DEFAULT_FROM_EMAIL

    send_mail(
        subject,
        message,
        from_email,
        [to_email],
        fail_silently=False,
    )