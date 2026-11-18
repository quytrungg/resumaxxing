import io
from typing import List

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
)
from reportlab.platypus.flowables import HRFlowable
from xml.sax.saxutils import escape

from app.models import Suggestion, SuggestionStatus, SuggestionType
from app.schemas import StructuredCV


# The CV design is owned by the LaTeX template in `services/latex.py`; these
# values mirror that pinned preamble so the Word, PDF and `.tex` downloads of a
# review look like the same document:
#   \documentclass[11pt,a4paper]{article} + \usepackage{lmodern}
#   \usepackage[margin=1.5cm,top=1.4cm,bottom=1.4cm]{geometry}
#   {\LARGE\bfseries name}\\[2pt] {\large headline}\\[3pt] {contact $\mid$ ...}
#   \titlespacing*{\section}{0pt}{0.75em}{0.25em} + \titlerule[0.6pt]
#   \setlist[itemize]{leftmargin=1.1em,itemsep=0.1em,topsep=0.15em,parsep=0pt}
CV_LAYOUT = {
    "page": A4,
    "margin_x_cm": 1.5,
    "margin_top_cm": 1.4,
    "margin_bottom_cm": 1.4,
    # lmodern is not available to reportlab/python-docx; Times is the closest
    # metrically compatible serif (and is installed everywhere Word runs).
    "face": "Times New Roman",
    "pdf_body_font": "Times-Roman",
    "pdf_bold_font": "Times-Bold",
    "body_size": 11.0,                 # \normalsize at 11pt
    "name_size": 17.3,                 # \LARGE at 11pt
    "headline_size": 12.0,             # \large at 11pt
    "leading": 13.6,                   # \baselineskip at 11pt
    "name_space_after": 2.0,           # \\[2pt]
    "headline_space_after": 3.0,       # \\[3pt]
    "contact_space_after": 2.0,
    "contact_separator": " | ",
    "heading_space_before": 8.25,      # 0.75em
    "heading_space_after": 2.75,       # 0.25em
    "heading_rule": 0.6,               # \titlerule[0.6pt]
    "bullet_indent": 12.1,             # leftmargin=1.1em
    "bullet_topsep": 1.65,             # topsep=0.15em
    "bullet_space_after": 1.1,         # itemsep=0.1em
}

# A4 dimensions in twips, used verbatim so the DOCX page size is exactly A4.
A4_TWIPS = (11906, 16838)


def _twips(count: int) -> Emu:
    """OOXML measures lengths in twentieths of a point (635 EMU each)."""
    return Emu(count * 635)


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


def _cv_pdf_styles() -> dict:
    """Styles for the CV download, matched to the LaTeX template."""
    layout = CV_LAYOUT
    base = getSampleStyleSheet()
    face = layout["pdf_body_font"]
    bold = layout["pdf_bold_font"]
    return {
        "name": ParagraphStyle(
            "CVName", parent=base["Title"], fontName=bold,
            fontSize=layout["name_size"], leading=layout["name_size"] + 2,
            alignment=TA_CENTER, spaceBefore=0,
            spaceAfter=layout["name_space_after"],
        ),
        "headline": ParagraphStyle(
            "CVHeadline", parent=base["BodyText"], fontName=face,
            fontSize=layout["headline_size"], leading=layout["headline_size"] + 2,
            alignment=TA_CENTER, spaceBefore=0,
            spaceAfter=layout["headline_space_after"],
        ),
        "contact": ParagraphStyle(
            "CVContact", parent=base["BodyText"], fontName=face,
            fontSize=layout["body_size"], leading=layout["leading"],
            alignment=TA_CENTER, spaceBefore=0,
            spaceAfter=layout["contact_space_after"],
        ),
        "heading": ParagraphStyle(
            "CVHeading", parent=base["Heading2"], fontName=bold,
            fontSize=layout["body_size"], leading=layout["leading"],
            spaceBefore=layout["heading_space_before"], spaceAfter=0,
            keepWithNext=1,
        ),
        "body": ParagraphStyle(
            "CVBody", parent=base["BodyText"], fontName=face,
            fontSize=layout["body_size"], leading=layout["leading"],
            spaceBefore=0, spaceAfter=layout["bullet_space_after"],
        ),
        "bullet": ParagraphStyle(
            "CVBullet", parent=base["BodyText"], fontName=face,
            fontSize=layout["body_size"], leading=layout["leading"],
            leftIndent=layout["bullet_indent"], bulletIndent=0,
            bulletFontName=face, bulletFontSize=layout["body_size"],
            spaceBefore=0, spaceAfter=layout["bullet_space_after"],
        ),
    }


def _pdf_build(flowables, margins=None, padding=6) -> bytes:
    """Build the PDF. `padding` is the frame inset; reportlab defaults to 6pt,
    while the CV passes 0 so the text area sits exactly on the LaTeX margins."""
    page = CV_LAYOUT["page"]
    left, right, top, bottom = margins or (2 * cm, 2 * cm, 2 * cm, 2 * cm)
    frame = Frame(
        left, bottom, page[0] - left - right, page[1] - top - bottom, id="body",
        leftPadding=padding, rightPadding=padding,
        topPadding=padding, bottomPadding=padding,
    )
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=page,
        leftMargin=left, rightMargin=right,
        topMargin=top, bottomMargin=bottom,
        title="CV",
    )
    doc.addPageTemplates([PageTemplate(id="body", frames=[frame])])
    doc.build(flowables)
    return buf.getvalue()


def to_pdf_bytes_structured(cv: StructuredCV) -> bytes:
    """CV PDF in the LaTeX template's layout (A4, 1.5/1.4cm margins, serif)."""
    layout = CV_LAYOUT
    styles = _cv_pdf_styles()
    flowables = []
    if cv.name:
        flowables.append(Paragraph(escape(cv.name), styles["name"]))
    if cv.headline:
        flowables.append(Paragraph(escape(cv.headline), styles["headline"]))
    if cv.contact:
        contact = layout["contact_separator"].join(cv.contact)
        flowables.append(Paragraph(escape(contact), styles["contact"]))
    for section in cv.sections:
        flowables.append(Paragraph(escape(section.heading.upper()), styles["heading"]))
        flowables.append(HRFlowable(
            width="100%", thickness=layout["heading_rule"], color="#000000",
            spaceBefore=0, spaceAfter=layout["heading_space_after"],
        ))
        for bullet in section.bullets:
            flowables.append(
                Paragraph(escape(bullet), styles["bullet"], bulletText="\u2022")
            )
    if not flowables:
        flowables.append(Paragraph("(empty document)", styles["body"]))
    margins = (
        layout["margin_x_cm"] * cm, layout["margin_x_cm"] * cm,
        layout["margin_top_cm"] * cm, layout["margin_bottom_cm"] * cm,
    )
    return _pdf_build(flowables, margins=margins, padding=0)


# ----- DOCX rendering (mirrors the LaTeX template layout) -----

def _cm_to_twips(value: float) -> int:
    return int(round(value / 2.54 * 1440))


def _new_cv_document() -> Document:
    layout = CV_LAYOUT
    doc = Document()
    section = doc.sections[0]
    section.page_width = _twips(A4_TWIPS[0])
    section.page_height = _twips(A4_TWIPS[1])
    section.left_margin = section.right_margin = _twips(
        _cm_to_twips(layout["margin_x_cm"])
    )
    section.top_margin = _twips(_cm_to_twips(layout["margin_top_cm"]))
    section.bottom_margin = _twips(_cm_to_twips(layout["margin_bottom_cm"]))

    normal = doc.styles["Normal"]
    normal.font.name = layout["face"]
    normal.font.size = Pt(layout["body_size"])
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), layout["face"])
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = Pt(layout["leading"])

    # Word's List Bullet style suppresses spacing between same-style
    # paragraphs; LaTeX's itemsep wants a thin gap instead.
    bullet_ppr = doc.styles["List Bullet"].element.find(qn("w:pPr"))
    if bullet_ppr is not None:
        for element in bullet_ppr.findall(qn("w:contextualSpacing")):
            bullet_ppr.remove(element)
    return doc


def _add_bottom_border(paragraph, thickness_pt: float) -> None:
    """Reproduce the LaTeX \\titlerule under a section heading."""
    pPr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    # w:sz is measured in eighths of a point.
    bottom.set(qn("w:sz"), str(int(round(thickness_pt * 8))))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    borders.append(bottom)
    pPr.append(borders)


def _add_cv_heading(doc: Document, heading: str):
    layout = CV_LAYOUT
    para = doc.add_paragraph()
    run = para.add_run(heading.upper())
    run.bold = True
    run.font.size = Pt(layout["body_size"])
    _add_bottom_border(para, layout["heading_rule"])
    fmt = para.paragraph_format
    fmt.keep_with_next = True
    fmt.space_before = Pt(layout["heading_space_before"])
    fmt.space_after = Pt(layout["heading_space_after"])
    return para


def _add_cv_bullet(doc: Document, text: str, first: bool = False):
    layout = CV_LAYOUT
    para = doc.add_paragraph(text, style="List Bullet")
    fmt = para.paragraph_format
    fmt.left_indent = Pt(layout["bullet_indent"])
    fmt.first_line_indent = Pt(-layout["bullet_indent"])
    fmt.space_before = Pt(layout["bullet_topsep"] if first else 0)
    fmt.space_after = Pt(layout["bullet_space_after"])
    return para


def to_docx_bytes_structured(cv: StructuredCV) -> bytes:
    layout = CV_LAYOUT
    doc = _new_cv_document()

    def add_header(text: str, size: float, bold: bool = False,
                   space_after: float = 0.0) -> None:
        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run(text)
        run.bold = bold
        # Word stores font sizes on a half-point grid.
        run.font.size = Pt(round(size * 2) / 2)
        para.paragraph_format.space_after = Pt(space_after)

    if cv.name:
        add_header(cv.name, layout["name_size"], bold=True,
                   space_after=layout["name_space_after"])
    if cv.headline:
        add_header(cv.headline, layout["headline_size"],
                   space_after=layout["headline_space_after"])
    if cv.contact:
        add_header(layout["contact_separator"].join(cv.contact),
                   layout["body_size"], space_after=layout["contact_space_after"])
    for section in cv.sections:
        _add_cv_heading(doc, section.heading)
        for index, bullet in enumerate(section.bullets):
            _add_cv_bullet(doc, bullet, first=index == 0)

    if not cv.sections and not (cv.name or cv.headline or cv.contact):
        doc.add_paragraph("(empty document)")

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
