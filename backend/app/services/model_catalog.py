"""Provider metadata and model-list lookups for the Settings page.

Keys never leave the backend in plaintext: the listing helper accepts either a
freshly typed key (used for the request only) or falls back to the decrypted
stored key when the client sends a blank/masked value.
"""
from typing import List, Optional

import httpx

from app.models import UserSettings
from app.services import crypto

PROVIDERS = {
    "claude": {
        "label": "Claude",
        "key_field": "claude_key",
        "base_url_field": "claude_base_url",
        "model_field": "claude_model",
        "default_base_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-5",
    },
    "ollama": {
        "label": "Ollama Cloud",
        "key_field": "ollama_key",
        "base_url_field": "ollama_base_url",
        "model_field": "ollama_model",
        "default_base_url": "https://ollama.com",
        "default_model": "gpt-oss:120b-cloud",
    },
    "opencode": {
        "label": "Opencode Zen",
        "key_field": "opencode_key",
        "base_url_field": "opencode_base_url",
        "model_field": "opencode_model",
        "default_base_url": "https://opencode.ai/zen",
        "default_model": "grok-code",
    },
    "opencode_go": {
        "label": "Opencode Go",
        "key_field": "opencode_go_key",
        "base_url_field": "opencode_go_base_url",
        "model_field": "opencode_go_model",
        "default_base_url": "https://opencode.ai/zen/go",
        "default_model": "glm-5.3",
    },
}

MASK_MARK = "\u2026"


class ModelListError(Exception):
    """A provider model-list failure with a user-safe message."""


def api_base(url: Optional[str]) -> str:
    """Normalise a base URL so callers can append `/v1/...` consistently."""
    base = (url or "").strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base


def stored_base_url(settings: Optional[UserSettings], provider: str) -> str:
    spec = PROVIDERS[provider]
    stored = getattr(settings, spec["base_url_field"], None) if settings else None
    return api_base(stored or spec["default_base_url"])


def resolve_base_url(settings: Optional[UserSettings], provider: str,
                     override: Optional[str] = None) -> str:
    base = api_base(override or stored_base_url(settings, provider))
    if not base.startswith(("http://", "https://")):
        raise ModelListError("Base URL must start with http:// or https://.")
    return base


def resolve_api_key(settings: Optional[UserSettings], provider: str,
                    override: Optional[str] = None) -> Optional[str]:
    """Fresh key wins; blank or an echoed mask falls back to the saved key."""
    candidate = (override or "").strip()
    if candidate and MASK_MARK not in candidate:
        return candidate
    spec = PROVIDERS[provider]
    stored = getattr(settings, spec["key_field"], None) if settings else None
    return crypto.decrypt(stored)


def _headers(provider: str, key: Optional[str]) -> dict:
    if provider == "claude":
        return {
            "x-api-key": key or "",
            "anthropic-version": "2023-06-01",
            "accept": "application/json",
        }
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _parse_models(payload: dict) -> List[str]:
    items = payload.get("data")
    if items is None:
        items = payload.get("models")
    if not isinstance(items, list):
        raise ModelListError("Provider returned an unexpected model list.")
    models = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("name")
        if isinstance(model_id, str) and model_id.strip():
            models.add(model_id.strip())
    return sorted(models)


async def list_models(provider: str,
                      settings: Optional[UserSettings],
                      api_key: Optional[str] = None,
                      base_url: Optional[str] = None) -> List[str]:
    if provider not in PROVIDERS:
        raise ModelListError(f"Unknown provider: {provider}")

    spec = PROVIDERS[provider]
    key = resolve_api_key(settings, provider, api_key)
    if not key and provider != "ollama":
        raise ModelListError(f"Add a {spec['label']} API key first.")
    base = resolve_base_url(settings, provider, base_url)
    url = f"{base}/v1/models"

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers=_headers(provider, key),
                params={"limit": 1000} if provider == "claude" else None,
            )
    except httpx.TimeoutException:
        raise ModelListError(f"{spec['label']} model list timed out.")
    except httpx.HTTPError:
        raise ModelListError(
            f"Could not reach {spec['label']} at {base}. Check the base URL."
        )

    if resp.status_code in (401, 403):
        raise ModelListError(f"{spec['label']} rejected the API key.")
    if resp.status_code == 404:
        raise ModelListError(
            f"{spec['label']} model list not found at {base}. Check the base URL."
        )
    if resp.status_code == 429:
        raise ModelListError(f"{spec['label']} rate limited the request. Try again shortly.")
    if resp.status_code >= 400:
        raise ModelListError(f"{spec['label']} returned HTTP {resp.status_code}.")

    try:
        payload = resp.json()
    except ValueError:
        raise ModelListError(f"{spec['label']} returned a non-JSON model list.")
    if not isinstance(payload, dict):
        raise ModelListError(f"{spec['label']} returned an unexpected model list.")

    return _parse_models(payload)
