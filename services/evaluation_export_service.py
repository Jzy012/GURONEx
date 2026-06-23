"""
Evaluation PDF export service.
"""
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from reportlab.platypus.flowables import Flowable


def _evaluator_position(ea) -> str:
    """Return designation for an EvaluationAssignment evaluator, or empty string."""
    acc = ea.evaluator
    role = getattr(acc, 'role', None)
    try:
        if role == 'faculty':
            return (acc.faculty_profile.designation or '').strip()
        if role in ('admin', 'system_admin'):
            return (acc.admin_profile.designation or '').strip()
    except Exception:
        pass
    return ''


def build_evaluation_pdf_response(applicant):
    submitted_assignments = list(
        applicant.evaluation_assignments
        .filter(is_submitted=True)
        .select_related('evaluator', 'submission')
        .prefetch_related('submission__scores__criteria')
        .order_by('assigned_at')
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.8 * cm,
        bottomMargin=2.0 * cm,
    )
    avail = A4[0] - doc.leftMargin - doc.rightMargin

    styles = getSampleStyleSheet()

    def _style(name, **kw):
        base = kw.pop('parent', styles['Normal'])
        return ParagraphStyle(name, parent=base, **kw)

    header_center_s = _style('ev_hdr', fontName='Helvetica', fontSize=8,
                              alignment=1, leading=12, textColor=colors.HexColor('#111827'))
    header_bold_s = _style('ev_hdrbold', fontName='Helvetica-Bold', fontSize=9,
                            alignment=1, textColor=colors.HexColor('#111827'))
    doc_title_s = _style('ev_doctitle', fontName='Helvetica-Bold', fontSize=11,
                          alignment=1, textColor=colors.HexColor('#111827'),
                          spaceBefore=8, spaceAfter=4)
    section_s = _style('ev_sec', fontName='Helvetica-Bold', fontSize=10,
                        textColor=colors.HexColor('#111827'), spaceBefore=8, spaceAfter=3)
    ev_name_s = _style('ev_evname', fontName='Helvetica-Bold', fontSize=10,
                        textColor=colors.HexColor("#000000"), spaceBefore=6, spaceAfter=2)
    body_s = _style('ev_body', fontName='Helvetica', fontSize=9, leading=13)
    label_s = _style('ev_lbl', fontName='Helvetica-Bold', fontSize=9)
    small_s = _style('ev_sm', fontName='Helvetica', fontSize=8, leading=11,
                     textColor=colors.HexColor('#4B5563'))
    panel_s = _style('ev_panel', fontName='Helvetica', fontSize=9, alignment=1, leading=13)
    footer_s = _style('ev_foot', fontName='Helvetica', fontSize=7.5,
                      alignment=1, textColor=colors.HexColor('#374151'), leading=10)
    footer_bold_s = _style('ev_footbold', fontName='Helvetica-Bold', fontSize=8,
                            alignment=1, textColor=colors.HexColor('#111827'))

    story = []

    # ── HEADER (content blanked; spacing preserved) ───────────────────────────
    pup = Spacer(2.0 * cm, 2.0 * cm)
    bp = Spacer(2.0 * cm, 2.0 * cm)

    center_lines = [
        Paragraph('', header_center_s),
        Paragraph('', header_bold_s),
        Paragraph('', header_center_s),
    ]

    logo_col = avail * 0.15
    text_col = avail * 0.70
    hdr_table = Table(
        [[pup, center_lines, bp]],
        colWidths=[logo_col, text_col, logo_col],
    )
    hdr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'CENTER'),
    ]))
    story.append(hdr_table)
    story.append(HRFlowable(width=avail, thickness=1, color=colors.HexColor("#6B7280"), spaceAfter=6))
    story.append(Paragraph('FACULTY APPLICANT INTERVIEW FORM', doc_title_s))
    story.append(Spacer(1, 7))  # replaces HRFlowable (1pt thickness + 6pt spaceAfter)
    story.append(Paragraph('', doc_title_s))
    story.append(Spacer(1, 4))

    # ── APPLICANT INFO ─────────────────────────────────────────────────────────
    date_str = '—'
    if applicant.evaluation_date:
        date_str = applicant.evaluation_date.strftime('%B %d, %Y')
    elif submitted_assignments:
        first_sub = submitted_assignments[0]
        if first_sub.submission and first_sub.submission.submitted_at:
            date_str = timezone.localtime(first_sub.submission.submitted_at).strftime('%B %d, %Y')

    info_data = [[
        Paragraph("Applicant's\nName:", label_s),
        Paragraph(applicant.full_name, body_s),
        Paragraph('Date of\nInterview:', label_s),
        Paragraph(date_str, body_s),
    ]]
    c1, c3 = 2.2 * cm, 2.2 * cm
    c2 = (avail - c1 - c3) / 2
    c4 = avail - c1 - c2 - c3
    info_table = Table(info_data, colWidths=[c1, c2, c3, c4])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#000000')),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#F9FAFB')),
        ('BACKGROUND', (2, 0), (2, 0), colors.HexColor('#F9FAFB')),
    ]))
    story.append(info_table)

    # ── SECTION I: QUALIFICATIONS ──────────────────────────────────────────────
    story.append(Paragraph('I. Qualifications', section_s))

    def _qual_row(label, value):
        return [Paragraph(label + ':', label_s), Paragraph(value or '', body_s)]

    qual_data = [
        _qual_row('College Degree', applicant.college_degree),
        _qual_row('Educational Institution', applicant.college_institution),
        _qual_row("Master's Degree", applicant.masters_degree),
        _qual_row('Educational Institution', applicant.masters_institution),
        _qual_row("Doctorate's Degree", applicant.doctorate_degree),
        _qual_row('Educational Institution', applicant.doctorate_institution),
        _qual_row('Eligibility', ''),
        _qual_row('Current Employment', ''),
    ]
    lw = avail * 0.32
    qual_table = Table(qual_data, colWidths=[lw, avail - lw])
    qual_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#000000')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F9FAFB')),
    ]))
    story.append(qual_table)

    # ── PER-EVALUATOR SECTIONS ─────────────────────────────────────────────────
    multiple = len(submitted_assignments) > 1

    for i, ea in enumerate(submitted_assignments):
        submission = ea.submission

        # Divider between evaluators (not before the first)
        if i > 0:
            story.append(Spacer(1, 12))
            story.append(HRFlowable(
                width=avail, thickness=0.8,
                color=colors.HexColor('#6B7280'),
                lineCap='round',
                spaceAfter=8,
            ))

        # Evaluator heading (only when multiple evaluators)
        if multiple:
            story.append(Spacer(1, 12))

            story.append(Paragraph(
                f'Evaluator {i + 1} - {ea.evaluator_display_name}',
                ev_name_s,
            ))
            
            story.append(Spacer(1, 6))

        # Section II: Evaluation Criteria
        story.append(Paragraph('II. Evaluation Criteria', section_s))
        story.append(Paragraph(
            'Please rate the applicant in each category based on the scale below:',
            small_s,
        ))
        story.append(Paragraph(
            '5 – Excellent | 4 – Very Good | 3 – Satisfactory | 2 – Needs Improvement | 1 – Poor',
            small_s,
        ))
        story.append(Spacer(1, 4))

        scores = list(submission.scores.all()) if submission else []

        criteria_data = [[
            Paragraph('<b>Criteria</b>', label_s),
            Paragraph('<b>Rating</b>', label_s),
            Paragraph('<b>Comments</b>', label_s),
        ]]
        if scores:
            for score in scores:
                criteria_data.append([
                    Paragraph(score.criteria.label, body_s),
                    Paragraph(str(score.rating), body_s),
                    Paragraph(score.comments or '', body_s),
                ])
            criteria_data.append([
                Paragraph('<b>Overall Score</b>', label_s),
                Paragraph(f'<b>{submission.total_score} / {submission.max_score}</b>', label_s),
                Paragraph('', body_s),
            ])
        else:
            for _ in range(7):
                criteria_data.append([Paragraph('', body_s), Paragraph('', body_s), Paragraph('', body_s)])

        cw_c = avail * 0.45
        cw_r = avail * 0.15
        cw_m = avail - cw_c - cw_r
        crit_table = Table(criteria_data, colWidths=[cw_c, cw_r, cw_m])
        ts = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#000000')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ]
        if scores:
            ts.append(('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F0FDF4')))
        crit_table.setStyle(TableStyle(ts))
        story.append(crit_table)

        # Section III: Summary of Discussion
        summary_text = (submission.summary if submission else '') or ''
        story.append(Paragraph('III. Summary of Discussion and Panel Observations', section_s))
        story.append(Paragraph(
            'Provide a brief narrative highlighting the strengths, areas for improvement, '
            'and key points raised during the interview.',
            small_s,
        ))
        _add_text_box(story, summary_text, body_s, avail, height=2.4 * cm)

        # Section IV: Justification
        just_text = (submission.justification if submission else '') or ''
        story.append(Paragraph('IV. Justification for Recommendation', section_s))
        story.append(Paragraph(
            '(Please include the subjects to be taught in the justification)',
            small_s,
        ))
        _add_text_box(story, just_text, body_s, avail, height=2.4 * cm)

    # ── PANEL MEMBERS ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(Paragraph('Interview Panel Members:', section_s))

    if submitted_assignments:
        position_s = _style('ev_pos', fontName='Helvetica', fontSize=8,
                            alignment=1, leading=11, textColor=colors.HexColor('#6B7280'))
        rows = []
        cells = []
        for ea in submitted_assignments:
            name_para = Paragraph(f'<b>{ea.evaluator_display_name}</b>', panel_s)
            pos = _evaluator_position(ea)
            if pos:
                cell_content = [name_para, Paragraph(pos, position_s)]
            else:
                cell_content = [name_para]
            cells.append(cell_content)

        for i in range(0, len(cells), 2):
            left = cells[i]
            right = cells[i + 1] if i + 1 < len(cells) else [Paragraph('', body_s)]
            rows.append([left, right])

        panel_table = Table(rows, colWidths=[avail / 2, avail / 2])
        panel_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#000000')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 18),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(panel_table)

    # ── FOOTER (content blanked; spacing preserved) ───────────────────────────
    story.append(Spacer(1, 12))
    story.append(Spacer(1, 5))  # replaces HRFlowable (0.5pt thickness + 4pt spaceAfter)

    ft_col = avail * 0.55
    qs_col = avail - ft_col
    qs = Spacer(qs_col, 3.4 * cm)
    footer_text = [
        Paragraph('', footer_s),
        Paragraph('', footer_s),
        Paragraph('', footer_s),
        Spacer(1, 3),
        Paragraph('', footer_bold_s),
    ]
    footer_table = Table([[footer_text, qs]], colWidths=[ft_col, qs_col])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    story.append(footer_table)

    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()

    last_name = (applicant.last_name or '').strip().title()
    app_id = applicant.applicant_id
    filename = f'{last_name} - {app_id} - Evaluation Form.pdf'
    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _add_text_box(story, text, style, width, height):
    """Render a bordered text box; shows content if present, else blank lines."""
    if text:
        inner = Paragraph(text.replace('\n', '<br/>'), style)
    else:
        inner = Paragraph('<br/><br/>', style)
    box_table = Table([[inner]], colWidths=[width])
    box_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.4, colors.HexColor('#000000')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('MINROWHEIGHT', (0, 0), (-1, -1), height),
    ]))
    story.append(box_table)
