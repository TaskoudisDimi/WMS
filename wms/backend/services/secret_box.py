"""Encrypt third-party credentials (e.g. invoicing API keys) before storing them.

Key: APP_SECRET env var if set, otherwise derived from SUPABASE_KEY. Rotating the key
makes stored credentials unreadable — users then re-enter them in Settings."""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from core.config import SUPABASE_KEY

_fernet = Fernet(base64.urlsafe_b64encode(
    hashlib.sha256((os.getenv("APP_SECRET") or SUPABASE_KEY or "").encode()).digest()))


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
