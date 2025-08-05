from django.contrib import admin
from .models import FacultyProfile, EmploymentStatus, FileType, DocumentCategory, FacultyDocument, AcademicYear, Semester, Deliverable, DeliverableTemplate

# Register your models here.

admin.site.register(FacultyProfile)
admin.site.register(EmploymentStatus)
admin.site.register(FileType)
admin.site.register(DocumentCategory)
admin.site.register(FacultyDocument)
admin.site.register(AcademicYear)
admin.site.register(Semester)
admin.site.register(Deliverable)
admin.site.register(DeliverableTemplate)