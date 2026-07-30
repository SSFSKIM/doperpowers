# P2 — Subagent as a detached harness session

**Date:** 2026-07-30
**Round:** clean-slate R1–R4 (`../round-brief.md`), probe phase, feeding R1 (runtime gap analysis & co-design)
**Subject under test:** cc-harness (`/Users/new/developer/github/codex_somersault/CC-to-SDK`) on `@anthropic-ai/claude-agent-sdk@0.3.211`, bundled CLI `claude-agent-sdk-darwin-arm64/claude`, Node v24.18.0, macOS 25.5.0.

**Design question.** Can a subagent run as its *own* harness session — own session id, own transcript row in the sessionStore — so that it survives the parent session dying and can later be revived or resumed? This is the "6 shells + 5 subagents die with the session" failure case named in the round brief's R1 section.

---

## Headline

**Split verdict, and the split is the finding.**

| Sub-capability | Verdict |
|---|---|
| A native `Task`/`Agent` subagent as an independently addressable, resumable session | **Impossible as-is** — a subagent has no session id of its own. It is a *subfile* of its parent: on disk `…/<parentSessionId>/subagents/agent-<id>.jsonl`, in an external store `SessionKey{projectKey, sessionId: <parent>, subpath: "subagents/agent-<id>"}`. Its transcript lines carry the **parent's** `sessionId`. Nothing in the SDK resumes an `agentId`. |
| Subagent transcript *readable* after the fact (post-mortem, forensic, ledger) | **Exists** — `listSubagents()` + `getSubagentMessages()` work against the parent session id; verified live against 292 real subagent transcripts. |
| A detached process holding a *genuinely separate* session that outlives its spawner | **Exists** — `ccx --bg` (cc-harness fleet substrate). Verified live today: the spawning shell returned immediately, the detached host wrote a roster row carrying its **own** SDK session id, and that session has its own top-level transcript in the store. |
| An in-process session/subagent surviving its parent process | **Impossible** — measured both parent-death modes. Clean parent exit: the SDK's own `process.on("exit")` hook SIGTERMs every engine subprocess it spawned. Parent SIGKILL: the engine's stdin pipe hits EOF, and the real bundled `claude` binary in the SDK's exact argv shape exits `code 0` on stdin EOF. |
| **Routing a subagent into a detached session** (the actual ask) | **Needs-build** — every ingredient exists; nothing connects them. Four named build items in §5. |

The one-line summary for the reference architecture: **a subagent is a subkey, not a session; a detached worker is a session; the missing piece is a Task-shaped tool that spawns the latter instead of the former.**

---

## 1. Method and the credential blocker (read this before trusting any number below)

The house rule is live-probe-first: no "the SDK can/cannot X" claim is taken off `sdk.d.ts`. Two new probes were written for this question:

- `probes/probes/70-subagent-session-addressability.ts` — a real turn that launches a `general-purpose` subagent with a recording `sessionStore` attached, then interrogates `listSubagents` / `getSubagentMessages` / `listSessions` / `getSessionInfo` / `resume(agentId)` and dumps the store's `append()` key shapes.
- `probes/probes/71-detached-session-survival.ts` (+ `71-parent-lifecycle.ts`, `71-worker-child.mjs`) — process-lifecycle probe.

**Probe 70 could not complete: both credentials in this environment are exhausted.**

```
$ set -a; . ../.env; set +a; ./node_modules/.bin/tsx probes/70-subagent-session-addressability.ts
=== PROBE 70 subagent session addressability ===
…
Error: Claude Code returned an error result: You've hit your weekly limit · resets Aug 3 at 12am (Asia/Seoul)

$ ANTHROPIC_API_KEY=<from .env> ./node_modules/.bin/tsx probes/00-health-check.ts
subtype: success | text: Credit balance is too low
HEALTH ❌ — auth/billing problem, fix .env before probing
```

The subscription OAuth token is rate-limited until **2026-08-03**; the API key has no credit balance. Rather than fabricate or defer, the question was re-cut into evidence that needs **no model turn**, and the residue is listed explicitly in §6 as *must-verify-when-credited*. Everything reported below as measured was measured in this session; everything read out of the shipped bundle is labelled as a source read.

Three keyless evidence lines were used:

1. **Real on-disk subagent transcripts** from prior Claude Code sessions (1,009 project dirs in `~/.claude/projects`), driven through the SDK's own read API — `probes/probes/70b-subagent-addressability-keyless.ts` (new).
2. **Process lifecycle under substitution** — the SDK's documented `spawnClaudeCodeProcess` seam (already proven end-to-end by probe 50) lets a stand-in child stand where the `claude` engine would, under the SDK's real lifecycle management, with no credentials. Plus one case exercising the **real** bundled binary's stdin coupling without ever submitting a turn.
3. **Shipped-bundle source reads** of `sdk.mjs`, used only for mechanism (key derivation, exit hooks), each one corroborated by a measurement where a measurement was possible.

---

## 2. Question (a) — does a Task subagent leave an independently addressable transcript?

### 2.1 Live result (keyless, real data)

```
$ ./node_modules/.bin/tsx probes/70b-subagent-addressability-keyless.ts
=== PROBE 70b subagent addressability (keyless, real on-disk sessions) ===
storage dir : /Users/new/.claude/projects/-Users-new-Developer-GitHub-manim-master
project dir (SDK `dir` arg) : /Users/new/Developer/GitHub/manim-master
session     : e851af63-2aa8-4015-ba4c-69fe146a028b

(0) layout: <project>/e851af63-….jsonl  +  <project>/e851af63-…/subagents/ (292 agent transcripts, 584 files)
(1) listSubagents("e851af63-…") -> 292 ids; sample: ["a00255bcac32b31e4","a007a5bb15c282906","a013ca6ad088d8104"]
(2) getSubagentMessages("e851af63-…", "a00255bcac32b31e4") -> 31 messages
    first msg session_id: e851af63-2aa8-4015-ba4c-69fe146a028b | parent_agent_id: null
    subagent messages report session_id === PARENT session id: true
(3) listSessions({dir}) -> 477 rows; any row whose sessionId is a subagent id: false
    rows flagged isSidechain: 0
(4) getSessionInfo("a00255bcac32b31e4") -> undefined
    getSessionMessages("a00255bcac32b31e4") -> 0 messages
(4) getSessionInfo("agent-a00255bcac32b31e4") -> undefined
    getSessionMessages("agent-a00255bcac32b31e4") -> 0 messages
(5) raw agent-a00255bcac32b31e4.jsonl:
    distinct sessionId values : ["e851af63-2aa8-4015-ba4c-69fe146a028b"]
    distinct agentId values   : ["a00255bcac32b31e4"]
    isSidechain values        : [true]
    agent-….meta.json: {"agentType":"general-purpose","description":"Judge eval 28 (matrix display)",
                        "toolUseId":"toolu_0197fYL6xzjzxcVHSpTbCEt1","spawnDepth":1}
(6) parent transcript: 15465 lines (43004905b), of which isSidechain: 0
```

Read this carefully — six separate facts fall out:

1. **The subagent transcript is real and durable.** 292 of them for one session, each a full JSONL conversation, each with a `.meta.json` sidecar recording `agentType`, the human-readable `description`, the originating `toolUseId`, and `spawnDepth`. That sidecar is a ready-made ledger record.
2. **The subagent has no identity of its own.** Every line inside `agent-a00255….jsonl` carries `sessionId: <parent>`; the only distinguishing field is `agentId`, and `isSidechain: true`.
3. **It is not a session.** 477 session rows in that project; not one of them is a subagent id, and not one row is flagged `isSidechain`. `getSessionInfo(agentId)` → `undefined`; `getSessionMessages(agentId)` → 0 messages. The SDK's own doc comment for `getSessionInfo` says it returns `undefined` when the target "is a sidechain session" (`sdk.d.ts:692`) — measured behaviour matches.
4. **Therefore it cannot be resumed.** `resume` takes a session id; the subagent never gets one. There is no id to pass. This is not a missing feature to probe around — it is an identity that does not exist.
5. **The subagent's work is NOT in the parent transcript.** 15,465 parent lines, zero `isSidechain`. The parent holds the `Task` `tool_use` and the final `tool_result` summary; the subagent's own turns live *only* in the sidechain file. Deleting or truncating the sidechain directory silently destroys the detail while the parent still looks complete.
6. **`dir` means project path, not storage path.** A first run passing `~/.claude/projects/<encoded>` returned `listSubagents → 0`, `listSessions → 0` — **silently empty, no throw**. The correct argument is the session's `cwd`. Any ledger/observability consumer that gets this wrong sees an empty world and no error. (Recorded because E2's derived ledger stream will call exactly these functions.)

### 2.2 How it is addressed in an external sessionStore (source read + adapter check)

The live-mirror path derives the store key from the transcript file path. From the shipped bundle (`node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs`, function `i1`):

```js
function i1(e,t){ let r=c1(t,e), o=r.split(ck);
  if(o[0]===".."||l1(r)) return null;
  if(o.length<2) return null;
  let n=o[0], i=o[1];
  if(o.length===2 && i.endsWith(".jsonl")) return {projectKey:n, sessionId:i.replace(/\.jsonl$/,"")};
  if(o.length>=4){ let s=o.slice(2), a=s.length-1;
    s[a]=s.at(-1).replace(/\.jsonl$/,"");
    return {projectKey:n, sessionId:i, subpath:s.join("/")}; }
  return null; }
```

So `<projectKey>/<sessionId>.jsonl` → `{projectKey, sessionId}`, and `<projectKey>/<sessionId>/subagents/agent-x.jsonl` → `{projectKey, sessionId, subpath:"subagents/agent-x"}`. Reading back matches: `listSubagents` against a store calls `listSubkeys({projectKey, sessionId})`, keeps only keys starting `subagents/`, and strips the `agent-` prefix — and it **throws** if the adapter has no `listSubkeys` ("sessionStore.listSubkeys is not implemented -- cannot list subagents").

Our shipped Postgres adapter already handles this: `harness/src/store/postgresSessionStore.ts` normalises `subpath` to `''` for the main transcript (deliberately, because Postgres `UNIQUE` treats NULLs as distinct and dedup would silently break), carries `subpath` in the unique index and in `load`, cascades subpath deletion from the main key, and implements `listSubkeys` (line 217). The conformance suite covers key isolation across `subpath` and the `listSubkeys` round-trip (`harness/src/store/conformance.ts:47,80`).

**Consequence for the Postgres-SSOT board:** subagent transcripts land in the same `*_entries` table as a third key column, under the *parent's* `session_id`. They are queryable — `WHERE subpath LIKE 'subagents/%'` — but they are not rows in any session index, they have no summary sidecar (the adapter deliberately skips the sidecar for subpaths, `postgresSessionStore.ts:181`), and nothing can resume them.

**Two hazards found in the same code path, both worth carrying into R1/R2:**

- The mirror mapper returns `null` — dropping the frame with only a `warn` — when the emitted file path is not under the *parent process's* projects root. The bundle's own message names the case: `"subprocess CLAUDE_CONFIG_DIR likely differs from parent -- custom spawnClaudeCodeProcess / container?"`. In a k8s design where the engine may not share a filesystem with the SDK parent, **transcript mirroring degrades silently to data loss**. This is a source read; it needs a live probe on the target pod topology.
- `.meta.json` sidecars are read by `importSessionToStore` but there is no evidence they ride the live mirror path (`i1` only handles `.jsonl`; a `.meta.json` path yields `null`). If the ledger wants `agentType`/`description`/`toolUseId`, the live-mirror route may not carry it. Flagged for the credited re-run.

---

## 3. Question (b) — can a parent spawn a separate session that survives the parent dying?

### 3.1 What dies with the parent process (measured, keyless)

`probes/probes/71-detached-session-survival.ts` puts two children under one parent: (A) an SDK-owned engine subprocess, substituted through the SDK's `spawnClaudeCodeProcess` seam so it is under the SDK's genuine lifecycle management, and (B) a `detached:true` + `unref()` sibling — the shape `ccx --bg` uses.

```
=== PROBE 71 what survives the harness process? (keyless) ===

########## parent death mode: EXIT ##########
pids: parent=51341 sdk-engine-child=51344 detached-sibling=51343
parent exited cleanly (process.exit(0))
AFTER parent death (exit):
  SDK engine child  : alive=false  events=["start","SIGTERM"]
  detached sibling  : alive=true   events=["start","stdin-end"]  heartbeat advancing=true

########## parent death mode: KILL ##########
pids: parent=51475 sdk-engine-child=51483 detached-sibling=51482
parent SIGKILLed
AFTER parent death (kill):
  SDK engine child  : alive=true   events=["start","stdin-end","stdin-close"]
  detached sibling  : alive=true   events=["start","stdin-end"]  heartbeat advancing=true

########## case C: real bundled `claude` CLI, stdin coupling ##########
bundled binary: …/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude
  spawned pid=51575; alive after 3s: true
  after stdin EOF: exited=true {"code":0,"sig":null}
```

Three measured conclusions:

1. **Clean parent exit kills the engine deliberately.** The engine child received **SIGTERM**. The mechanism is in the shipped bundle: every spawned process is registered by `YK(e){ xc.add(e); if(!IR){IR=!0; process.on("exit",XK)} }` and the hook is `XK(){ for(let e of xc) if(!e.killed) … e.kill("SIGTERM") }`. This is not incidental coupling — the SDK actively reaps its engine children at parent exit.
2. **Parent SIGKILL kills the engine indirectly.** The exit hook cannot run, and the stand-in child was still alive — but it recorded `stdin-end` and `stdin-close`: the pipe the SDK held went away. Case C settles what the *real* engine does with that: the actual bundled `claude` binary, launched with the SDK's own argv (`--output-format stream-json --verbose --input-format stream-json`), **exits `code 0` on stdin EOF**. So the real engine dies in both modes; only the substitute survived, and only because it was written to.
3. **A detached sibling survives both modes**, with its heartbeat still advancing after the parent is gone.

So the brief's failure case is confirmed at the mechanism level: an in-process subagent, an in-process swarm teammate (`harness/src/swarm/teammate.ts` — each teammate is a peer `query()` inside the same OS process), and every background shell owned by that engine go away with the parent. There is no configuration that changes this; it is the SDK's process model.

### 3.2 What a detached harness session actually is (measured, live)

`ccx --bg` was exercised end to end in a throwaway git repo. The turn itself failed on the weekly rate limit — irrelevant, because the object under test is the *session*, not the answer:

```
$ node harness/dist/cli/bin.js --bg "Reply with exactly: OK"
backgrounded · d968b66e
--- spawner shell returned ---

$ cat ~/.claude/ccx/roster/d968b66e.json
{"short":"d968b66e","pid":51952,"cwd":"/private/tmp/ccxbg.t3vD","kind":"bg","name":"d968b66e",
 "state":"done","startedAt":1785402922323,"procStart":"Thu Jul 30 09:15:22 2026",
 "sessionId":"e3dd0494-140a-4710-85b7-c19225e8ef91","endedAt":1785402924202}

$ node harness/dist/cli/bin.js agents --json --all      # keyless, works with no credentials
… {"id":"d968b66e","cwd":"/private/tmp/ccxbg.t3vD","name":"d968b66e",
   "sessionId":"e3dd0494-140a-4710-85b7-c19225e8ef91","state":"done","status":"idle"} …

$ ls ~/.claude/projects/-private-tmp-ccxbg-t3vD/e3dd0494-….jsonl   # 11 lines
  queue-operation · attachment · user("Reply with exactly: OK") · file-history-snapshot · assistant(…)
```

That is exactly the shape the design wants: a worker started by a parent that immediately returned, holding **its own top-level session id**, **its own transcript** (a first-class `{projectKey, sessionId}` key, not a subpath), and a roster row addressable by an 8-hex short id.

The revive/resume half is already recorded as live-verified in the harness's own evidence base and was **not** re-run here (it needs credits): cross-process resume by id (probe 16, `docs/parity/coverage.md` domain 5), fork-copies-forward so purging a superseded parent is safe (probe 59), cross-host resume through an external store (W3.3), and the four-scenario doperpowers acceptance run of spawn → resume → reply → finalize → retire (C6, 2026-07-29, `.doperpowers/sdd/c6-scenario-*-report.md`). Those are Class-C prose citations, not measurements from this session.

---

## 4. Question (c) — what state is structurally unrecoverable

| State | Recoverable? | Evidence |
|---|---|---|
| The user prompt of an interrupted turn | Yes — written before the turn runs | The rate-limited `ccx --bg` transcript above contains the `user` line despite the turn failing |
| A completed turn's messages | Yes | Standard transcript persistence |
| **The in-flight turn at the moment of death** (assistant text, pending `tool_use`, tool results already returned) | **No** | Probe 62 established there are **no mid-turn transcript writes** for ordinary tool calls (recorded prior result, cited in `probes/probes/69-transcript-at-park.ts` header). A killed session loses the entire turn in progress, not just its tail |
| **A parked permission / question / plan decision** | **No** | The park lives in the host process's in-memory decision registry (`canUseTool` broker, `PendingPermissions`). Nothing on disk holds it; the parked tool call is part of an uncommitted turn |
| **Background shells owned by a dying engine** | Process may survive, output cannot land | Probe 71 shows an OS child is not signalled when its parent is SIGKILLed — the shell keeps running orphaned, but the `tool_result` has nowhere to return and the engine that would record it has exited |
| **In-process swarm teammates / native subagents** | **No** | §3.1: SIGTERM on clean exit, stdin EOF on SIGKILL. Their sidechain transcripts persist only as far as the last completed subagent turn |
| The pid-keyed `~/.claude/sessions/<pid>.json` engine registry row | No | The engine writes it at session start (probe 56, live-verified) and unlinks it on exit — the reason cc-harness keeps its own `procStart` copy, documented at `harness/src/fleet/roster.ts:11-15`. The roster is the durable layer, and it records only a TERMINAL state (`docs/parity/coverage.md` domain 11) |
| A subagent's identity as a resumable unit | **Never existed** | §2 |

The pattern: **the durability boundary is the turn, not the session.** Anything that has not closed a turn is gone. This is the single most load-bearing fact for the reference architecture's crash/eviction story — a pod evicted mid-turn loses that turn everywhere, whether the transcript lives on local disk, in Redis, or in Postgres, because the engine only emits at turn boundaries.

---

## 5. Classification and the cc-harness backlog

**Capability: subagent-as-detached-harness-session → NEEDS-BUILD.** Not impossible, and not close to free: the two halves exist and nothing joins them. Four named items, in dependency order.

**B1 — `DetachedTask` tool (a Task-shaped MCP tool that spawns `ccx --bg`).**
A tool in the `cc-swarm` server (or a new `cc-fleet` server) whose input mirrors `Task` — `{description, prompt, subagent_type}` — but whose implementation spawns a detached host and returns `{short, sessionId}` immediately instead of running an in-process subagent. **The native `Task`/`Agent` tools must be disallowed on any session that carries it**: coverage records the D3-shadowing lesson (SDK 2.1.211 made the model prefer native `TaskCreate` over the deferred MCP equivalent and it wrote to the wrong store) and the 33d lesson (an unadvertised capability is inert — the tool needs an explicit note in the system prompt or the model will not reach for it). Both are stated as already-paid-for mistakes in `docs/parity/coverage.md`.

**B2 — parent↔child linkage in the roster (and in the board).**
The roster row measured above is `{short, pid, cwd, kind, name, state, startedAt, procStart, sessionId, endedAt}`, and the `RosterRow` interface itself (`harness/src/fleet/roster.ts:8-16`) has no parent field either — **the record has nowhere to put a parent**. A detached child is therefore an orphan the instant it is created: after the parent dies, nothing reconstructs which goal it belonged to. Add `parentSessionId` and `parentToolUseId` to the roster record and mirror the edge into the Postgres SSOT (a `session_parent` relation or a board-ticket column). This is what makes the swarm tree queryable after any node dies, and it is cheap.

**B3 — a collect/join path for the parent.**
`DetachedTask` returns a handle, so the parent needs a way to await or poll it: a `TaskResult`-shaped tool over the existing roster state plus `getSessionMessages(childSessionId)` for the final assistant text, or a host op. Without this the parent can dispatch but cannot integrate. Note the natural fit with the appserver WS seam named in the brief's R1 question list — a cross-pod parent and child cannot share a UDS.

**B4 — engine/parent filesystem co-location check for the mirror path (or a fix).**
§2.2: the live mirror silently drops frames whose file path is not under the parent's projects root, which is precisely the container-split case. Either pin the engine and the SDK parent to a shared `CLAUDE_CONFIG_DIR` in the pod spec and assert it at startup, or surface the dropped-frame warning as a hard error. Today it is a `warn` in a library nobody reads.

**Explicitly NOT recommended (a fifth option, considered and rejected):** promoting a sidechain transcript to a session — rewriting `sessionId`, clearing `isSidechain`, materialising it as a top-level file so a finished subagent's context can be resumed. It is mechanically plausible (fork already rewrites every UUID and copies forward — probe 59) but it is a private-format transformation against a CLI-internal union that the SDK's own docs decline to specify (`SessionStoreEntry` is "CLI-internal and not part of the SDK API surface"). B1 gets the same outcome without owning a format the vendor can change. Record it as the fallback if B1 is ever blocked.

---

## 6. What a credited environment (or a cluster) must verify

None of the following was measurable here; do not treat any of it as settled.

1. **Probe 70 as written** (`probes/probes/70-subagent-session-addressability.ts`, uncommitted, ready to run): does the *live* mirror path actually emit `append()` calls with `subpath: "subagents/agent-…"` during a real subagent turn? §2.2 derives this from the shipped `i1` mapper; it has never been observed. The probe already prints the store's key shapes.
2. **Does `.meta.json` ride the live mirror?** If not, `agentType`/`description`/`toolUseId` — the fields E2's ledger would most want — exist only on local disk and never reach the SSOT.
3. **`resume(agentId)` failure mode.** Predicted: no such session. Worth one run to confirm it fails *loudly* rather than silently starting a fresh session (a silent fresh start would be a nasty trap for B1's error handling).
4. **A model-driven variant of probe 71**: a detached child that runs a real multi-step turn while its spawner is SIGKILLed mid-turn, proving (i) the child finishes, (ii) the child's session resumes afterwards from a third process, and (iii) exactly how much of the killed parent's in-flight turn is missing from disk. The keyless probe proves the process semantics; only this proves the *session* semantics end to end.
5. **In a cluster:** whether the engine subprocess and the SDK parent share a filesystem, and what the mirror does when they do not (item B4). Also whether an evicted pod's SIGTERM grace period is long enough for the engine to close its current turn — §4 says everything not committed at a turn boundary is lost, so grace-period length is directly a data-loss knob.
6. **Re-run everything above against whatever SDK version the cluster pins.** All of §2.2 and §3.1 are reads of `0.3.211`'s bundle; the exit hook and the key mapper are internal and unversioned.

---

## Artifacts produced

New probe files in `/Users/new/developer/github/codex_somersault/CC-to-SDK/probes/probes/` (written this session, **uncommitted** — the CC-to-SDK repo was not touched by git):

| File | Status |
|---|---|
| `70-subagent-session-addressability.ts` | written, **blocked on credentials** — run when the limit resets |
| `70b-subagent-addressability-keyless.ts` | **run, passing** — the §2.1 transcript |
| `71-detached-session-survival.ts` | **run, passing** — the §3.1 transcript |
| `71-parent-lifecycle.ts` | helper for 71 |
| `71-worker-child.mjs` | helper for 71 |

Live artifact left behind: roster row `d968b66e` under `~/.claude/ccx/roster/` and its session transcript under `~/.claude/projects/-private-tmp-ccxbg-t3vD/` (scratch cwd `/private/tmp/ccxbg.t3vD`).
