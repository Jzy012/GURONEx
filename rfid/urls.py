from django.urls import path
from . import views



urlpatterns = [
    path('api/rfid_tap/', views.rfid_tap_api, name='rfid_tap_api'),
    path('api/pair_rfid/', views.pair_rfid_api, name='pair_rfid_api'),
    path('api/log_attendance/', views.log_attendance, name='log_attendance'),   
    path('api/check_reset/', views.check_wifi_reset, name='check_wifi_reset'),


]