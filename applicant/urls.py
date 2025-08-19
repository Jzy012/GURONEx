from django.urls import path
from . import views


app_name = 'applicants'

urlpatterns = [
    path("apply/", views.applicant_apply, name="apply"),
    path("check-status/", views.applicant_check_status, name="check_status"),
    path("status/<int:pk>/", views.applicant_status_page, name="status_page"),
    path("upload-doc/<int:pk>/", views.applicant_upload_doc, name="upload_doc"),
]