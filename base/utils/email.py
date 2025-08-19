from django.core.mail import send_mail
from django.conf import settings

def send_applicant_status_email(applicant, new_status):
    subject = f"[FEMS] Application Status Update: {new_status}"
    message = (
        f"Hello {applicant.first_name},\n\n"
        f"Your application status has changed to: {new_status}.\n"
        f"You can check your status any time at: "
        f"If you have any questions, please reply to this email.\n\n"
        f"Regards,\nFEMS Team"
    )
    from_email = settings.DEFAULT_FROM_EMAIL
    send_mail(
        subject,
        message,
        from_email,
        [applicant.email],
        fail_silently=False,
    )