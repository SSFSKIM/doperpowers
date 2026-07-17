# Migrate implement and spike workers from the codex-CLI species to the clodex gateway route

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. It is maintained in accordance with `skills/execplan/references/PLANS.md` from the repository root.

## Purpose / Big Picture

Today this repository's board pipeline runs two different kinds of unattended worker processes ("daemons"). The review side already runs every worker on one harness: a background Claude Code CLI session whose model is routed per dispatch — either through a local proxy gateway to GPT models (the "clodex" route, the default) or to plain Claude models (`engine:claude` opt-out). The implement side still runs its default workers as a *different species entirely*: detached `codex exec` processes (the OpenAI Codex CLI), with their own spawn script, their own resume mechanics, their own liveness rules, and a separate execution-doctrine text because the Codex CLI has no Skill tool and no plugin system.

After this change, an operator dispatching an implement or spike ticket gets the same one-harness world the review loop already has: every worker is a Claude-harness daemon spawned by `daemon-spawn.sh`, and "engine" means only which *model route* the daemon rides — `codex` = the clodex gateway settings (GPT models through the local proxy), `claude` = plain Claude models. The codex CLI is no longer how implement workers run; new codex-CLI workers are not created anywhere in the pipeline. You can see it working by following the dispatch ritual in `skills/issue-tracker/SKILL.md` on a real ticket: the spawned worker appears in `claude agents`, self-reports the gateway model when probed, writes its gate verdict to the board as its first board write, and — when parked and answered — resumes through `board-answer.sh` → `daemon-resume.sh` still on the gateway (the `--settings` flag is restored from registry metadata on every resume fork).

This was deliberately deferred scope: the 2026-07-15 review-loop rebuild (see `docs/doperpowers/execplans/2026-07-15-reviewing-prs-orchestrator-rebuild.md`, Decision Log entry six) migrated only review workers and recorded "implement workers keep their current codex-CLI species; their migration is informed by how the review loop's gateway workers behave in dog-food". That precondition is satisfied: gateway review workers were dog-fooded live on ida-solution PR #570 with sound engine/audit/wave/park behavior. The human partner confirmed proceeding on 2026-07-17, in a brainstorming grill whose decisions are all recorded in the Decision Log below.

## Progress

- [x] (2026-07-17 13:55Z) Brainstorming grill completed in the interactive session; roadmap decision (migration first, skill-as-protocol restructure as a separate later ExecPlan), codex-machinery decision (retire the dispatch path only, keep legacy resume/read paths, no file deletion in this change), and spawn-mechanism decision for the later restructure recorded.
- [x] (2026-07-17 14:05Z) Isolated worktree created at `.claude/worktrees/implement-worker-clodex-migration` on branch `worktree-implement-worker-clodex-migration`, branched from `origin/main` (local main == origin/main at `36bb600`).
- [x] (2026-07-17 14:20Z) Milestone 0: baseline suites green before any edit — implementing-tickets protocol suite, orchestrating-daemons daemon+codex suites, issue-tracker board suite, codex-plugin sync hermetic suite, all "all tests passed"/PASS.
- [x] (2026-07-17 14:35Z) Milestone 1: engine blocks collapsed to one `execution.md` (`git mv` of execution-claude.md; execution-codex.md removed). RED shown first (suite hard-failed on missing execution.md), then 11 single-block assertions GREEN; commit `fadf79f`.
- [x] (2026-07-17 14:45Z) Milestone 2: 6 new assertions RED first, then dispatch ritual steps 2–3 rewritten (route semantics, one `daemon-spawn.sh` command, gateway env + model `fable`, codex-spawn.sh dereferenced), implementing-tickets pieces row + spike web-reach note updated; suite GREEN; commit `35592af`.
- [x] (2026-07-17 14:50Z) Milestone 3: orchestrating-daemons SKILL.md re-framed (one-harness dispatch, codex-CLI = legacy species, codex-spawn.sh/codex-resume.sh rows marked LEGACY); daemon+codex suites still green unchanged; commit `d58cb9b`.
- [x] (2026-07-17 14:55Z) Milestone 4: dated Revision Notes appended to `2026-07-10-codex-workers-design.md` and `2026-07-09-implement-worker-autonomy-design.md`; commit `dcc1c8c`.
- [x] (2026-07-17 15:50Z) Milestone 5: live shakedown complete on SSFSKIM/doperpowers-shakedown — gateway worker spawned via the new ritual (meta: settings+effort+model=fable persisted), parked the taste fork as its FIRST board write, exposed and drove the daemon-finalize blocked-shape fix (commit `7f1814c`, test-first), resumed via `board-answer.sh` still on the gateway (in-session probe `http://localhost:8317` recorded verbatim in the PR), `[gate] re-pass — codex/direct`, PR #2 with `Closes #1` + TDD red→green Validation Evidence + `FOLLOW-UPS: none`. Evidence in Artifacts and Notes.
- [ ] Milestone 6: full verification set green; exit review from a disposable clone; branch pushed; PR opened; retrospective written.

## Surprises & Discoveries

- Observation: the shakedown's park→answer path failed on first try — `board-answer.sh` refused with "bound session … is mid-turn (status=working)" although the worker had cleanly parked and ended its turn. Root cause: the ended session lingered in `claude agents` as `state=blocked, status=idle`, and `daemon-finalize.sh` normalized only the `state=working, status=idle` lying shape (observed 2026-07-15); `blocked` mapped to "live", so the registry meta stayed `working` forever. The legacy codex species never hit this because it self-finalized. This would have broken EVERY gateway implement worker's park→answer flow — exactly what the live shakedown existed to catch.
  Evidence: `claude agents` row `{'status': 'idle', 'state': 'blocked'}` for session c901fbcb while `daemon-finalize.sh` printed `live` and the meta read `status=working`; after the fix (commit `7f1814c`) the same invocation printed `idle` and `board-answer.sh` relayed: `relay: #1 → claude session c901fbcb (status=idle …)`, `#1: needs-human → in-progress`.
- Observation: the worker gate behaved exactly per protocol on the deliberately-unsettled taste fork: first board write was the park (`status:needs-human` label + `[gate] fail` comment naming the greeting decision, with a recommended answer and orientation summary), no code written.
  Evidence: issue #1 labels `["enhancement","status:needs-human","priority:P3"]`; comment "[gate] fail — needs-human: the exact no-argument greeting is an unresolved product-wording decision required by acceptance."

## Decision Log

- Decision: migrate first, restructure later — this ExecPlan covers only the species migration; the skill-as-protocol restructure of `skills/implementing-tickets` (mirroring the reviewing-prs SKILL.md-is-the-protocol shape, bootstrap-file spawn) is a separate, subsequent ExecPlan.
  Rationale: both work items touch the same files; migrating first collapses the two-worker-species fork so the restructure designs against a single harness instead of baking in a structure that would immediately be deleted. Rejected alternative: restructure first (double work on engine blocks); one combined plan (weaker landing points, oversized PR).
  Date/Author: 2026-07-17, human-confirmed in the brainstorming grill.
- Decision: retire the codex-CLI *dispatch path* only. The dispatch ritual stops referencing `codex-spawn.sh`; no pipeline path creates new codex-CLI workers. `codex-spawn.sh`, `codex-resume.sh`, `_codex_lib.sh`, the codex branch in `board-answer.sh`, the codex legacy read/kill paths in `daemon-retire.sh` / review-loop scripts, and `tests/orchestrating-daemons/test-codex-scripts.sh` all remain untouched. Full deletion is a separate follow-up once no bound codex session exists anywhere (consumer repos may hold parked tickets bound to live codex sessions).
  Rationale: mirrors how the review loop retired the species (dispatch stopped, read paths stayed); deleting resume machinery now could strand an existing parked worker. Rejected alternatives: full deletion now (risk to live bound sessions, larger test surgery); leaving the ritual pointing at codex-spawn (keeps minting the very species being retired).
  Date/Author: 2026-07-17, human-confirmed in the brainstorming grill.
- Decision: engine labels keep their names and their resolution order (ticket label `engine:claude`/`engine:codex` → `$WORKER_ENGINE` → default `codex`) but are redefined as the model ROUTE of a single Claude-harness worker: `codex` = gateway settings (GPT models via the local proxy), `claude` = plain Claude models.
  Rationale: exact symmetry with the review loop (`review-dispatch.sh` already implements this semantics); renaming the labels would break existing tickets and cross-repo habits for zero behavior gain.
  Date/Author: 2026-07-17, human-confirmed in the brainstorming grill.
- Decision: the two implement execution blocks (`execution-claude.md`, `execution-codex.md`) collapse into ONE file, `skills/implementing-tickets/references/engine-blocks/execution.md`, based on the claude block's content (plugin-skill references like `doperpowers:execplan`, `doperpowers:test-driven-development`). The codex block's `.agents/skills` vendored-doctrine pointer is dropped from the block.
  Rationale: the split existed only because the Codex CLI lacked the Skill tool and plugin system; a gateway worker IS a Claude-harness session — plugin skills resolve natively regardless of which model the session rides. Keeping a per-route doctrine fork would preserve a distinction with no referent. The file keeps its `engine-blocks/` directory (path stability for the ritual text and future blocks). Rejected alternative: keep two blocks with identical content (drift hazard, lies about a difference that no longer exists).
  Date/Author: 2026-07-17, settled during grill follow-through (mechanical consequence of one harness).
- Decision: the live shakedown (Milestone 5) runs against a scratch GitHub repository with issues enabled, created for the purpose, not against the ida-solution consumer board.
  Rationale: this repo's own GitHub issues are disabled, and coupling a plugin migration's first live run to a production consumer board mixes concerns; the review-loop migration validated its gateway mechanics with probe sessions first, then dog-fooded on the consumer. Consumer dog-food happens naturally on the next real ida-solution dispatch after release. Rejected alternative: shakedown directly on ida-solution (real stakes on an unproven path; a stuck worker there costs a wake-queue cleanup).
  Date/Author: 2026-07-17, resolved autonomously while authoring (feasibility, not taste: both ends were sanctioned by the grill's evidence-first requirement).
- Decision: the gate-comment format `[gate] pass — {{ENGINE_NAME}}/<mode>` is unchanged; `ENGINE_NAME` now names the route (`codex` or `claude`).
  Rationale: the review worker's compliance audit and the board's history parse this line; the route name carries the same operational information (which model family built this).
  Date/Author: 2026-07-17, authoring.
- Decision: mid-execution scope addition — `skills/orchestrating-daemons/scripts/daemon-finalize.sh` gains a second lying-shape normalization (`state=blocked, status=idle` → ended, finalized `idle`, reply recorded through the blocked renderer so a pending AskUserQuestion still surfaces). This amends the plan's original "substrate scripts byte-identical" intent (which was about the LEGACY codex machinery; daemon-finalize is claude-species machinery).
  Rationale: discovered live in Milestone 5 — without it, every gateway implement worker's park→answer relay dead-ends on a stale `working` meta, because claude-species `--no-wait` daemons have no self-finalizer and `board-answer.sh`'s built-in finalize call read the lingering `blocked` state as a live turn. Keeping the harness `status` field as the single turn signal matches the script's own documented doctrine. Rejected alternative: documenting a manual `daemon-finalize` step in the wake ritual (pushes a mechanical reconciliation onto the human; the relay already calls finalize — it just missed this shape).
  Date/Author: 2026-07-17, during Milestone 5.
- Decision: second mid-execution scope addition — `skills/reviewing-prs/scripts/land-dispatch.sh` migrates in this plan too: its default engine spawned the land worker via `codex-spawn.sh`, making it a second live consumer of the codex-CLI spawn path (the grill's "implement dispatch is the last consumer" premise was wrong). The spawn branch now mirrors `review-dispatch.sh`'s gateway route (`DAEMON_CLAUDE_SETTINGS`/`DAEMON_CLAUDE_EFFORT`, model `fable`), test-first in `tests/reviewing-prs/test-land-dispatch.sh`.
  Rationale: leaving it would contradict the settled decision "no new codex-CLI workers anywhere" and the rewritten orchestrating-daemons doctrine ("no pipeline path creates new ones") — and the operation manual already claimed the land worker is "same daemon machinery, not a third species", so the code was out of line with its own documentation. Rejected alternative: registering it as a follow-up (ships a doctrine the code visibly violates).
  Date/Author: 2026-07-17, during Milestone 6's reference sweep.

## Outcomes & Retrospective

Pending — written at finish.

## Context and Orientation

All paths are relative to the repository root (`doperpowers`, a fork of obra/superpowers — a plugin of agent "skills": markdown behavior-protocols loaded by coding agents). The pieces that matter here:

**The board pipeline.** Work is tracked as GitHub issues ("tickets") managed by the scripts in `skills/issue-tracker/scripts/` (`board-list.sh`, `board-register.sh`, `board-transition.sh`, `board-bind.sh`, `board-answer.sh`, `board-reconcile.sh`). An operator (a human's interactive Claude session) dispatches a ticket by following "The dispatch ritual" in `skills/issue-tracker/SKILL.md`: render a worker-protocol markdown file into a prompt (substituting `{{PLACEHOLDER}}` tokens), spawn a background worker with that prompt, and bind the worker's session id to the ticket (`board-bind.sh`). The worker gates the ticket, builds, and opens a PR; the review loop (`skills/reviewing-prs/`) takes it from there.

**Daemons.** A daemon is a durable background worker session tracked in a registry at `~/.claude/orchestrating-daemons`. The substrate scripts live in `skills/orchestrating-daemons/scripts/`. Two species exist today: (a) Claude-harness daemons — background Claude Code CLI sessions spawned by `daemon-spawn.sh <name> <task> [cwd] [worktree] [model]`, resumed by `daemon-resume.sh` (a resume *forks* a new session that carries the conversation; the registry chains ids); (b) codex-CLI daemons — detached `codex exec --json` processes spawned by `codex-spawn.sh`, resumed by `codex-resume.sh` (one session id for life), sharing the same registry with `engine: codex` metadata. This plan retires species (b) from the *dispatch ritual*; its scripts remain as legacy machinery.

**The gateway ("clodex") route.** `~/.claude/clodex-settings.json` is a Claude Code `--settings` file that points `ANTHROPIC_BASE_URL` at a local proxy (`http://localhost:8317`) which maps Claude model aliases (fable/opus/sonnet) to GPT models. A Claude-harness daemon spawned with these settings is a full Claude Code session (Skill tool, Task subagents, resume machinery, plugin skills) whose *model* is a GPT model. `daemon-spawn.sh` already supports this: the env vars `DAEMON_CLAUDE_SETTINGS` (a `--settings` path) and `DAEMON_CLAUDE_EFFORT` (an `--effort` value) are forwarded to the spawn AND persisted into the daemon's registry metadata (`settings`, `effort` keys); `daemon-resume.sh` reads them back and re-passes `--settings`/`--effort` on every resume fork — without that, a gateway daemon silently reverts to plain Claude models on its first resume. This substrate is proven: the review loop has dispatched gateway workers through it since 2026-07-15 (see `skills/reviewing-prs/scripts/review-dispatch.sh`, the `engine = codex` branch around line 364: `DAEMON_CLAUDE_SETTINGS="${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}" DAEMON_CLAUDE_EFFORT="${CLODEX_EFFORT:-xhigh}" daemon-spawn.sh --no-wait <name> <prompt> <worktree> "" "${REVIEW_MODEL:-fable}"`), and it was verified live that a resume fork with `--settings` stays on the gateway while one without silently reverts.

**The implement worker protocol.** `skills/implementing-tickets/references/implement-worker-protocol.md` is the text rendered into an implement worker's spawn prompt. It contains a `{{EXECUTION_BLOCK}}` placeholder which the dispatch ritual fills from a per-engine file in `skills/implementing-tickets/references/engine-blocks/`: currently `execution-claude.md` (references doperpowers plugin skills directly) or `execution-codex.md` (same discipline, but routes skill doctrine through a `.agents/skills` vendored copy because the codex CLI cannot load plugins). `references/spike-worker-protocol.md` is rendered instead for tickets whose category is `spike`; it has no execution block. Both protocols carry an `{{ENGINE_NAME}}` placeholder used in the worker's `[gate] pass — <engine>/<mode>` board comment.

**Tests are prose-invariant asserts.** `tests/implementing-tickets/test-protocol-content.sh` greps the protocol and skill files for load-bearing clauses (this repo treats skill prose as behavior — the tests pin it). Its "engine blocks:" section currently asserts both per-engine files exist with specific content. `tests/orchestrating-daemons/test-codex-scripts.sh` and `test-daemon-scripts.sh` are hermetic integration tests over the substrate scripts (stub `codex`/`claude` binaries on PATH). `tests/issue-tracker/test-board-scripts.sh` covers the board scripts with a mock `gh`. `tests/codex-plugin-sync/test-sync-to-codex-plugin.sh` is a hermetic regression over the outward distribution script.

**What already reads correctly and must NOT be touched.** The review loop's legacy codex read paths (`review-dispatch.sh` pid-liveness for old codex metas, `land-dispatch.sh` equivalents), `board-answer.sh`'s codex branch (`engine == codex → codex-resume.sh`), `daemon-retire.sh`'s codex kill path, and the whole `test-codex-scripts.sh` suite: these are the legacy machinery the grill decided to keep. `RELEASE-NOTES.md` is history — never edited retroactively.

## Plan of Work

Milestone 0 — baseline. In the worktree, run the four suites named in Concrete Steps and record that they pass before any edit. This distinguishes pre-existing breakage from breakage this plan introduces.

Milestone 1 — collapse the engine blocks (test-first). Edit `tests/implementing-tickets/test-protocol-content.sh`: replace the "engine blocks:" section's two-file assertions with single-file assertions over `skills/implementing-tickets/references/engine-blocks/execution.md` — assert the file exists; assert it contains `doperpowers:execplan`, `EXECPLAN:`, `writing-plans`, `subagent-driven-development`, `claim completion on reasoning alone`, `big-but-atomic`; assert it does NOT contain `.agents/skills` (the codex-CLI-only vendored-doctrine pointer must not survive into the one-harness block), `work ALONE`, or `YOURSELF`. Run the suite — the new assertions must FAIL against the still-two-file tree (RED). Then: create `execution.md` with the content of today's `execution-claude.md` (reproduced in Artifacts and Notes below so this plan is self-contained), delete `execution-claude.md` and `execution-codex.md`, and re-run the suite (GREEN). The implement protocol itself (`implement-worker-protocol.md`) does not change — `{{EXECUTION_BLOCK}}` and `{{ENGINE_NAME}}` remain placeholders; only what the ritual substitutes into them changes.

Milestone 2 — rewrite the dispatch ritual and the implementing-tickets doctrine. In `skills/issue-tracker/SKILL.md`, "The dispatch ritual" section: step 2 currently reads "Resolve the ENGINE — ticket label `engine:claude`/`engine:codex` → `$WORKER_ENGINE` → default `codex`" and later binds `EXECUTION_BLOCK` to "the engine's `references/engine-blocks/execution-<engine>.md`". Rewrite step 2 so the resolution order is unchanged but the meaning is stated as the model route of one Claude-harness worker (codex = clodex gateway settings / GPT models, claude = plain Claude models), and `EXECUTION_BLOCK` binds to the single `references/engine-blocks/execution.md`. Step 3 currently forks on species: "codex: `codex-spawn.sh …` (model/effort default gpt-5.6-sol/high — override with `$CODEX_MODEL`/`$CODEX_EFFORT` as args 5–6). claude: `daemon-spawn.sh …`". Rewrite it to ONE spawn command for both routes: `daemon-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>` — with the codex route prefixing the environment `DAEMON_CLAUDE_SETTINGS="${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}" DAEMON_CLAUDE_EFFORT="${CLODEX_EFFORT:-xhigh}"` and passing model `fable` (arg 5), the claude route passing no env and leaving model to inherit — exactly the review loop's convention, stated in the ritual's prose. Remove every `codex-spawn.sh` mention from this file. In `skills/implementing-tickets/SKILL.md`: rewrite the pieces-table row for `references/engine-blocks/` (currently "per-engine EXECUTION text (claude: TDD/execplan skills; codex: the same discipline via the vendored `.agents/skills` doctrine)") to describe the single execution block composed into the protocol at render time, and note that both routes are Claude-harness sessions. Update the spike-lane bullet "Research-heavy spikes often want `engine:claude` (web reach); the label mechanism is unchanged" — web reach is now harness-level (every worker has it); the engine label is purely a model-route preference. Add test-first assertions for the load-bearing new prose (see Validation) to `test-protocol-content.sh` in the same RED→GREEN discipline: at minimum, assert the issue-tracker SKILL no longer contains `codex-spawn.sh` — note the file is in a *different* skill directory, so the test must derive its path from `$REPO_ROOT/skills/issue-tracker/SKILL.md`.

Milestone 3 — re-frame the substrate doc. `skills/orchestrating-daemons/SKILL.md`: the overview paragraph currently says "The substrate drives two engines under one registry: `claude --bg` daemons and detached `codex exec` workers (`engine: codex` in the meta) — the board pipeline picks per dispatch (label → `WORKER_ENGINE` → codex)." Rewrite: the board pipeline dispatches Claude-harness daemons only, with the engine label selecting the model route (gateway settings vs plain); detached `codex exec` workers are a legacy species — existing registry metas remain readable/resumable/retirable, no pipeline path creates new ones. Mark the `codex-spawn.sh` pieces-table row "(legacy — retired from board dispatch; kept until no bound codex sessions remain)" and leave the `codex-resume.sh` row as the legacy-session continuation path.

Milestone 4 — living-spec revision notes. Append a dated entry to `## Revision Notes` in `docs/doperpowers/specs/2026-07-10-codex-workers-design.md` (the spec that created the codex-CLI implement-worker species and the per-engine blocks): the species is retired from dispatch as of this plan; engine labels now name model routes; the vendored-doctrine execution block is gone; legacy machinery retained pending a separate deletion follow-up; pointer to this ExecPlan. Same for `docs/doperpowers/specs/2026-07-09-implement-worker-autonomy-design.md` (its engine-block description changed). Do not rewrite historical body text — revision notes only, per the living-spec doctrine (`skills/execspec/`).

Milestone 5 — live shakedown (evidence, not hope). Create a throwaway GitHub repo (issues enabled) with a trivial code surface, register one synthetic P3 ticket via `board-register.sh` with a fully-authored body (a change small enough for a direct-mode build, e.g. "add a --version flag to the hello script; print 0.1.0"), then perform the NEW ritual by hand exactly as written: render the protocol with the single execution block, spawn via `daemon-spawn.sh` with the gateway env, `board-bind.sh` the printed uuid. Observe and record: (1) the worker's registry meta contains `settings` and `effort` keys (inspect the meta file under `~/.claude/orchestrating-daemons`); (2) the worker's first board write is `in-progress` + a `[gate] pass — codex/<mode>` comment; (3) a deterministic gateway probe from inside the worker's turn — ask it (or have the ticket require it to log) `echo ${ANTHROPIC_BASE_URL:-unset}` — shows the local proxy, not unset (self-reported model ids are context-echo-prone; trust the env probe); (4) park/resume: post a follow-up via `board-answer.sh` and confirm the resumed fork still rides the gateway (repeat the env probe; also confirm `daemon-resume.sh` passed `--settings` by checking the new session's spawn args in the registry). (5) the PR closes the loop (`Closes #N`, `## Validation Evidence` present). If the gateway proxy is down (`curl -s http://localhost:8317` fails), restart it (`brew services restart cliproxyapi` — its credential cooldowns are in-memory) before concluding anything about the pipeline. Tear the scratch repo down afterwards; paste the key transcript lines into Artifacts and Notes.

Milestone 6 — verification, exit review, PR. Run the full suite set (Concrete Steps). Then the exit gate: from an EMPTY temp directory, `git clone` this worktree's repo, check out the branch, and run `codex exec review --base main` there (never in-place — the codex review agent wanders the filesystem and picks up neighboring git contexts; also never on a dirty tree). Read only what follows "Final review comments:"; triage every finding (fix or record why not). Then push the branch and open a PR against `main` titled for the migration, and finish with doperpowers:finishing-a-development-branch — its retrospective step writes this plan's `Outcomes & Retrospective`.

## Concrete Steps

All commands run from the worktree root (`.claude/worktrees/implement-worker-clodex-migration` under the repo, itself a full checkout).

Baseline and per-milestone verification:

    tests/implementing-tickets/test-protocol-content.sh
    tests/orchestrating-daemons/test-daemon-scripts.sh
    tests/orchestrating-daemons/test-codex-scripts.sh
    tests/issue-tracker/test-board-scripts.sh
    tests/codex-plugin-sync/test-sync-to-codex-plugin.sh
    scripts/lint-shell.sh
    git diff --check

Each prints per-assert `[PASS]`/`[FAIL]` lines and exits non-zero on any failure; "all tests passed" (or the suite's equivalent summary) is the success marker. `test-codex-scripts.sh` must stay green UNCHANGED — it now covers legacy machinery, and a failure there means this plan touched something the grill said to keep.

Milestone 1 file operations:

    git mv skills/implementing-tickets/references/engine-blocks/execution-claude.md \
           skills/implementing-tickets/references/engine-blocks/execution.md
    git rm skills/implementing-tickets/references/engine-blocks/execution-codex.md

(Then edit `execution.md` per Artifacts and Notes — the claude block is already plugin-skill-based; verify no `.agents/skills` reference remains.)

Shakedown scaffolding (Milestone 5), sketch:

    gh repo create <user>/doperpowers-shakedown --private --add-readme
    # enable issues (on by default), clone to a scratch dir, add hello script, push
    SKILLDIR=<abs path to>/skills/issue-tracker/scripts
    "$SKILLDIR/board-register.sh" "hello: add --version flag" enhancement P3 --body-file <spec.md>
    # render prompt per the NEW ritual, then:
    DAEMON_CLAUDE_SETTINGS="$HOME/.claude/clodex-settings.json" DAEMON_CLAUDE_EFFORT=xhigh \
      <abs path to>/skills/orchestrating-daemons/scripts/daemon-spawn.sh --no-wait \
      "1-hello-version" "<prompt>" <scratch-repo-path> issue-1 fable
    "$SKILLDIR/board-bind.sh" <uuid> 1

Commit at every green point with small, described commits (no Co-Authored-By lines, per repo convention).

## Validation and Acceptance

Acceptance is behavior, observed twice over — hermetically and live:

1. `tests/implementing-tickets/test-protocol-content.sh` passes and now asserts: exactly one execution block exists (`references/engine-blocks/execution.md`); it routes execplan mode through `doperpowers:execplan`; it does not reference `.agents/skills`; the implement protocol's placeholder set is unchanged (`{{EXECUTION_BLOCK}}`, `{{ENGINE_NAME}}`, … — the `want=` line in the test does not change); `skills/issue-tracker/SKILL.md` contains no `codex-spawn.sh` reference; the two engine-block files `execution-claude.md`/`execution-codex.md` no longer exist. Before Milestone 1's edits, the new assertions fail (RED shown in the transcript); after, the whole suite passes.
2. `tests/orchestrating-daemons/test-codex-scripts.sh` and `test-daemon-scripts.sh` pass with zero modifications to either suite or to any script under `skills/orchestrating-daemons/scripts/`.
3. Reading `skills/issue-tracker/SKILL.md`'s dispatch ritual end-to-end, a novice operator would spawn BOTH routes through `daemon-spawn.sh`; the word `codex-spawn` does not appear in the file; the codex route's command line includes `DAEMON_CLAUDE_SETTINGS` and model `fable`.
4. The live shakedown (Milestone 5) shows, in order: a spawned worker whose registry meta carries `settings`/`effort`; `[gate] pass — codex/…` as the ticket's first non-registration board event; an in-worker env probe printing the local proxy URL; a `board-answer.sh` resume whose forked session still probes to the proxy URL; a PR with `Closes #N`. Every one of these is a transcript/board artifact pasted into this plan.
5. `scripts/lint-shell.sh` and `git diff --check` are clean; the codex-plugin sync hermetic suite passes (the sync script mirrors skills — the engine-block rename must not break it).

## Idempotence and Recovery

Every edit is a tracked-file change on an isolated branch; re-running a milestone means re-applying edits that are already there (no-ops) and re-running suites (read-only). The engine-block collapse is a `git mv` + `git rm` — recoverable with `git checkout` until commit, `git revert` after. The shakedown's writes land only in a throwaway repo and the daemon registry: retire the worker (`daemon-retire.sh <uuid>`) and delete the scratch repo (`gh repo delete`) to clean up; a failed shakedown leaves the main repo untouched. If the gateway proxy is refusing (in-memory credential cooldown after a quota reset), `brew services restart cliproxyapi` and re-probe before drawing conclusions. If a resume fork ever probes to plain Anthropic instead of the proxy, that is the known settings-drop failure — check that the registry meta still has the `settings` key and that the resume went through `daemon-resume.sh` (not a hand-rolled `--resume`).

## Artifacts and Notes

The single execution block, `skills/implementing-tickets/references/engine-blocks/execution.md`, verbatim (this is today's `execution-claude.md`, which is already correct for a Claude-harness worker on either model route — carried unchanged; the codex variant's `.agents/skills` plumbing is the only content dropped from the union):

    EXECUTION (gate passed) — name the mode in the gate comment.
    Every claim of done carries EVIDENCE appropriate to the change — never
    claim completion on reasoning alone:
    - testable logic: TDD (doperpowers:test-driven-development) — failing
      test first. Green checks are what keep your PR self-merge-eligible.
    - UI/visual changes: build + run it — verify the actual rendered
      behavior (E2E where the repo has it); write tests only where behavior
      is assertable without theater.
    - config/docs/infra: the relevant check (build, lint, dry-run) passes.
    Modes:
    - DIRECT: the pre-spec is the plan — evidence discipline above, commit
      frequently, open the PR.
    - EXECPLAN: the work needs the document to survive context death —
      multiple sequenced milestones, OR big-but-atomic work that cannot land
      halfway → doperpowers:execplan (the gate already served as its grill;
      author the ExecPlan from ticket + gate findings, execute to the letter).
    Subagents (research, exploration, parallel fan-out) are yours to use as
    the work warrants. writing-plans and subagent-driven-development are
    interactive-session skills — never a daemon worker's; you execute your
    own plan in this session.

Current dispatch-ritual step 3 (`skills/issue-tracker/SKILL.md`), the text being replaced — kept here so a reader can locate it without git history:

    3. codex: `codex-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>`
       (model/effort default gpt-5.6-sol/high — override with
       `$CODEX_MODEL` / `$CODEX_EFFORT` as args 5–6). claude:
       `daemon-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>`. Both
       from `orchestrating-daemons` — always a worktree; workers write code.

Shakedown evidence (Milestone 5, all from SSFSKIM/doperpowers-shakedown — repo deleted after; transcripts preserved here):

    # spawn (new ritual, gateway route):
    daemon spawned (no-wait): 1-hello-version  [c901fbcb / c901fbcb-...]  status=working
    # registry meta after spawn:
    {'name': '1-hello-version', 'model': 'fable',
     'settings': '/Users/new/.claude/clodex-settings.json', 'effort': 'xhigh', ...}
    # first board write = the gate verdict (park, no code):
    labels: ["enhancement","status:needs-human","priority:P3"]
    "[gate] fail — needs-human: the exact no-argument greeting is an
     unresolved product-wording decision required by acceptance." (+ recommended
     answer `hello`, + orientation summary)
    # answer relay (after the daemon-finalize fix):
    relay: #1 → claude session c901fbcb (status=idle, ...)
    #1: needs-human → in-progress
    # resumed fork still on the gateway — worker's in-session probe, verbatim
    # from PR #2's Validation Evidence:
    echo "${ANTHROPIC_BASE_URL:-unset}"   →   http://localhost:8317
    # gate re-verdict and closure:
    "[gate] re-pass — codex/direct: the human approved the exact default
     greeting `hello` ..."
    PR #2 "Add hello.sh version flag": Closes #1; TDD red phase recorded
    (test.sh exited 1 before, 0 after); FOLLOW-UPS: none; ticket → in-review.

Exit-review verdict: appended at Milestone 6.

## Interfaces and Dependencies

No new code interfaces. The contract surfaces at the end of this plan:

- `skills/implementing-tickets/references/engine-blocks/execution.md` exists; `execution-claude.md` and `execution-codex.md` do not.
- `skills/issue-tracker/SKILL.md` dispatch ritual: engine = model route; both routes spawn via `skills/orchestrating-daemons/scripts/daemon-spawn.sh`; the codex route's documented invocation carries `DAEMON_CLAUDE_SETTINGS` (default `${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}`), `DAEMON_CLAUDE_EFFORT` (default `${CLODEX_EFFORT:-xhigh}`), and model `fable`.
- `skills/orchestrating-daemons/scripts/*` byte-identical to `main`, with ONE exception decided mid-flight (Decision Log): `daemon-finalize.sh` normalizes the ended `state=blocked, status=idle` shape to a finalized-idle meta. All LEGACY codex machinery (`codex-spawn.sh`, `codex-resume.sh`, `_codex_lib.sh`) is byte-identical.
- `skills/implementing-tickets/references/implement-worker-protocol.md` and `spike-worker-protocol.md` byte-identical to `main` (placeholder sets unchanged).
- External dependencies, unchanged from the review loop's: the local cliproxy gateway on `localhost:8317`, `~/.claude/clodex-settings.json`, the `claude` CLI daemon supervisor, `gh`.

## Revision Notes

- 2026-07-17 (authoring): initial plan, authored from the brainstorming grill of the same date.
