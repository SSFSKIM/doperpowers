# Native review recovery — one codex reviewer for both worker species (2026-07-12)

## Purpose

Restore the review loop's product core: **a review worker calls the native
`codex exec review` engine and receives a compact structured verdict — the
PR diff never lands in the worker's own context.** The verdict→fix→re-review
→confident-ready loop then runs exactly as today.

The current state deviates from that core. The codex-workers build
(2026-07-10) hit two walls — the `--base`-vs-`[PROMPT]` clap conflict, then
FU-7's nested-sandbox failure — and over-corrected to a species-split
engine: a Codex worker reviews **in-thread** (the whole PR diff enters its
main context, the exact opposite of the compact-verdict property), and a
Claude worker calls the cookbook plain-`codex exec` form. Both walls are
now overturned by live spikes (2026-07-12, codex-cli 0.144.1,
gpt-5.6-sol):

- **Fixed review policy rides as config, not PROMPT.** `-c
  developer_instructions="…"` carries correctness and compliance discipline
  past the clap conflict. PR and ticket text stay in an external file that
  the policy explicitly labels untrusted data — `codex exec review --base`
  still works in ONE call (rc=0, both planted findings, ~1KB structured
  `-o` output).
- **Codex-in-codex review works** with three environment fixes:
  `SSL_CERT_FILE=/etc/ssl/cert.pem` (FU-6, already shipped), inner
  `-c sandbox_mode="danger-full-access"` (macOS forbids applying a second
  Seatbelt profile; the flag only skips self-profiling — the OUTER
  workspace-write profile still confines every child), and
  `CODEX_CODE_MODE_HOST_PATH=$HOME/.local/bin/codex-code-mode-host` (nested
  codex misresolves the code-mode host to `/usr/local/bin/`). Plus the
  already-known isolated writable `CODEX_HOME` + symlinked `auth.json`.
  Verified end-to-end: nested reviewer under an outer seatbelted
  `codex exec` returned rc=0 with zero `sandbox_apply` / host-spawn errors
  and produced both the correctness and the compliance finding.

The human's mandate (2026-07-12): the reviewer is **codex-only**, the
review worker shell is **codex** (workspace-write + `approval_policy=
on-request` + `approvals_reviewer=auto_review`, unchanged), and the
Claude-reviewer-subagent fallback is deleted. When the codex CLI is down,
the ticket stays `in-review` — `needs-human` means "human judgment/input
required", never "infrastructure failed".

## Ground truth (verified live 2026-07-12)

- The reviewer invocation, identical for both worker species:

  ```
  codex exec review --base origin/<base> \
    -m $CODEX_REVIEW_MODEL -c model_reasoning_effort=$CODEX_REVIEW_EFFORT \
    -c features.hooks=false \
    -c developer_instructions="<fixed policy referencing criteria-file>" \
    --json -o <findings-file>
  ```

  Reviews the full multi-commit range `origin/<base>...HEAD`; the fixed
  developer policy carries ONLY the spec-compliance addendum (the native
  review owns code quality itself — Revision Note 3) and reads the ticket
  text from an explicitly untrusted data file (Revision Note 2). Output is
  the compact structured verdict in the `-o` file. `codex exec review` (not
  top-level `codex review`) is the right form — it has
  `-o`/`--json`/`-m`; top-level `codex review` has none of those.
- The engine runs `git diff` **via shell** (`/bin/zsh -lc`), not
  in-process — that's why nesting needs the environment recipe above.
- Current worker-shell flags (`_codex_lib.sh`): `--sandbox
  workspace-write`, `sandbox_workspace_write.network_access=true`,
  `approval_policy=on-request`, `approvals_reviewer=auto_review`,
  `features.hooks=false`. Confirmed correct for the fix-writing worker;
  this spec changes nothing about them.
- Full spike evidence: memory `codex-native-review-devinstr`; spike repo
  `scratchpad/native-review-spike` (planted `[P2]` div-by-zero correctness
  bug + `[P1]` missing-`median` compliance gap; both found nested and
  non-nested).

## Design

### 1. One engine, one script — `review-engine.sh`

New `skills/reviewing-prs/scripts/review-engine.sh`, the single owner of
the reviewer invocation. The hard-won recipe becomes executable, lintable,
testable code instead of prose an LLM re-types every round.

```
review-engine.sh --base <ref> --criteria <file> --out <file>
```

- Model/effort from env `CODEX_REVIEW_MODEL` (default `gpt-5.6-sol`) /
  `CODEX_REVIEW_EFFORT` (default `xhigh`) — same knobs and defaults as
  `review-dispatch.sh`.
- Owns the environment recipe, each part applied only when needed:
  temporary `CODEX_HOME` outside the reviewed tree with `auth.json`
  symlinked from the caller's `${CODEX_HOME:-$HOME/.codex}` (created for
  the run, removed after);
  `SSL_CERT_FILE=/etc/ssl/cert.pem`
  and `CODEX_CODE_MODE_HOST_PATH=$HOME/.local/bin/codex-code-mode-host`
  each exported only if unset (and, for the host path, only if the binary
  exists).
- **Conditional** `-c sandbox_mode="danger-full-access"`: passed **only
  when the script is itself running inside a codex sandbox** (detected via
  the `CODEX_SANDBOX` env var codex exports to its children — a
  front-loaded verification task in the plan). Nested, the flag is the
  only way past the second-Seatbelt wall and the outer profile still
  confines the child; non-nested (Claude-species worker on the host) the
  flag would be a real, unjustified widening, so the engine runs under
  codex's default sandbox.
- Fixed developer instructions reference the criteria file as untrusted
  review context. PR-controlled titles, bodies, and ticket text never enter
  the developer-level config value.
- Exits with codex's rc; the findings file is the engine's output.

Both species call the same file: the codex worker nested, the
`engine:claude` opt-out worker non-nested. "Reviewer is codex-only" is
literally one script.

### 2. Engine block and fallback rewrite

- `references/engine-blocks/engine-codex-review.md`: drop the in-thread
  instruction, the cookbook form, and the "codex-in-codex is structurally
  broken" prose. New shape: write the untrusted context file (the
  ticket's requirements ONLY, as data — never into developer
  instructions; ticket "none" → an empty file, and the engine then sends
  no developer instructions at all — Revision Notes 2-4), run
  `{{REVIEW_ENGINE}}`, read the findings file. The
  work-alone rule gets a one-line carve-out: the engine call is a tool
  invocation, not a nested agent (the same status the cookbook form had).
- The protocol's ORIENT step drops its full-diff read (`git diff
  origin/<base>...HEAD`) for a shape-only read (`git diff --stat`): the
  engine reviews the range, and a worker that pre-reads the whole diff
  re-creates exactly the context dump this spec removes. The worker reads
  only the code each finding names.
- The two fallback blocks merge into ONE (`fallback-engine.md`): the
  Claude-reviewer-subagent fallback is deleted; both species behave
  identically on engine failure (see §3). `review-dispatch.sh` loses the
  per-species fallback branch and gains the `{{REVIEW_ENGINE}}`
  placeholder (absolute path to the script, resolved from `SKILL_DIR` like
  `BOARD_SCRIPTS`).

### 3. Engine down → ticket stays `in-review`, sweep retries

When the engine call fails (missing CLI, auth failure, or repeated API
errors after 2 retries with a short backoff):

- The worker posts the review-trail comment ("engine unavailable:
  <error>"), touches **no** board state (the ticket remains `in-review`),
  and ends its turn with a final message whose last line is the
  machine-readable marker `ENGINE-UNAVAILABLE`.
- The sweep gains one dedupe-table row: a **finished** registry entry
  whose reply contains the `ENGINE-UNAVAILABLE` marker is retired and the
  PR re-dispatched. Recovery is automatic on the first sweep (~30 min)
  after the CLI is healthy again — no human decision manufactured, no
  `in-review` limbo that nobody ever returns to.
- `needs-human` is never written by this path: that state is reserved for
  open questions/scoping/real-world input, which an infra outage is not.

### 4. Substrate — one export

`_codex_launch` (orchestrating-daemons `_codex_lib.sh`) exports
`CODEX_CODE_MODE_HOST_PATH=$HOME/.local/bin/codex-code-mode-host` when
unset and the binary exists — beside the existing `SSL_CERT_FILE` export,
same only-if-unset pattern. Worker-shell flags unchanged.

### 5. Documentation surfaces

- `skills/reviewing-prs/SKILL.md` "Review engine" section rewritten: one
  native engine, one script, both species; species differ only in
  nesting; engine-down semantics per §3.
- codex-workers spec (`2026-07-10-codex-workers-design.md`): Revision
  Note recording the two overturned conclusions, pointing here.
- Shakedown doc FU-7 section: dated correction note pointing here.

## Out of scope

- The implement-worker pipeline (spawn/resume substrate, board rituals) —
  untouched beyond the one env export.
- Auto-merge rollout policy (`AUTO_MERGE_ENABLED` staging) — unchanged.
- Top-level `codex review` — rejected (no `-m`/`-o`/`--json`).
- Upstreaming — fork-local product core.

## Acceptance

- A codex review worker's transcript shows the PR verdict arriving as a
  compact findings file from `review-engine.sh` — no full-diff dump into
  the worker's main context; the trail comment names the native engine.
- `review-engine.sh` run **non-nested** against the spike repo returns
  rc=0 and both planted findings (compliance + correctness).
- The same script run **nested** (inside a seatbelted `codex exec`)
  returns the same, with zero `sandbox_apply` and zero code-mode-host
  spawn errors.
- No protocol/fallback text anywhere instructs an in-thread review or a
  Claude reviewer subagent; both species' rendered prompts carry the same
  engine block and the same single fallback block.
- With the codex CLI made unavailable, a review worker ends with the
  `ENGINE-UNAVAILABLE` marker, the ticket still `in-review`, and the next
  sweep retires the entry and re-dispatches the PR.
- `scripts/lint-shell.sh` green; the review-dispatch test suite green,
  including a sweep test for the marker row.
- One live SD-style shakedown cell: a real PR reviewed end-to-end through
  the script by a codex worker (verdict → routing → escalation tier).

## Decision Log

1. **Engine invocation owned by a substrate script (chosen) vs prose
   engine block vs dispatch-time prerender.** Prose (the current pattern)
   would have the worker re-assemble the 3-env recipe + quoting every
   round — the walls this design overcomes were all environment bugs, and
   prose is where they'd regress. Dispatch prerender can't cover
   re-review rounds (the command must re-run after fixes). The script
   makes the recipe testable and the "same engine both species" claim
   literal.
2. **Engine down → `in-review` + sweep-retry marker (chosen) vs
   `needs-human` park.** The human overruled the original park:
   `needs-human` semantics are human judgment/input, not infra outage.
   The marker row keeps `in-review` honest — someone (the sweep) is
   actually coming back.
3. **Claude-reviewer-subagent fallback deleted (chosen) vs kept as last
   resort.** Reviewer is codex-only by mandate; a silent second engine
   changes what a verdict means. No engine → retry later, loudly.
4. **No in-thread runtime fallback for nested failures.** In-thread is
   exactly the context-efficiency regression this spec removes; failing
   loud routes to §3's retry instead of silently degrading the core.
5. **`danger-full-access` conditional on nesting (chosen) vs
   unconditional.** The flag's only justification (the second-Seatbelt
   wall) exists only when nested; non-nested it would genuinely widen the
   reviewer's sandbox on the host. The earlier "red flag" judgment
   (shakedown FU-7) was made when in-thread was already chosen and no
   longer applies to the nested case, where the outer profile confines.
6. **`codex exec review` (chosen) vs top-level `codex review`.** Only the
   former has `-m`/`-o`/`--json`.
7. **Worker-shell posture confirmed unchanged**: `--sandbox
   workspace-write` + `approval_policy=on-request` +
   `approvals_reviewer=auto_review` — the fix-writing worker needs
   commit/push/gh; this is the existing verified safety contract.

## Surprises & Discoveries

- **The clap wall had a config-shaped door.** Task 2 (codex-workers spec)
  correctly proved `--base` + positional `[PROMPT]` is a CLI
  impossibility, then over-generalized to "no working invocation at all".
  Custom criteria as a **config value** (`-c developer_instructions=`)
  were never tried; they work (rc=0, both findings, one call).
- **FU-7's "structurally dead" was three fixable env bugs**, not an OS
  impossibility: TLS anchors (file bundle), the second-Seatbelt rule
  (skip self-profiling via `danger-full-access`; outer profile still
  confines children), and the code-mode host misresolving to
  `/usr/local/bin/` (fixed by `CODEX_CODE_MODE_HOST_PATH`, an env var
  found by `strings ~/.local/bin/codex`).
- Both overturned conclusions shared the same failure shape: one
  invocation form fails → the whole family is declared impossible. The
  correction each time was to vary the *carrier* (config vs positional;
  env vs flags), not the goal.
- **Spike verdict — nested marker is `CODEX_SANDBOX=seatbelt` (Task 1,
  live, 2026-07-12).** A seatbelted `codex exec` (`--sandbox
  workspace-write`) was asked to run `env | sort | grep -iE
  'codex|sandbox'`; its children see exactly three codex vars:
  `CODEX_SANDBOX=seatbelt`, `CODEX_CI=1`, and
  `CODEX_THREAD_ID=<uuid>`. This confirms the §1 hypothesis verbatim, so
  the engine can detect nesting with a cheap, side-effect-free
  `[ -n "$CODEX_SANDBOX" ]` and needs **no** `sandbox-exec` probe
  fallback. (`CODEX_SANDBOX` also carries the mode name, `seatbelt` on
  macOS — a truthiness test is enough; the value isn't parsed.)
- **Spike verdict — raw multi-line `developer_instructions` survives,
  embedded `"` and all (Task 1, live, 2026-07-12).** `codex exec review
  --base base ... -c "developer_instructions=$(cat crit.md)"` with a
  three-line criteria file whose middle line contains a literal
  double-quote (`was "required" to ALSO add ... median(nums)`) returned
  **rc=0** with no TOML parse error, and the model acted on the injected
  criteria (flagged the missing `median` compliance gap). The raw
  (non-TOML-quoted) value reaches the model intact — the Step-5
  `json.dumps` escaping fallback is **not** needed. (One note: at
  `model_reasoning_effort="low"` this run reported only the compliance
  gap, not the `mean([])` div-by-zero; that is a model-effort artifact,
  not a carrier failure — immaterial to the quoting question this spike
  closes.)

- **Security hardening — criteria are not developer instructions.** The
  spike proved the carrier worked but also proved it would elevate PR- and
  ticket-controlled text. The final engine therefore passes only fixed
  review policy at developer privilege and points that policy to an external
  criteria file explicitly classified as untrusted data.

- **Finding recall is severity-of-signal-dependent, not effort-dependent.**
  Acceptance runs (gpt-5.6-sol, efforts low→high) always caught the planted
  compliance gap, but consistently declined to flag `mean([])`'s
  ZeroDivisionError — a defensible judgment for an uncalled 2-line function
  with no spec on empty input. Planting a DEFINITE bug (docstring promises
  `safe_ratio` returns 0 on zero denominator; code raises) was flagged
  immediately as [P2], alongside a correct out-of-scope finding on stray
  files. The correctness channel works; weak-signal planted bugs are the
  wrong acceptance probe. (Engine transport itself passed everywhere:
  rc=0, criteria reach the model, nested run clean — 0 sandbox_apply,
  0 host errors.)

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

1. **2026-07-12 (planning).** Planning's hostile read caught a
   contradiction the design sections had missed: the review-worker
   protocol's ORIENT step instructs a FULL diff read
   (`git diff origin/<base>...HEAD`) before the engine ever runs — which
   would put the whole PR diff back into the worker's context and void the
   acceptance clause "no full-diff dump into the worker's main context".
   Design §2 now includes the ORIENT rewrite (shape-only `--stat` read;
   the worker reads only the code each finding names).
2. **2026-07-12 (PR review).** Adversarial review caught that the original
   carrier elevated PR-controlled title and ticket text into developer
   instructions. The engine now keeps a fixed developer policy and reads
   all PR/ticket criteria from an explicitly untrusted data file.
3. **2026-07-12 (human feedback, post-live-shakedown-start).** The criteria
   template was over-prompted: it re-instructed things the native review
   already does (review the full `--base` range, review correctness
   rigorously, rate severity, cite file:lines) and carried checks smarter
   models make moot (PR-body-vs-diff claims; ignored acceptance criteria).
   Cut to the ONE thing the native review cannot know — the ticket's
   spec-compliance addendum, framed as decision discipline: did the
   implementer proceed only after surfacing every scope/product-taste fork
   that needed a human call, and where it assumed, was the assumption
   valid to make unasked. A ticketless PR now writes an EMPTY criteria
   file (verified live: empty `developer_instructions` passes the parser,
   rc=0, native review unaffected).
4. **2026-07-12 (reconciliation).** Notes 2 and 3 landed concurrently — the
   review worker hardened the carrier mid-shakedown while the human
   minimized the content — and merged as structure-from-2 +
   content-from-3: the fixed developer policy keeps the
   untrusted-data-file carrier but instructs ONLY the
   spec-compliance/decision-discipline addendum; the data file carries the
   ticket requirements alone (no PR-claims section — Note 3 dropped that
   check); a ticketless PR sends no developer instructions at all.
