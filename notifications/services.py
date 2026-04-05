import json
from typing import Iterable
import re

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from base.models import Account

from .models import ActivityLog, Notification


ROLE_ADMIN_GROUP = ["admin", "system_admin"]


def _user_group_name(user_id: int) -> str:
    return f"notifications_user_{user_id}"


def serialize_notification(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "url": notification.url,
        "is_read": notification.is_read,
        "is_important": notification.is_important,
        "aggregate_count": notification.aggregate_count,
        "created_at": notification.created_at.isoformat(),
        "updated_at": notification.updated_at.isoformat(),
    }


def push_notification_event(user_id: int, event: str, payload: dict):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(
        _user_group_name(user_id),
        {
            "type": "notification.message",
            "event": event,
            "payload": payload,
        },
    )


def _upsert_aggregate_notification(
    *,
    recipient: Account,
    actor: Account | None,
    notification_type: str,
    title: str,
    message: str,
    url: str,
    related_type: str,
    related_id: str,
    aggregate_key: str,
    is_important: bool,
) -> tuple[Notification, bool]:
    with transaction.atomic():
        existing = (
            Notification.objects.select_for_update()
            .filter(
                recipient=recipient,
                aggregate_key=aggregate_key,
                is_read=False,
            )
            .first()
        )

        if existing:
            existing.aggregate_count += 1
            existing.actor = actor
            existing.notification_type = notification_type
            existing.title = title
            existing.message = message
            existing.url = url
            existing.related_type = related_type
            existing.related_id = related_id
            existing.is_important = is_important or existing.is_important
            existing.save(
                update_fields=[
                    "aggregate_count",
                    "actor",
                    "notification_type",
                    "title",
                    "message",
                    "url",
                    "related_type",
                    "related_id",
                    "is_important",
                    "updated_at",
                ]
            )
            return existing, False

        created = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            notification_type=notification_type,
            title=title,
            message=message,
            url=url,
            related_type=related_type,
            related_id=related_id,
            is_important=is_important,
            aggregate_key=aggregate_key,
            aggregate_count=1,
        )
        return created, True


def notify_user(
    *,
    recipient: Account,
    actor: Account | None = None,
    notification_type: str = "system",
    title: str,
    message: str,
    url: str = "",
    related_type: str = "",
    related_id: str = "",
    is_important: bool = False,
    aggregate_key: str = "",
) -> Notification:
    if aggregate_key:
        notification, _ = _upsert_aggregate_notification(
            recipient=recipient,
            actor=actor,
            notification_type=notification_type,
            title=title,
            message=message,
            url=url,
            related_type=related_type,
            related_id=related_id,
            aggregate_key=aggregate_key,
            is_important=is_important,
        )
    else:
        notification = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            notification_type=notification_type,
            title=title,
            message=message,
            url=url,
            related_type=related_type,
            related_id=related_id,
            is_important=is_important,
        )

    unread_count = Notification.objects.filter(recipient=recipient, is_read=False).count()
    push_notification_event(
        recipient.id,
        "notification.updated",
        {
            "notification": serialize_notification(notification),
            "unread_count": unread_count,
        },
    )
    return notification


def notify_role(
    *,
    roles: Iterable[str],
    actor: Account | None = None,
    notification_type: str = "system",
    title: str,
    message: str,
    url: str = "",
    related_type: str = "",
    related_id: str = "",
    is_important: bool = False,
    aggregate_key: str = "",
) -> list[Notification]:
    recipients = Account.objects.filter(role__in=list(roles), is_active=True).distinct()
    notifications: list[Notification] = []
    for recipient in recipients:
        notifications.append(
            notify_user(
                recipient=recipient,
                actor=actor,
                notification_type=notification_type,
                title=title,
                message=message,
                url=url,
                related_type=related_type,
                related_id=related_id,
                is_important=is_important,
                aggregate_key=aggregate_key,
            )
        )
    return notifications


def log_activity(
    *,
    action: str,
    actor: Account | None = None,
    target_type: str = "",
    target_id: str = "",
    details: dict | None = None,
) -> ActivityLog:
    return ActivityLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    )


def _humanize_identifier(value: str) -> str:
    if not value:
        return ""

    value = value.replace("_", " ")
    value = re.sub(r"(?<!^)(?=[A-Z])", " ", value)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value[:1].upper() + value[1:] if value else ""


def _format_activity_detail_value(value):
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def serialize_activity_log(activity_log: ActivityLog) -> dict:
    action_label = _humanize_identifier(activity_log.action)
    target_label = _humanize_identifier(activity_log.target_type)
    details = activity_log.details or {}

    subject_label = (
        details.get("target_name")
        or details.get("name")
        or details.get("full_name")
        or details.get("faculty_name")
        or details.get("document_name")
        or details.get("title")
        or details.get("email")
        or target_label
    )

    local_created_at = timezone.localtime(activity_log.created_at)

    details_items = [
        {
            "label": _humanize_identifier(str(key)),
            "value": _format_activity_detail_value(value),
        }
        for key, value in details.items()
        if str(key) not in {"target_name", "name", "full_name", "faculty_name", "document_name", "title", "email"}
    ]

    return {
        "id": activity_log.id,
        "action": activity_log.action,
        "action_label": action_label,
        "target_type": activity_log.target_type,
        "target_label": target_label,
        "subject_label": subject_label,
        "details": details,
        "details_items": details_items,
        "created_at": local_created_at.isoformat(),
        "created_day": local_created_at.strftime("%a, %b %d, %Y"),
        "created_time": local_created_at.strftime("%I:%M %p"),
    }


def get_user_activity_logs(user: Account, *, limit: int = 200) -> list[dict]:
    activity_logs = ActivityLog.objects.filter(actor=user).order_by("-created_at")[:limit]
    return [serialize_activity_log(item) for item in activity_logs]


def get_user_notification_summary(user: Account, *, limit: int = 5) -> dict:
    unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
    latest = Notification.objects.filter(recipient=user).order_by("-created_at")[:limit]
    return {
        "unread_count": unread_count,
        "latest": [serialize_notification(item) for item in latest],
    }


def mark_notification_as_read(*, user: Account, notification_id: int) -> Notification | None:
    notification = Notification.objects.filter(id=notification_id, recipient=user).first()
    if not notification:
        return None

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at", "updated_at"])

    unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
    push_notification_event(
        user.id,
        "notification.read",
        {
            "notification_id": notification.id,
            "unread_count": unread_count,
        },
    )
    return notification


def mark_all_notifications_as_read(*, user: Account) -> int:
    now = timezone.now()
    updated = Notification.objects.filter(recipient=user, is_read=False).update(is_read=True, read_at=now)
    push_notification_event(
        user.id,
        "notification.read_all",
        {
            "unread_count": 0,
        },
    )
    return updated


def cleanup_read_notifications() -> dict:
    retention_days = int(getattr(settings, "NOTIFICATION_RETENTION_DAYS", 60))
    max_read = int(getattr(settings, "NOTIFICATION_MAX_READ_PER_USER", 20))

    cutoff = timezone.now() - timezone.timedelta(days=retention_days)

    old_read_qs = Notification.objects.filter(
        is_read=True,
        is_important=False,
        created_at__lt=cutoff,
    )
    old_deleted, _ = old_read_qs.delete()

    count_deleted = 0
    recipients = Account.objects.filter(notifications__is_read=True).distinct()
    for recipient in recipients:
        read_ids_to_keep = list(
            Notification.objects.filter(
                recipient=recipient,
                is_read=True,
                is_important=False,
            )
            .order_by("-created_at")
            .values_list("id", flat=True)[:max_read]
        )

        deleted, _ = (
            Notification.objects.filter(
                recipient=recipient,
                is_read=True,
                is_important=False,
            )
            .exclude(id__in=read_ids_to_keep)
            .delete()
        )
        count_deleted += deleted

    return {
        "deleted_old": old_deleted,
        "deleted_excess": count_deleted,
    }
