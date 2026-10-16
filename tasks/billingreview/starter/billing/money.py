"""Money in integer minor units. Floats never touch money."""

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

EXPONENTS = {"EUR": 2, "USD": 2, "GBP": 2, "JPY": 0}


def check_currency(code):
    if code not in EXPONENTS:
        raise ValueError(f"unsupported currency {code!r}")
    return code


@dataclass(frozen=True)
class Money:
    amount: int  # minor units
    currency: str

    def __post_init__(self):
        if type(self.amount) is not int:
            raise TypeError("Money.amount must be an int of minor units")
        check_currency(self.currency)

    @classmethod
    def zero(cls, currency):
        return cls(0, currency)

    @classmethod
    def from_decimal(cls, value, currency):
        """Major units (Decimal or numeric string) to Money, ROUND_HALF_EVEN."""
        exp = EXPONENTS[check_currency(currency)]
        minor = (Decimal(value) * (Decimal(10) ** exp)).quantize(
            Decimal(1), rounding=ROUND_HALF_EVEN)
        return cls(int(minor), currency)

    def to_decimal(self):
        return Decimal(self.amount) / (Decimal(10) ** EXPONENTS[self.currency])

    def _same(self, other):
        if not isinstance(other, Money) or other.currency != self.currency:
            raise ValueError("currency mismatch")

    def __add__(self, other):
        self._same(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other):
        self._same(other)
        return Money(self.amount - other.amount, self.currency)

    def times(self, quantity):
        if type(quantity) is not int:
            raise TypeError("quantity must be an int")
        return Money(self.amount * quantity, self.currency)

    def __str__(self):
        return f"{self.to_decimal():f} {self.currency}"


def convert(money, rate, currency):
    """Convert with `rate` units of `currency` per unit of money.currency,
    straight in minor units (no detour through major units)."""
    scale = Decimal(10) ** (EXPONENTS[check_currency(currency)] - EXPONENTS[money.currency])
    return Money(int(money.amount * rate * scale), currency)
