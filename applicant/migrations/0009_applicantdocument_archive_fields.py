from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('applicant', '0008_applicant_status_step_dates'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='applicantdocument',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='applicantdocument',
            name='archived_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='archived_applicant_documents', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='applicantdocument',
            name='is_archived',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='applicantdocument',
            name='restored_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='applicantdocument',
            name='restored_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='restored_applicant_documents', to=settings.AUTH_USER_MODEL),
        ),
    ]
