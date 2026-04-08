from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('applicant', '0010_rejected_status_and_date'),
    ]

    operations = [
        migrations.AlterField(
            model_name='applicant',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('demo_scheduled', 'Demo Scheduled'),
                    ('for_interview', 'For Interview'),
                    ('psych_test', 'Psych Test'),
                    ('contract_of_service', 'Contract of Service'),
                    ('first_salary_requirements', 'First Salary Requirements'),
                    ('hired', 'Hired'),
                    ('rejected', 'Rejected'),
                ],
                default='pending',
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='applicant',
            name='rejected_from_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('pending', 'Pending'),
                    ('demo_scheduled', 'Demo Scheduled'),
                    ('for_interview', 'For Interview'),
                    ('psych_test', 'Psych Test'),
                    ('contract_of_service', 'Contract of Service'),
                    ('first_salary_requirements', 'First Salary Requirements'),
                    ('hired', 'Hired'),
                ],
                max_length=40,
                null=True,
            ),
        ),
    ]
