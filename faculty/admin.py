from django.contrib import admin
from .models import FacultyProfile, EmploymentStatus, FileType, DocumentCategory, FacultyDocument, AcademicYear, Semester, Deliverable, DeliverableTemplate, RequestType, FacultyRequest, TeachingAssignment, FacultyClearanceRequest

# Register your models here.

@admin.register(FacultyProfile)
class FacultyProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'faculty_code', 'department', 'other_position', 'status')
    search_fields = ('name', 'faculty_code', 'account__email', 'department')
    list_filter = ('status', 'department')
    fieldsets = (
        (None, {
            'fields': ('account', 'faculty_code', 'name', 'first_name', 'middle_name', 'last_name', 'suffix'),
        }),
        ('Position & Department', {
            'fields': ('other_position', 'department', 'status'),
            'description': 'other_position is used in the Interview Panel section of evaluation exports.',
        }),
        ('Contact & Other', {
            'fields': ('contact_number', 'birth_date', 'gdrive_folder_id'),
        }),
    )
admin.site.register(EmploymentStatus)
admin.site.register(FileType)
admin.site.register(DocumentCategory)
admin.site.register(FacultyDocument)
admin.site.register(AcademicYear)
admin.site.register(Semester)
admin.site.register(Deliverable)
admin.site.register(DeliverableTemplate)
admin.site.register(RequestType)
admin.site.register(FacultyRequest)
admin.site.register(TeachingAssignment)
admin.site.register(FacultyClearanceRequest)