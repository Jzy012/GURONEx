from django.urls import path
from . import views


app_name = 'applicants'

urlpatterns = [
    path("applicant/", views.applicant_home, name="home"),  
    path("applicant/apply/", views.applicant_apply, name="apply"),
    path("applicant/check-status/", views.applicant_check_status, name="check_status"),
    path("applicant/status/<int:pk>/", views.applicant_status_page, name="status_page"),
    path("applicant/upload-doc/<int:pk>/", views.applicant_upload_doc, name="upload_doc"),
]