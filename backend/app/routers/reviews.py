from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
import httpx
from bs4 import BeautifulSoup

from app.database import get_db
from app.models import (
    BaseCV, CVReview, JobDescription, ReviewStatus, Suggestion,
    SuggestionStatus, UserSettings,
)
from app.schemas import (
    ReviewCreate, ReviewOut, ScoreOut, SuggestionOut, SuggestionStatusUpdate,
)
from app.services import export, llm
from app.routers.settings import get_default_user

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def _scrape_url(url: str) -> str:
    resp = httpx.get(url, follow_redirects=True, timeout=20,
                     headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def _serialize(review: CVReview) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        current_score=review.current_score,
        status=review.status,
        created_at=review.created_at,
        suggestions=[SuggestionOut.model_validate(s) for s in review.suggestions],
        jd_text=review.job_description.raw_text if review.job_description else None,
        cv_preview=review.base_cv.parsed_text if review.base_cv else None,
    )


def _get_user_settings(db: Session, user_id: int):
    return db.query(UserSettings).filter(UserSettings.user_id == user_id).first()


def _pending_cv_text(review: CVReview) -> str:
    """CV with accepted changes applied and rejected/pending ignored."""
    accepted = [s for s in review.suggestions if s.status == SuggestionStatus.ACCEPTED]
    return export.build_final_text(review.base_cv.parsed_text, accepted)


@router.post("", response_model=ReviewOut)
async def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    user = get_default_user(db)
    cv = (db.query(BaseCV).filter(BaseCV.user_id == user.id)
          .order_by(BaseCV.uploaded_at.desc()).first())
    if not cv:
        raise HTTPException(status_code=400, detail="Upload a base CV first")

    if payload.jd_url:
        try:
            jd_text = _scrape_url(payload.jd_url)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not fetch URL: {e}")
    elif payload.jd_text:
        jd_text = payload.jd_text
    else:
        raise HTTPException(status_code=400, detail="Provide jd_text or jd_url")

    settings = _get_user_settings(db, user.id)
    score, suggestions = await llm.llm_review(cv.parsed_text, jd_text, settings)

    jd = JobDescription(user_id=user.id, source_url=payload.jd_url, raw_text=jd_text)
    db.add(jd)
    db.flush()
    review = CVReview(
        user_id=user.id, base_cv_id=cv.id, job_description_id=jd.id,
        current_score=score, status=ReviewStatus.draft,
    )
    db.add(review)
    db.flush()
    for s in suggestions:
        db.add(Suggestion(
            cv_review_id=review.id, type=s.type, target_section=s.target_section,
            original_text=s.original_text, suggested_text=s.suggested_text,
            reasoning=s.reasoning,
        ))
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
    review = db.get(CVReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return _serialize(review)


@router.patch("/{review_id}/suggestions/{suggestion_id}", response_model=ScoreOut)
async def update_suggestion(review_id: int, suggestion_id: int,
                            payload: SuggestionStatusUpdate,
                            db: Session = Depends(get_db)):
    review = db.get(CVReview, review_id)
    suggestion = db.get(Suggestion, suggestion_id)
    if not review or not suggestion or suggestion.cv_review_id != review.id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    suggestion.status = payload.status
    db.flush()

    settings = _get_user_settings(db, review.user_id)
    new_score = await llm.llm_score(
        _pending_cv_text(review), review.job_description.raw_text, settings
    )
    review.current_score = new_score
    db.commit()
    return ScoreOut(score=new_score)


@router.post("/{review_id}/finalize")
async def finalize_review(review_id: int, format: str = "docx",
                          db: Session = Depends(get_db)):
    review = db.get(CVReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    reviews_final_text = export.build_final_text(
        review.base_cv.parsed_text, review.suggestions
    )
    review.status = ReviewStatus.finalized
    db.commit()

    if format == "pdf":
        data = export.to_pdf_bytes(reviews_final_text)
        media = "application/pdf"
        name = f"cv_optimized_{review_id}.pdf"
    else:
        data = export.to_docx_bytes(reviews_final_text)
        media = ("application/vnd.openxmlformats-officedocument"
                 ".wordprocessingml.document")
        name = f"cv_optimized_{review_id}.docx"
    return Response(
        content=data, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
