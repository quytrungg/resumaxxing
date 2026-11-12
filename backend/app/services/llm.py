"""LLM service router: Claude / Ollama Cloud / Opencode Cloud, with a
deterministic local heuristic fallback so the app runs end-to-end
without any API keys.
"""
import json
import re
from typing import List, Optional

import httpx

from app.models import UserSettings
from app.schemas import LLMSuggestion

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


def _keywords(text: str, top_n: int = 25) -> List[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z+#.]{2,}", text.lower())
    freq = {}
    for w in words:
        if w not in STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:top_n]]


def heuristic_score(cv_text: str, jd_text: str) -> int:
    jd_kws = set(_keywords(jd_text, 30))
    if not jd_kws:
        return 50
    cv_lower = cv_text.lower()
    hit = sum(1 for k in jd_kws if k in cv_lower)
    return round(100 * hit / len(jd_kws))


def heuristic_suggestions(cv_text: str, jd_text: str) -> List[LLMSuggestion]:
    jd_kws = _keywords(jd_text, 20)
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


async def _chat_completion(provider: str, settings: UserSettings,
                           system: str, user: str) -> str:
    if provider == "claude":
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.claude_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "accept": "application/json",
            },
            json={
                "model": "claude-sonnet-4-5",
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

    openai_style = {
        # Ollama Cloud exposes an OpenAI-compatible /v1 API
        "ollama": "https://ollama.com/v1",
        # Opencode Zen is OpenAI-compatible
        "opencode": "https://opencode.ai/zen/v1",
    }
    if provider in openai_style:
        key = settings.ollama_key if provider == "ollama" else settings.opencode_key
        resp = httpx.post(
            f"{openai_style[provider]}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "gpt-oss:120b-cloud" if provider == "ollama" else "grok-code",
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
                     settings: Optional[UserSettings]) -> tuple[int, List[LLMSuggestion]]:
    provider = settings.llm_provider if settings else "mock"
    if provider == "mock":
        return heuristic_score(cv_text, jd_text), heuristic_suggestions(cv_text, jd_text)

    body = f"CV:\n{cv_text}\n\nJOB DESCRIPTION:\n{jd_text}"
    raw = await _chat_completion(provider, settings, SUGGESTION_PROMPT, body)
    parsed = _extract_json(raw)
    items = parsed if isinstance(parsed, list) else parsed.get("suggestions", [])
    suggestions = [LLMSuggestion(**s) for s in items]
    score = await llm_score(cv_text, jd_text, settings)
    return score, suggestions


async def llm_score(cv_text: str, jd_text: str,
                    settings: Optional[UserSettings]) -> int:
    provider = settings.llm_provider if settings else "mock"
    if provider == "mock":
        return heuristic_score(cv_text, jd_text)

    body = f"CV:\n{cv_text}\n\nJOB DESCRIPTION:\n{jd_text}"
    raw = await _chat_completion(provider, settings, SCORING_PROMPT, body)
    return int(_extract_json(raw)["score"])
