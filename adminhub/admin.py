from django.contrib import admin
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
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'other_position', 'contact_number', 'account')
    search_fields = ('name', 'account__email', 'other_position')
    fieldsets = (
        (None, {
            'fields': ('account', 'name', 'contact_number'),
        }),
        ('Position', {
            'fields': ('other_position',),
            'description': 'other_position is used in the Interview Panel section of evaluation exports.',
        }),
    )
admin.site.register(CreatedAccountLog)
admin.site.register(DocumentTemplate)
admin.site.register(PUPSite)

# adminhub/admin.py

 
@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'creator', 'start_date', 'end_date', 'is_active', 'is_important')
    list_filter = ('is_active', 'is_important', 'start_date')
    search_fields = ('title', 'content')

@admin.register(AnnouncementViewLog)
class AnnouncementViewLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'announcement', 'seen_at')
    list_filter = ('seen_at',)
    search_fields = ('user__email', 'announcement__title')


@admin.register(AttendanceFeatureSetting)
class AttendanceFeatureSettingAdmin(admin.ModelAdmin):
    list_display = ('enable_faculty_manual_attendance', 'updated_at')


