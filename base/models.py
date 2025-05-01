from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone

# Custom User Manager
class AccountManager(BaseUserManager):
    def create_user(self, email, password=None, role=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        if not role:
            raise ValueError("Users must have a role assigned")

        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, role="system_admin", **extra_fields)

# Custom User Model
class Account(AbstractUser):
    ROLE_CHOICES = (
        ('system_admin', 'System Admin'),
        ('admin', 'Admin'),
        ('faculty', 'Faculty'),
    )

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    created_at = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['role']

    objects = AccountManager()

    def __str__(self):
        return f"{self.email} ({self.role})"
