"""Role checks."""

from enum import Enum

from .errors import Forbidden


class Role(str, Enum):
    """Ordered roles: VIEWER < BILLING < ADMIN. Being a str enum, a Role
    compares equal to its database value."""

    VIEWER = "viewer"
    BILLING = "billing"
    ADMIN = "admin"


def require(ctx, minimum):
    """Raise Forbidden unless the context's user has at least `minimum`."""
    if ctx.user is None:
        raise Forbidden("no user in context")
    if Role(ctx.user.role) < minimum:
        raise Forbidden(f"requires role {minimum.value}")
