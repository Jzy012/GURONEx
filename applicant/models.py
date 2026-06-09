from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from faculty.models import DocumentCategory, phone_validator
import uuid


# applicant/models.py

from django.utils import timezone


class AreaOfSpecialization(models.Model):
    name = models.CharField(max_length=200, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Area of Specialization'
        verbose_name_plural = 'Areas of Specialization'

    def __str__(self):
        return self.name


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
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    suffix = models.CharField(max_length=20, blank=True)

    # Contact / basic info
    email = models.EmailField()
    contact_number = models.CharField(
        max_length=11, null=True, blank=True,
        validators=[phone_validator],
    )
    area_of_specialization = models.ForeignKey(
        AreaOfSpecialization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='applicants',
    )
    birth_date = models.DateField(null=True, blank=True)

    # Educational Background
    college_degree = models.CharField(max_length=200, blank=True)
    college_institution = models.CharField(max_length=200, blank=True)
    masters_degree = models.CharField(max_length=200, blank=True)
    masters_institution = models.CharField(max_length=200, blank=True)
    doctorate_degree = models.CharField(max_length=200, blank=True)
    doctorate_institution = models.CharField(max_length=200, blank=True)

    status = models.CharField(
        max_length=30,
        choices=[
            ('pending', 'Initial Review'),
            ('demo_scheduled', 'Demo Scheduled'),
            ('for_interview', 'For Interview'),
            ('evaluation', 'Evaluation'),
            ('psych_test', 'Psych Test'),
            ('contract_of_service', 'Contract of Service'),
            ('first_salary_requirements', 'First Salary Requirements'),
            ('hired', 'Hired'),
            ('rejected', 'Rejected'),
            ('withdrawn', 'Withdrawn'),
        ],
        default='pending'
    )

    demo_scheduled_date = models.DateField(null=True, blank=True)
    for_interview_date = models.DateField(null=True, blank=True)
    evaluation_date = models.DateField(null=True, blank=True)
    evaluation_deadline = models.DateField(null=True, blank=True)
    psych_test_date = models.DateField(null=True, blank=True)
    hired_date = models.DateField(null=True, blank=True)
    rejected_date = models.DateField(null=True, blank=True)
    rejected_from_status = models.CharField(
        max_length=40,
        choices=[
            ('pending', 'Initial Review'),
            ('demo_scheduled', 'Demo Scheduled'),
            ('for_interview', 'For Interview'),
            ('evaluation', 'Evaluation'),
            ('psych_test', 'Psych Test'),
            ('contract_of_service', 'Contract of Service'),
            ('first_salary_requirements', 'First Salary Requirements'),
            ('hired', 'Hired'),
        ],
        null=True,
        blank=True,
    )

    # Rejection audit trail
    rejected_by = models.ForeignKey(
        "base.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_applicants",
    )
    rejection_message = models.TextField(blank=True)

    # Availability confirmation (demo/interview step)
    confirmed_by_applicant = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    # Voluntary withdrawal
    cancelled_by_applicant = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    withdrawn_from_status = models.CharField(max_length=40, null=True, blank=True)

    # Emergency contact
    emergency_contact_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_number = models.CharField(max_length=15, null=True, blank=True)

    # Step-specific deadlines set by admin on advance
    psych_test_deadline = models.DateField(null=True, blank=True)
    contract_of_service_deadline = models.DateField(null=True, blank=True)
    first_salary_deadline = models.DateField(null=True, blank=True)

    # Optional instructions shown to applicant for interview/demo steps
    interview_instructions = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    google_drive_folder_id = models.CharField(max_length=255, null=True, blank=True)
    account_created = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        "base.Account",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="archived_applicants",
    )

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

    @property
    def full_name(self) -> str:
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        if self.suffix:
            parts.append(self.suffix)
        return " ".join(parts)

    def __str__(self):
        return f"{self.applicant_id} - {self.full_name}"


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
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        "base.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='archived_applicant_documents',
    )
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        "base.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='restored_applicant_documents',
    )
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

    @property 
    def document_name(self): 
        return f"{self.document_category.name} ({self.applicant.applicant_id})"

    def archive(self, by_user):
        if self.is_archived:
            return
        self.is_archived = True
        self.archived_at = timezone.now()
        self.archived_by = by_user
        self.save(update_fields=['is_archived', 'archived_at', 'archived_by'])

    def restore(self, by_user):
        if not self.is_archived:
            return
        self.is_archived = False
        self.restored_at = timezone.now()
        self.restored_by = by_user
        self.save(update_fields=['is_archived', 'restored_at', 'restored_by'])


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


class ApplicantRescheduleRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_DENIED = 'denied'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_DENIED, 'Denied'),
    ]

    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name='reschedule_requests')
    step = models.CharField(max_length=30)  # 'demo_scheduled' or 'for_interview'
    reason = models.TextField()
    preferred_date = models.DateField(null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "base.Account", on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_reschedule_requests',
    )
    admin_note = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.applicant.applicant_id} reschedule ({self.step}) – {self.status}"


class ApplicantStepDocument(models.Model):
    STEP_PSYCH_TEST = 'psych_test'
    STEP_CONTRACT_ADMIN = 'contract_admin'
    STEP_CONTRACT_SIGNED = 'contract_signed'
    STEP_SALARY_REQUIREMENT = 'salary_requirement'
    STEP_TYPE_CHOICES = [
        (STEP_PSYCH_TEST, 'Psych Test'),
        (STEP_CONTRACT_ADMIN, 'Contract (Admin Uploaded)'),
        (STEP_CONTRACT_SIGNED, 'Signed Contract (Applicant)'),
        (STEP_SALARY_REQUIREMENT, 'First Salary Requirement'),
    ]

    STATUS_PENDING = 'Pending'
    STATUS_APPROVED = 'Approved'
    STATUS_REJECTED = 'Rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name='step_documents')
    step_type = models.CharField(max_length=30, choices=STEP_TYPE_CHOICES)
    document_category = models.ForeignKey(
        DocumentCategory, on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    uploaded_by = models.ForeignKey(
        "base.Account", on_delete=models.SET_NULL,
        null=True, blank=True, related_name='uploaded_step_documents',
    )
    file_path = models.URLField(max_length=500)
    google_drive_id = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    admin_remarks = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.applicant.applicant_id} – {self.get_step_type_display()}"


class ApplicantSalaryRequirementConfig(models.Model):
    """Admin-configured per-applicant document checklist for first salary requirements."""
    applicant = models.ForeignKey(
        Applicant, on_delete=models.CASCADE,
        related_name='salary_requirement_configs',
    )
    document_category = models.ForeignKey(DocumentCategory, on_delete=models.CASCADE)
    is_required = models.BooleanField(default=True)

    class Meta:
        unique_together = ('applicant', 'document_category')
        ordering = ['document_category__name']

    def __str__(self):
        flag = 'Required' if self.is_required else 'Optional'
        return f"{self.applicant.applicant_id} – {self.document_category.name} ({flag})"


# ---------------------------------------------------------------------------
# Evaluation Models
# ---------------------------------------------------------------------------

class EvaluationCriteria(models.Model):
    label = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'label']
        verbose_name = 'Evaluation Criteria'
        verbose_name_plural = 'Evaluation Criteria'

    def __str__(self):
        return self.label


EVALUATION_TOKEN_VALIDITY_DAYS = 14

RATING_CHOICES = [
    (1, '1 – Poor'),
    (2, '2 – Needs Improvement'),
    (3, '3 – Satisfactory'),
    (4, '4 – Very Good'),
    (5, '5 – Excellent'),
]


class EvaluationAssignment(models.Model):
    applicant = models.ForeignKey(
        Applicant, on_delete=models.CASCADE, related_name='evaluation_assignments',
    )
    evaluator = models.ForeignKey(
        'base.Account', on_delete=models.CASCADE, related_name='evaluation_assignments',
    )
    assigned_by = models.ForeignKey(
        'base.Account', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_evaluation_assignments',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    token = models.CharField(max_length=64, unique=True, db_index=True)
    token_expires_at = models.DateTimeField()
    submission_deadline = models.DateTimeField(null=True, blank=True)

    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['assigned_at']
        unique_together = ('applicant', 'evaluator')

    def __str__(self):
        return f"{self.applicant.applicant_id} – evaluator: {self.evaluator.email}"

    @property
    def evaluator_display_name(self) -> str:
        acc = self.evaluator
        role = getattr(acc, 'role', None)
        if role == 'faculty':
            try:
                name = acc.faculty_profile.name
                if name:
                    return name
            except Exception:
                pass
        elif role in ('admin', 'system_admin'):
            try:
                name = acc.admin_profile.name
                if name:
                    return name
            except Exception:
                pass
        full = acc.get_full_name().strip()
        if full:
            return full
        local = acc.email.split('@')[0]
        readable = local.replace('.', ' ').replace('_', ' ').replace('-', ' ').title()
        return readable or acc.email

    @property
    def evaluator_role_label(self) -> str:
        labels = {'system_admin': 'System Admin', 'admin': 'Admin', 'faculty': 'Faculty'}
        return labels.get(getattr(self.evaluator, 'role', ''), 'User')

    @property
    def is_deadline_passed(self):
        return bool(self.submission_deadline and timezone.now() > self.submission_deadline)

    @property
    def is_expired(self):
        return timezone.now() > self.token_expires_at or self.is_deadline_passed

    @property
    def is_usable(self):
        return not self.is_submitted and not self.is_expired


class EvaluationSubmission(models.Model):
    assignment = models.OneToOneField(
        EvaluationAssignment, on_delete=models.CASCADE, related_name='submission',
    )
    summary = models.TextField(blank=True)
    justification = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Submission for {self.assignment}"

    @property
    def total_score(self):
        return sum(s.rating for s in self.scores.all())

    @property
    def max_score(self):
        return self.scores.count() * 5


class EvaluationScore(models.Model):
    submission = models.ForeignKey(
        EvaluationSubmission, on_delete=models.CASCADE, related_name='scores',
    )
    criteria = models.ForeignKey(
        EvaluationCriteria, on_delete=models.PROTECT, related_name='scores',
    )
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    comments = models.TextField(blank=True)

    class Meta:
        unique_together = ('submission', 'criteria')
        ordering = ['criteria__order']

    def __str__(self):
        return f"{self.submission} – {self.criteria}: {self.rating}"