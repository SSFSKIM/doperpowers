# case2 — answer key (never show to reviewers)

**Scenario.** A dependency-free TypeScript shipping-quote service in four
modules that call each other: `rates.ts` (weight-tier table, zone multipliers,
`baseRateFor`), `discounts.ts` (promo table, `resolvePromos`, discount math),
`quote.ts` (`quoteShipment`), and `api.ts` (`handleQuote` over an untrusted JSON
body, plus a legacy `quickEstimate` the marketing widget calls). The patch adds
an itemized `QuoteBreakdown` and moves all internal money arithmetic from
rounded dollar floats to integer cents.

**Seeded classes: L2, L1, L3.** `case2-b2` (L2) is the cross-file contract
break: `baseRateFor` keeps its name and its `number` return type but changes
unit from dollars to cents, `quote.ts` is updated to match, and the other
caller — `quickEstimate` in `api.ts`, which the patch does touch elsewhere in
the same file — still formats the value as dollars, so the widget shows
"310.00" for a parcel that costs $3.10. Because both units are `number`, the
TypeScript compiler is silent. `case2-b1` (L1) is in the rewritten `tierFor`:
the loop `weightKg <= tier.maxKg` became `TIERS.find(tier => weightKg <
tier.maxKg)`, which contradicts the "inclusive upper bound" documented on
`WeightTier.maxKg` and in the README, so exactly 1 kg, 5 kg and 20 kg parcels
are priced one tier too high. `case2-b3` (L3) is the guard the refactor removed:
`quoteShipment`'s `RangeError` check on a non-positive or non-finite weight did
not survive the move into `buildBreakdown`, and `handleQuote`'s matching catch
block was deleted with it, so weight 0 prices at $2.50, weight -3 prices at $0,
and `NaN` returns HTTP 200 with `"total": null` — while the README's Validation
section still promises a 400.

**Baits (all correct and intentional).** (1) The rounding direction changes:
insurance surcharge uses `Math.floor` and percentage discounts use `Math.ceil`,
so quotes move by up to a cent against the old float behaviour. It looks like
sloppy money handling in two directions but it is a deliberate, one-directional
"remainder goes to the customer" policy stated in the `discountCents` docstring,
the `buildBreakdown` comment, the README Money section and `intent.md`. (2)
`resolvePromos` loses its `if (!codes) return []` guard and narrows its
parameter from `string[] | undefined` to `string[]`; this looks like a deleted
null check but the sole caller now passes `req.promoCodes ?? []` and the type
system enforces it. (3) Promo codes are deduplicated before resolution, which
silently changes stacking behaviour for a repeated code — intentional, stated in
`intent.md` and in the `distinctCodes` docstring.
