# Case study: Prime Intellect, "Prime Agent" TypeScript → Rust port

Source: https://www.primeintellect.ai/blog/prime-agent-rust (read 2026-10-15).
Extracted for the compile-class work-system design; numbers are the post's own.

## What was ported

The Prime Agent CLI (TypeScript; the largest source file ~15,000 lines, four
files over 5,000) rewritten in Rust as nine crates with a one-way dependency
graph enforced by Cargo (largest file ~2,500 lines, none over 5,000). The
rewrite also added features (Windows, session crash isolation) and redesigned
the TUI flows and the model-facing API — so not a pure parity port.

## Decomposition

A root orchestrator divided the work into a topological ordering of tasks.
It wrote no product code and merged finished work. Each task ran as a finite
state machine with four roles:

- Planner — wrote the feature spec, the ground-truth TypeScript behavior, and
  the parity verifier for the task.
- Implementer — wrote the Rust in its own worktree (tasks developed in
  parallel).
- Reviewer — adversarial PR review, a different model in a separate context.
- Verifier — compiled and ran the parity checks and tests in a fresh sandbox.

A failed review or verification returned the task to the implementer; a PR
merged only after both passed.

## The oracle

The TypeScript binary was the oracle, through four parity specifications:

- TUI parity — a differential suite ran both binaries against the same
  scripted model and diffed rendered terminal frames (launch, slash menus,
  tool calls, compaction, subagents, resume, crash recovery).
- Harness parity — session transcripts and the requests sent to the model
  provider diffed; the same inputs must yield the same sessions.
- Protocol parity — every daemon protocol message type checked against the
  TypeScript implementation.
- Feature parity — agents audited the TypeScript product component by
  component, classifying each as matching, partial, or missing, because
  scripted flows cannot cover the whole interface.

Stated limitation: "the parity checks only verified the behavior they
exercised." The rest surfaced when the internal team used the Rust build
daily; agents then reviewed beta users' logs and traces.

## Scale and duration

| Phase | Duration | Agents | Tokens |
|---|---|---|---|
| Rust rewrite | over two weeks | 1,981 | 193.0B |
| Performance hillclimb | three days | 228 | 35.7B |

Over 10,000 sandboxes, 16,758 agent-to-agent messages, two 8-core CPU nodes
each running 100+ concurrent subagents; compilation, type-checking and
diffing offloaded to sandboxes. Model: GLM-5.3. Dollar cost, a parity
percentage, and a defect count are not reported. Release quality took
several more weeks of fixes, feature ports, and polish after parity.

## The humans

- Before the run: built the verification setup the autonomous run needed.
- During: set priorities and made decisions with the root agent.
- After parity: dogfooded the Rust build (the oracle for what the
  differential suite did not exercise); found problems, directed changes,
  reviewed results; agents wrote and tested the changes.
- Hillclimb: a second orchestrator ran profile → build and benchmark against
  baseline → two reviewers on different frontier models audit → merge. No
  numeric targets, deliberately: "a fixed threshold tends to become a
  stopping point." 144+ experiment records, 69+ changes merged; cold start
  736 ms (TS) → 52 ms, large-session RSS 1,130 MB → 237 MB.

## What transfers

1. The verifier is built before the run and is the humans' main pre-work.
2. The planner writes the task's parity verifier; the implementer does not.
3. The verifier role is mechanical and runs in a fresh sandbox; merge needs
   both an adversarial cross-model review and a verifier pass.
4. A feature inventory with per-component matching/partial/missing status is
   the coverage map that makes "done" meaningful.
5. The oracle only proves what it exercises; a dogfooding phase with a
   human is scheduled, not improvised.
6. Open-ended optimization gets no numeric target; parity is binary.
