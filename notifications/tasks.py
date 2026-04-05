from celery import shared_task
from django.utils import timezone

from faculty.models import Deliverable, Semester, TeachingAssignment

from .services import ROLE_ADMIN_GROUP, cleanup_read_notifications, log_activity, notify_role, notify_user


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def cleanup_notifications_task(self):
    return cleanup_read_notifications()


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def send_deliverable_deadline_reminders_task(self, days_ahead=3):
    target_date = timezone.localdate() + timezone.timedelta(days=days_ahead)
    deliverables = Deliverable.objects.filter(deadline=target_date).select_related("document_category", "semester")

    sent = 0
    for deliverable in deliverables:
        assignments = TeachingAssignment.objects.filter(semester=deliverable.semester).select_related("faculty__account")
        faculty_ids_seen = set()

        for assignment in assignments:
            faculty_account = assignment.faculty.account
            if not faculty_account or faculty_account.id in faculty_ids_seen:
                continue
            faculty_ids_seen.add(faculty_account.id)

            notify_user(
                recipient=faculty_account,
                notification_type="deliverable_deadline_reminder",
                title="Deliverable deadline approaching",
                message=(
                    f"{deliverable.document_category.name} is due on {deliverable.deadline:%Y-%m-%d}."
                ),
                url="/faculty/deliverables/",
                related_type="Deliverable",
                related_id=str(deliverable.id),
                aggregate_key=f"deadline:{deliverable.id}:{faculty_account.id}",
            )
            sent += 1

    return {
        "target_date": str(target_date),
        "sent": sent,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def notify_missing_deliverables_task(self):
    active_semester = Semester.objects.filter(is_active=True).order_by("-id").first()
    if not active_semester:
        return {"sent": 0, "reason": "no_active_semester"}

    has_deliverables = Deliverable.objects.filter(semester=active_semester).exists()
    if has_deliverables:
        return {"sent": 0, "reason": "deliverables_exist"}

    notifications = notify_role(
        roles=ROLE_ADMIN_GROUP,
        notification_type="missing_deliverables",
        title="No deliverables set for current semester",
        message=(
            f"No deliverables are configured for {active_semester}. Please assign deliverables."
        ),
        url="/admin/deliverables/assign/",
        related_type="Semester",
        related_id=str(active_semester.id),
        is_important=True,
        aggregate_key=f"missing_deliverables:{active_semester.id}",
    )
    log_activity(
        action="missing_deliverables_detected",
        target_type="Semester",
        target_id=str(active_semester.id),
        details={"target_name": str(active_semester), "semester": str(active_semester)},
    )

    return {
        "sent": len(notifications),
        "semester_id": active_semester.id,
    }
