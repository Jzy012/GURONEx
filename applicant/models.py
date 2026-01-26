from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from faculty.models import DocumentCategory
import uuid


# applicant/models.py

from django.utils import timezone

def generate_applicant_id():
    current_year = timezone.now().year
    prefix = f"APL-{current_year}-"   # e.g. "APL-2026-"

    # Get last applicant for this year
    last_applicant = Applicant.objects.filter(
        applicant_id__startswith=prefix
    ).order_by('-id').first()

    if not last_applicant or not last_applicant.applicant_id:
        seq = 1
    else:
        # applicant_id format: "APL-2026-001"
        try:
            last_seq_str = last_applicant.applicant_id.split('-')[2]
            seq = int(last_seq_str) + 1
        except (IndexError, ValueError):
            seq = 1  # fallback to 1 if old/bad data

    return f"{prefix}{seq:03d}"  # 3 digits: 001, 002, ...

class Applicant(models.Model):
    applicant_id = models.CharField(max_length=20, unique=True, editable=False)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Name fields
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)  # NEW: optional
    last_name = models.CharField(max_length=100)
    suffix = models.CharField(max_length=20, blank=True)

    # Contact / basic info
    email = models.EmailField()
    contact_number = models.CharField(max_length=15, null=True, blank=True)
    department = models.CharField(max_length=100)
    birth_date = models.DateField(null=True, blank=True)


    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('demo_scheduled', 'Demo Scheduled'),
            ('for_interview', 'For Interview'),
            ('psych_test', 'Psych Test'),
            ('hired', 'Hired'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )

    # Emergency contact
    emergency_contact_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_number = models.CharField(max_length=15, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    google_drive_folder_id = models.CharField(max_length=255, null=True, blank=True)
    account_created = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        creating = not self.pk
        if creating:
            self.applicant_id = generate_applicant_id()
        super().save(*args, **kwargs)
        # Create Google Drive folder after initial save
        if creating and not self.google_drive_folder_id:
            from services.google_drive_service import CentralGoogleDriveService
            drive_service = CentralGoogleDriveService()
            folder_id = drive_service.create_applicant_folder(self)
            self.google_drive_folder_id = folder_id
            super().save(update_fields=['google_drive_folder_id'])

    def __str__(self):
        # Include middle name if present
        name_parts = [self.first_name]
        if self.middle_name:
            name_parts.append(self.middle_name)
        name_parts.append(self.last_name)
        if self.suffix:
            name_parts.append(self.suffix)
        full_name = " ".join(name_parts)
        return f"{self.applicant_id} - {full_name}"


class ApplicantRequiredDocument(models.Model):
    document_category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.CASCADE
    )
    is_required = models.BooleanField(default=True)  # False = Optional
    validity_days = models.IntegerField(null=True, blank=True)  # For required/optional alike

    class Meta:
        # Ensure only one ApplicantRequiredDocument per DocumentCategory
        constraints = [
            models.UniqueConstraint(
                fields=["document_category"],
                name="unique_required_doc_per_category",
            )
        ]

    def __str__(self):
        return f"{self.document_category.name} ({'Required' if self.is_required else 'Optional'})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # After saving, update related DocumentCategory.is_required flag
        has_required = ApplicantRequiredDocument.objects.filter(
            document_category=self.document_category,
            is_required=True,
        ).exists()
        if self.document_category.is_required != has_required:
            self.document_category.is_required = has_required
            self.document_category.save(update_fields=["is_required"])

    def delete(self, *args, **kwargs):
        doc_cat = self.document_category
        super().delete(*args, **kwargs)
        # After deletion, recalc if any required records remain
        has_required = ApplicantRequiredDocument.objects.filter(
            document_category=doc_cat,
            is_required=True,
        ).exists()
        if doc_cat.is_required != has_required:
            doc_cat.is_required = has_required
            doc_cat.save(update_fields=["is_required"])


class ApplicantDocument(models.Model):
    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name="documents")
    document_category = models.ForeignKey(DocumentCategory, on_delete=models.CASCADE)
    file_path = models.URLField(max_length=500)
    google_drive_id = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    file = models.FileField(upload_to="applicants/", null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=[
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ], default='Pending')
    admin_remarks = models.TextField(null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        max_size = 15 * 1024 * 1024  # 15MB
        if self.file and self.file.size > max_size:
            raise ValidationError("File size must be <= 15MB.")
        if self.file_size and self.file_size > max_size:
            raise ValidationError("Uploaded file exceeds 15MB limit.")
        if self.document_category.requires_expiry_date and not self.expiry_date:
            raise ValidationError("Expiry date is required for this document category.")

    def __str__(self):
        return f"{self.applicant.applicant_id} - {self.document_category.name}"

    @property
    def is_valid(self):
        if self.expiry_date:
            return self.expiry_date >= timezone.now().date()
        return True


class ApplicantTimeline(models.Model):
    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name="timeline")
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=255)
    note = models.TextField(blank=True, null=True)
    admin = models.ForeignKey("base.Account", null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.applicant.applicant_id} @ {self.timestamp}: {self.action}"


class ApplicantRetentionPolicy(models.Model):
    retention_days = models.PositiveIntegerField(default=30)
    last_modified = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey("base.Account", null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"Applicant Retention: {self.retention_days} days"