from django.urls import path
from . import views



urlpatterns = [
    path('api/rfid_tap/', views.rfid_tap_api, name='rfid_tap_api'),
    # path('api/rfid_list/', views.rfid_list_api, name='rfid_list_api'),
    path('api/pair_rfid/', views.pair_rfid_api, name='pair_rfid_api'),
    # path('api/last_rfid_uid/', views.last_rfid_uid_api, name='last_rfid_uid_api'),
    path('api/log_attendance/', views.log_attendance, name='log_attendance'),   
    path('api/check_reset/', views.check_wifi_reset, name='check_wifi_reset'),


    # path('api/auto_log_update_api/', views.auto_log_update_api, name='auto_log_update_api'),
]