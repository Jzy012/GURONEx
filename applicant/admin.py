from django.contrib import admin
from .models import (
    Applicant, ApplicantDocument, ApplicantRequiredDocument,
    ApplicantTimeline, AreaOfSpecialization,
)


@admin.register(AreaOfSpecialization)
class AreaOfSpecializationAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    list_editable = ('is_active',)
    ordering = ('name',)


admin.site.register(Applicant)
admin.site.register(ApplicantDocument)
admin.site.register(ApplicantRequiredDocument)
admin.site.register(ApplicantTimeline)
