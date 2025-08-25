from django.contrib import admin
from .models import RFIDTag, AttendanceLog, ESP32WiFi

# Register your models here.


admin.site.register(RFIDTag)
admin.site.register(AttendanceLog)

@admin.register(ESP32WiFi)
class ESP32WiFiAdmin(admin.ModelAdmin):
    list_display = ('device_name', 'reset_wifi')    
