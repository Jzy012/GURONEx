from .models import Notification


def notifications_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    if user.role not in {"admin", "system_admin", "faculty"}:
        return {}

    unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
    latest = Notification.objects.filter(recipient=user).order_by("-created_at")[:5]

    return {
        "notification_unread_count": unread_count,
        "notification_latest_items": latest,
    }
