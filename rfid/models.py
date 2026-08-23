from django.db import models

# Create your models here.


from django.db import models
from faculty.models import FacultyProfile, TeachingAssignment  # adjust import to your FEMS app location
from django.utils import timezone


class RFIDTag(models.Model):
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, null=True, blank=True)
    uid = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)




class AttendanceLog(models.Model):
    # Why a manual log was filed instead of an RFID tap. Grounded in how
    # attendance is actually captured: RFID is the primary path, so a manual
    # entry needs a concrete justification for why that path was unavailable.
    REASON_RFID_OFFLINE = 'rfid_offline'
    REASON_CARD_UNAVAILABLE = 'card_unavailable'
    REASON_ONLINE_CLASS = 'online_class'
    REASON_OFFSITE_ACTIVITY = 'offsite_activity'
    REASON_NETWORK_ISSUE = 'network_issue'
    REASON_OTHER = 'other'

    MANUAL_REASON_CHOICES = [
        (REASON_RFID_OFFLINE, 'RFID Reader Offline / Malfunction'),
        (REASON_CARD_UNAVAILABLE, 'RFID Card Lost or Unavailable'),
        (REASON_ONLINE_CLASS, 'Online Class'),
        (REASON_OFFSITE_ACTIVITY, 'Official Business / Off-campus Activity'),
        (REASON_NETWORK_ISSUE, 'Device or Network Issue'),
        (REASON_OTHER, 'Other'),
    ]

    # Reasons that require uploaded photo documentation to be accepted.
    REASONS_REQUIRING_DOCUMENTATION = {REASON_ONLINE_CLASS}
    # Reasons that require a free-text explanation.
    REASONS_REQUIRING_DETAILS = {REASON_OTHER}

    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE)
    uid = models.CharField(max_length=50, blank=True, null=True)
    date = models.DateField(default=timezone.localdate)
    time_in = models.DateTimeField(null=True, blank=True)
    time_out = models.DateTimeField(null=True, blank=True)
    teaching_assignments = models.ManyToManyField(
        TeachingAssignment,
        blank=True,
        related_name='attendance_logs',
    )
    is_manual = models.BooleanField(default=False)

    manual_reason = models.CharField(
        max_length=32,
        choices=MANUAL_REASON_CHOICES,
        blank=True,
        help_text="Why this attendance was logged manually instead of via RFID.",
    )
    manual_reason_details = models.TextField(
        blank=True,
        help_text="Required explanation when the reason is 'Other'.",
    )
    # Photo documentation is stored on Google Drive, matching FacultyDocument.
    documentation_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Google Drive link to the uploaded photo documentation.",
    )
    documentation_drive_id = models.CharField(max_length=255, blank=True)

    @property
    def has_documentation(self):
        return bool(self.documentation_url or self.documentation_drive_id)

    def __str__(self):
        return f"{self.faculty} - {self.date} ({self.time_in} - {self.time_out})"


class ESP32WiFi(models.Model):
    device_name = models.CharField(max_length=50, default="ESP32")
    reset_wifi = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.device_name} WiFi Control"