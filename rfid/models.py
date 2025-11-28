from django.db import models

# Create your models here.


from django.db import models
from faculty.models import FacultyProfile  # adjust import to your FEMS app location
from django.utils import timezone


class RFIDTag(models.Model):
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, null=True, blank=True)
    uid = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)


class AttendanceLog(models.Model):
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE)
    uid = models.CharField(max_length=50)
    date = models.DateField(default=timezone.localdate)
    time_in = models.DateTimeField(null=True, blank=True)
    time_out = models.DateTimeField(null=True, blank=True)




class ESP32WiFi(models.Model):
    device_name = models.CharField(max_length=50, default="ESP32")
    reset_wifi = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.device_name} WiFi Control"