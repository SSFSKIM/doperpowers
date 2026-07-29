# Implement Lane Split — Architect / Implementer / QAgent (2026-07-30)

> **Status:** design approved in-session (ideadump roadmapping, epic E1;
> grill record in the Decision Log below), then amended v1.1 after an
> independent fable review (see Revision Notes). Implementation sequencing
> is routed by the roadmap consolidation at the end of the roadmapping
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

What you can observe after: every plan document the pipeline's dispatch
produces is Fable-authored (the architect dispatch is exempt from engine
opt-in labels — see State machine changes); Opus workers never author
plans; design gaps discovered downstream flow to a named state
(`ready-for-architect`) instead of leaking into `needs-human`; and the
whole relay runs with no orchestrator-judge — each phase ends by writing
the board and dying.

## The relay

```
register ─► ready-for-architect ─►(gate verdict)─► in-design ─►(plan done)─► ready-for-implementer
   │                                               │      │                        │
   │                        parks return here ─────┘      └─ down-shortcircuit ────┤
   │                                                          ("pre-spec suffices")│
   └────────────────────────► ready-for-implementer ◄──────────────────────────────┘
                                     │
                                     ├─ plan attached → execute (no gate)
                                     ├─ no plan → today's gate + DIRECT
                                     │     └─ gate finds plan-need ──► ready-for-architect
                                     ▼
                              in-progress ──► in-review ──► (QAgent loop) ──► confident-ready ──► done
                                     └─ genuine mid-build block ──► ready-for-architect (return park)

Convergence: the SECOND traversal of the same escalation/return edge on a
ticket parks needs-human. A down-shortcircuit ruling binds the next
gate's plan-need check.
```

## State machine changes

`ready-for-agent` splits into two dispatchable states, and the Architect
phase gains an in-flight state; everything downstream of `in-progress` is
untouched.

| state | meaning | worker |
|---|---|---|
| `ready-for-architect` | dispatchable to design: purpose and success criteria stated to the architect-lane bar (below); the work needs design/plan authorship | Architect (Fable high/xhigh) |
| `in-design` | the Architect's in-flight state — gate passed, grill/authoring underway; its parks return here | (bound Architect) |
| `ready-for-implementer` | dispatchable to execution: an Architect's plan is attached, or the ticket is small enough that the pre-spec is the plan | Implementer (Opus med/high) |

**Birth classification (registrar judgment, unsure → implementer).**
Whoever registers the ticket assigns the lane state: obvious
multi-milestone, novel-design, or cross-cutting work is born
`ready-for-architect`; everything else — including every unsure case —
is born `ready-for-implementer`. Misclassification is self-correcting
and cheap: the Implementer's gate escalates upward (below), and an Opus
gate costs far less than defaulting borderline tickets onto Fable.
**Category `spike` is always born `ready-for-implementer`** and binds the
spike protocol regardless of lane judgment — category precedence keeps
the dispatcher's routing total (a findings-only exploration never needs a
plan author).

**The architect-lane gate bar.** The ticket gate's Check-1 cannot apply
verbatim to this lane — it fails tickets with unanswered architecture
forks, which is exactly this lane's population. The architect-lane
variant: WELL-DEFINED means the PURPOSE and success criteria are stated
and human-taste forks are answered or enumerable-for-parking; **open
design forks are the lane's work, not gate failures**. Check-2
(WELL-SCOPED → decomposing) applies unchanged. `ticket-gate.md` gains
this variant (migration surface).

**Engine labels.** The architect dispatch IGNORES `engine:*` labels —
plan authorship is exempt from the X4 gateway opt-in, which now applies
to implementer/QAgent routes only (a deliberate GPT-plan experiment is
run by hand, not by label). This narrows the review-stack roadmap's X4
contract and is flagged there on landing.

**New legal transitions:**

1. **Architect gate pass** — `ready-for-architect → in-design`, plus the
   standard one-line `[gate]` comment. Gate fail parks directly from
   `ready-for-architect` per the (extended) discriminant.
2. **Architect completion** — `in-design → ready-for-implementer`. The
   closing contract: the plan document committed on the ticket branch
   **and pushed** (cattle reclaim depends on origin-visible artifacts),
   the branch recorded via `--branch`, the plan's repo path recorded in a
   dedicated meta field (`plan:`), and a note carrying brief context and
   intent. "Plan attached" downstream means the meta field, never note
   prose.
3. **Architect down-shortcircuit** — the ticket turned out small:
   `in-design → ready-for-implementer` with note "pre-spec suffices as
   the plan"; no plan document. **This ruling binds the next
   Implementer's plan-need check** (a narrow inherited-trust exception —
   the stronger model has explicitly ruled on plan-need; the Implementer
   may still park for unrelated reasons).
4. **Implementer gate escalation** — a plan-less ticket's gate finds
   plan-need (multiple sequenced milestones, work that must survive
   context death, missing design decisions that are agent-answerable):
   `ready-for-implementer → ready-for-architect`, note required. This
   replaces the current practice of leaking design gaps into
   `needs-human`/`needs-info`.
5. **Return park** — mid-execution the plan proves genuinely blocked (not
   merely divergent): `in-progress → ready-for-architect`, note + the
   standard orientation summary + WIP committed and recorded on the
   branch. Divergence that can be absorbed is NOT a park — see the
   Implementer protocol.
6. **Convergence rule** — the second traversal of the SAME
   escalation/return edge on one ticket parks `needs-human`, its note
   carrying both sides' positions. No third mechanical bounce; two
   honest model disagreements are a human fork.
7. **Park return rule** — an answered park returns the ticket to its
   pre-park state (read from the event record): `in-design` for an
   Architect's park, `in-progress` for an Implementer's. This
   generalizes `board-answer.sh`'s hardcoded `in-progress` and is what
   makes an answered Architect park resumable at all.
8. **Binding release** — the lane-crossing transitions (2, 3, 4, 5) end
   the writing worker's scope and release its binding; the next dispatch
   binds fresh. The "park = pause, session stays bound, answers arrive
   as a resume" contract applies to `needs-human`/`needs-info` parks
   only — lane transitions are scope ends, not pauses.

**The park discriminant becomes a three-address system** (extends
issue-tracker's single authoritative copy): a decision or real-world
input only the human can provide → `needs-human`; missing knowledge
anyone could research → `needs-info`; **missing or broken design that an
agent can author → `ready-for-architect`**. `interactive-preferred`
survives unchanged for work whose core needs the human's live steering.

**Sweep behavior over the new states**: a dead bound worker on an
in-flight state (`in-design`, `in-progress`) gets the resume-with-nudge
recovery (mid-design Fable work is the pipeline's most expensive
in-flight asset — never fresh-dispatched away); a dead worker on a
`ready-for-*` state is the cheap pre-verdict case, fresh-dispatched as
today.

## Worker protocols

| role | model | scope | closing artifact |
|---|---|---|---|
| **Architect** | Fable high/xhigh | architect-lane gate → grill (batch parks) → track judgment → author ExecPlan or Spec → Impl Plan. **Ends at the plan** — no post-implementation review, no code | transition 2's closing contract (pushed plan + `plan:` meta + branch + context/intent note) |
| **Implementer** | Opus med/high | dual mode: plan-execution (no intake gate — trust and drive) / DIRECT (plan-less small ticket, today's protocol minus plan authorship). **No plan authorship** | PR (Validation Evidence + FOLLOW-UPS, unchanged) |
| **QAgent** | ONE Opus high | codex review rounds + fix-wave dispatch (reviewing-prs loop structure unchanged) | `confident-ready` (unchanged) |
| **fix-wave agent** | Opus medium | applies a review round's findings as a dispatched subagent (declared `agents/fix-wave.md`; formalizes the fixer contract that lives in reviewing-prs references today) | fixes committed for the next round |

**Architect = brainstorming in worker clothes.** The behavior protocol is
doperpowers:brainstorming plus decomposing, applied per-ticket: the
architect-lane gate is the scope assessment; unclear nontrivial decisions
become a `needs-human` park in the existing batch format (numbered
questions, each with a recommended answer — the format issue-tracker
already owns and `board-answer.sh` already relays; **no new batch-grill
reference file**); a goal too big for one unit routes to
doperpowers:decomposing; children are registered with lane states per the
birth-classification rule. In worker clothes, brainstorming's
human-approval gate maps to the council (below) plus parks — there is no
synchronous human gate. A ticket whose registrar wants a human
spec-approval anyway says so in its body; the Architect then parks
`needs-human` at spec completion (ticket-level configuration, not
doctrine).

**No intake gate at the Implementer.** The Architect's phase carries the
quality machinery (council, spec review, plan review), so the plan is
presumed sound — the Implementer does not re-run the gate or re-judge the
design. When the codebase reveals divergence from the plan mid-execution,
the Implementer absorbs it under the living-spec doctrine (record in the
spec's Surprises/Revision Notes, adapt, drive to the end). Only a
genuinely blocked plan produces the return park (transition 5); if the
Architect disagrees with a return, the convergence rule (transition 6)
keeps the disagreement from ping-ponging — second bounce goes to the
human.

**The ExecPlan exit-gate is subsumed.** doperpowers:execplan bundles
authoring, execution, and a final-branch review gate into one owner;
split across sessions, that exit-gate would be homeless. In this pipeline
it is owned by the QAgent loop, which attaches to every non-draft PR —
the Implementer adds no pre-PR review duplicate.

**Model pins ride dispatch, not protocols.** The lane state selects the
worker protocol and its default model (architect → Fable,
implementer/QAgent → Opus). The QAgent's Opus-high pin and the fix-wave
agent declaration land as this initiative's implementation work in
reviewing-prs, sequenced WITH the review-stack roadmap's C5
(doperpowers#32) and C6 (doperpowers#33) so the dispatch scripts are
touched once — C5/C6 flip route defaults; this spec adds the pins and
the declared agent. Architect-lane concurrency is capped separately from
the implementer lane (the Fable-spend lever; exact knob named in the
implementation plan).

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

- `architecting` — thin: role framing, the architect-lane gate, the
  brainstorming/decomposing routing above, the batch-park format pointer,
  council scaling, the closing artifact contract. Expected to be light —
  most of its content is pointers into brainstorming, decomposing, and
  issue-tracker's single-copy schema.
- `implementing` — implementing-tickets minus the EXECPLAN-authoring mode
  and minus gate-time decompose-vs-design ambiguity: plan-execution mode
  + DIRECT mode + the escalation/return transitions. The spike lane and
  its protocol move with it unchanged
  (`references/spike-worker-protocol.md`). Two pieces of inherited text
  need rework, not carry-over: the ticket-gate's ExecPlan-based scope
  sizing ("roughly 1–2 ExecPlans") now describes the architect lane's
  output, and the "writing-plans is never a daemon worker's" ban must be
  re-scoped — the Architect is a daemon worker whose whole job is
  authoring plans another session executes.
- The Implementer's clear-cut decompose authority (gate Check-2:
  children whose self-contained pre-specs can be written NOW) survives —
  that is mechanical splitting, not design. Children that need design
  are the escalation case.

**Migration surface** (inventory for the implementation plan, not decided
here): dispatch ritual and `implement-dispatch.sh` gain state→protocol
routing and the architect lane's concurrency cap; worker-bootstrap
`PROTOCOL_FILE` paths; issue-tracker SKILL.md protocol references, state
vocabulary, and the park-discriminant paragraph (third address);
`_board.py` (LEGAL table, BIRTH set, `eligible()`, `newly_eligible()`,
and edge-keyed note enforcement — today's `NOTE_REQUIRED` is
state-keyed, but transitions 2/4/5 require notes into states that are
note-free at birth); `board-sweep.sh` (RECOVER set gains the new states
with the in-flight/pre-verdict recovery split above); `board-answer.sh`
(pre-park return state); `ticket-gate.md` (architect-lane variant +
sizing-language rework); the triaging-feedback registrar (its
TypeScript gate/prompt/verdict compile in `ready-for-agent` — must learn
birth classification); `implement-decompose.md` and spike graduation
paths (children born with lane states); `references/issue-dispatch.yml`;
reviewing-prs (fix-wave agent declaration + QAgent pin); operation
manuals; board-lint legality tables; the `ready-for-agent` label
migration on live boards.

## What does not change

No orchestrator-judge (the Architect is a relay phase, not a judge —
it never reviews the Implementer's output; the QAgent owns the review
loop). The spike lane's protocol and deliverable. The wake ritual's
shape (its answer relay becomes pre-park-state-aware — transition 7).
`needs-human`/`needs-info`/`interactive-preferred` semantics (minus the
design-gap traffic that now has its own address). Workers registering
their own follow-ups. The reviewing-prs loop structure and exit gates.

## Acceptance (observable)

1. A ticket registered `ready-for-architect` is picked up by a
   Fable-routed worker whose first board write is the gate verdict —
   `in-design` (+ `[gate]` comment) on pass, a park on fail. Its scope
   ends with `ready-for-implementer` carrying a pushed branch, a `plan:`
   meta field, and a context/intent note. It writes no implementation
   code.
2. A dispatch on `ready-for-implementer` with a `plan:` meta field
   spawns an Opus worker that authors no plan document, executes, and
   opens a PR whose body carries Validation Evidence — with no gate
   comment re-litigating the design.
3. An Implementer dispatched on a plan-less ticket that needs a plan
   writes `ready-for-architect` (with note) as its verdict — not
   `needs-human`.
4. A mid-execution genuine blockage lands as
   `in-progress → ready-for-architect` with note + orientation summary +
   WIP on the recorded branch; mere divergence produces living-spec
   updates and a finished PR instead.
5. A review dispatch spawns ONE Opus-high QAgent; fixes between rounds
   arrive as fix-wave agent (Opus medium) dispatches; the loop's exit
   behavior is unchanged.
6. An Architect on an oversized goal routes to decomposing and registers
   children carrying lane states per the birth rule; a `spike` child is
   born `ready-for-implementer`.
7. A ticket that traverses the same escalation/return edge twice parks
   `needs-human` with both sides' notes — never a third bounce.
8. An answered Architect park resumes the ticket into `in-design`, and
   the resumed session completes via transition 2 legally.

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
  agent on Opus medium; pins and the agent declaration land in
  reviewing-prs as this initiative's work, sequenced with C5/C6.
  Date/Author: 2026-07-30, human; ownership per review F7.
- Decision: Self-compact deferred until a policy hardens.
  Rationale: both phases end before context pressure at expected ticket
  sizes.
  Date/Author: 2026-07-30, human.
- Decision (v1.1): `in-design` in-flight state + the pre-park return
  rule.
  Rationale: the pipeline's verdict convention is a state write; without
  an in-flight state the sweep fresh-dispatches mid-design crashes
  (discarding the pipeline's most expensive in-flight work) and an
  answered Architect park has no legal completion path
  (`board-answer.sh` hardcodes `in-progress`). Rejected: keeping the
  whole design phase inside `ready-for-architect`.
  Date/Author: 2026-07-30, session, from fable review F1.
- Decision (v1.1): Convergence tie-breakers — the down-shortcircuit
  ruling binds the next plan-need check; the second traversal of the
  same escalation/return edge parks `needs-human`.
  Rationale: two models honestly disagreeing must not produce an
  unbounded mechanical relay with no human surface. Rejected: unbounded
  self-correction ("cheap" only per bounce, not per loop).
  Date/Author: 2026-07-30, session, from fable review F2.
- Decision (v1.1): Architect-lane gate variant (open design forks are
  the work, not failures; Check-2 unchanged).
  Rationale: Check-1 verbatim fails the lane's entire population.
  Date/Author: 2026-07-30, session, from fable review F3.
- Decision (v1.1): Architect dispatch exempt from `engine:*` labels; X4
  narrowed to implementer/QAgent routes. **Flagged to the human** (X4 is
  a recorded review-stack contract).
  Rationale: a per-ticket gateway opt-in must not silently falsify the
  design's core observable (Fable-authored plans). Rejected: label
  overrides plan authorship.
  Date/Author: 2026-07-30, session, from fable review F4.
- Decision (v1.1): Artifact transport contract — pushed branch,
  `--branch` recorded, `plan:` meta field; WIP banked on the branch at
  return parks; binding released on lane-crossing transitions.
  Rationale: cattle reclaim depends on origin-visible artifacts and
  machine-readable attachment, not note prose; lane transitions are
  scope ends, so the bound-session park contract must not apply.
  Date/Author: 2026-07-30, session, from fable review F8.

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
- Observation: The independent review's meta-finding — the relay's happy
  path was coherent, but every high-severity hole was a face of one gap:
  the Architect's missing in-flight existence (its pass verdict, its
  answered parks, its crashes, its disagreements with the Implementer).
  A single new state (`in-design`) plus two edge rules resolved F1, F2,
  and the sweep half of F5 together.
  Evidence: fable review 2026-07-30, findings F1/F2/F5.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-30: v1, authored from the E1 grill of the ideadump roadmapping
  session (handoff → states → intake → classification → authorship →
  topology, in that order; all decisions human-confirmed in-session).
- 2026-07-30: v1.1, post-review amendment (independent fable subagent
  review; all 8 findings + 3 notes adopted as gap-fills, no recorded
  decision re-opened): `in-design` state + pre-park return rule (F1);
  convergence tie-breakers (F2); architect-lane gate bar (F3);
  engine-label exemption, flagged for X4 (F4); migration surface
  expanded to the scripts/registrars that hardcode the old vocabulary
  (F5); spike birth rule + category precedence (F6); fix-wave/pin
  ownership assigned to reviewing-prs alongside C5/C6 (F7); artifact
  transport + binding-release contract (F8); ticket-gate sizing and
  daemon-plan-ban rework flagged, execplan exit-gate subsumed by the
  QAgent loop, architect-lane concurrency cap split.
