from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models import SuggestionType, SuggestionStatus, ReviewStatus


class SettingsIn(BaseModel):
    llm_provider: str = "mock"
    claude_key: Optional[str] = None
    ollama_key: Optional[str] = None
    opencode_key: Optional[str] = None
    linkedin_url: Optional[str] = None


class SettingsOut(SettingsIn):
    class Config:
        from_attributes = True


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
    reasoning: Optional[str]
    status: SuggestionStatus

    class Config:
        from_attributes = True


class SuggestionStatusUpdate(BaseModel):
    status: SuggestionStatus


class ReviewCreate(BaseModel):
    jd_text: Optional[str] = None
    jd_url: Optional[str] = None


class ReviewOut(BaseModel):
    id: int
    current_score: int
    status: ReviewStatus
    created_at: datetime
    suggestions: List[SuggestionOut]
    jd_text: Optional[str] = None
    cv_preview: Optional[str] = None


class ScoreOut(BaseModel):
    score: int


# ----- LLM structured payloads (for parsing LLM JSON responses) -----

class LLMSuggestion(BaseModel):
    type: SuggestionType
    target_section: Optional[str] = None
    original_text: Optional[str] = None
    suggested_text: str
    reasoning: Optional[str] = None


class LLMReviewResponse(BaseModel):
    score: int
    suggestions: List[LLMSuggestion]
