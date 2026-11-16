import io
from typing import List

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from xml.sax.saxutils import escape

from app.models import Suggestion, SuggestionStatus, SuggestionType
from app.schemas import StructuredCV


def build_final_text(base_cv_text: str, suggestions: List[Suggestion]) -> str:
    """Merge accepted suggestions into the base CV text (the quick-export path)."""
    text = base_cv_text
    additions: List[str] = []
    for s in suggestions:
        if s.status != SuggestionStatus.ACCEPTED:
            continue
        if s.type == SuggestionType.REMOVE and s.original_text:
            text = text.replace(s.original_text, "")
        elif s.type == SuggestionType.UPDATE and s.original_text and s.original_text in text:
            text = text.replace(s.original_text, s.suggested_text)
        else:
            additions.append(s.suggested_text)
    if additions:
        text = text.rstrip() + "\n\n" + "\n".join(additions)
    return text


def accepted_change_texts(suggestions: List[Suggestion]) -> List[str]:
    """Accepted suggestions as plain lines, for LLM rewrite prompts."""
    return [
        f"{s.type.value} in {s.target_section or 'CV'}: {s.suggested_text}"
        for s in suggestions if s.status == SuggestionStatus.ACCEPTED
    ]


# ----- PDF rendering (reportlab platypus, wraps instead of truncating) -----

def _pdf_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "CVName", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, spaceAfter=2,
        ),
        "headline": ParagraphStyle(
            "CVHeadline", parent=base["BodyText"], fontName="Helvetica-Oblique",
            fontSize=10.5, leading=14, textColor="#444444", spaceAfter=2,
        ),
        "contact": ParagraphStyle(
            "CVContact", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9, leading=12, textColor="#555555", spaceAfter=6,
        ),
        "heading": ParagraphStyle(
            "CVHeading", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "CVBody", parent=base["BodyText"], fontName="Helvetica",
            fontSize=10, leading=14, spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "CVBullet", parent=base["BodyText"], fontName="Helvetica",
            fontSize=10, leading=14, leftIndent=14, bulletIndent=3,
            spaceAfter=3,
        ),
    }


def _pdf_build(flowables) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title="CV",
    )
    doc.build(flowables)
    return buf.getvalue()


def to_pdf_bytes(text: str) -> bytes:
    """Plain-text PDF (quick export); long lines wrap across the page width."""
    styles = _pdf_styles()
    flowables = []
    for line in text.splitlines():
        if not line.strip():
            flowables.append(Spacer(1, 6))
            continue
        flowables.append(Paragraph(escape(line), styles["body"]))
    return _pdf_build(flowables)


def to_pdf_bytes_structured(cv: StructuredCV) -> bytes:
    styles = _pdf_styles()
    flowables = []
    if cv.name:
        flowables.append(Paragraph(escape(cv.name), styles["name"]))
    if cv.headline:
        flowables.append(Paragraph(escape(cv.headline), styles["headline"]))
    if cv.contact:
        flowables.append(
            Paragraph(escape("  |  ".join(cv.contact)), styles["contact"])
        )
    for section in cv.sections:
        flowables.append(Paragraph(escape(section.heading.upper()), styles["heading"]))
        for bullet in section.bullets:
            flowables.append(
                Paragraph(escape(bullet), styles["bullet"], bulletText="\u2022")
            )
    if not flowables:
        flowables.append(Paragraph("(empty document)", styles["body"]))
    return _pdf_build(flowables)


# ----- DOCX rendering -----

def to_docx_bytes(text: str) -> bytes:
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def to_docx_bytes_structured(cv: StructuredCV) -> bytes:
    doc = Document()
    if cv.name:
        doc.add_heading(cv.name, level=0)
    if cv.headline:
        p = doc.add_paragraph(cv.headline)
        if p.runs:
            p.runs[0].italic = True
    if cv.contact:
        doc.add_paragraph("  |  ".join(cv.contact))
    for section in cv.sections:
        doc.add_heading(section.heading, level=2)
        for bullet in section.bullets:
            doc.add_paragraph(bullet, style="List Bullet")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ----- Cover letter rendering (paragraph blocks) -----

def _blocks(text: str) -> List[str]:
    blocks = [b.strip() for b in text.replace("\r\n", "\n").split("\n\n")]
    return [b for b in blocks if b]


def letter_to_docx_bytes(text: str) -> bytes:
    doc = Document()
    for block in _blocks(text):
        for i, line in enumerate(block.split("\n")):
            para = doc.add_paragraph(line)
            if i:
                para.paragraph_format.space_after = 0
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def letter_to_pdf_bytes(text: str) -> bytes:
    styles = _pdf_styles()
    flowables = []
    for block in _blocks(text):
        flowables.append(
            Paragraph(escape(block).replace("\n", "<br/>"), styles["body"])
        )
        flowables.append(Spacer(1, 8))
    return _pdf_build(flowables)
