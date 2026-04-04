from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adminhub", "0007_documenttemplate"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="email_attempted_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="announcement",
            name="email_failed_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="announcement",
            name="email_last_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="announcement",
            name="email_processed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="announcement",
            name="email_queued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="announcement",
            name="email_sent_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="announcement",
            name="email_status",
            field=models.CharField(
                choices=[
                    ("not_requested", "Not Requested"),
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
