# ARCHITECTURE.md Format

## Section contract

Each of these questions needs a home; the headings below are the default
shape, not a quota. A small repo may fold Layer Law into Boundaries.

- **Bird's Eye View** — a few paragraphs orienting the system: what it
  accepts, what it produces, the major runtime shape.
- **Code Map** — coarse modules/directories and what each does, one
  heading per component. Answers "where is the thing that does X?" and
  "what does this thing do?"
- **Boundaries & API Surfaces** — where rules change or external callers
  enter: library entrypoints, server routes, CLI commands, public
  component boundaries, data schemas, plugin/extension seams,
  generated-vs-source and runtime-state boundaries. Write the boundary
  contract; it is never obvious from filenames.
- **Layer Law** — the dependency direction and the forbidden edges.
- **Architectural Invariants** — numbered rules (AI-1, AI-2, …), each
  with one sentence of why, citable by reviews. Many are absences.
- **Cross-Cutting Concerns** — the sanctioned location/interface for
  config, path/env resolution, logging, auth, external clients,
  generated files, migrations, test fixtures.
- **Data Flows** — the few end-to-end flows that explain how the system
  actually works.

## Example shape

rust-analyzer's ARCHITECTURE.md is the pattern (not a template to copy):
a short bird's-eye view; a code map with one heading per coarse
component; **Architecture Invariant** callouts under the components they
bind; **API Boundary** labels where callers enter or rules change;
cross-cutting concerns after the map.

## Anti-patterns

- **The atlas.** Listing every file. It goes stale within weeks and stops
  being read — a map of a country, not an atlas of every state.
- **The internals guide.** How a module works inside belongs in deeper
  design docs or inline comments; the map covers where and what, not how.
- **Silent absences.** Leaving "X never depends on Y" unwritten because
  the code currently implies it — future agents copy existing patterns,
  and an unwritten absence rule doesn't exist.
- **Deep links.** `src/foo.rs#L142` goes stale; the name `FooResolver`
  stays searchable.
- **Sprint state.** Active plans and volatile work state live in the
  repo's plans/specs documents, never here.
- **Imported laws.** Deriving the layer law or invariants from another
  repo's architecture instead of from this repo's own code.
