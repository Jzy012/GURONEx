from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone


from django.conf import settings
from datetime import timedelta
import secrets

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
        return self.create_user(email, password, **extra_fields)

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




# Password Reset OTP Model
class PasswordResetOTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_used", "expires_at"]),
        ]

    def has_expired(self):
        return timezone.now() > self.expires_at

    def mark_as_used(self):
        self.is_used = True
        self.save()

    @staticmethod
    def generate_otp(length=6):
        return ''.join(secrets.choice('0123456789') for _ in range(length))

    @classmethod
    def create_for_user(cls, user, expiry_minutes=10): 
        # Invalidate old unused OTPs for this user
        cls.objects.filter(
            user=user,
            is_used=False,
            expires_at__gt=timezone.now()
        ).update(is_used=True)

        otp = cls.generate_otp()
        expires_at = timezone.now() + timedelta(minutes=expiry_minutes)
        return cls.objects.create(user=user, otp=otp, expires_at=expires_at)

    @staticmethod
    def otp_requests_today(user):
        today = timezone.now().date()
        return PasswordResetOTP.objects.filter(
            user=user,
            created_at__date=today
        ).count()

    @staticmethod
    def get_active_otp(user):
        return PasswordResetOTP.objects.filter(
            user=user, is_used=False, expires_at__gt=timezone.now()
        ).order_by('-created_at').first()

    def __str__(self):
        return f"{self.user.email} - OTP: {self.otp} ({'used' if self.is_used else 'active'})"