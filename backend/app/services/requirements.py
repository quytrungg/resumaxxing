"""JD requirement extraction and alias-aware ATS matching.

Two halves, deliberately separated:

* **Extraction** is provider-dependent. The LLM reads the JD once per review and
  returns the *actual* requirements (``llm.extract_requirements``). With the
  ``mock`` provider - or when that call fails - :func:`from_heuristic` adapts the
  old word-frequency list so the app still works with no API keys.
* **Matching** is deterministic and identical for every provider: given a
  requirement list, decide which entries the CV covers using word boundaries and
  the alias table in ``skills_aliases``.

Word-boundary matching is what fixes the old substring bug where a CV saying
only "JavaScript" satisfied a "Java" requirement.

Ambiguous terms - skills that are also ordinary English words (``Go``, ``React``,
``Flask``, ...) - are matched **case-sensitively** against the form written in
the requirement. We would rather report a missing skill than claim a false
match, and it stops "go to market" from counting as Go experience.
"""
import re
from functools import lru_cache
from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from app.services.keywords import extract_keywords
from app.services.skills_aliases import ALIASES

MUST = "must"
NICE = "nice"

# Weights for the headline coverage number: a must-have is worth three
# nice-to-haves, so closing a hard requirement moves the bar more.
MUST_WEIGHT = 3
NICE_WEIGHT = 1

# Surfaces that collide with ordinary English; matched case-sensitively.
AMBIGUOUS_SURFACES = {
    "go", "react", "flask", "spark", "express", "swift", "rust", "airflow",
    "r", "c", "d",
}

# Prose the model sometimes mistakes for a requirement. Cheap defence against
# re-introducing the "ATS: nice, deep, hands" panel this work replaces.
JUNK_LABELS = {
    "nice", "deep", "hands", "hands-on", "handson", "building", "collaborate",
    "collaboration", "designers", "mentor", "mentoring", "familiarity",
    "understanding", "ability", "experience", "years", "team", "teams", "role",
    "candidate", "requirements", "responsibilities", "benefits", "plus", "etc",
    "strong", "good", "great", "excellent", "knowledge", "working",
    "environment", "opportunity", "you", "your", "we", "our",
}

_SURFACE_SPLIT = re.compile(r"[\s/\-_]+")
# Lookarounds keep "java" out of "javascript" and "api" out of "capital", while
# letting technical suffixes through ("c++", "c#", ".net").
_BEFORE = r"(?<![a-z0-9+#])"
_AFTER = r"(?![a-z0-9+#])"
_MAX_LABEL_CHARS = 60

# Framing the model sometimes leaves on a label ("experience with Kubernetes").
# Stripped before matching so the surface is the skill, not the sentence.
_QUALIFIER_PREFIX = re.compile(
    r"^(?:(?:strong|solid|deep|good|great|excellent|working|hands-on|proven|"
    r"demonstrable|basic|advanced|practical|extensive|hands on)\s+)?"
    r"(?:experience|knowledge|understanding|proficiency|familiarity|expertise|"
    r"ability|skills?|background|exposure|command)"
    r"\s*(?:in|with|of|using|across|to|on)?\s+",
    re.IGNORECASE,
)


class Requirement(BaseModel):
    label: str
    canonical: str = ""
    aliases: List[str] = Field(default_factory=list)
    importance: str = MUST
    category: Optional[str] = None
    quote: Optional[str] = None
    matched: bool = False


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, and unify dashes/underscores."""
    text = (text or "").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"[\s_]+", " ", text).strip().lower()


def _build_alias_index() -> Dict[str, str]:
    index: Dict[str, str] = {}
    for canonical, variants in ALIASES.items():
        index[normalize(canonical)] = normalize(canonical)
        for variant in variants:
            index.setdefault(normalize(variant), normalize(canonical))
    return index


_ALIAS_INDEX = _build_alias_index()


def canonical_for(text: str) -> str:
    """Map a known surface form onto its canonical term ("k8s" -> "kubernetes")."""
    key = normalize(text)
    return _ALIAS_INDEX.get(key, key)


@lru_cache(maxsize=1024)
def _compiled(surface: str, flags: int) -> re.Pattern:
    tokens = [re.escape(part) for part in _SURFACE_SPLIT.split(surface) if part]
    body = r"[\s/\-_]+".join(tokens)
    return re.compile(_BEFORE + body + _AFTER, flags)


def surface_forms(requirement: Requirement) -> List[str]:
    """Every spelling that should satisfy `requirement`, deduped, order kept."""
    raw: Iterable[str] = [
        requirement.label,
        requirement.canonical,
        *requirement.aliases,
        *ALIASES.get(normalize(requirement.canonical), []),
    ]
    seen, forms = set(), []
    for value in raw:
        text = (value or "").strip()
        if len(text) < 2:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        forms.append(text)
    return forms


def _covers(cv_text: str, requirement: Requirement) -> bool:
    for surface in surface_forms(requirement):
        flags = 0 if surface.lower() in AMBIGUOUS_SURFACES else re.IGNORECASE
        if _compiled(surface, flags).search(cv_text):
            return True
    return False


def _pct(hits: int, total: int) -> Optional[int]:
    return round(100 * hits / total) if total else None


def match_requirements(cv_text: str, requirements: List[Requirement]) -> Dict:
    """Score a requirement list against the CV.

    Returned ``coverage`` weights must-haves over nice-to-haves; the per-group
    percentages are ``None`` when that group is empty so callers can hide it.
    """
    results = [
        req.model_copy(update={"matched": _covers(cv_text, req)})
        for req in requirements
    ]
    must = [r for r in results if r.importance != NICE]
    nice = [r for r in results if r.importance == NICE]
    must_hits = sum(1 for r in must if r.matched)
    nice_hits = sum(1 for r in nice if r.matched)

    weighted_top = must_hits * MUST_WEIGHT + nice_hits * NICE_WEIGHT
    weighted_bottom = len(must) * MUST_WEIGHT + len(nice) * NICE_WEIGHT
    coverage = round(100 * weighted_top / weighted_bottom) if weighted_bottom else 0

    matched = [r for r in results if r.matched]
    missing = [r for r in results if not r.matched]
    return {
        "requirements": results,
        "matched": matched,
        "missing": missing,
        "matched_labels": [r.label for r in matched],
        "missing_labels": [r.label for r in missing],
        "coverage": coverage,
        "must_have_coverage": _pct(must_hits, len(must)),
        "nice_to_have_coverage": _pct(nice_hits, len(nice)),
    }


def _first_occurrence(text: str, term: str) -> Optional[str]:
    """The term as the JD actually spells it, so labels keep their casing."""
    match = _compiled(term, re.IGNORECASE).search(text)
    return match.group(0) if match else None


def _quote_for(text: str, term: str) -> Optional[str]:
    """The JD line containing `term`, trimmed - evidence for the panel."""
    pattern = _compiled(term, re.IGNORECASE)
    for line in text.splitlines():
        if pattern.search(line):
            return line.strip()[:240] or None
    return None


def _importance(value) -> str:
    text = normalize(str(value or ""))
    if any(word in text for word in (
        "nice", "preferred", "prefer", "optional", "plus", "bonus", "desirable",
        "desired", "good to have", "not required",
    )):
        return NICE
    return MUST


def _strip_qualifiers(label: str) -> str:
    """Drop "experience with"/"strong understanding of" framing from a label."""
    text = label.strip(" .:;-")
    for _ in range(2):
        stripped = _QUALIFIER_PREFIX.sub("", text).strip(" .:;-")
        if stripped == text or not stripped:
            break
        text = stripped
    return text


def _is_junk(label: str) -> bool:
    text = normalize(label)
    if not text or text in JUNK_LABELS:
        return True
    return len(label) > _MAX_LABEL_CHARS or len(text.split()) > 5


def parse_requirements(items) -> List[Requirement]:
    """Validate the model's JSON payload into deduped `Requirement` objects."""
    if isinstance(items, dict):
        items = items.get("requirements") or []
    if not isinstance(items, list):
        return []

    parsed: List[Requirement] = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        label = _strip_qualifiers(str(item.get("label") or item.get("name") or ""))
        if _is_junk(label):
            continue
        canonical = canonical_for(item.get("canonical") or label)
        if canonical in seen:
            continue
        seen.add(canonical)

        aliases = [
            str(alias).strip()
            for alias in (item.get("aliases") or [])
            if str(alias).strip()
        ]
        for extra in ALIASES.get(canonical, []):
            if extra not in aliases:
                aliases.append(extra)

        quote = item.get("quote")
        category = item.get("category")
        parsed.append(Requirement(
            label=label,
            canonical=canonical,
            aliases=aliases,
            importance=_importance(item.get("importance")),
            category=str(category).strip()[:40] if category else None,
            quote=str(quote).strip()[:300] if quote else None,
        ))
    return parsed[:40]


def from_heuristic(jd_text: str, top_n: int = 30) -> List[Requirement]:
    """Fallback list built from the deterministic word-frequency extractor.

    Used for the ``mock`` provider and when the extraction call fails. It is
    intentionally *not* a better extractor - same single-word frequency signal as
    before - but it is alias-normalised so matching still behaves.
    """
    requirements: List[Requirement] = []
    seen = set()
    for keyword in extract_keywords(jd_text, top_n):
        canonical = canonical_for(keyword)
        if canonical in seen or _is_junk(keyword):
            continue
        seen.add(canonical)
        requirements.append(Requirement(
            label=_first_occurrence(jd_text, keyword) or keyword,
            canonical=canonical,
            aliases=list(ALIASES.get(canonical, [])),
            importance=MUST,
            quote=_quote_for(jd_text, keyword),
        ))
    return requirements
