# Spec Document Reviewer Prompt Template

Use this template when dispatching the spec document reviewer subagent.

**Purpose:** Stand in for the fresh session the spec is written for — the reader
with no conversation history who must be able to pick the spec up and build from
it (doperpowers:execspec's bar). Whatever that reader cannot resolve from the
document and the repo is a defect in the document.

**Dispatch after:** The spec is written, self-reviewed, and committed.

**Model:** the strongest available at its highest effort (Claude: Fable, effort
xhigh) — specify it explicitly; an omitted model silently inherits the session's.

**Context to pass:** the spec path, one line on what the project is, one line on
what stage this is. Nothing else. The thin brief is the instrument: if the
reviewer needs the conversation to understand the spec, the spec is not done.

```
Subagent (general-purpose, model: fable):
  description: "Review spec document"
  prompt: |
    You are reviewing a design spec before an implementation plan is written
    from it. You have no conversation history — that is deliberate. This spec
    is written to be picked up by a session exactly like yours, so anything you
    cannot resolve from the document plus the repository is a defect in the
    document, not a gap in your briefing.

    **Spec:** [SPEC_FILE_PATH]
    **Project:** [ONE LINE — what this codebase is]
    **Stage:** the design is settled and human-approved; the next step is
    writing an implementation plan from this document.

    Read the spec, then read enough of the repository to check what it claims.

    ## The two questions

    1. **Could you build this without asking anything?** Every place you would
       have had to ask is an issue — record what you would have asked.
    2. **Does what the spec says about the world hold?** It was written by
       someone carrying context you don't have, which is exactly how unchecked
       assumptions get in. Verify its claims about existing files, current
       behavior, and external tools against the actual repo.

    ## What to check

    | Category | What to look for |
    |----------|------------------|
    | Purpose | Opens with why this matters and what someone can do after it that they couldn't before — not with mechanics |
    | Acceptance | Phrased as observable behavior with real commands and expected output, not internal attributes ("X is refactored") |
    | Grounding | Claims about existing code, file paths, and third-party behavior are true — check them |
    | Completeness | TBD, TODO, placeholders, sections that trail off |
    | Consistency | Sections that contradict each other; architecture that doesn't match the described behavior |
    | Ambiguity | Requirements two competent engineers would build differently |
    | Traceability | Every load-bearing declaration ("the artifact must carry X") has a concrete section or slot that carries it |
    | Scope | One plan's worth of work, not several independent subsystems |
    | YAGNI | Features nobody asked for; complexity the purpose doesn't earn |
    | Living tail | `## Decision Log` (with at least one rejected alternative and why it lost), `## Surprises & Discoveries`, `## Outcomes & Retrospective`, `## Revision Notes` all present |

    ## Calibration

    **The design itself is settled — do not re-run the brainstorm.** Proposing a
    different architecture, a better library, or a wider scope is out of bounds;
    a human chose this. The exception is a design decision that is internally
    contradictory or that the codebase contradicts — that is a defect, flag it.

    **Flag only what would change what gets built.** An issue is something that
    leads to the wrong thing being built, a planner getting stuck, or a claim
    that is false. Wording, ordering, section balance, and "this could be more
    detailed" are not issues; put them under Advisory or drop them.

    Approve unless real gaps remain. Do not edit the spec — report only.

    ## Output format

    ## Spec Review

    **Status:** Approved | Issues Found

    **Issues (if any):**
    - [Section]: [the defect] — [what gets built wrong, or what claim is false]

    **Questions I would have had to ask:**
    - [anything you could not resolve from the spec + repo; "none" if none]

    **Advisory (does not block):**
    - [suggestions the author may take or drop]
```

**Reviewer returns:** Status, Issues, Questions it could not resolve, Advisory.

**Handling the report:** fix every Issue and every unresolvable Question in the
spec, take or drop Advisory items on your own judgment, and add a Revision Note
if the fixes changed anything load-bearing. Re-dispatch only if a fix changed the
design substantively — wording and gap-filling do not need a second pass.
