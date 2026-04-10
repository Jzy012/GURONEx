from celery import shared_task
from datetime import timedelta
from django.db.models import Q
from django.utils import timezone

from .models import UserOTP


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def cleanup_user_otps_task(self):
    cutoff = timezone.now() - timedelta(days=1)
    deleted_count, _ = UserOTP.objects.filter(
        Q(created_at__lt=cutoff)
    ).delete()
    return {"deleted": deleted_count}