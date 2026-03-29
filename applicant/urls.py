from django.urls import path
from . import views


app_name = 'applicants'

urlpatterns = [
    path("applicant/", views.applicant_home, name="home"),  
    path("applicant/apply/", views.applicant_apply, name="apply"),
    path("applicant/registration-confirmed/", views.applicant_registration_confirmed, name="registration_confirmed"),
  
    path("applicant/check-status/", views.applicant_login, name="check_status"),
    path("applicant/logout/", views.applicant_logout, name="logout"),
    path("applicant/dashboard/", views.applicant_dashboard, name="dashboard"),

    path("applicant/upload-documents/", views.applicant_upload_documents, name="upload_documents"),
    path("applicant/document/<int:pk>/download/", views.applicant_download_document, name="download_document"),
]










  
  
  

    
