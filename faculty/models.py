from django.db import models
from base.models import Account
from django.utils import timezone
import uuid


# Create your models here.

# faculty/models.py
import uuid
from django.db import models
from django.core.validators import RegexValidator
from base.models import Account


class EmploymentStatus(models.Model):
    name = models.CharField(max_length=50, unique=True)  # e.g., Full-Time, On-Leave
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# Reusable validator for name parts: letters, spaces, apostrophes, periods, hyphens
name_part_validator = RegexValidator(
    regex=r"^[A-Za-zÀ-ÿÑñ\s\.\-']+$",
    message="Names may only contain letters, spaces, apostrophes, periods, and hyphens.",
)




# PH mobile number validator (09XXXXXXXXX)
phone_validator = RegexValidator(
    regex=r'^09\d{9}$',
    message="Enter a valid Philippine mobile number (e.g., 09171234567).",
)

class FacultyProfile(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.OneToOneField(
        Account,
        on_delete=models.CASCADE,
        related_name="faculty_profile"
    )

    # NEW structured name fields
    first_name = models.CharField(max_length=100,null=True,blank=True,validators=[name_part_validator],)
    middle_name = models.CharField(max_length=100,null=True,blank=True,validators=[name_part_validator],)
    last_name = models.CharField(max_length=100,null=True,blank=True,validators=[name_part_validator],)
    suffix = models.CharField(max_length=20,null=True,blank=True,validators=[name_part_validator],help_text="e.g., Jr., Sr., III (optional)",)

    # Existing old field (KEEP THIS)
    faculty_code = models.CharField(max_length=20,unique=True,null=True,blank=True,help_text="Unique faculty code, e.g. FA0018SP2023")
    name = models.CharField(max_length=255,blank=True,null=True,validators=[name_part_validator])  # still used everywhere else

    department = models.CharField(max_length=100, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    contact_number = models.CharField(max_length=11,null=True,blank=True,validators=[phone_validator],)
    status = models.ForeignKey(EmploymentStatus,on_delete=models.SET_NULL,null=True,blank=True,)
    created_at = models.DateTimeField(auto_now_add=True)
    gdrive_folder_id = models.CharField(max_length=100, null=True, blank=True)

    def save(self, *args, **kwargs):
        """
        Auto-generate `name` from structured parts when they are present.
        This keeps old code using `name` working as before.
        """
        parts = [
            (self.first_name or "").strip(),
            (self.middle_name or "").strip(),
            (self.last_name or "").strip(),
            (self.suffix or "").strip(),
        ]
        full_name = " ".join([p for p in parts if p])

        # Only override if we actually have at least one structured part
        if full_name:
            self.name = full_name

        super().save(*args, **kwargs)

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




from django.db import models
from django.utils import timezone


class AcademicYear(models.Model):
    year_start = models.IntegerField()  # e.g. 2025
    year_end = models.IntegerField()    # e.g. 2026
    is_active = models.BooleanField(default=False)

    class Meta:
        unique_together = ('year_start', 'year_end')

    def __str__(self):
        return f"{self.year_start}–{self.year_end}"

    @property
    def start_date(self):
        """
        Effective start date of this academic year, defined as the earliest
        semester.start_date. If there are no semesters yet, we fall back
        to Jan 1 of year_start.
        """
        first_semester = self.semesters.order_by('start_date').first()
        if first_semester:
            return first_semester.start_date
        # Fallback: arbitrary, only used if there are no semesters
        return timezone.datetime(self.year_start, 1, 1, tzinfo=timezone.get_current_timezone()).date()

    @property
    def end_date(self):
        """
        Effective end date of this academic year, defined as the latest
        semester.end_date. If there are no semesters yet, we fall back
        to Dec 31 of year_end.
        """
        last_semester = self.semesters.order_by('-end_date').first()
        if last_semester:
            return last_semester.end_date
        # Fallback: arbitrary, only used if there are no semesters
        return timezone.datetime(self.year_end, 12, 31, tzinfo=timezone.get_current_timezone()).date()

    @classmethod
    def update_active_years(cls, ref_date=None):
        """
        Set is_active=True for the academic year whose date range contains ref_date,
        and False for all others.
        """
        if ref_date is None:
            ref_date = timezone.localdate()

        years = list(cls.objects.prefetch_related('semesters'))
        active_ids = []
        for year in years:
            if year.start_date <= ref_date <= year.end_date:
                active_ids.append(year.id)

        # Reset all to False
        cls.objects.update(is_active=False)

        # Mark found ones as active (normally just 1)
        if active_ids:
            cls.objects.filter(id__in=active_ids).update(is_active=True)


class Semester(models.Model):
    SEMESTER_CHOICES = [
        ('1st', '1st Semester'),
        ('2nd', '2nd Semester'),
        ('summer', 'Summer Term'),
        ('full', 'Full Academic Year'),
    ]

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="semesters"
    )
    semester_type = models.CharField(max_length=10, choices=SEMESTER_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        unique_together = ('academic_year', 'semester_type')

    def __str__(self):
        return f"{self.get_semester_type_display()} {self.academic_year}"

    @classmethod
    def update_active_semesters(cls, ref_date=None):
        """
        For each academic year, mark the semester containing ref_date as active,
        and all others inactive.
        """
        if ref_date is None:
            ref_date = timezone.localdate()

        semesters = list(
            cls.objects
            .select_related("academic_year")
            .order_by("academic_year__year_start", "start_date")
        )

        # Group by academic year id
        by_year = {}
        for sem in semesters:
            by_year.setdefault(sem.academic_year_id, []).append(sem)

        # Reset all to False
        cls.objects.update(is_active=False)

        # Activate the semester that contains ref_date in each academic year
        for year_id, sems in by_year.items():
            for sem in sems:
                if sem.start_date <= ref_date <= sem.end_date:
                    cls.objects.filter(pk=sem.pk).update(is_active=True)
                    break  # only one active per academic year




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

    teaching_assignment = models.ForeignKey(
        'TeachingAssignment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        help_text="If this document is for a specific teaching assignment, link it here."
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



import uuid
from django.core.exceptions import ValidationError
from django.db import models

class TeachingAssignment(models.Model):
    DAYS_OF_WEEK = [
        ('mon', 'Monday'),
        ('tue', 'Tuesday'),
        ('wed', 'Wednesday'),
        ('thu', 'Thursday'),
        ('fri', 'Friday'),
        ('sat', 'Saturday'),
    ]

    faculty = models.ForeignKey('faculty.FacultyProfile', on_delete=models.CASCADE)
    subject_code = models.CharField(max_length=20)
    subject_description = models.CharField(max_length=200)
    year_section = models.CharField(max_length=20)
    day_of_week = models.CharField(max_length=3, choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    semester = models.ForeignKey('Semester', on_delete=models.CASCADE)
    room = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return f"{self.faculty} - {self.subject_code} ({self.get_day_of_week_display()} {self.start_time}-{self.end_time} @ {self.room})"

    def clean(self):
        errors = {}

        # Basic time ordering
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors['end_time'] = "End time must be after start time."

        if not self.faculty:
            errors['faculty'] = "Faculty is required."

        # Overlap: same faculty + semester + day_of_week; touching endpoints allowed
        if (
            self.faculty and self.semester_id and self.day_of_week
            and self.start_time and self.end_time
        ):
            qs = TeachingAssignment.objects.filter(
                faculty=self.faculty,
                semester=self.semester,
                day_of_week=self.day_of_week,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)

            if qs.exists():
                conflict_msg = (
                    "This time range overlaps another assignment for this faculty on this day in this semester."
                )
                # Direct assignment (NOT setdefault) to ensure message appears even if other errors exist.
                errors['start_time'] = conflict_msg
                errors['end_time'] = conflict_msg
                # If you prefer a single top message instead:
                # errors['__all__'] = conflict_msg

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()  # Ensures clean() always runs
        return super().save(*args, **kwargs)