from django.urls import path
from . import views
from django.contrib.auth import views as auth_views


app_name = 'adminhub'


urlpatterns = [
    path('admin/home/', views.home, name='home'),
    path('admin/documents/', views.documents, name='documents'),
    path('admin/settings/', views.admin_settings, name='admin_settings'),


    path('admin/settings/change-password/', auth_views.PasswordChangeView.as_view(
        template_name='admin/admin_change_password.html',
        success_url='/admin/settings/change-password/done/'
    ), name='admin_change_password'),

    path('admin/settings/change-password/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='admin/admin_change_password_done.html'
    ), name='admin_change_password_done'),
]