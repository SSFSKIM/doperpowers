---
name: writing-skills
description: Doctrine for writing text another agent will execute, and for testing it by its stakes. For creating or editing a skill, a registered agent definition, a worker protocol or a dispatch-prompt template, or verifying a skill before it is relied on.
---

# Writing Skills

## What a skill is for

This applies to any authored agent behavior — a skill, a subagent or
dispatch prompt, a worker protocol. The reader is a model either way,
and the same economics hold. A one-off brief for a subagent needs this
section and nothing below it.

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
observation is its license; the skill states the reason, not the case. Reasons travel further
than bans: "never `HEAD~1` — it silently drops all but the last commit"
lets the reader recognize when the rule applies and when it doesn't; a
bare "never" teaches nothing and invites negotiation.

Generalize the rule; don't state the case. A case-study finding
encoded as-is covers only that case — distill it into the principle it taught,
so the reader recognizes the next instance that doesn't look like the
first.

Write for the weakest model that will actually consume the skill. A
worker-facing prompt template can justify denser scaffolding than a
skill read by frontier orchestrators.

Before calling a draft done, walk it line by line and ask of each line
whether it rightfully claims its place. A line earns it only by
changing behavior the reader wouldn't already produce; cut the rest. A
draft that survives this pass is normally much shorter than the one
that entered it.

## What stays, where it lives, what binds

- **The line is what the reader can derive against what it cannot.**
  Kept: a measured value, a contract another party depends on (a format
  that is parsed, a field that is read), a gotcha, your human partner's
  taste, the reason behind a rule. Cut: generic procedure, a restated
  default, anything already said elsewhere. What a tool does is the
  first kind; how to use it is usually the second.
- **Where a text loads decides what it costs.** A skill's description,
  a loaded tool's description and a root CLAUDE.md are in context for
  every session on every turn. The rest is scoped: a nested CLAUDE.md
  attaches the first time a session reads a file beneath it, an output
  style when it is selected, a deferred tool's schema when it is loaded,
  a skill body when invoked, a supporting file when read. A line goes in
  the narrowest of these that still reaches its reader, which is often
  the scoped file it is already in: heavy reference in a supporting
  file, flags behind `--help`, other skills named
  (`doperpowers:test-driven-development`) and never `@`-linked, which
  loads the file at once.
- **Text that should not bind is removed, or moved behind a read the
  agent chooses.** Softened in place ("consider", "you may") it still
  steers: a model that follows its context closely takes what it was
  shown as what is wanted.
- **A kept rule carries its reason**, so a later author can tell when it
  no longer applies and retire it. The incident behind it (the date, the
  model, the counts) belongs in the commit message and the spec.
- **One home per rule.** Stated twice, it is paid for twice and drifts
  into two rules; any other place points to its home.

## What is a skill?

A reference for a technique, a pattern or a tool that is reused across
work: a directory holding `SKILL.md` and, for heavy reference (100+
lines) or a reusable tool, supporting files. Not worth one: a one-off
solution, standard practice documented well elsewhere, a
project-specific convention (the project's instructions file holds
those), or anything a validator can enforce — automate that;
documentation is for judgment calls.

Frontmatter requires `name` (letters, numbers, hyphens) and
`description`, 1024 characters together
([agentskills.io/specification](https://agentskills.io/specification)).
Personal skills live in `~/.claude/skills/` on Claude Code; Codex,
Copilot CLI and Gemini CLI also read `~/.agents/skills/`.

Anthropic's guide is
[Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).
This skill departs from it twice: steps are kept for an observed
failure, where the guide teaches workflows as copyable checklists; and
testing follows stakes, where the guide asks every skill for a fixed
set of evaluations.

## The description

The description is in every session's context, and it is what a future
agent reads to decide whether to load the skill. Its parts, in order:
what the skill holds, then the situations it serves, in the third
person.

```
description: The board — a repository's ticket backlog — with its states, its commands and its conventions. For registering or searching tickets, taking a ticket, or closing it out.
```

- **It is an offer.** Worded as a command over a class of work ("Use
  when starting any …"), it reads as a mandate in every session that
  loads it; the skill is there for the agent to reach for.
- **The situations are named concretely**: the symptoms, the tool names,
  the words an agent would search for. They are how the skill is found.
- **Steps stay out of it.** A procedure summarized in a description gets
  followed in place of the body: a description that said "code review
  between tasks" produced one review where the body required two.

## Flowcharts and examples

Use a flowchart only for a genuinely non-obvious decision — an A-vs-B
choice agents get wrong, a loop they exit too early. Never for reference
material, linear instructions, or code. `graphviz-conventions.dot` in
this directory has style rules; `render-graphs.js ../some-skill` renders
a skill's graphs to SVG for your human partner.

One excellent example beats many mediocre ones: complete, runnable,
commented for WHY, drawn from a real scenario, in the single most
relevant language. Agents port well.

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

## Testing, by stakes

How hard to test follows what a wrong text would cost and the evidence
behind what is being changed. It applies to text that persists (a skill,
an agent definition, a protocol, a template), not to a one-off brief.

- **A cut of duplicate, derivable, dead or wrong text** ships on review
  alone.
- **New guidance** answers a failure that was observed or is structural.
  A control run without it shows whether the failure exists on the
  models that will read it: a control that does not fail leaves nothing
  to fix, and guidance written without one encodes what its author
  imagined.
- **Removing or weakening a rule with an incident or an eval behind it**
  takes a control-versus-variant run on today's readers first. Where
  that costs more than the change is worth, the rule stays, restated
  with its reason.
- **A rule that cuts against its reader's immediate goal** gets a
  pressure run:
  [testing-skills-with-subagents.md](testing-skills-with-subagents.md).

The control run, which is also how wording is compared:

1. One fresh-context sample per call — a raw API call or single-shot
   subagent. System prompt = the realistic context the guidance will
   live in (the full skill or prompt template, not the guidance in
   isolation); user message = a task that tempts the failure.
2. A no-guidance control beside every variant.
3. 5+ reps per variant. Single samples lie.
4. Manually read every flagged match — template echoes and quoted
   counter-examples masquerade as hits; automated counts overstate both
   failure and success.
5. Variance is a metric. When guidance lands, reps converge on the same
   shape; five interpretations across five reps means the wording isn't
   binding — tighten the form before adding words.

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
