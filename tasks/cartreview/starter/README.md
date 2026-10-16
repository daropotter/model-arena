# shopcart

Prices a shopping cart. All money is `decimal.Decimal`; floats are never
used for money.

## Pricing rules

1. The subtotal is the sum of `unit_price * qty` over all items.
2. The total is rounded to whole cents once, at the very end, with
   `ROUND_HALF_UP` (0.125 becomes 0.13).
3. Bulk discount: a cart holding 10 or more units in total (the sum of
   `qty` over all items) gets 5% off its subtotal.
4. Coupons take a whole-number `percent` from 1 to 100 off. A coupon with
   any other percent is rejected with `ValueError` when it is created.
   Coupons apply after the bulk discount, in the order they were added,
   each to the running amount. A coupon added to one cart never affects
   another cart.

## Tests

    python3 tests/test_pricing.py
