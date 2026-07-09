"""Unfold admin dashboard callback for the FEMS (PUP-GURONEx) system config.

Builds the KPI cards + recent-activity list shown on the Django admin index at
/system-config/. Referenced by ``UNFOLD["DASHBOARD_CALLBACK"]`` in settings.

Each KPI is computed defensively so one failing query (e.g. after a schema
change) never blanks the whole dashboard.
"""

from django.urls import reverse
from django.utils import timezone


def _safe(fn, default=0):
    try:
        return fn()
    except Exception:
        return default


def dashboard_callback(request, context):
    # Imported lazily so the app registry is ready when the callback runs.
    from base.models import Account
    from faculty.models import FacultyProfile, FacultyRequest, FacultyClearanceRequest
    from applicant.models import Applicant
    from rfid.models import AttendanceLog
    from notifications.models import ActivityLog

    today = timezone.localdate()

    def link(name):
        try:
            return reverse(name)
        except Exception:
            return None

    kpi_cards = [
        {
            "title": "Total Accounts",
            "value": _safe(lambda: Account.objects.count()),
            "icon": "group",
            "footer": "Faculty: %s"
            % _safe(lambda: Account.objects.filter(role="faculty").count()),
            "link": link("admin:base_account_changelist"),
        },
        {
            "title": "Faculty Profiles",
            "value": _safe(lambda: FacultyProfile.objects.count()),
            "icon": "school",
            "footer": "Registered faculty",
            "link": link("admin:faculty_facultyprofile_changelist"),
        },
        {
            "title": "Applicants",
            "value": _safe(lambda: Applicant.objects.count()),
            "icon": "how_to_reg",
            "footer": "All applicants",
            "link": link("admin:applicant_applicant_changelist"),
        },
        {
            "title": "Pending Faculty Requests",
            "value": _safe(lambda: FacultyRequest.objects.filter(status="Pending").count()),
            "icon": "assignment_late",
            "footer": "Awaiting action",
            "link": link("admin:faculty_facultyrequest_changelist"),
        },
        {
            "title": "Open Clearance Requests",
            "value": _safe(
                lambda: FacultyClearanceRequest.objects.filter(status="Requested").count()
            ),
            "icon": "verified",
            "footer": "Requested clearances",
            "link": link("admin:faculty_facultyclearancerequest_changelist"),
        },
        {
            "title": "Attendance Today",
            "value": _safe(lambda: AttendanceLog.objects.filter(date=today).count()),
            "icon": "schedule",
            "footer": today.strftime("%b %d, %Y"),
            "link": link("admin:rfid_attendancelog_changelist"),
        },
    ]

    recent_activity = _safe(
        lambda: list(ActivityLog.objects.order_by("-created_at")[:8]), default=[]
    )

    context.update(
        {
            "kpi_cards": kpi_cards,
            "recent_activity": recent_activity,
        }
    )
    return context
