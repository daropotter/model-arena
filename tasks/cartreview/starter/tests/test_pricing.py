import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shopcart.models import Cart, Coupon, Item  # noqa: E402
from shopcart.pricing import subtotal, total  # noqa: E402


class PricingTest(unittest.TestCase):
    def test_subtotal(self):
        cart = Cart([Item("a", Decimal("2.50"), 2), Item("b", Decimal("1.00"), 1)])
        self.assertEqual(subtotal(cart), Decimal("6.00"))

    def test_empty_cart(self):
        self.assertEqual(total(Cart()), Decimal("0"))

    def test_item_validation(self):
        with self.assertRaises(ValueError):
            Item("a", Decimal("1"), 0)

    def test_half_up_rounding(self):
        cart = Cart([Item("a", Decimal("0.125"), 1)])
        self.assertEqual(total(cart), Decimal("0.13"))

    def test_coupon(self):
        cart = Cart([Item("a", Decimal("20.00"), 2)], coupons=[Coupon("TEN", 10)])
        self.assertEqual(total(cart), Decimal("36.00"))


if __name__ == "__main__":
    unittest.main()
