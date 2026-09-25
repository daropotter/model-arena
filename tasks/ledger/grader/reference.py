"""Reference implementation of SPEC.md. Used only by the hidden grader."""

from decimal import Decimal, ROUND_HALF_EVEN


def _fee(amount: Decimal) -> Decimal:
    return (abs(amount) * Decimal("0.01")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN
    )


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def summarize_reference(payload: dict) -> dict:
    transactions = payload.get("transactions", [])
    ordered = sorted(transactions, key=lambda t: t["timestamp"])

    accounts: dict[str, dict] = {}
    out_transactions = []
    fees_total = Decimal("0")

    for tx in ordered:
        amount = Decimal(str(tx["amount"]))
        fee = _fee(amount)
        fees_total += fee

        account = accounts.setdefault(tx["account"], {"balance": Decimal("0"), "count": 0})
        account["balance"] += amount
        if amount != 0:
            account["count"] += 1

        out_transactions.append({"id": tx["id"], "fee": _money(fee)})

    return {
        "transactions": out_transactions,
        "accounts": {
            name: {"balance": _money(acc["balance"]), "count": acc["count"]}
            for name, acc in accounts.items()
        },
        "fees_total": _money(fees_total),
    }
