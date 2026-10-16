"""Tenant context: which tenant a piece of work runs in, and for whom.

Every repository method takes a TenantContext instead of a bare tenant
id, so tenant scoping cannot be forgotten at a call site. The system
context (tenant_id None) is for jobs and webhooks that legitimately work
across tenants.
"""

from dataclasses import dataclass
from typing import Optional

from .errors import NotFound
from .models import User


@dataclass(frozen=True)
class TenantContext:
    tenant_id: Optional[int]
    user: Optional[User] = None

    @property
    def is_system(self):
        return self.tenant_id is None

    @property
    def actor_id(self):
        return self.user.id if self.user else None

    @classmethod
    def system(cls):
        return cls(None, None)

    @classmethod
    def for_user(cls, user, acting_as=None):
        """Context for an authenticated user; staff may act in another
        tenant by passing its id (the X-Tenant-Id header)."""
        if acting_as is not None and user.is_staff is not None:
            try:
                return cls(int(acting_as), user)
            except ValueError:
                raise NotFound()
        return cls(user.tenant_id, user)

    def within(self, tenant_id):
        """Narrow a system context to one tenant."""
        return TenantContext(tenant_id, self.user)
