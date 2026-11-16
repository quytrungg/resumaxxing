import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    BaseCV, CVReview, JobDescription, ReviewStatus, ScoreEvent, Suggestion,
    SuggestionStatus, UserSettings,
)
from app.schemas import (
    CoverLetterOut, CoverLetterUpdate, ReviewCreate, ReviewOut, ScoreHistoryOut,
    ScoreOut, StructuredCV, SuggestionOut, SuggestionStatusOut,
    SuggestionStatusUpdate,
)
from app.services import export, keywords, llm
from app.services import jd as jd_meta
from app.services.document import structure_text
from app.services.scrape import fetch_jd
from app.routers.settings import get_default_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
LLM_PROVIDERS = ("mock", "claude", "ollama", "opencode", "opencode_go")


def _serialize(review: CVReview) -> ReviewOut:
    job = review.job_description
    cov = keywords.coverage(
        _pending_cv_text(review), job.raw_text
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
        matched_keywords=cov["matched"],
        missing_keywords=cov["missing"],
        score_history=[ScoreHistoryOut.model_validate(e) for e in review.score_events],
        final_document=(
            StructuredCV.model_validate(review.final_document)
            if review.final_document else None
        ),
        cover_letter=review.cover_letter,
        llm_provider=review.llm_provider,
        llm_model=review.llm_model,
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


def _file_response(data: bytes, media: str, name: str) -> Response:
    return Response(
        content=data, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("", response_model=ReviewOut)
async def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    user = get_default_user(db)
    cv = (db.query(BaseCV).filter(BaseCV.user_id == user.id)
          .order_by(BaseCV.uploaded_at.desc()).first())
    if not cv:
        raise HTTPException(status_code=400, detail="Upload a base CV first")

    if payload.jd_url:
        try:
            jd_text, page_title = fetch_jd(payload.jd_url)
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
    try:
        score, suggestions = await llm.llm_review(
            cv.parsed_text, jd_text, settings, provider=provider, model=model
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")

    jd = JobDescription(
        user_id=user.id, source_url=payload.jd_url, raw_text=jd_text,
        title=jd_title, company=jd_company,
    )
    db.add(jd)
    db.flush()
    review = CVReview(
        user_id=user.id, base_cv_id=cv.id, job_description_id=jd.id,
        current_score=score, status=ReviewStatus.draft,
        llm_provider=provider, llm_model=model,
    )
    db.add(review)
    db.flush()
    for s in suggestions:
        db.add(Suggestion(
            cv_review_id=review.id, type=s.type, target_section=s.target_section,
            original_text=s.original_text, suggested_text=s.suggested_text,
            reasoning=s.reasoning,
        ))
    db.add(ScoreEvent(cv_review_id=review.id, score=score, reason="initial review"))
    db.commit()
    db.refresh(review)
    return _serialize(review)


@router.get("", response_model=list[ReviewOut])
def list_reviews(db: Session = Depends(get_db)):
    user = get_default_user(db)
    reviews = (db.query(CVReview).filter(CVReview.user_id == user.id)
               .order_by(CVReview.created_at.desc()).all())
    return [_serialize(r) for r in reviews]


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(review_id: int, db: Session = Depends(get_db)):
    return _serialize(_get_review(db, review_id))


@router.patch("/{review_id}/suggestions/{suggestion_id}",
              response_model=SuggestionStatusOut)
def update_suggestion(review_id: int, suggestion_id: int,
                      payload: SuggestionStatusUpdate,
                      db: Session = Depends(get_db)):
    review = _get_review(db, review_id)
    suggestion = db.get(Suggestion, suggestion_id)
    if not suggestion or suggestion.cv_review_id != review.id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    suggestion.status = payload.status
    # Any decision invalidates a previously stored polished document.
    review.final_document = None
    db.commit()
    return SuggestionStatusOut(status=suggestion.status)


@router.post("/{review_id}/rescore", response_model=ScoreOut)
async def rescore_review(review_id: int, db: Session = Depends(get_db)):
    """Re-score from the current accepted/rejected/pending set (one LLM call)."""
    review = _get_review(db, review_id)
    pending_text = _pending_cv_text(review)
    jd_text = review.job_description.raw_text
    settings = _get_user_settings(db, review.user_id)
    cov = keywords.coverage(pending_text, jd_text)
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
        matched_keywords=cov["matched"],
        missing_keywords=cov["missing"],
        history_entry=ScoreHistoryOut.model_validate(event),
    )


@router.post("/{review_id}/finalize")
async def finalize_review(review_id: int, format: str = "docx",
                          mode: str = "polished",
                          db: Session = Depends(get_db)):
    if mode not in ("polished", "quick"):
        raise HTTPException(status_code=400, detail="mode must be 'polished' or 'quick'")
    review = _get_review(db, review_id)
    merged_text = export.build_final_text(
        review.base_cv.parsed_text, review.suggestions
    )

    if mode == "quick":
        review.status = ReviewStatus.finalized
        db.commit()
        if format == "pdf":
            return _file_response(
                export.to_pdf_bytes(merged_text), "application/pdf",
                f"cv_optimized_{review_id}.pdf",
            )
        return _file_response(
            export.to_docx_bytes(merged_text), DOCX_MEDIA,
            f"cv_optimized_{review_id}.docx",
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
    review.status = ReviewStatus.finalized
    db.commit()

    doc = StructuredCV.model_validate(review.final_document)
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
