from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from base.forms import StyledPasswordChangeForm

app_name = 'adminhub'


urlpatterns = [
    path('admin/home/', views.home, name='home'),


    path('admin/documents/', views.documents, name='documents'),
    path('admin/documents/archived/', views.archived_documents, name='archived_documents'),
    path('admin/documents/archived/bulk-action/', views.archived_documents_bulk_action, name='archived_documents_bulk_action'),
    path('admin/documents/view/<uuid:uid>/', views.view_document, name='view_document'),
    path('admin/document/change-status/<uuid:uid>/', views.change_document_status, name='change_document_status'),
    path('admin/document/archive/<uuid:uid>/', views.archive_document, name='archive_document'),
    path('admin/document/restore/<uuid:uid>/', views.restore_document, name='restore_document'),
    path('admin/documents/download/<uuid:uid>/', views.download_document, name='download_document'),
    path("documents/templates/", views.document_templates, name="document_templates"),
    path("documents/templates/<uuid:uid>/download/", views.download_document_template, name="download_document_template"),
    path("documents/templates/<uuid:uid>/delete/", views.delete_document_template, name="delete_document_template"),

    # DocumentCategory CRUD URLs
    path('admin/document-categories/', views.document_category_list, name='document_category_list'),
    path('admin/document-categories/create/', views.document_category_create_or_edit, name='document_category_create'),
    path('admin/document-categories/<int:id>/edit/', views.document_category_create_or_edit, name='document_category_edit'),
    path('admin/document-categories/<int:id>/delete/', views.document_category_delete, name='document_category_delete'),

    path('admin/faculty-list/', views.faculty_list_view, name='faculty_list'),
    path('admin/faculty/<uuid:faculty_uuid>/', views.faculty_detail_view, name='faculty_detail'),
    path('admin/faculty/create/', views.create_faculty_view, name='create_faculty'),
    path('admin/faculty/<uuid:faculty_uuid>/edit/', views.edit_faculty_view, name='edit_faculty'),
    path('admin/faculty/documents/download/<int:pk>/',views.download_faculty_document,name='download_faculty_document'),
    path('admin/faculty/document/change-status/<int:pk>/',views.change_faculty_document_status,name='change_faculty_document_status'),
    path('admin/faculty/document/archive/<int:pk>/', views.archive_faculty_document, name='archive_faculty_document'),
    path('admin/faculty/document/restore/<int:pk>/', views.restore_faculty_document, name='restore_faculty_document'),
    path('admin/faculty/document/delete/<int:pk>/', views.delete_faculty_document_permanently, name='delete_faculty_document_permanently'),
    path('admin/faculty/employment-status/',views.employment_status_list_view,name='employment_status_list',),
    path('admin/faculty/employment-status/create/',views.employment_status_create_or_edit_view,name='employment_status_create',),
    path('admin/faculty/employment-status/<int:pk>/edit/',views.employment_status_create_or_edit_view,name='employment_status_edit',),
    path('admin/faculty/employment-status/<int:pk>/delete/',views.employment_status_delete_view,name='employment_status_delete',),

    path('admin/announcements/', views.announcements_view, name='announcements'),
    path('admin/announcements/create/', views.create_announcement_view, name='create_announcement'),
    path('admin/announcements/edit/<uuid:uuid>/', views.edit_announcement_view, name='edit_announcement'),
    path('admin/announcements/delete/<uuid:uuid>/', views.delete_announcement_view, name='delete_announcement'),


    path('admin/deliverables/', views.deliverables_view, name='deliverables'),
    path('admin/deliverables/deliverable-templates/create/',views.create_deliverable_template_view,name='create_deliverable_template'),
    path('admin/deliverables/deliverable-templates/',views.deliverable_templates_view,name='deliverable_template'),
    path('admin/deliverables/deliverable-templates/<int:pk>/edit/',views.edit_deliverable_template_view,name='edit_deliverable_template'),
    path('admin/deliverables/deliverable-templates/<int:pk>/delete/',views.delete_deliverable_template_view,name='delete_deliverable_template'),
    path('admin/deliverables/assign/', views.assign_deliverables_view, name='assign_deliverables'),
    path('admin/faculty/<uuid:faculty_uuid>/deliverables/',views.faculty_deliverables,name='faculty_deliverables',),


 

    path('admin/applicants/', views.applicant_list_view, name='applicant_list'),
    path('admin/applicants/<uuid:uuid>/', views.applicant_detail_view, name='applicant_detail'),
    path('admin/applicants/documents/download/<int:pk>/',views.download_applicant_document,name='download_applicant_document',),
    path('admin/applicants/document/change-status/<int:pk>/',views.change_applicant_document_status,name='change_applicant_document_status',),
    path('admin/applicants/document/archive/<int:pk>/', views.archive_applicant_document, name='archive_applicant_document'),
    path('admin/applicants/document/restore/<int:pk>/', views.restore_applicant_document, name='restore_applicant_document'),
    path('admin/applicants/document/delete/<int:pk>/', views.delete_applicant_document_permanently, name='delete_applicant_document_permanently'),
    path('admin/applicants/account-creation/', views.account_creation_view, name='account_creation'),
    path('admin/applicants/account-creation/log/', views.created_account_log_view, name='account_creation_log'),
    path('admin/applicants/required-documents/',views.applicant_required_document_list_view,name='applicant_required_document_list',),
    path('admin/applicants/required-documents/create/',views.applicant_required_document_create_or_edit_view,name='applicant_required_document_create',),
    path('admin/applicants/required-documents/<int:pk>/edit/',views.applicant_required_document_create_or_edit_view,name='applicant_required_document_edit',),
    path('admin/applicants/required-documents/<int:pk>/delete/',views.applicant_required_document_delete_view,name='applicant_required_document_delete',),

  
    


    path('admin/attendance-logs/',views.attendance_logs_view, name='attendance_logs'),
    path('admin/attendance-logs/manual-log/', views.manual_attendance_log_view, name='manual_attendance_log'),
    path('admin/pair-rfid/', views.pair_rfid, name='pair_rfid'),
    path('api/rfid_pairing_tap/', views.rfid_pairing_tap_api, name='rfid_pairing_tap_api'),
    path('admin/faculty/<uuid:faculty_uuid>/dtr/',views.dtr_tab_view,name='dtr_tab'),
    path('admin/faculty/<uuid:faculty_uuid>/dtr-export-preview/', views.admin_dtr_export_preview, name='admin_dtr_export_preview'),
    path('admin/faculty/<uuid:faculty_uuid>/dtr-export/', views.admin_dtr_export_view, name='admin_dtr_export'),
    path('admin/teaching-assignments-dtr/', views.teaching_assignment_view, name='teaching_assignment'),
    path('admin/faculty/<uuid:faculty_uuid>/teaching-assignments/',views.teaching_assignment_list, name='teaching_assignment_list'),
    path('admin/faculty/<uuid:faculty_uuid>/teaching-assignments/create/',views.teaching_assignment_create, name='teaching_assignment_create'),
    path('admin/faculty/<uuid:faculty_uuid>/teaching-assignments/<int:pk>/edit/',views.teaching_assignment_update, name='teaching_assignment_update'),
    path('admin/faculty/<uuid:faculty_uuid>/teaching-assignments/<int:pk>/delete/',views.teaching_assignment_delete, name='teaching_assignment_delete'),

    path('admin/teaching-assignments/upload/', views.teaching_assignment_bulk_upload, name='teaching_assignment_bulk_upload'),
    path('admin/teaching-assignments/confirm/', views.teaching_assignment_bulk_confirm, name='teaching_assignment_bulk_confirm'),

    path('admin/settings/', views.admin_settings, name='admin_settings'),
    path('admin/settings/academic-years/', views.academic_years_view, name='academic_years'),
    path('admin/settings/academic-years/create/', views.create_academic_year_view, name='create_academic_year'),

    path('admin/settings/pup-sites/', views.pup_sites_admin_list, name='pup_sites_admin_list'),
    path('admin/settings/pup-sites/add/', views.pup_site_create, name='pup_site_create'),
    path('admin/settings/pup-sites/<uuid:uid>/edit/', views.pup_site_update, name='pup_site_update'),
    path('admin/settings/pup-sites/<uuid:uid>/delete/', views.pup_site_delete, name='pup_site_delete'),
   
    path('admin/settings/landing-background/', views.landing_background_settings, name='landing_background_settings'),

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