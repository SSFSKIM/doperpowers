# Vendor the Codex companion runtime into doperpowers as the `codex-companion` skill

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. It is maintained in accordance with `skills/execplan/references/PLANS.md` (the ExecPlan doctrine vendored into this repository).

## Purpose / Big Picture

Today, using OpenAI's Codex as a second-opinion reviewer or task delegate from Claude Code goes through the separately installed `openai-codex` plugin (`/codex:review`, `/codex:adversarial-review`, `/codex:rescue`). Every one of those slash commands is marked `disable-model-invocation: true`, meaning only a human typing the command can fire them — the agent cannot decide on its own judgment to run a Codex review, which blocks the workflows doperpowers actually wants (multi-lens review sweeps, autonomous final-branch reviews, resumable Codex discussion partners). The `/codex:rescue` path additionally routes through a sonnet subagent that exists only to forward one Bash call.

After this change, doperpowers carries its own `skills/codex-companion/` bundle: the OpenAI plugin's Node runtime vendored byte-identically, fronted by a single model-invocable SKILL.md that acts as an index (progressive disclosure into reference docs). Any Claude session with doperpowers installed can run a Codex review, an adversarial lens review, or a delegated write-capable Codex task by invoking one `node` command directly — no slash command, no subagent hop, no second plugin. You can see it working by asking a session "run a codex review of this branch against main" and watching it invoke the vendored runtime and return Codex's findings.

## Progress

- [x] (2026-08-01) Milestone 1: runtime vendored byte-identically (incl. `.claude-plugin/plugin.json` — see Surprises), adapted tests pass under `node --test`: 81 pass / 0 fail via `tests/codex-companion/run-codex-companion-tests.sh`. `commands.test.mjs` and `bump-version.test.mjs` deleted (they test the dropped commands layer and the upstream repo's version tooling, not the runtime).
- [x] (2026-08-01) Milestone 2: `skills/codex-companion/SKILL.md` (index, model-invocable, trigger-only description) + `references/{reviews,delegation,jobs}.md` written; canonical invocation verified live via `setup --json` (ready:true, codex-cli 0.145.0, ChatGPT auth). Note: vendored `setup` output mentions `/codex:setup --enable-review-gate` in nextSteps — an upstream advisory string we cannot patch (byte-identity); harmless.
- [x] (2026-08-01) Milestone 3: live verification against the real Codex CLI — `setup` ready-check; foreground working-tree review returned a correct P2 finding on the planted bug, exit 0; `status` listed running/finished jobs at the pinned state root (`~/.claude/doperpowers/codex-companion/state/…`); `cancel <job-id>` killed an orphaned job; `task` + `task --resume-last` round-trip resumed the same thread with a context-dependent correct answer; background review detached via harness background Bash, auto-woke on completion, and `result` retrieved the stored findings (3 valid P2s) plus the Codex session id for `codex resume`.
- [x] (2026-08-01) Milestone 4: consumer swaps — `skills/execplan/SKILL.md` exit gate and `skills/subagent-driven-development/SKILL.md` final-review step (a consumer the plan missed, found by grep) now route through doperpowers:codex-companion; `~/.claude/CLAUDE.md` Independent Reviews section rewritten to the skill's `review` verb (`--model gpt-5.6-sol`, background Bash, effort via codex config). `skills/reviewing-prs` deliberately untouched (deferred round).
- [ ] Milestone 5: version bump, release, uninstall the openai-codex plugin

## Surprises & Discoveries

- Observation: the OpenAI plugin's review/task execution paths never leave a resident broker process. `plugins/codex/scripts/lib/codex.mjs` connects with `disableBroker: true` (per-invocation `codex app-server` child) or `reuseExistingBroker: true` (attach only if one already exists); `ensureBrokerSession` — the only spawner — is reached solely from hook/stop-gate paths we are not vendoring. Dropping the hook layer therefore leaks nothing.
  Evidence: `grep -n "disableBroker\|reuseExistingBroker" plugins/codex/scripts/lib/codex.mjs` → lines 635, 645 (`disableBroker: true`), 944, 982 (`reuseExistingBroker: true`).
- Observation: the runtime hard-requires `.claude-plugin/plugin.json` next to `scripts/` — `lib/app-server.mjs` reads it at module load to build the client-info version it reports to the Codex app-server. The initial vendor set omitted it and every runtime test failed with ENOENT. Resolution: vendor it byte-identical as part of the runtime tree.
  Evidence: `Error: ENOENT … skills/codex-companion/runtime/.claude-plugin/plugin.json` from `app-server.mjs:20` during `node --test`; suite went 81 pass / 0 fail after the copy.
- Observation: any session with the openai-codex plugin installed has `CLAUDE_PLUGIN_DATA`, `CODEX_COMPANION_SESSION_ID`, and `CODEX_COMPANION_TRANSCRIPT_PATH` injected into its shell environment by that plugin's SessionStart hook. This broke the state-dir tmpdir-fallback test and would silently redirect our pinned state root until the plugin is uninstalled. The test runner strips these vars; the skill's explicit `CLAUDE_PLUGIN_DATA=…` prefix wins either way.
  Evidence: `env | grep CLAUDE_PLUGIN_DATA` in this session → `/Users/new/.claude/plugins/data/codex-openai-codex`.
- Observation: the first foreground-review verification returned "no changes to review" and it was the runtime being RIGHT, not a bug: an interrupted earlier attempt had already created the scratch fixture, and a later `git add -A` commit had swept it in, so the tree really was clean. Amended the file out of that commit and re-ran with a genuinely untracked fixture → correct P2 finding (unquoted `$CONFIG_FILE` word-splitting). Lesson: `git add -A` around scratch fixtures is how verification fixtures leak into history.
  Evidence: `git log --all -- scratch-review-target.sh` showed it inside the amigo-rename commit; after amend, review returned the P2 finding with the exact line reference.
- Observation: an interrupted foreground run leaves its job record (and possibly its Codex turn) alive as `running` — the harness kill doesn't reach the job ledger. `cancel <job-id>` cleaned it up correctly.
  Evidence: `status` showed the orphan at 7m11s elapsed; `cancel review-ms9gm7f6-sujbj2` → "Cancelled".

## Decision Log

- Decision: vendor the runtime wholesale and byte-identical (`scripts/` + `lib/` + `prompts/` + `schemas/`), rather than referencing the installed openai-codex plugin's cache path or extracting a trimmed subset.
  Rationale: referencing the installed plugin couples doperpowers to another plugin's install location and version and the bundle stops being self-contained; a trimmed fork of ~5.3k lines maximizes initial work and destroys the cheap `diff` channel against future upstream releases. Byte-identical wholesale costs nothing at runtime and keeps bugfix imports a one-diff operation.
  Date/Author: 2026-08-01 / brainstorming session with human partner.
- Decision: single skill (`skills/codex-companion/`) with an index-style SKILL.md and progressive disclosure into `references/`, not a per-use-case skill split and not a rebrand of the original three internal skills.
  Rationale: one trigger surface ("the model needs the Codex runtime"); the original three-skill split existed to serve a subagent/slash-command architecture we are deleting. Human partner explicitly chose the index + progressive-disclosure shape.
  Date/Author: 2026-08-01 / human partner.
- Decision: do not vendor the commands/, agents/, hooks/ layers, the `/codex:transfer` feature, the stop-review-gate, or the `gpt-5-4-prompting` guidance.
  Rationale: commands were `disable-model-invocation: true` ceremony around the same runtime; the rescue agent was a pure forwarder; hooks exist only for broker teardown (not needed — see Surprises), transfer transcript injection (feature dropped by human partner), and the stop gate (unwanted). Human partner judged the prompting guide unnecessary.
  Date/Author: 2026-08-01 / human partner.
- Decision: after live verification, uninstall the openai-codex plugin; manual use goes through natural language, no doperpowers slash command added.
  Rationale: the model-invocable skill covers both agent-initiated and human-asked runs; keeping both installed leaves two state directories and two job registries for the same runtime.
  Date/Author: 2026-08-01 / human partner.
- Decision: pin the runtime's state root by exporting `CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion"` on every invocation, written into the skill's canonical command lines.
  Rationale: the runtime falls back to `os.tmpdir()/codex-companion` when that env is unset (see `lib/state.mjs`), and tmpdir is periodically purged — job history (`status`/`result`/`--resume-last`) would silently vanish. Setting env at the call site keeps the vendored scripts unpatched.
  Date/Author: 2026-08-01 / planning session.
- Decision: the task-verb reference is `references/amigo.md`, not `delegation.md`, and frames `task` as a resumable partner rather than one-shot delegation.
  Rationale: human partner's mid-implementation call — `--resume` makes the verb a standing discussion/critique partner (the future brainstorming-critique integration depends on exactly this), so naming it "delegation" undersold and would mis-anchor future consumers.
  Date/Author: 2026-08-01 / human partner.
- Decision: tests are vendored *adapted*, not byte-identical — the import prefix `../plugins/codex/` is rewritten to point at the vendored tree.
  Rationale: byte-identity protects the diff channel for the runtime we execute; tests are our safety net and must import from where the code actually lives. A mechanical prefix rewrite is trivially re-appliable to future upstream test updates.
  Date/Author: 2026-08-01 / planning session.

## Outcomes & Retrospective

Pending — written at finish.

## Context and Orientation

This repository (`doperpowers`) is a Claude Code plugin whose product is the `skills/` directory: one directory per skill, each with a `SKILL.md` whose frontmatter `name` and `description` drive when the model loads it. There is no `commands/` or `hooks/` directory — hooks were deliberately removed from this fork. The plugin is installed from a locally served marketplace; releasing means bumping the version with `scripts/bump-version.sh`, committing, pushing, and letting the marketplace pull.

The source being vendored is the OpenAI Codex plugin for Claude Code, checked out at `/Users/new/developer/github/codex-plugin-cc/` (Apache-2.0; `LICENSE` and `NOTICE` at its repo root, duplicated in `plugins/codex/`). Its runtime lives under `plugins/codex/`:

    plugins/codex/scripts/codex-companion.mjs     — the CLI entrypoint (verbs: setup, review,
                                                    adversarial-review, task, transfer, status,
                                                    result, cancel; plus internal task-worker /
                                                    task-resume-candidate)
    plugins/codex/scripts/app-server-broker.mjs   — optional resident broker (we never spawn it)
    plugins/codex/scripts/lib/*.mjs               — 16 modules (~4k lines): app-server JSONL client,
                                                    git scoping, job state, rendering, arg parsing
    plugins/codex/prompts/adversarial-review.md   — template read at runtime via lib/prompts.mjs
    plugins/codex/prompts/stop-review-gate.md     — template for the stop gate (unused by us, but
                                                    vendored to keep the tree byte-identical)
    plugins/codex/schemas/review-output.schema.json — review output schema, resolved as
                                                    ROOT_DIR/schemas/… where ROOT_DIR is the parent
                                                    of scripts/ (codex-companion.mjs line 67)
    tests/*.test.mjs + helpers                    — node:test suite at the OUTER repo root, using a
                                                    fake `codex` fixture (no real Codex needed);
                                                    imports use the prefix ../plugins/codex/

Because `ROOT_DIR` is computed as the parent directory of `scripts/`, the vendored tree must preserve the relative layout `<root>/scripts/`, `<root>/scripts/lib/`, `<root>/prompts/`, `<root>/schemas/`.

Terms: "app-server" is Codex's long-lived JSON-RPC-over-stdio server mode (`codex app-server`); the runtime spawns one as a child per invocation and talks JSONL to it. A "job" is the runtime's record of one review/task run, stored as JSON under the state root so `status`, `result`, `cancel`, and `--resume-last` work across processes. The state root is `$CLAUDE_PLUGIN_DATA/state/<workspace-slug>-<hash>/` with a tmpdir fallback.

Runtime facts confirmed by reading the source, which the skill docs must carry: `review` accepts `--base <ref>`, `--scope auto|working-tree|branch`, `--model <m>` (alias `spark` → `gpt-5.3-codex-spark`), `--json`, `--background`, `--wait`, `--cwd`; it does NOT accept `--effort` or focus text. `adversarial-review` accepts the same plus trailing positional focus text. `task` accepts `--write`, `--model`, `--effort none|minimal|low|medium|high|xhigh`, `--resume-last|--resume|--fresh`, `--background`, `--prompt-file`, and positional prompt text; without `--write` it is read-only. `--background` in the script only shapes the job record — actual detachment comes from running the whole command with the harness's background Bash. In this harness a background Bash job wakes the session on completion, so `status` polling is only for cross-session checks or mid-flight peeks at long runs, not a required loop.

Existing consumers to touch: `skills/execplan/SKILL.md` names `codex exec review --base <base-branch>` in its exit gate; the user-global `~/.claude/CLAUDE.md` has an "Independent Reviews" section routing through `/codex:review --base <ref> --background --model gpt-5.6-sol`. NOT in scope (deferred to later rounds, per the brainstorm): `skills/reviewing-prs`'s own `codex exec review` engine, and any brainstorming-critique integration.

## Plan of Work

Milestone 1 — vendor. Create `skills/codex-companion/runtime/` and copy, byte-identical, from `/Users/new/developer/github/codex-plugin-cc/plugins/codex/`: `scripts/` (all `.mjs` including `lib/`, excluding nothing — the two hook scripts `session-lifecycle-hook.mjs` and `stop-review-gate-hook.mjs` ride along unreferenced to keep the tree diffable), `prompts/`, `schemas/`, `LICENSE`, `NOTICE`. Do not copy `commands/`, `agents/`, `hooks/`, `skills/`, `.claude-plugin/`, `CHANGELOG.md`. Verify byte-identity with a checksum comparison over the copied set. Then vendor the test suite: copy the outer repo's `tests/*.mjs` into `tests/codex-companion/`, rewriting only the import prefix `../plugins/codex/scripts/` → `../../skills/codex-companion/runtime/scripts/` (a `sed` over the copied files), and add a small `tests/codex-companion/run-codex-companion-tests.sh` that runs `node --test tests/codex-companion/*.test.mjs` from the repo root, following the runner convention of the sibling test dirs. Record the upstream commit hash of the source checkout in a one-line `skills/codex-companion/runtime/VENDORED-FROM` file (repo URL + commit + date) so future diffs have an anchor.

Milestone 2 — the skill. Write `skills/codex-companion/SKILL.md` as an index, in doperpowers voice, model-invocable (no `user-invocable: false`, no `disable-model-invocation`). Frontmatter description must trigger on needing the Codex runtime: independent/second-opinion code review, adversarial or lens-focused review, delegating implementation/diagnosis to Codex, resuming a prior Codex thread. The body carries only what the model cannot derive: the canonical invocation line (`CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" node "<skill-base>/runtime/scripts/codex-companion.mjs" <verb> …` — the Skill tool supplies the base directory at load time), a one-line-per-verb index routing to references, and the two harness facts that prevent misuse (backgrounding is the harness's `run_in_background`, which auto-wakes on completion; the state env must always be set or job history lands in tmpdir). Reference docs, each loaded only when needed: `references/reviews.md` (review vs adversarial-review contract, exact flags, focus-text semantics, `--json` for programmatic consumers, when to background, `setup` as preflight), `references/amigo.md` (task contract: `--write` semantics and read-only default, `--effort`, resume trio `--resume-last|--resume|--fresh`, `--prompt-file` for long prompts; framed as a resumable partner — critique debates, steered execution — not just one-shot delegation), `references/jobs.md` (status/result/cancel, job ids, cross-session use, where state lives). Per this repo's rules, skill content follows doperpowers:writing-skills; this is a new skill in a personal fork, so the bar is a sanity pass (description triggers on the intended phrasings, instructions executable as written), not a full eval round.

Milestone 3 — live verification, exact scenarios in Validation below. Run from this repository's working tree using the real `codex` CLI (already installed and authenticated on this machine; `setup` verb confirms).

Milestone 4 — consumer swaps. In `skills/execplan/SKILL.md`, replace the exit-gate parenthetical `(codex native review: \`codex exec review --base <base-branch>\`; …)` with the companion equivalent (route through the doperpowers:codex-companion skill, review verb with `--base <base-branch>`), keeping the fresh-Claude-reviewer fallback clause. In `~/.claude/CLAUDE.md`, rewrite the "Independent Reviews" section to route through the doperpowers:codex-companion skill (review verb, `--base <ref>`, background, `--model gpt-5.6-sol`) instead of the `/codex:review` slash command — preserve the model and effort intent as written there.

Milestone 5 — release and cutover. Bump the version with `scripts/bump-version.sh` (minor bump — new skill), commit everything (plan file updates included), push, refresh the marketplace-installed copy, then uninstall the openai-codex plugin and confirm the `/codex:*` commands and `codex:*` skills are gone while the new skill loads.

## Concrete Steps

All commands run from the repository root (the git worktree containing this file) unless stated.

Milestone 1:

    SRC=/Users/new/developer/github/codex-plugin-cc/plugins/codex
    DST=skills/codex-companion/runtime
    mkdir -p "$DST"
    cp -R "$SRC/scripts" "$SRC/prompts" "$SRC/schemas" "$DST/"
    cp "$SRC/LICENSE" "$SRC/NOTICE" "$DST/"
    ( cd "$SRC" && find scripts prompts schemas -type f -exec shasum -a 256 {} + | sort -k2 ) > /tmp/src.sums
    ( cd "$DST" && find scripts prompts schemas -type f -exec shasum -a 256 {} + | sort -k2 ) > /tmp/dst.sums
    diff /tmp/src.sums /tmp/dst.sums     # expect: no output
    git -C /Users/new/developer/github/codex-plugin-cc rev-parse HEAD   # goes into VENDORED-FROM

    mkdir -p tests/codex-companion
    cp /Users/new/developer/github/codex-plugin-cc/tests/*.mjs tests/codex-companion/
    # rewrite import prefixes (exact relative depth: tests/codex-companion/ → skills/…)
    sed -i '' 's#\.\./plugins/codex/scripts/#../../skills/codex-companion/runtime/scripts/#g' tests/codex-companion/*.mjs
    node --test tests/codex-companion/*.test.mjs

Expected: the suite passes (upstream ships it green; the fake-codex fixture removes any dependency on a real Codex install). One test file (`bump-version.test.mjs`) targets the outer repo's version tooling, not the runtime — if it fails for path reasons, delete it rather than adapting it, and note that in Progress. If any other test fails, stop and diagnose before proceeding: it means the path rewrite or the copy is wrong, not the runtime.

Milestone 2: write the three reference files first, then SKILL.md so the index matches what exists. Sanity checks: every command line in the docs must be runnable verbatim (test at least one per file by pasting it); the SKILL.md description read cold should fire on "run a codex review", "get a second opinion on this diff", "hand this bug to codex", and should NOT fire on generic code-review requests that doperpowers' own review machinery handles.

Milestone 3 (validation scenarios; see next section for acceptance).

Milestone 4:

    grep -n "codex exec review" skills/execplan/SKILL.md    # locate the exit-gate line, then edit
    # edit ~/.claude/CLAUDE.md "Independent Reviews" section

Milestone 5:

    ./scripts/bump-version.sh minor
    git add -A && git commit
    git push origin HEAD
    claude plugin --help    # discover exact subcommands on this machine
    # then: update/refresh the doperpowers marketplace install, uninstall codex@openai-codex
    # (if the CLI lacks these verbs, do it via /plugin in an interactive session and note it here)

## Validation and Acceptance

Milestone 1 acceptance: the checksum diff is empty (byte-identity proven) and `node --test tests/codex-companion/*.test.mjs` reports 0 failures.

Milestone 3 acceptance, three scenarios against the real Codex CLI:

1. Foreground review. Make a two-line scratch edit on a throwaway branch of this repo (e.g. introduce an obvious unused variable in a shell script), then run
       CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" node skills/codex-companion/runtime/scripts/codex-companion.mjs review --wait --scope working-tree
   Expect: rendered review output on stdout (finding list or explicit "no findings"), exit code 0, and a new job directory under `$HOME/.claude/doperpowers/codex-companion/state/`. Revert the scratch edit.
2. Background review + jobs. Run the same command with `--background` via a backgrounded Bash. Expect: immediate stdout naming a job id; `… status` shows it queued/running; on completion (harness wake) `… result` prints the stored review. This proves job state survives across processes at the pinned state root.
3. Task resume round-trip. Run
       … task --wait "summarize the purpose of scripts/bump-version.sh in two sentences"
   (read-only, no `--write`), expect a sensible answer; then
       … task --wait --resume-last "now name its input config file"
   and expect an answer referencing `.version-bump.json`, proving thread resume works from the vendored location.

Milestone 4 acceptance: `grep -rn "codex exec review" skills/execplan/` returns nothing; the user CLAUDE.md section names the skill, not `/codex:review`.

Milestone 5 acceptance: after cutover, a fresh Claude Code session in any repo shows `doperpowers:codex-companion` in its skill list and no `codex:*` entries; asking that session for "a codex review of the working tree" invokes the vendored runtime (observable in the transcript as the `node …codex-companion.mjs review` Bash call).

## Idempotence and Recovery

The vendor copy is idempotent — rerunning `cp -R` over the same destination converges, and the checksum diff is the arbiter. The state root under `$HOME/.claude/doperpowers/codex-companion` can be deleted at any time; the runtime recreates it (only job history is lost). If live verification fails because of Codex auth, run the `setup` verb for diagnosis and `codex login` interactively; nothing in this plan changes Codex configuration. Uninstalling the openai-codex plugin is reversible via reinstall from its marketplace; do it only after Milestone 3 passes. If the release step goes out mid-failure, the fork's convention applies: fix forward on the branch, bump again if manifests already shipped.

## Interfaces and Dependencies

The bundle depends on: Node.js ≥ 18.18 (runtime engine requirement), the `codex` CLI installed and authenticated on the host (checked by the `setup` verb), and `git` (the runtime shells out for scoping). The vendored entrypoint contract that the skill docs expose, verbatim from the source (`codex-companion.mjs` printUsage, minus `setup`'s gate flags and minus `transfer`):

    node …/runtime/scripts/codex-companion.mjs setup [--json]
    node …/runtime/scripts/codex-companion.mjs review [--wait|--background] [--base <ref>] [--scope <auto|working-tree|branch>] [--model <m>] [--json]
    node …/runtime/scripts/codex-companion.mjs adversarial-review [--wait|--background] [--base <ref>] [--scope <auto|working-tree|branch>] [--model <m>] [--json] [focus text]
    node …/runtime/scripts/codex-companion.mjs task [--background] [--write] [--resume-last|--resume|--fresh] [--model <m|spark>] [--effort <none|minimal|low|medium|high|xhigh>] [--prompt-file <p>] [prompt]
    node …/runtime/scripts/codex-companion.mjs status [job-id] [--all] [--json]
    node …/runtime/scripts/codex-companion.mjs result [job-id] [--json]
    node …/runtime/scripts/codex-companion.mjs cancel [job-id] [--json]

Every invocation is prefixed with `CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion"`. No file under `runtime/` may be modified — behavior changes happen at the call site (env, flags) or in the skill docs, never by patching vendored code.
