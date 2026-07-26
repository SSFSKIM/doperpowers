/** Promo codes and what they are worth. */

import { roundDollars } from "./rates";

export type PromoKind = "percent" | "fixed";

export interface Promo {
  code: string;
  kind: PromoKind;
  /** For `percent`, a percentage 0-100. For `fixed`, an amount in dollars. */
  value: number;
  /** Smallest pre-discount subtotal the promo may be used against, in dollars. */
  minSubtotalDollars: number;
}

export const PROMOS: Promo[] = [
  { code: "WELCOME10", kind: "percent", value: 10, minSubtotalDollars: 0 },
  { code: "BULK25", kind: "percent", value: 25, minSubtotalDollars: 200 },
  { code: "FLAT5", kind: "fixed", value: 5, minSubtotalDollars: 20 },
  { code: "SHIPFREE", kind: "percent", value: 100, minSubtotalDollars: 500 },
];

/** Promo codes are case- and whitespace-insensitive. */
export function normalizeCode(raw: string): string {
  return raw.trim().toUpperCase();
}

/** Look up the promos named by `codes`; unknown codes are ignored. */
export function resolvePromos(codes: string[] | undefined): Promo[] {
  if (!codes) {
    return [];
  }
  const resolved: Promo[] = [];
  for (const raw of codes) {
    const promo = PROMOS.find((candidate) => candidate.code === normalizeCode(raw));
    if (promo !== undefined) {
      resolved.push(promo);
    }
  }
  return resolved;
}

/**
 * What `promos` are worth against `subtotalDollars`.
 *
 * Every promo is computed against the same pre-discount subtotal, so stacking
 * two promos never compounds. The result is capped at the subtotal.
 */
export function discountDollars(promos: Promo[], subtotalDollars: number): number {
  let total = 0;
  for (const promo of promos) {
    if (subtotalDollars < promo.minSubtotalDollars) {
      continue;
    }
    if (promo.kind === "percent") {
      total += roundDollars((subtotalDollars * promo.value) / 100);
    } else {
      total += promo.value;
    }
  }
  return roundDollars(Math.min(total, subtotalDollars));
}
