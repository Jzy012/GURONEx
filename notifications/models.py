from django.db import models
from django.utils import timezone


class Notification(models.Model):
	TYPE_CHOICES = [
		("faculty_approval_request", "Faculty Approval Request"),
		("faculty_account_approved", "Faculty Account Approved"),
		("faculty_account_rejected", "Faculty Account Rejected"),
		("faculty_document_uploaded", "Faculty Document Uploaded"),
		("faculty_deliverable_uploaded", "Faculty Deliverable Uploaded"),
		("document_status_updated", "Document Status Updated"),
		("announcement_published", "Announcement Published"),
		("applicant_submitted", "Applicant Submitted"),
		("teaching_assignment_assigned", "Teaching Assignment Assigned"),
		("google_storage_changed", "Google Storage Changed"),
		("deliverable_deadline_reminder", "Deliverable Deadline Reminder"),
		("missing_deliverables", "Missing Deliverables"),
		("applicant_reschedule_requested", "Applicant Reschedule Requested"),
		("applicant_step_document_uploaded", "Applicant Step Document Uploaded"),
		("applicant_availability_confirmed", "Applicant Availability Confirmed"),
		("applicant_application_withdrawn", "Applicant Application Withdrawn"),
		("system", "System"),
	]

	recipient = models.ForeignKey(
		"base.Account",
		on_delete=models.CASCADE,
		related_name="notifications",
	)
	actor = models.ForeignKey(
		"base.Account",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="notifications_created",
	)
	notification_type = models.CharField(max_length=64, choices=TYPE_CHOICES, default="system")
	title = models.CharField(max_length=255)
	message = models.TextField()
	url = models.CharField(max_length=512, blank=True)

	related_type = models.CharField(max_length=100, blank=True)
	related_id = models.CharField(max_length=64, blank=True)

	is_read = models.BooleanField(default=False, db_index=True)
	read_at = models.DateTimeField(null=True, blank=True)
	is_important = models.BooleanField(default=False, db_index=True)

	aggregate_key = models.CharField(max_length=255, blank=True, db_index=True)
	aggregate_count = models.PositiveIntegerField(default=1)

	created_at = models.DateTimeField(auto_now_add=True, db_index=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["recipient", "is_read", "-created_at"]),
			models.Index(fields=["recipient", "aggregate_key", "is_read"]),
		]

	def mark_as_read(self):
		if not self.is_read:
			self.is_read = True
			self.read_at = timezone.now()
			self.save(update_fields=["is_read", "read_at", "updated_at"])

	def __str__(self):
		return f"{self.recipient.email} - {self.title}"


class ActivityLog(models.Model):
	actor = models.ForeignKey(
		"base.Account",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="activity_logs",
	)
	action = models.CharField(max_length=100, db_index=True)
	target_type = models.CharField(max_length=100, blank=True)
	target_id = models.CharField(max_length=64, blank=True)
	details = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True, db_index=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["action", "created_at"]),
			models.Index(fields=["actor", "created_at"]),
		]

	def __str__(self):
		actor = self.actor.email if self.actor else "system"
		return f"{actor} - {self.action}"
