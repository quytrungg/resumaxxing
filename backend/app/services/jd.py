"""Deterministic job title/company extraction from a job description.

No network and no LLM: these helpers only read what the posting already says.
A miss returns ``None`` so callers can fall back to a neutral label.
"""
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

MAX_TITLE_LEN = 120
MAX_COMPANY_LEN = 80
MAX_TITLE_WORDS = 15
MAX_COMPANY_WORDS = 8

# Section headings and generic words that are never a job title.
BOILERPLATE = {
    "about us", "about the company", "about the role", "about the team",
    "about you", "benefits", "company", "description", "job description",
    "job summary", "login", "log in", "sign in", "join now", "overview",
    "perks", "qualifications", "requirements", "responsibilities", "the role",
    "what we do", "what you'll do", "who we are", "why join us",
}

# Words that look like an ``at <Company>`` tail but are not companies.
NOT_COMPANIES = {
    "a", "an", "home", "large", "least", "our", "remote", "scale", "the",
    "their", "work",
}

# Path segments that identify a job board rather than the employer.
URL_NOISE = {
    "apply", "career", "careers", "details", "en", "job", "jobs", "opening",
    "openings", "position", "positions", "posting", "postings", "us", "view",
}

# Host/site names commonly appended to a page <title>.
KNOWN_SITES = {
    "angellist", "ashby", "bamboohr", "glassdoor", "greenhouse", "indeed",
    "jobvite", "lever", "linkedin", "monster", "seek", "smartrecruiters",
    "wellfound", "workday", "ziprecruiter",
}

_TITLE_LABEL = re.compile(
    r"^[>*#•\-\s]*(?:job\s*title|position|role|title)\s*[:\-–—]\s*(.+)$",
    re.IGNORECASE,
)
_COMPANY_LABEL = re.compile(
    r"^[>*#•\-\s]*(?:company|employer|organisation|organization)"
    r"\s*[:\-–—]\s*(.+)$",
    re.IGNORECASE,
)
_AT_FORM = re.compile(
    r"^(?P<title>.+?)\s+(?:at|@)\s+(?P<company>[^·|]+?)"
    r"(?:\s*[·|].*)?$",
    re.IGNORECASE,
)


def _lines(text):
    return [
        line.strip()
        for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]


def clean_title(raw):
    """Normalise one candidate title, or return ``None`` if it is not one."""
    if not raw:
        return None
    text = " ".join(str(raw).split()).strip(" \"'“”‘’")
    text = re.sub(r"^[>*#•\-–—\s]+", "", text)
    text = re.sub(r"[\s\-–—|,:;]+$", "", text)
    if not text or len(text) > MAX_TITLE_LEN:
        return None
    if len(text.split()) > MAX_TITLE_WORDS:
        return None
    if text[-1] in ".;!?":
        return None
    if re.match(r"^(?:https?://|www\.)", text, re.IGNORECASE):
        return None
    if re.match(rf"^(?:{'|'.join(sorted(KNOWN_SITES))})\b", text.lower()):
        return None
    if text.lower() in BOILERPLATE:
        return None
    return text


def _clean_company(raw):
    if not raw:
        return None
    text = " ".join(str(raw).split())
    text = re.split(r"\s*[·|]\s*", text)[0]
    text = text.strip(" \"'“”‘’,;:-–—")
    if not text or len(text) > MAX_COMPANY_LEN:
        return None
    if len(text.split()) > MAX_COMPANY_WORDS:
        return None
    if text[-1] in ".!?":
        return None
    if text.lower() in BOILERPLATE or text.lower() in NOT_COMPANIES:
        return None
    return text


def _at_parts(line):
    """Split ``Senior Engineer at Acme`` into ``("Senior Engineer", "Acme")``."""
    match = _AT_FORM.match(line)
    if not match:
        return None
    title = clean_title(match.group("title"))
    company = _clean_company(match.group("company"))
    if not title or not company:
        return None
    if not company[0].isupper() or company.lower() in NOT_COMPANIES:
        return None
    return title, company


def _leading_headline(text):
    """First visible headline: the first line, or the leading chunk of a
    one-line scraped page before a location/site separator."""
    lines = _lines(text)
    first = next((line for line in lines if line), "")
    if not first or len([line for line in lines if line]) > 1:
        return first
    return re.split(r"\s+[—–]\s+|\s+\|\s+", first, maxsplit=1)[0].strip()


def extract_title_from_text(text):
    """Best-effort title from pasted or scraped JD text."""
    lines = _lines(text)
    if not lines:
        return None

    for line in lines[:30]:
        match = _TITLE_LABEL.match(line)
        if match:
            title = clean_title(match.group(1))
            if title:
                return title

    headline = _leading_headline(text)
    if not headline:
        return None
    parts = _at_parts(headline)
    if parts:
        return parts[0]
    return clean_title(headline)


def extract_company_from_text(text):
    """Best-effort company from an explicit label or an ``at <Company>`` tail."""
    lines = _lines(text)
    if not lines:
        return None

    for line in lines[:30]:
        match = _COMPANY_LABEL.match(line)
        if match:
            company = _clean_company(match.group(1))
            if company:
                return company

    parts = _at_parts(_leading_headline(text))
    return parts[1] if parts else None


def title_from_url(url):
    """Derive a title from the last meaningful path segment of a URL."""
    if not url:
        return None
    try:
        path = urlparse(url).path
    except ValueError:
        return None
    for segment in reversed([s for s in path.split("/") if s]):
        candidate = segment.rsplit(".", 1)[0]
        candidate = re.sub(r"[-_+]+", " ", candidate).strip()
        if not candidate or candidate.isdigit() or candidate.lower() in URL_NOISE:
            continue
        title = clean_title(candidate)
        if title:
            return title.title() if title.islower() else title
    return None


def _title_from_page_title(raw):
    text = " ".join(str(raw or "").split())
    if not text:
        return None
    parts = [part.strip() for part in re.split(r"\s+[|\-–—]\s+", text) if part.strip()]
    if len(parts) > 1:
        kept = [
            part for part in parts
            if not any(site in part.lower() for site in KNOWN_SITES)
        ]
        # A job title is usually the longest surviving segment.
        parts = sorted(kept or parts, key=len, reverse=True)
    for part in parts:
        title = clean_title(part)
        if title:
            return title
    return None


def title_from_html(html):
    """Read the role from a page's ``<h1>``, else its ``<title>``."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    if heading is not None:
        title = clean_title(heading.get_text(" "))
        if title:
            return title
    if soup.title is not None:
        return _title_from_page_title(soup.title.get_text(" "))
    return None
