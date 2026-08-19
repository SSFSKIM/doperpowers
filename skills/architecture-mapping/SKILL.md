---
name: architecture-mapping
description: Use when writing or revising a repo's ARCHITECTURE.md or architecture map/codemap — no architecture doc exists, sessions keep re-answering "where is the thing that does X?", a domain or subsystem landed, a real boundary moved, or reviews need numbered architectural invariants to cite.
---

# Architecture Mapping

`ARCHITECTURE.md` is the repo's spine document: a short, stable mental map
that answers "where should I change X?" without a linear read of the
codebase. The hard part of contributing is rarely making a change — it is
finding where the change goes. A core developer carries that map in their
head; this file transfers it to every future session and contributor.

Do this work with full repo context — it is deep codebase reading, not
delegable to an isolated subagent. The map is maintained, not generated
once: revisit it when the architecture evolves or a domain is added.

## Map, not atlas

Keep it short and stable: facts unlikely to change per sprint, specific
enough to name directories, key files, modules, types, commands, and
entrypoints. Push algorithms and volatile detail down into design docs or
inline comments. Name entities instead of deep-linking them — a link to an
exact line goes stale; a stable name stays searchable.

The section contract, example shape, and anti-patterns live in
[ARCHITECTURE-FORMAT.md](./ARCHITECTURE-FORMAT.md).

## Exploration procedure

Write the map from the real source, in this order:

1. **Inventory the top level** — source roots, manifests, build/test
   config, generated directories, entrypoints, CLI commands, routes,
   jobs, migrations.
2. **Trace two or three representative flows end to end** — the flows a
   maintainer actually changes (request → handler → domain → persistence;
   CLI command → parser → action → output).
3. **Separate ground state from derived state** where the app has them —
   stored inputs, config, external facts vs generated artifacts, caches,
   outputs — and note which modules own each.
4. **Derive the layer law from the code that exists.** Never import
   another repo's law; if this repo doesn't have that shape, it doesn't
   have that law.
5. **Mark boundary surfaces** — where rules change or external callers
   enter (the format doc's Boundaries section lists the kinds).
6. **Collect invariants while reading** — positive rules ("all schema
   parsing lives in X") and absences ("UI never imports repo") alike.

Use the writing itself as inspection: if things adjacent in the map are
far apart on disk, or unrelated concerns sit together, record the tension
as a known limitation rather than silently normalizing it.

## Absences are the point

Boundaries are the least inferable part of a codebase — which layers
never know about which others, which state never lives where, which
surfaces are public. Future agents copy existing patterns, so an absence
that isn't written down doesn't exist as a rule.

In a multi-context repo (a `CONTEXT-MAP.md` exists at the root),
ARCHITECTURE.md owns the physical boundaries — layers, dependency
direction, module seams — and cross-references `CONTEXT-MAP.md` for the
semantic ones (where a term's meaning changes;
doperpowers:domain-modeling owns that side). The two kinds of boundary
often coincide; they are not the same thing, and merging the documents
breaks both.

## Invariants are the enforcement

Number the architectural invariants (AI-1, AI-2, …), each with one
sentence of why. The enforcement medium here is review: qa-loops
reviewers and independent review passes cite violations by number, which
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

Update when a real boundary changes: a new domain, a moved seam, a new
public surface. Implementation churn inside a module is not an update
trigger. Sprint state and active plans never live here — the repo's
plans/specs documents own volatile work.
