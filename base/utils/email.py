from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse


def send_applicant_status_email(applicant, new_status):
    subject = f"[FEMS] Application Status Update: {new_status}"
    # Build status check URL (relative); you can prepend domain in settings if needed
    status_url = reverse('applicants:check_status')
    message = (
        f"Hello {applicant.first_name},\n\n"
        f"Your application status has changed to: {new_status}.\n"
        f"You can check your status any time at: {status_url}\n\n"
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


def send_applicant_submission_receipt(applicant):
    """
    Sends a receipt email to the applicant with a summary of their application
    and their Applicant ID, which they use to check their status.
    """
    subject = "[FEMS] Application Received"

    # Build full name with middle + suffix
    name_parts = [applicant.first_name]
    if applicant.middle_name:
        name_parts.append(applicant.middle_name)
    name_parts.append(applicant.last_name)
    if applicant.suffix:
        name_parts.append(applicant.suffix)
    full_name = " ".join(name_parts)

    # URL where they can check status (relative)
    status_url = reverse('applicants:check_status')

    message_lines = [
        f"Hello {applicant.first_name},",
        "",
        "Thank you for submitting your application to FEMS.",
        "",
        "Here is a summary of your application:",
        f"Applicant ID: {applicant.applicant_id}",
        f"Name: {full_name}",
        f"Email: {applicant.email}",
        f"Contact Number: {applicant.contact_number or 'N/A'}",
        f"Department: {applicant.department}",
        f"Birth Date: {applicant.birth_date or 'N/A'}",
        "",
        "Educational Background:",
        f"  College Course: {applicant.college_course or 'N/A'}",
        f"  College School: {applicant.college_school_name or 'N/A'}",
        f"  College Graduation Year: {applicant.college_graduation_year or 'N/A'}",
        "",
        f"  Graduate Course: {applicant.grad_course or 'N/A'}",
        f"  Graduate School: {applicant.grad_school_name or 'N/A'}",
        f"  Graduate Graduation Year: {applicant.grad_graduation_year or 'N/A'}",
        "",
        "Emergency Contact:",
        f"  Name: {applicant.emergency_contact_name or 'N/A'}",
        f"  Number: {applicant.emergency_contact_number or 'N/A'}",
        "",
        "You can use your Applicant ID together with your email address to",
        f"check your application status here: {status_url}",
        "",
        "If you did not submit this application or have any concerns,",
        "please reply to this email.",
        "",
        "Regards,",
        "FEMS Team",
    ]

    message = "\n".join(message_lines)
    from_email = settings.DEFAULT_FROM_EMAIL

    send_mail(
        subject,
        message,
        from_email,
        [applicant.email],
        fail_silently=False,
    )