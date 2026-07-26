# quote-service

A tiny, dependency-free shipping quote service.

## Modules

* `rates.ts` — the weight-tier table, the zone multipliers, and `baseRateFor`,
  which prices a parcel before surcharges and discounts.
* `discounts.ts` — the promo table, code normalization, and the discount a set
  of promos is worth against a given subtotal.
* `quote.ts` — `quoteShipment`, which combines base rate, surcharges and
  discounts into the amount we charge.
* `api.ts` — the two request handlers: `handleQuote` (the real endpoint, takes
  an untrusted JSON body) and `quickEstimate` (a legacy endpoint the marketing
  widget still calls for a base-rate-only number).

## Money

Amounts are dollars, rounded to the cent with `roundDollars`.

## Validation

`handleQuote` answers `400` — never a price — for a body that is not a JSON
object, a zone it does not know, a non-numeric weight, or a weight that is not
a positive finite number.

## Weight tiers

`maxKg` is the **inclusive** upper bound of a tier: a parcel weighing exactly
`maxKg` is priced in that tier, not the next one up. The last tier has no upper
bound.

## Usage

```ts
import { quoteShipment } from "./quote";

const quote = quoteShipment({
  zone: "regional",
  weightKg: 3.2,
  residential: true,
  promoCodes: ["welcome10"],
});
console.log(quote.totalDollars, quote.currency);
```
