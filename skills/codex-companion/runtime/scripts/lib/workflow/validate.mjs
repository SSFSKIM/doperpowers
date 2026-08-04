// Minimal structural JSON-schema validator for workflow agent() results.
//
// The runtime's parseStructuredOutput is JSON.parse-only, so a syntactically
// valid but wrong-shaped payload passes silently (false green). This closes
// that hole for the subset of JSON Schema the workflow engine actually uses:
// `type` (a single name or a union array), `properties`, `required`, `items`,
// `enum`. Unknown keywords are ignored on purpose — the same schema also rides
// `outputSchema` server-side, where the full validator lives.

function matchesType(value, t) {
  return (t === "object" && value !== null && typeof value === "object" && !Array.isArray(value)) ||
    (t === "array" && Array.isArray(value)) ||
    (t === "string" && typeof value === "string") ||
    (t === "boolean" && typeof value === "boolean") ||
    (t === "number" && typeof value === "number") ||
    (t === "integer" && Number.isInteger(value)) ||
    (t === "null" && value === null);
}

// Enum membership is STRUCTURAL. A member can be an object or an array (a review
// target, a tuple), and a value that came out of JSON.parse is never the same
// reference as the schema literal beside it — so identity comparison rejected
// every structurally correct payload and spent the run's single repair turn
// proving it. Object key ORDER is not part of a JSON value, which is why this is
// a walk and not a stringify comparison: a model that emits the same object with
// its keys in another order emitted the same value.
function sameJsonValue(a, b) {
  if (a === b) return true;
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    return a.length === b.length && a.every((item, i) => sameJsonValue(item, b[i]));
  }
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length &&
    keys.every((key) => Object.hasOwn(b, key) && sameJsonValue(a[key], b[key]));
}

export function validateSchema(value, schema, path = "$") {
  const errors = [];
  if (!schema || typeof schema !== "object") return errors;
  // A union `type` (`["string", "null"]`) is how a strict output schema spells
  // an OPTIONAL property: the API's strict mode requires every property to be
  // listed in `required`, so "absent" has to be expressed as an allowed null.
  const types = schema.type ? (Array.isArray(schema.type) ? schema.type : [schema.type]) : [];
  if (types.length > 0 && !types.some((t) => matchesType(value, t))) {
    errors.push(`${path}: expected ${types.join("|")}`);
    return errors;
  }
  if (schema.enum && !schema.enum.some((member) => sameJsonValue(member, value))) {
    errors.push(`${path}: not in enum [${schema.enum.join(", ")}]`);
  }
  if (types.includes("object") && matchesType(value, "object")) {
    for (const key of schema.required ?? []) {
      if (!(key in value)) errors.push(`${path}: missing required "${key}" (have: ${Object.keys(value).join(",") || "none"})`);
    }
    for (const [key, sub] of Object.entries(schema.properties ?? {})) {
      if (key in value) errors.push(...validateSchema(value[key], sub, `${path}.${key}`));
    }
  }
  if (types.includes("array") && Array.isArray(value) && schema.items) {
    value.forEach((item, i) => errors.push(...validateSchema(item, schema.items, `${path}[${i}]`)));
  }
  return errors;
}
