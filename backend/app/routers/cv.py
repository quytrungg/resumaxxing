import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.config import settings as cfg
from app.database import get_db
from app.models import BaseCV
from app.schemas import BaseCVOut
from app.services.parsing import parse_cv
from app.routers.settings import get_default_user

router = APIRouter(prefix="/api/cv", tags=["cv"])


@router.post("/upload", response_model=BaseCVOut)
async def upload_cv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = get_default_user(db)
    content = await file.read()
    try:
        text = parse_cv(content, file.filename or "cv.txt")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not text:
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    os.makedirs(cfg.upload_dir, exist_ok=True)
    path = os.path.join(cfg.upload_dir, f"{uuid.uuid4()}_{file.filename}")
    with open(path, "wb") as f:
        f.write(content)

    cv = BaseCV(user_id=user.id, original_file_path=path, parsed_text=text)
    db.add(cv)
    db.commit()
    db.refresh(cv)
    return cv


@router.get("/latest", response_model=BaseCVOut)
def latest_cv(db: Session = Depends(get_db)):
    user = get_default_user(db)
    cv = (db.query(BaseCV).filter(BaseCV.user_id == user.id)
          .order_by(BaseCV.uploaded_at.desc()).first())
    if not cv:
        raise HTTPException(status_code=404, detail="No CV uploaded yet")
    return cv
