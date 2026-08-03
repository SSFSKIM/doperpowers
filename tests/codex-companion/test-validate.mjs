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
// An enum whose members are objects or arrays. A parsed value can never be
// reference-equal to a schema literal, so identity comparison rejected every
// structurally-correct payload — and burned the single repair turn proving it.
const STRUCTURAL = {
  type: "object", required: ["target"],
  properties: {
    target: { enum: [{ type: "baseBranch", branch: "main" }, { type: "uncommittedChanges" }, ["a", "b"]] }
  }
};
assert.deepEqual(validateSchema({ target: { type: "baseBranch", branch: "main" } }, STRUCTURAL), []);
assert.deepEqual(validateSchema({ target: { type: "uncommittedChanges" } }, STRUCTURAL), []);
assert.deepEqual(validateSchema({ target: ["a", "b"] }, STRUCTURAL), []);
assert.ok(validateSchema({ target: { type: "baseBranch", branch: "other" } }, STRUCTURAL)
  .some(e => e.includes("enum")), "a structurally different member is still rejected");
assert.ok(validateSchema({ target: ["b", "a"] }, STRUCTURAL)
  .some(e => e.includes("enum")), "array order is part of the value");
// Scalars keep behaving exactly as before.
assert.deepEqual(validateSchema("P0", { enum: ["P0", "P1"] }), []);
assert.ok(validateSchema("P2", { enum: ["P0", "P1"] }).length === 1);

console.log("test-validate: ok");
