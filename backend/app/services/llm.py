"""LLM service router: Claude / Ollama Cloud / Opencode Zen & Go, with a
deterministic local heuristic fallback so the app runs end-to-end
without any API keys.
"""
import hashlib
import json
import logging
import re
from typing import Callable, List, Optional

import httpx

from app.models import UserSettings
from app.schemas import LLMSuggestion, StructuredCV
from app.services import crypto, keywords, latex, requirements
from app.services.document import structure_text
from app.services.model_catalog import PROVIDERS, stored_base_url

logger = logging.getLogger(__name__)

SUGGESTION_PROMPT = (
    "You are an expert tech recruiter. Compare this CV to this Job Description. "
    "First write 3-5 short sentences of plain-text analysis: which requirements "
    "the CV already covers, which are missing, and what the highest-leverage "
    "changes are. Then, on its own, output a JSON array of suggestions with keys: "
    "`type` (exactly one of ADD, REMOVE, UPDATE), `target_section` (e.g., "
    "Experience, Skills), `original_text` (the existing text being changed; "
    "required for REMOVE and UPDATE), `suggested_text` (the replacement text; "
    "required for ADD and UPDATE, use an empty string for REMOVE), and "
    "`reasoning`. The analysis must come before the JSON. No markdown, no code "
    "fences: prose followed by valid JSON."
)

REQUIREMENTS_PROMPT = (
    "You are an ATS (applicant tracking system) analyst. Read the job "
    "description below and list the concrete requirements a candidate is "
    "assessed on: technologies, languages, frameworks, platforms, tools, cloud "
    "services, methodologies and named domain skills.\n"
    "Rules:\n"
    "- Return 10 to 25 items, most important first.\n"
    "- Each `label` is an ATOMIC TERM of one to four words that a keyword "
    "scanner could search for: a technology, product, protocol, platform, "
    "language, library, methodology or skills-section phrase (\"PostgreSQL\", "
    "\"CI/CD\", \"OpenTelemetry\", \"responsive design\", \"code review\").\n"
    "- Never emit a clause, sentence or framed requirement. Drop the framing: "
    "emit \"Kubernetes\", not \"experience with Kubernetes\"; emit \"cloud\", "
    "not \"knowledge in developing cloud-based applications\". No leading "
    "\"experience with\", \"knowledge of\", \"familiarity with\", "
    "\"understanding of\", \"ability to\".\n"
    "- When the posting names a category instead of specific entries "
    "(\"front-end frameworks\", \"testing frameworks\"), use the category as "
    "the label and put up to six concrete technologies that would satisfy it in "
    "`aliases` (\"react\", \"vue\", \"angular\"). This is what lets a CV that "
    "says \"React\" count as covering \"front-end frameworks\".\n"
    "- Prefer specific terms the posting names (\"PostgreSQL\", \"CI/CD\") over "
    "generic ones (\"databases\", \"teamwork\").\n"
    "- Never emit prose fragments, filler adjectives or soft-skill platitudes as "
    "an item (\"strong\", \"nice\", \"hands-on\", \"experience\", \"deep\").\n"
    "- `label` keeps the posting's casing and punctuation exactly (\"Go\", "
    "\"CI/CD\", \"C++\", \"OpenTelemetry\").\n"
    "- `canonical` is a lowercase canonical term (\"kubernetes\" for "
    "\"Kubernetes\").\n"
    "- `aliases` lists up to six surface forms that should satisfy the item: "
    "other spellings for a technology (\"k8s\", \"postgres\") or the concrete "
    "tools behind a category. Use an empty array when there are none.\n"
    "- `importance` is \"must\" for mandatory requirements and \"nice\" for "
    "anything the posting frames as preferred, optional, bonus or nice-to-have. "
    "Default to \"must\".\n"
    "- `category` is one short word: language, framework, cloud, data, infra, "
    "tooling, practice or domain.\n"
    "- `quote` is the verbatim sentence or bullet from the posting that "
    "justifies the item; never invent text.\n"
    "Return ONLY a JSON array of objects with keys `label`, `canonical`, "
    "`aliases`, `importance`, `category`, `quote`. No markdown, no prose."
)

SCORING_PROMPT = (
    "Evaluate how well this CV matches this Job Description. First write 1-3 "
    "short sentences explaining the strongest matches and the biggest gaps, then "
    "output a JSON object with a single key \"score\" containing an integer from "
    "0 to 100. The analysis must come before the JSON, with no markdown."
)

REWRITE_PROMPT = (
    "You are a senior software engineer who has reviewed thousands of top-tier "
    "(FAANG/high-growth) engineering CVs and edits them for their authors. "
    "Rewrite the CV below into a single-page, ATS-friendly CV tailored to the job "
    "description, applying the standards of an outstanding software engineer CV:\n"
    "- Lead with a 2-3 line professional summary that names the target role and "
    "the candidate's strongest, JD-relevant specialisation.\n"
    "- Experience: reverse-chronological; every role gets 2-4 bullets that start "
    "with a strong action verb, state what was built, the technology and the "
    "measurable outcome. Never invent numbers: quantify only where the CV "
    "provides the facts, otherwise describe impact qualitatively.\n"
    "- Group the skills section into short labelled lines (Languages, "
    "Frameworks, Cloud/Infra, Tooling) using only skills the CV supports.\n"
    "- Keep Education, Projects, Certifications and similar sections concise; "
    "drop anything clearly irrelevant to the role.\n"
    "- Never invent employers, titles, dates, degrees, metrics or technologies.\n"
    "Return ONLY valid JSON with keys: `name` (string or null), `headline` "
    "(string or null), `contact` (array of strings), and `sections` (array of "
    "objects with `heading` (string) and `bullets` (array of strings)). Do not "
    "use markdown."
)

LATEX_PROMPT = (
    "You are a senior software engineer who has reviewed thousands of top-tier "
    "(FAANG/high-growth) engineering CVs and edits them for their authors. "
    "Rewrite the CV below as a single-page, ATS-friendly LaTeX document tailored "
    "to the job description, applying the standards of an outstanding software "
    "engineer CV:\n"
    "- Lead with a 2-3 line professional summary that names the target role and "
    "the candidate's strongest, JD-relevant specialisation.\n"
    "- Experience: reverse-chronological; every role gets 2-4 bullets that start "
    "with a strong action verb, state what was built, the technology and the "
    "measurable outcome. Never invent numbers: quantify only where the CV "
    "provides the facts, otherwise describe impact qualitatively.\n"
    "- Group the skills section into short labelled lines (Languages, "
    "Frameworks, Cloud/Infra, Tooling) using only skills the CV supports.\n"
    "- Keep Education, Projects, Certifications and similar sections concise; "
    "drop anything clearly irrelevant to the role.\n"
    "- Never invent employers, titles, dates, degrees, metrics or technologies. "
    "Use plain ASCII quotes when possible.\n"
    "Output rules: return a complete, compilable LaTeX source file and nothing "
    "else - no markdown fences, no commentary. Keep this exact preamble and use "
    "`\\cvsection{HEADING}` for section headings and `itemize` for bullets:\n"
    "\\documentclass[11pt,a4paper]{article}\n"
    "\\usepackage[T1]{fontenc}\n"
    "\\usepackage[utf8]{inputenc}\n"
    "\\usepackage{lmodern}\n"
    "\\usepackage[margin=1.5cm,top=1.4cm,bottom=1.4cm]{geometry}\n"
    "\\usepackage{enumitem}\n"
    "\\usepackage{titlesec}\n"
    "\\usepackage[hidelinks]{hyperref}\n"
    "\\pagestyle{empty}\n"
    "\\setlength{\\parindent}{0pt}\n"
    "\\newcommand{\\cvsection}[1]{%\n"
    "  \\section*{#1}%\n"
    "  \\vspace{-0.6em}\\titlerule[0.6pt]\\vspace{0.4em}%\n"
    "}\n"
    "\\titlespacing*{\\section}{0pt}{0.75em}{0.25em}\n"
    "\\setlist[itemize]{leftmargin=1.1em,itemsep=0.1em,topsep=0.15em,parsep=0pt}\n"
    "Use no images, icons, colours, tables or multi-column layouts. Escape "
    "LaTeX special characters (& % $ # _ { } ~ ^ \\)."
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
    """Parse the JSON payload that follows the model's prose analysis.

    ``raw_decode`` from the first ``{``/``[`` accepts trailing prose and avoids
    the greedy-regex trap of swallowing two JSON values; the regex stays as a
    fallback for responses with leading noise before the first bracket.
    """
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            return value
        except json.JSONDecodeError:
            continue
    match = re.search(r"\{.*\}|\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON in LLM response")
    return json.loads(match.group(0))


def _parse_suggestions(items) -> List[LLMSuggestion]:
    """Validate LLM suggestions one by one.

    A single malformed object (missing keys, unknown enum value, wrong shape)
    must not fail the whole review, so invalid items are logged and dropped.
    """
    if not isinstance(items, list):
        raise ValueError("LLM response did not contain a suggestions array")
    suggestions: List[LLMSuggestion] = []
    for index, item in enumerate(items):
        try:
            suggestions.append(
                item if isinstance(item, LLMSuggestion)
                else LLMSuggestion.model_validate(item)
            )
        except Exception as exc:
            logger.warning("dropping malformed LLM suggestion %s: %s", index, exc)
    if not suggestions:
        raise ValueError("LLM returned no usable suggestions")
    return suggestions


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


TIMEOUT = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=15.0)


def _request_spec(provider: str, settings: UserSettings, system: str, user: str,
                  model: Optional[str], session: Optional[str],
                  stream: bool) -> tuple[str, dict, dict]:
    """Build (url, headers, json) for the provider's chat endpoint."""
    if provider == "claude":
        base = stored_base_url(settings, provider)
        return (
            f"{base}/v1/messages",
            {
                "x-api-key": crypto.decrypt(settings.claude_key) or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "accept": "text/event-stream" if stream else "application/json",
            },
            {
                "model": model or DEFAULT_MODELS["claude"],
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                **({"stream": True} if stream else {}),
            },
        )

    if provider in ("ollama", "opencode", "opencode_go"):
        stored = getattr(settings, PROVIDERS[provider]["key_field"], None)
        key = crypto.decrypt(stored)
        base = stored_base_url(settings, provider)
        headers = {"Authorization": f"Bearer {key}"}
        # OpenCode Go rejects requests without a stable session id.
        if provider == "opencode_go" and session:
            headers["x-opencode-session"] = session
        return (
            f"{base}/v1/chat/completions",
            headers,
            {
                "model": model or DEFAULT_MODELS[provider],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **({"stream": True} if stream else {}),
            },
        )

    raise ValueError(f"Unknown LLM provider: {provider}")


async def _chat_completion(provider: str, settings: UserSettings,
                           system: str, user: str,
                           model: Optional[str] = None,
                           session: Optional[str] = None) -> str:
    """Non-streaming completion. Async so it never blocks the event loop."""
    url, headers, payload = _request_spec(
        provider, settings, system, user, model, session, stream=False
    )
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    if provider == "claude":
        return "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
    return data["choices"][0]["message"]["content"]


def _stream_handlers(provider: str, on_delta: Callable[[str, str], None]):
    """Return a function handling one SSE JSON chunk for the given provider.

    ``on_delta(text, source)`` is called with ``source`` = ``"output"`` for
    answer text and ``"thinking"`` for reasoning text.
    """

    def handle(chunk: dict) -> None:
        if provider == "claude":
            if chunk.get("type") != "content_block_delta":
                return
            delta = chunk.get("delta") or {}
            if delta.get("type") == "thinking_delta" and delta.get("thinking"):
                on_delta(delta["thinking"], "thinking")
            elif delta.get("type") == "text_delta" and delta.get("text"):
                on_delta(delta["text"], "output")
            return
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("reasoning_content"):
                on_delta(delta["reasoning_content"], "thinking")
            if delta.get("reasoning"):
                on_delta(delta["reasoning"], "thinking")
            if delta.get("content"):
                on_delta(delta["content"], "output")

    return handle


async def _stream_chat_completion(provider: str, settings: UserSettings,
                                  system: str, user: str,
                                  model: Optional[str] = None,
                                  session: Optional[str] = None,
                                  on_delta: Optional[Callable[[str, str], None]] = None
                                  ) -> str:
    """Stream one completion, returning the concatenated **answer** text.

    Reasoning text is forwarded to ``on_delta`` as ``"thinking"`` but is never
    part of the returned string, so JSON parsing sees only the answer.
    """
    url, headers, payload = _request_spec(
        provider, settings, system, user, model, session, stream=True
    )
    collected: List[str] = []

    def forward(text: str, source: str) -> None:
        if source == "output":
            collected.append(text)
        if on_delta:
            on_delta(text, source)

    handle = _stream_handlers(provider, forward)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or line.startswith(":") or line.startswith("event:"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                handle(chunk)

    text = "".join(collected)
    if not text.strip():
        raise ValueError("LLM returned an empty response")
    return text


def _emit(emit: Optional[Callable[[dict], None]], event: dict) -> None:
    if emit is None:
        return
    try:
        emit(event)
    except Exception:  # a broken consumer must never fail the run
        logger.debug("progress emit failed", exc_info=True)


def _stage(emit, stage: str, label: str, text: str = "") -> None:
    _emit(emit, {"type": "stage", "stage": stage, "label": label, "text": text})


def _delta(emit, stage: str, kind: str, text: str) -> None:
    if text:
        _emit(emit, {"type": "delta", "stage": stage, "kind": kind, "text": text})


def _json_splitter(emit, stage: str):
    """Turn one streamed completion into thinking/output deltas.

    Prose before the JSON payload is human-readable ``thinking``; once the
    payload starts the rest is ``output`` (the UI shows a "composing…" state
    instead of raw JSON).
    """
    started = {"value": False}

    def on_delta(text: str, source: str) -> None:
        if source == "thinking":
            _delta(emit, stage, "thinking", text)
            return
        if started["value"]:
            _delta(emit, stage, "output", text)
            return
        positions = [pos for pos in (text.find("{"), text.find("[")) if pos != -1]
        index = min(positions) if positions else -1
        if index == -1:
            _delta(emit, stage, "thinking", text)
            return
        if index:
            _delta(emit, stage, "thinking", text[:index])
        started["value"] = True
        _delta(emit, stage, "output", text[index:])

    return on_delta


async def extract_requirements(jd_text: str,
                              settings: Optional[UserSettings],
                              provider: Optional[str] = None,
                              model: Optional[str] = None,
                              ) -> List[requirements.Requirement]:
    """Extract the JD's real requirements (one call, cached on the review row).

    ``mock`` gets the deterministic heuristic list. Any other failure is raised
    so the caller can decide whether to degrade or surface it.
    """
    provider, model = resolve_choice(settings, provider, model)
    if provider == "mock":
        return requirements.from_heuristic(jd_text)

    raw = await _chat_completion(
        provider, settings, REQUIREMENTS_PROMPT, jd_text, model=model,
        session=_session_id(provider, "requirements", jd_text),
    )
    parsed = _extract_json(raw)
    items = parsed if isinstance(parsed, list) else (
        parsed.get("requirements") if isinstance(parsed, dict) else None
    )
    found = requirements.parse_requirements(items)
    if not found:
        raise ValueError("The model returned no usable requirements")
    return found


async def llm_review_streaming(cv_text: str, jd_text: str,
                               settings: Optional[UserSettings],
                               provider: Optional[str] = None,
                               model: Optional[str] = None,
                               emit: Optional[Callable[[dict], None]] = None
                               ) -> tuple[int, List[LLMSuggestion],
                                          List[requirements.Requirement]]:
    """Run the review pipeline, narrating real progress as it goes.

    Emits ``stage`` events for jd/cv/requirements/suggestions/score plus
    ``delta`` events carrying the model's own streamed text. ``emit=None`` is
    the non-streaming path used by callers that only need the result.

    The extracted requirement list is returned so the caller can persist it on
    the job description; matching stays deterministic.
    """
    provider, model = resolve_choice(settings, provider, model)

    _stage(emit, "jd", "Reading the job description",
           f"{len(jd_text):,} characters")
    _stage(emit, "cv", "Scanning your CV", f"{len(cv_text):,} characters")
    _stage(emit, "requirements", "Extracting ATS requirements",
           "local heuristic" if provider == "mock"
           else f"{provider} - {model or 'provider default'}")
    try:
        reqs = await extract_requirements(jd_text, settings, provider, model)
    except Exception as exc:  # a keyword list must never sink the whole review
        logger.warning("requirement extraction failed, using heuristic: %s", exc)
        reqs = requirements.from_heuristic(jd_text)
    cov = requirements.match_requirements(cv_text, reqs)
    _delta(emit, "requirements", "thinking",
           f"{len(reqs)} requirements identified"
           + (f": {', '.join(r.label for r in reqs[:12])}." if reqs else ".")
           + "\n"
           + f"Matched {len(cov['matched'])} of {len(reqs)} "
           f"({cov['coverage']}% weighted coverage).\n"
           + (f"Missing: {', '.join(cov['missing_labels'][:12])}.\n"
              if cov["missing"] else "Every requirement already appears.\n"))

    if provider == "mock":
        _stage(emit, "suggestions", "Drafting suggestions", "local heuristic")
        suggestions = heuristic_suggestions(cv_text, jd_text)
        for suggestion in suggestions:
            _delta(emit, "suggestions", "thinking",
                   f"- {suggestion.type} {suggestion.target_section or 'CV'}: "
                   f"{suggestion.reasoning or suggestion.suggested_text}\n")
        score = heuristic_score(cv_text, jd_text)
        _stage(emit, "score", "Scoring the match", "local heuristic")
        _delta(emit, "score", "thinking",
               f"ATS keyword coverage {cov['coverage']}% -> match score "
               f"{score}.\n")
        return score, suggestions, reqs

    body = f"CV:\n{cv_text}\n\nJOB DESCRIPTION:\n{jd_text}"
    _stage(emit, "suggestions", "Drafting suggestions",
           f"{provider} · {model or 'provider default'}")
    raw = await _stream_chat_completion(
        provider, settings, SUGGESTION_PROMPT, body,
        model=model, session=_session_id(provider, cv_text, jd_text),
        on_delta=_json_splitter(emit, "suggestions"),
    )
    parsed = _extract_json(raw)
    items = parsed if isinstance(parsed, list) else parsed.get("suggestions", [])
    suggestions = _parse_suggestions(items)

    _stage(emit, "score", "Scoring the match",
           f"{len(suggestions)} suggestions drafted")
    score_raw = await _stream_chat_completion(
        provider, settings, SCORING_PROMPT, body,
        model=model, session=_session_id(provider, cv_text, jd_text),
        on_delta=_json_splitter(emit, "score"),
    )
    return int(_extract_json(score_raw)["score"]), suggestions, reqs


async def llm_review(cv_text: str, jd_text: str,
                     settings: Optional[UserSettings],
                     provider: Optional[str] = None,
                     model: Optional[str] = None
                     ) -> tuple[int, List[LLMSuggestion],
                                List[requirements.Requirement]]:
    """Non-streaming wrapper around the one review code path."""
    return await llm_review_streaming(
        cv_text, jd_text, settings, provider=provider, model=model, emit=None
    )


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


async def rewrite_cv_latex(cv_text: str, accepted_changes: List[str], jd_text: str,
                           settings: Optional[UserSettings],
                           provider: Optional[str] = None,
                           model: Optional[str] = None) -> str:
    """Rewrite the CV as LaTeX source. Raises when the provider fails or returns
    something that is not a self-contained document, so the caller can fall back
    to `latex.render_document`."""
    provider, model = resolve_choice(settings, provider, model)
    if provider == "mock":
        return latex.render_document(structure_text(cv_text))

    changes = "\n".join(f"- {c}" for c in accepted_changes) or "(none)"
    body = (
        f"CURRENT CV:\n{cv_text}\n\n"
        f"ACCEPTED CHANGES TO INCORPORATE:\n{changes}\n\n"
        f"JOB DESCRIPTION:\n{jd_text}"
    )
    raw = await _chat_completion(provider, settings, LATEX_PROMPT, body,
                                 model=model,
                                 session=_session_id(provider, cv_text, jd_text))
    source = latex.sanitize_latex(raw)
    if not latex.is_valid_latex(source):
        raise ValueError("LLM did not return a usable LaTeX document")
    return source


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
