"""
Official work-hour totals for the DTR exports.

"Official Work Hours" is the total scheduled duration of the teaching assignments
the faculty actually attended. Attendance is decided by DTRCalculator's existing
status rules (45-minute late threshold, 30-minute early threshold), so nothing
here re-judges whether a class was attended - it only sums the schedule.
"""

from datetime import date, datetime, timedelta


# Statuses that credit no hours. Every other status DTRCalculator can emit
# ('on time', 'late', 'early in', 'overtime') means the faculty was present.
NON_ATTENDED_STATUSES = frozenset({"absent", "no assignment"})


def _assignment_duration(assignment):
    """Scheduled length of one teaching assignment as a timedelta."""
    start = getattr(assignment, "start_time", None)
    end = getattr(assignment, "end_time", None)
    if not start or not end:
        return timedelta()

    span = datetime.combine(date.min, end) - datetime.combine(date.min, start)
    # TeachingAssignment.clean() already rejects end <= start; guard anyway so a
    # bad row can never subtract from the month's total.
    return span if span > timedelta() else timedelta()


def format_duration(total):
    """Render a timedelta as the "8h 30m" form the DTR templates and PDF expect."""
    seconds = max(total.total_seconds(), 0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes:02d}m"


def calculate_official_work_hours(dtr_rows):
    """
    Total the scheduled hours of every teaching assignment that was attended.

    `dtr_rows` is the structure returned by DTRCalculator.get_dtr_for_month():
    a list of {'date': ..., 'statuses': [{'assignment', 'attendance_log',
    'status', 'is_manual'}, ...]} - one entry per day of the month.

    Days with no attendance, and days whose assignments are all 'absent',
    contribute nothing. Days with an attendance log but no scheduled assignment
    also contribute nothing: official hours are scheduled teaching hours.

    Computing from the assignment times (rather than from the formatted AM/PM
    strings the export grid displays) is deliberate. Those four slots cannot
    represent a single shift spanning noon, which is why the previous
    implementation reported 0h for a normal 08:00-17:00 day.
    """
    total = timedelta()

    for row in dtr_rows or []:
        counted_assignment_ids = set()

        for status in row.get("statuses", []):
            assignment = status.get("assignment")
            if assignment is None:
                continue
            if status.get("status") in NON_ATTENDED_STATUSES:
                continue

            # One credit per assignment per day, even if it appears in the
            # status list more than once.
            assignment_id = getattr(assignment, "pk", None) or id(assignment)
            if assignment_id in counted_assignment_ids:
                continue
            counted_assignment_ids.add(assignment_id)

            total += _assignment_duration(assignment)

    return format_duration(total)
