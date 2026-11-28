---
name: architecture-mapping
description: Verified guidance on writing or revising a repo's ARCHITECTURE.md or codemap, including when none exists and sessions keep re-asking where things live.
---

# Architecture Mapping

`ARCHITECTURE.md` is the repo's spine document: a short, stable mental map
that answers "where should I change X?" without a linear read of the
codebase. The hard part of contributing is rarely making a change — it is
finding where the change goes. A core developer carries that map in their
head; this file transfers it to every future session and contributor.

The map is only as good as the reading behind it: boundaries and absences
show to a reader who has gone across the whole codebase, not to one who
read a single area of it.

## Map, not atlas

Keep it short and stable: facts unlikely to change per sprint, specific
enough to name directories, key files, modules, types, commands, and
entrypoints. Push algorithms and volatile detail down into design docs or
inline comments.

What each section captures, the example shape, and the anti-patterns are
in [ARCHITECTURE-FORMAT.md](./ARCHITECTURE-FORMAT.md). Write the map from
the real source, and use the writing itself as inspection: if things
adjacent in the map are far apart on disk, or unrelated concerns sit
together, record the tension as a known limitation rather than silently
normalizing it.

## Absences are the point

Boundaries are the least inferable part of a codebase — which layers
never know about which others, which state never lives where, which
surfaces are public. Future agents copy existing patterns, so an absence
that isn't written down doesn't exist as a rule.

## Invariants are the enforcement

Number the architectural invariants (AI-1, AI-2, …), each with one
sentence of why. The enforcement medium here is review: reviewers cite
violations by number, which
only works when the rule has a number and a reason a zero-context
reviewer can apply. An invariant living as folklore is invisible to every
reviewer.

Two graduations beyond the doc, both earned rather than speculative:

- A rule that is mechanically decidable, always true, and costly when
  missed belongs in CI or a linter, not in prose.
- A methodology rule that has actually bitten ("schema changes only via
  migration") can graduate into the repo's agent instructions or a
  guide-skill. Encode nothing for hypothetical violations — cheap, rare
  mistakes are fixed forward.

## Maintenance

The map is maintained, not generated once. Update it when a real boundary
changes: a new domain, a moved seam, a new public surface. Implementation
churn inside a module is not an update trigger.
