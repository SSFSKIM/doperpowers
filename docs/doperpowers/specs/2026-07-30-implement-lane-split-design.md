# Implement Lane Split — Architect / Implementer / QAgent (2026-07-30)

> **Status:** design approved in-session (ideadump roadmapping, epic E1;
> grill record in the Decision Log below). Implementation sequencing is
> routed by the roadmap consolidation at the end of the roadmapping
> session — no skill/script edits land from this spec alone.
> **Substrate target:** the AI-native Postgres board and the cloud runtime
> (k8s + gVisor + cc-harness pods) per the 2026-07-30 cloud-native
> pipeline pivot. The current GitHub Issues board (doperpowers:issue-tracker
> v8) serves as the interim rendering and the future one-way mirror; every
> rule below is written substrate-neutrally against the state machine.

## Purpose

Today one implement worker carries a ticket from design judgment through
execution: it runs the gate, authors its own ExecPlan when the work needs
one, and drives to a PR — all on one model route. That couples two jobs
with opposite model economics: **plan authorship wants the frontier model**
(a bad plan is the most expensive artifact in the pipeline — it produces
confident wrong execution that the review loop catches only at PR time),
while **executing a finished plan is middle-class work**.

After this change, a big ticket relays through three scopes: an
**Architect** (Fable high/xhigh) grills, decides, and authors the plan —
with an agent council on the biggest work — then ends; an **Implementer**
(Opus medium/high) executes the finished plan without re-litigating it;
the **QAgent** (the reviewing-prs worker's role name, ONE Opus high)
reviews to a confident merge, dispatching fix waves to a dedicated
fix-wave agent (Opus medium). Small tickets skip the Architect entirely
and run today's direct path unchanged. The relay is encoded in board
states, so the dispatcher stays judgment-free.

What you can observe after: every plan document in the pipeline is
Fable-authored; Opus workers never author plans; design gaps discovered
downstream flow to a named state (`ready-for-architect`) instead of
leaking into `needs-human`; and the whole relay runs with no
orchestrator-judge — each phase ends by writing the board and dying.

## The relay

```
register ──► ready-for-architect ──► [Architect: gate → grill/council → plan] ──► ready-for-implementer
   │                ▲    │ down-shortcircuit ("pre-spec suffices")                        │
   │                │    └────────────────────────────────────────────────────────────────┤
   └──► ready-for-implementer ◄──────────────────────────────────────────────────────────┘
                    │
                    ├─ [Implementer: plan attached → execute; no plan → today's gate + DIRECT]
                    │        │ gate finds plan-need / genuine mid-build block
                    │        └────────────► ready-for-architect (escalation / return park)
                    └──► in-progress ──► in-review ──► [QAgent loop] ──► confident-ready ──► done
```

## State machine changes

`ready-for-agent` splits into two states; everything downstream of
`in-progress` is untouched.

| state | meaning | dispatched worker |
|---|---|---|
| `ready-for-architect` | pre-spec complete to today's ready-for-agent bar, and the work needs design/plan authorship | Architect (Fable high/xhigh) |
| `ready-for-implementer` | dispatchable to execution: either an Architect's plan is attached, or the ticket is small enough that the pre-spec is the plan | Implementer (Opus med/high) |

**Birth classification (registrar judgment, unsure → implementer).**
Whoever registers the ticket assigns the lane state: obvious
multi-milestone, novel-design, or cross-cutting work is born
`ready-for-architect`; everything else — including every unsure case —
is born `ready-for-implementer`. Misclassification is self-correcting
and cheap: the Implementer's gate escalates upward (below), and an Opus
gate costs far less than defaulting borderline tickets onto Fable.

**New legal transitions:**

1. **Architect completion** — `ready-for-architect → ready-for-implementer`,
   note REQUIRED: the plan's repo path plus a brief statement of context
   and intent. This is the Architect's closing artifact (symmetric to the
   Implementer's PR).
2. **Architect down-shortcircuit** — the ticket turned out small: same
   transition with note "pre-spec suffices as the plan"; no plan document
   authored.
3. **Implementer gate escalation** — a plan-less ticket's gate finds
   plan-need (multiple sequenced milestones, work that must survive
   context death, missing design decisions that are agent-answerable):
   `ready-for-implementer → ready-for-architect`, note required. This
   replaces the current practice of leaking design gaps into
   `needs-human`/`needs-info`.
4. **Return park** — mid-execution the plan proves genuinely blocked (not
   merely divergent): `in-progress → ready-for-architect`, note + the
   standard orientation summary. Divergence that can be absorbed is NOT a
   park — see the Implementer protocol.

**The park discriminant becomes a three-address system** (extends
issue-tracker's single authoritative copy): a decision or real-world
input only the human can provide → `needs-human`; missing knowledge
anyone could research → `needs-info`; **missing or broken design that an
agent can author → `ready-for-architect`**. `interactive-preferred`
survives unchanged for work whose core needs the human's live steering.

## Worker protocols

| role | model | scope | closing artifact |
|---|---|---|---|
| **Architect** | Fable high/xhigh | ticket gate → grill (batch parks) → track judgment → author ExecPlan or Spec → Impl Plan. **Ends at the plan** — no post-implementation review, no code | plan committed to the ticket branch + path/context/intent note + `ready-for-implementer` transition |
| **Implementer** | Opus med/high | dual mode: plan-execution (no intake gate — trust and drive) / DIRECT (plan-less small ticket, today's protocol verbatim). **No plan authorship** | PR (Validation Evidence + FOLLOW-UPS, unchanged) |
| **QAgent** | ONE Opus high | codex review rounds + fix-wave dispatch (reviewing-prs loop structure unchanged) | `confident-ready` (unchanged) |
| **fix-wave agent** | Opus medium | applies a review round's findings as a dispatched subagent (`agents/fix-wave.md`) | fixes committed for the next round |

**Architect = brainstorming in worker clothes.** The behavior protocol is
doperpowers:brainstorming plus decomposing, applied per-ticket: the ticket
gate is the scope assessment; unclear nontrivial decisions become a
`needs-human` park in the existing batch format (numbered questions, each
with a recommended answer — the format issue-tracker already owns and
`board-answer.sh` already relays; **no new batch-grill reference file**);
a goal too big for one unit routes to doperpowers:decomposing; children
are registered with lane states per the birth-classification rule. In
worker clothes, brainstorming's human-approval gate maps to the council
(below) plus parks — there is no synchronous human gate. A ticket whose
registrar wants a human spec-approval anyway says so in its body; the
Architect then parks `needs-human` at spec completion (ticket-level
configuration, not doctrine).

**No intake gate at the Implementer.** The Architect's phase carries the
quality machinery (council, spec review, plan review), so the plan is
presumed sound — the Implementer does not re-run the gate or re-judge the
design. When the codebase reveals divergence from the plan mid-execution,
the Implementer absorbs it under the living-spec doctrine (record in the
spec's Surprises/Revision Notes, adapt, drive to the end). Only a
genuinely blocked plan produces the return park (transition 4).

**Model pins ride dispatch, not protocols.** The engine-label semantics
(`engine:codex` opt-in per review-stack contract X4) are unchanged; the
lane state selects the worker protocol and its default model
(architect → Fable, implementer/QAgent → Opus). The QAgent's Opus-high
pin and the implementer's Opus default land via/with the review-stack
roadmap's C5 (doperpowers#32) and C6 (doperpowers#33) — this spec adds
the pins, not a parallel flip.

## Council scaling

Council cost scales with the artifact shape the Architect chooses (the
existing brainstorming track logic, applied by the Architect):

- **ExecPlan shape** (medium work; big-but-atomic): **solo Fable, no
  council.** The Architect grills the ticket, authors the ExecPlan, ends.
- **Spec → Impl Plan shape** (large/novel/high-stakes): the council —
  `doperpowers:critique` (design debate to convergence), the spec-review
  pass, and `doperpowers:plan-reviewer` on the implementation plan — all
  existing agents, reused.

## Skill topology

**Split doperpowers:implementing-tickets into two skills** (not a new
standalone skill): **`architecting`** and **`implementing`** — bare
gerunds, per the naming precedent set when `decomposing-goals` became
`decomposing`. Each skill IS its worker's protocol, exactly as
implementing-tickets is today:

- `architecting` — thin: role framing, the gate, the brainstorming/
  decomposing routing above, the batch-park format pointer, council
  scaling, the closing artifact contract. Expected to be light — most of
  its content is pointers into brainstorming, decomposing, and
  issue-tracker's single-copy schema.
- `implementing` — implementing-tickets minus the EXECPLAN-authoring mode
  and minus gate-time decompose-vs-design ambiguity: plan-execution mode
  + DIRECT mode + the escalation/return transitions. The spike lane and
  its protocol move with it unchanged
  (`references/spike-worker-protocol.md`).
- The Implementer's clear-cut decompose authority (gate Check-2:
  children whose self-contained pre-specs can be written NOW) survives —
  that is mechanical splitting, not design. Children that need design
  are the escalation case.

**Migration surface** (for the implementation plan, not decided here):
dispatch ritual and `implement-dispatch.sh` gain state→protocol routing;
worker-bootstrap `PROTOCOL_FILE` paths; issue-tracker SKILL.md protocol
references and state vocabulary; operation manuals; board-lint legality
tables; the `ready-for-agent` label migration on live boards.

## What does not change

No orchestrator-judge (the Architect is a relay phase, not a judge —
it never reviews the Implementer's output; the QAgent owns the review
loop). The spike lane. The wake ritual and `board-answer.sh` relay.
`needs-human`/`needs-info`/`interactive-preferred` semantics (minus the
design-gap traffic that now has its own address). Workers registering
their own follow-ups. The reviewing-prs loop structure and exit gates.

## Acceptance (observable)

1. A ticket registered `ready-for-architect` is picked up by a
   Fable-routed worker whose first board write is its gate verdict; on
   pass, its scope ends with a plan document committed to the ticket
   branch, a note carrying path + context/intent, and the
   `ready-for-implementer` transition. It writes no implementation code.
2. A dispatch on `ready-for-implementer` with a plan attached spawns an
   Opus worker that authors no plan document, executes, and opens a PR
   whose body carries Validation Evidence — with no gate comment
   re-litigating the design.
3. An Implementer dispatched on a plan-less ticket that needs a plan
   writes `ready-for-architect` (with note) as its verdict — not
   `needs-human`.
4. A mid-execution genuine blockage lands as
   `in-progress → ready-for-architect` with note + orientation summary;
   mere divergence produces living-spec updates and a finished PR
   instead.
5. A review dispatch spawns ONE Opus-high QAgent; fixes between rounds
   arrive as fix-wave agent (Opus medium) dispatches; the loop's exit
   behavior is unchanged.
6. An Architect on an oversized goal routes to decomposing and registers
   children carrying lane states per the birth rule.

## Deferred

- **Self-compact policy** — the Agent SDK supports it, but both phases
  end their scopes well before context pressure in the expected sizes;
  adopt only when a policy hardens from observed need (human direction
  2026-07-30).
- **Cross-model session-fork handoff** (Implementer forks the
  Architect's session inheriting context) — rejected for now (Decision
  Log #1); revisit only if plan self-containment proves insufficient in
  practice.
- Renaming `reviewing-prs` (the QAgent name is a role name, not a skill
  rename).

## Decision Log

- Decision: Handoff = separate sessions + artifact contract; the plan (+
  ticket note) is the entire interface.
  Rationale: forces plan self-containment (the existing execplan bar),
  reclaim-safe on the cattle runtime (any pod resumes from artifacts),
  independent crash/billing domains per phase. Rejected: session fork
  with model downshift (inherits reasoning free but kills the
  self-containment forcing function; cross-model resume unproven);
  single-session model swap (context accretes, phase boundaries blur).
  Date/Author: 2026-07-30, human + roadmapping session.
- Decision: Relay encoded as board states (`ready-for-agent` →
  `ready-for-architect` / `ready-for-implementer`).
  Rationale: dispatcher stays mechanical/judgment-free — state selects
  protocol and model route.
  Date/Author: 2026-07-30, human.
- Decision: No intake gate at the Implementer; divergence absorbed via
  living-spec doctrine; only genuine blockage returns to the Architect.
  Rationale: the Architect phase already carries council + spec/plan
  review; re-gating would have the weaker model re-judge the stronger
  model's design. Rejected: full gate re-run without redesign rights
  (cost per ticket for rare catches); full re-run with redesign rights
  (defeats the split's economics entirely).
  Date/Author: 2026-07-30, human ("cool" refinement of the recommended
  intake-check option — even the intake check was dropped).
- Decision: Birth classification by registrar; unsure →
  `ready-for-implementer`.
  Rationale: the gate-escalation edge makes misclassification
  self-correcting; the opposite default burns Fable on borderline
  tickets. Rejected: unsure→architect; all-architect birth.
  Date/Author: 2026-07-30, human.
- Decision: Plan authorship exclusive to Fable — the Implementer loses
  the EXECPLAN self-authoring mode; plan-need is an escalation trigger.
  Rationale: plans are the pipeline's quality fulcrum; uniform
  frontier authorship is the pivot's value proposition; bounce cost on a
  warm-pool runtime is effectively Fable tokens only. Rejected: bounded
  self-authoring for sequencing-only plans (two plan authors blur the
  quality boundary).
  Date/Author: 2026-07-30, human.
- Decision: Council on the Spec→Impl-Plan shape only; ExecPlan-shape
  tickets get a solo Fable Architect.
  Rationale: council cost scales with stakes via the existing track
  logic; medium work doesn't warrant a critique debate.
  Date/Author: 2026-07-30, human.
- Decision: Skill topology = split implementing-tickets into
  `architecting` + `implementing` (bare gerunds), not a new standalone
  skill.
  Rationale: the Architect's protocol is mostly brainstorming (+
  decomposing, per-ticket gate) in worker clothes — a thin adapter, and
  the split mirrors the real phase seam in the existing skill. Naming
  follows the decomposing precedent. Rejected: new `architecting-tickets`
  skill beside an untouched implementing-tickets.
  Date/Author: 2026-07-30, human.
- Decision: Batch grill = the existing park format (numbered questions +
  recommended answers, board-answer relay); no new reference file.
  Rationale: already shipped in the pipeline's protocols; the Architect
  applies it at design time.
  Date/Author: 2026-07-30, human ("origin에 이미 batch grilling이
  들어가있다").
- Decision: Architect ends at the plan — the ideadump's original
  "architect reviews the implementer's work with hot context, then
  QAgent" is dropped.
  Rationale: preserves no-orchestrator-judge and the review loop's
  single ownership; hot-context review value is served by the QAgent's
  evidence cross-check.
  Date/Author: 2026-07-30, human correction during roadmapping.
- Decision: QAgent = ONE Opus high; fix waves = declared `fix-wave`
  agent on Opus medium. Lands via/with review-stack C5/C6 — this spec
  adds pins, not a parallel flip.
  Date/Author: 2026-07-30, human.
- Decision: Self-compact deferred until a policy hardens.
  Rationale: both phases end before context pressure at expected ticket
  sizes.
  Date/Author: 2026-07-30, human.

## Surprises & Discoveries

- Observation: The batch-grill mechanism the ideadump proposed already
  exists — mid-build parks post numbered questions with recommended
  answers, and `board-answer.sh` relays answers into the bound session.
  Evidence: implementing-tickets "Mid-build Forks and Parks";
  issue-tracker's needs-human note law and wake ritual.
- Observation: Splitting `ready-for-agent` turned the park discriminant
  into a three-address system — design gaps that previously leaked into
  `needs-human` (where they waited on the human) now route to
  `ready-for-architect` (where an agent resolves them).
  Evidence: the grill's Q2 exchange; issue-tracker's park discriminant
  paragraph (single authoritative copy, to be extended there).

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-30: v1, authored from the E1 grill of the ideadump roadmapping
  session (handoff → states → intake → classification → authorship →
  topology, in that order; all decisions human-confirmed in-session).
