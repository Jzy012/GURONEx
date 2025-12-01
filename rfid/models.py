from django.db import models

# Create your models here.


from django.db import models
from faculty.models import FacultyProfile, TeachingAssignment  # adjust import to your FEMS app location
from django.utils import timezone


class RFIDTag(models.Model):
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, null=True, blank=True)
    uid = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)




class AttendanceLog(models.Model):
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE)
    uid = models.CharField(max_length=50, blank=True, null=True)
    date = models.DateField(default=timezone.localdate)
    time_in = models.DateTimeField(null=True, blank=True)
    time_out = models.DateTimeField(null=True, blank=True)
    teaching_assignments = models.ManyToManyField(
        TeachingAssignment,
        blank=True,
        related_name='attendance_logs',
    )
    is_manual = models.BooleanField(default=False)    


    def __str__(self):
        return f"{self.faculty} - {self.date} ({self.time_in} - {self.time_out})"


class ESP32WiFi(models.Model):
    device_name = models.CharField(max_length=50, default="ESP32")
    reset_wifi = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.device_name} WiFi Control"