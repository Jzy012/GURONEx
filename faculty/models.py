from django.db import models
from base.models import Account
from django.utils import timezone
import uuid


# Create your models here.

class EmploymentStatus(models.Model):
    name = models.CharField(max_length=50, unique=True)  # e.g., Full-Time, On-Leave
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name



class FacultyProfile(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)  
    account = models.OneToOneField(Account, on_delete=models.CASCADE, related_name='faculty_profile')
    name = models.CharField(max_length=255)
    department = models.CharField(max_length=100)
    birth_date = models.DateField(null=True, blank=True)
    contact_number = models.CharField(max_length=11, null=True, blank=True)
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



class AcademicYear(models.Model):
    year_start = models.IntegerField()  # e.g. 2025
    year_end = models.IntegerField()    # e.g. 2026
    is_active = models.BooleanField(default=False)

    class Meta:
        unique_together = ('year_start', 'year_end')

    def __str__(self):
        return f"{self.year_start}–{self.year_end}"



class Semester(models.Model):
    SEMESTER_CHOICES = [
        ('1st', '1st Semester'),
        ('2nd', '2nd Semester'),
        ('summer', 'Summer Term'),
        ('full', 'Full Academic Year'),
    ]

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="semesters")
    semester_type = models.CharField(max_length=10, choices=SEMESTER_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        unique_together = ('academic_year', 'semester_type')

    def __str__(self):
        return f"{self.get_semester_type_display()} {self.academic_year}"




class DeliverableTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)  # e.g., "Standard Semester Deliverables"
    document_categories = models.ManyToManyField(
        DocumentCategory,
        related_name='included_in_templates'
    )

    def __str__(self):
        return self.name




class Deliverable(models.Model):
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name='deliverables'
    )
    document_category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.CASCADE,
        related_name='deliverables'
    )
    deadline = models.DateField()

    class Meta:
        unique_together = ('semester', 'document_category')

    def __str__(self):
        return f"{self.document_category.name} - {self.semester}"




class FacultyDocument(models.Model):
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name='documents')
    uploaded_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_documents')

    document_name = models.CharField(max_length=255)
    document_category = models.ForeignKey(DocumentCategory, on_delete=models.SET_NULL, null=True, related_name='documents')

    file_path = models.URLField(max_length=500)
    google_drive_id = models.CharField(max_length=255)

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    file_size = models.PositiveIntegerField(null=True, blank=True)      # auto-filled on upload

    expiry_date = models.DateField(null=True, blank=True)  # only required if category.requires_expiry_date

    status = models.CharField(max_length=50, choices=[
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]) # default='Pending') for admin view only, which will be set by admin if approved or rejected
    admin_remarks = models.TextField(null=True, blank=True)  # Filled by admin only

    uploaded_at = models.DateTimeField(auto_now_add=True)

    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="faculty_documents"
    )

    deliverable = models.ForeignKey(
        'Deliverable',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_documents',
        help_text="If this document fulfills a specific deliverable, link it here."
    )

    
    def __str__(self):
        sem = f" - {self.semester}" if self.semester else ""
        return f"{self.document_name} (Faculty: {self.faculty.account.email}){sem}"


    @property
    def is_valid(self):
        """
        Determines if the document is valid based on expiry date.
        """
        if self.expiry_date:
            return self.expiry_date >= timezone.now().date()
        return True
    

from django.db import models
from faculty.models import FacultyProfile
import uuid


class RequestType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class FacultyRequest(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    faculty = models.ForeignKey(FacultyProfile,on_delete=models.CASCADE,related_name="requests")
    request_type = models.ForeignKey(RequestType,on_delete=models.SET_NULL,null=True)
    description = models.TextField()
    status = models.CharField(max_length=20,choices=STATUS_CHOICES,default="Pending")
    remarks = models.TextField(blank=True, null=True)
    created_by_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.request_type} - {self.faculty}"



class TeachingAssignment(models.Model):
    DAYS_OF_WEEK = [
        ('mon', 'Monday'),
        ('tue', 'Tuesday'),
        ('wed', 'Wednesday'),
        ('thu', 'Thursday'),
        ('fri', 'Friday'),
        ('sat', 'Saturday'),
    ]
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE)
    subject_code = models.CharField(max_length=20)
    subject_description = models.CharField(max_length=200)
    year_section = models.CharField(max_length=20)      # e.g. BSIT 2-1
    day_of_week = models.CharField(max_length=3, choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.faculty} - {self.subject_code} ({self.get_day_of_week_display()} {self.start_time}-{self.end_time})"