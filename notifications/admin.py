from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import ActivityLog, Notification


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
	list_display = (
		"id",
		"recipient",
		"notification_type",
		"title",
		"is_read",
		"is_important",
		"aggregate_count",
		"created_at",
	)
	list_filter = ("notification_type", "is_read", "is_important", "created_at")
	search_fields = ("recipient__email", "title", "message", "related_type", "related_id")
	readonly_fields = ("created_at", "updated_at", "read_at")


@admin.register(ActivityLog)
class ActivityLogAdmin(ModelAdmin):
	list_display = ("id", "actor", "action", "target_type", "target_id", "created_at")
	list_filter = ("action", "created_at")
	search_fields = ("actor__email", "action", "target_type", "target_id")
	readonly_fields = ("created_at",)
