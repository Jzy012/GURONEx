import datetime

from django.test import RequestFactory, TestCase

from base.models import Account
from base.utils.academic_calendar import get_faculty_semesters, resolve_faculty_semester
from base.utils.email_base import build_recipient_list, get_faculty_notification_recipients
from faculty.models import AcademicYear, FacultyProfile, Semester, TeachingAssignment


def make_faculty(email, code, personal_email=None):
    account = Account.objects.create_user(
        email=email, password="test-pass-123", role="faculty"
    )
    return FacultyProfile.objects.create(
        account=account,
        faculty_code=code,
        name=f"Faculty {code}",
        personal_email=personal_email,
    )


def make_semester(year_start, semester_type, start, end, is_active=False):
    year, _ = AcademicYear.objects.get_or_create(
        year_start=year_start, year_end=year_start + 1
    )
    return Semester.objects.create(
        academic_year=year,
        semester_type=semester_type,
        start_date=start,
        end_date=end,
        is_active=is_active,
    )


def make_assignment(faculty, semester, subject_code="CS101"):
    return TeachingAssignment.objects.create(
        faculty=faculty,
        subject_code=subject_code,
        subject_description="Intro",
        year_section="BSCS 1-1",
        day_of_week="mon",
        start_time=datetime.time(8, 0),
        end_time=datetime.time(10, 0),
        semester=semester,
    )


class ResolveFacultySemesterTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.faculty = make_faculty("owner@pup.edu.ph", "FA001")
        self.other_faculty = make_faculty("other@pup.edu.ph", "FA002")

        self.current = make_semester(
            2026, "1st", datetime.date(2026, 8, 1), datetime.date(2026, 12, 20), is_active=True
        )
        self.past = make_semester(
            2025, "1st", datetime.date(2025, 8, 1), datetime.date(2025, 12, 20)
        )
        # A semester only the other faculty teaches in.
        self.foreign = make_semester(
            2024, "1st", datetime.date(2024, 8, 1), datetime.date(2024, 12, 20)
        )

        make_assignment(self.faculty, self.current)
        make_assignment(self.faculty, self.past)
        make_assignment(self.other_faculty, self.foreign)

    def resolve(self, query=""):
        request = self.factory.get(f"/faculty/teaching-assignments-dtr/{query}")
        return resolve_faculty_semester(request, self.faculty)

    def test_defaults_to_active_semester_without_a_parameter(self):
        semester, _, is_active_view = self.resolve()
        self.assertEqual(semester, self.current)
        self.assertTrue(is_active_view)

    def test_valid_historical_semester_is_selected(self):
        semester, _, is_active_view = self.resolve(f"?semester={self.past.id}")
        self.assertEqual(semester, self.past)
        self.assertFalse(is_active_view)

    def test_another_facultys_semester_falls_back_to_active(self):
        semester, selectable, _ = self.resolve(f"?semester={self.foreign.id}")
        self.assertEqual(semester, self.current)
        self.assertNotIn(self.foreign, selectable)

    def test_non_numeric_semester_falls_back_to_active(self):
        semester, _, _ = self.resolve("?semester=abc")
        self.assertEqual(semester, self.current)

    def test_unknown_semester_id_falls_back_to_active(self):
        semester, _, _ = self.resolve("?semester=999999")
        self.assertEqual(semester, self.current)

    def test_empty_semester_param_falls_back_to_active(self):
        semester, _, _ = self.resolve("?semester=")
        self.assertEqual(semester, self.current)

    def test_selectable_semesters_are_scoped_to_this_faculty(self):
        _, selectable, _ = self.resolve()
        self.assertIn(self.current, selectable)
        self.assertIn(self.past, selectable)
        self.assertNotIn(self.foreign, selectable)

    def test_selectable_semesters_are_newest_first(self):
        _, selectable, _ = self.resolve()
        self.assertEqual(selectable[0], self.current)

    def test_active_semester_is_offered_even_without_assignments(self):
        fresh = make_faculty("fresh@pup.edu.ph", "FA003")
        semesters = get_faculty_semesters(fresh)
        self.assertEqual(semesters, [self.current])

    def test_no_active_semester_falls_back_to_newest_viewable(self):
        # The active semester is derived from dates, so push every semester into
        # the future rather than clearing the no-longer-authoritative flag.
        Semester.objects.update(
            start_date=datetime.date(2099, 8, 1), end_date=datetime.date(2099, 12, 20)
        )
        semester, _, is_active_view = self.resolve()
        self.assertEqual(semester, self.current)
        self.assertFalse(is_active_view)

    def test_faculty_with_no_assignments_and_no_active_semester_gets_none(self):
        Semester.objects.update(
            start_date=datetime.date(2099, 8, 1), end_date=datetime.date(2099, 12, 20)
        )
        fresh = make_faculty("nobody@pup.edu.ph", "FA004")
        request = self.factory.get("/faculty/teaching-assignments-dtr/")
        semester, selectable, is_active_view = resolve_faculty_semester(request, fresh)
        self.assertIsNone(semester)
        self.assertEqual(selectable, [])
        self.assertFalse(is_active_view)


class FacultyNotificationRecipientTests(TestCase):
    def test_includes_personal_email_when_present(self):
        faculty = make_faculty("main@pup.edu.ph", "FB001", personal_email="me@gmail.com")
        self.assertEqual(
            get_faculty_notification_recipients(faculty.account),
            ["main@pup.edu.ph", "me@gmail.com"],
        )

    def test_missing_personal_email_yields_primary_only(self):
        faculty = make_faculty("solo@pup.edu.ph", "FB002")
        self.assertEqual(
            get_faculty_notification_recipients(faculty.account), ["solo@pup.edu.ph"]
        )

    def test_identical_personal_email_is_not_duplicated(self):
        faculty = make_faculty("same@pup.edu.ph", "FB003", personal_email="SAME@pup.edu.ph")
        self.assertEqual(
            get_faculty_notification_recipients(faculty.account), ["same@pup.edu.ph"]
        )

    def test_account_without_faculty_profile_yields_primary_only(self):
        admin = Account.objects.create_user(
            email="admin@pup.edu.ph", password="test-pass-123", role="admin"
        )
        self.assertEqual(get_faculty_notification_recipients(admin), ["admin@pup.edu.ph"])

    def test_none_account_yields_empty_list(self):
        self.assertEqual(get_faculty_notification_recipients(None), [])

    def test_build_recipient_list_dedupes_case_insensitively(self):
        self.assertEqual(
            build_recipient_list("A@x.com", "a@x.com", "  ", None, "b@x.com"),
            ["A@x.com", "b@x.com"],
        )
