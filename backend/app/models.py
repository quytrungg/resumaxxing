import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Enum as SAEnum, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


class ReviewStatus(str, enum.Enum):
    draft = "draft"
    finalized = "finalized"


class SuggestionType(str, enum.Enum):
    ADD = "ADD"
    REMOVE = "REMOVE"
    UPDATE = "UPDATE"


class SuggestionStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    settings = relationship("UserSettings", back_populates="user", uselist=False)
    base_cvs = relationship("BaseCV", back_populates="user")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    llm_provider = Column(String(50), default="mock")  # claude | ollama | opencode | opencode_go | mock
    claude_key = Column(Text, nullable=True)
    # Claude subscription sign-in (null/"api_key" = use claude_key).
    claude_auth_mode = Column(String(20), nullable=True)
    claude_oauth_access_token = Column(Text, nullable=True)
    claude_oauth_refresh_token = Column(Text, nullable=True)
    claude_oauth_expires_at = Column(DateTime, nullable=True)
    claude_oauth_account = Column(String(255), nullable=True)
    ollama_key = Column(Text, nullable=True)
    opencode_key = Column(Text, nullable=True)
    opencode_go_key = Column(Text, nullable=True)
    # Optional per-provider endpoint overrides (local Ollama, proxies).
    claude_base_url = Column(String(500), nullable=True)
    ollama_base_url = Column(String(500), nullable=True)
    opencode_base_url = Column(String(500), nullable=True)
    opencode_go_base_url = Column(String(500), nullable=True)
    # Default model per provider when a review does not pin one.
    claude_model = Column(String(100), nullable=True)
    ollama_model = Column(String(100), nullable=True)
    opencode_model = Column(String(100), nullable=True)
    opencode_go_model = Column(String(100), nullable=True)
    linkedin_url = Column(String(500), nullable=True)

    user = relationship("User", back_populates="settings")


class BaseCV(Base):
    __tablename__ = "base_cvs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    original_file_path = Column(String(500), nullable=False)
    parsed_text = Column(Text, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="base_cvs")


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_url = Column(String(1000), nullable=True)
    raw_text = Column(Text, nullable=False)
    # Resolved headline from the posting; null when nothing credible was found.
    title = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    # LLM-extracted requirement set for this posting (services/requirements.py).
    # Null means "not extracted yet" - readers fall back to the heuristic list.
    jd_requirements = Column(JSON, nullable=True)


class CVReview(Base):
    __tablename__ = "cv_reviews"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    base_cv_id = Column(Integer, ForeignKey("base_cvs.id"), nullable=False)
    job_description_id = Column(Integer, ForeignKey("job_descriptions.id"), nullable=False)
    current_score = Column(Integer, default=0)
    status = Column(SAEnum(ReviewStatus), default=ReviewStatus.draft)
    created_at = Column(DateTime, default=datetime.utcnow)
    # LLM pinned for this review (null on pre-existing rows -> saved setting).
    llm_provider = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)
    # Structured CV produced by the LLM rewrite at finalize time.
    final_document = Column(JSON, nullable=True)
    # LaTeX source produced for the .tex download (same rewrite, .tex layout).
    final_latex = Column(Text, nullable=True)
    cover_letter = Column(Text, nullable=True)
    # Background run state: running | complete | failed. Separate from `status`
    # (draft/finalized) so no Postgres enum surgery is needed.
    run_state = Column(String(20), nullable=False, server_default="complete",
                       default="complete")
    run_error = Column(Text, nullable=True)

    suggestions = relationship("Suggestion", back_populates="review",
                               cascade="all, delete-orphan")
    score_events = relationship("ScoreEvent", back_populates="review",
                                cascade="all, delete-orphan",
                                order_by="ScoreEvent.id")
    base_cv = relationship("BaseCV")
    job_description = relationship("JobDescription")


class ScoreEvent(Base):
    __tablename__ = "score_events"

    id = Column(Integer, primary_key=True)
    cv_review_id = Column(Integer, ForeignKey("cv_reviews.id"), nullable=False,
                          index=True)
    score = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    review = relationship("CVReview", back_populates="score_events")


class Suggestion(Base):
    __tablename__ = "suggestions"

    id = Column(Integer, primary_key=True)
    cv_review_id = Column(Integer, ForeignKey("cv_reviews.id"), nullable=False)
    type = Column(SAEnum(SuggestionType), nullable=False)
    target_section = Column(String(100), nullable=True)
    original_text = Column(Text, nullable=True)
    suggested_text = Column(Text, nullable=False)
    # First AI wording, captured only when the user first edits
    # `suggested_text`; null means the text is still the LLM's own. Lets the
    # card offer "Reset to AI text" (see routers/reviews.py suggestion text
    # endpoints).
    original_suggested_text = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)
    status = Column(SAEnum(SuggestionStatus), default=SuggestionStatus.PENDING)

    review = relationship("CVReview", back_populates="suggestions")
