"""
PDF scorecard generation using ReportLab. Only ever called from the admin
router - candidates never see this.
"""
from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

from app import models


def generate_report_pdf(session: models.InterviewSession) -> bytes:
    candidate = session.user
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], textColor=colors.HexColor("#1a1a2e"))
    h2_style = ParagraphStyle("H2Custom", parent=styles["Heading2"], textColor=colors.HexColor("#16213e"))
    normal = styles["Normal"]
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"))
    feedback_style = ParagraphStyle("Feedback", parent=styles["Normal"], fontSize=10, spaceAfter=4)
    missed_style = ParagraphStyle("Missed", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#a4133c"))

    elements = []

    elements.append(Paragraph("AI Technical Interview Report", title_style))
    elements.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", small))
    elements.append(Spacer(1, 14))

    skills_str = ", ".join(candidate.skills) if candidate.skills else "N/A"
    elements.append(Paragraph(f"<b>Candidate:</b> {candidate.name}", normal))
    elements.append(Paragraph(f"<b>Email:</b> {candidate.email}", normal))
    elements.append(Paragraph(f"<b>Experience:</b> {candidate.experience_years} years", normal))
    elements.append(Paragraph(f"<b>Skills:</b> {skills_str}", normal))
    elements.append(Spacer(1, 14))

    elements.append(Paragraph("Overall Summary", h2_style))
    summary_data = [
        ["Overall Score", f"{session.overall_score:.1f} / 10"],
        ["Average Technical Score", f"{session.avg_technical_score:.1f} / 10"],
        ["Average Communication Score", f"{session.avg_communication_score:.1f} / 10"],
        ["Verdict", session.verdict],
    ]
    summary_table = Table(summary_data, colWidths=[220, 220])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef1ff")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1a1a2e")),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Question-by-Question Breakdown", h2_style))
    elements.append(Spacer(1, 8))

    sorted_answers = sorted(session.answers, key=lambda a: a.session_question.question_index)

    for ans in sorted_answers:
        q = ans.session_question
        elements.append(Paragraph(f"<b>Q{q.question_index + 1} ({q.topic}). {q.question_text}</b>", normal))
        elements.append(Paragraph(
            f"Technical: {ans.technical_score:.1f}/10 &nbsp;|&nbsp; "
            f"Communication: {ans.communication_score:.1f}/10 &nbsp;|&nbsp; "
            f"Time: {ans.time_taken_seconds}s &nbsp;|&nbsp; "
            f"Speaking rate: {ans.words_per_minute} wpm &nbsp;|&nbsp; "
            f"Filler words: {ans.filler_word_count}",
            small,
        ))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"<b>Feedback:</b> {ans.feedback}", feedback_style))
        if ans.missed_concepts:
            elements.append(Paragraph(f"<b>Missed:</b> {'; '.join(ans.missed_concepts)}", missed_style))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"<i>Transcript:</i> \"{ans.transcript}\"", small))
        elements.append(Spacer(1, 8))
        elements.append(HRFlowable(width="100%", color=colors.HexColor("#dddddd")))
        elements.append(Spacer(1, 10))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
