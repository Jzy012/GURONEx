from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("faculty", "0020_deliverabletemplate_is_default"),
    ]

    operations = [
        migrations.CreateModel(
            name="FacultyClearanceRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("Requested", "Requested"), ("Approved", "Approved"), ("Rejected", "Rejected")], default="Requested", max_length=20)),
                ("clearance_number", models.CharField(blank=True, max_length=120)),
                ("snapshot_total_required", models.PositiveIntegerField(default=0)),
                ("snapshot_total_approved", models.PositiveIntegerField(default=0)),
                ("snapshot_total_pending", models.PositiveIntegerField(default=0)),
                ("snapshot_total_rejected", models.PositiveIntegerField(default=0)),
                ("snapshot_total_missing", models.PositiveIntegerField(default=0)),
                ("snapshot_total_overdue", models.PositiveIntegerField(default=0)),
                ("requested_at", models.DateTimeField(auto_now=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("faculty", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="clearance_requests", to="faculty.facultyprofile")),
                ("semester", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="faculty_clearance_requests", to="faculty.semester")),
            ],
            options={
                "ordering": ["-updated_at"],
                "constraints": [models.UniqueConstraint(fields=("faculty", "semester"), name="unique_faculty_clearance_per_semester")],
            },
        ),
    ]
