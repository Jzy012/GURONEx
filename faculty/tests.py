import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from base.models import Account
from faculty.models import AcademicYear, FacultyProfile, Semester, TeachingAssignment


def make_year(start, end, is_active=False):
    return AcademicYear.objects.create(year_start=start, year_end=end, is_active=is_active)


def make_semester(year, semester_type, start, end, is_active=False):
    return Semester.objects.create(
        academic_year=year,
        semester_type=semester_type,
        start_date=start,
        end_date=end,
        is_active=is_active,
    )


class SemesterLabelTests(TestCase):
    def test_label_uses_academic_year_then_semester(self):
        year = make_year(2026, 2027)
        semester = make_semester(
            year, "1st", datetime.date(2026, 8, 1), datetime.date(2026, 12, 20)
        )
        self.assertEqual(semester.label, "2026–2027 • 1st Semester")


class SemesterResolveForDateTests(TestCase):
    """
    The active semester is derived from the calendar dates, never from the
    stored is_active flag, so transitions happen the moment a date passes even
    if the nightly sync did not run. ref_date is passed explicitly so these
    tests never depend on the wall clock.
    """

    def setUp(self):
        self.year = make_year(2026, 2027)
        # 1st: Aug 1 - Dec 15 2026 | 2nd: Jan 5 - May 15 2027  (the reported case)
        self.first = make_semester(
            self.year, "1st", datetime.date(2026, 8, 1), datetime.date(2026, 12, 15)
        )
        self.second = make_semester(
            self.year, "2nd", datetime.date(2027, 1, 5), datetime.date(2027, 5, 15)
        )

    # --- boundaries ---

    def test_day_before_start_is_not_yet_current(self):
        self.assertIsNone(Semester.resolve_for_date(datetime.date(2026, 7, 31)))

    def test_start_date_today_is_current(self):
        """start_date == today is inclusive."""
        self.assertEqual(
            Semester.resolve_for_date(datetime.date(2026, 8, 1)), self.first
        )

    def test_day_after_start_is_current(self):
        self.assertEqual(
            Semester.resolve_for_date(datetime.date(2026, 8, 2)), self.first
        )

    def test_end_date_today_is_still_current(self):
        """end_date == today is inclusive."""
        self.assertEqual(
            Semester.resolve_for_date(datetime.date(2026, 12, 15)), self.first
        )

    # --- the reported bug ---

    def test_next_semester_wins_once_it_starts(self):
        self.assertEqual(
            Semester.resolve_for_date(datetime.date(2027, 1, 5)), self.second
        )

    def test_next_semester_stays_current_after_its_start(self):
        self.assertEqual(
            Semester.resolve_for_date(datetime.date(2027, 3, 1)), self.second
        )

    def test_future_semester_does_not_activate_early(self):
        """The day before the 2nd starts, the 1st is still the answer."""
        self.assertEqual(
            Semester.resolve_for_date(datetime.date(2027, 1, 4)), self.first
        )

    # --- gap behaviour ---

    def test_gap_keeps_the_previous_semester_current(self):
        for day in (datetime.date(2026, 12, 16), datetime.date(2027, 1, 1)):
            with self.subTest(day=day):
                self.assertEqual(Semester.resolve_for_date(day), self.first)

    # --- academic year rollover ---

    def test_rolls_over_into_the_next_academic_year(self):
        next_year = make_year(2027, 2028)
        next_first = make_semester(
            next_year, "1st", datetime.date(2027, 8, 1), datetime.date(2027, 12, 15)
        )
        self.assertEqual(
            Semester.resolve_for_date(datetime.date(2027, 5, 15)), self.second
        )
        self.assertEqual(
            Semester.resolve_for_date(datetime.date(2027, 8, 1)), next_first
        )

    # --- degenerate data ---

    def test_no_semester_started_returns_none(self):
        Semester.objects.all().delete()
        make_semester(
            self.year, "1st", datetime.date(2030, 8, 1), datetime.date(2030, 12, 15)
        )
        self.assertIsNone(Semester.resolve_for_date(datetime.date(2026, 8, 1)))

    def test_empty_calendar_returns_none(self):
        Semester.objects.all().delete()
        self.assertIsNone(Semester.resolve_for_date(datetime.date(2026, 8, 1)))

    def test_overlapping_semesters_pick_the_latest_start_deterministically(self):
        overlapping = make_semester(
            self.year, "summer", datetime.date(2026, 10, 1), datetime.date(2026, 12, 31)
        )
        day = datetime.date(2026, 11, 1)
        self.assertEqual(Semester.resolve_for_date(day), overlapping)
        self.assertEqual(
            Semester.resolve_for_date(day), Semester.resolve_for_date(day)
        )

    def test_ignores_a_wrong_is_active_flag(self):
        """A stale flag must not override the dates."""
        Semester.objects.filter(pk=self.second.pk).update(is_active=True)
        self.assertEqual(
            Semester.resolve_for_date(datetime.date(2026, 9, 1)), self.first
        )


class UpdateActiveSemestersTests(TestCase):
    def setUp(self):
        self.year_a = make_year(2025, 2026)
        self.year_b = make_year(2026, 2027)
        self.a_first = make_semester(
            self.year_a, "1st", datetime.date(2025, 8, 1), datetime.date(2025, 12, 15)
        )
        self.a_second = make_semester(
            self.year_a, "2nd", datetime.date(2026, 1, 5), datetime.date(2026, 5, 15)
        )
        self.b_first = make_semester(
            self.year_b, "1st", datetime.date(2026, 8, 1), datetime.date(2026, 12, 15)
        )

    def active_ids(self):
        return set(Semester.objects.filter(is_active=True).values_list("pk", flat=True))

    def test_activates_exactly_one_semester_globally(self):
        """
        Previously one semester per academic year was activated, so finished
        academic years kept a semester flagged active forever.
        """
        Semester.objects.update(is_active=True)
        Semester.update_active_semesters(ref_date=datetime.date(2026, 9, 1))
        self.assertEqual(self.active_ids(), {self.b_first.pk})

    def test_returns_the_semester_it_activated(self):
        result = Semester.update_active_semesters(ref_date=datetime.date(2026, 9, 1))
        self.assertEqual(result, self.b_first)

    def test_clears_stale_flags_from_finished_academic_years(self):
        Semester.objects.filter(pk=self.a_first.pk).update(is_active=True)
        Semester.update_active_semesters(ref_date=datetime.date(2026, 9, 1))
        self.a_first.refresh_from_db()
        self.assertFalse(self.a_first.is_active)

    def test_is_idempotent(self):
        for _ in range(3):
            Semester.update_active_semesters(ref_date=datetime.date(2026, 9, 1))
        self.assertEqual(self.active_ids(), {self.b_first.pk})

    def test_never_leaves_zero_active_when_a_semester_has_started(self):
        Semester.update_active_semesters(ref_date=datetime.date(2026, 9, 1))
        self.assertEqual(len(self.active_ids()), 1)

    def test_deactivates_everything_when_nothing_has_started(self):
        Semester.objects.update(is_active=True)
        Semester.update_active_semesters(ref_date=datetime.date(2020, 1, 1))
        self.assertEqual(self.active_ids(), set())

    def test_transition_across_the_semester_boundary(self):
        Semester.update_active_semesters(ref_date=datetime.date(2025, 12, 15))
        self.assertEqual(self.active_ids(), {self.a_first.pk})

        Semester.update_active_semesters(ref_date=datetime.date(2026, 1, 5))
        self.assertEqual(self.active_ids(), {self.a_second.pk})

    def test_get_active_matches_the_synced_flag(self):
        Semester.update_active_semesters()
        active = Semester.get_active()
        self.assertEqual(self.active_ids(), {active.pk})


class GetActiveSelfHealTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.year = make_year(2026, 2027)
        self.semester = make_semester(
            self.year, "1st", datetime.date(2026, 1, 1), datetime.date(2030, 12, 31)
        )

    def test_repairs_a_stale_flag_on_read(self):
        """
        The nightly sync may not have run. Reading the active semester should
        converge the stored flag so admin pages that query is_active agree.
        """
        Semester.objects.update(is_active=False)
        active = Semester.get_active()
        self.assertEqual(active, self.semester)

        self.semester.refresh_from_db()
        self.assertTrue(self.semester.is_active)

    def test_does_not_crash_when_no_semester_resolves(self):
        Semester.objects.all().delete()
        self.assertIsNone(Semester.get_active())


class FacultySemesterViewTests(TestCase):
    """
    End-to-end checks that the faculty pages render, agree on the semester, and
    reject cross-faculty semester access.
    """

    def setUp(self):
        self.account = Account.objects.create_user(
            email="viewer@pup.edu.ph", password="test-pass-123", role="faculty"
        )
        self.faculty = FacultyProfile.objects.create(
            account=self.account, faculty_code="FV001", name="View Tester"
        )

        other_account = Account.objects.create_user(
            email="rival@pup.edu.ph", password="test-pass-123", role="faculty"
        )
        self.other_faculty = FacultyProfile.objects.create(
            account=other_account, faculty_code="FV002", name="Rival"
        )

        current_year = make_year(2026, 2027)
        past_year = make_year(2025, 2026)
        foreign_year = make_year(2024, 2025)

        self.current = make_semester(
            current_year, "1st", datetime.date(2026, 8, 1), datetime.date(2026, 12, 20),
            is_active=True,
        )
        self.past = make_semester(
            past_year, "1st", datetime.date(2025, 8, 1), datetime.date(2025, 12, 20)
        )
        self.foreign = make_semester(
            foreign_year, "1st", datetime.date(2024, 8, 1), datetime.date(2024, 12, 20)
        )

        self.current_assignment = self.make_assignment(self.faculty, self.current, "CS101")
        self.past_assignment = self.make_assignment(self.faculty, self.past, "CS100")
        self.foreign_assignment = self.make_assignment(
            self.other_faculty, self.foreign, "SECRET101"
        )

        self.client.force_login(self.account)

    def make_assignment(self, faculty, semester, subject_code):
        return TeachingAssignment.objects.create(
            faculty=faculty,
            subject_code=subject_code,
            subject_description="Course",
            year_section="BSCS 1-1",
            day_of_week="mon",
            start_time=datetime.time(8, 0),
            end_time=datetime.time(10, 0),
            semester=semester,
        )

    # --- Home ---

    def test_home_renders_and_shows_the_active_semester_label(self):
        response = self.client.get(reverse("faculty:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_semester"], self.current)
        self.assertContains(response, "2026–2027 • 1st Semester")

    def test_home_weekly_schedule_excludes_other_semesters(self):
        response = self.client.get(reverse("faculty:home"))
        codes = [ta.subject_code for ta in response.context["teaching_assignments"]]
        self.assertIn("CS101", codes)
        self.assertNotIn("CS100", codes)

    def test_home_shows_no_schedule_when_no_semester_has_started(self):
        """The old code fell through unfiltered and leaked every past assignment."""
        # The semester is now derived from dates, so push every one into the
        # future rather than clearing the (no longer authoritative) flag.
        Semester.objects.update(
            start_date=datetime.date(2099, 8, 1), end_date=datetime.date(2099, 12, 20)
        )
        response = self.client.get(reverse("faculty:home"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["active_semester"])
        self.assertEqual(list(response.context["teaching_assignments"]), [])

    # --- Teaching Assignment / DTR ---

    def test_dtr_defaults_to_active_semester(self):
        response = self.client.get(reverse("faculty:faculty_teaching_assignment"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_semester"], self.current)
        self.assertTrue(response.context["is_active_semester_view"])
        self.assertEqual(
            [a.subject_code for a in response.context["assignments"]], ["CS101"]
        )

    def test_dtr_can_view_a_historical_semester(self):
        response = self.client.get(
            reverse("faculty:faculty_teaching_assignment"), {"semester": self.past.id}
        )
        self.assertEqual(response.context["selected_semester"], self.past)
        self.assertFalse(response.context["is_active_semester_view"])
        self.assertEqual(
            [a.subject_code for a in response.context["assignments"]], ["CS100"]
        )

    def test_dtr_rejects_another_facultys_semester(self):
        response = self.client.get(
            reverse("faculty:faculty_teaching_assignment"), {"semester": self.foreign.id}
        )
        self.assertEqual(response.context["selected_semester"], self.current)
        self.assertNotContains(response, "SECRET101")

    def test_dtr_ignores_a_malformed_semester_parameter(self):
        response = self.client.get(
            reverse("faculty:faculty_teaching_assignment"), {"semester": "'; DROP--"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_semester"], self.current)

    def test_dtr_preserves_month_and_year_filters(self):
        response = self.client.get(
            reverse("faculty:faculty_teaching_assignment"),
            {"semester": self.past.id, "year": 2025, "month": 9},
        )
        self.assertEqual(response.context["year"], 2025)
        self.assertEqual(response.context["month"], 9)
        self.assertEqual(response.context["selected_semester"], self.past)

    # --- Classroom Management (deliverables) ---

    def test_deliverables_defaults_to_active_semester(self):
        response = self.client.get(reverse("faculty:faculty_deliverables"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["semester"], self.current)
        self.assertTrue(response.context["is_active_semester_view"])

    def test_deliverables_can_view_a_historical_semester(self):
        response = self.client.get(
            reverse("faculty:faculty_deliverables"), {"semester": self.past.id}
        )
        self.assertEqual(response.context["semester"], self.past)
        self.assertFalse(response.context["is_active_semester_view"])

    def test_clearance_cannot_be_requested_from_a_historical_view(self):
        response = self.client.get(
            reverse("faculty:faculty_deliverables"), {"semester": self.past.id}
        )
        self.assertFalse(response.context["can_request_clearance"])

    def test_deliverables_rejects_another_facultys_semester(self):
        response = self.client.get(
            reverse("faculty:faculty_deliverables"), {"semester": self.foreign.id}
        )
        self.assertEqual(response.context["semester"], self.current)

    # --- consistency across tabs ---

    def test_home_dtr_and_deliverables_agree_on_the_current_semester(self):
        home = self.client.get(reverse("faculty:home"))
        dtr = self.client.get(reverse("faculty:faculty_teaching_assignment"))
        deliverables = self.client.get(reverse("faculty:faculty_deliverables"))

        self.assertEqual(home.context["active_semester"], self.current)
        self.assertEqual(dtr.context["selected_semester"], self.current)
        self.assertEqual(deliverables.context["semester"], self.current)

    def test_ended_semester_in_a_gap_is_shown_consistently(self):
        """
        Between semesters the previous one stays current, and every tab must
        agree on it. Home previously showed nothing here while the others did.
        """
        # End the current semester yesterday with no later semester to take over.
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        Semester.objects.filter(pk=self.current.pk).update(end_date=yesterday)
        self.current.refresh_from_db()

        home = self.client.get(reverse("faculty:home"))
        dtr = self.client.get(reverse("faculty:faculty_teaching_assignment"))
        deliverables = self.client.get(reverse("faculty:faculty_deliverables"))

        self.assertEqual(home.context["active_semester"], self.current)
        self.assertEqual(dtr.context["selected_semester"], self.current)
        self.assertEqual(deliverables.context["semester"], self.current)

    def test_all_tabs_follow_the_transition_to_the_next_semester(self):
        """The reported bug, verified end to end across the three tabs."""
        today = timezone.localdate()
        # Current semester ended yesterday; a new one starts today.
        Semester.objects.filter(pk=self.current.pk).update(
            end_date=today - datetime.timedelta(days=1)
        )
        next_semester = make_semester(
            self.current.academic_year,
            "2nd",
            today,
            today + datetime.timedelta(days=120),
        )

        home = self.client.get(reverse("faculty:home"))
        dtr = self.client.get(reverse("faculty:faculty_teaching_assignment"))
        deliverables = self.client.get(reverse("faculty:faculty_deliverables"))

        self.assertEqual(home.context["active_semester"], next_semester)
        self.assertEqual(dtr.context["selected_semester"], next_semester)
        self.assertEqual(deliverables.context["semester"], next_semester)

    # --- clearance download authorization ---

    def test_clearance_download_requires_an_approved_record(self):
        response = self.client.get(
            reverse("faculty:faculty_download_clearance"), {"semester": self.current.id}
        )
        self.assertEqual(response.status_code, 404)

    def test_clearance_download_rejects_a_missing_semester_param(self):
        response = self.client.get(reverse("faculty:faculty_download_clearance"))
        self.assertEqual(response.status_code, 404)
