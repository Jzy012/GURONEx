import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
from datetime import timedelta


INITIAL_CRITERIA = [
    "Communication Skills",
    "Subject Matter Expertise",
    "Instructional Competence",
    "Research Engagement/Potential",
    "Attitude and Professional Demeanor",
    "Alignment with Institutional Values",
    "Potential Contribution to Department",
]


def seed_criteria(apps, schema_editor):
    EvaluationCriteria = apps.get_model('applicant', 'EvaluationCriteria')
    for order, label in enumerate(INITIAL_CRITERIA, start=1):
        EvaluationCriteria.objects.get_or_create(label=label, defaults={'order': order})


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('applicant', '0013_enhancements'),
        ('faculty', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Add evaluation_date and evaluation_deadline to Applicant
        migrations.AddField(
            model_name='applicant',
            name='evaluation_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='applicant',
            name='evaluation_deadline',
            field=models.DateField(blank=True, null=True),
        ),

        # 2. Add 'evaluation' to Applicant status choices
        migrations.AlterField(
            model_name='applicant',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Initial Review'),
                    ('demo_scheduled', 'Demo Scheduled'),
                    ('for_interview', 'For Interview'),
                    ('evaluation', 'Evaluation'),
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

        # 3. Add 'evaluation' to rejected_from_status choices
        migrations.AlterField(
            model_name='applicant',
            name='rejected_from_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('pending', 'Initial Review'),
                    ('demo_scheduled', 'Demo Scheduled'),
                    ('for_interview', 'For Interview'),
                    ('evaluation', 'Evaluation'),
                    ('psych_test', 'Psych Test'),
                    ('contract_of_service', 'Contract of Service'),
                    ('first_salary_requirements', 'First Salary Requirements'),
                    ('hired', 'Hired'),
                ],
                max_length=40,
                null=True,
            ),
        ),

        # 4. Also update 'pending' label in status choices (cosmetic, from 'Pending' → 'Initial Review')
        # Already handled in operation 2 above.

        # 5. Create EvaluationCriteria
        migrations.CreateModel(
            name='EvaluationCriteria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=255)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Evaluation Criteria',
                'verbose_name_plural': 'Evaluation Criteria',
                'ordering': ['order', 'label'],
            },
        ),

        # 6. Seed the 7 criteria
        migrations.RunPython(seed_criteria, reverse_seed),

        # 7. Create EvaluationAssignment
        migrations.CreateModel(
            name='EvaluationAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('token', models.CharField(db_index=True, max_length=64, unique=True)),
                ('token_expires_at', models.DateTimeField()),
                ('is_submitted', models.BooleanField(default=False)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('applicant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='evaluation_assignments',
                    to='applicant.applicant',
                )),
                ('evaluator', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='evaluation_assignments',
                    to='faculty.facultyprofile',
                )),
                ('assigned_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_evaluation_assignments',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['assigned_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='evaluationassignment',
            constraint=models.UniqueConstraint(
                fields=['applicant', 'evaluator'],
                name='unique_evaluation_assignment',
            ),
        ),

        # 8. Create EvaluationSubmission
        migrations.CreateModel(
            name='EvaluationSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('summary', models.TextField(blank=True)),
                ('justification', models.TextField(blank=True)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('assignment', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='submission',
                    to='applicant.evaluationassignment',
                )),
            ],
        ),

        # 9. Create EvaluationScore
        migrations.CreateModel(
            name='EvaluationScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField(choices=[
                    (1, '1 – Poor'), (2, '2 – Needs Improvement'), (3, '3 – Satisfactory'),
                    (4, '4 – Very Good'), (5, '5 – Excellent'),
                ])),
                ('comments', models.TextField(blank=True)),
                ('criteria', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='scores',
                    to='applicant.evaluationcriteria',
                )),
                ('submission', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='scores',
                    to='applicant.evaluationsubmission',
                )),
            ],
            options={
                'ordering': ['criteria__order'],
            },
        ),
        migrations.AddConstraint(
            model_name='evaluationscore',
            constraint=models.UniqueConstraint(
                fields=['submission', 'criteria'],
                name='unique_score_per_criteria',
            ),
        ),
    ]
