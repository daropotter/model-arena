"""Request body validation."""

from .errors import BadRequest

MAX_TITLE = 200
MAX_BODY = 100_000


def require_fields(body, *names):
    if not isinstance(body, dict):
        raise BadRequest("body must be a JSON object")
    missing = [name for name in names if name not in body]
    if missing:
        raise BadRequest("missing: " + ", ".join(missing))


def title(value):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TITLE:
        raise BadRequest("invalid title")
    return value.strip()


def body_text(value):
    if not isinstance(value, str) or len(value) > MAX_BODY:
        raise BadRequest("invalid body")
    return value


def email(value):
    if not isinstance(value, str) or "@" not in value or len(value) > 254:
        raise BadRequest("invalid email")
    return value.strip().lower()


def password(value):
    if not isinstance(value, str) or len(value) < 8:
        raise BadRequest("password must have at least 8 characters")
    return value


def sort_key(value, allowed):
    if value is None:
        return "created"
    if value not in allowed:
        raise BadRequest("invalid sort")
    return value


def ttl_hours(value):
    if value is None:
        return 24
    if type(value) is not int or not 1 <= value <= 168:
        raise BadRequest("ttl_hours must be an integer from 1 to 168")
    return value


def limit(value, maximum):
    if value is None:
        return maximum
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise BadRequest("invalid limit")
    if not 1 <= number <= maximum:
        raise BadRequest("invalid limit")
    return number
