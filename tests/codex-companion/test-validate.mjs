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
console.log("test-validate: ok");
