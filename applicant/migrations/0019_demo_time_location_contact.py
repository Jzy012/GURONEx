from django.db import migrations, models
import faculty.models


class Migration(migrations.Migration):

    dependencies = [
        ('applicant', '0018_step_instructions'),
    ]

    operations = [
        migrations.AddField(
            model_name='applicant',
            name='demo_scheduled_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='applicant',
            name='demo_location',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='applicantreschedulerequest',
            name='preferred_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='applicant',
            name='emergency_contact_number',
            field=models.CharField(
                blank=True,
                max_length=11,
                null=True,
                validators=[faculty.models.phone_validator],
            ),
        ),
    ]
