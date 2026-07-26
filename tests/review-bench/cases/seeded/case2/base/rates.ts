/** The weight-tier table and the base rate built from it. */

export type Zone = "domestic" | "regional" | "international";

export interface WeightTier {
  /**
   * Inclusive upper bound of the tier in kilograms: a parcel weighing exactly
   * `maxKg` is priced in this tier, not in the next one up.
   */
  maxKg: number;
  /** Flat handling charge for anything in this tier, in dollars. */
  handlingDollars: number;
  /** Charge per kilogram inside this tier, in dollars. */
  perKgDollars: number;
}

export const TIERS: WeightTier[] = [
  { maxKg: 1, handlingDollars: 2.5, perKgDollars: 1.2 },
  { maxKg: 5, handlingDollars: 4.0, perKgDollars: 0.95 },
  { maxKg: 20, handlingDollars: 7.5, perKgDollars: 0.8 },
  { maxKg: Infinity, handlingDollars: 12.0, perKgDollars: 0.65 },
];

export const ZONE_MULTIPLIER: Record<Zone, number> = {
  domestic: 1,
  regional: 1.35,
  international: 2.4,
};

/** Round a dollar amount to the nearest cent. */
export function roundDollars(value: number): number {
  return Math.round(value * 100) / 100;
}

/** The tier a parcel of `weightKg` is priced in. */
export function tierFor(weightKg: number): WeightTier {
  for (const tier of TIERS) {
    if (weightKg <= tier.maxKg) {
      return tier;
    }
  }
  return TIERS[TIERS.length - 1];
}

/**
 * The base rate for a parcel, in dollars, before surcharges and discounts.
 */
export function baseRateFor(zone: Zone, weightKg: number): number {
  const tier = tierFor(weightKg);
  const beforeZone = tier.handlingDollars + tier.perKgDollars * weightKg;
  return roundDollars(beforeZone * ZONE_MULTIPLIER[zone]);
}
