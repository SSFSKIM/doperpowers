// The review panel: one lens-free native sweep, up to five diff-derived
// scalpel lenses, and one binding verifier. This file is a pure orchestration
// script on the `workflow` verb's engine — every model judgment lives in a
// turn, everything else here is deterministic.
export const meta = { name: "code-review", description: "Multi-lens codex review panel: native sweep + diff-derived scalpels + one binding verifier" };

// The panel's mandate cap is the owner's, not the model's: it binds the derived
// lenses and a caller's `args.lenses` alike.
const MAX_LENSES = 5;

const DERIVER_SCHEMA = {
  type: "object", required: ["lenses"],
  properties: { lenses: { type: "array", items: { type: "string" } } }
};

const DERIVER_PROMPT = (base) => `You are preparing a multi-reviewer code-review panel for the diff between merge-base(HEAD, ${base}) and HEAD in this repository. Run \`git diff $(git merge-base HEAD ${base}) --stat\` and skim the largest hunks with \`git diff\`.

Write between 0 and 5 scalpel lens mandates. Each mandate is AT MOST TWO SIMPLE SENTENCES naming one structural risk surface of THIS diff (example of the calibre required: "Pay attention to authorization and actor-identity assumptions in the changed API routes."). A separate lens-free reviewer already sweeps everything, so a mandate must earn its slot: fewer, sharper mandates beat coverage padding — a small single-concern diff deserves zero or one. Consider, only where this diff actually raises them: changed-logic accuracy, cross-file contract impact, behavior lost with removed/moved code, security surface, performance/resources.

Return JSON: {"lenses": ["...", ...]}`;

export default async function run({ agent, log, args }) {
  if (!args?.base) throw new Error("code-review workflow requires args.base");
  const base = args.base;
  const finderModel  = args.finderModel  ?? "gpt-5.6-sol";
  const finderEffort = args.finderEffort ?? "xhigh";

  let lenses = args.lenses;
  if (!Array.isArray(lenses)) {
    const derived = await agent(DERIVER_PROMPT(base), {
      model: args.finderModel ?? "gpt-5.6-sol", effort: "medium",
      schema: DERIVER_SCHEMA, label: "lens-deriver"
    });
    lenses = derived.lenses;
  }
  lenses = lenses.slice(0, MAX_LENSES).map((l) => String(l).trim()).filter(Boolean);
  log(`panel: sweep + ${lenses.length} scalpels`);

  // … Tasks 3–4 continue here: finder fan-out, verifier, assembly. Until they
  // land the run reports what it derived, so the lens contract is observable.
  return { lenses, base, finderModel, finderEffort };
}
