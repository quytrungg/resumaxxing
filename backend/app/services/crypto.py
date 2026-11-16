"""Encryption-at-rest for API keys stored in user_settings.

The Fernet key is derived from `SECRET_KEY` so any sufficiently random string
works. Values that are not valid Fernet tokens are returned unchanged, which
keeps plaintext keys created before this feature working until their next save.
"""
import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        # Legacy plaintext value stored before encryption was introduced.
        return value
