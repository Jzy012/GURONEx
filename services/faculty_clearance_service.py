import calendar
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from faculty.models import FacultyDocument


SEMESTER_CODE_MAP = {
    "1st": "1ST",
    "2nd": "2ND",
    "summer": "SUMMER",
    "full": "FULL",
}


def build_clearance_number(faculty, semester):
    if semester and semester.academic_year_id:
        academic_year_label = f"{semester.academic_year.year_start}-{semester.academic_year.year_end}(Academic Year)"
    else:
        current_year = timezone.localdate().year
        academic_year_label = f"{current_year}-{current_year + 1}(Academic Year)"

    sem_code = SEMESTER_CODE_MAP.get(semester.semester_type, semester.semester_type.upper())
    if faculty.last_name:
        last_name = faculty.last_name.strip().replace(" ", "-")
    elif faculty.name:
        last_name = faculty.name.strip().split()[-1].replace(" ", "-")
    else:
        last_name = f"FACULTY-{faculty.pk}"

    return f"CLR-{academic_year_label}-{sem_code}-{last_name}"


def evaluate_faculty_clearance_eligibility(faculty, semester):
    today = timezone.localdate()

    assignments = list(
        faculty.teachingassignment_set.filter(semester=semester).order_by("day_of_week", "start_time")
    )
    deliverables = list(
        semester.deliverables.select_related("document_category").order_by("document_category__name")
    )

    if not assignments:
        return {
            "is_eligible": False,
            "has_assignments": False,
            "has_deliverables": bool(deliverables),
            "total_required": 0,
            "approved_slots": 0,
            "pending_slots": 0,
            "rejected_slots": 0,
            "missing_slots": 0,
            "overdue_slots": 0,
            "blocking_reasons": ["No teaching assignments found for the selected semester."],
        }

    if not deliverables:
        return {
            "is_eligible": False,
            "has_assignments": True,
            "has_deliverables": False,
            "total_required": 0,
            "approved_slots": 0,
            "pending_slots": 0,
            "rejected_slots": 0,
            "missing_slots": 0,
            "overdue_slots": 0,
            "blocking_reasons": ["No deliverables are configured for the selected semester."],
        }

    docs_qs = FacultyDocument.objects.filter(
        faculty=faculty,
        semester=semester,
        teaching_assignment__in=assignments,
        deliverable__in=deliverables,
        is_archived=False,
    ).select_related("deliverable", "teaching_assignment")

    latest_by_slot = {}
    for doc in docs_qs.order_by("-uploaded_at"):
        key = (doc.teaching_assignment_id, doc.deliverable_id)
        if key not in latest_by_slot:
            latest_by_slot[key] = doc

    approved_slots = 0
    pending_slots = 0
    rejected_slots = 0
    missing_slots = 0
    overdue_slots = 0

    for assignment in assignments:
        for deliverable in deliverables:
            key = (assignment.id, deliverable.id)
            latest_doc = latest_by_slot.get(key)

            if latest_doc is None:
                missing_slots += 1
                if today > deliverable.deadline:
                    overdue_slots += 1
                continue

            if latest_doc.status == "Approved":
                approved_slots += 1
            elif latest_doc.status == "Pending":
                pending_slots += 1
                if today > deliverable.deadline:
                    overdue_slots += 1
            elif latest_doc.status == "Rejected":
                rejected_slots += 1
                if today > deliverable.deadline:
                    overdue_slots += 1
            else:
                pending_slots += 1
                if today > deliverable.deadline:
                    overdue_slots += 1

    total_required = len(assignments) * len(deliverables)

    blocking_reasons = []
    if missing_slots > 0:
        blocking_reasons.append(f"{missing_slots} required deliverable slot(s) are missing uploads.")
    if pending_slots > 0:
        blocking_reasons.append(f"{pending_slots} deliverable slot(s) are still pending admin review.")
    if rejected_slots > 0:
        blocking_reasons.append(f"{rejected_slots} deliverable slot(s) were rejected and must be re-uploaded.")
    if overdue_slots > 0:
        blocking_reasons.append(f"{overdue_slots} deliverable slot(s) are overdue and not approved.")

    return {
        "is_eligible": total_required > 0 and approved_slots == total_required,
        "has_assignments": True,
        "has_deliverables": True,
        "total_required": total_required,
        "approved_slots": approved_slots,
        "pending_slots": pending_slots,
        "rejected_slots": rejected_slots,
        "missing_slots": missing_slots,
        "overdue_slots": overdue_slots,
        "blocking_reasons": blocking_reasons,
    }


def build_clearance_pdf_response(clearance_request):
    faculty = clearance_request.faculty
    semester = clearance_request.semester

    month_name = calendar.month_name[timezone.localdate().month]
    generated_on = timezone.localtime().strftime("%b %d, %Y %I:%M %p")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2.2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "clearance_title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        alignment=1,
        textColor=colors.HexColor("#800505"),
        spaceAfter=12,
    )
    body_style = ParagraphStyle(
        "clearance_body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=17,
        alignment=0,
        textColor=colors.HexColor("#111827"),
    )
    centered_style = ParagraphStyle(
        "clearance_centered",
        parent=body_style,
        alignment=1,
        fontName="Helvetica-Bold",
    )

    details = [
        ["Faculty Name", faculty.name or faculty.account.email],
        ["Faculty Code", faculty.faculty_code or "N/A"],
        ["Academic Year", str(semester.academic_year)],
        ["Semester", semester.get_semester_type_display()],
        ["Clearance Number", clearance_request.clearance_number],
        ["Requested On", timezone.localtime(clearance_request.requested_at).strftime("%b %d, %Y %I:%M %p")],
    ]

    details_table = Table(details, colWidths=[4.1 * cm, 10.9 * cm])
    details_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story = [
        Paragraph("Certificate of Completion", title_style),
        Paragraph("This certifies that", centered_style),
        Spacer(1, 8),
        Paragraph(faculty.name or faculty.account.email, ParagraphStyle(
            "faculty_name",
            parent=centered_style,
            fontSize=17,
            textColor=colors.HexColor("#111827"),
        )),
        Spacer(1, 10),
        Paragraph(
            (
                "has completed and obtained approval for all required semester deliverables "
                "for the selected academic period."
            ),
            centered_style,
        ),
        Spacer(1, 20),
        details_table,
        Spacer(1, 20),
        Paragraph(
            f"Issued this {month_name} on {generated_on}.",
            body_style,
        ),
        Spacer(1, 24),
        Paragraph("______________________________", centered_style),
        Paragraph("Authorized by System Validation", centered_style),
    ]

    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()

    filename = f"{clearance_request.clearance_number}.pdf"
    response = HttpResponse(pdf_data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
