from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import (
    AdminProfile,
    Announcement,
    AnnouncementViewLog,
    AttendanceFeatureSetting,
    CreatedAccountLog,
    DocumentTemplate,
    PUPSite,
)

# Register your models here.


@admin.register(AdminProfile)
class AdminProfileAdmin(ModelAdmin):
    list_display = ('name', 'position', 'designation', 'contact_number', 'account')
    search_fields = ('name', 'account__email', 'position', 'designation')
    fieldsets = (
        (None, {
            'fields': ('account', 'name', 'contact_number'),
        }),
        ('Position', {
            'fields': ('position', 'designation'),
            'description': 'designation is used in the Interview Panel section of evaluation exports.',
        }),
    )


@admin.register(CreatedAccountLog)
class CreatedAccountLogAdmin(ModelAdmin):
    list_display = ('faculty_email', 'applicant_name', 'applicant_email', 'created_at')
    search_fields = ('faculty_email', 'applicant_name', 'applicant_email')
    list_filter = ('created_at',)


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(ModelAdmin):
    list_display = ('name', 'document_category', 'is_active', 'uploaded_by', 'uploaded_at')
    list_filter = ('is_active', 'document_category')
    search_fields = ('name',)


@admin.register(PUPSite)
class PUPSiteAdmin(ModelAdmin):
    list_display = ('name', 'url', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'url')

# adminhub/admin.py


@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin):
    list_display = ('title', 'creator', 'start_date', 'end_date', 'is_active', 'is_important')
    list_filter = ('is_active', 'is_important', 'start_date')
    search_fields = ('title', 'content')

@admin.register(AnnouncementViewLog)
class AnnouncementViewLogAdmin(ModelAdmin):
    list_display = ('user', 'announcement', 'seen_at')
    list_filter = ('seen_at',)
    search_fields = ('user__email', 'announcement__title')


@admin.register(AttendanceFeatureSetting)
class AttendanceFeatureSettingAdmin(ModelAdmin):
    list_display = ('enable_faculty_manual_attendance', 'updated_at')
