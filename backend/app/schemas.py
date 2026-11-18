from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator

from app.models import SuggestionType, SuggestionStatus, ReviewStatus


class SettingsIn(BaseModel):
    llm_provider: str = "mock"
    claude_key: Optional[str] = None
    ollama_key: Optional[str] = None
    opencode_key: Optional[str] = None
    opencode_go_key: Optional[str] = None
    claude_base_url: Optional[str] = None
    ollama_base_url: Optional[str] = None
    opencode_base_url: Optional[str] = None
    opencode_go_base_url: Optional[str] = None
    claude_model: Optional[str] = None
    ollama_model: Optional[str] = None
    opencode_model: Optional[str] = None
    opencode_go_model: Optional[str] = None
    linkedin_url: Optional[str] = None


class SettingsOut(BaseModel):
    """Key fields carry masked previews only - never plaintext."""

    llm_provider: str = "mock"
    claude_key: Optional[str] = None
    ollama_key: Optional[str] = None
    opencode_key: Optional[str] = None
    opencode_go_key: Optional[str] = None
    claude_base_url: Optional[str] = None
    ollama_base_url: Optional[str] = None
    opencode_base_url: Optional[str] = None
    opencode_go_base_url: Optional[str] = None
    claude_model: Optional[str] = None
    ollama_model: Optional[str] = None
    opencode_model: Optional[str] = None
    opencode_go_model: Optional[str] = None
    linkedin_url: Optional[str] = None


class ModelListIn(BaseModel):
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class BaseCVOut(BaseModel):
    id: int
    original_file_path: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class SuggestionOut(BaseModel):
    id: int
    type: SuggestionType
    target_section: Optional[str]
    original_text: Optional[str]
    suggested_text: str
    # AI wording preserved after the user edits `suggested_text` (null until the
    # first edit); the card uses it to offer "Reset to AI text".
    original_suggested_text: Optional[str] = None
    reasoning: Optional[str]
    status: SuggestionStatus

    class Config:
        from_attributes = True


class SuggestionStatusUpdate(BaseModel):
    status: SuggestionStatus


class SuggestionTextUpdate(BaseModel):
    """User-adjusted replacement text for an ADD/UPDATE suggestion."""

    suggested_text: str = Field(min_length=1, max_length=4000)

    @field_validator("suggested_text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("suggested_text must not be blank")
        return value


class SuggestionStatusOut(BaseModel):
    status: SuggestionStatus


class ReviewCreate(BaseModel):
    jd_text: Optional[str] = None
    jd_url: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class ScoreHistoryOut(BaseModel):
    score: int
    reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RequirementOut(BaseModel):
    label: str
    canonical: str = ""
    aliases: List[str] = Field(default_factory=list)
    importance: str = "must"
    category: Optional[str] = None
    quote: Optional[str] = None
    matched: bool = False

    class Config:
        from_attributes = True


class ReviewOut(BaseModel):
    id: int
    current_score: int
    status: ReviewStatus
    created_at: datetime
    suggestions: List[SuggestionOut]
    jd_text: Optional[str] = None
    jd_title: Optional[str] = None
    jd_company: Optional[str] = None
    cv_preview: Optional[str] = None
    keyword_coverage: int = 0
    must_have_coverage: Optional[int] = None
    nice_to_have_coverage: Optional[int] = None
    requirements: List[RequirementOut] = Field(default_factory=list)
    matched_keywords: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    score_history: List[ScoreHistoryOut] = Field(default_factory=list)
    final_document: Optional["StructuredCV"] = None
    cover_letter: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    run_state: str = "complete"
    run_error: Optional[str] = None


class ScoreOut(BaseModel):
    score: int
    keyword_coverage: int = 0
    must_have_coverage: Optional[int] = None
    nice_to_have_coverage: Optional[int] = None
    requirements: List[RequirementOut] = Field(default_factory=list)
    matched_keywords: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    history_entry: Optional[ScoreHistoryOut] = None


class CoverLetterOut(BaseModel):
    text: str


class CoverLetterUpdate(BaseModel):
    text: str


# ----- Structured CV document (LLM rewrite output) -----

class StructuredSection(BaseModel):
    heading: str
    bullets: List[str] = Field(default_factory=list)


class StructuredCV(BaseModel):
    name: Optional[str] = None
    headline: Optional[str] = None
    contact: List[str] = Field(default_factory=list)
    sections: List[StructuredSection] = Field(default_factory=list)


# ----- LLM structured payloads (for parsing LLM JSON responses) -----

class LLMSuggestion(BaseModel):
    type: SuggestionType
    target_section: Optional[str] = None
    original_text: Optional[str] = None
    # A REMOVE item has no replacement text, so the LLM may omit this key
    # entirely (or send null); an empty string is the canonical value.
    suggested_text: str = ""
    reasoning: Optional[str] = None

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value):
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("suggested_text", mode="before")
    @classmethod
    def _normalize_suggested_text(cls, value):
        return "" if value is None else value


class LLMReviewResponse(BaseModel):
    score: int
    suggestions: List[LLMSuggestion]
