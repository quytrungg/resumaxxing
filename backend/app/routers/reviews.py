import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import (
    BaseCV, CVReview, JobDescription, ReviewStatus, ScoreEvent, Suggestion,
    SuggestionStatus, SuggestionType, UserSettings,
)
from app.schemas import (
    CoverLetterOut, CoverLetterUpdate, RequirementOut, ReviewCreate, ReviewOut,
    ScoreHistoryOut, ScoreOut, StructuredCV, SuggestionOut, SuggestionStatusOut,
    SuggestionStatusUpdate, SuggestionTextUpdate,
)
from app.services import export, latex, llm, progress, requirements
from app.services import jd as jd_meta
from app.services.document import structure_text
from app.services.scrape import fetch_jd
from app.routers.settings import get_default_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEX_MEDIA = "application/x-tex"
LLM_PROVIDERS = ("mock", "claude", "ollama", "opencode", "opencode_go")
INTERRUPTED_ERROR = "Interrupted (the backend restarted while this review ran)"


def _requirements_for(job: JobDescription | None) -> list:
    """Stored LLM extraction, or the deterministic fallback for older rows."""
    if job is None:
        return []
    stored = job.jd_requirements
    if stored:
        parsed = requirements.parse_requirements(stored)
        if parsed:
            return parsed
    return requirements.from_heuristic(job.raw_text)


def _serialize(review: CVReview) -> ReviewOut:
    job = review.job_description
    cov = requirements.match_requirements(
        _pending_cv_text(review), _requirements_for(job)
    )
    jd_title = jd_company = None
    if job is not None:
        # Older rows predate the stored title; resolve them lazily.
        jd_title = (
            job.title
            or jd_meta.extract_title_from_text(job.raw_text)
            or jd_meta.title_from_url(job.source_url)
        )
        jd_company = job.company or jd_meta.extract_company_from_text(job.raw_text)
    return ReviewOut(
        id=review.id,
        current_score=review.current_score,
        status=review.status,
        created_at=review.created_at,
        suggestions=[SuggestionOut.model_validate(s) for s in review.suggestions],
        jd_text=job.raw_text if job else None,
        jd_title=jd_title,
        jd_company=jd_company,
        cv_preview=review.base_cv.parsed_text if review.base_cv else None,
        keyword_coverage=cov["coverage"],
        must_have_coverage=cov["must_have_coverage"],
        nice_to_have_coverage=cov["nice_to_have_coverage"],
        requirements=[RequirementOut.model_validate(r) for r in cov["requirements"]],
        matched_keywords=cov["matched_labels"],
        missing_keywords=cov["missing_labels"],
        score_history=[ScoreHistoryOut.model_validate(e) for e in review.score_events],
        final_document=(
            StructuredCV.model_validate(review.final_document)
            if review.final_document else None
        ),
        cover_letter=review.cover_letter,
        llm_provider=review.llm_provider,
        llm_model=review.llm_model,
        run_state=review.run_state,
        run_error=review.run_error,
    )


def _get_user_settings(db: Session, user_id: int):
    return db.query(UserSettings).filter(UserSettings.user_id == user_id).first()


def _pending_cv_text(review: CVReview) -> str:
    """CV with accepted changes applied and rejected/pending ignored."""
    accepted = [s for s in review.suggestions if s.status == SuggestionStatus.ACCEPTED]
    return export.build_final_text(review.base_cv.parsed_text, accepted)


def _get_review(db: Session, review_id: int) -> CVReview:
    review = db.get(CVReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


def _reconcile(reviews: list[CVReview], db: Session) -> None:
    """Fail runs whose in-memory state vanished (e.g. a backend restart).

    Without this a review could sit on `running` forever. Only rows that claim
    to be running *and* have no live broker entry are touched.
    """
    changed = False
    for review in reviews:
        if review.run_state == "running" and not progress.active(review.id):
            review.run_state = "failed"
            review.run_error = INTERRUPTED_ERROR
            changed = True
    if changed:
        db.commit()


def _file_response(data: bytes, media: str, name: str) -> Response:
    return Response(
        content=data, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


async def _run_review(review_id: int, cv_text: str, jd_text: str,
                      provider: str, model: str | None) -> None:
    """Background LLM work for a freshly created review.

    Owns its DB session, writes either the full result or a failure in one
    commit, and always closes the in-memory run so subscribers stop waiting.
    """
    db = SessionLocal()
    try:
        review = db.get(CVReview, review_id)
        if review is None:
            progress.emit(review_id, {"type": "error", "message": "Review not found"})
            return
        settings = _get_user_settings(db, review.user_id)
        try:
            score, suggestions, reqs = await llm.llm_review_streaming(
                cv_text, jd_text, settings, provider=provider, model=model,
                emit=lambda event: progress.emit(review_id, event),
            )
            if review.job_description is not None:
                review.job_description.jd_requirements = [
                    r.model_dump(exclude={"matched"}) for r in reqs
                ]
            for suggestion in suggestions:
                db.add(Suggestion(
                    cv_review_id=review.id, type=suggestion.type,
                    target_section=suggestion.target_section,
                    original_text=suggestion.original_text,
                    suggested_text=suggestion.suggested_text,
                    reasoning=suggestion.reasoning,
                ))
            review.current_score = score
            review.run_state = "complete"
            review.run_error = None
            db.add(ScoreEvent(cv_review_id=review.id, score=score,
                              reason="initial review"))
            db.commit()
        except Exception as exc:  # provider failure or a bad payload/DB write
            logger.exception("review run %s failed", review_id)
            db.rollback()
            review = db.get(CVReview, review_id)
            if review is not None:
                review.run_state = "failed"
                review.run_error = (str(exc) or exc.__class__.__name__)[:1000]
                db.commit()
            progress.emit(review_id, {
                "type": "error",
                "message": str(exc) or "The LLM request failed",
            })
            return
        progress.emit(review_id, {"type": "done", "score": score})
    finally:
        progress.finish_run(review_id)
        db.close()


@router.post("", response_model=ReviewOut, status_code=202)
async def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    user = get_default_user(db)
    cv = (db.query(BaseCV).filter(BaseCV.user_id == user.id)
          .order_by(BaseCV.uploaded_at.desc()).first())
    if not cv:
        raise HTTPException(status_code=400, detail="Upload a base CV first")

    if payload.jd_url:
        try:
            # Scrape in a worker thread: the sync client must not block the loop.
            jd_text, page_title = await asyncio.to_thread(fetch_jd, payload.jd_url)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not fetch URL: {e}")
    elif payload.jd_text:
        jd_text = payload.jd_text
        page_title = None
    else:
        raise HTTPException(status_code=400, detail="Provide jd_text or jd_url")

    jd_title = (
        page_title
        or jd_meta.extract_title_from_text(jd_text)
        or (jd_meta.title_from_url(payload.jd_url) if payload.jd_url else None)
    )
    jd_company = jd_meta.extract_company_from_text(jd_text)

    settings = _get_user_settings(db, user.id)
    stored_provider = settings.llm_provider if settings is not None else None
    provider = payload.llm_provider or (
        str(stored_provider) if stored_provider is not None else "mock"
    )
    if provider not in LLM_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown LLM provider: {provider}")
    model = llm.resolve_choice(settings, provider, payload.llm_model)[1]

    jd = JobDescription(
        user_id=user.id, source_url=payload.jd_url, raw_text=jd_text,
        title=jd_title, company=jd_company,
    )
    db.add(jd)
    db.flush()
    review = CVReview(
        user_id=user.id, base_cv_id=cv.id, job_description_id=jd.id,
        current_score=0, status=ReviewStatus.draft,
        llm_provider=provider, llm_model=model, run_state="running",
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    # Open the run before returning so an immediate SSE connect always sees it.
    progress.open_run(review.id)
    task = asyncio.create_task(
        _run_review(review.id, cv.parsed_text, jd_text, provider, model)
    )
    progress.register_task(review.id, task)
    return _serialize(review)


@router.get("", response_model=list[ReviewOut])
def list_reviews(db: Session = Depends(get_db)):
    user = get_default_user(db)
    reviews = (db.query(CVReview).filter(CVReview.user_id == user.id)
               .order_by(CVReview.created_at.desc()).all())
    _reconcile(reviews, db)
    return [_serialize(r) for r in reviews]


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(review_id: int, db: Session = Depends(get_db)):
    review = _get_review(db, review_id)
    _reconcile([review], db)
    return _serialize(review)


def _sse_frame(event: dict) -> str:
    frame = ""
    if event.get("seq") is not None:
        frame += f"id: {event['seq']}\n"
    return frame + f"data: {json.dumps(event, default=str)}\n\n"


def _terminal_event(review_id: int, run_state: str, run_error: str | None,
                    score: int) -> dict:
    if run_state == "failed":
        return {"type": "error", "message": run_error or "Review failed"}
    return {"type": "done", "score": score}


@router.get("/{review_id}/events")
async def review_events(review_id: int, request: Request):
    """Server-sent events for a running review (replay + live tail).

    Uses a short-lived session for the state check so a long-lived stream never
    holds a pooled DB connection.
    """
    db = SessionLocal()
    try:
        review = db.get(CVReview, review_id)
        if review is None:
            raise HTTPException(status_code=404, detail="Review not found")
        run_state, run_error, score = (
            review.run_state, review.run_error, review.current_score,
        )
        if run_state == "running" and not progress.active(review_id):
            review.run_state = "failed"
            review.run_error = INTERRUPTED_ERROR
            db.commit()
            run_state, run_error = "failed", INTERRUPTED_ERROR
    finally:
        db.close()

    async def stream():
        if run_state != "running":
            yield _sse_frame(_terminal_event(review_id, run_state, run_error, score))
            return

        run = progress.get_run(review_id)
        queue = progress.subscribe(review_id)
        try:
            for event in progress.snapshot(review_id):
                yield _sse_frame(event)
                if event.get("type") in progress.TERMINAL_TYPES:
                    return

            if run is None or run.finished or queue is None:
                # Finished between the state read and subscribing, or cancelled.
                state = SessionLocal()
                try:
                    fresh = state.get(CVReview, review_id)
                    final_state = fresh.run_state if fresh else "failed"
                    final_error = fresh.run_error if fresh else INTERRUPTED_ERROR
                    final_score = fresh.current_score if fresh else 0
                    if fresh is not None and final_state == "running":
                        fresh.run_state = "failed"
                        fresh.run_error = INTERRUPTED_ERROR
                        state.commit()
                        final_state, final_error = "failed", INTERRUPTED_ERROR
                finally:
                    state.close()
                yield _sse_frame(
                    _terminal_event(review_id, final_state, final_error, final_score)
                )
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if event is None:
                    yield _sse_frame({
                        "type": "error", "message": "Review run ended unexpectedly",
                    })
                    return
                yield _sse_frame(event)
                if event.get("type") in progress.TERMINAL_TYPES:
                    return
        finally:
            if queue is not None:
                progress.unsubscribe(review_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _get_suggestion(db: Session, review: CVReview,
                    suggestion_id: int) -> Suggestion:
    suggestion = db.get(Suggestion, suggestion_id)
    if not suggestion or suggestion.cv_review_id != review.id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return suggestion


def _invalidate_outputs(review: CVReview) -> None:
    """Any change to a suggestion's text or status stales stored downloads."""
    review.final_document = None
    review.final_latex = None


@router.patch("/{review_id}/suggestions/{suggestion_id}",
              response_model=SuggestionStatusOut)
def update_suggestion(review_id: int, suggestion_id: int,
                      payload: SuggestionStatusUpdate,
                      db: Session = Depends(get_db)):
    review = _get_review(db, review_id)
    suggestion = _get_suggestion(db, review, suggestion_id)
    suggestion.status = payload.status
    _invalidate_outputs(review)
    db.commit()
    return SuggestionStatusOut(status=suggestion.status)


def _require_editable(suggestion: Suggestion) -> None:
    if suggestion.type not in (SuggestionType.ADD, SuggestionType.UPDATE):
        raise HTTPException(
            status_code=400,
            detail="This suggestion type has no replacement text to edit",
        )


@router.put("/{review_id}/suggestions/{suggestion_id}/text",
            response_model=SuggestionOut)
def update_suggestion_text(review_id: int, suggestion_id: int,
                           payload: SuggestionTextUpdate,
                           db: Session = Depends(get_db)):
    """Save the user's own wording for an ADD/UPDATE suggestion.

    Status is untouched (accepting stays a separate, explicit decision) and no
    LLM call happens; the stored outputs are invalidated because the text they
    were built from is now different.
    """
    review = _get_review(db, review_id)
    suggestion = _get_suggestion(db, review, suggestion_id)
    _require_editable(suggestion)
    # Capture the AI wording once, so later edits can still reset to it.
    if suggestion.original_suggested_text is None:
        suggestion.original_suggested_text = suggestion.suggested_text
    suggestion.suggested_text = payload.suggested_text
    _invalidate_outputs(review)
    db.commit()
    db.refresh(suggestion)
    return SuggestionOut.model_validate(suggestion)


@router.delete("/{review_id}/suggestions/{suggestion_id}/text",
               response_model=SuggestionOut)
def reset_suggestion_text(review_id: int, suggestion_id: int,
                          db: Session = Depends(get_db)):
    """Drop the user's edit and restore the first AI wording."""
    review = _get_review(db, review_id)
    suggestion = _get_suggestion(db, review, suggestion_id)
    if suggestion.original_suggested_text is None:
        raise HTTPException(status_code=400,
                            detail="This suggestion has no edited text to reset")
    suggestion.suggested_text = suggestion.original_suggested_text
    suggestion.original_suggested_text = None
    _invalidate_outputs(review)
    db.commit()
    db.refresh(suggestion)
    return SuggestionOut.model_validate(suggestion)



@router.post("/{review_id}/rescore", response_model=ScoreOut)
async def rescore_review(review_id: int, db: Session = Depends(get_db)):
    """Re-score from the current accepted/rejected/pending set (one LLM call)."""
    review = _get_review(db, review_id)
    pending_text = _pending_cv_text(review)
    jd_text = review.job_description.raw_text
    settings = _get_user_settings(db, review.user_id)
    cov = requirements.match_requirements(
        pending_text, _requirements_for(review.job_description)
    )
    try:
        new_score = await llm.llm_score(
            pending_text, jd_text, settings,
            provider=review.llm_provider, model=review.llm_model,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")
    review.current_score = new_score

    counts = {status: 0 for status in SuggestionStatus}
    for suggestion in review.suggestions:
        counts[suggestion.status] += 1
    reason = (
        f"re-evaluated ({counts[SuggestionStatus.ACCEPTED]} accepted, "
        f"{counts[SuggestionStatus.REJECTED]} rejected, "
        f"{counts[SuggestionStatus.PENDING]} pending)"
    )
    event = ScoreEvent(cv_review_id=review.id, score=new_score, reason=reason)
    db.add(event)
    db.commit()
    db.refresh(event)
    return ScoreOut(
        score=new_score,
        keyword_coverage=cov["coverage"],
        must_have_coverage=cov["must_have_coverage"],
        nice_to_have_coverage=cov["nice_to_have_coverage"],
        requirements=[RequirementOut.model_validate(r) for r in cov["requirements"]],
        matched_keywords=cov["matched_labels"],
        missing_keywords=cov["missing_labels"],
        history_entry=ScoreHistoryOut.model_validate(event),
    )


@router.post("/{review_id}/requirements/refresh", response_model=ReviewOut)
async def refresh_requirements(review_id: int, db: Session = Depends(get_db)):
    """Re-extract the JD requirement list (one LLM call) and return the review."""
    review = _get_review(db, review_id)
    settings = _get_user_settings(db, review.user_id)
    try:
        reqs = await llm.extract_requirements(
            review.job_description.raw_text, settings,
            provider=review.llm_provider, model=review.llm_model,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Requirement extraction failed: {exc}"
        )
    review.job_description.jd_requirements = [
        r.model_dump(exclude={"matched"}) for r in reqs
    ]
    db.commit()
    db.refresh(review)
    return _serialize(review)


@router.post("/{review_id}/finalize")
async def finalize_review(review_id: int, format: str = "docx",
                          db: Session = Depends(get_db)):
    if format not in ("docx", "pdf", "tex"):
        raise HTTPException(status_code=400,
                            detail="format must be 'docx', 'pdf' or 'tex'")
    review = _get_review(db, review_id)
    merged_text = export.build_final_text(
        review.base_cv.parsed_text, review.suggestions
    )

    if format == "tex":
        if not review.final_latex:
            settings = _get_user_settings(db, review.user_id)
            try:
                review.final_latex = await llm.rewrite_cv_latex(
                    merged_text,
                    export.accepted_change_texts(review.suggestions),
                    review.job_description.raw_text,
                    settings,
                    provider=review.llm_provider,
                    model=review.llm_model,
                )
            except Exception as exc:  # provider failure -> deterministic render
                logger.warning("LaTeX rewrite failed, using template: %s", exc)
                fallback = (
                    StructuredCV.model_validate(review.final_document)
                    if review.final_document else structure_text(merged_text)
                )
                review.final_latex = latex.render_document(fallback)
        review.status = ReviewStatus.finalized
        db.commit()
        return _file_response(
            review.final_latex.encode("utf-8"), TEX_MEDIA,
            f"cv_optimized_{review_id}.tex",
        )

    if not review.final_document:
        settings = _get_user_settings(db, review.user_id)
        try:
            doc = await llm.rewrite_cv(
                merged_text,
                export.accepted_change_texts(review.suggestions),
                review.job_description.raw_text,
                settings,
                provider=review.llm_provider,
                model=review.llm_model,
            )
        except Exception as exc:  # provider failure -> deterministic structure
            logger.warning("CV rewrite failed, using structured fallback: %s", exc)
            doc = structure_text(merged_text)
        if not doc.sections:
            doc = structure_text(merged_text)
        review.final_document = doc.model_dump()
    doc = StructuredCV.model_validate(review.final_document)
    review.status = ReviewStatus.finalized
    db.commit()

    if format == "pdf":
        return _file_response(
            export.to_pdf_bytes_structured(doc), "application/pdf",
            f"cv_optimized_{review_id}.pdf",
        )
    return _file_response(
        export.to_docx_bytes_structured(doc), DOCX_MEDIA,
        f"cv_optimized_{review_id}.docx",
    )


@router.post("/{review_id}/cover-letter", response_model=CoverLetterOut)
async def generate_cover_letter(review_id: int, db: Session = Depends(get_db)):
    review = _get_review(db, review_id)
    if review.status != ReviewStatus.finalized:
        raise HTTPException(status_code=409,
                            detail="Finalize the CV before generating a cover letter")
    settings = _get_user_settings(db, review.user_id)
    text = await llm.generate_cover_letter(
        _pending_cv_text(review),
        review.job_description.raw_text,
        settings.linkedin_url if settings else None,
        settings,
        provider=review.llm_provider,
        model=review.llm_model,
    )
    review.cover_letter = text
    db.commit()
    return CoverLetterOut(text=text)


@router.put("/{review_id}/cover-letter", response_model=CoverLetterOut)
def save_cover_letter(review_id: int, payload: CoverLetterUpdate,
                      db: Session = Depends(get_db)):
    review = _get_review(db, review_id)
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Cover letter text is empty")
    review.cover_letter = payload.text
    db.commit()
    return CoverLetterOut(text=payload.text)


@router.post("/{review_id}/cover-letter/export")
def export_cover_letter(review_id: int, format: str = "docx",
                        db: Session = Depends(get_db)):
    review = _get_review(db, review_id)
    if not review.cover_letter:
        raise HTTPException(status_code=404, detail="No cover letter generated yet")
    if format == "pdf":
        return _file_response(
            export.letter_to_pdf_bytes(review.cover_letter), "application/pdf",
            f"cover_letter_{review_id}.pdf",
        )
    return _file_response(
        export.letter_to_docx_bytes(review.cover_letter), DOCX_MEDIA,
        f"cover_letter_{review_id}.docx",
    )
