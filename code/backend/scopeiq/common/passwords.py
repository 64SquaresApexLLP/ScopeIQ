"""Password hashing for sign-in credentials: salted PBKDF2-SHA256 from the standard library (no extra dependency).

Stored format: "pbkdf2_sha256$<iterations>$<salt b64>$<hash b64>". Only the hash is stored, never the password.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """True when `password` matches the stored hash. A missing or malformed hash never matches."""
    try:
        algorithm, iterations, salt, digest = (stored or "").split("$")
        if algorithm != ALGORITHM:
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


# Compared against when the username is unknown, so a wrong username takes as long as a wrong password.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
