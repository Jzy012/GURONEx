from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from base.forms import StyledPasswordChangeForm


app_name = 'faculty'


urlpatterns = [
    path('faculty/home/', views.home, name='home'),

    path('faculty/documents/upload/', views.faculty_document_upload, name='upload_documents'),
    path('faculty/documents/', views.faculty_documents_view, name='faculty_documents'),
    path('faculty/documents/download/<uuid:uid>/', views.download_document, name='download_document'),

    path('faculty/attendance-logs/', views.faculty_attendance_logs_view, name='faculty_attendance_logs'),
    path('faculty/teaching-assignments/', views.faculty_teaching_assignment_dtr_view, name='faculty_teaching_assignment'),


    path('faculty/announcements/', views.faculty_announcements_view, name='faculty_announcements'),
    path('faculty/announcements/view/<uuid:uuid>/', views.view_announcement_ajax, name='view_announcement_ajax'),

    path('faculty/deliverables/', views.faculty_deliverables_view, name='faculty_deliverables'),
    path('faculty/deliverables/upload/', views.faculty_deliverable_upload, name='faculty_deliverables_upload'),

    path("faculty/requests/", views.faculty_request_list_view, name="faculty_request_list"),
    path("faculty/requests/create/", views.faculty_request_create_view, name="faculty_request_create"),


    path('faculty/settings/', views.faculty_settings_view, name='faculty_settings'),

    path('faculty/settings/change-password/', auth_views.PasswordChangeView.as_view(
        template_name='faculty/faculty_change_password.html',
        form_class=StyledPasswordChangeForm,
        success_url='/faculty/settings/change-password/done/'
    ), name='faculty_change_password'),

    path('faculty/settings/change-password/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='faculty/faculty_change_password_done.html'
    ), name='faculty_change_password_done'),


    path('faculty/settings/two-factor/', views.faculty_2fa, name='faculty_2fa'),
]