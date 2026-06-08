import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


INITIAL_SPECIALIZATIONS = [
    "Accountancy and Finance",
    "Business Administration major in Human Resource Management",
    "Business Administration major in Marketing Management",
    "English Language Teaching",
    "Mathematics Education",
    "Educational Management",
    "Information and Computer Technology",
    "Entrepreneurship",
    "Life and Physical Science",
    "Social and Behavioral Science",
    "Humanities and Fine Arts",
    "Law and Government Works",
    "Physical Education",
    "Others",
]


def seed_specializations(apps, schema_editor):
    AreaOfSpecialization = apps.get_model('applicant', 'AreaOfSpecialization')
    for name in INITIAL_SPECIALIZATIONS:
        AreaOfSpecialization.objects.get_or_create(name=name)


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('applicant', '0012_step_workflow_models'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Create AreaOfSpecialization model
        migrations.CreateModel(
            name='AreaOfSpecialization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Area of Specialization',
                'verbose_name_plural': 'Areas of Specialization',
                'ordering': ['name'],
            },
        ),

        # 2. Seed initial specializations
        migrations.RunPython(seed_specializations, reverse_seed),

        # 3. Add area_of_specialization FK to Applicant (nullable)
        migrations.AddField(
            model_name='applicant',
            name='area_of_specialization',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='applicants',
                to='applicant.areaofspecialization',
            ),
        ),

        # 4. Remove the old department CharField
        migrations.RemoveField(
            model_name='applicant',
            name='department',
        ),

        # 5. Educational background fields
        migrations.AddField(
            model_name='applicant',
            name='college_degree',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='applicant',
            name='college_institution',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='applicant',
            name='masters_degree',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='applicant',
            name='masters_institution',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='applicant',
            name='doctorate_degree',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='applicant',
            name='doctorate_institution',
            field=models.CharField(blank=True, max_length=200),
        ),

        # 6. Rejection audit trail
        migrations.AddField(
            model_name='applicant',
            name='rejected_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rejected_applicants',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='applicant',
            name='rejection_message',
            field=models.TextField(blank=True),
        ),

        # 7. Availability confirmation
        migrations.AddField(
            model_name='applicant',
            name='confirmed_by_applicant',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='applicant',
            name='confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # 8. Voluntary withdrawal
        migrations.AddField(
            model_name='applicant',
            name='cancelled_by_applicant',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='applicant',
            name='cancelled_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='applicant',
            name='cancellation_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='applicant',
            name='withdrawn_from_status',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),

        # 9. Add 'withdrawn' to status choices
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
                    ('withdrawn', 'Withdrawn'),
                ],
                default='pending',
                max_length=30,
            ),
        ),
    ]
