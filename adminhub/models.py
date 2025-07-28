from django.db import models
from base.models import Account  # your custom user model


# Create your models here.

class AdminProfile(models.Model):
    account = models.OneToOneField(Account, on_delete=models.CASCADE, related_name='admin_profile')
    name = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or self.account.email




# adminhub/models.py

import uuid
from django.db import models
from django.utils import timezone
from base.models import Account  

class Announcement(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    title = models.CharField(max_length=255)
    content = models.TextField()
    creator = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True)
    visible_to_roles = models.JSONField(default=list)  # Example: ['faculty', 'admin']
    is_important = models.BooleanField(default=False)
    send_email = models.BooleanField(default=False)
    attachment_link = models.URLField(null=True, blank=True)

    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_visible(self):
        today = timezone.now().date()
        return self.is_active and self.start_date <= today and (self.end_date is None or today <= self.end_date)

    def __str__(self):
        return f"{self.title} ({', '.join(self.visible_to_roles)})"


class AnnouncementViewLog(models.Model):
    user = models.ForeignKey(Account, on_delete=models.CASCADE)
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'announcement')
        ordering = ['-seen_at']

    def __str__(self):
        return f"{self.user.email} saw {self.announcement.title} at {self.seen_at}"
