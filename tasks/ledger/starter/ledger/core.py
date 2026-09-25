"""Core ledger logic. See SPEC.md for the authoritative rules."""

from decimal import Decimal
from typing import Any


def money(value: Decimal) -> str:
    """Format a Decimal as a string with exactly 2 decimal places."""
    return f"{value:.2f}"


def compute_fee(amount: Decimal) -> Decimal:
    """Return the fee charged for a transaction amount."""
    return Decimal(str(round(float(amount) * 0.01, 2)))


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize a ledger payload according to SPEC.md."""
    transactions = payload.get("transactions", [])
    ordered = sorted(transactions, key=lambda t: (t["timestamp"], t["id"]))

    accounts: dict[str, dict[str, Any]] = {}
    out_transactions: list[dict[str, Any]] = []
    fees_total = Decimal("0")

    for tx in ordered:
        amount = Decimal(str(tx["amount"]))
        fee = compute_fee(amount)
        fees_total += fee

        account = accounts.setdefault(
            tx["account"], {"balance": Decimal("0"), "count": 0}
        )
        account["balance"] += amount
        account["count"] += 1

        out_transactions.append({"id": tx["id"], "fee": money(fee)})

    return {
        "transactions": out_transactions,
        "accounts": {
            name: {"balance": money(acc["balance"]), "count": acc["count"]}
            for name, acc in accounts.items()
        },
        "fees_total": money(fees_total),
    }
