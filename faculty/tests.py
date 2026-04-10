import datetime

from django.test import TestCase

from faculty.models import AcademicYear, Deliverable, DeliverableTemplate, DocumentCategory, Semester
from services.deliverable_assignment_service import auto_assign_deliverables_for_semester


class DeliverableAutoAssignServiceTests(TestCase):
	def _create_year(self, start_year=2025, end_year=2026):
		return AcademicYear.objects.create(year_start=start_year, year_end=end_year)

	def _create_semester(self, year, sem_type, start_date, end_date):
		return Semester.objects.create(
			academic_year=year,
			semester_type=sem_type,
			start_date=start_date,
			end_date=end_date,
		)

	def test_auto_assign_from_previous_semester_and_idempotent(self):
		year = self._create_year()
		cat_a = DocumentCategory.objects.create(name="Syllabus")
		cat_b = DocumentCategory.objects.create(name="Class Record")

		previous_semester = self._create_semester(
			year,
			"1st",
			datetime.date(2025, 8, 1),
			datetime.date(2025, 12, 31),
		)
		target_semester = self._create_semester(
			year,
			"2nd",
			datetime.date(2026, 1, 10),
			datetime.date(2026, 5, 31),
		)

		Deliverable.objects.create(
			semester=previous_semester,
			document_category=cat_a,
			deadline=datetime.date(2025, 11, 30),
		)
		Deliverable.objects.create(
			semester=previous_semester,
			document_category=cat_b,
			deadline=datetime.date(2025, 11, 30),
		)

		first_result = auto_assign_deliverables_for_semester(target_semester.id)
		self.assertTrue(first_result["ok"])
		self.assertEqual(first_result["source_type"], "previous_semester")
		self.assertEqual(first_result["created_count"], 2)

		target_deliverables = Deliverable.objects.filter(semester=target_semester)
		self.assertEqual(target_deliverables.count(), 2)
		self.assertTrue(all(d.deadline == target_semester.end_date for d in target_deliverables))

		second_result = auto_assign_deliverables_for_semester(target_semester.id)
		self.assertTrue(second_result["ok"])
		self.assertEqual(second_result["created_count"], 0)

	def test_auto_assign_falls_back_to_default_template(self):
		year = self._create_year(2027, 2028)
		cat_a = DocumentCategory.objects.create(name="Course Plan")
		cat_b = DocumentCategory.objects.create(name="Classroom Rules")

		template = DeliverableTemplate.objects.create(name="Default Faculty Template", is_default=True)
		template.document_categories.add(cat_a, cat_b)

		target_semester = self._create_semester(
			year,
			"1st",
			datetime.date(2027, 8, 1),
			datetime.date(2027, 12, 15),
		)

		result = auto_assign_deliverables_for_semester(target_semester.id)
		self.assertTrue(result["ok"])
		self.assertEqual(result["source_type"], "default_template")
		self.assertEqual(result["created_count"], 2)

	def test_auto_assign_returns_error_when_no_source_exists(self):
		year = self._create_year(2029, 2030)
		target_semester = self._create_semester(
			year,
			"1st",
			datetime.date(2029, 8, 1),
			datetime.date(2029, 12, 10),
		)

		result = auto_assign_deliverables_for_semester(target_semester.id)
		self.assertFalse(result["ok"])
		self.assertEqual(result["reason"], "no_source")

	def test_setting_new_default_template_unsets_previous_default(self):
		first = DeliverableTemplate.objects.create(name="Template A", is_default=True)
		second = DeliverableTemplate.objects.create(name="Template B", is_default=True)

		first.refresh_from_db()
		second.refresh_from_db()

		self.assertFalse(first.is_default)
		self.assertTrue(second.is_default)
