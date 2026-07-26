/** Request handlers. No framework: a handler takes a body and returns a reply. */

import { Zone, ZONE_MULTIPLIER, baseRateFor, roundDollars } from "./rates";
import { QuoteRequest, quoteShipment } from "./quote";

export interface Reply {
  status: number;
  body: Record<string, unknown>;
}

function isZone(value: unknown): value is Zone {
  return typeof value === "string" && value in ZONE_MULTIPLIER;
}

/** Parse an untrusted JSON body into a QuoteRequest, or explain what is wrong. */
export function parseQuoteRequest(body: unknown): QuoteRequest | string {
  if (typeof body !== "object" || body === null) {
    return "body must be a JSON object";
  }
  const raw = body as Record<string, unknown>;

  if (!isZone(raw.zone)) {
    return "zone must be one of: " + Object.keys(ZONE_MULTIPLIER).join(", ");
  }
  if (typeof raw.weightKg !== "number") {
    return "weightKg must be a number";
  }

  const req: QuoteRequest = { zone: raw.zone, weightKg: raw.weightKg };

  if (typeof raw.residential === "boolean") {
    req.residential = raw.residential;
  }
  if (typeof raw.insuredValueDollars === "number") {
    req.insuredValueDollars = raw.insuredValueDollars;
  }
  if (Array.isArray(raw.promoCodes)) {
    req.promoCodes = raw.promoCodes.filter(
      (code): code is string => typeof code === "string"
    );
  }

  return req;
}

/** POST /quote */
export function handleQuote(body: unknown): Reply {
  const parsed = parseQuoteRequest(body);
  if (typeof parsed === "string") {
    return { status: 400, body: { error: parsed } };
  }

  try {
    const quote = quoteShipment(parsed);
    return {
      status: 200,
      body: { total: quote.totalDollars, currency: quote.currency },
    };
  } catch (err) {
    if (err instanceof RangeError) {
      return { status: 400, body: { error: err.message } };
    }
    throw err;
  }
}

/**
 * GET /estimate — legacy endpoint for the marketing widget.
 *
 * Base rate only: no surcharges, no promos. The widget renders the string
 * as-is next to a dollar sign.
 */
export function quickEstimate(zone: Zone, weightKg: number): string {
  return roundDollars(baseRateFor(zone, weightKg)).toFixed(2);
}
