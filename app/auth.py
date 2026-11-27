"""Therapist authentication (A5): a child-proof gate plus LAN-grade auth. Not hospital-grade.

- PIN: 4-6 digits. Stored as salted PBKDF2 once changed; until then the env default is used
  and the server logs a warning at startup.
- Lockout: 5 wrong PINs -> 60 s lockout. Counter persisted in the settings table so a
  restart doesn't reset it. Compare with hmac.compare_digest (constant time).
- Token: HMAC-SHA256 over an expiry time, signed with a per-install random secret kept in the
  data volume. Sent as an HttpOnly, SameSite=Strict cookie. Expires after 15 minutes idle
  (each therapist request slides the expiry forward).
Pitfall: SameSite=Strict blocks cross-site form posts (CSRF) but anyone with network access to
the port can still try PINs; the lockout is what slows them down.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

from fastapi import HTTPException, Request, Response

from .config import settings
from .db import db, get_setting, set_setting

log = logging.getLogger("pesu.auth")

COOKIE = "pesu_t"
IDLE_SECONDS = 15 * 60
MAX_FAILS = 5
LOCK_SECONDS = 60
_secret_cache: bytes | None = None


def secret() -> bytes:
    global _secret_cache
    if _secret_cache is None:
        path = settings.secret_file
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(secrets.token_bytes(32))
            path.chmod(0o600)
        _secret_cache = path.read_bytes()
    return _secret_cache


def reset_secret_cache() -> None:
    global _secret_cache
    _secret_cache = None


def _sign(payload: bytes) -> str:
    return hmac.new(secret(), payload, hashlib.sha256).hexdigest()


def make_token(now: float | None = None) -> str:
    payload = json.dumps({"exp": int((now or time.time()) + IDLE_SECONDS)}).encode()
    return base64.urlsafe_b64encode(payload).decode() + "." + _sign(payload)


def check_token(token: str | None, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    b64, sig = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(b64.encode())
        exp = json.loads(payload)["exp"]
    except Exception:
        return False
    return hmac.compare_digest(_sign(payload), sig) and exp > (now or time.time())


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()


def pin_is_default() -> bool:
    with db() as conn:
        return get_setting(conn, "pin_hash") is None


def verify_pin(pin: str) -> dict:
    """Returns {ok, locked_for}. Counts failures and applies the lockout."""
    with db() as conn:
        locked_until = float(get_setting(conn, "pin_locked_until", "0"))
        if locked_until > time.time():
            return {"ok": False, "locked_for": int(locked_until - time.time()) + 1}
        stored, salt = get_setting(conn, "pin_hash"), get_setting(conn, "pin_salt")
        if stored and salt:
            ok = hmac.compare_digest(_hash_pin(pin, salt), stored)
        else:
            ok = hmac.compare_digest(pin.encode(), settings.default_pin.encode())
        if ok:
            set_setting(conn, "pin_fails", "0")
            return {"ok": True, "locked_for": 0}
        fails = int(get_setting(conn, "pin_fails", "0")) + 1
        set_setting(conn, "pin_fails", str(fails))
        if fails >= MAX_FAILS:
            set_setting(conn, "pin_fails", "0")
            set_setting(conn, "pin_locked_until", str(time.time() + LOCK_SECONDS))
            return {"ok": False, "locked_for": LOCK_SECONDS}
        return {"ok": False, "locked_for": 0}


def change_pin(new_pin: str) -> None:
    salt = secrets.token_hex(8)
    with db() as conn:
        set_setting(conn, "pin_salt", salt)
        set_setting(conn, "pin_hash", _hash_pin(new_pin, salt))


def set_cookie(response: Response) -> None:
    response.set_cookie(COOKIE, make_token(), max_age=IDLE_SECONDS, httponly=True, samesite="strict", path="/")


def require_therapist(request: Request, response: Response) -> None:
    """FastAPI dependency for every therapist route. Slides the idle expiry forward."""
    if not check_token(request.cookies.get(COOKIE)):
        raise HTTPException(401, "Therapist PIN required")
    set_cookie(response)
