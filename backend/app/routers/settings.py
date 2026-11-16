from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserSettings
from app.schemas import ModelListIn, SettingsIn, SettingsOut
from app.services import crypto
from app.services.model_catalog import PROVIDERS, ModelListError, list_models

router = APIRouter(prefix="/api", tags=["settings"])

KEY_FIELDS = ("claude_key", "ollama_key", "opencode_key", "opencode_go_key")
# Blank values clear these instead of storing an empty string.
NULLABLE_FIELDS = {
    "claude_base_url", "ollama_base_url", "opencode_base_url",
    "opencode_go_base_url",
    "claude_model", "ollama_model", "opencode_model", "opencode_go_model",
}


def get_default_user(db: Session) -> User:
    from app.config import settings as cfg
    user = db.query(User).filter(User.email == cfg.default_user_email).first()
    if not user:
        user = User(email=cfg.default_user_email)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def mask_key(stored: Optional[str]) -> str:
    """Preview a stored (encrypted) key without revealing it."""
    plain = crypto.decrypt(stored)
    if not plain:
        return ""
    if len(plain) <= 8:
        return "\u2022" * len(plain)
    return f"{plain[:6]}\u2026{plain[-4:]}"


def _settings_out(s: Optional[UserSettings]) -> SettingsOut:
    if not s:
        return SettingsOut()
    return SettingsOut(
        llm_provider=s.llm_provider or "mock",
        claude_key=mask_key(s.claude_key),
        ollama_key=mask_key(s.ollama_key),
        opencode_key=mask_key(s.opencode_key),
        opencode_go_key=mask_key(s.opencode_go_key),
        claude_base_url=s.claude_base_url or None,
        ollama_base_url=s.ollama_base_url or None,
        opencode_base_url=s.opencode_base_url or None,
        opencode_go_base_url=s.opencode_go_base_url or None,
        claude_model=s.claude_model or None,
        ollama_model=s.ollama_model or None,
        opencode_model=s.opencode_model or None,
        opencode_go_model=s.opencode_go_model or None,
        linkedin_url=s.linkedin_url,
    )


def _get_or_create(db: Session) -> UserSettings:
    user = get_default_user(db)
    s = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not s:
        s = UserSettings(user_id=user.id)
        db.add(s)
    return s


@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)):
    user = get_default_user(db)
    s = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    return _settings_out(s)


@router.put("/settings", response_model=SettingsOut)
def save_settings(payload: SettingsIn, db: Session = Depends(get_db)):
    s = _get_or_create(db)
    # True partial update: fields the client omitted are left untouched.
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in KEY_FIELDS:
            # Blank fields and echoed mask previews never overwrite a saved key.
            if not value or "\u2026" in value:
                continue
            setattr(s, field, crypto.encrypt(value))
        elif field in NULLABLE_FIELDS and not value:
            setattr(s, field, None)
        else:
            setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return _settings_out(s)


@router.delete("/settings/providers/{provider}", response_model=SettingsOut)
def delete_provider_key(provider: str, db: Session = Depends(get_db)):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    user = get_default_user(db)
    s = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not s:
        return SettingsOut()
    spec = PROVIDERS[provider]
    setattr(s, spec["key_field"], None)
    setattr(s, spec["base_url_field"], None)
    setattr(s, spec["model_field"], None)
    if (s.llm_provider or "") == provider:
        s.llm_provider = "mock"
    db.commit()
    db.refresh(s)
    return _settings_out(s)


@router.post("/settings/providers/models")
async def provider_models(payload: ModelListIn, db: Session = Depends(get_db)):
    if payload.provider not in PROVIDERS:
        raise HTTPException(
            status_code=400, detail=f"Unknown provider: {payload.provider}"
        )
    user = get_default_user(db)
    s = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    try:
        models = await list_models(
            payload.provider, s, api_key=payload.api_key, base_url=payload.base_url
        )
    except ModelListError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"models": models}
