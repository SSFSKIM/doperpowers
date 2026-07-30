# Implement Lane Split — Architect / Implementer / QAgent (2026-07-30)

> **Status:** design approved in-session (ideadump roadmapping, epic E1;
> grill record in the Decision Log below), then amended v1.1 after an
> independent fable review, and v1.3 after the 2026-07-31 pre-
> implementation maturity round (three independent evaluators; see
> Revision Notes). Implementation sequencing is routed by the roadmap
> consolidation at the end of the roadmapping session — no skill/script
> edits land from this spec alone.
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
                                     │                └─ review impasse (broken design) ──► ready-for-architect
                                     └─ genuine mid-build block ──► ready-for-architect (return park)

Convergence: the SECOND traversal of the same escalation/return edge on a
ticket parks needs-human. A down-shortcircuit ruling binds the next
gate's plan-need check.
```

## State machine changes

`ready-for-agent` splits into two dispatchable states, and the Architect
phase gains an in-flight state; downstream of `in-progress` the states
are untouched — the only downstream edge edits are the QAgent's
escalation edge and the park-return edges (transitions 6–8).

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
plan author). Precedence is state-free, not birth-only, matching today's
rule (`ROLE = SPIKE` whenever the category is `spike`): a spike moved
into `ready-for-architect` by hand still dispatches on the spike
protocol. E2's `env-issue` category births per its own spec's
classification.

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
to the implementer/QAgent/land routes only (a deliberate GPT-plan
experiment is run by hand, not by label). This narrows the review-stack roadmap's X4
contract; the roadmap's X4 section and Parent-Level Acceptance 3 are
amended alongside this revision. **Precedence on the surviving routes:**
an `engine:codex` opt-in overrides the lane's model pins for that
ticket/PR — the QAgent and fix-wave pins bind the default plain-Claude
route only, and acceptance 5 is read against a label-less dispatch (X4's
purpose is exactly the deliberate per-ticket experiment; a pin that
outranked it would delete the opt-in).

**New legal transitions:**

1. **Architect gate pass** — `ready-for-architect → in-design`, plus the
   standard one-line `[gate]` comment. Gate fail parks directly from
   `ready-for-architect` per the (extended) discriminant.
2. **Architect completion** — `in-design → ready-for-implementer`. The
   closing contract: the plan document committed on the ticket branch
   **and pushed** (cattle reclaim depends on origin-visible artifacts),
   the branch recorded via `--branch`, and the plan recorded in a
   dedicated meta field (`plan:`) as `<repo path>@<commit SHA>` — an
   **immutable revision pin**, written via a new `--plan` flag on
   `board-transition.sh` (`META_KEYS` gains `plan`; an unknown key is
   silently dropped by `render_body` today, so the schema edit is load-
   bearing, not cosmetic). The pin is what makes the plan admissible
   review evidence (see the QAgent paragraph below) and what separates
   the plan-as-authored from the Implementer's living-plan updates on
   the branch. A note carries brief context and intent. "Plan attached"
   downstream means the meta field, never note prose.
3. **Architect down-shortcircuit** — the ticket turned out small:
   `in-design → ready-for-implementer` with the sentinel meta value
   **`plan: pre-spec`** and note "pre-spec suffices as the plan"; no
   plan document. The sentinel — not the note — carries the ruling:
   `note:` meta is overwritten on every transition and note prose is
   not machine-read, so a note-borne ruling would not survive an
   intervening park/answer cycle, while the sentinel makes dispatch
   routing uniform (every `ready-for-implementer` ticket has a `plan:`
   value: a pin, `pre-spec`, or absent = plan-less DIRECT).
   **The ruling is persistent and binds every subsequent Implementer's
   plan-need check** — it attaches to the ticket, not to one worker, so
   a fresh dispatch after a pre-verdict crash inherits it (a narrow
   inherited-trust exception — the stronger model has explicitly ruled
   on plan-need; the Implementer may still park for unrelated reasons).
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
   honest model disagreements are a human fork. **Enforcement lives in
   `board-transition.sh`**, not worker judgment: escalation/return
   edges always post a `[board]` comment (their notes are required), so
   the traversal count is machine-readable from the comment trail; the
   script converts a third traversal into the `needs-human` park
   mechanically. **The count resets at human adjudication**: traversals
   are counted since the last `[answers]` relay (or human comment), so
   a human-sanctioned re-traversal after a convergence park ("yes, the
   plan is wrong — send it back") starts a fresh count instead of
   tripping the rule it just resolved.
7. **Park return rule** — an answered `needs-human` park returns the
   ticket to **its parking lane's in-flight state**: `in-design` for
   parks written from the architect lane (including a gate-fail park
   from `ready-for-architect` — the resumed session re-states its
   verdict, today's established precedent), `in-progress` for the
   implementer lane's, `in-review` for the QAgent's. In-flight, never
   the dispatchable queue: a return to a `ready-for-*` state would race
   the sweep in the window before the resumed session's meta flips to
   `working` (an idle bound meta deliberately never blocks a dispatch),
   binding a second worker onto the ticket — the hardcoded `in-progress`
   avoided this by accident; the generalization must avoid it by rule.
   The return target is recorded at park time in a **`pre-park:` meta
   field** written automatically by `board-transition.sh` (the mechanism
   must be a build, not a read: entering an in-flight state is a
   note-free write that posts no `[board]` comment, `note:` meta is
   overwritten per transition, and no board script queries GitHub's
   label timeline — there is no existing event record to consult). A
   born-parked ticket has no `pre-park:`; its answer stays on the wake
   ritual's fold path and the answerer assigns the lane per the birth
   rule. `LEGAL` gains the return edges (`needs-human → in-design`,
   `needs-human → in-review`). This generalizes `board-answer.sh`'s
   hardcoded `in-progress` (and its `needs-human`-only refusal, which
   stands — see transition 8) and is what makes an answered Architect
   park resumable at all.
8. **Binding release** — the lane-crossing transitions (2, 3, 4, 5) end
   the writing worker's scope and release its binding; the next dispatch
   binds fresh. Release is implemented where it already de-facto lives:
   the dispatcher's slot accounting (`_slots_used`'s state tuple) — a
   bound meta on a state outside the lane's in-flight set never eats a
   slot; no unbind ceremony exists or is added. The "park = pause,
   session stays bound, answers arrive as a resume" contract applies to
   **`needs-human` parks only** — `needs-info` stays on the wake
   ritual's fold-and-re-cut path (no resume machinery exists for it,
   deliberately: `board-answer.sh` refuses non-`needs-human` states and
   the sweep's relay pass scans `needs-human` rows only). Lane
   transitions are scope ends, not pauses.

**The park discriminant becomes a three-address system** (extends
issue-tracker's single authoritative copy, and the condensed second
copy in `_board.py`'s comment): a decision or real-world input only the
human can provide → `needs-human`; missing knowledge anyone could
research → `needs-info`; **missing or broken design that an agent can
author → `ready-for-architect`**. `interactive-preferred` survives
unchanged for work whose core needs the human's live steering.

**Who may write the third address** (the legality table is edited to
exactly these edges, no others): the Implementer's gate (transition 4),
the Implementer mid-build (transition 5), and — a deliberate new edge —
**the QAgent at review impasse: `in-review → ready-for-architect`**,
note required. The review loop's round-cap escalation ("a likely
decomposition defect, not N independent bugs") is the archetypal
agent-authorable design gap; leaving it parked `needs-human` while the
purpose statement promises design gaps "flow to a named state instead
of leaking into needs-human" would contradict the design's own core
observable. The edge is counted by the convergence rule like every
escalation edge — the second review→architect traversal on one ticket
parks `needs-human`. reviewing-prs's AUTHORITY list gains the state
(migration surface).

**Sweep behavior over the new states**: a dead bound worker on an
in-flight state (`in-design`, `in-progress`) gets the resume-with-nudge
recovery (mid-design Fable work is the pipeline's most expensive
in-flight asset — never fresh-dispatched away); a dead worker on a
`ready-for-*` state is the cheap pre-verdict case, fresh-dispatched as
today.

**Lane-aware queue returns.** Every existing path that returns a ticket
to `ready-for-agent` today becomes lane-aware: the unblock return (the
discriminant's "cut `blocked-by`" route), `deferred`'s revival edge, and
the wake ritual's unbound-park fallback all target
`ready-for-implementer` when `plan:` is attached or by the unsure
default, `ready-for-architect` only by the returner's explicit judgment
(the birth rule, re-applied at return time). The wake fallback's "next
dispatch re-runs the gate" promise holds on plan-less tickets only — a
plan-carrying ticket dispatches into plan-execution, gate-free by
design; an answer that reshapes scope on such a ticket is the
answerer's cue to strip `plan:` or route to `ready-for-architect`
instead of returning it to the queue unchanged.

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
doctrine). **Every Architect park from `in-design` banks its WIP**,
mirroring transition 5's contract: draft plan committed and pushed on
the ticket branch, branch recorded — a parked Fable session that dies
unresumably must not take the pipeline's most expensive in-flight asset
with it.

**Mid-design decomposition has a defined exit.** Check-2 runs at the
gate, but grills reveal scale late; a too-big discovery from `in-design`
is a scope-ending verdict, not a dead end. The Architect registers
children per `implement-decompose.md` (the birth rule applies to each
child), updates the parent — which becomes an epic, exactly today's
contract — and exits via the transition-2 edge with note "decomposed —
parent is an epic" and no `plan:`. Epics are never dispatched
(eligibility excludes them), so the missing plan is moot; the epic pull
returns the finished parent to `in-progress` as today, which requires
`PULLABLE` to gain the lane states (migration surface).

**No intake gate at the Implementer.** The Architect's phase carries the
quality machinery (council, spec review, plan review), so the plan is
presumed sound — the Implementer does not re-run the gate or re-judge the
design. Its first board write is the `in-progress` transition with a
note naming the plan revision it executes; it posts no `[gate]` comment
(the convention two implementers would otherwise guess differently).
On architect-lane tickets the authorization-time anchor that
reviewing-prs's audit keys to the `[gate] pass` timestamp today becomes
the Architect's transition-2 `[board] ready-for-implementer` comment —
the moment implementation was actually authorized (migration surface).

When the codebase reveals divergence from the plan mid-execution,
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

**The plan is admissible review evidence.** reviewing-prs's
specification hierarchy admits only documents the issue body explicitly
references, resolved from base-ref or an immutable revision — never the
PR head. Unamended, that contract would bar the QAgent from reading the
very artifact this design makes the entire Architect→Implementer
interface, leaving it to audit a plan-executed PR against an issue body
that is no longer the operative spec. The amendment is one admissibility
clause, not a loop change: the `plan:` meta's `path@SHA` pin names an
admissible secondary spec source at an immutable revision (satisfying
the same anti-self-certification rule that motivates the head-ref ban —
the Implementer cannot rewrite the contract it is audited against). The
QAgent audits against the plan as authored plus the issue body, and
reads the branch's living-plan divergence notes as evidence of absorbed
divergence, not as the contract.

**Model pins ride dispatch, not protocols.** The lane state selects the
worker protocol and its default model (architect → Fable,
implementer/QAgent → Opus). The QAgent's Opus-high pin and the fix-wave
agent declaration land as this initiative's implementation work in
reviewing-prs. Sequencing follows board reality, not the original
"touched once" hope (already false: C6, doperpowers#33, is at
`confident-ready` and lands before this spec's work starts): the
implement-dispatch changes build on the post-C6 script; the
reviewing-prs pins ride with C5 (doperpowers#32) — which unblocks on
the human's pending wontfix closes of #30/#31 — or land as their own
touch if C5 stays parked, the implementation plan's call. Pins bind the
default plain-Claude route only (see Engine labels). Architect-lane
concurrency is capped separately from the implementer lane (the
Fable-spend lever; the knob lands in `_slots_used`'s lane accounting,
which today counts no slot at all for an in-flight `in-design` row).

## Council scaling

Council cost scales with the artifact shape the Architect chooses (the
existing brainstorming track logic, applied by the Architect):

- **ExecPlan shape** (medium work; big-but-atomic): **solo Fable, no
  council.** The Architect grills the ticket, authors the ExecPlan, ends.
- **Spec → Impl Plan shape** (large/novel/high-stakes): the council —
  `doperpowers:critique` (design debate to convergence), the spec-review
  pass, and `doperpowers:plan-reviewer` on the implementation plan — all
  existing machinery, reused (critique and plan-reviewer are declared
  agents; the spec-review pass is brainstorming's inline fable dispatch,
  prose-defined, and stays that way).

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
  (`references/spike-worker-protocol.md`). Two pieces of existing text
  need rework, not carry-over — one inherited, one cross-skill: the
  "writing-plans is never a daemon worker's" ban is `implementing`'s
  inherited text and must be re-scoped (the Architect is a daemon worker
  whose whole job is authoring plans another session executes); the
  ticket-gate's ExecPlan-based scope sizing ("roughly 1–2 ExecPlans")
  now describes the architect lane's output, but it lives in
  issue-tracker's `ticket-gate.md` — the board schema's single copy,
  consumed by five registrar paths — so its rework is a cross-skill
  edit, not text either new skill inherits.
- The Implementer's clear-cut decompose authority (gate Check-2:
  children whose self-contained pre-specs can be written NOW) survives —
  that is mechanical splitting, not design. Children that need design
  are the escalation case.

**Migration surface** (inventory for the implementation plan, not decided
here; verified against the code 2026-07-31):

- **`_board.py`** — `LEGAL` (every `ready-for-agent` edge replaced by
  lane equivalents; new escalation edges `ready-for-implementer` /
  `in-progress` / `in-review → ready-for-architect`; park-return edges
  `needs-human → in-design` / `in-review`), `BIRTH`, `OPEN_STATES`,
  `ACTIVE`, `PULLABLE` (epic pulls — without it a decomposed parent in a
  lane state is never pulled), `STATUS_COLORS` (a state with no color
  entry never gets its GitHub label created), `eligible()` /
  `newly_eligible()`, `META_KEYS` + `plan:` / `pre-park:` writers,
  edge-keyed note enforcement (today's `NOTE_REQUIRED` is state-keyed,
  but transitions 2/4/5 require notes into states that are note-free at
  birth), the condensed park-discriminant comment.
- **Board scripts** — `board-transition.sh` (legality, `--plan`,
  automatic `pre-park:`, convergence-count enforcement, skeleton-guard
  re-key off `ready-for-agent`); `board-register.sh` (the default birth
  state constant and the skeleton-refusal rule, both keyed to the state
  this spec deletes); `board-answer.sh` (pre-park return + refusal
  text); `board-sweep.sh` (the recovery split is a hardcoded `case`
  plus state regexes — RECOVER, CANCEL, and RELAY greps all carry the
  vocabulary); `board-map.sh` (duplicates `eligible()` inline — a
  second authority that would silently disagree; consolidate onto
  `B.eligible`) + `board-map.template.html` (kanban columns, CSS map,
  eligible-first sort, column counts); `board-list.sh` (the ELIGIBLE
  tagging the dispatch ritual reads); `board-edge.sh` (third inline
  eligibility re-derivation); `board-lint.sh` — which holds NO legality
  table (legality is enforced only in `board-transition.sh`); what lint
  gains is the edge-keyed note rule its state-keyed check cannot
  express.
- **Dispatch** — dispatch ritual + `implement-dispatch.sh`
  (state→protocol routing; `_slots_used`'s lane tuple = both the
  binding-release mechanism and the architect concurrency cap);
  worker-bootstrap `PROTOCOL_FILE`/`ROLE` (one file — the review-side
  bootstrap uses `{{SKILL_FILE}}` and no `{{ROLE}}`, a separate shape);
  `references/issue-dispatch.yml` template AND its live consumer-repo
  copies (the workflow's `if:` condition hardcodes the label).
- **Gate & registrars** — `ticket-gate.md` (architect-lane variant +
  sizing-language rework; issue-tracker-owned, five registrar
  consumers); the triaging-feedback registrar (TypeScript: the
  `BirthState` union, `routeTicket`, verdict `STATES`, the worker
  prompt, plus its references/setup/SKILL.md prose — must learn birth
  classification); `implement-decompose.md` and spike graduation paths
  (children born with lane states); reviewing-prs's TOO-BIG
  registration (births the default state today).
- **reviewing-prs** — fix-wave agent declaration (`wave-board.md`'s
  Task-tool dispatch line is the mechanism change; the quiescence/
  ledger contract must hold for a declared agent) + QAgent pin;
  AUTHORITY gains `ready-for-architect`; the spec-hierarchy
  plan-admissibility clause; the `[gate] pass` authorization-time
  anchor re-keyed for architect-lane tickets.
- **Docs & boards** — issue-tracker SKILL.md (protocol references,
  state vocabulary, park discriminant, wake-ritual fallback
  lane-awareness); both operation manuals; the review-stack roadmap's
  X4/acceptance amendment (landed with this revision); the
  `ready-for-agent` label migration on live boards + new labels via
  `STATUS_COLORS`; teaching materials (`teaching/cloud-scale-
  architecture` SQL examples; low priority).
- **Tests** — `tests/issue-tracker/test-board-scripts.sh` (~28 sites
  assert exact transition strings and label lists),
  `tests/implementing-tickets/test-implement-dispatch.sh` (fixtures
  keyed on the old label), `test-protocol-content.sh` (asserts protocol
  prose — fails on the skill split itself),
  `tests/issue-tracker/test-board-template.cjs` (kanban columns).

## What does not change

No orchestrator-judge (the Architect is a relay phase, not a judge —
it never reviews the Implementer's output; the QAgent owns the review
loop). The spike lane's protocol and deliverable. The wake ritual's
shape (its answer relay becomes pre-park-state-aware — transition 7).
`needs-human`/`needs-info`/`interactive-preferred` semantics (minus the
design-gap traffic that now has its own address). Workers registering
their own follow-ups. The reviewing-prs loop structure and exit gates
(its evidence rules gain the plan-admissibility clause and its
authority the third address — the rounds and the exit bar are
untouched). The land worker (human-Approve-triggered, not
lane-dispatched) sits outside the lane states entirely; C5 flips its
route independently.

## Acceptance (observable)

1. A ticket registered `ready-for-architect` is picked up by a
   Fable-routed worker whose first board write is the gate verdict —
   `in-design` (+ `[gate]` comment) on pass, a park on fail. Its scope
   ends with `ready-for-implementer` carrying a pushed branch, a `plan:`
   meta field (a `path@SHA` pin, or `pre-spec` on the down-shortcircuit),
   and a context/intent note — or the decompose exit (children
   registered, epic parent, no plan). It writes no implementation code.
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
5. A label-less review dispatch spawns ONE Opus-high QAgent; fixes
   between rounds arrive as fix-wave agent (Opus medium) dispatches; an
   `engine:codex`-labelled dispatch still rides the gateway route with
   its own models (X4); the loop's exit behavior is unchanged.
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
  narrowed to implementer/QAgent routes. Human-confirmed 2026-07-30
  ("X4는 맞다") — the review-stack roadmap's X4 contract is amended
  accordingly when this lands.
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
- Decision (v1.3): `plan:` = `path@SHA` immutable pin, and reviewing-prs's
  spec hierarchy gains the pin as an admissible secondary source.
  Rationale: the review contract admits only issue-body-referenced
  documents at immutable revisions, never PR head — unamended it bars
  the QAgent from the artifact that IS the phase interface; the pin
  satisfies the same anti-self-certification rule (the Implementer
  cannot rewrite the contract it is audited against) and separates
  plan-as-authored from living-plan divergence. Rejected: issue-body
  back-reference convention (registrars cannot know the path
  pre-design); loosening the head-ref ban (lets the PR self-certify).
  Date/Author: 2026-07-31, session, from cross-spec review (blocking).
- Decision (v1.3): park returns target the parking lane's in-flight
  state, carried by an automatic `pre-park:` meta field; `LEGAL` gains
  `needs-human → in-design` / `in-review`.
  Rationale: "read from the event record" was a build, not a read — no
  script queries state history, `note:` is overwritten per transition,
  and in-flight entries post no comment; returning to a dispatchable
  state races the sweep onto a second bound worker (the hardcoded
  `in-progress` avoided this by accident). Born-parked tickets (no
  `pre-park:`) stay on the wake fold path with the birth rule
  re-applied. Rejected: querying GitHub's label timeline (new GraphQL
  surface + pagination for what one meta field records at write time).
  Date/Author: 2026-07-31, session, from code-grounding + both reviews.
- Decision (v1.3): down-shortcircuit ruling carried as sentinel
  `plan: pre-spec`, persistent across dispatches.
  Rationale: the ruling must survive note overwrites and pre-verdict
  crashes; a sentinel makes every `ready-for-implementer` ticket's
  routing machine-readable from one field. Rejected: note-borne ruling
  (dies on the next transition); one-shot binding (the ruling is about
  the ticket, not one worker).
  Date/Author: 2026-07-31, session, from design review F3.
- Decision (v1.3): convergence enforcement in `board-transition.sh`,
  counting traversals since the last human adjudication.
  Rationale: escalation edges always post comments (notes required), so
  the count is mechanical; without a reset, a human-sanctioned
  re-traversal after a convergence park would trip the rule it just
  resolved. Rejected: worker-judgment enforcement (two implementers
  build different things).
  Date/Author: 2026-07-31, session, from design review F2.
- Decision (v1.3): the QAgent may write the third address —
  `in-review → ready-for-architect`, counted by the convergence rule.
  Rationale: the review impasse's decomposition-defect cluster is the
  archetypal agent-authorable design gap; leaving it at `needs-human`
  contradicts the purpose statement's core promise. Rejected: scoping
  the third address to implement-lane writers only (preserves a leak
  the spec exists to close).
  Date/Author: 2026-07-31, session, from cross-spec + design review
  converging on the same gap.
- Decision (v1.3): engine-label opt-in outranks lane model pins;
  acceptance 5 reads against label-less dispatch.
  Rationale: X4's surviving purpose is the deliberate per-ticket
  experiment; a pin that outranked it would delete the opt-in.
  Date/Author: 2026-07-31, session, from cross-spec review.
- Decision (v1.3): mid-design decomposition exits via the transition-2
  edge with epic semantics; `PULLABLE` gains the lane states; Architect
  parks bank WIP; `needs-info` excluded from the resume contract;
  queue returns become lane-aware (birth rule re-applied at return).
  Rationale: seam gap-fills — each generalizes a hardcoded path
  (`implement-decompose`'s parent contract, transition 5's banking,
  `board-answer`'s refusal, the `ready-for-agent` return targets) that
  the v1.1 rules referenced without covering.
  Date/Author: 2026-07-31, session, from design review F4/F6/F7 +
  cross-spec 4c.

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
- Observation: The v1.3 evaluation round (code-grounding, cross-spec,
  and design review, run as three independent agents) found the same
  pattern one level down: every residual defect was a seam where a v1.1
  rule generalized a hardcoded mechanism without covering a case the
  hardcode silently handled — `in-progress` returns were race-free by
  accident, note-free gate writes meant no event trail existed to read,
  the state-keyed `NOTE_REQUIRED` had quietly shaped what the comment
  stream could carry, and the review loop's evidence rules predated the
  existence of a plan to admit. Generalizing a hardcode means owning
  its accidental guarantees.
  Evidence: 2026-07-31 evaluation round; the v1.3 Decision Log block.
- Observation: The sequencing clause aged in one day — C6 reached
  `confident-ready` and C5's chain parked `needs-human` (#30/#31
  wontfix recommendations awaiting the human), turning "touch the
  dispatch scripts once" from a plan into a counterfactual. Substrate-
  neutral state rules survived contact with reality; cross-roadmap
  timing promises did not.
  Evidence: board state 2026-07-31; the amended sequencing paragraph.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-31: v1.3, pre-implementation maturity round (three independent
  evaluators: Opus code-grounding vs the actual scripts, Opus cross-spec
  vs E2/E3/the review-stack roadmap/the v8 schema, fable design review
  of the v1.2 state machine; all surviving findings adopted as
  gap-fills, no recorded decision re-opened): `plan:` = `path@SHA` pin +
  QAgent plan-admissibility clause; `pre-park:` meta + in-flight return
  targets + two new legal return edges; `plan: pre-spec` sentinel;
  convergence enforcement locus + reset; QAgent third-address edge;
  engine-label/pin precedence; mid-design decomposition exit;
  Architect park WIP banking; `needs-info` out of the resume contract;
  lane-aware queue returns; plan-execution first-write convention +
  `[gate]`-anchor re-key; sequencing paragraph rewritten to board
  reality (C6 landing, C5 parked behind #30/#31); migration surface
  rewritten as a verified grouped inventory (board-register/map/list/
  edge, `_board.py`'s full table set, sweep's three greps, tests,
  consumer-repo workflow copies); board-lint and "RECOVER set"
  mischaracterizations corrected; ticket-gate ownership corrected.
  Companion edits: E2's writer clause/env-issue birth/acceptance 4;
  review-stack roadmap X4 + Parent-Acceptance 3 amendment.
- 2026-07-30: v1, authored from the E1 grill of the ideadump roadmapping
  session (handoff → states → intake → classification → authorship →
  topology, in that order; all decisions human-confirmed in-session).
- 2026-07-30: v1.2, X4 narrowing human-confirmed — the engine-label
  exemption's flag is cleared; no design change.
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
