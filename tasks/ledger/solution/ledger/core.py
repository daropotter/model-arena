"""Reference solution for verification: a spec-compliant ledger core."""

from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def compute_fee(amount: Decimal) -> Decimal:
    return (abs(amount) * Decimal("0.01")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN
    )


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    transactions = payload.get("transactions", [])
    ordered = sorted(transactions, key=lambda t: t["timestamp"])

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
        if amount != 0:
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
