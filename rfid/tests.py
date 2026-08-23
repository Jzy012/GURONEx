import datetime
import io
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from adminhub.models import AttendanceFeatureSetting
from base.forms import ManualAttendanceLogForm, get_current_week_range
from base.models import Account
from faculty.models import AcademicYear, FacultyProfile, Semester, TeachingAssignment
from rfid.models import AttendanceLog


def make_faculty(email="week@pup.edu.ph", code="FW001"):
    account = Account.objects.create_user(
        email=email, password="test-pass-123", role="faculty"
    )
    return FacultyProfile.objects.create(
        account=account, faculty_code=code, name="Week Tester"
    )


def make_png(name="proof.png", size_bytes=None):
    """A minimal valid PNG so ImageField's Pillow verification passes."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buffer, format="PNG")
    content = buffer.getvalue()
    if size_bytes:
        content = content + b"\0" * (size_bytes - len(content))
    return SimpleUploadedFile(name, content, content_type="image/png")


class CurrentWeekRangeTests(TestCase):
    def test_range_starts_on_monday_and_ends_today(self):
        wednesday = datetime.date(2026, 8, 12)  # a Wednesday
        start, end = get_current_week_range(wednesday)
        self.assertEqual(start, datetime.date(2026, 8, 10))  # Monday
        self.assertEqual(end, wednesday)

    def test_monday_range_is_a_single_day(self):
        monday = datetime.date(2026, 8, 10)
        start, end = get_current_week_range(monday)
        self.assertEqual(start, monday)
        self.assertEqual(end, monday)

    def test_sunday_is_treated_as_the_last_day_of_its_week(self):
        sunday = datetime.date(2026, 8, 16)
        start, end = get_current_week_range(sunday)
        self.assertEqual(start, datetime.date(2026, 8, 10))
        self.assertEqual(end, sunday)


class ManualAttendanceFormTests(TestCase):
    def setUp(self):
        self.faculty = make_faculty()
        self.today = timezone.localdate()
        self.week_start, self.week_end = get_current_week_range(self.today)

    def build(self, **overrides):
        data = {
            "faculty": str(self.faculty.pk),
            "date": self.today.isoformat(),
            "time_in": "08:00",
            "time_out": "10:00",
            "manual_reason": AttendanceLog.REASON_RFID_OFFLINE,
        }
        files = overrides.pop("files", None)
        data.update(overrides)
        return ManualAttendanceLogForm(
            data, files, faculty=self.faculty, restrict_to_current_week=True
        )

    # --- date window ---

    def test_today_is_accepted(self):
        self.assertTrue(self.build().is_valid())

    def test_monday_of_current_week_is_accepted(self):
        form = self.build(date=self.week_start.isoformat())
        self.assertTrue(form.is_valid(), form.errors)

    def test_previous_week_is_rejected(self):
        form = self.build(date=(self.week_start - datetime.timedelta(days=1)).isoformat())
        self.assertFalse(form.is_valid())
        self.assertIn("date", form.errors)

    def test_future_date_is_rejected(self):
        form = self.build(date=(self.today + datetime.timedelta(days=1)).isoformat())
        self.assertFalse(form.is_valid())
        self.assertIn("date", form.errors)

    def test_admin_path_is_not_restricted_to_the_current_week(self):
        """The shared form must keep the admin's unrestricted date range."""
        form = ManualAttendanceLogForm(
            {
                "faculty": str(self.faculty.pk),
                "date": (self.today - datetime.timedelta(days=90)).isoformat(),
                "time_in": "08:00",
                "time_out": "10:00",
            },
            faculty=self.faculty,
        )
        self.assertTrue(form.is_valid(), form.errors)

    # --- reason ---

    def test_missing_reason_is_rejected_for_faculty(self):
        form = self.build(manual_reason="")
        self.assertFalse(form.is_valid())
        self.assertIn("manual_reason", form.errors)

    def test_other_reason_requires_details(self):
        form = self.build(manual_reason=AttendanceLog.REASON_OTHER)
        self.assertFalse(form.is_valid())
        self.assertIn("manual_reason_details", form.errors)

    def test_other_reason_with_details_is_accepted(self):
        form = self.build(
            manual_reason=AttendanceLog.REASON_OTHER,
            manual_reason_details="Power outage on campus.",
        )
        self.assertTrue(form.is_valid(), form.errors)

    # --- online class documentation ---

    def test_online_class_without_photo_is_rejected(self):
        form = self.build(manual_reason=AttendanceLog.REASON_ONLINE_CLASS)
        self.assertFalse(form.is_valid())
        self.assertIn("documentation", form.errors)

    def test_online_class_with_photo_is_accepted(self):
        form = self.build(
            manual_reason=AttendanceLog.REASON_ONLINE_CLASS,
            files={"documentation": make_png()},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_reasons_do_not_require_a_photo(self):
        form = self.build(manual_reason=AttendanceLog.REASON_NETWORK_ISSUE)
        self.assertTrue(form.is_valid(), form.errors)

    # --- file validation ---

    def test_oversized_photo_is_rejected(self):
        oversized = make_png(size_bytes=6 * 1024 * 1024)
        form = self.build(
            manual_reason=AttendanceLog.REASON_ONLINE_CLASS,
            files={"documentation": oversized},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("documentation", form.errors)

    def test_non_image_file_is_rejected(self):
        bogus = SimpleUploadedFile(
            "notes.pdf", b"%PDF-1.4 not really an image", content_type="application/pdf"
        )
        form = self.build(
            manual_reason=AttendanceLog.REASON_ONLINE_CLASS,
            files={"documentation": bogus},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("documentation", form.errors)

    def test_disallowed_extension_is_rejected(self):
        """A real image with an extension outside the allow-list."""
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), color="blue").save(buffer, format="GIF")
        gif = SimpleUploadedFile("proof.gif", buffer.getvalue(), content_type="image/gif")
        form = self.build(
            manual_reason=AttendanceLog.REASON_ONLINE_CLASS,
            files={"documentation": gif},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("documentation", form.errors)

    # --- duplicates ---

    def test_duplicate_log_for_the_same_date_is_rejected(self):
        AttendanceLog.objects.create(faculty=self.faculty, date=self.today)
        form = self.build()
        self.assertFalse(form.is_valid())

    # --- weekly rate limit ---

    def _fill_week(self, count):
        """Create `count` manual logs on distinct earlier days of this week."""
        made = 0
        offset = 1
        while made < count:
            day = self.today - datetime.timedelta(days=offset)
            offset += 1
            if day < self.week_start:
                break
            AttendanceLog.objects.create(faculty=self.faculty, date=day, is_manual=True)
            made += 1
        return made

    def test_weekly_cap_blocks_further_manual_logs(self):
        from base.forms import MAX_MANUAL_LOGS_PER_WEEK

        created = self._fill_week(MAX_MANUAL_LOGS_PER_WEEK)
        if created < MAX_MANUAL_LOGS_PER_WEEK:
            self.skipTest("Not enough elapsed days this week to reach the cap.")
        form = self.build()
        self.assertFalse(form.is_valid())
        self.assertIn("limit", str(form.errors).lower())

    def test_under_the_weekly_cap_is_still_allowed(self):
        from base.forms import MAX_MANUAL_LOGS_PER_WEEK

        created = self._fill_week(MAX_MANUAL_LOGS_PER_WEEK - 1)
        if created < MAX_MANUAL_LOGS_PER_WEEK - 1:
            self.skipTest("Not enough elapsed days this week for this scenario.")
        form = self.build()
        self.assertTrue(form.is_valid(), form.errors)

    def test_rfid_logs_do_not_count_toward_the_manual_cap(self):
        from base.forms import MAX_MANUAL_LOGS_PER_WEEK

        made = 0
        offset = 1
        while made < MAX_MANUAL_LOGS_PER_WEEK:
            day = self.today - datetime.timedelta(days=offset)
            offset += 1
            if day < self.week_start:
                break
            # is_manual defaults to False -> an RFID tap
            AttendanceLog.objects.create(faculty=self.faculty, date=day)
            made += 1
        form = self.build()
        self.assertTrue(form.is_valid(), form.errors)

    def test_admin_path_is_not_rate_limited(self):
        self._fill_week(5)
        form = ManualAttendanceLogForm(
            {
                "faculty": str(self.faculty.pk),
                "date": self.today.isoformat(),
                "time_in": "08:00",
                "time_out": "10:00",
            },
            faculty=self.faculty,
        )
        self.assertTrue(form.is_valid(), form.errors)

    # --- assignment time coupling (existing rule must survive) ---

    def test_times_must_match_selected_assignments(self):
        year = AcademicYear.objects.create(year_start=2026, year_end=2027)
        semester = Semester.objects.create(
            academic_year=year,
            semester_type="1st",
            start_date=datetime.date(2026, 8, 1),
            end_date=datetime.date(2026, 12, 20),
        )
        assignment = TeachingAssignment.objects.create(
            faculty=self.faculty,
            subject_code="CS101",
            subject_description="Intro",
            year_section="BSCS 1-1",
            day_of_week="mon",
            start_time=datetime.time(8, 0),
            end_time=datetime.time(10, 0),
            semester=semester,
        )
        form = self.build(
            teaching_assignments=[str(assignment.pk)],
            time_in="09:00",
            time_out="11:00",
        )
        self.assertFalse(form.is_valid())


class ManualAttendanceViewTests(TestCase):
    def setUp(self):
        self.faculty = make_faculty("page@pup.edu.ph", "FP001")
        self.today = timezone.localdate()
        self.week_start, self.week_end = get_current_week_range(self.today)

        settings_row = AttendanceFeatureSetting.get_solo()
        settings_row.enable_faculty_manual_attendance = True
        settings_row.save()

        self.client.force_login(self.faculty.account)
        self.url = reverse("faculty:faculty_manual_attendance_log")

    def test_page_renders_with_the_current_week_range(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["week_start"], self.week_start)
        self.assertEqual(response.context["week_end"], self.week_end)
        self.assertContains(response, f'min="{self.week_start.isoformat()}"')
        self.assertContains(response, f'max="{self.week_end.isoformat()}"')

    def test_page_renders_every_reason_choice(self):
        response = self.client.get(self.url)
        for value, label in AttendanceLog.MANUAL_REASON_CHOICES:
            self.assertContains(response, f'value="{value}"')
            self.assertContains(response, label)

    def test_form_accepts_multipart_uploads(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_reason_metadata_is_emitted_as_json_script(self):
        """
        The reason sets must reach Alpine via json_script, never interpolated
        into an attribute. See test_no_x_data_attribute_contains_raw_json.
        """
        response = self.client.get(self.url)
        html = response.content.decode()
        for element_id in (
            "reasons-needing-photo",
            "reasons-needing-details",
            "reason-labels",
            "selected-reason",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("online_class", html)

    def test_no_django_template_comment_leaks_into_the_page(self):
        """
        Django's lexer compiles its tag regex without re.DOTALL, so a {# #}
        comment spanning multiple lines is never tokenized as a comment and
        renders to the page as visible text. Multi-line notes must use the
        comment block tag instead.
        """
        html = self.client.get(self.url).content.decode()
        self.assertNotIn("{#", html)
        self.assertNotIn("#}", html)
        self.assertNotIn("{% comment %}", html)
        self.assertNotIn("{% endcomment %}", html)

    def test_photo_upload_field_is_present_and_labelled(self):
        html = self.client.get(self.url).content.decode()

        # The real input keeps its name, type filter and label association.
        self.assertIn('name="documentation"', html)
        self.assertIn('id="documentation"', html)
        self.assertIn('accept="image/jpeg,image/png,image/webp"', html)
        self.assertIn('for="documentation"', html)
        self.assertIn('id="documentation-label"', html)
        self.assertIn('id="documentation-help"', html)

        # And the redesigned affordance communicates purpose and limits.
        self.assertIn("Upload Photo Documentation", html)
        self.assertIn("Required for Online Class", html)
        self.assertIn("maximum 5MB", html)

    def test_photo_field_error_is_rendered_inline_after_a_failed_post(self):
        response = self.client.post(
            self.url,
            {
                "date": self.today.isoformat(),
                "time_in": "08:00",
                "time_out": "10:00",
                "manual_reason": AttendanceLog.REASON_ONLINE_CLASS,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["documentation_error"])
        self.assertTrue(response.context["documentation_has_error"])

        html = response.content.decode()
        self.assertIn('id="documentation-error"', html)
        self.assertIn('role="alert"', html)

    def test_no_x_data_attribute_contains_raw_json(self):
        """
        Regression guard. A json.dumps value was once interpolated into the
        double-quoted x-data attribute; its own double quotes closed the
        attribute early, broke the whole Alpine component, and the Online Class
        photo field never appeared. Server-rendered content assertions all
        still passed, so this checks the attribute itself.
        """
        html = self.client.get(self.url).content.decode()

        # Every x-data="..." value must parse as a complete attribute, i.e.
        # contain no double quote of its own.
        attributes = re.findall(r'x-data="([^"]*)"', html)
        self.assertTrue(attributes, "expected at least one x-data attribute")

        for value in attributes:
            self.assertNotIn("[", value, f"raw JSON leaked into x-data: {value!r}")
            self.assertNotIn("{", value, f"inline object in x-data: {value!r}")

        # And the component the photo toggle depends on must be referenced.
        self.assertIn("manualAttendanceForm()", attributes)

    def test_backend_rejects_a_previous_week_date_even_if_the_ui_is_bypassed(self):
        stale = self.week_start - datetime.timedelta(days=3)
        response = self.client.post(
            self.url,
            {
                "date": stale.isoformat(),
                "time_in": "08:00",
                "time_out": "10:00",
                "manual_reason": AttendanceLog.REASON_RFID_OFFLINE,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AttendanceLog.objects.filter(date=stale).exists())

    def test_backend_rejects_online_class_without_a_photo(self):
        response = self.client.post(
            self.url,
            {
                "date": self.today.isoformat(),
                "time_in": "08:00",
                "time_out": "10:00",
                "manual_reason": AttendanceLog.REASON_ONLINE_CLASS,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AttendanceLog.objects.exists())

    def test_successful_submission_saves_and_writes_an_activity_log(self):
        from notifications.models import ActivityLog

        response = self.client.post(
            self.url,
            {
                "date": self.today.isoformat(),
                "time_in": "08:00",
                "time_out": "10:00",
                "manual_reason": AttendanceLog.REASON_RFID_OFFLINE,
            },
        )
        self.assertEqual(response.status_code, 302)

        log = AttendanceLog.objects.get()
        self.assertTrue(log.is_manual)
        self.assertEqual(log.manual_reason, AttendanceLog.REASON_RFID_OFFLINE)
        self.assertFalse(log.has_documentation)

        activity = ActivityLog.objects.get(action="faculty_manual_attendance_logged")
        self.assertEqual(activity.actor, self.faculty.account)
        self.assertEqual(activity.details["attendance_date"], self.today.isoformat())
        self.assertEqual(activity.details["reason"], "RFID Reader Offline / Malfunction")
        self.assertFalse(activity.details["documentation_submitted"])
        self.assertEqual(activity.details["target_name"], self.faculty.name)

    def test_faculty_cannot_log_attendance_for_another_faculty(self):
        victim = make_faculty("victim@pup.edu.ph", "FP002")
        self.client.post(
            self.url,
            {
                "faculty": str(victim.pk),
                "date": self.today.isoformat(),
                "time_in": "08:00",
                "time_out": "10:00",
                "manual_reason": AttendanceLog.REASON_RFID_OFFLINE,
            },
        )
        self.assertFalse(AttendanceLog.objects.filter(faculty=victim).exists())
        self.assertTrue(AttendanceLog.objects.filter(faculty=self.faculty).exists())

    def test_duplicate_submission_for_the_same_day_is_rejected(self):
        payload = {
            "date": self.today.isoformat(),
            "time_in": "08:00",
            "time_out": "10:00",
            "manual_reason": AttendanceLog.REASON_RFID_OFFLINE,
        }
        self.client.post(self.url, payload)
        self.client.post(self.url, payload)
        self.assertEqual(AttendanceLog.objects.count(), 1)

    def test_feature_flag_off_blocks_the_page(self):
        settings_row = AttendanceFeatureSetting.get_solo()
        settings_row.enable_faculty_manual_attendance = False
        settings_row.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
