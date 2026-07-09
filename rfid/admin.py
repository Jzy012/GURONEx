from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import RFIDTag, AttendanceLog, ESP32WiFi

# Register your models here.


@admin.register(RFIDTag)
class RFIDTagAdmin(ModelAdmin):
    list_display = ('uid', 'faculty', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('uid', 'faculty__name')


@admin.register(AttendanceLog)
class AttendanceLogAdmin(ModelAdmin):
    list_display = ('faculty', 'date', 'time_in', 'time_out', 'is_manual')
    list_filter = ('date', 'is_manual')
    search_fields = ('faculty__name', 'uid')


@admin.register(ESP32WiFi)
class ESP32WiFiAdmin(ModelAdmin):
    list_display = ('device_name', 'reset_wifi')
