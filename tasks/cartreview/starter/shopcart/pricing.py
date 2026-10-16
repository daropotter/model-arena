"""Cart pricing. README.md is the pricing contract."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
BULK_MIN_QTY = 10
BULK_RATE = 0.05


def subtotal(cart):
    return sum((item.unit_price * item.qty for item in cart.items), Decimal("0"))


def bulk_discount(cart, amount):
    if cart.quantity() > BULK_MIN_QTY:
        return amount * BULK_RATE
    return Decimal("0")


def apply_coupon(amount, coupon):
    return amount - amount * coupon.percent / 100


def total(cart):
    amount = subtotal(cart)
    amount -= bulk_discount(cart, amount)
    for coupon in cart.coupons:
        amount = apply_coupon(amount, coupon)
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)
