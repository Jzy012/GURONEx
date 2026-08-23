"""
Official Work Hours totals for the DTR exports.

The rule (see base/utils/dtr_workinghours.py): sum the scheduled duration of
every teaching assignment whose DTRCalculator status is not 'absent'. Days with
no assignments, and days with no attendance, credit nothing.
"""

import datetime

from django.test import TestCase
from django.utils import timezone

from base.models import Account
from base.utils.dtr_workinghours import calculate_official_work_hours
from faculty.models import AcademicYear, FacultyProfile, Semester, TeachingAssignment
from rfid.models import AttendanceLog
from services.dtr_service import DTRCalculator

# 2026-08-10 is a Monday; the whole month sits inside the semester below.
YEAR = 2026
MONTH = 8
MONDAY = datetime.date(2026, 8, 10)


def make_faculty(email, code):
    account = Account.objects.create_user(
        email=email, password="test-pass-123", role="faculty"
    )
    return FacultyProfile.objects.create(
        account=account, faculty_code=code, name=f"Faculty {code}"
    )


def aware(day, hour, minute=0):
    return timezone.make_aware(
        datetime.datetime.combine(day, datetime.time(hour, minute))
    )


class DTRWorkHoursTests(TestCase):
    def setUp(self):
        self.faculty = make_faculty("hours@pup.edu.ph", "FH001")
        year = AcademicYear.objects.create(year_start=2026, year_end=2027)
        self.semester = Semester.objects.create(
            academic_year=year,
            semester_type="1st",
            start_date=datetime.date(2026, 8, 1),
            end_date=datetime.date(2026, 12, 20),
        )

    def add_assignment(self, start, end, day_of_week="mon", code="CS101", faculty=None):
        return TeachingAssignment.objects.create(
            faculty=faculty or self.faculty,
            subject_code=code,
            subject_description="Course",
            year_section="BSCS 1-1",
            day_of_week=day_of_week,
            start_time=datetime.time(*start),
            end_time=datetime.time(*end),
            semester=self.semester,
        )

    def add_log(self, day, time_in, time_out=None, faculty=None):
        return AttendanceLog.objects.create(
            faculty=faculty or self.faculty,
            date=day,
            time_in=aware(day, *time_in) if time_in else None,
            time_out=aware(day, *time_out) if time_out else None,
        )

    def hours(self, faculty=None):
        dtr = DTRCalculator.get_dtr_for_month(faculty or self.faculty, YEAR, MONTH)
        return calculate_official_work_hours(dtr)

    def statuses_on(self, day, faculty=None):
        dtr = DTRCalculator.get_dtr_for_month(faculty or self.faculty, YEAR, MONTH)
        return [s["status"] for s in dtr[day.day - 1]["statuses"]]

    # --- the reported bug ---

    def test_shift_spanning_noon_credits_all_attended_assignments(self):
        """
        08:00-17:00 across a morning and an afternoon class. The old
        implementation bucketed this as am_in + pm_out, left both AM/PM pairs
        incomplete, and reported 0h 00m.
        """
        self.add_assignment((8, 0), (10, 0), code="CS101")
        self.add_assignment((13, 0), (15, 0), code="CS102")
        self.add_log(MONDAY, (8, 0), (17, 0))

        self.assertNotIn("absent", self.statuses_on(MONDAY))
        self.assertEqual(self.hours(), "4h 00m")

    def test_single_morning_class_credits_its_scheduled_duration(self):
        self.add_assignment((8, 0), (10, 30))
        self.add_log(MONDAY, (8, 0), (10, 30))
        self.assertEqual(self.hours(), "2h 30m")

    def test_single_afternoon_class_credits_its_scheduled_duration(self):
        self.add_assignment((13, 0), (17, 0))
        self.add_log(MONDAY, (13, 0), (17, 0))
        self.assertEqual(self.hours(), "4h 00m")

    # --- zero cases ---

    def test_no_attendance_log_credits_nothing(self):
        self.add_assignment((8, 0), (10, 0))
        self.assertEqual(self.hours(), "0h 00m")

    def test_month_with_no_data_at_all_credits_nothing(self):
        self.assertEqual(self.hours(), "0h 00m")

    def test_attendance_with_no_scheduled_assignment_credits_nothing(self):
        """Official hours are scheduled teaching hours, so presence alone is 0."""
        self.add_log(MONDAY, (8, 0), (17, 0))
        self.assertEqual(self.statuses_on(MONDAY), ["no assignment"])
        self.assertEqual(self.hours(), "0h 00m")

    def test_absent_assignment_is_not_credited(self):
        """
        Leaving before a later class ends marks that class absent; only the
        attended one counts.
        """
        self.add_assignment((8, 0), (10, 0), code="CS101")
        self.add_assignment((13, 0), (15, 0), code="CS102")
        self.add_log(MONDAY, (8, 0), (11, 0))

        self.assertIn("absent", self.statuses_on(MONDAY))
        self.assertEqual(self.hours(), "2h 00m")

    # --- agreed crediting rule ---

    def test_late_arrival_still_credits_the_full_duration(self):
        self.add_assignment((8, 0), (10, 0))
        self.add_log(MONDAY, (9, 0), (10, 0))  # 60 min late, past the 45 min threshold
        self.assertEqual(self.hours(), "2h 00m")

    def test_missing_time_out_follows_the_status_rules(self):
        """
        A tap-in with no tap-out is still credited when it lands within the
        scheduled window - it is not a raw span, so it is not silently 0.
        """
        self.add_assignment((8, 0), (10, 0))
        self.add_log(MONDAY, (8, 0), None)
        self.assertEqual(self.hours(), "2h 00m")

    # --- aggregation ---

    def test_totals_accumulate_across_multiple_days(self):
        self.add_assignment((8, 0), (10, 0))
        for day in (MONDAY, MONDAY + datetime.timedelta(days=7)):
            self.add_log(day, (8, 0), (10, 0))
        self.assertEqual(self.hours(), "4h 00m")

    def test_minutes_are_formatted_with_two_digits(self):
        self.add_assignment((8, 0), (9, 5))
        self.add_log(MONDAY, (8, 0), (9, 5))
        self.assertEqual(self.hours(), "1h 05m")

    # --- isolation ---

    def test_another_facultys_assignments_are_never_counted(self):
        other = make_faculty("other-hours@pup.edu.ph", "FH002")
        self.add_assignment((8, 0), (10, 0), code="OTHER1", faculty=other)
        self.add_log(MONDAY, (8, 0), (10, 0), faculty=other)

        self.assertEqual(self.hours(), "0h 00m")
        self.assertEqual(self.hours(faculty=other), "2h 00m")

    # --- helper-level guards ---

    def test_handles_empty_and_none_input(self):
        self.assertEqual(calculate_official_work_hours([]), "0h 00m")
        self.assertEqual(calculate_official_work_hours(None), "0h 00m")

    def test_duplicate_status_entries_credit_only_once(self):
        """A pk-keyed guard stops an assignment being counted twice in a day."""
        assignment = self.add_assignment((8, 0), (10, 0))
        duplicated = [
            {
                "date": MONDAY,
                "statuses": [
                    {"assignment": assignment, "status": "on time"},
                    {"assignment": assignment, "status": "on time"},
                ],
            }
        ]
        self.assertEqual(calculate_official_work_hours(duplicated), "2h 00m")
