from django.contrib import admin
from .models import Applicant, ApplicantDocument, ApplicantRequiredDocument, ApplicantTimeline


# Register your models here.
admin.site.register(Applicant)
admin.site.register(ApplicantDocument)
admin.site.register(ApplicantRequiredDocument)
admin.site.register(ApplicantTimeline)
