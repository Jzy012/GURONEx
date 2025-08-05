from django.urls import path
from . import views
from django.contrib.auth import views as auth_views


app_name = 'adminhub'


urlpatterns = [
    path('admin/home/', views.home, name='home'),

    path('admin/documents/', views.documents, name='documents'),

    path('admin/faculty-list/', views.faculty_list_view, name='faculty_list'),
    path('admin/faculty/<uuid:faculty_uuid>/', views.faculty_detail_view, name='faculty_detail'),
    path('admin/faculty/create/', views.create_faculty_view, name='create_faculty'),

    path('admin/announcements/', views.announcements_view, name='announcements'),
    path('admin/announcements/create/', views.create_announcement_view, name='create_announcement'),
    path('admin/announcements/edit/<uuid:uuid>/', views.edit_announcement_view, name='edit_announcement'),
    path('admin/announcements/delete/<uuid:uuid>/', views.delete_announcement_view, name='delete_announcement'),


    path('admin/deliverables/', views.deliverables_view, name='deliverables'),
    path('admin/deliverables/deliverable-templates/create/',views.create_deliverable_template_view,name='create_deliverable_template'),
    path('admin/deliverables/deliverable-templates/',views.deliverable_templates_view,name='deliverable_template'),

    path('admin/deliverables/assign/', views.assign_deliverables_view, name='assign_deliverables'),

    path('admin/settings/', views.admin_settings, name='admin_settings'),

    path('admin/settings/academic-years/', views.academic_years_view, name='academic_years'),
    path('admin/settings/academic-years/create/', views.create_academic_year_view, name='create_academic_year'),


    path('admin/settings/change-password/', auth_views.PasswordChangeView.as_view(
        template_name='admin/admin_change_password.html',
        success_url='/admin/settings/change-password/done/'
    ), name='admin_change_password'),

    path('admin/settings/change-password/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='admin/admin_change_password_done.html'
    ), name='admin_change_password_done'),


    path('admin/settings/two-factor/', views.admin_2fa, name='admin_2fa'),

]