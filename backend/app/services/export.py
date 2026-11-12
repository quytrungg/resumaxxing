import io
from typing import List

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from app.models import Suggestion, SuggestionStatus, SuggestionType


def build_final_text(base_cv_text: str, suggestions: List[Suggestion]) -> str:
    """Merge accepted suggestions into the base CV text."""
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


def to_pdf_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 2 * cm
    c.setFont("Helvetica", 10)
    for line in text.splitlines():
        if y < 2 * cm:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 2 * cm
        c.drawString(2 * cm, y, line[:110])
        y -= 14
    c.save()
    return buf.getvalue()


def to_docx_bytes(text: str) -> bytes:
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
