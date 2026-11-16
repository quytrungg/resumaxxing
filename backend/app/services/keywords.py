"""Deterministic JD keyword extraction and ATS-style coverage.

Heuristic only - it never calls an LLM, so coverage is identical for every
provider (including `mock`).
"""
import re
from typing import Dict, List

STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "are", "our", "this", "that",
    "will", "have", "has", "job", "role", "team", "work", "working", "ability",
    "experience", "years", "year", "skills", "skill", "strong", "plus", "etc",
    "including", "across", "within", "about", "from", "into", "who", "what",
    "how", "new", "all", "any", "can", "may", "must", "requirements", "join",
    "hiring", "senior", "junior", "looking", "candidate", "ideal", "engineer",
    "engineering", "developer", "development", "software", "company", "teams",
    "need", "needs", "wanted", "their", "they", "them", "who", "someone",
}


def extract_keywords(text: str, top_n: int = 25) -> List[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z+#.]{2,}", text.lower())
    freq: Dict[str, int] = {}
    for w in words:
        w = w.rstrip(".")
        if w and w not in STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:top_n]]


def coverage(cv_text: str, jd_text: str, top_n: int = 30) -> Dict:
    """Return {matched, missing, coverage} for the JD keywords in `jd_text`."""
    jd_kws = extract_keywords(jd_text, top_n)
    if not jd_kws:
        return {"matched": [], "missing": [], "coverage": 0}
    cv_lower = cv_text.lower()
    matched = [k for k in jd_kws if k in cv_lower]
    missing = [k for k in jd_kws if k not in cv_lower]
    return {
        "matched": matched,
        "missing": missing,
        "coverage": round(100 * len(matched) / len(jd_kws)),
    }
