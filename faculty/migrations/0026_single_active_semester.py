"""
Collapse multiply-active semesters down to a single active row.

update_active_semesters() used to activate the latest started semester in *each*
academic year, so every finished academic year kept one semester flagged active
forever. Code that queries is_active=True directly (admin deliverables pages,
notification tasks) could then resolve to a stale semester.

The resolution rule is duplicated here rather than imported from the model,
because a data migration must keep working even when the model code changes.
It mirrors Semester.resolve_for_date().
"""

from django.db import migrations
from django.utils import timezone


def collapse_to_single_active_semester(apps, schema_editor):
    Semester = apps.get_model('faculty', 'Semester')
    AcademicYear = apps.get_model('faculty', 'AcademicYear')

    today = timezone.localdate()

    # 1. A semester containing today (inclusive both ends), newest first.
    active = (
        Semester.objects
        .filter(start_date__lte=today, end_date__gte=today)
        .order_by('-start_date', '-id')
        .first()
    )

    # 2. Otherwise the most recently started semester (gap behaviour).
    if active is None:
        active = (
            Semester.objects
            .filter(start_date__lte=today)
            .order_by('-start_date', '-id')
            .first()
        )

    if active is None:
        # Nothing has started yet - clear any stray flags and stop.
        Semester.objects.filter(is_active=True).update(is_active=False)
        return

    Semester.objects.exclude(pk=active.pk).filter(is_active=True).update(is_active=False)
    Semester.objects.filter(pk=active.pk).update(is_active=True)

    # Keep the academic-year flag consistent with the semester we just picked.
    AcademicYear.objects.exclude(pk=active.academic_year_id).filter(
        is_active=True
    ).update(is_active=False)
    AcademicYear.objects.filter(pk=active.academic_year_id).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0025_alter_facultyprofile_designation'),
    ]

    operations = [
        # Reverse is a no-op: the old multi-active state was a bug, not a state
        # worth restoring.
        migrations.RunPython(collapse_to_single_active_semester, migrations.RunPython.noop),
    ]
