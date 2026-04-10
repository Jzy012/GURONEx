from __future__ import annotations

import datetime
from typing import Any

from django.db import transaction

from faculty.models import Deliverable, DeliverableTemplate, Semester


def compute_semester_deadline(
    semester: Semester,
    override_deadline: datetime.date | None = None,
) -> datetime.date:
    """
    Semester-level deadline rule.

    If an override is provided (e.g., admin form), use it; otherwise use
    semester.end_date as the default semester-level deadline.
    """
    return override_deadline or semester.end_date


def get_previous_semester(target_semester: Semester) -> Semester | None:
    return (
        Semester.objects.filter(start_date__lt=target_semester.start_date)
        .order_by("-start_date", "-id")
        .first()
    )


def get_default_deliverable_template() -> DeliverableTemplate | None:
    return DeliverableTemplate.objects.filter(is_default=True).order_by("-id").first()


def _resolve_source_document_category_ids(
    semester: Semester,
) -> tuple[list[int], str, int | None]:
    previous_semester = get_previous_semester(semester)
    if previous_semester is not None:
        previous_ids = list(
            Deliverable.objects.filter(semester=previous_semester)
            .values_list("document_category_id", flat=True)
            .distinct()
        )
        if previous_ids:
            return previous_ids, "previous_semester", previous_semester.id

    default_template = get_default_deliverable_template()
    if default_template is not None:
        template_ids = list(
            default_template.document_categories.values_list("id", flat=True)
        )
        if template_ids:
            return template_ids, "default_template", default_template.id

    return [], "none", None


def auto_assign_deliverables_for_semester(
    semester_id: int,
    deadline: datetime.date | None = None,
) -> dict[str, Any]:
    try:
        semester = Semester.objects.get(pk=semester_id)
    except Semester.DoesNotExist:
        return {
            "ok": False,
            "reason": "missing_semester",
            "semester_id": semester_id,
            "created_count": 0,
            "skipped_count": 0,
        }

    category_ids, source_type, source_id = _resolve_source_document_category_ids(semester)
    if not category_ids:
        return {
            "ok": False,
            "reason": "no_source",
            "semester_id": semester.id,
            "created_count": 0,
            "skipped_count": 0,
            "source_type": source_type,
            "source_id": source_id,
        }

    applied_deadline = compute_semester_deadline(semester, deadline)

    existing_count_before = Deliverable.objects.filter(
        semester=semester,
        document_category_id__in=category_ids,
    ).count()

    existing_ids = set(
        Deliverable.objects.filter(
            semester=semester,
            document_category_id__in=category_ids,
        ).values_list("document_category_id", flat=True)
    )

    to_create = [
        Deliverable(
            semester=semester,
            document_category_id=category_id,
            deadline=applied_deadline,
        )
        for category_id in category_ids
        if category_id not in existing_ids
    ]

    if to_create:
        with transaction.atomic():
            Deliverable.objects.bulk_create(to_create, ignore_conflicts=True)

    existing_count_after = Deliverable.objects.filter(
        semester=semester,
        document_category_id__in=category_ids,
    ).count()
    created_count = max(existing_count_after - existing_count_before, 0)
    skipped_count = max(len(category_ids) - created_count, 0)

    return {
        "ok": True,
        "reason": "assigned",
        "semester_id": semester.id,
        "created_count": created_count,
        "skipped_count": skipped_count,
        "source_type": source_type,
        "source_id": source_id,
        "deadline": str(applied_deadline),
    }


def ensure_auto_assign_for_active_semesters(
    ref_date: datetime.date | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    active_semesters = Semester.objects.filter(is_active=True).order_by("id")

    for semester in active_semesters:
        results.append(auto_assign_deliverables_for_semester(semester.id))

    return {
        "checked": active_semesters.count(),
        "results": results,
        "ref_date": str(ref_date) if ref_date else None,
    }
