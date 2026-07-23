# The Ticket Gate — what `ready-for-agent` means

The bar a ticket must pass before implement work begins — board schema,
one copy, owned by doperpowers:issue-tracker. (This is the board rendering
of the universal division gate — doctrine in doperpowers:decomposing,
ticket procedure here.) Consumed everywhere a
readiness judgment is made: the implement worker re-runs both checks at
every dispatch (a registrar's verdict is a
recommendation, never inherited trust), and every registrar — follow-ups,
decompose children, spike graduations, feedback triage, sprint
materialization — triages honestly against it: `ready-for-agent` only if
the ticket would pass.

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

The work must fit the ticket as one purpose-unit: roughly 1–2 ExecPlans —
big-but-ATOMIC work that cannot land halfway still counts as ONE unit
(that is what plan-mode execution exists for). Decompose only work whose
children could land on main independently. Too big? One question decides:
can the remainder be written down as self-contained child pre-specs right
now? Yes → decompose. No → the work needs one continuously steered human
context: `interactive-preferred`.
