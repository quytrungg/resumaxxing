"""Turn free-text CVs into a structured document and back.

Shared by the LLM rewrite path (structured JSON output) and the deterministic
fallback used when no provider is configured or the LLM call fails.
"""
import re
from typing import List, Optional

from app.schemas import StructuredCV, StructuredSection

KNOWN_HEADINGS = {
    "summary", "profile", "professional summary", "objective", "about",
    "about me", "experience", "work experience", "professional experience",
    "employment", "employment history", "skills", "technical skills",
    "core skills", "education", "projects", "certifications", "certificates",
    "publications", "awards", "languages", "interests", "volunteering",
}

BULLET_PREFIX = re.compile(r"^\s*(?:[-*•·–—]|\d+[.)])\s*")


def _is_known_heading(line: str) -> bool:
    return line.strip().rstrip(":").strip().lower() in KNOWN_HEADINGS


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 45:
        return False
    bare = stripped.rstrip(":").strip()
    if bare.lower() in KNOWN_HEADINGS:
        return True
    # ALL-CAPS short lines are treated as headings ("WORK EXPERIENCE").
    letters = [c for c in bare if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def structure_text(cv_text: str) -> StructuredCV:
    """Deterministically split CV text into header fields and sections."""
    lines = cv_text.replace("\r\n", "\n").split("\n")
    name: Optional[str] = None
    headline: Optional[str] = None
    contact: List[str] = []
    sections: List[StructuredSection] = []
    current: Optional[StructuredSection] = None
    preamble: List[str] = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if (name is None and not sections and not contact and not preamble
                and not _is_known_heading(line)
                and len(line) <= 60 and "@" not in line
                and not any(ch.isdigit() for ch in line)):
            name = line
            continue
        if _is_heading(line):
            current = StructuredSection(heading=line.rstrip(":").strip(), bullets=[])
            sections.append(current)
            continue
        if current is None:
            # Header block before the first heading: contact details or a
            # headline line.
            if "@" in line or any(ch.isdigit() for ch in line) or "http" in line.lower():
                contact.append(line)
            elif len(line) <= 120:
                preamble.append(line)
            continue
        current.bullets.append(BULLET_PREFIX.sub("", line))

    if not headline and preamble:
        headline = preamble[0]
    if not sections:
        body = [BULLET_PREFIX.sub("", ln.strip()) for ln in lines if ln.strip()]
        if name:
            body = body[1:] if body and body[0] == name else body
        sections = [StructuredSection(heading="Experience", bullets=body)]
    return StructuredCV(name=name, headline=headline, contact=contact, sections=sections)


def document_to_plain_text(doc: StructuredCV) -> str:
    parts: List[str] = []
    if doc.name:
        parts.append(doc.name)
    if doc.headline:
        parts.append(doc.headline)
    if doc.contact:
        parts.append(" | ".join(doc.contact))
    for section in doc.sections:
        parts.append("")
        parts.append(section.heading.upper())
        parts.extend(f"- {b}" for b in section.bullets)
    return "\n".join(parts).strip() + "\n"
