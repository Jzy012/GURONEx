from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from base.decorators import admin_required, faculty_required

from .models import Notification
from .services import (
	get_user_activity_logs,
	get_user_notification_summary,
	mark_all_notifications_as_read,
	mark_notification_as_read,
	serialize_notification,
)


def _is_notification_user(user) -> bool:
	return user.is_authenticated and user.role in {"admin", "system_admin", "faculty"}


@require_GET
@login_required
def notification_summary_api(request):
	if not _is_notification_user(request.user):
		return JsonResponse({"error": "Forbidden"}, status=403)

	return JsonResponse(get_user_notification_summary(request.user, limit=5))


@require_GET
@login_required
def notification_list_api(request):
	if not _is_notification_user(request.user):
		return JsonResponse({"error": "Forbidden"}, status=403)

	filter_value = (request.GET.get("filter") or "all").strip().lower()
	type_filter = (request.GET.get("type") or "").strip()

	queryset = Notification.objects.filter(recipient=request.user)
	if filter_value == "unread":
		queryset = queryset.filter(is_read=False)
	if type_filter:
		queryset = queryset.filter(notification_type=type_filter)

	items = [serialize_notification(item) for item in queryset.order_by("-updated_at", "-created_at")[:200]]
	return JsonResponse({"items": items})


@require_POST
@login_required
def mark_notification_read_api(request, notification_id):
	if not _is_notification_user(request.user):
		return JsonResponse({"error": "Forbidden"}, status=403)

	notification = mark_notification_as_read(user=request.user, notification_id=notification_id)
	if not notification:
		return JsonResponse({"error": "Notification not found"}, status=404)

	return JsonResponse({"success": True})


@require_POST
@login_required
def mark_all_notifications_read_api(request):
	if not _is_notification_user(request.user):
		return JsonResponse({"error": "Forbidden"}, status=403)

	updated = mark_all_notifications_as_read(user=request.user)
	return JsonResponse({"success": True, "updated": updated})


@admin_required
def admin_notifications_page(request):
	notifications = Notification.objects.filter(recipient=request.user).order_by("-updated_at", "-created_at")[:200]
	return render(
		request,
		"admin/admin_notifications.html",
		{
			"notifications": notifications,
			"selected_filter": "all",
		},
	)


@faculty_required
def faculty_notifications_page(request):
	notifications = Notification.objects.filter(recipient=request.user).order_by("-updated_at", "-created_at")[:200]
	return render(
		request,
		"faculty/faculty_notifications.html",
		{
			"notifications": notifications,
			"selected_filter": "all",
		},
	)


@admin_required
def admin_activity_logs_page(request):
	activity_logs = get_user_activity_logs(request.user)
	return render(
		request,
		"admin/admin_activity_logs.html",
		{
			"activity_logs": activity_logs,
		},
	)


@faculty_required
def faculty_activity_logs_page(request):
	activity_logs = get_user_activity_logs(request.user)
	return render(
		request,
		"faculty/faculty_activity_logs.html",
		{
			"activity_logs": activity_logs,
		},
	)
