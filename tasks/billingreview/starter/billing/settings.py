"""Service settings."""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path
    webhook_secret: bytes = b"whsec-dev-only"
    max_charge_attempts: int = 3
    retry_backoff: float = 2.0  # seconds before the 2nd attempt, doubling after
    invoice_cache_ttl: float = 30.0
    # units of the second currency per unit of the first
    fx_rates: dict = field(default_factory=lambda: {
        ("EUR", "USD"): Decimal("1.0850"),
        ("USD", "EUR"): Decimal("0.9217"),
        ("EUR", "JPY"): Decimal("161.42"),
        ("USD", "JPY"): Decimal("148.77"),
    })

    @property
    def db_path(self):
        return self.data_dir / "billing.db"
