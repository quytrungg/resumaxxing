"""Claude subscription (OAuth) sign-in.

Reuses the public OAuth client Claude Code uses. This is an undocumented
third-party integration: endpoints or scopes can change, and Anthropic may
restrict subscription usage outside Claude Code. Failures must therefore stay
contained to the Claude provider (see docs/phase-plan-20-claude-oauth.md).

Tokens are stored Fernet-encrypted in `user_settings` and never returned by the
API. Refresh rotates the refresh token, so the new pair is persisted through a
short-lived session and guarded against clobbering a newer sign-in.
"""
import asyncio
import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from urllib.parse import urlencode

import httpx

from app.database import SessionLocal
from app.models import UserSettings
from app.services import crypto

logger = logging.getLogger(__name__)

CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
AUTHORIZE_URL = "https://claude.com/cai/oauth/authorize"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
REDIRECT_URI = "https://platform.claude.com/oauth/code/callback"
SCOPES = ("user:profile", "user:inference")
OAUTH_BETA = "oauth-2025-04-20"
TIMEOUT = httpx.Timeout(20.0)
REFRESH_SKEW = timedelta(seconds=60)

# Refresh tokens rotate and are single-use; serialise refresh attempts so two
# concurrent reviews cannot both spend the same token.
_refresh_lock = asyncio.Lock()


class ClaudeOAuthError(Exception):
    """A sign-in/refresh failure safe to show to the user."""


def is_connected(settings: Optional[UserSettings]) -> bool:
    return bool(
        settings
        and (settings.claude_auth_mode or "") == "oauth"
        and settings.claude_oauth_refresh_token
    )


def inference_headers(access_token: str) -> dict:
    """Headers required by the Messages API for subscription tokens."""
    return {
        "Authorization": f"Bearer {access_token}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": OAUTH_BETA,
        # The OAuth client identifies as Claude Code on the wire.
        "x-app": "cli",
    }


def start() -> Tuple[str, str, str]:
    """Build the authorize URL plus the PKCE/state values to post back."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    state = secrets.token_hex(16)
    params = {
        "code": "true",
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    query = urlencode(params)
    return f"{AUTHORIZE_URL}?{query}", state, verifier


def _split_code(code: str) -> Tuple[str, Optional[str]]:
    """The manual page shows `code#state`; accept the pasted form."""
    code = (code or "").strip()
    if "#" in code:
        code, embedded = code.split("#", 1)
        return code.strip(), embedded.strip() or None
    return code, None


def _apply(settings: UserSettings, payload: dict,
           fallback_refresh: Optional[str] = None) -> None:
    access = payload.get("access_token")
    if not isinstance(access, str) or not access:
        raise ClaudeOAuthError("Claude did not return an access token.")
    refresh = payload.get("refresh_token") or fallback_refresh
    if not isinstance(refresh, str) or not refresh:
        raise ClaudeOAuthError("Claude did not return a refresh token.")
    try:
        expires_in = int(payload.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0

    settings.claude_auth_mode = "oauth"
    settings.claude_oauth_access_token = crypto.encrypt(access)
    settings.claude_oauth_refresh_token = crypto.encrypt(refresh)
    settings.claude_oauth_expires_at = (
        datetime.utcnow() + timedelta(seconds=expires_in)
        if expires_in > 0 else None
    )
    account = payload.get("account")
    if isinstance(account, dict):
        email = account.get("email_address") or account.get("email")
        if isinstance(email, str) and email.strip():
            settings.claude_oauth_account = email.strip()[:255]


def _error_message(resp: httpx.Response, prefix: str) -> str:
    """Readable, token-free error from a token-endpoint response."""
    detail = ""
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        detail = str(
            body.get("error_description") or body.get("error") or ""
        ).strip()
    if not detail:
        detail = (resp.text or "").strip()[:200]
    if "invalid_grant" in detail.lower():
        return "Claude session expired — sign in again from Settings."
    if any(name in detail.lower() for name in
           ("invalid_client", "unauthorized_client")):
        return "Claude rejected this sign-in client. Try again later."
    suffix = f": {detail}" if detail else ""
    return f"{prefix} (HTTP {resp.status_code}){suffix}"


async def _post_token(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(TOKEN_URL, json=payload)
    except httpx.HTTPError:
        raise ClaudeOAuthError("Could not reach Claude's sign-in service.")
    if resp.status_code == 400 and "authorization code" in (
        (resp.text or "").lower()
    ):
        raise ClaudeOAuthError("That authorization code is invalid or expired.")
    if resp.status_code != 200:
        raise ClaudeOAuthError(_error_message(resp, "Claude sign-in failed"))
    try:
        data = resp.json()
    except ValueError:
        raise ClaudeOAuthError("Claude's sign-in service returned an invalid response.")
    if not isinstance(data, dict):
        raise ClaudeOAuthError("Claude's sign-in service returned an invalid response.")
    return data


async def exchange(settings: UserSettings, code: str, state: str,
                   code_verifier: str) -> None:
    """Trade the authorization code for tokens and switch to OAuth mode."""
    code, embedded_state = _split_code(code)
    state = embedded_state or (state or "").strip()
    if not code or not state or not code_verifier:
        raise ClaudeOAuthError("The sign-in code, state and verifier are required.")
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
        "state": state,
    }
    data = await _post_token(payload)
    _apply(settings, data)


async def _refresh_tokens(refresh_token: str) -> dict:
    return await _post_token({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "scope": " ".join(SCOPES),
    })


def _persist(settings: UserSettings, previous_refresh: Optional[str]) -> None:
    """Persist refreshed tokens without clobbering a newer sign-in."""
    db = SessionLocal()
    try:
        row = db.get(UserSettings, settings.id)
        if row is None:
            return
        current = crypto.decrypt(row.claude_oauth_refresh_token)
        if previous_refresh and current and current != previous_refresh:
            return
        row.claude_auth_mode = settings.claude_auth_mode
        row.claude_oauth_access_token = settings.claude_oauth_access_token
        row.claude_oauth_refresh_token = settings.claude_oauth_refresh_token
        row.claude_oauth_expires_at = settings.claude_oauth_expires_at
        row.claude_oauth_account = settings.claude_oauth_account
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("could not persist refreshed Claude OAuth tokens", exc_info=True)
    finally:
        db.close()


def _usable(settings: UserSettings) -> Optional[str]:
    token = crypto.decrypt(settings.claude_oauth_access_token)
    expires = settings.claude_oauth_expires_at
    if token and (expires is None or expires - datetime.utcnow() > REFRESH_SKEW):
        return token
    return None


async def ensure_access_token(settings: Optional[UserSettings]) -> str:
    """Return a valid access token, refreshing and persisting it when needed."""
    if not is_connected(settings):
        raise ClaudeOAuthError(
            "Claude is not connected. Sign in from Settings or use an API key."
        )
    token = _usable(settings)
    if token:
        return token

    async with _refresh_lock:
        # Another request may have refreshed while we waited on the lock.
        db = SessionLocal()
        try:
            row = db.get(UserSettings, settings.id)
            if row is not None and is_connected(row):
                token = _usable(row)
                if token:
                    settings.claude_oauth_access_token = row.claude_oauth_access_token
                    settings.claude_oauth_refresh_token = row.claude_oauth_refresh_token
                    settings.claude_oauth_expires_at = row.claude_oauth_expires_at
                    settings.claude_oauth_account = row.claude_oauth_account
                    return token
        finally:
            db.close()

        refresh_token = crypto.decrypt(settings.claude_oauth_refresh_token)
        if not refresh_token:
            raise ClaudeOAuthError(
                "Claude session expired — sign in again from Settings."
            )
        data = await _refresh_tokens(refresh_token)
        _apply(settings, data, fallback_refresh=refresh_token)
        _persist(settings, previous_refresh=refresh_token)
        token = _usable(settings)
        if not token:
            raise ClaudeOAuthError(
                "Claude returned an unusable session token. Sign in again."
            )
        return token


def disconnect(settings: UserSettings) -> None:
    settings.claude_auth_mode = "api_key"
    settings.claude_oauth_access_token = None
    settings.claude_oauth_refresh_token = None
    settings.claude_oauth_expires_at = None
    settings.claude_oauth_account = None
