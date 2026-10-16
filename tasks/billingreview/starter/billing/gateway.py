"""Payment gateway client interface and the in-memory fake used by tests.

The gateway is idempotent per idempotency key: repeating a charge or a
refund with a key it has already seen returns the original result and
moves no money. That is what makes retrying after a timeout safe.
"""

import itertools
from dataclasses import dataclass

from .errors import GatewayDeclined, GatewayTimeout


@dataclass(frozen=True)
class ChargeResult:
    charge_id: str


@dataclass(frozen=True)
class RefundResult:
    refund_id: str


class FakeGateway:
    """Scriptable fake. `script` is a list of outcomes consumed by
    successive calls: "ok", "decline", "timeout" (no answer, nothing
    happened) or "lost" (money moved, but the answer was lost)."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.charges = {}   # idempotency key -> (charge id, customer ref, amount, currency)
        self.refunds = {}   # idempotency key -> (refund id, charge id, amount)
        self._ids = itertools.count(1)

    def _next(self):
        return self.script.pop(0) if self.script else "ok"

    def charge(self, customer_ref, amount_minor, currency, idempotency_key):
        if idempotency_key in self.charges:
            return ChargeResult(self.charges[idempotency_key][0])
        outcome = self._next()
        if outcome == "decline":
            raise GatewayDeclined("card declined")
        if outcome == "timeout":
            raise GatewayTimeout("no response")
        charge_id = f"ch_{next(self._ids)}"
        self.charges[idempotency_key] = (charge_id, customer_ref, amount_minor, currency)
        if outcome == "lost":
            raise GatewayTimeout("response lost")
        return ChargeResult(charge_id)

    def refund(self, charge_id, amount_minor, idempotency_key):
        if idempotency_key in self.refunds:
            return RefundResult(self.refunds[idempotency_key][0])
        outcome = self._next()
        if outcome == "decline":
            raise GatewayDeclined("refund declined")
        if outcome == "timeout":
            raise GatewayTimeout("no response")
        refund_id = f"re_{next(self._ids)}"
        self.refunds[idempotency_key] = (refund_id, charge_id, amount_minor)
        if outcome == "lost":
            raise GatewayTimeout("response lost")
        return RefundResult(refund_id)

    def total_charged(self, customer_ref):
        return sum(c[2] for c in self.charges.values() if c[1] == customer_ref)
