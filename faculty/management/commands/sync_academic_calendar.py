"""
Force (or inspect) the active academic year / semester calculation.

Wraps the same helper the nightly Celery beat job uses, so there is exactly one
synchronization implementation. Useful to repair the calendar immediately
without waiting for the 00:05 tick, and to verify what the sync would decide.
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from adminhub.tasks import _sync_active_academic_calendar
from faculty.models import AcademicYear, Semester


class Command(BaseCommand):
    help = "Recalculate the active academic year and semester from the calendar dates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="ref_date",
            help="Reference date in YYYY-MM-DD form. Defaults to today (Asia/Manila).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be activated without writing anything.",
        )

    def handle(self, *args, **options):
        ref_date = options.get("ref_date")
        if ref_date:
            try:
                ref_date = datetime.date.fromisoformat(ref_date)
            except (TypeError, ValueError):
                raise CommandError(f"Invalid --date value: {ref_date!r}. Use YYYY-MM-DD.")
        else:
            ref_date = timezone.localdate()

        self.stdout.write(f"Reference date: {ref_date}")

        resolved = Semester.resolve_for_date(ref_date=ref_date)
        self.stdout.write(f"Resolved semester: {resolved or 'None (no semester has started)'}")

        if options.get("dry_run"):
            currently_active = list(Semester.objects.filter(is_active=True))
            self.stdout.write(
                f"Currently flagged active: {len(currently_active)} "
                f"({', '.join(str(s) for s in currently_active) or 'none'})"
            )
            self.stdout.write(self.style.WARNING("Dry run - nothing written."))
            return

        payload = _sync_active_academic_calendar(ref_date=ref_date)

        active_semesters = list(Semester.objects.filter(is_active=True))
        active_years = list(AcademicYear.objects.filter(is_active=True))

        self.stdout.write(f"Active semesters after sync: {len(active_semesters)}")
        for semester in active_semesters:
            self.stdout.write(f"  - {semester.label}")
        self.stdout.write(f"Active academic years after sync: {len(active_years)}")

        if len(active_semesters) > 1:
            self.stdout.write(
                self.style.ERROR(
                    f"Expected at most one active semester, found {len(active_semesters)}."
                )
            )
            return

        self.stdout.write(self.style.SUCCESS(f"Calendar synced: {payload}"))
