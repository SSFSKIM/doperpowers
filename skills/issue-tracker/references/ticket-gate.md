# The Ticket Gate — what the dispatchable lane states mean

The bar a ticket must pass before implement work begins — board schema,
one copy, owned by doperpowers:issue-tracker. (This is the board rendering
of the universal division gate — doctrine in doperpowers:decomposing,
ticket procedure here.) Consumed everywhere a
readiness judgment is made: the Executor worker re-runs both checks at
every dispatch (a registrar's verdict is a
recommendation, never inherited trust), and every registrar — follow-ups,
decompose children, spike graduations, feedback triage, sprint
materialization — triages honestly against it: a dispatchable lane
state only if the ticket would pass (the birth rule: design-heavy work →
`ready-for-architect`; everything else, including every unsure case and
every spike → `ready-for-implementer`).

Every answer must come from the ticket body, the codebase, or repo docs.
The human is a source too — asynchronously: a human-grade fork parks the
ticket, and the relayed answers become ticket content before work
resumes.

## Check 1 — WELL-DEFINED

Classify every fork the implementation will hit:

- Mechanical/technical with one obvious best answer (internal naming,
  idiomatic choice, repo precedent) → the worker's call. Parking these is
  a protocol violation, not caution.
- Non-trivial architecture (subsystem boundary, data model, API shape) →
  must be answered by ticket + codebase; unanswered → gate-fail.
- Product design or taste, major OR minor (user-facing behavior, wording,
  interaction/visual choices — anywhere a reasonable human could prefer
  differently on non-technical grounds) → must be answered by the ticket;
  unanswered → gate-fail. Even minor taste is never the worker's call.

## Check 2 — WELL-SCOPED

The work must fit the ticket as one purpose-unit: roughly ONE plan — an
ExecPlan, or a Spec → Impl Plan for the largest work (the architect
lane's output; on a plan-less DIRECT ticket the pre-spec itself is the
plan) — big-but-ATOMIC work that cannot land halfway still counts as
ONE unit (plan-execution is what lands it whole). Decompose only work whose
children could land on main independently. Too big? One question decides:
can the remainder be written down as self-contained child pre-specs right
now? Yes → decompose. No → the work needs one continuously steered human
context: `interactive-preferred`.

## The architect-lane variant (Check 1)

On a `ready-for-architect` ticket, Check-1 cannot apply verbatim — open
architecture forks are exactly this lane's population. The variant:
WELL-DEFINED means the PURPOSE and success criteria are stated, and
human-taste forks are answered or enumerable-for-parking. Open DESIGN
forks are the lane's work, never gate failures. Check-2 applies
unchanged in both lanes.
