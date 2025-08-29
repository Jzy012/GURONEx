from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from base.forms import StyledPasswordChangeForm

app_name = 'adminhub'


urlpatterns = [
    path('admin/home/', views.home, name='home'),


    path('admin/documents/', views.documents, name='documents'),


    path('admin/faculty-list/', views.faculty_list_view, name='faculty_list'),
    path('admin/faculty/<uuid:faculty_uuid>/', views.faculty_detail_view, name='faculty_detail'),
    path('admin/faculty/create/', views.create_faculty_view, name='create_faculty'),
    path('admin/faculty/<uuid:faculty_uuid>/edit/', views.edit_faculty_view, name='edit_faculty'),


    path('admin/announcements/', views.announcements_view, name='announcements'),
    path('admin/announcements/create/', views.create_announcement_view, name='create_announcement'),
    path('admin/announcements/edit/<uuid:uuid>/', views.edit_announcement_view, name='edit_announcement'),
    path('admin/announcements/delete/<uuid:uuid>/', views.delete_announcement_view, name='delete_announcement'),


    path('admin/deliverables/', views.deliverables_view, name='deliverables'),
    path('admin/deliverables/deliverable-templates/create/',views.create_deliverable_template_view,name='create_deliverable_template'),
    path('admin/deliverables/deliverable-templates/',views.deliverable_templates_view,name='deliverable_template'),
    path('admin/deliverables/assign/', views.assign_deliverables_view, name='assign_deliverables'),


    path("admin/requests/", views.admin_request_list_view, name="request_list"),
    path("admin/requests/create/",views.admin_request_create_view,name="request_create"),
    path("admin/requests/<uuid:uuid>/action/", views.admin_request_action_view, name="request_action"),

    path('admin/applicants/', views.applicant_list_view, name='applicant_list'),
    # path('admin/applicants/<int:pk>/', views.applicant_detail_view, name='applicant_detail'),
    path('admin/applicants/<uuid:uuid>/', views.applicant_detail_view, name='applicant_detail'),
    path('admin/applicants/account-creation/', views.account_creation_view, name='account_creation'),
    path('admin/applicants/account-creation/log/', views.created_account_log_view, name='account_creation_log'),

    path("admin/request-types/",views.request_type_list_view,name="request_type_list"),
    path("admin/request-types/create/",views.request_type_create_view,name="request_type_create"),
    path("admin/request-types/<int:pk>/edit/",views.request_type_edit_view,name="request_type_edit"),
    path("admin/request-types/<int:pk>/delete/",views.request_type_delete_view,name="request_type_delete"),
    


    path('admin/attendance-logs/',views.attendance_logs_view, name='attendance_logs'),
    path('admin/attendance-logs/manual-log/', views.manual_attendance_log_view, name='manual_attendance_log'),
    path('admin/pair-rfid/', views.pair_rfid, name='pair_rfid'),
    path('api/rfid_pairing_tap/', views.rfid_pairing_tap_api, name='rfid_pairing_tap_api'),

    path('admin/faculty/<uuid:faculty_uuid>/dtr/',views.dtr_tab_view,name='dtr_tab'),

    path('admin/teaching-assignments', views.teaching_assignment_view, name='teaching_assignment'),

    path('admin/faculty/<uuid:faculty_uuid>/teaching-assignments/',views.teaching_assignment_list, name='teaching_assignment_list'),

    # Create assignment for a faculty
    path('admin/faculty/<uuid:faculty_uuid>/teaching-assignments/create/',views.teaching_assignment_create, name='teaching_assignment_create'),

    # Bulk upload for a faculty
    path('admin/faculty/<uuid:faculty_uuid>/teaching-assignments/bulk-upload/',views.teaching_assignment_bulk_upload, name='teaching_assignment_bulk_upload'),

    # Update a specific assignment (by assignment pk)
    path('admin/faculty/<uuid:faculty_uuid>/teaching-assignments/<int:pk>/edit/',views.teaching_assignment_update, name='teaching_assignment_update'),

    # Delete a specific assignment (by assignment pk)
    path('admin/faculty/<uuid:faculty_uuid>/teaching-assignments/<int:pk>/delete/',views.teaching_assignment_delete, name='teaching_assignment_delete'),

    path('admin/settings/', views.admin_settings, name='admin_settings'),
    path('admin/settings/academic-years/', views.academic_years_view, name='academic_years'),
    path('admin/settings/academic-years/create/', views.create_academic_year_view, name='create_academic_year'),


   

    path('admin/settings/change-password/', auth_views.PasswordChangeView.as_view(
        template_name='admin/admin_change_password.html',
        form_class=StyledPasswordChangeForm,
        success_url='/admin/settings/change-password/done/'
    ), name='admin_change_password'),

    path('admin/settings/change-password/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='admin/admin_change_password_done.html'
    ), name='admin_change_password_done'),


    path('admin/settings/two-factor/', views.admin_2fa, name='admin_2fa'),

]