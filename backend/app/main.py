from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import cv, reviews, settings

app = FastAPI(title="Resumaxxing")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings.router)
app.include_router(cv.router)
app.include_router(reviews.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
