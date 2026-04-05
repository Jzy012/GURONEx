from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("api/notifications/summary/", views.notification_summary_api, name="notification_summary_api"),
    path("api/notifications/list/", views.notification_list_api, name="notification_list_api"),
    path("api/notifications/<int:notification_id>/read/", views.mark_notification_read_api, name="mark_notification_read_api"),
    path("api/notifications/read-all/", views.mark_all_notifications_read_api, name="mark_all_notifications_read_api"),
    path("admin/notifications/", views.admin_notifications_page, name="admin_notifications_page"),
    path("admin/activity-logs/", views.admin_activity_logs_page, name="admin_activity_logs_page"),
    path("faculty/notifications/", views.faculty_notifications_page, name="faculty_notifications_page"),
    path("faculty/activity-logs/", views.faculty_activity_logs_page, name="faculty_activity_logs_page"),
]
