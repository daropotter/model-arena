# Bulk discount and percent coupons (SHOP-112)

Implements pricing rules 3 and 4 from README.md:

- carts with 10 or more units get 5% off the subtotal;
- percent coupons, which stack and apply after the bulk discount.

Also switches the final rounding to `ROUND_HALF_UP` (README rule 2).
`round()` on a `Decimal` uses banker's rounding, and finance reported a
0.125 line totalling 0.12 instead of 0.13.

Tests: added a rounding test and a coupon test; all tests pass.
