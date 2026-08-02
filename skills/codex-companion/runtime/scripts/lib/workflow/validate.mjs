// Minimal structural JSON-schema validator for workflow agent() results.
//
// The runtime's parseStructuredOutput is JSON.parse-only, so a syntactically
// valid but wrong-shaped payload passes silently (false green). This closes
// that hole for the subset of JSON Schema the workflow engine actually uses:
// `type`, `properties`, `required`, `items`, `enum`. Unknown keywords are
// ignored on purpose — the same schema also rides `outputSchema` server-side,
// where the full validator lives.

export function validateSchema(value, schema, path = "$") {
  const errors = [];
  if (!schema || typeof schema !== "object") return errors;
  if (schema.type) {
    const t = schema.type;
    const ok =
      (t === "object" && value !== null && typeof value === "object" && !Array.isArray(value)) ||
      (t === "array" && Array.isArray(value)) ||
      (t === "string" && typeof value === "string") ||
      (t === "boolean" && typeof value === "boolean") ||
      (t === "number" && typeof value === "number") ||
      (t === "integer" && Number.isInteger(value)) ||
      (t === "null" && value === null);
    if (!ok) { errors.push(`${path}: expected ${t}`); return errors; }
  }
  if (schema.enum && !schema.enum.includes(value)) {
    errors.push(`${path}: not in enum [${schema.enum.join(", ")}]`);
  }
  if (schema.type === "object") {
    for (const key of schema.required ?? []) {
      if (!(key in value)) errors.push(`${path}: missing required "${key}" (have: ${Object.keys(value).join(",") || "none"})`);
    }
    for (const [key, sub] of Object.entries(schema.properties ?? {})) {
      if (key in value) errors.push(...validateSchema(value[key], sub, `${path}.${key}`));
    }
  }
  if (schema.type === "array" && schema.items) {
    value.forEach((item, i) => errors.push(...validateSchema(item, schema.items, `${path}[${i}]`)));
  }
  return errors;
}
