from django.core.mail import send_mail
from django.conf import settings

def send_otp_email(to_email, otp, purpose="password_reset"):
    """
    Sends an OTP email using the configured SMTP provider.
    Supports different purposes like password_reset, login_2fa, etc.
    """
    from_email = settings.DEFAULT_FROM_EMAIL

    if purpose == "password_reset":
        subject = "Password Reset OTP"
        message = f"Your OTP for password reset is: {otp}\nThis code will expire in 5–10 minutes."
    elif purpose == "login_2fa":
        subject = "Login Verification OTP"
        message = f"Use this OTP to complete your login: {otp}\nThis code will expire in 5 minutes."
    else:
        subject = "Your One-Time Password (OTP)"
        message = f"Your OTP is: {otp}"

    send_mail(
        subject,
        message,
        from_email,
        [to_email],
        fail_silently=False,
    )
