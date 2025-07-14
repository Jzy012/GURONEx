from django.urls import path
from . import views
from django.contrib.auth import views as auth_views


app_name = 'faculty'


urlpatterns = [
    path('faculty/home/', views.home, name='home'),


    path('faculty/settings/', views.faculty_settings_view, name='faculty_settings'),

    path('faculty/settings/change-password/', auth_views.PasswordChangeView.as_view(
        template_name='faculty/faculty_change_password.html',
        success_url='/faculty/settings/change-password/done/'
    ), name='faculty_change_password'),

    path('faculty/settings/change-password/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='faculty/faculty_change_password_done.html'
    ), name='faculty_change_password_done'),
]