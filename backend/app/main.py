import hmac

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings as cfg
from app.routers import cv, reviews, settings

app = FastAPI(title="Resumaxxing")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUTH_EXEMPT_PATHS = {"/api/health", "/api/auth"}


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """Optional single-password gate; disabled unless APP_PASSWORD is set."""
    path = request.url.path
    if (cfg.app_password and path.startswith("/api")
            and path not in AUTH_EXEMPT_PATHS
            and request.method != "OPTIONS"):
        supplied = request.headers.get("x-app-password", "")
        if not hmac.compare_digest(supplied, cfg.app_password):
            return JSONResponse({"detail": "Password required"}, status_code=401)
    return await call_next(request)


app.include_router(settings.router)
app.include_router(cv.router)
app.include_router(reviews.router)


@app.get("/api/auth")
def auth_status():
    return {"required": bool(cfg.app_password)}


@app.get("/api/health")
def health():
    return {"status": "ok"}
