from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adminhub", "0008_announcement_email_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="announcement",
            name="scheduled_publish_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="announcement",
            name="email_status",
            field=models.CharField(
                choices=[
                    ("not_requested", "Not Requested"),
                    ("scheduled", "Scheduled"),
                    ("queued", "Queued"),
                    ("sending", "Sending"),
                    ("sent", "Sent"),
                    ("partial_failed", "Partially Failed"),
                    ("failed", "Failed"),
                ],
                default="not_requested",
                max_length=20,
            ),
        ),
    ]
