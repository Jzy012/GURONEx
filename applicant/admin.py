from django.contrib import admin
from .models import (
    Applicant, ApplicantDocument, ApplicantRequiredDocument,
    ApplicantTimeline, AreaOfSpecialization,
    EvaluationCriteria, EvaluationAssignment, EvaluationSubmission, EvaluationScore,
)


@admin.register(AreaOfSpecialization)
class AreaOfSpecializationAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    list_editable = ('is_active',)
    ordering = ('name',)


@admin.register(EvaluationCriteria)
class EvaluationCriteriaAdmin(admin.ModelAdmin):
    list_display = ('label', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    list_display_links = ('label',)
    ordering = ('order',)


admin.site.register(Applicant)
admin.site.register(ApplicantDocument)
admin.site.register(ApplicantRequiredDocument)
admin.site.register(ApplicantTimeline)
admin.site.register(EvaluationAssignment)
admin.site.register(EvaluationSubmission)
admin.site.register(EvaluationScore)
