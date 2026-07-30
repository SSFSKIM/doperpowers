# R1 — Runtime gap analysis & co-design (cc-harness) — 2026-07-30

**Round:** clean-slate R1–R4 (`round-brief.md` §R1). **Subject under test:**
cc-harness at `/Users/new/developer/github/codex_somersault/CC-to-SDK`
(`cc-harness@0.1.0`), Claude Agent SDK, Node v24.18.0, macOS Darwin 25.5.0.
**Class-A frame (binding, not re-argued here):** both tiers k8s+gVisor;
runtime = cc-harness co-designed with the environment; Postgres SSOT board;
the two governing principles (sidecar necessity ∝ 1/credential-substitutability;
decouple only across envelope asymmetry).

**Method and the credential limitation, stated up front.** The house rule is
live-probe-first: no "the SDK can/cannot X" claim is taken off `sdk.d.ts`.
Both credentials in this environment are exhausted (the subscription OAuth
token hit its weekly limit, resets 2026-08-03; the API key returns "Credit
balance is too low" — transcripts in `probes/p2-subagent-detached-session.md`
§1), so **no new model-turn probe could run in this session**. What this
report adds live is the keyless layer: runtime reads of the installed SDK
(not `.d.ts`), a drift-check run against npm HEAD, bundle-mechanism re-checks
against the version the harness actually ships, and source verification of
the limit classifier. Every claim below is tagged with its evidence class:
**[live this session]**, **[probe report]** (P1–P4, this round, files in
`probes/`), **[recorded live]** (CC-to-SDK's own probe/scorecard record —
Class C prose, re-verified only where cheap), or **[source read]**. §5
aggregates everything a credited or in-cluster environment must re-verify.

---

## 0. Headline

1. **The runtime substrate for a swarm worker exists and is largely proven**:
   headless engine, six permission modes, external Postgres sessionStore,
   resume/fork/rewind, warm spawn, OTel export, programmatic hooks, a
   detached fleet surface (`ccx --bg`), and a network-capable decisions-as-
   state control plane (`ccx serve`). The gaps are concentrated in exactly
   the places the brief predicted: **anything whose lifetime must exceed a
   process** (subagents, parks, background shells) and **anything that must
   be true across pods** (identity, discovery, config injection).
2. **The durability boundary is the turn, not the session** [probe report
   P2 §4]. An evicted pod loses its in-flight turn everywhere — local disk,
   Redis, or Postgres — because the engine emits transcript writes only at
   turn boundaries (probe 62, no mid-turn writes). This is the one
   structural ceiling no adapter fixes; it drives the SIGTERM-grace,
   small-turn, and park-mirroring designs below.
3. **A subagent is a subkey, not a session** [probe report P2]. Nothing can
   resume an `agentId`; the detached-worker shape (`ccx --bg`, own session
   id, own top-level transcript) already exists; the missing piece is a
   Task-shaped tool that spawns the latter — needs-build, four scoped
   tickets (§4 T1–T4).
4. **New live finding — version skew inside CC-to-SDK itself** [live this
   session]: the harness now installs and declares SDK **0.3.220**
   (`harness/package.json` `^0.3.220`; drift-check run today: "installed
   0.3.220 vs npm HEAD 0.3.220", zero name-level drift), while the probes
   and app-server packages still pin **^0.3.211** — the version every
   scorecard number was measured against. 0.3.220 declares **31 hook
   events** (adds `DirectoryAdded`) vs 0.3.211's 30 [live runtime read,
   both bundles]. The evidence base and the deployed engine have quietly
   diverged by one minor version; the fleet needs a single pinned version
   and the drift ritual as a gate (§4 T12).
5. **Fleet auth is settled by this round's own failure**: the probe phase
   was disabled by a *shared personal* OAuth weekly limit — a live
   demonstration that subscription auth is a fleet-wide single point of
   failure. API-key/gateway-virtual-key auth is the only fleet shape; the
   harness already has every hook it needs (`baseUrl` →
   `ANTHROPIC_BASE_URL`, `tenantHarnessConfig`, limit classification that
   catches the "success-with-error-text" failure mode) (§1E).

---

## 1. Gap table

Verdicts: **exists** (shipped and evidenced), **needs-build** (no blocker,
not built), **impossible** (structural — engine- or bridge-owned), with
**partial** where a capability is real but has a ceiling. Grouped by the
brief's six R1 questions.

### A. Native-CC parity gaps that matter for swarm workers

| Capability | Verdict | Evidence |
|---|---|---|
| Headless turn loop, 37 native tools, 6 permission modes (incl. `auto` classifier, `dontAsk`), settings cascade | **exists** | Scorecard domains 1–4, 9 (60–98%); full live suite 40/40 green on 0.3.211 [recorded live, `docs/parity/coverage.md` §7] |
| Structured outputs (`runStructured<T>`, Zod → validated `structured_output`) | **exists** | Probe 53 [recorded live] — workers can return machine-checkable verdicts to the board |
| Warm spawn (init 51 ms warm vs 602 ms cold; `createWarmPool`) | **exists** | Probes 40/50 [recorded live] — feeds R2's warm-pool-vs-claim-latency sizing |
| Custom engine placement (`spawnClaudeCodeProcess` seam) | **exists** | Probe 50 [recorded live]; P2 used it as the lifecycle-substitution seam [probe report] |
| External sessionStore — Postgres adapter, conformance, cross-host resume | **exists** | Shipped 2026-07-30 (`harness/src/store/postgresSessionStore.ts`, conformance green on PGlite, keyless) [recorded live]; Redis cross-host resume live-proven (W3.3) |
| Resume / fork / rewind / boot-rehydration / daemon durable sessions | **exists** | Domain 5 ~97% [recorded live]; C6 doperpowers acceptance 4/4 scenarios PASS (2026-07-29) |
| Detached fleet surface (`ccx --bg`, roster, `agents --json`, stop/rm/gc) | **exists** | Domain 11 ~90%; re-exercised live today — detached host survived spawner exit, own session id, keyless `agents` read [probe report P2 §3.2] |
| Model-initiated background shells (`run_in_background`) visible + stoppable | **exists** | Probe 39: `background_tasks_changed` streams headlessly; `stopTask` works [recorded live] |
| Backgrounding an already-running foreground shell (Ctrl+B semantics) | **impossible today** | Live acceptance 2026-07-28: op wired, SDK reports success, real CLI runs the call to completion anyway (`docs/parity/tui-ux.md` §8). Swarm impact: low — workers should launch long shells backgrounded, not convert them |
| Native scheduling/wake (`CronCreate`, `PushNotification`, `/goal`) | **impossible headless** | Bridge-coupled/DEAD (probes 46/46b/46c; scorecard domain 7). By design: the board + control plane own scheduling — this gap costs the architecture nothing |
| OTel **traces** | **impossible** | Probe 51: CLI emits metrics + log events only, no traces [recorded live]. E2/R3 correlation must join on `session.id`/`prompt.id` attributes instead |
| `usage().rate_limits` under fleet auth | **impossible under fleet credentials** | Probe 55: `null` under API key AND under `CLAUDE_CODE_OAUTH_TOKEN` (setup-token lacks `user:profile` scope); populates only under the interactive credential [recorded live]. Fleet quota telemetry must come from the gateway and `limitState`, not in-band |
| Subagent transcript drill-in (read-only) | **exists** | `listSubagents`/`getSubagentMessages` verified against 292 real transcripts, keyless [probe report P2 §2.1] |
| Inter-agent messaging in-process (SendMessage, Monitor) | **exists** | Probes 41/41b/47 [recorded live]; cross-pod equivalent is the appserver seam (§F) |
| Engine self-registration hygiene (`CLAUDE_JOB_DIR` scrub on spawn) | **exists (caveat)** | Probe 60 [recorded live]: inherited env absorbs the session into a parent agent's job row — pod spec must scrub |

**Swarm-relevant reading:** none of the *impossible* rows blocks the
architecture; each has a designed-around owner (board scheduling, gateway
metering, event-join instead of traces). The parity gaps that actually bite
are all in sections B–F below.

### B. Run-state externalization beyond the sessionStore

| State | Verdict | Evidence |
|---|---|---|
| Committed turns (transcript) in shared Postgres | **exists** | Postgres adapter, incl. `subpath` subagent keys + `listSubkeys` [source read + conformance, P2 §2.2] |
| **In-flight turn at pod death** | **impossible (engine-owned ceiling)** | No mid-turn transcript writes (probe 62); parent SIGKILL → engine stdin EOF → exit; clean exit → SDK SIGTERMs engine [probe report P2 §3.1, measured]. Mitigations only: SIGTERM grace ≥ turn close, small turns, idempotent re-run |
| Parked decisions (permission/question/plan) across restart | **needs-build** | Parks are un-settled Promises in process memory; `expireAfterMs:"never"` but zero disk presence [probe report P3 §f.5]. Mirror-to-board is the fix (§4 T5) |
| bg-process registry | **partial → needs-build** | `ccx` roster exists (live-is-asked / terminal-recorded, keyless reads) but is a node-local JSON dir with **no parent linkage** (`RosterRow` has no parent field) [probe report P2 §5 B2]. Externalize rows + parent edges to the board (§4 T2) |
| Subagent as revivable unit | **impossible as-is / needs-build as DetachedTask** | Subagent has no session id — a subkey `{projectKey, sessionId:<parent>, subpath:"subagents/agent-<id>"}`; `getSessionInfo(agentId)` → `undefined`; nothing resumes an `agentId` [probe report P2 §2, live keyless]. Detached path exists (`ccx --bg`); the join is T1–T4 |
| Subagent metadata (`agentType`, `description`, `toolUseId`) in the SSOT | **needs-verify (likely needs-build)** | `.meta.json` sidecar exists on disk; the live-mirror key mapper handles only `.jsonl` paths — sidecar likely never reaches the external store [probe report P2 §2.2, source read; probe 70 written, blocked on credentials] |
| Orphaned background shells after engine death | **impossible to recover output** | OS child survives SIGKILL of parent but its `tool_result` has no engine to land in [probe report P2 §4] |
| Engine/parent filesystem split (container topology) | **needs-build (assert or fix)** | Live mirror silently drops frames whose path is outside the parent's projects root — the exact container-split case; today a library `warn` [probe report P2 §2.2; warning string re-confirmed present in the 0.3.220 bundle, live this session] |

### C. The exec-decoupling boundary (envelope asymmetry applied)

The principle (Class A): decouple only across envelope asymmetry —
sessionStore/human-seam/browser yes; Read/Write/Edit never; exec conditional.
Applied to the tool inventory with this round's lifecycle evidence:

| Tool class | Envelope vs the session | Boundary decision | Status |
|---|---|---|---|
| Read/Write/Edit/Grep/Glob (hot loop) | Symmetric — sub-second, dies with the turn, needs the worktree filesystem | **Never decouple.** Same pod, same fs. Corroborated structurally: the transcript mirror itself assumes engine and SDK parent share a filesystem (B, last row) | exists (in-pod, native) |
| Foreground Bash | Symmetric in lifetime; asymmetric only in *blast radius* | Stays in-pod; isolation is srt-inside-gVisor (P4, R2's probe), **not** decoupling. Sidecar only where credential-substitutability fails (enterprise push-cred class — R2) | exists (in-pod) |
| Background Bash (`run_in_background`) | **Lifetime-asymmetric** — outlives the turn, today dies (orphaned) with the engine | Decouple *above a threshold*: short bg shells stay native (visible via `background_tasks_changed`, probe 39); anything meant to outlive the session becomes a detached spawn or a board ticket. Publish bg-task snapshots so an evicted pod's orphans are known (§4 T13) | partial |
| Task / subagent | **Lifetime- and failure-asymmetric** — the "6 shells + 5 subagents die with the session" case, now measured [P2 §3.1] | Decouple via `DetachedTask` (§4 T1): in-process `Task` stays for cheap short-lived fan-out; durable/child-goal work spawns a detached session with its own transcript | needs-build |
| Human seam / decisions | Asymmetric by definition (a park can outlive any client) | Decoupled already — appserver decisions-as-state, verified cross-connection + reconnect-replay over a real network interface [probe report P3 §d,e] | exists |
| Session transcript | Asymmetric (must outlive the pod) | Decoupled already — external sessionStore | exists |
| Browser / web tools | Asymmetric (own runtime, own egress class) | Out of R1 scope — R2 run-class egress; prior decision stands (A0 DL13) | — |

The ideadump's "every tool call a container" is therefore resolved
concretely: **two tool families decouple (Task above the durability
threshold, bg Bash above the lifetime threshold); everything else stays in
the pod**, with gVisor+srt as the blast-radius answer rather than
per-call containers.

### D. OTel / hook wiring for E2's derived ledger stream

E2 (Class A, `2026-07-30-ticket-ledger-observability-design.md`) needs a
read-only derived stream filling the silence between a worker's scope-end
writes. Three candidate carriers, with a finding that re-orders them:

**Finding: the sessionStore mirror alone cannot fill the silence.** The
mirror lands at turn boundaries only (probe 62 / P2 §4) — a long multi-tool
turn is exactly the silent stretch E2 wants to illuminate, and it is silent
*in Postgres too* until the turn closes. Real-time grain must come from
hooks and/or OTel, which both emit during the turn.

| Carrier | Grain / latency | Verdict | Evidence |
|---|---|---|---|
| sessionStore transcripts (Postgres) | Turn-boundary | **exists** — the archival layer, not the live layer | Probe 62 [recorded live]; adapter shipped |
| OTel export (CLI-emitted, env-gated) | ~1 s export intervals during the turn | **exists** | Probe 51 [recorded live]: metrics `claude_code.{session.count,cost.usage,token.usage,active_time.total}`; log events `user_prompt, api_request, assistant_response, tool_decision, tool_result, hook_registered`; attrs `session.id`, `prompt.id`, `user.*`, custom `resourceAttributes` (tenant/ticket stamping); **no traces**; `logUserPrompts` privacy-off by default (`docs/guides/observability-otel.md`) |
| Programmatic hooks (host-process, real-time) | Per-event, in-process | **exists** — 17 of 30 declared events verified-fired headlessly on 0.3.211 (probes 42/42b/43b) [recorded live] | The fired set below; `config.hooks` + `observe` builder shipped (domain 8) |

**Which hook events carry the ledger** (fired set per the Wave-2 sweep,
0.3.211; mapped to E2's timeline needs):

| E2 timeline need | Hook event(s) that carry it |
|---|---|
| Turn start | `UserPromptSubmit` |
| Tool activity (the between-decisions heartbeat) | `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch` |
| Parks / permission traffic | `PermissionRequest` — informational, fires on *allowed* calls too, carries `permission_suggestions` [recorded live, probe 42b]; authoritative park events additionally come from the appserver `decision/requested`/`decision/resolved` notifications [probe report P3 §d] |
| Task graph | `TaskCreated`, `TaskCompleted` |
| Subagent lifecycle | `SubagentStop` only — **`SubagentStart` was silent in the 0.3.211 sweep** (attribution instead via the host-side `parentToolUseID`→`subagentType` correlation map, shipped in GB 2026-07-28) |
| Compaction | `PreCompact`, `PostCompact` (+ `SessionStart` fires at the /compact boundary, not process start) |
| Turn end | `Stop` |
| Human-visible text / context | `MessageDisplay`, `InstructionsLoaded` |
| MCP elicitation | `Elicitation`, `ElicitationResult` |

**Events E2 must NOT depend on** (silent under driven scenarios, 0.3.211):
`SessionEnd` (session end must be derived from host lifecycle, not hooks),
`Notification`, `PermissionDenied` (never fires for callback/hook denials),
`FileChanged` (file activity must be read from `PostToolUse` Write/Edit
payloads), `CwdChanged`, `Worktree*`, `TeammateIdle`, `ConfigChange`,
`Setup`, `StopFailure`, `UserPromptExpansion`, `SubagentStart`.

**Correlation key:** `prompt.id` is stamped on both hook payloads and OTel
events [probe 51, recorded live] — hook-derived board events and OTel
telemetry join at prompt grain; `session.id` joins both to the transcript
and the ticket binding.

**Verdict for E2: sufficient, with hooks as the primary carrier.** The
recommended shape (§4 T11): a harness-side hook emitter (the existing
`observe` builder) writing structured events into the board's append-only
event table, with OTel as the ops-plane secondary (R3's intake) rather than
a ledger source — it keeps PII (`user.email`) and needs a collector hop.
One caveat: the sweep is 0.3.211 evidence; 0.3.220 adds `DirectoryAdded`
[live this session] and the fired set must be re-swept on the pinned fleet
version (§4 T12, §5).

### E. Fleet auth

| Item | Verdict | Evidence |
|---|---|---|
| OAuth subscription auth for fleet workers | **rejected — and live-demonstrated this round** | The probe phase itself was disabled by the *shared* weekly limit ("You've hit your weekly limit · resets Aug 3", P1/P2/P3 transcripts) [probe report, live]; 2026-07 org-side flip made every turn "succeed" with an error text (productized in `classify.ts` OBSERVED_ORG_POLICY) [source read]; `rate_limits` null under setup-token (probe 55). Subscription auth couples the whole fleet to one human's quota and one org toggle |
| API-key / gateway auth headless | **exists** | The entire keyed live suite runs under it [recorded live]. Failure surfaces as a *successful* result frame with error text ("Credit balance is too low", observed live this round) — which is why classification is text-first |
| Limit/billing classification | **exists** | `harness/src/limits/classify.ts` [source read, live this session]: SDK runtime prefix constants (`USAGE_LIMIT_ERROR_PREFIXES` — 12 prefixes confirmed by runtime read [live this session]) + observed org-policy and credit families; `Session.limitState` + daemon registry `limit` field (Wave 1) → the direct feed for the quota breaker (A0 Plan 2 lineage) |
| Gateway virtual keys per run-class | **exists (harness side)** / broker placement = R2 | `baseUrl` → `ANTHROPIC_BASE_URL` (`harness/src/config/provider.ts:14`) [source read]; `tenantHarnessConfig` keeps the real key out of tenant reach behind the proxy (W3.4, live deny proof) [recorded live]; `sandbox.credentials` deny-mode redaction verified (probe 48). Key issuance/rotation/metering is the platform's virtual-key broker — R2's question |
| In-band fleet quota telemetry | **impossible** (see §A rate_limits row) | Meter at the gateway; classify in-band failures via `limitState` |

**Co-design stance:** the harness needs *no new auth capability* — it needs
a **fleet auth preset** (§4 T10) so every pod is born with gateway `baseUrl`
+ virtual key + redaction + telemetry stamped, and `limitState` wired to the
board as a first-class event (the breaker's sensor).

### F. The appserver WS as the cross-pod seam

P3's verdict adopted in full [probe report P3, live over LAN + Tailscale
interfaces]: **viable seam today** — binds any interface; bearer token
in-band at `initialize`, fail-closed (no/wrong/bare/query token all
refused); `Origin` fail-closed 403; decisions-as-state proven
cross-connection; reconnect is replay-first (bounded 500-event per-turn
buffer, drop-oldest with fold-forward). The gap list, classified:

| Gap | Verdict | Owner |
|---|---|---|
| Per-identity authorization (one shared token = arbitrary code exec via `thread/start` config + full control of every thread; `by` attribution half caller-chosen) | **needs-build** — the blocker for multi-tenant use | Fork: in-harness principal on `ConnCtx` vs authorizing proxy (must parse JSON-RPC to scope per-`threadId`). §4 T8 |
| TLS (`listenWs` takes no server/cert; `--listen` rejects non-`ws:`) | **needs-build → infra** | Terminate at mesh/ingress (mTLS also part-solves identity). No harness change recommended |
| Discovery (`thread/list` = this process's memory; ClusterIP round-robin unusable) | **needs-build → board** | Postgres board owns `threadId → pod DNS → sessionId`; StatefulSet + headless Service for stable names. No harness change |
| Park durability across pod restart | **needs-build** (see §B) | §4 T5 — without it the ceiling is turn-level: resume as a new thread over the same `sessionId`, re-attempt the tool call |
| Heartbeat (no ping/pong; k8s LBs idle out silent parked sockets) + unauthenticated `/healthz` | **needs-build (small)** | §4 T7 |
| Process-side default config for `ccx serve` (`new AppServer({token})`, no deps; sessionStore/hooks can't cross the JSON wire — correctly) | **needs-build** — the single highest-leverage in-harness item | §4 T6 |
| M2 control surface over the wire (`thread/model/set`, `permissionMode/set`, `compact`, `usage`, `contextUsage`, `task/list`, `rewind`, `mcp*` — all `-32601` today, live-probed) | **needs-build (planned M2)** | Required by E3's web terminal; every underlying host op already exists (`docs/parity/appserver.md` rows) — this is wire plumbing, not capability. §4 T9 |
| Naming trap | — | `ccx attach` is a UDS, node-local by construction; cross-pod "attach" always means `thread/subscribe`+`thread/read` [probe report P3 §c] |

---

## 2. Pod-anatomy inputs handed to R2 (from P1)

For R2's sizing, not re-argued here [probe report P1]: production-only
install ~312 MB disk (245 MB of it the platform-specific native `claude`
binary; darwin-arm64 measured — linux variant must be re-measured);
harness wrapper ~100 MB RSS idle; engine subprocess 345→402 MB RSS in the
~2 s before the quota wall — **a floor, not a ceiling** (no completed turn
observed). Treat ≥1 GiB request per single-session worker pod as the
starting hypothesis and re-measure in-cluster with a real credential.

---

## 3. Through-question contribution (R1's structural half)

Nothing in the runtime evidence forces two architectures. The same harness
binary serves both tiers; every tier difference R1 touched is a *knob*, not
a *shape*: warm-pool size, auth (virtual-key class), sidecar presence
(credential-substitutability principle — enterprise push-cred class only),
park posture (auto-mode workers vs interactive-preferred lanes), and
telemetry stamping. The one candidate shape-difference — the execution
sidecar — is already expressed as a per-run-class option under k8s
multi-container pods (P4's fallback analysis), not a fork of the runtime.
R1 therefore weighs toward **one architecture, two knob-sets**; R4 owns the
economic half of the verdict.

---

## 4. Co-design proposals — the cc-harness backlog

Each scoped to become a ticket. Ordering = dependency, then leverage.

- **T1 — `DetachedTask` tool.** A Task-shaped MCP tool (`cc-fleet` server or
  in `cc-swarm`) with `Task`'s input (`{description, prompt, subagent_type}`)
  that spawns `ccx --bg` and returns `{short, sessionId}` immediately.
  Constraints from paid-for lessons: disallow native `Task`/`Agent` on
  sessions that carry it (the D3-shadowing lesson) and advertise it in the
  system prompt (the 33d unadvertised-capability lesson). Acceptance: a
  model autonomously dispatches a durable child; parent SIGKILL leaves the
  child running with its own resumable transcript. [P2 §5 B1]
- **T2 — Parent linkage in the roster + board.** Add `parentSessionId` +
  `parentToolUseId` to `RosterRow` (`harness/src/fleet/roster.ts:8-16` has
  no parent field today) and mirror the edge to the Postgres board. Makes
  the swarm tree queryable after any node dies. Cheap. [P2 §5 B2]
- **T3 — Collect/join for detached children.** A `TaskResult`-shaped tool /
  host op: poll-or-await over roster state + `getSessionMessages(child)` for
  final text; cross-pod variant rides the appserver seam. Without it the
  parent can dispatch but not integrate. [P2 §5 B3]
- **T4 — Mirror co-location assert.** Engine and SDK parent must share
  `CLAUDE_CONFIG_DIR`/filesystem or the live transcript mirror silently
  drops frames (a library `warn` today; warning string present in the
  0.3.220 bundle [live this session]). Assert at startup and fail loudly, or
  surface as a hard error + metric. [P2 §5 B4]
- **T5 — Park mirroring to the board.** On `decision/requested`, write the
  park (threadId, toolUseID, kind, input, suggestions) as a board event; on
  `decision/resolved`, close it. Converts park durability from
  process-memory to board-recoverable: after pod death the resumed thread
  re-raises, and the control plane can show/answer from history. Also the
  authoritative park feed for E2's timeline. [P3 §f.5; E2 spec]
- **T6 — `ccx serve --config` (process-side defaults).** Today
  `serveMain.ts` constructs `new AppServer({token})` with no deps; non-JSON
  knobs (sessionStore, hooks, permission posture) cannot cross the wire by
  construction — correctly. A pod must be able to pin "always Postgres
  store, always these hooks, always this posture" without a bespoke entry
  point. Highest-leverage single in-harness item for k8s. [P3 §f.6]
- **T7 — WS heartbeat + `/healthz`.** ws ping/pong sweep (~20 lines in
  `transport/ws.ts`) so parked-but-silent connections survive LB idle
  timeouts; a tokenless HTTP health endpoint so kubelet probes don't need
  the bearer token. [P3 §f.3, f.7]
- **T8 — Per-identity authorization.** Decide the fork: principal on
  `ConnCtx` (mTLS/SPIFFE or verified JWT) + thread-ownership checks
  in-harness, vs an authorizing proxy (which must parse JSON-RPC to scope
  per-threadId). Until then the appserver is a single-tenant pod API, and
  the shared token must be treated as root on the pod. [P3 §f.2]
- **T9 — Appserver M2 control surface.** Wire the already-existing host ops
  over the wire: `thread/model/set`, `thread/permissionMode/set`,
  `thread/thinking/set`, `thread/compact/start`, `thread/usage/read`,
  `thread/contextUsage/read`, `task/list`, `thread/rewind*`, `mcpServer/*`.
  Pure plumbing (every op exists in `host/ops.ts`); prerequisite for E3's
  web terminal. [P3 §c; `docs/parity/appserver.md`]
- **T10 — Fleet auth preset + limit events.** A `fleetHarnessConfig` preset:
  gateway `baseUrl` + virtual key env, `sandbox.credentials` deny defaults,
  OTel stamping (`tenant.id`/ticket id via `resourceAttributes`), OAuth env
  scrubbed; plus `limitState` transitions emitted as board events (the
  quota-breaker sensor). Builds on `tenantHarnessConfig`, `provider.ts`,
  `limits/classify.ts` — config composition, not new capability. [§1E]
- **T11 — E2 ledger emitter.** Hook-based (`observe` builder) structured
  event writer → board append-only event table, covering the §1D mapping
  (turn start/end, tool heartbeat, tasks, compaction, SubagentStop +
  host-side attribution map); `prompt.id` carried for OTel join. Explicitly
  read-only/derived — zero new worker duties (E2's acceptance #1). [§1D]
- **T12 — Fleet SDK pin + drift gate.** Pin one SDK version across
  harness/probes/app-server (today: 0.3.220 vs ^0.3.211 skew [live this
  session]); run `scripts/drift-check.mjs` in CI; re-run the hook sweep
  (probe 42) and the P2 mechanism probes on every pin bump. First backlog
  item on the new pin: settle `DirectoryAdded` and the
  `SubagentStart`-silent discrepancy. [§0.4]
- **T13 — bg-task snapshot publication.** Persist the latest
  `background_tasks_changed` snapshot (ids + descriptions) per session to
  roster/board so an evicted pod's orphaned shells are enumerable by the
  ops agent (R3 intake). Small; complements (not replaces) the T1 threshold
  rule for long-lived work. [§1C]

**Explicitly rejected:** promoting sidechain transcripts to sessions by
rewriting `sessionId`/`isSidechain` — a private-format transformation
against a CLI-internal union the vendor declines to specify; T1 achieves
the outcome without owning the format. Recorded as fallback only. [P2 §5]

## 5. What a credited or in-cluster environment must verify

Aggregated; nothing below is settled.

1. Probe 70 as written (subagent `append()` subpath shapes on the *live*
   mirror; `.meta.json` on the mirror path; `resume(agentId)` fails loudly
   not silently-fresh) — written, blocked on credentials [P2 §6].
2. A model-driven detached-child kill test: spawner SIGKILLed mid-turn,
   child finishes, child resumes from a third process; measure exactly what
   the killed parent's in-flight turn lost [P2 §6].
3. One real-model spawn→turn→park→respond over a pod-to-pod (non-loopback)
   connection with a fleet credential; NetworkPolicy + `[::]` dual-stack
   bind [P3 §a].
4. Re-run the 30/31-event hook sweep and probes 39/51/55 on the pinned SDK
   (0.3.220+): the fired-17 set, `DirectoryAdded`, `SubagentStart`,
   OTel catalog stability.
5. Linux (linux-x64 / arm64 / musl) native binary size + full-turn RSS under
   gVisor, and eviction-grace vs turn-close timing — the grace period is
   directly a data-loss knob [P1 §re-verify; P2 §6].
6. srt-inside-gVisor in-cluster (P4's four-step plan) — R2's probe, listed
   here only because T1's children inherit the same pod anatomy.

## Sources

- This round's probe reports (beside this file): `probes/p1-pod-footprint.md`,
  `probes/p2-subagent-detached-session.md`, `probes/p3-cross-pod-appserver.md`,
  `probes/p4-srt-inside-gvisor.md`.
- Live this session (keyless): runtime import of the installed SDK bundles —
  probes package 0.3.211 (30 `HOOK_EVENTS`) and harness package 0.3.220
  (31 `HOOK_EVENTS`, adds `DirectoryAdded`); `USAGE_LIMIT_ERROR_PREFIXES`
  (12) + `ORG_POLICY_LIMIT_PREFIXES` runtime-read; `scripts/drift-check.mjs`
  run ("installed 0.3.220 vs npm HEAD 0.3.220", no name-level drift, seam
  scorecard no drift); 0.3.220 bundle greps (exit-hook SIGTERM reap,
  `subagents/` subpath mapping, `CLAUDE_CONFIG_DIR` mirror-drop warning all
  present); `harness/package.json` `^0.3.220` vs `probes|app-server`
  `^0.3.211`.
- Source reads: `harness/src/limits/classify.ts`,
  `harness/src/config/{provider,tenantPreset,types}.ts`,
  `harness/src/fleet/roster.ts`.
- Class C scorecards (re-verified where cheap, cited elsewhere as recorded):
  `CC-to-SDK/docs/parity/coverage.md` (measured against 0.3.211),
  `docs/parity/full-potential.md` (hook sweep detail, probe 55 correction),
  `docs/parity/appserver.md` (M1/M2/M3 rows), `docs/parity/tui-ux.md` §8
  (Ctrl+B gap), `docs/guides/observability-otel.md` (probe-51 catalog).
- Class A: `round-brief.md`; specs `2026-07-30-ticket-ledger-observability-design.md`,
  `2026-07-30-control-plane-product-design.md`,
  `2026-07-30-implement-lane-split-design.md`;
  memory `cloud-scale-research-state.md` (pivot + governing principles).
- Class B priors: `research/2026-07-23-startup-scale/managed-agents-substrate.md`
  (what-a-runtime-provides comparison — its "nobody sells your-harness-on-
  our-runtime" verdict is the standing reason this runtime is co-designed
  rather than bought); A0 spec DL11–15 lineage (virtual keys, srt inner
  layer).
