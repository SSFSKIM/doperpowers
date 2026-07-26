/** Turning a request into the amount we charge. */

import { Zone, baseRateFor, roundDollars } from "./rates";
import { discountDollars, resolvePromos } from "./discounts";

export interface QuoteRequest {
  zone: Zone;
  weightKg: number;
  residential?: boolean;
  insuredValueDollars?: number;
  promoCodes?: string[];
}

export interface Quote {
  totalDollars: number;
  currency: "USD";
}

export const RESIDENTIAL_SURCHARGE_DOLLARS = 3.25;
export const INSURANCE_RATE = 0.01;

export function quoteShipment(req: QuoteRequest): Quote {
  if (!Number.isFinite(req.weightKg) || req.weightKg <= 0) {
    throw new RangeError("weightKg must be a positive, finite number");
  }

  const base = baseRateFor(req.zone, req.weightKg);

  let surcharges = 0;
  if (req.residential === true) {
    surcharges += RESIDENTIAL_SURCHARGE_DOLLARS;
  }
  if (req.insuredValueDollars !== undefined && req.insuredValueDollars > 0) {
    surcharges += roundDollars(req.insuredValueDollars * INSURANCE_RATE);
  }

  const subtotal = roundDollars(base + surcharges);
  const discount = discountDollars(resolvePromos(req.promoCodes), subtotal);

  return {
    totalDollars: roundDollars(subtotal - discount),
    currency: "USD",
  };
}
