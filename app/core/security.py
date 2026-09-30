"""Security primitives: password hashing (scrypt), signed sessions, CSRF tokens, login rate limiting."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return "scrypt$%s$%s" % (base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ---- stateless signed session cookie: "exp_b64.hmac" ----
def _sig(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_session_token(secret: str, ttl_hours: int) -> str:
    exp = int(time.time()) + ttl_hours * 3600
    payload = str(exp)
    return f"{payload}.{_sig(secret, payload)}"


def verify_session_token(secret: str, token: str | None) -> bool:
    if not token or not secret or "." not in token:
        return False
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(_sig(secret, payload), sig):
        return False
    try:
        return int(payload) >= time.time()
    except ValueError:
        return False


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def check_csrf(submitted: str | None, cookie_token: str | None) -> bool:
    return bool(submitted and cookie_token and hmac.compare_digest(submitted, cookie_token))


# ---- in-memory login throttle (per process; enough for a single-admin panel) ----
class LoginThrottle:
    def __init__(self, max_failures: int = 5, window_seconds: int = 900) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}

    def is_blocked(self, key: str) -> bool:
        now = time.time()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        self._failures[key] = recent
        return len(recent) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._failures.setdefault(key, []).append(time.time())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


if __name__ == "__main__":  # `python -m app.core.security make-hash <password>`
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "make-hash":
        print(hash_password(sys.argv[2]))
