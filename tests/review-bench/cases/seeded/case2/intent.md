# Itemized quotes, and money in integer cents

Support keeps getting "why is it $11.47?" tickets and we have nothing to show
the customer. This change makes the quote itemized end to end.

* `buildBreakdown` is the new core: it returns the `QuoteLine[]` that make up a
  quote — base, residential, insurance, discount — plus the subtotal, the
  discount and the total. `quoteShipment` becomes a thin wrapper that converts
  the total for its existing callers, and `POST /quote` now returns the lines
  alongside the total.

* All internal arithmetic moves to **integer cents**. The tier table, the promo
  table and every `QuoteLine` are cents; `centsToDollars` converts once, at the
  edge, where a handler builds its reply. The old approach — floats plus a
  `roundDollars` call after every operation — was what produced the off-by-a-cent
  totals in the ledger reconciliation reports.

* Rounding policy is now explicit and one-directional: surcharges round **down**
  (`Math.floor` on insurance), percentage discounts round **up** (`Math.ceil`).
  Both remainders go to the customer. Expect quotes to move by at most one cent
  against the old float behaviour.

* Repeated promo codes are collapsed before resolution, so `["FLAT5","flat5"]`
  is worth one $5 credit rather than two. Previously the same code, spelled two
  ways, stacked with itself.

* `resolvePromos` now takes a plain `string[]`. The `undefined` case is handled
  by its only caller, which defaults `req.promoCodes` to `[]` before deduping.

Not in scope: the tier boundaries, the zone multipliers and the promo table
values are unchanged in meaning — only their units changed.
