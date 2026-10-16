"""Row types."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class User:
    id: int
    tenant_id: int
    name: str
    role: str
    is_staff: int
    api_key_hash: str


@dataclass(frozen=True)
class Customer:
    id: int
    tenant_id: int
    name: str
    email: str
    gateway_ref: str
    created_at: int


@dataclass(frozen=True)
class Invoice:
    id: int
    tenant_id: int
    customer_id: int
    number: str
    currency: str
    status: str
    total_minor: int
    paid_minor: int
    due_date: str
    created_at: int
    updated_at: int

    def public(self):
        return {"id": self.id, "number": self.number, "customer_id": self.customer_id,
                "currency": self.currency, "status": self.status,
                "total": self.total_minor, "paid": self.paid_minor,
                "due_date": self.due_date}


@dataclass(frozen=True)
class Payment:
    id: int
    tenant_id: int
    customer_id: int
    invoice_id: Optional[int]
    amount_minor: int
    currency: str
    status: str
    idempotency_key: str
    gateway_charge_id: Optional[str]
    attempts: int
    created_at: int

    def public(self):
        return {"id": self.id, "invoice_id": self.invoice_id,
                "amount": self.amount_minor, "currency": self.currency,
                "status": self.status, "attempts": self.attempts}


@dataclass(frozen=True)
class Refund:
    id: int
    payment_id: int
    amount_minor: int
    status: str
    reason: str
    gateway_refund_id: Optional[str]
    created_at: int

    def public(self):
        return {"id": self.id, "payment_id": self.payment_id,
                "amount": self.amount_minor, "status": self.status}
