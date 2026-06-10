from django.db import models
from base.models import Account  # your custom user model


# Create your models here.

class AdminProfile(models.Model):
    account = models.OneToOneField(Account, on_delete=models.CASCADE, related_name='admin_profile')
    name = models.CharField(max_length=255)
    other_position = models.CharField(max_length=255, blank=True, help_text="Optional title/position used in exports (e.g. HR Coordinator, Guidance Coordinator).")
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or self.account.email




# adminhub/models.py

import uuid
from django.db import models
from django.utils import timezone
from base.models import Account  

class Announcement(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    title = models.CharField(max_length=255)
    content = models.TextField()
    creator = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True)
    visible_to_roles = models.JSONField(default=list)  # Example: ['faculty', 'admin']
    is_important = models.BooleanField(default=False)
    send_email = models.BooleanField(default=False)
    email_status = models.CharField(
        max_length=20,
        choices=[
            ('not_requested', 'Not Requested'),
            ('scheduled', 'Scheduled'),
            ('queued', 'Queued'),
            ('sending', 'Sending'),
            ('sent', 'Sent'),
            ('partial_failed', 'Partially Failed'),
            ('failed', 'Failed'),
        ],
        default='not_requested',
    )
    email_attempted_count = models.PositiveIntegerField(default=0)
    email_sent_count = models.PositiveIntegerField(default=0)
    email_failed_count = models.PositiveIntegerField(default=0)
    email_queued_at = models.DateTimeField(null=True, blank=True)
    email_processed_at = models.DateTimeField(null=True, blank=True)
    email_last_error = models.TextField(blank=True)
    scheduled_publish_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    attachment_link = models.URLField(null=True, blank=True)

    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_visible(self):
        today = timezone.now().date()
        return self.is_active and self.start_date <= today and (self.end_date is None or today <= self.end_date)

    def __str__(self):
        return f"{self.title} ({', '.join(self.visible_to_roles)})"


class AnnouncementViewLog(models.Model):
    user = models.ForeignKey(Account, on_delete=models.CASCADE)
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'announcement')
        ordering = ['-seen_at']

    def __str__(self):
        return f"{self.user.email} saw {self.announcement.title} at {self.seen_at}"





from django.db import models
from applicant.models import Applicant

class CreatedAccountLog(models.Model):
    faculty_email = models.EmailField()
    password = models.CharField(max_length=128)
    applicant = models.ForeignKey(Applicant, on_delete=models.SET_NULL, null=True)
    # Snapshot fields
    applicant_name = models.CharField(max_length=255, blank=True)
    applicant_email = models.EmailField(blank=True)
    applicant_id_snapshot = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.faculty_email} ({self.created_at})"







import uuid
from django.db import models

class PUPSite(models.Model):
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255)
    url = models.URLField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
    



# faculty/models.py (near other models)
from django.db import models
from base.models import Account
from faculty.models import DocumentCategory  # adjust if needed
import uuid


class DocumentTemplate(models.Model):
    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    name = models.CharField(max_length=255)
    document_category = models.OneToOneField(
        DocumentCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_template",
        help_text="Each category can have at most one template."
    )

    file_path = models.URLField(max_length=500)        # Google Drive webViewLink
    google_drive_id = models.CharField(max_length=255) # Drive file id
    file_size = models.PositiveIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True, null=True)

    uploaded_by = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_document_templates"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name or f"Template {self.uid}"


class AttendanceFeatureSetting(models.Model):
    enable_faculty_manual_attendance = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Attendance Feature Setting"
        verbose_name_plural = "Attendance Feature Setting"

    def __str__(self):
        state = "Enabled" if self.enable_faculty_manual_attendance else "Disabled"
        return f"Faculty Manual Attendance: {state}"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class RegistrationSettings(models.Model):
    is_registration_open = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Account,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='registration_setting_updates',
    )

    class Meta:
        verbose_name = "Registration Settings"
        verbose_name_plural = "Registration Settings"

    def __str__(self):
        return f"Applicant Registration: {'Open' if self.is_registration_open else 'Closed'}"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj