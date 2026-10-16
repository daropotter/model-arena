"""Cart data model."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Item:
    sku: str
    unit_price: Decimal
    qty: int

    def __post_init__(self):
        if not isinstance(self.unit_price, Decimal):
            raise TypeError("unit_price must be a Decimal")
        if self.unit_price < 0:
            raise ValueError(f"negative price: {self.unit_price}")
        if self.qty < 1:
            raise ValueError(f"qty must be at least 1: {self.qty}")


@dataclass(frozen=True)
class Coupon:
    code: str
    percent: int


class Cart:
    def __init__(self, items=None, coupons=[]):
        self.items = list(items) if items else []
        self.coupons = coupons

    def add(self, item):
        self.items.append(item)

    def add_coupon(self, coupon):
        self.coupons.append(coupon)

    def quantity(self):
        return sum(item.qty for item in self.items)
