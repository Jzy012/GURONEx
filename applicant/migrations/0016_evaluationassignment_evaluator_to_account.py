import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('applicant', '0015_evaluation_assignment_deadline'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Drop the old FK constraint (FacultyProfile) so we can update the IDs freely.
        migrations.RunSQL(
            sql="ALTER TABLE applicant_evaluationassignment DROP CONSTRAINT IF EXISTS applicant_evaluation_evaluator_id_62e6c44d_fk_faculty_f",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Convert evaluator_id from FacultyProfile PK → Account PK using the 1:1 link.
        # Assignments whose profile no longer exists are deleted.
        migrations.RunSQL(
            sql="""
                UPDATE applicant_evaluationassignment ea
                SET evaluator_id = fp.account_id
                FROM faculty_facultyprofile fp
                WHERE ea.evaluator_id = fp.id;

                DELETE FROM applicant_evaluationscore
                WHERE submission_id IN (
                    SELECT id FROM applicant_evaluationsubmission
                    WHERE assignment_id IN (
                        SELECT id FROM applicant_evaluationassignment
                        WHERE evaluator_id NOT IN (SELECT id FROM base_account)
                    )
                );

                DELETE FROM applicant_evaluationsubmission
                WHERE assignment_id IN (
                    SELECT id FROM applicant_evaluationassignment
                    WHERE evaluator_id NOT IN (SELECT id FROM base_account)
                );

                DELETE FROM applicant_evaluationassignment
                WHERE evaluator_id NOT IN (SELECT id FROM base_account);
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Now alter the field to point to Account with the proper FK constraint.
        migrations.AlterField(
            model_name='evaluationassignment',
            name='evaluator',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='evaluation_assignments',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
