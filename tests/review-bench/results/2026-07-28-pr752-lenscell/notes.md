# PR752 lens validation cell (2026-07-28) — does a developer_instructions lens shift Sol's recall profile?

Gate for the multi-lens review engine ExecPlan
(`docs/doperpowers/execplans/2026-07-28-multilens-review-engine.md`): the
`CODEX_REVIEW_LENS` passthrough ships into `reviewing-prs` SKILL.md only if a
lens demonstrably moves the native reviewer's profile on the recorded PR752
case. Transport of developer_instructions was proven 2026-07-12; recall effect
was not.

Invocation: `run-case.sh --case cases-real/pr752 --engine codex` (unchanged),
with the env var inherited into `review-engine.sh` (gpt-5.6-sol, xhigh, same
defaults as both recorded plain runs).

Lens text (verbatim):

> Focus this review on authorization and actor-identity assumptions in the
> changed API routes: how the acting principal is derived versus what the
> request body claims, and any guard, rate limit, or access-control branch
> whose behavior depends on request shape (which optional fields are present)
> rather than on the authenticated actor. Examine client-supplied identifiers
> that select privileged buckets or bypass narrower limits.

Scoring key: the 13-item confirmed union in
`../2026-07-27-pr752-modelcells/notes.md`. Both recorded plain-native runs
(Sol xhigh) found C1 C2 C3 C4 C5 C6 C7 F1 F2 C10 and missed F3 N1 N2.

- PASS: this run reports F3 (promotion route rate-limit bucket chosen by
  request shape — `student_id` present routes an authenticated student into
  the 60/hr operator bucket instead of the 5/hr self bucket;
  app/api/students/promotion/route.ts ~204-207) — or, failing F3, at least
  one confirmed union item absent from both plain profiles (N1/N2/newly
  adjudicated).
- FAIL: profile is a subset of the plain profile.
- Also record: total union hits (narrowing is acceptable — fan-out unions
  with a plain sweep — but worth noting for the skill prose).

## Result

**PASS.** 390s, rc=0, exactly ONE finding — and it is F3, at the exact
recorded location (app/api/students/promotion/route.ts:204-207) with the
exact confirmed mechanism: optional `student_id` present → `isSelfPath`
false → authenticated student rides the 60/hr operator bucket instead of
the 5/hr self bucket; fix by `student.user_id === user.id` / server-side
role. [P1], severity argued via repeatable transition/audit/cache churn.

Two implications recorded for the skill prose:
1. Lens efficacy proven: developer_instructions doesn't just transport —
   it recovers a defect the identical plain invocation missed twice.
2. A lensed run narrows HARD (1 finding vs plain's 10; 390s vs ~670s).
   A lens run is a scalpel, not a sweep — the fan-out must keep one
   lens-free run as the broad sweep, and lensed findings union with it.
