from django.contrib import admin
from .models import (
    AdminProfile,
    Announcement,
    AnnouncementViewLog,
    AttendanceFeatureSetting,
    CreatedAccountLog,
    DocumentTemplate,
)
 
# Register your models here.


admin.site.register(AdminProfile)
admin.site.register(CreatedAccountLog)
admin.site.register(DocumentTemplate)

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


