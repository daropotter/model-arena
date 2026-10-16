"""Password hashing and signed session tokens."""

import base64
import hashlib
import hmac
import json
import os
import time

PBKDF2_ROUNDS = 120_000


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        scheme, rounds, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(candidate.hex(), digest)


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_session(secret, user_id, ttl, now=None):
    now = int(time.time() if now is None else now)
    payload = _b64(json.dumps({"uid": user_id, "exp": now + ttl}).encode())
    mac = _b64(hmac.new(secret, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{mac}"


def read_session(secret, token, now=None):
    """Return the user id of a valid, unexpired token, else None."""
    now = int(time.time() if now is None else now)
    try:
        payload, mac = token.split(".")
        expected = _b64(hmac.new(secret, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(mac, expected):
            return None
        data = json.loads(_unb64(payload))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("exp", 0) <= now:
        return None
    return data.get("uid")
