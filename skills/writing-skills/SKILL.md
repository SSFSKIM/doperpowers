---
name: writing-skills
description: Use when creating new skills, editing existing skills, or verifying skills work before deployment
---

# Writing Skills

## What a skill is for

The model reading your skill carries its own situational judgment. A
skill's job is to supply what that judgment cannot derive on its own —
domain facts, validated tribal knowledge (the incident, the footgun, the
exact command), interfaces, and defaults with their reasons — and to
leave room for the reader to think. It is not to re-teach what the model
already knows, and not to replace judgment with rules.

Two tests for every line you write:

1. **Could a capable agent derive this itself?** Then cut it.
2. **Does this line close off a judgment the agent should be making?**
   Then rephrase it as a reason or a default, not a mandate.

A hard constraint earns its place only when it maps to a validated
failure — observed or structural, never hypothetical — and the
observation is its license: cite it in the skill. Reasons travel further
than bans: "never `HEAD~1` — it silently drops all but the last commit"
lets the reader recognize when the rule applies and when it doesn't; a
bare "never" teaches nothing and invites negotiation.

Write for the weakest model that will actually consume the skill. A
worker-facing prompt template can justify denser scaffolding than a
skill read by frontier orchestrators.

## Overview

**Writing skills is Test-Driven Development applied to process
documentation.** Run scenarios without the skill (baseline — watch the
failure), write the skill against those observed failures, verify agents
now succeed, and refine what still misses.

**Core principle:** if you didn't watch an agent fail without the skill,
you don't know if the skill teaches the right thing.

**Personal skills live in your runtime's skills directory** —
`~/.claude/skills/` on Claude Code. Codex, Copilot CLI, and Gemini CLI
also recognize `~/.agents/skills/` as a cross-runtime alias.

**Official guidance:** for Anthropic's skill authoring best practices,
see anthropic-best-practices.md — an external reference; where it
conflicts with this repo's tested philosophy, this skill governs.

## What is a skill?

A reference guide for proven techniques, patterns, or tools — reusable
across projects. Not a narrative about how you solved a problem once.

**Create one when** the technique wasn't intuitively obvious, you'd
reference it again, and it applies broadly. **Don't create one for**
one-off solutions, standard practice already documented well elsewhere,
project-specific conventions (those go in the project's instructions
file), or anything enforceable with a validator — automate that; save
documentation for judgment calls.

Three rough types, which test differently (see Testing below):
**technique** (concrete method with steps), **pattern** (way of thinking
about a problem class), **reference** (API docs, syntax, tools).

## Structure

```
skills/
  skill-name/
    SKILL.md              # Main reference (required)
    supporting-file.*     # Only for heavy reference (100+ lines) or reusable tools
```

Keep principles, concepts, and short code patterns inline in SKILL.md;
split out heavy API reference and runnable tools. Shape the sections to
the skill — a typical arc is: overview with the core principle, when to
use, the content itself, common mistakes — but form follows the
material, not a fixed template.

**Frontmatter:** two required fields, `name` and `description`, max 1024
characters total (see [agentskills.io/specification](https://agentskills.io/specification)).
Name with letters, numbers, and hyphens; verb-first gerunds read best
(`creating-skills`, `root-cause-tracing`, `condition-based-waiting`).

## Getting discovered

The description is how future agents decide whether to load your skill.

- **Describe ONLY when to use it — never summarize the workflow.**
  Tested: a description that summarized the process ("code review
  between tasks") caused agents to follow the description and skip the
  skill body, missing the two-stage review the body required; a
  trigger-only description sent them into the body.
- Start with "Use when …", write in third person, and name concrete
  triggers: symptoms, situations, error messages, tool names, and the
  synonyms an agent would search for.
- Describe the problem (race conditions, flaky tests), not
  language-specific symptoms — unless the skill itself is
  technology-specific, in which case say so explicitly.

Token economy: every loaded skill costs context. Keep SKILL.md lean,
move heavy reference to supporting files, point at `--help` instead of
documenting flags, and cross-reference other skills by name
(`doperpowers:test-driven-development`) — never `@`-links, which
force-load the file into context immediately.

## Flowcharts and examples

Use a flowchart only for a genuinely non-obvious decision — an A-vs-B
choice agents get wrong, a loop they exit too early. Never for reference
material, linear instructions, or code. `graphviz-conventions.dot` in
this directory has style rules; `render-graphs.js ../some-skill` renders
a skill's graphs to SVG for your human partner.

One excellent example beats many mediocre ones: complete, runnable,
commented for WHY, drawn from a real scenario, in the single most
relevant language. Agents port well — one great example is enough.

## Match the form to the failure

Before writing guidance, classify the baseline failure. The form that
fixes one failure type measurably backfires on another.

| Baseline failure | Right form | Wrong form |
|---|---|---|
| Skips or violates a rule under pressure | State the reason and cite the observed failure; escalate to enforcement (see Last resort) only if re-testing shows the failure persists | Reaching for prohibition machinery by default |
| Complies, but output has the wrong shape (bloated prompt, buried verdict) | Positive recipe or contract: state what the output IS — its parts, in order | Prohibition list ("don't restate", "never narrate") |
| Omits a required element from something they already produce | Structural: a REQUIRED field or slot in the template they fill in | Prose reminders near the template |
| Behavior should depend on a condition | Conditional keyed to an observable predicate ("if the brief exists, reference it") | Unconditional rule + exemption clauses |

**Why prohibitions backfire on shaping problems:** in head-to-head
wording tests on dispatch-prompt guidance, the prohibition arm produced
clearly more of the unwanted content than the recipe arm (fully
separated distributions), and trended worse than even the no-guidance
control. A recipe leaves nothing to negotiate: the output matches the
stated shape or it doesn't.

**Rules for whichever form you pick:**

- **No nuance clauses.** "Don't X unless it matters" reopens the
  negotiation — appending a single nuance clause to a winning recipe
  degraded it from consistent to noisy in the same wording tests.
  Express a real exception as its own conditional on an observable
  predicate.
- **Exemption clauses don't scope.** "This limit doesn't apply to code
  blocks" still suppresses code blocks. If part of the output must be
  exempt, restructure so the rule can't reach it.

## Testing skills

Baseline first, always: run the scenario WITHOUT the skill and document
the exact failure — what the agent did, its reasoning verbatim. Then
write the minimal skill addressing those observed failures, re-run, and
refine what still misses. Writing the skill first reveals what YOU think
needs preventing, not what actually does.

Match the test to the skill type:

- **Technique / pattern skills** — application scenarios: can an agent
  apply it to a new case? Do the instructions have gaps? Does it know
  when NOT to apply the pattern?
- **Reference skills** — retrieval scenarios: can an agent find the
  right information and use it correctly? Are common cases covered?
- **Discipline skills** (rules with compliance costs) — pressure
  scenarios with combined pressures (time, sunk cost, authority,
  exhaustion). See
  [testing-skills-with-subagents.md](testing-skills-with-subagents.md)
  for scenario construction and the refinement loop.

**Micro-test wording before full scenarios.** Full pressure runs are the
final gate but slow per iteration; verify the wording itself first:

1. One fresh-context sample per call — a raw API call or single-shot
   subagent. System prompt = the realistic context the guidance will
   live in (the full skill or prompt template, not the guidance in
   isolation); user message = a task that tempts the failure.
2. Always include a no-guidance control. If the control doesn't exhibit
   the failure, there is nothing to fix — stop; don't author the
   guidance.
3. 5+ reps per variant. Single samples lie.
4. Manually read every flagged match — template echoes and quoted
   counter-examples masquerade as hits; automated counts overstate both
   failure and success.
5. Variance is a metric. When guidance lands, reps converge on the same
   shape; five interpretations across five reps means the wording isn't
   binding — tighten the form before adding words.

Test each skill before starting the next — batching untested skills is
deploying untested code. Commit when it passes.

## Last resort: enforcement machinery

Rationalization tables, red-flags lists, "no exceptions" prohibitions —
the toolkit exists and can work, but it is gated, not default. Reach for
it only when baseline testing shows a discipline failure that reasons
and a recalibrated form did NOT fix, and the skill's consumers include
models weak enough to need it. On frontier consumers the machinery is
net-negative (see the wording-test evidence above) — and every
prohibition list also ships a catalogue of the evasions it bans. When
you do use it: close loopholes explicitly and specifically ("don't keep
it as reference" works; "don't cheat" doesn't), and re-test until the
observed rationalizations stop appearing.

## Common mistakes

- **Narrative examples** ("in session 2025-10-03 we found…") — too
  specific to reuse.
- **Multi-language example dilution** — one great example; agents port.
- **Code in flowcharts, generic labels** (helper1, step3) — labels need
  semantic meaning; code belongs in markdown blocks.
- **Descriptions that summarize workflow** — the shortcut agents will
  take instead of reading the skill.
