from django.urls import path
from . import views


app_name = 'applicants'

urlpatterns = [
    path("applicant/", views.applicant_home, name="home"),
    path("applicant/apply/", views.applicant_apply, name="apply"),
    path("applicant/registration-confirmed/", views.applicant_registration_confirmed, name="registration_confirmed"),

    path("applicant/check-status/", views.applicant_login, name="check_status"),
    path("applicant/logout/", views.applicant_logout, name="logout"),
    path("applicant/inactive/", views.applicant_inactive, name="inactive"),
    path("applicant/dashboard/", views.applicant_dashboard, name="dashboard"),

    path("applicant/upload-documents/", views.applicant_upload_documents, name="upload_documents"),
    path("applicant/document/<int:pk>/download/", views.applicant_download_document, name="download_document"),

    # Step-specific applicant actions
    path("applicant/dashboard/reschedule-request/", views.applicant_request_reschedule, name="request_reschedule"),
    path("applicant/dashboard/psych-test/upload/", views.applicant_upload_psych_test, name="upload_psych_test"),
    path("applicant/dashboard/permit-to-teach/upload/", views.applicant_upload_permit_to_teach, name="upload_permit_to_teach"),
    path("applicant/dashboard/contract/upload-signed/", views.applicant_upload_signed_contract, name="upload_signed_contract"),
    path("applicant/step-document/<int:pk>/download/", views.applicant_download_step_document, name="download_step_document"),
    path("applicant/dashboard/salary-requirements/upload/", views.applicant_upload_salary_requirement, name="upload_salary_requirement"),
    path("applicant/dashboard/confirm-availability/", views.applicant_confirm_availability, name="confirm_availability"),
    path("applicant/dashboard/cancel-application/", views.applicant_cancel_application, name="cancel_application"),

    # Public token-based evaluation form (no authentication required)
    path("evaluate/<str:token>/", views.evaluate_form, name="evaluate_form"),
]










  
  
  

    
