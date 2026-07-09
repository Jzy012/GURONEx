from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import (
    Applicant, ApplicantDocument, ApplicantRequiredDocument,
    ApplicantTimeline, AreaOfSpecialization,
    EvaluationCriteria, EvaluationAssignment, EvaluationSubmission, EvaluationScore,
)


@admin.register(AreaOfSpecialization)
class AreaOfSpecializationAdmin(ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    list_editable = ('is_active',)
    ordering = ('name',)


@admin.register(EvaluationCriteria)
class EvaluationCriteriaAdmin(ModelAdmin):
    list_display = ('label', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    list_display_links = ('label',)
    ordering = ('order',)


@admin.register(Applicant)
class ApplicantAdmin(ModelAdmin):
    list_display = ('applicant_id', 'first_name', 'last_name', 'email', 'status', 'created_at')
    list_filter = ('status', 'created_at', 'area_of_specialization')
    search_fields = ('applicant_id', 'first_name', 'last_name', 'email')


@admin.register(ApplicantDocument)
class ApplicantDocumentAdmin(ModelAdmin):
    list_display = ('applicant', 'document_category', 'status', 'is_archived', 'submitted_at')
    list_filter = ('status', 'is_archived')
    search_fields = ('applicant__last_name', 'applicant__first_name')


@admin.register(ApplicantRequiredDocument)
class ApplicantRequiredDocumentAdmin(ModelAdmin):
    list_display = ('document_category', 'is_required', 'validity_days')
    list_filter = ('is_required',)


@admin.register(ApplicantTimeline)
class ApplicantTimelineAdmin(ModelAdmin):
    list_display = ('applicant', 'action', 'timestamp', 'admin')
    list_filter = ('timestamp',)
    search_fields = ('applicant__last_name', 'action')


@admin.register(EvaluationAssignment)
class EvaluationAssignmentAdmin(ModelAdmin):
    list_display = ('applicant', 'evaluator', 'is_submitted', 'assigned_at', 'submission_deadline')
    list_filter = ('is_submitted', 'assigned_at')
    search_fields = ('applicant__last_name',)


@admin.register(EvaluationSubmission)
class EvaluationSubmissionAdmin(ModelAdmin):
    list_display = ('assignment', 'submitted_at')


@admin.register(EvaluationScore)
class EvaluationScoreAdmin(ModelAdmin):
    list_display = ('submission', 'criteria', 'rating')
    list_filter = ('rating',)
