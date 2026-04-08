from django.db import migrations, models


def migrate_failed_to_rejected(apps, schema_editor):
    Applicant = apps.get_model('applicant', 'Applicant')
    Applicant.objects.filter(status='failed').update(status='rejected')


class Migration(migrations.Migration):

    dependencies = [
        ('applicant', '0009_applicantdocument_archive_fields'),
    ]

    operations = [
        migrations.RenameField(
            model_name='applicant',
            old_name='failed_date',
            new_name='rejected_date',
        ),
        migrations.AlterField(
            model_name='applicant',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('demo_scheduled', 'Demo Scheduled'),
                    ('for_interview', 'For Interview'),
                    ('psych_test', 'Psych Test'),
                    ('hired', 'Hired'),
                    ('rejected', 'Rejected'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.RunPython(migrate_failed_to_rejected, migrations.RunPython.noop),
    ]
