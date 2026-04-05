import datetime

from celery import shared_task
from django.db import DatabaseError
from django.utils import timezone

from adminhub.models import Announcement
from applicant.models import Applicant
from base.models import Account
from base.utils.email import send_html_email
from notifications.services import log_activity, notify_role


DEFAULT_ANNOUNCEMENT_ROLES = ["admin", "faculty"]


def _sync_active_academic_calendar(ref_date=None):
    from faculty.models import AcademicYear, Semester

    if ref_date is None:
        ref_date = timezone.localdate()

    AcademicYear.update_active_years(ref_date=ref_date)
    Semester.update_active_semesters(ref_date=ref_date)

    return {
        "ref_date": str(ref_date),
    }


def _get_announcement_recipient_emails(visible_roles):
    roles = set(visible_roles or DEFAULT_ANNOUNCEMENT_ROLES)
    recipients = set()

    if "admin" in roles:
        admin_emails = Account.objects.filter(
            role__in=["admin", "system_admin"],
            is_active=True,
        ).exclude(email="").values_list("email", flat=True)
        recipients.update(email.strip() for email in admin_emails if email)

    if "faculty" in roles:
        faculty_emails = Account.objects.filter(
            role="faculty",
            is_active=True,
        ).exclude(email="").values_list("email", flat=True)
        recipients.update(email.strip() for email in faculty_emails if email)

    if "applicant" in roles:
        applicant_emails = Applicant.objects.exclude(email="").values_list("email", flat=True)
        recipients.update(email.strip() for email in applicant_emails if email)

    return sorted(recipients)


def _update_announcement_email_state(announcement_id, **fields):
    Announcement.objects.filter(pk=announcement_id).update(**fields)


def _queue_scheduled_publish_if_needed(announcement_id):
    publish_scheduled_announcement_task.apply_async(args=[announcement_id], countdown=1)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def sync_active_academic_calendar_task(self, ref_date=None):
    """
    Recalculate the active academic year and semester for a given date.

    Used as a daily catch-up job and as a shared helper for manual refreshes.
    """
    if ref_date:
        try:
            ref_date = datetime.date.fromisoformat(ref_date)
        except (TypeError, ValueError):
            ref_date = timezone.localdate()
    return _sync_active_academic_calendar(ref_date=ref_date)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def activate_semester_start_task(self, semester_id):
    """
    Activate the semester that has reached its start date.

    The task is idempotent and will no-op only if the start date is still in
    the future. If it runs late, it still refreshes the active calendar so the
    latest started semester remains active.
    """
    from faculty.models import AcademicYear, Semester

    try:
        semester = Semester.objects.select_related("academic_year").get(pk=semester_id)
    except Semester.DoesNotExist:
        return {"activated": False, "reason": "missing_semester"}

    today = timezone.localdate()
    if today < semester.start_date:
        return {
            "activated": False,
            "reason": "start_date_pending",
            "semester_id": semester_id,
            "today": str(today),
        }

    AcademicYear.update_active_years(ref_date=today)
    Semester.update_active_semesters(ref_date=today)

    return {
        "activated": True,
        "semester_id": semester_id,
        "today": str(today),
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def publish_due_scheduled_announcements_task(self, limit=50):
    """
    Catch-up job for missed scheduled announcements.
    Publishes announcements that are due but still not published.
    """
    due_ids = list(
        Announcement.objects.filter(
            scheduled_publish_at__isnull=False,
            published_at__isnull=True,
            scheduled_publish_at__lte=timezone.now(),
        )
        .order_by("scheduled_publish_at")
        .values_list("id", flat=True)[:limit]
    )

    published_count = 0
    for announcement_id in due_ids:
        result = publish_scheduled_announcement_task.apply(args=[announcement_id])
        if isinstance(result.result, dict) and result.result.get("published"):
            published_count += 1

    return {
        "checked": len(due_ids),
        "published": published_count,
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def publish_scheduled_announcement_task(self, announcement_id):
    try:
        announcement = Announcement.objects.get(pk=announcement_id)
    except Announcement.DoesNotExist:
        return {"published": False, "reason": "missing_announcement"}

    scheduled_at = announcement.scheduled_publish_at
    if not scheduled_at:
        return {"published": False, "reason": "not_scheduled"}

    now = timezone.now()
    if scheduled_at > now:
        countdown = max(1, int((scheduled_at - now).total_seconds()))
        publish_scheduled_announcement_task.apply_async(args=[announcement_id], countdown=countdown)
        return {"published": False, "reason": "rescheduled", "countdown": countdown}

    if announcement.published_at:
        return {"published": True, "reason": "already_published"}

    announcement.start_date = scheduled_at.date()
    announcement.is_active = True
    announcement.published_at = now
    announcement.save(update_fields=["start_date", "is_active", "published_at"])

    roles = announcement.visible_to_roles or DEFAULT_ANNOUNCEMENT_ROLES
    notify_role(
        roles=roles,
        actor=announcement.creator,
        notification_type='announcement_published',
        title=f"New announcement: {announcement.title}",
        message=announcement.content[:220],
        url='/faculty/announcements/' if 'faculty' in roles else '/admin/announcements/',
        related_type='Announcement',
        related_id=str(announcement.uuid),
        aggregate_key=f"announcement:{announcement.uuid}",
        is_important=announcement.is_important,
    )
    log_activity(
        actor=announcement.creator,
        action='announcement_published',
        target_type='Announcement',
        target_id=str(announcement.uuid),
        details={'scheduled': True, 'send_email': announcement.send_email},
    )

    if announcement.send_email:
        _update_announcement_email_state(
            announcement_id,
            email_status="queued",
            email_queued_at=now,
            email_processed_at=None,
            email_attempted_count=0,
            email_sent_count=0,
            email_failed_count=0,
            email_last_error="",
        )
        # Run inline in the same worker process to avoid nested queue handoff issues on Windows.
        send_announcement_email_task.apply(args=[announcement_id])
    else:
        _update_announcement_email_state(
            announcement_id,
            email_status="not_requested",
            email_queued_at=None,
            email_processed_at=now,
            email_attempted_count=0,
            email_sent_count=0,
            email_failed_count=0,
            email_last_error="",
        )

    return {"published": True, "reason": "published_now"}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_announcement_email_task(self, announcement_id):
    try:
        announcement = Announcement.objects.get(pk=announcement_id)
    except Announcement.DoesNotExist:
        return {"sent": 0, "reason": "missing_announcement"}

    _update_announcement_email_state(
        announcement_id,
        email_status="sending",
        email_last_error="",
    )

    recipients = _get_announcement_recipient_emails(announcement.visible_to_roles)
    if not recipients:
        _update_announcement_email_state(
            announcement_id,
            email_status="failed",
            email_attempted_count=0,
            email_sent_count=0,
            email_failed_count=0,
            email_last_error="No recipients matched announcement visibility roles.",
            email_processed_at=timezone.now(),
        )
        return {"sent": 0, "reason": "no_recipients"}

    role_labels = {
        "admin": "Admin",
        "faculty": "Faculty",
        "applicant": "Applicant",
    }
    visible_label = ", ".join(
        role_labels.get(role, role.title()) for role in (announcement.visible_to_roles or [])
    )

    subject = f"[LINANG] New Announcement: {announcement.title}"
    context = {
        "announcement": announcement,
        "visible_label": visible_label,
        "is_important": announcement.is_important,
    }

    sent_count = 0
    failed_count = 0
    last_error = ""
    for recipient in recipients:
        try:
            send_html_email(
                subject=subject,
                to_emails=recipient,
                template_name="emails/announcement_copy.html",
                context=context,
            )
            sent_count += 1
        except DatabaseError as exc:
            raise self.retry(exc=exc)
        except Exception as exc:
            # Continue sending to other recipients even if one fails.
            failed_count += 1
            last_error = str(exc)
            continue

    attempted_count = len(recipients)
    if sent_count == attempted_count:
        status = "sent"
    elif sent_count == 0:
        status = "failed"
    else:
        status = "partial_failed"

    _update_announcement_email_state(
        announcement_id,
        email_status=status,
        email_attempted_count=attempted_count,
        email_sent_count=sent_count,
        email_failed_count=failed_count,
        email_last_error=last_error,
        email_processed_at=timezone.now(),
    )

    return {"sent": sent_count, "attempted": attempted_count, "failed": failed_count, "status": status}
