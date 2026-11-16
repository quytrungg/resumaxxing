"""LLM service router: Claude / Ollama Cloud / Opencode Zen & Go, with a
deterministic local heuristic fallback so the app runs end-to-end
without any API keys.
"""
import hashlib
import json
import re
from typing import List, Optional

import httpx

from app.models import UserSettings
from app.schemas import LLMSuggestion, StructuredCV
from app.services import crypto, keywords
from app.services.document import structure_text
from app.services.model_catalog import PROVIDERS, stored_base_url

SUGGESTION_PROMPT = (
    "You are an expert tech recruiter. Compare this CV to this Job Description. "
    "Provide a JSON array of suggestions with keys: `type` (ADD/REMOVE/UPDATE), "
    "`target_section` (e.g., Experience, Skills), `original_text` (if applicable), "
    "`suggested_text`, and `reasoning`. Return ONLY valid JSON."
)

SCORING_PROMPT = (
    "Evaluate how well this CV matches this Job Description. Return ONLY a JSON "
    'object with a single key "score" containing an integer from 0 to 100.'
)

REWRITE_PROMPT = (
    "You are a professional CV editor. Rewrite the CV below into a cohesive, "
    "professional CV tailored to the job description, incorporating the accepted "
    "changes and removing anything that is clearly irrelevant to the role. Keep "
    "every fact truthful: never invent employers, dates, degrees or metrics. "
    "Return ONLY valid JSON with keys: `name` (string or null), `headline` "
    "(string or null), `contact` (array of strings), and `sections` (array of "
    "objects with `heading` (string) and `bullets` (array of strings)). Do not "
    "use markdown."
)

COVER_LETTER_PROMPT = (
    "You are a professional career writer. Write a concise cover letter (at most "
    "350 words) for the candidate CV below against the job description. Ground it "
    "only in facts present in the CV, reference the most relevant strengths, and "
    "use a confident, specific tone. Return plain text only: no markdown, no JSON, "
    "and no bracketed placeholders."
)

# Model used per provider when the caller does not override it.
DEFAULT_MODELS = {
    provider: spec["default_model"] for provider, spec in PROVIDERS.items()
}


def resolve_choice(settings: Optional[UserSettings],
                   provider: Optional[str] = None,
                   model: Optional[str] = None) -> tuple[str, Optional[str]]:
    """Effective (provider, model): explicit override > saved setting > mock."""
    stored_provider = settings.llm_provider if settings else None
    prov = provider or (str(stored_provider) if stored_provider else None) or "mock"
    if model:
        return prov, model
    saved = getattr(settings, PROVIDERS[prov]["model_field"], None) if (
        settings and prov in PROVIDERS
    ) else None
    return prov, (str(saved) if saved else DEFAULT_MODELS.get(prov))


def heuristic_score(cv_text: str, jd_text: str) -> int:
    if not keywords.extract_keywords(jd_text, 30):
        return 50
    return keywords.coverage(cv_text, jd_text, 30)["coverage"]


def heuristic_suggestions(cv_text: str, jd_text: str) -> List[LLMSuggestion]:
    jd_kws = keywords.extract_keywords(jd_text, 20)
    cv_lower = cv_text.lower()
    missing = [k for k in jd_kws if k not in cv_lower][:6]
    suggestions = [
        LLMSuggestion(
            type="ADD",
            target_section="Skills",
            suggested_text=f"- {kw.title()}",
            reasoning=f'"{kw}" appears in the job description but not in your CV.',
        )
        for kw in missing
    ]
    suggestions.append(
        LLMSuggestion(
            type="UPDATE",
            target_section="Summary",
            original_text=(cv_text.splitlines()[0] if cv_text else ""),
            suggested_text=(
                "Tailor your summary to mention "
                + ", ".join(missing[:2] if missing else jd_kws[:2])
                + " to mirror the job description."
            ),
            reasoning="A JD-aligned summary improves recruiter and ATS matching.",
        )
    )
    return suggestions


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}|\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON in LLM response")
    return json.loads(match.group(0))


def _candidate_name(cv_text: str) -> str:
    for line in cv_text.splitlines():
        line = line.strip()
        if (line and len(line) <= 60 and "@" not in line
                and not any(ch.isdigit() for ch in line)):
            return line
    return "the candidate"


def mock_cover_letter(cv_text: str, jd_text: str,
                      linkedin_url: Optional[str]) -> str:
    """Template letter that slots in matched/missing JD keywords."""
    cov = keywords.coverage(cv_text, jd_text)
    focus_kws = cov["matched"][:4] or keywords.extract_keywords(jd_text, 4)
    focus = ", ".join(focus_kws) if focus_kws else "software engineering"
    name = _candidate_name(cv_text)

    paragraphs = [
        "Dear Hiring Manager,",
        (
            "I am writing to express my interest in the position described in "
            f"your job posting. My background in {focus} aligns closely with "
            "the requirements you have outlined, and I would welcome the "
            "opportunity to contribute to your team."
        ),
        (
            f"My experience centres on {focus}. The attached CV details the "
            "projects and outcomes most relevant to this role, including how I "
            "have applied these skills in practice."
        ),
    ]
    if cov["missing"]:
        paragraphs.append(
            "I am also actively deepening my hands-on experience with "
            f"{', '.join(cov['missing'][:3])}, which your posting highlights."
        )
    if linkedin_url:
        paragraphs.append(
            f"You can find further detail on my LinkedIn profile: {linkedin_url}"
        )
    paragraphs.append(
        "I would be glad to discuss how my experience can support your goals. "
        "Thank you for your time and consideration."
    )
    paragraphs.append(f"Sincerely,\n{name}")
    return "\n\n".join(paragraphs) + "\n"


def _session_id(provider: str, cv_text: str, jd_text: str) -> str:
    """Stable per-review id; OpenCode Go routes on `x-opencode-session`."""
    digest = hashlib.sha256(f"{provider}:{cv_text}:{jd_text}".encode()).hexdigest()
    return f"resumaxxing-{digest[:32]}"


async def _chat_completion(provider: str, settings: UserSettings,
                           system: str, user: str,
                           model: Optional[str] = None,
                           session: Optional[str] = None) -> str:
    if provider == "claude":
        base = stored_base_url(settings, provider)
        resp = httpx.post(
            f"{base}/v1/messages",
            headers={
                "x-api-key": crypto.decrypt(settings.claude_key) or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "accept": "application/json",
            },
            json={
                "model": model or DEFAULT_MODELS["claude"],
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return "".join(
            b.get("text", "")
            for b in resp.json().get("content", []) if b.get("type") == "text"
        )

    if provider in ("ollama", "opencode", "opencode_go"):
        stored = getattr(settings, PROVIDERS[provider]["key_field"], None)
        key = crypto.decrypt(stored)
        base = stored_base_url(settings, provider)
        headers = {"Authorization": f"Bearer {key}"}
        # OpenCode Go rejects requests without a stable session id.
        if provider == "opencode_go" and session:
            headers["x-opencode-session"] = session
        resp = httpx.post(
            f"{base}/v1/chat/completions",
            headers=headers,
            json={
                "model": model or DEFAULT_MODELS[provider],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    raise ValueError(f"Unknown LLM provider: {provider}")


async def llm_review(cv_text: str, jd_text: str,
                     settings: Optional[UserSettings],
                     provider: Optional[str] = None,
                     model: Optional[str] = None) -> tuple[int, List[LLMSuggestion]]:
    provider, model = resolve_choice(settings, provider, model)
    if provider == "mock":
        return heuristic_score(cv_text, jd_text), heuristic_suggestions(cv_text, jd_text)

    body = f"CV:\n{cv_text}\n\nJOB DESCRIPTION:\n{jd_text}"
    raw = await _chat_completion(provider, settings, SUGGESTION_PROMPT, body,
                                 model=model,
                                 session=_session_id(provider, cv_text, jd_text))
    parsed = _extract_json(raw)
    items = parsed if isinstance(parsed, list) else parsed.get("suggestions", [])
    suggestions = [LLMSuggestion(**s) for s in items]
    score = await llm_score(cv_text, jd_text, settings, provider=provider, model=model)
    return score, suggestions


async def llm_score(cv_text: str, jd_text: str,
                    settings: Optional[UserSettings],
                    provider: Optional[str] = None,
                    model: Optional[str] = None) -> int:
    provider, model = resolve_choice(settings, provider, model)
    if provider == "mock":
        return heuristic_score(cv_text, jd_text)

    body = f"CV:\n{cv_text}\n\nJOB DESCRIPTION:\n{jd_text}"
    raw = await _chat_completion(provider, settings, SCORING_PROMPT, body,
                                 model=model,
                                 session=_session_id(provider, cv_text, jd_text))
    return int(_extract_json(raw)["score"])


async def rewrite_cv(cv_text: str, accepted_changes: List[str], jd_text: str,
                     settings: Optional[UserSettings],
                     provider: Optional[str] = None,
                     model: Optional[str] = None) -> StructuredCV:
    """Rewrite the CV into a structured document. Raises on provider failure so
    the caller can fall back to `document.structure_text`."""
    provider, model = resolve_choice(settings, provider, model)
    if provider == "mock":
        return structure_text(cv_text)

    changes = "\n".join(f"- {c}" for c in accepted_changes) or "(none)"
    body = (
        f"CURRENT CV:\n{cv_text}\n\n"
        f"ACCEPTED CHANGES TO INCORPORATE:\n{changes}\n\n"
        f"JOB DESCRIPTION:\n{jd_text}"
    )
    raw = await _chat_completion(provider, settings, REWRITE_PROMPT, body,
                                 model=model,
                                 session=_session_id(provider, cv_text, jd_text))
    return StructuredCV.model_validate(_extract_json(raw))


async def generate_cover_letter(cv_text: str, jd_text: str,
                                linkedin_url: Optional[str],
                                settings: Optional[UserSettings],
                                provider: Optional[str] = None,
                                model: Optional[str] = None) -> str:
    provider, model = resolve_choice(settings, provider, model)
    if provider == "mock":
        return mock_cover_letter(cv_text, jd_text, linkedin_url)

    body = (
        f"CV:\n{cv_text}\n\nJOB DESCRIPTION:\n{jd_text}\n\n"
        f"LINKEDIN PROFILE: {linkedin_url or '(none provided)'}"
    )
    raw = await _chat_completion(provider, settings, COVER_LETTER_PROMPT, body,
                                 model=model,
                                 session=_session_id(provider, cv_text, jd_text))
    return raw.strip()
