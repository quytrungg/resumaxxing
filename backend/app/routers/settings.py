from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserSettings
from app.schemas import SettingsIn, SettingsOut

router = APIRouter(prefix="/api", tags=["settings"])


def get_default_user(db: Session) -> User:
    from app.config import settings as cfg
    user = db.query(User).filter(User.email == cfg.default_user_email).first()
    if not user:
        user = User(email=cfg.default_user_email)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)):
    user = get_default_user(db)
    s = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not s:
        return SettingsOut()
    return s


@router.put("/settings", response_model=SettingsOut)
def save_settings(payload: SettingsIn, db: Session = Depends(get_db)):
    user = get_default_user(db)
    s = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not s:
        s = UserSettings(user_id=user.id)
        db.add(s)
    for field, value in payload.model_dump().items():
        # empty strings from the form should not wipe stored keys
        if field.endswith("_key") and value == "":
            continue
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return s
