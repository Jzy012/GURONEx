from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import FacultyProfile, EmploymentStatus, FileType, DocumentCategory, FacultyDocument, AcademicYear, Semester, Deliverable, DeliverableTemplate, RequestType, FacultyRequest, TeachingAssignment, FacultyClearanceRequest

# Register your models here.

@admin.register(FacultyProfile)
class FacultyProfileAdmin(ModelAdmin):
    list_display = ('name', 'faculty_code', 'department', 'position', 'designation', 'status')
    search_fields = ('name', 'faculty_code', 'account__email', 'department')
    list_filter = ('status', 'department')
    fieldsets = (
        (None, {
            'fields': ('account', 'faculty_code', 'name', 'first_name', 'middle_name', 'last_name', 'suffix'),
        }),
        ('Position & Department', {
            'fields': ('position', 'designation', 'department', 'status'),
            'description': 'designation is used in the Interview Panel section of evaluation exports.',
        }),
        ('Contact & Other', {
            'fields': ('contact_number', 'birth_date', 'personal_email', 'gdrive_folder_id'),
        }),
    )


@admin.register(EmploymentStatus)
class EmploymentStatusAdmin(ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(FileType)
class FileTypeAdmin(ModelAdmin):
    list_display = ('extension',)
    search_fields = ('extension',)


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(ModelAdmin):
    list_display = ('name', 'is_required', 'requires_expiry_date')
    list_filter = ('is_required', 'requires_expiry_date')
    search_fields = ('name',)


@admin.register(FacultyDocument)
class FacultyDocumentAdmin(ModelAdmin):
    list_display = ('document_name', 'faculty', 'document_category', 'status', 'is_archived', 'uploaded_at')
    list_filter = ('status', 'document_category', 'is_archived')
    search_fields = ('document_name', 'faculty__name')


@admin.register(AcademicYear)
class AcademicYearAdmin(ModelAdmin):
    list_display = ('year_start', 'year_end', 'is_active')
    list_filter = ('is_active',)


@admin.register(Semester)
class SemesterAdmin(ModelAdmin):
    list_display = ('academic_year', 'semester_type', 'is_active', 'start_date', 'end_date')
    list_filter = ('is_active', 'semester_type')


@admin.register(Deliverable)
class DeliverableAdmin(ModelAdmin):
    list_display = ('semester', 'document_category', 'deadline')
    list_filter = ('semester',)


@admin.register(DeliverableTemplate)
class DeliverableTemplateAdmin(ModelAdmin):
    list_display = ('name', 'is_default')
    list_filter = ('is_default',)
    search_fields = ('name',)


@admin.register(RequestType)
class RequestTypeAdmin(ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(FacultyRequest)
class FacultyRequestAdmin(ModelAdmin):
    list_display = ('uuid', 'faculty', 'request_type', 'status', 'created_at')
    list_filter = ('status', 'request_type', 'created_at')
    search_fields = ('faculty__name',)


@admin.register(TeachingAssignment)
class TeachingAssignmentAdmin(ModelAdmin):
    list_display = ('faculty', 'subject_code', 'year_section', 'day_of_week', 'semester')
    list_filter = ('day_of_week', 'semester')
    search_fields = ('subject_code', 'subject_description', 'faculty__name')


@admin.register(FacultyClearanceRequest)
class FacultyClearanceRequestAdmin(ModelAdmin):
    list_display = ('faculty', 'semester', 'status', 'clearance_number', 'requested_at')
    list_filter = ('status', 'semester')
    search_fields = ('clearance_number', 'faculty__name')
