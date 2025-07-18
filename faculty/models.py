from django.db import models
from base.models import Account
from django.utils import timezone


# Create your models here.

class EmploymentStatus(models.Model):
    name = models.CharField(max_length=50, unique=True)  # e.g., Full-Time, On-Leave
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name



class FacultyProfile(models.Model):
    account = models.OneToOneField(Account, on_delete=models.CASCADE, related_name='faculty_profile')
    name = models.CharField(max_length=255)
    department = models.CharField(max_length=100)
    birth_date = models.DateField(null=True, blank=True)
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    status = models.ForeignKey(EmploymentStatus, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    gdrive_folder_id = models.CharField(max_length=100, null=True, blank=True)


    def __str__(self):
        return self.name



# This model is used to store file types for documents uploaded by faculty.
class FileType(models.Model):
    extension = models.CharField(
        max_length=10,
        unique=True,
        help_text="Enter the file extension only (e.g., pdf, docx, jpeg). Do not include a dot or quotes."
    )

    def save(self, *args, **kwargs):
        # Clean the extension before saving
        cleaned = self.extension.strip().lower().lstrip('.')  # remove whitespace + leading dot
        self.extension = cleaned
        super().save(*args, **kwargs)

    def __str__(self):
        return self.extension



class DocumentCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    is_required = models.BooleanField(default=False)
    requires_expiry_date = models.BooleanField(default=False)

    allowed_file_types = models.ManyToManyField(FileType, related_name='document_categories')

    def __str__(self):
        return self.name




class FacultyDocument(models.Model):
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name='documents')
    uploaded_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_documents')

    document_name = models.CharField(max_length=255)
    document_category = models.ForeignKey(DocumentCategory, on_delete=models.SET_NULL, null=True, related_name='documents')

    file_path = models.URLField(max_length=500)
    google_drive_id = models.CharField(max_length=255)

    file_type = models.CharField(max_length=50, null=True, blank=True)  # auto-filled on upload
    file_size = models.PositiveIntegerField(null=True, blank=True)      # auto-filled on upload

    expiry_date = models.DateField(null=True, blank=True)  # only required if category.requires_expiry_date

    status = models.CharField(max_length=50, choices=[
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ])
    admin_remarks = models.TextField(null=True, blank=True)  # Filled by admin only

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document_name} (Faculty: {self.faculty.account.email})"

    @property
    def is_valid(self):
        """
        Determines if the document is valid based on expiry date.
        """
        if self.expiry_date:
            return self.expiry_date >= timezone.now().date()
        return True
