from .models import Notification
from .services import get_admin_pending_deliverables_count, get_faculty_pending_deliverables_count


def notifications_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    if user.role not in {"admin", "system_admin", "faculty"}:
        return {}

    unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
    latest = Notification.objects.filter(recipient=user, is_read=False).order_by("-updated_at", "-created_at")[:5]

    pending_deliverables_count = 0
    if user.role in {"admin", "system_admin"}:
        pending_deliverables_count = get_admin_pending_deliverables_count()
    elif user.role == "faculty":
        faculty = getattr(user, "faculty_profile", None)
        if faculty:
            pending_deliverables_count = get_faculty_pending_deliverables_count(faculty)

    return {
        "notification_unread_count": unread_count,
        "notification_latest_items": latest,
        "notification_pending_deliverables_count": pending_deliverables_count,
    }
