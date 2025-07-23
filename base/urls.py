from django.urls import path
from . import views  
from .views import forgot_password_view, verify_otp_view, reset_password_view

from django.contrib.auth import views as auth_views

urlpatterns =[
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('forgot-password/', forgot_password_view, name='forgot_password'),
    path('verify-otp/', verify_otp_view, name='verify_otp'),
    path('reset-password/', reset_password_view, name='reset_password'),

    path("verify-2fa-otp/", views.verify_two_factor_otp_view, name="verify_2fa_otp"),

    path('authorize/', views.authorize_google, name='authorize_google'),
    path('oauth2callback/', views.oauth2callback, name='oauth2callback'),
]


