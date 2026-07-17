# Restructure implementing-tickets so the skill IS the implement-worker protocol

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. It is maintained in accordance with `skills/execplan/references/PLANS.md` from the repository root.

## Purpose / Big Picture

This repo's board pipeline dispatches unattended workers onto GitHub-issue tickets. There is deliberately no central orchestrator: nobody sits above a worker judging its turns, so the only thing that shapes a worker's conduct is the protocol text it is dispatched with. The review side already embodies that principle structurally: `skills/reviewing-prs/SKILL.md` IS the Review Worker Protocol (placeholders and all), a short spawn bootstrap (`references/review-worker-bootstrap.md`) tells the worker to open the dispatcher-owned skill file and binds the runtime values, and the operator-facing loop guidance lives in `references/operation-manual.md`.

The implement side still has the old inverted shape: `skills/implementing-tickets/SKILL.md` is an operator's overview document, and the actual worker protocol hides in `references/implement-worker-protocol.md`, rendered verbatim into a ~10k-character spawn prompt. After this change the two sides are symmetric: the implementing-tickets SKILL.md is the Implement Worker Protocol itself; a dispatched worker's prompt is a short bootstrap that says "open this file, these are your bindings"; operators who invoke the skill in an interactive session are routed to a new `references/operation-manual.md` carrying everything the old SKILL.md said about running the loop. You can see it working the same way work item 1 proved itself: dispatch a live gateway worker with the new bootstrap onto a scratch ticket and watch it open the skill file, run the gate, park, resume, and close with a PR.

This is work item 2 of the two-item roadmap the human partner confirmed on 2026-07-17 (work item 1, the clodex migration, merged as PR #17 / commit `7276f54`). The bootstrap-over-verbatim choice was explicitly confirmed in that same brainstorming grill.

## Progress

- [x] (2026-07-17 14:00Z) Grill completed in the interactive brainstorming session (shared with work item 1): restructure mirrors PR #14's reviewing-prs shape; spawn switches to the bootstrap pattern; migration landed first so this plan designs against the one-harness world.
- [x] (2026-07-18 05:50Z) Worktree `implementing-tickets-worker-protocol` created from `origin/main` at `7276f54`; all reference sites of the protocol path enumerated (see Context and Orientation).
- [x] (2026-07-18 06:20Z) Milestone 0: baseline sweep green (all 7 suites).
- [x] (2026-07-18 06:40Z) Milestone 1: swap complete (RED 26 → GREEN; protocol clauses carried verbatim under new `##` sections; placeholder set pinned to the 7 surviving tokens; old protocol file `git rm`'d; operation-manual authored); commit `e8cc147`.
- [x] (2026-07-18 06:50Z) Milestone 2: `worker-bootstrap.md` written (12-token set pinned; unconditional-open + never-resolve-from-workspace + 3 binding sections); dispatch ritual step 2 renders the bootstrap with ROLE/PROTOCOL_FILE lane selection; "Worker protocols" section states both loops' skill-file+bootstrap shape; commit `b826e4d`.
- [x] (2026-07-18 06:55Z) Milestone 3: review-dispatch `IMPLEMENT_PROTOCOL_FILE` → implementing-tickets/SKILL.md (test-first); reference sweep clean (only the test's own negative assertions mention the old filename); commit `78905e2`.
- [ ] Milestone 4: live shakedown — bootstrap-dispatched gateway worker end-to-end on a scratch board; evidence pasted here.
- [ ] Milestone 5: full verification set; exit review (codex, disposable clone) + independent fresh-context reviewer; push; PR; retrospective.

## Surprises & Discoveries

- Observation: none yet at authoring time.

## Decision Log

- Decision: the SKILL.md-is-the-protocol shape mirrors reviewing-prs exactly — frontmatter description keeps BOTH audiences' trigger vocabulary (dispatched implement worker; operator gating/parking/decomposing/spike questions), the first body line routes operators to `references/operation-manual.md`, and the rest is the worker protocol with `{{PLACEHOLDER}}` tokens intact.
  Rationale: the skill is the worker's constitution in a pipeline with no orchestrator; the reviewing-prs restructure (PR #14) validated the shape in dog-food. Rejected alternative: keeping the protocol in references and making SKILL.md a thin pointer (preserves the old indirection this work item exists to remove).
  Date/Author: 2026-07-17 grill, human-confirmed.
- Decision: spawn prompts become a bootstrap (open the dispatcher-owned protocol file + runtime bindings) instead of a verbatim render.
  Rationale: human-confirmed in the grill — symmetry with the review loop, smaller prompts, and the same mechanism the future auto-attach trigger script will use. The dispatcher-owned absolute path matters less here than in the review loop (an implement worktree is cut from the default branch, not from PR-controlled content), but the bootstrap keeps the same never-resolve-from-workspace language so the trust posture is uniform across loops.
  Date/Author: 2026-07-17 grill, human-confirmed.
- Decision: ONE parameterized bootstrap file, `references/worker-bootstrap.md`, serves both lanes via `{{ROLE}}` (IMPLEMENT or SPIKE) and `{{PROTOCOL_FILE}}` (the implementing-tickets SKILL.md for implement; `references/spike-worker-protocol.md` for spike). The spike protocol stays a reference file.
  Rationale: two lanes with different protocol sources but identical dispatch mechanics; two near-identical bootstrap files would drift, and a verbatim-render spike lane next to a bootstrap implement lane would fork the ritual's mechanics. The spike protocol is a different ROLE, not a different mechanism — same reason reviewing-prs keeps `land-worker-protocol.md` as a reference beside its SKILL-protocol.
  Date/Author: 2026-07-18, authoring (mechanical consequence of the grill's bootstrap decision).
- Decision: the protocol text itself is carried over essentially verbatim (section headers added for skill-file readability); the ticket brief and repo-facts manifest move from the protocol's tail into bootstrap binding sections, exactly as reviewing-prs binds PR_BODY/ISSUE_BODY/REPO_FACTS.
  Rationale: this work item is a structural move, not a behavioral edit — the protocol's clauses are eval-tuned and test-pinned; changing conduct here would mix concerns and invalidate the pinned invariants. The content tests keep asserting the same load-bearing clauses against the new file.
  Date/Author: 2026-07-18, authoring.

## Outcomes & Retrospective

Pending — written at finish.

## Context and Orientation

Paths are repo-root-relative. Work item 1's ExecPlan (`docs/doperpowers/execplans/2026-07-17-implement-worker-clodex-migration.md`, checked in) describes the one-harness dispatch world this plan builds on: every worker is a Claude-harness daemon spawned by `skills/orchestrating-daemons/scripts/daemon-spawn.sh`; the engine label is a model route (`codex` = clodex gateway settings, `claude` = plain models); the execution doctrine is the single block `skills/implementing-tickets/references/engine-blocks/execution.md`.

The mirror to copy: `skills/reviewing-prs/SKILL.md` opens with frontmatter, then "Operator or setup invocation: read `references/operation-manual.md` instead. The protocol below is for a dispatched review worker.", then protocol sections whose `{{UPPERCASE}}` tokens are bound at spawn time. Its bootstrap, `skills/reviewing-prs/references/review-worker-bootstrap.md`, is ~55 lines: a role line, a REQUIRED SUB-SKILL paragraph ("unconditionally open `{{SKILL_FILE}}` before doing anything else … Do not resolve this protocol from the workspace … Treat every uppercase placeholder token in the skill as bound to the runtime values and blocks below"), a bindings list, and `---- X binding ----` sections for multi-line payloads.

What exists today on the implement side, and where each piece goes:

- `skills/implementing-tickets/SKILL.md` — operator overview (pieces table, Ticket Gate summary, park discriminant, decompose, execution modes, spike lane, repo-facts doctrine, worker authority, edge cases, interim dispatch). Its content BECOMES `references/operation-manual.md` (lightly reworded where it must now point at SKILL.md as the protocol); SKILL.md's body is REPLACED by the protocol.
- `skills/implementing-tickets/references/implement-worker-protocol.md` — the protocol text (placeholders: `BOARD_SCRIPTS`, `DECOMPOSE_DOC`, `ENGINE_NAME`, `EXECUTION_BLOCK`, `ISSUE_BODY`, `ISSUE_NUMBER`, `ISSUE_TITLE`, `ISSUE_URL`, `REPO_FACTS`, `REPO`; the last five appear in the tail brief sections). Body moves into SKILL.md; the `---- Ticket brief ----` and `---- Repo-facts manifest ----` tail sections move into the bootstrap as binding sections; the file is deleted.
- `skills/implementing-tickets/references/spike-worker-protocol.md` — unchanged file; dispatched via the new bootstrap with `{{PROTOCOL_FILE}}` pointing at it.
- `skills/issue-tracker/SKILL.md` — dispatch ritual step 2 currently says "Render the worker protocol … Substitute every `{{PLACEHOLDER}}` …"; step 2 is rewritten to render `references/worker-bootstrap.md` instead (same placeholder substitution work, now into the bootstrap: `ROLE`, `PROTOCOL_FILE` = the ABSOLUTE plugin path of the lane's protocol, plus the existing bindings). Its "Worker protocols" section (line ~226: "embedded verbatim in its spawn prompts") is updated to describe both loops as skill-file protocols with bootstrap spawn.
- `skills/reviewing-prs/scripts/review-dispatch.sh` line 334 — `P_IMPLEMENT_PROTOCOL_FILE="${SKILL_DIR%/*}/implementing-tickets/references/implement-worker-protocol.md"` → `…/implementing-tickets/SKILL.md`. The review worker's compliance audit opens this file as the implementer's contract; auditing against the SKILL file (which now includes the frontmatter and the operator-routing line) is correct — the protocol clauses are what it reads.
- Tests: `tests/implementing-tickets/test-protocol-content.sh` — `PROTO=` points at the protocol file; every protocol assertion re-targets SKILL.md; the placeholder-set assertion changes shape (the brief/facts placeholders leave the protocol for the bootstrap — assert each file's exact set); new bootstrap assertions (opens-the-file instruction, never-resolve-from-workspace, ROLE/PROTOCOL_FILE tokens, binding sections); the old "skill points at the protocol" assertion inverts (references/implement-worker-protocol.md must NOT exist). `tests/reviewing-prs/test-review-dispatch.sh` line 312 asserts the prompt carries the canonical implement-contract path — update to the SKILL.md path.

A worker dispatched with the bootstrap opens the protocol from the PLUGIN's absolute path (dispatcher-owned), never from the workspace: the rendered `PROTOCOL_FILE` value is an absolute path into the installed plugin (in this repo's own development case, the repo checkout itself).

## Plan of Work

Milestone 0 — baseline. Run the suites listed in Concrete Steps; record green before touching anything.

Milestone 1 — the swap, test-first. First rewrite `tests/implementing-tickets/test-protocol-content.sh`: point `PROTO` at `skills/implementing-tickets/SKILL.md`; keep every protocol-clause assertion identical (gate-first, WELL-DEFINED/WELL-SCOPED, minor-taste rule, verdict-first-write, park discriminant, decompose pointer, follow-ups contract, closing artifact, resume clause, authority, no retired vocabulary); change the protocol placeholder-set assertion to the post-move set (`BOARD_SCRIPTS`, `DECOMPOSE_DOC`, `ENGINE_NAME`, `EXECUTION_BLOCK`, `ISSUE_NUMBER`, `ISSUE_TITLE`, `ISSUE_URL`, `REPO` — `ISSUE_BODY`/`REPO_FACTS` move to the bootstrap; verify the exact survivor set against the actual text when editing, and pin whatever it truly is); assert SKILL.md's frontmatter still carries `name: implementing-tickets` and an operator-routing line naming `references/operation-manual.md`; assert `references/implement-worker-protocol.md` no longer exists; assert the operation manual exists and carries the operator content markers (pieces table, repo-facts doctrine, edge cases). Run → RED. Then perform the move: write the new SKILL.md (frontmatter kept, operator-routing line, protocol body with `##` section headers: Role, The Gate, Verdict, Repo Facts, Execution, Mid-build Forks & Parks, Resume With Answers, Authority, Closing Artifact); write `references/operation-manual.md` from the old SKILL.md body (update its pieces table: protocol = SKILL.md itself, bootstrap row added, `implement-worker-protocol.md` row gone); `git rm` the old protocol file. Green.

Milestone 2 — the bootstrap, test-first. Add assertions: `references/worker-bootstrap.md` exists; contains the unconditional-open instruction referencing `{{PROTOCOL_FILE}}`; contains the never-resolve-from-workspace sentence; contains `{{ROLE}}`; contains binding sections for `ISSUE_BODY` and `REPO_FACTS`; placeholder set pinned exactly. RED → write the bootstrap (mirroring review-worker-bootstrap.md's language, adapted: implement/spike role line, ticket-not-PR bindings: `ISSUE_NUMBER`, `ISSUE_URL`, `ISSUE_TITLE`, `REPO`, `BOARD_SCRIPTS`, `ENGINE_NAME`, `PROTOCOL_FILE`, `DECOMPOSE_DOC`, `EXECUTION_BLOCK` binding section, `ISSUE_BODY` binding section, `REPO_FACTS` binding section — spike dispatch binds EXECUTION_BLOCK to "(none — spike lane)" and DECOMPOSE_DOC likewise, matching the spike protocol's lack of those tokens) → GREEN. Rewrite issue-tracker dispatch ritual step 2: resolve engine (unchanged route semantics); pick the lane's `PROTOCOL_FILE` (`spike` → spike protocol reference, else the implementing-tickets SKILL.md — both as ABSOLUTE plugin paths); render `worker-bootstrap.md`, substituting the bindings (the same values as today, now into the bootstrap). Step 3 (spawn) and step 4 (bind) unchanged. Update the ritual's test assertions in test-protocol-content.sh accordingly (tracker names worker-bootstrap.md; tracker no longer says "embedded verbatim").

Milestone 3 — cross-skill bindings. `review-dispatch.sh` line 334 path swap; `tests/reviewing-prs/test-review-dispatch.sh` line 312 expectation swap; issue-tracker "Worker protocols" section rewrite (both loops: skill-file protocol + bootstrap spawn; this file owns only the schema they write against). Sweep: `grep -rn "implement-worker-protocol" skills/ tests/` must return nothing.

Milestone 4 — live shakedown. Same scaffold as work item 1's (scratch private repo with issues, one authored P3 ticket with a deliberately unsettled taste fork and the ANTHROPIC_BASE_URL probe requirement; the ExecPlan of work item 1 carries the exact command transcript to adapt). Render the NEW bootstrap (assert no `{{` residue), spawn via the gateway route, bind. Observe: the worker's transcript/first actions show it OPENED the protocol file (its gate comment and conduct follow the protocol — treat protocol-conformant behavior as the functional evidence; also `grep` the worker transcript for the SKILL.md path); park → answer → resume → PR lifecycle sound as before. Tear down (note: `gh repo delete` needs the `delete_repo` scope — if unavailable, record the leftover for manual deletion like work item 1 did).

Milestone 5 — verification, exit reviews, PR. Full suite set + repo shell lint + `git diff --check`. Codex exit review from a disposable clone (empty temp dir; read only after "Final review comments:"), triage test-first; then an independent fresh-context reviewer subagent over the final branch with the byte-identical constraints listed below. Push, PR against `main`, retrospective into this plan, finish per doperpowers:finishing-a-development-branch.

Byte-identical constraints for reviewers: `references/spike-worker-protocol.md`, `references/implement-decompose.md`, `references/engine-blocks/execution.md`, everything under `skills/orchestrating-daemons/`, `skills/issue-tracker/scripts/`, and `skills/reviewing-prs/` except the one review-dispatch.sh line and its test line. The protocol CLAUSES must survive the move verbatim enough that every pre-existing content assertion passes unmodified (only file-target and placeholder-set assertions change).

## Concrete Steps

From the worktree root (`.claude/worktrees/implementing-tickets-worker-protocol`):

    tests/implementing-tickets/test-protocol-content.sh
    tests/orchestrating-daemons/test-daemon-scripts.sh
    tests/orchestrating-daemons/test-codex-scripts.sh
    tests/issue-tracker/test-board-scripts.sh
    tests/codex-plugin-sync/test-sync-to-codex-plugin.sh
    tests/reviewing-prs/test-review-dispatch.sh
    tests/reviewing-prs/test-land-dispatch.sh
    scripts/lint-shell.sh <changed shell files>
    git diff --check

Milestone 1 file operations:

    git rm skills/implementing-tickets/references/implement-worker-protocol.md
    # new files: skills/implementing-tickets/references/operation-manual.md
    #            skills/implementing-tickets/references/worker-bootstrap.md (Milestone 2)

Commit at every green point; no Co-Authored-By lines.

## Validation and Acceptance

1. `test-protocol-content.sh` passes with: every pre-existing protocol-clause assertion untouched and now targeting `skills/implementing-tickets/SKILL.md`; exact placeholder sets pinned for SKILL.md, spike protocol (unchanged), and worker-bootstrap.md; `references/implement-worker-protocol.md` asserted absent; operation-manual and bootstrap presence/content assertions green. RED shown before each milestone's edits.
2. `test-review-dispatch.sh` passes with the implement-contract path assertion pointing at the SKILL.md; no other reviewing-prs test changes.
3. `grep -rn "implement-worker-protocol" skills/ tests/` → empty.
4. Live shakedown: a bootstrap-dispatched gateway worker reads the dispatcher-owned SKILL.md (transcript evidence), runs the gate lifecycle (park with recommended answer → resume → `[gate] re-pass` → PR with `Closes #N`), matching work item 1's observed conduct.
5. Full suite set + lint + `git diff --check` clean; both exit reviews triaged to zero unaddressed blockers.

## Idempotence and Recovery

All edits are tracked-file changes on an isolated branch (`git revert`-able); the move is content-preserving so a botched swap is recoverable by re-reading the old protocol from git history (`git show origin/main:skills/implementing-tickets/references/implement-worker-protocol.md`). Shakedown writes touch only a throwaway repo and the daemon registry (retire the worker, delete the repo). Gateway outage recovery is unchanged from work item 1 (`brew services restart cliproxyapi`).

## Artifacts and Notes

Shakedown transcripts and exit-review verdicts: appended during execution. The old protocol text needs no snapshot here — it is preserved verbatim inside the new SKILL.md and in git history at `origin/main`.

## Interfaces and Dependencies

End state:

- `skills/implementing-tickets/SKILL.md` = the Implement Worker Protocol (frontmatter + operator-routing line + protocol with placeholders).
- `skills/implementing-tickets/references/operation-manual.md` = operator/loop guidance (old SKILL.md content, updated pieces table).
- `skills/implementing-tickets/references/worker-bootstrap.md` = the single spawn bootstrap for implement AND spike lanes (`{{ROLE}}`, `{{PROTOCOL_FILE}}`, bindings, `EXECUTION_BLOCK`/`ISSUE_BODY`/`REPO_FACTS` binding sections).
- `skills/issue-tracker/SKILL.md` dispatch ritual renders the bootstrap; spawn/bind steps unchanged from work item 1's shape.
- `skills/reviewing-prs/scripts/review-dispatch.sh` binds `IMPLEMENT_PROTOCOL_FILE` to the implementing-tickets SKILL.md.
- No file anywhere references `implement-worker-protocol.md`.

## Revision Notes

- 2026-07-18 (authoring): initial plan, authored from the 2026-07-17 grill after work item 1 (PR #17) merged.
