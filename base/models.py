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
    two_factor_authentication = models.BooleanField(default=False)


    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['role']

    objects = AccountManager()

    def __str__(self):
        return f"{self.email} ({self.role})"




# Password Reset OTP Model
class UserOTP(models.Model):
    PURPOSE_CHOICES = [
        ('password_reset', 'Password Reset'),
        ('login_2fa', 'Login 2FA'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["user", "purpose", "is_used", "expires_at"]),
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
    def create_for_user(cls, user, purpose, expiry_minutes=5):
        cls.objects.filter(
            user=user,
            purpose=purpose,
            is_used=False,
            expires_at__gt=timezone.now()
        ).update(is_used=True)

        otp = cls.generate_otp()
        expires_at = timezone.now() + timedelta(minutes=expiry_minutes)
        return cls.objects.create(user=user, otp=otp, purpose=purpose, expires_at=expires_at)

    @staticmethod
    def otp_requests_today(user, purpose):
        today = timezone.now().date()
        return UserOTP.objects.filter(
            user=user,
            purpose=purpose,
            created_at__date=today
        ).count()

    @staticmethod
    def get_active_otp(user, purpose):
        return UserOTP.objects.filter(
            user=user,
            purpose=purpose,
            is_used=False,
            expires_at__gt=timezone.now()
        ).order_by('-created_at').first()

    def __str__(self):
        return f"{self.user.email} - OTP: {self.otp} ({self.purpose})"