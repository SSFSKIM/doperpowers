import assert from "node:assert";
import { validateSchema } from "../../skills/codex-companion/runtime/scripts/lib/workflow/validate.mjs";

const FINDER = {
  type: "object", required: ["findings"],
  properties: { findings: { type: "array", items: {
    type: "object", required: ["id", "verdict"],
    properties: { id: { type: "string" },
      verdict: { type: "string", enum: ["CONFIRMED", "REFUTED"] } } } } }
};
assert.deepEqual(validateSchema({ findings: [] }, FINDER), []);
assert.deepEqual(validateSchema({ findings: [{ id: "a", verdict: "CONFIRMED" }] }, FINDER), []);
// syntactically-valid JSON, wrong shape — the exact false-green from the spec review:
assert.ok(validateSchema({ finding: [] }, FINDER).some(e => e.includes("findings")));
assert.ok(validateSchema({ findings: [{ id: 1, verdict: "CONFIRMED" }] }, FINDER)
  .some(e => e.includes(".id") && e.includes("string")));
assert.ok(validateSchema({ findings: [{ id: "a", verdict: "MAYBE" }] }, FINDER)
  .some(e => e.includes("enum")));
assert.ok(validateSchema("nope", FINDER).some(e => e.includes("object")));
assert.deepEqual(validateSchema(3, { type: "integer" }), []);
assert.ok(validateSchema(3.5, { type: "integer" }).length === 1);

// Union types: how a strict output schema spells an optional property (the API
// requires every property in `required`, so absent is expressed as null).
const NULLABLE = {
  type: "object", required: ["id", "priority"],
  properties: {
    id: { type: "string" },
    priority: { type: ["string", "null"], enum: ["P0", "P1", null] }
  }
};
assert.deepEqual(validateSchema({ id: "a", priority: "P1" }, NULLABLE), []);
assert.deepEqual(validateSchema({ id: "a", priority: null }, NULLABLE), []);
assert.ok(validateSchema({ id: "a", priority: 7 }, NULLABLE)
  .some(e => e.includes("expected string|null")));
assert.ok(validateSchema({ id: "a", priority: "P9" }, NULLABLE).some(e => e.includes("enum")));
// A union that includes "object"/"array" still recurses into the branch the
// value actually took, and still enforces `required` on it.
const UNION_OBJ = {
  type: ["object", "null"], required: ["n"], properties: { n: { type: "number" } }
};
assert.deepEqual(validateSchema(null, UNION_OBJ), []);
assert.ok(validateSchema({}, UNION_OBJ).some(e => e.includes('missing required "n"')));
assert.ok(validateSchema({ n: "x" }, UNION_OBJ).some(e => e.includes("expected number")));
console.log("test-validate: ok");
