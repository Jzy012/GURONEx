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
