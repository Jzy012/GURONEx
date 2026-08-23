"""
Shared academic year / semester resolution for faculty-facing pages.

Every faculty surface (Home, Teaching Assignment/DTR, Classroom Management) must
agree on which semester is being displayed. `Semester.get_active()` is the single
source of truth for the *current* semester; the helpers below add the semester
picker and the server-side validation for the `?semester=` query parameter.
"""

from faculty.models import Semester, TeachingAssignment


SEMESTER_QUERY_PARAM = "semester"


def get_faculty_semesters(faculty):
    """
    Semesters this faculty is allowed to view, newest first.

    A semester qualifies if the faculty has at least one teaching assignment in
    it. The currently active semester is always included so the default view is
    selectable even before any assignment exists for it.

    This doubles as the authorization allow-list for `resolve_faculty_semester`:
    a faculty can never select a semester that is not in this list, so the query
    parameter cannot be used to probe unrelated calendar rows.
    """
    semester_ids = set(
        TeachingAssignment.objects
        .filter(faculty=faculty)
        .values_list("semester_id", flat=True)
    )

    active = Semester.get_active()
    if active:
        semester_ids.add(active.pk)

    if not semester_ids:
        return []

    return list(
        Semester.objects
        .select_related("academic_year")
        .filter(pk__in=semester_ids)
        .order_by("-academic_year__year_start", "-start_date", "-id")
    )


def resolve_faculty_semester(request, faculty):
    """
    Resolve the semester a faculty page should display.

    Reads `?semester=<id>` and validates it server-side against
    `get_faculty_semesters()`. Anything missing, malformed, or not belonging to
    this faculty silently falls back to the active semester, so a tampered URL
    degrades to the default view instead of leaking or erroring.

    Returns (semester, selectable_semesters, is_active_semester_view) where
    `semester` may be None when the system has no active semester and the
    faculty has no assignments at all.
    """
    selectable = get_faculty_semesters(faculty)
    active = Semester.get_active()

    requested_id = (request.GET.get(SEMESTER_QUERY_PARAM) or "").strip()
    semester = None

    if requested_id.isdigit():
        requested_pk = int(requested_id)
        semester = next((s for s in selectable if s.pk == requested_pk), None)

    if semester is None:
        semester = active

    # The active semester is not guaranteed to be in `selectable` only when it is
    # None, so fall back to the newest viewable semester in that case.
    if semester is None and selectable:
        semester = selectable[0]

    is_active_view = bool(semester and active and semester.pk == active.pk)

    return semester, selectable, is_active_view


def build_semester_querystring(request, semester_id, drop=("page",)):
    """
    Current query string with `semester` replaced and paging params dropped.

    Lets the semester picker preserve unrelated filters (e.g. the DTR's
    year/month/day) while switching semesters.
    """
    params = request.GET.copy()
    params[SEMESTER_QUERY_PARAM] = str(semester_id)
    for key in drop:
        params.pop(key, None)
    return params.urlencode()
