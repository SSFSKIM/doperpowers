# Probe P3 — cross-pod appserver reachability (2026-07-30)

Question: the round brief nominates the cc-harness appserver (`ccx serve` —
a WebSocket JSON-RPC control plane built on *decisions-as-state*) as the
cross-pod agent↔agent and control-plane seam. Does it actually work across
a network boundary, what authenticates it, what is on the wire, and what
must be built on top for a Kubernetes deployment?

Environment: macOS (Darwin 25.5.0, arm64), Node v24.18.0. Code under test:
`/Users/new/developer/github/codex_somersault/CC-to-SDK/harness` at
`cc-harness@0.1.0`, rebuilt from source (`npm run build`) immediately
before probing. Credentials were sourced from
`/Users/new/developer/github/codex_somersault/CC-to-SDK/.env` into process
environments and never printed, echoed, or logged; only variable *names*
were inspected. Machine addresses used: LAN `192.168.35.41`, Tailscale
`100.92.238.1`, loopback `127.0.0.1`.

**Top-line answer:** the appserver is a genuine network service today —
it binds any interface, requires a shared bearer token at `initialize`,
fails closed on a browser `Origin`, and its decisions-as-state park
survives a hard client disconnect and can be answered by a *different*
connection. All four properties were verified live over the machine's LAN
IP from separate client processes. What it is **not** yet is a
multi-tenant control plane: one server-wide secret grants full control of
every thread, there is no TLS, no heartbeat, no service/DNS discovery, and
no server-side persistence of threads or parks across a process restart.
Those four are the k8s build list.

---

## Summary table

| Capability | Verdict | Evidence |
|---|---|---|
| Bind non-loopback (`0.0.0.0`) and reach over a real interface | **exists** | §a |
| Refuse non-loopback bind without an operator-pinned token | **exists** | §a T1 |
| Bearer-token auth at `initialize`, fail-closed | **exists** | §b |
| `Origin`-header allowlist, fail-closed by default | **exists** | §b |
| Park / respond / attach (`decision/*`, `thread/subscribe`) | **exists** | §c, §d |
| Cross-connection respond (any authed client answers any park) | **exists** | §d |
| Reconnect replay after hard disconnect | **exists** | §e |
| TLS / `wss://` | **needs-build** (terminate externally) | §f.1 |
| Per-identity / per-thread authorization | **needs-build** | §f.2 |
| Trustworthy actor attribution on `decision/respond` | **needs-build** | §f.2 |
| Application-level heartbeat / idle keepalive | **needs-build** | §f.3 |
| Service discovery (which pod holds thread X) | **needs-build** (out of process) | §f.4 |
| Thread/park survival across server process restart | **needs-build** — partial ceiling | §f.5 |
| Adopting a thread that lives in *another* process (`thread/attach`) | **needs-build** (spec'd as M3) | §c |
| Injecting non-JSON config (sessionStore, hooks) from a remote client | **impossible over this wire** by construction | §f.6 |

---

## (a) Bind address and network reachability

The bind host is a CLI flag with a loopback default, and there is a
pre-bind refusal for the dangerous combination.

`harness/src/cli/args.ts` parses `--listen` as a `ws://` URL and defaults
to `{ host: "127.0.0.1", port: 0 }`.
`harness/src/appserver/transport/ws.ts` defaults `host` to `"127.0.0.1"`
and `port` to `0` (ephemeral) independently. `nonLocalWithoutToken()`
(same file as the parser) and its call site in `harness/src/cli/main.ts`
refuse a non-loopback bind that has no `--token-file`.

**T1 — non-loopback bind, no token file (refusal):**

```
$ CCX_FLEET_ROOT=$SD/fleet node dist/cli/bin.js serve --listen ws://0.0.0.0:9711
ccx: --listen to a non-localhost host requires --token-file (spec §11)
exit=1
```

**T2 — non-loopback bind with a pinned token file (accepted):**

```
$ printf 'p3probetoken0123456789abcdef0123' > $SD/appserver.token; chmod 600 …
$ CCX_FLEET_ROOT=$SD/fleet node dist/cli/bin.js serve \
    --listen ws://0.0.0.0:9711 --token-file $SD/appserver.token
appserver listening ws://0.0.0.0:9711

$ lsof -nP -iTCP:9711 -sTCP:LISTEN
COMMAND   PID USER   FD   TYPE  DEVICE  NODE NAME
node    38987  new   12u  IPv4  …       TCP *:9711 (LISTEN)
```

`*:9711` — bound on every IPv4 interface, not loopback. A separate client
process then completed the JSON-RPC handshake over three different
interface addresses:

```
ws://192.168.35.41:9712 -> {"id":1,"result":{"userAgent":"cc-harness-appserver","version":"0.1.0","platformOs":"darwin"}}
ws://100.92.238.1:9712  -> {"id":1,"result":{"userAgent":"cc-harness-appserver","version":"0.1.0","platformOs":"darwin"}}
ws://127.0.0.1:9712     -> {"id":1,"result":{"userAgent":"cc-harness-appserver","version":"0.1.0","platformOs":"darwin"}}
```

**Control — the loopback default really is closed.** A second server bound
`ws://127.0.0.1:9713` and the same client refused on the LAN IP:

```
$ lsof -nP -iTCP:9713 -sTCP:LISTEN
node  69789  new  12u  IPv4  …  TCP 127.0.0.1:9713 (LISTEN)
LAN-IP -> REFUSED: connect ECONNREFUSED 192.168.35.41:9713
```

**Caveat to record honestly:** every client in this probe ran on the same
physical machine as the server, reaching it through the LAN and Tailscale
interface addresses rather than through loopback. That proves the socket
is not loopback-bound and that the full TCP/WebSocket path over a routable
address works. It does **not** prove reachability from a *foreign* host —
no second machine was available. A cluster environment must additionally
verify: pod-to-pod reachability with a `NetworkPolicy` in effect, and that
the service's `containerPort`/`targetPort` mapping reaches the bound port.

**Dual-stack note:** the listener above is `IPv4` only (`0.0.0.0`). A
dual-stack cluster needs `--listen ws://[::]:PORT`; `args.ts` strips IPv6
brackets before binding, so the flag form is supported, but the `::`
listener was not probed here.

## (b) Authentication as it exists today

Auth is a **single shared bearer token, checked once at `initialize`**.
`harness/src/appserver/server.ts` turns auth on by the *presence* of the
`token` option (not its truthiness — an empty configured token fails every
client closed, a deliberate fix recorded in the source as "C2"), and
`handleInitialize` compares `params.authorization` to
`"Bearer " + token`. `ccx serve` always passes a token: `serveMain.ts`
`loadOrMintToken()` reuses `--token-file` verbatim, or mints 16 random
bytes (32 hex chars) and writes it `0o600`; an existing but *empty* token
file is fatal rather than silently re-minted.

Live results, all from a separate client process over
`ws://192.168.35.41:9711`:

```
no-auth-initialize        :: {"error":{"code":-33003,"message":"Invalid token"}}
no-auth-then-thread-list  :: {"error":{"code":-33003,"message":"Not authenticated"}}
wrong-token-initialize    :: {"error":{"code":-33003,"message":"Invalid token"}}
bare-token-initialize     :: {"error":{"code":-33003,"message":"Invalid token"}}   # token without the "Bearer " prefix
good-token-initialize     :: {"result":{"userAgent":"cc-harness-appserver","version":"0.1.0","platformOs":"darwin"}}
query-token-initialize    :: {"error":{"code":-33003,"message":"Invalid token"}}   # ws://…?token=… is NOT read
origin-present-upgrade    :: "REFUSED: HTTP 403 Forbidden"                          # Origin: https://evil.example
```

Three things worth carrying forward:

1. **The token never crosses the URL.** `transport/ws.ts` deliberately
   does not read a query parameter; only the in-band `initialize` frame
   carries it. That keeps the secret out of proxy access logs — relevant
   because a k8s ingress *will* log request lines.
2. **`Origin` fails closed.** An *absent* `Origin` (any non-browser
   client) is always allowed; a *present* one is refused with a real
   HTTP 403 at upgrade unless listed via `--allow-origin`. Browsers do not
   apply CORS preflight to WebSocket upgrades, so this is the only defence
   against a page in an operator's browser dialling the control plane.
3. **The run-file leaks nothing.** `~/.claude/ccx/run/appserver.json`
   (`{"port":…,"tokenFile":…}`) records the *path*, and the token file
   itself is `0o600`; both were verified `-rw-------` on disk.

## (c) The JSON-RPC surface, probed rather than read

Every method name below was **called** on a live authenticated connection.
`-32601 Unknown method` means genuinely absent; `-32602 Invalid params`
means present and reachable (the probe sent `{}`).

| Method | Result |
|---|---|
| `initialize` | ✅ `{userAgent, version, platformOs}`, followed by an `initialized` notification |
| `server/status` | ✅ `{uptimeMs, threads, listeners}` |
| `thread/start` | ✅ `{thread:{id:"thr_…", origin:"inProcess", sessionId?, status, createdAt}}` |
| `thread/resume` | present (`-32602` on `{}`; takes `sessionId`) |
| `thread/list` | ✅ registry contents |
| `thread/close` | present |
| `thread/subscribe` / `thread/unsubscribe` | present |
| `thread/read` | present (paginated transcript, offset-from-end cursor) |
| `turn/start` | present — param is **`input`**, not `prompt` |
| `turn/interrupt` | present (`cancelQueued` accepted and inert — see the scorecard's gap 1) |
| `decision/list` / `decision/respond` | present |
| `thread/attach`, `thread/stop` | ❌ `-32601` |
| `thread/model/set`, `thread/permissionMode/set`, `thread/capabilities/read`, `thread/compact/start`, `thread/usage/read`, `thread/contextUsage/read` | ❌ `-32601` |
| `task/list`, `turn/background`, `thread/rewind` | ❌ `-32601` |
| `account/read`, `thread/init/read`, `mcpServer/status/list` | ❌ `-32601` |
| `toString`, `constructor` | ❌ `-32601` (prototype-pollution guard holds) |

Notifications observed on the wire during a full turn (union across the
probe runs):

```
initialized, thread/status/changed, turn/started, item/started,
item/completed, item/agentMessage/delta*, decision/requested,
decision/resolved, turn/completed, thread/closed*
```

(`*` = present in the source's broadcast set; the delta and `thread/closed`
frames were not both exercised by every run above.) Every notification
carries an `emittedAtMs` stamp.

Error codes are a stable, machine-readable vocabulary
(`harness/src/appserver/rpc.ts`), and the probe hit each of the
operationally interesting ones live:

```
-33001 BUSY               "Thread is busy"        (concurrent turn/start)
-33002 ALREADY_SETTLED    + data:{by:"B#6"}       (second answer to one park)
-33003 UNAUTHENTICATED    "Invalid token" / "Not authenticated"
-33004 THREAD_NOT_FOUND   (subscribe to thr_nope)
-32001 OVERLOADED         (admission refused during shutdown — read from source)
```

**This is a narrow-by-design M1 surface.** The scorecard at
`CC-to-SDK/docs/parity/appserver.md` marks the whole set/read family as
`planned(M2)` and fleet adoption (`thread/attach`) as `planned(M3)`. The
probe confirms the scorecard is accurate, not aspirational: the registry
type is literally `type ThreadOrigin = "inProcess"; // fleet adoption is M3`.

**Naming trap for the round:** `ccx attach` (the CLI verb) is **not** this
seam. `harness/src/cli/attach.ts` resolves a target to
`hostSocketPath(pid)` — `~/.claude/ccx/run/<pid>.sock`, a Unix domain
socket. It is node-local by construction and cannot cross a pod boundary.
The *appserver's* equivalent of attach is
`thread/subscribe` + `thread/read`, which is network-capable and was
probed live. Anything the round says about "attach" as a cross-pod
mechanism must mean the appserver methods, not the CLI verb.

## (d) Park / respond — the decisions-as-state property, live

The load-bearing claim is that a permission park is *state on the server*,
not a reverse-RPC call to whoever happened to ask — so any client can
answer it later. Verified: connection **A** started the thread, subscribed,
and started the turn; a completely independent connection **B** listed and
answered the park.

```
thread/start        :: {"thread":{"id":"thr_89039e146e83","origin":"inProcess","status":"idle",…}}
thread/subscribe    :: {"subscribed":true}
turn/start          :: {"turn":{"id":"turn_thr_89039e146e83_1","status":"inProgress"}}
decision/requested  :: {"threadId":"thr_89039e146e83","turnId":"turn_…_1",
                        "decision":{"toolUseID":"toolu_p3","toolName":"Bash","kind":"permission",
                                    "input":{"command":"echo p3-park-probe"},"createdAt":…}}
decision/list       :: [ …the same entry… ]                       (connection A)
second-conn-decision/list :: [ …the same entry… ]                 (connection B — a different socket)
second-conn-respond :: {"ok":true}                                (connection B answers)
decision/resolved   :: {"toolUseId":"toolu_p3","by":"p3-b#2","answer":{"kind":"allow_once"}}
turn/completed      :: {"turn":{"id":"turn_…_1","status":"completed"}}
```

Multi-subscriber fan-out is symmetric — two subscribed connections
received byte-identical notification sequences:

```
A notes :: ["initialized","thread/status/changed","thread/status/changed","turn/started",
            "item/started","item/completed","item/started","decision/requested"]
B notes :: ["initialized","thread/status/changed","thread/status/changed","turn/started",
            "item/started","item/completed","item/started","decision/requested"]
```

Idempotence and kind-checking hold: a second answer to the same park
returns `-33002 Already settled` with `data.by` naming who won, and a
kind-mismatched answer is rejected (here it surfaced as `alreadySettled`
because the park was already gone — the `ANSWER_KINDS` table in
`appserver/broker.ts` is the kind gate for a still-parked decision).

**Environmental limitation — stated plainly.** Both credentials on this
machine are exhausted, so the park above could not be raised by a *real*
model turn. Two real-model attempts were made and both returned an
immediate refusal message instead of a tool call:

```
item/completed … "text":"You've hit your weekly limit · resets Aug 3 at 12am (Asia/Seoul)"   # CLAUDE_CODE_OAUTH_TOKEN
item/completed … "text":"Credit balance is too low"                                          # ANTHROPIC_API_KEY
```

The probe therefore ran the **real `AppServer`** and the **real
`listenWs`** transport with only the engine replaced through the shipped
dependency-injection seam (`AppServerDeps.sessionFactory`), by a fake
`EngineSession` whose `submit()` awaits `config.permissionBroker.request(…)`
— the same call the SDK's `canUseTool` seam makes. Everything under test
in P3 (bind, auth, dispatch, broker park, broadcast, subscriber replay,
transport) is above that seam and was exercised unmodified. The
real-model path is separately covered by the repo's own gated live test,
`harness/test/live/appserver-m1.test.ts` ("real `AppServer` (default
sessionFactory — no DI fakes), real `listenWs`… against the real SDK"),
recorded as live-accepted on 2026-07-29 in
`CC-to-SDK/docs/parity/coverage.md`; that test binds an **ephemeral
loopback** port, so the network-boundary half of this probe is genuinely
new evidence and the model half is not.

**What a cluster environment must verify:** one real-model
spawn→turn→park→respond over a pod-to-pod (non-loopback) connection, with
a working fleet credential.

## (e) Reconnect and disconnect semantics

Tested by hard-terminating connection A's socket mid-turn with a parked
decision outstanding (`ws.terminate()` — no close frame, no
`thread/unsubscribe`), then joining from a brand-new connection B.

```
A-parked        :: true
(A socket terminated; 1.5s pause)
B-thread/list   :: [ …, {"id":"thr_6211b05cf955","origin":"inProcess","status":"active",…} ]
B-subscribe     :: {"subscribed":true}
B-replay-notes  :: [ {"method":"initialized"},
                     {"method":"turn/started",         keys:["threadId","turn"]},
                     {"method":"item/started",         keys:["threadId","turnId","item"]},
                     {"method":"item/completed",       keys:["threadId","turnId","item"]},
                     {"method":"item/started",         keys:["threadId","turnId","item"]},
                     {"method":"decision/requested",   keys:["threadId","turnId","decision"]},
                     {"method":"thread/status/changed",keys:["threadId","status"]} ]
B-saw-park      :: true
B-respond       :: {"ok":true}
B-turn/completed:: {"turn":{"id":"turn_thr_6211b05cf955_1","status":"completed"}}
B-close         :: {"ok":true}
```

The semantics, confirmed:

- **The thread outlives its client.** A dropped socket only removes that
  `Peer` from every thread's subscriber set (`AppServer.connect`'s `close`
  sweeps *all* records, not just the last one touched). The engine keeps
  running and the park keeps waiting.
- **Parks never expire.** `ThreadDecisions` constructs its inner
  `PendingDecisions` with `expireAfterMs: "never"` — "a detach-first
  server parks forever." There is no auto-deny timer to design around.
- **Rejoin is replay-first, in a fixed order:** `turn/started` (only if the
  client actually missed it) → buffered per-turn item events → parked
  decisions → `thread/status/changed` last. The item buffer is bounded at
  500 events per turn, reset each turn, with a drop-oldest policy that
  folds a still-deltaed `item/started` forward so replay stays
  reconstructable.
- **Backpressure disconnects rather than buffers.** `Peer` caps outbound
  at 32 MiB (`ws.bufferedAmount`) and closes the socket with code `1013`
  when a consumer falls behind; inbound frames are capped at 256 KiB
  measured in *bytes*. The design bet is explicit in the source: "replay-
  first subscribe makes reconnect cheap by design."
- **Shutdown is graceful on both SIGINT and SIGTERM** (`onStopSignals`),
  and tears threads down *before* the listener — parked decisions are
  settled with a system deny and `thread/closed` is broadcast. This is the
  right shape for a k8s `preStop`/termination-grace window.
- **There is no application-level heartbeat.** No `ping`/`pong`, no
  `clientTracking` liveness sweep anywhere in `src/appserver/` (grepped).
  Dead-peer detection is whatever TCP gives you.

## (f) What a k8s deployment needs on top

### f.1 TLS — needs-build (or terminate externally)

`listenWs` constructs `new WebSocketServer({ host, port, verifyClient })`
with no `server` option, so there is no way to hand it an HTTPS server, a
certificate, or a key. `--listen` also *rejects* any scheme but `ws:`
("`--listen` must use the ws:// scheme"). The bearer token therefore
crosses the wire in cleartext today.

Options, in order of least new code:
1. **Terminate TLS at the mesh/ingress** (Istio/Linkerd mTLS sidecar, or
   an ingress with a `wss://` front and `ws://` backend). Requires zero
   harness change and gives mutual authentication for free, which also
   addresses f.2 partly. This is the recommended shape.
2. Add a `server?: http.Server | https.Server` passthrough to
   `WsListenOpts` — a small, contained change to `transport/ws.ts` plus a
   `wss:` arm in the `--listen` parser.

Classification: **needs-build**, but option 1 makes it an *infra* build,
not a harness build.

### f.2 Authorization and identity — needs-build

Today's model is one server-wide shared secret with no notion of a
principal. Verified consequences:

- Any authenticated client can `thread/start` with an **arbitrary
  `config`** — `buildConfig` spreads the client's whole `config` object
  straight into `openSession` (`cwd`, `permissionMode`, `settings`,
  `mcpServers`). The probe created a thread with bare `{}` params. Holding
  the token is equivalent to arbitrary code execution in the pod.
- Any authenticated client can subscribe to, drive, answer decisions for,
  interrupt, and close **any other client's** thread. Demonstrated in §d.
- The `by` field on `decision/resolved` is documented as "server-stamped
  only," and the `connId` half genuinely is — but the string is
  `` `${ctx.clientName}#${ctx.connId}` `` where `clientName` comes from the
  client's own `initialize` params. The probe's connection B chose to be
  called `p3-b`, and the audit record says `by:"p3-b#2"`. **The human-
  readable half of the attribution is caller-chosen and must not be
  treated as an audit identity.**

For a k8s control plane this is the largest gap. The minimum shape:
per-caller credentials (mTLS SPIFFE identity from the mesh, or a signed
JWT the server verifies), a principal recorded on `ConnCtx`, and a
thread-ownership check on every thread-scoped method. Whether that is
built into `cc-harness` or enforced by an authorizing proxy in front of it
is a real design fork for R1/R2 — the proxy variant needs no harness
change but must parse the JSON-RPC method+params to scope anything, since
authorization decisions here are per-`threadId`, not per-URL.

Classification: **needs-build**, and it is the blocker for treating this
seam as a multi-tenant control plane rather than a single-tenant pod API.

### f.3 Heartbeat and idle timeouts — needs-build (small)

No `ping`/`pong` exists. Kubernetes ingress controllers and cloud load
balancers idle out WebSocket connections (typically 30–60s of silence),
and a long park with no activity is exactly a silent connection. Two
mitigations, both cheap: `ws`'s built-in
`ping`/`pong` with a `setInterval` sweep on the server, or a periodic
no-op notification. The replay-first design means a *dropped* connection
is recoverable (§e), so this is a quality-of-service issue rather than a
correctness one — but without it, every long-parked client silently churns
its socket.

Classification: **needs-build**, ~20 lines in `transport/ws.ts`.

### f.4 Service discovery — needs-build, but out of process

Nothing in the appserver knows about other appservers. `thread/list` is
`registry.list()` — this process's in-memory map only. So "which pod holds
thread X" has no answer on this wire, by design at M1.

The k8s-native shapes:
- **Per-worker addressability:** a `StatefulSet` + headless `Service`
  gives each pod a stable DNS name
  (`worker-3.workers.ns.svc.cluster.local`), which is the cheapest way to
  make a `threadId` routable *if* the controller records the pod that
  minted it. A plain `Deployment` behind a `ClusterIP` cannot work — any
  round-robin dial lands on a pod that answers `-33004 Thread not found`.
- **The board is the registry.** The Class-A Postgres SSOT board is the
  natural place to record `threadId → pod DNS name → sessionId`; that is a
  row, not a new protocol. The appserver needs no change for this.
- The M3 `thread/attach` method in the spec is about adopting a thread
  from a *fleet host on the same node*, not about cross-pod routing. It
  does not solve discovery and should not be mistaken for it.

Classification: **needs-build**, entirely outside `cc-harness`.

### f.5 Durability across pod restart — partial ceiling

Both the thread registry (`Registry`, a `Map`) and the parked decisions
(`PendingDecisions`, a `Map`) are process memory. If the pod dies:

- **Parked decisions are lost.** A park is an un-settled `Promise` in the
  dead process; nothing about it is on disk. Any answer for it is gone.
- **Conversation state is recoverable**, but only where the transcript is.
  `thread/resume` takes a `sessionId` and calls `resumeSession`, which
  reads the persisted transcript. On default settings that is the local
  filesystem (`~/.claude/projects/…`), which dies with an ephemeral pod —
  so a k8s deployment must route it to a shared store. The harness ships
  `sessionStore` adapters for exactly this
  (`harness/src/store/postgresSessionStore.ts`,
  `harness/src/store/redisSessionStore.ts`) with a conformance suite
  (`src/store/conformance.ts`), which is what makes resume-on-another-pod
  possible at all.
- **A restarted pod comes back with zero threads** and no way to enumerate
  what it was running. Reconstruction has to come from outside — again,
  the board.

So the honest ceiling is: **turn-level durability, not decision-level.** A
run interrupted mid-park must be resumed as a *new* thread over the same
`sessionId` and the tool call re-attempted; it cannot be answered where it
stopped. Whether that is acceptable is a real design question for R1 —
mitigations are (a) run swarm workers `unattended: "deny"` or in an
auto/bypass permission mode so parks are rare, or (b) mirror parks to the
board as they are raised, which requires a harness change.

Classification: **partial ceiling** — turn resume `exists` (given a shared
sessionStore), park survival `needs-build`.

### f.6 Config injection over the wire — impossible by construction

`thread/start`'s `config` is validated as
`z.record(z.string(), z.unknown())` — i.e. a JSON object. The harness's
most powerful knobs are **not JSON-representable**: `sessionStore` is an
object with methods, hooks are functions, and `permissionBroker` is
overwritten by the server's own broker regardless of what a client sends.
`serveMain.ts` constructs `new AppServer({ token })` with **no** `deps`
and no harness config of its own, so today a `ccx serve` process has no
mechanism to apply pod-level defaults such as "always use this Postgres
session store."

Consequence for k8s: either the pod's `ccx serve` is replaced by a small
program that constructs `AppServer` with the right `AppServerDeps` and
calls `listenWs` itself (the shape this probe's own fallback harness used
— it is a ~15-line entry point), or `serveMain` grows a way to load a
process-wide harness config. The former needs no upstream change; the
latter is a clean cc-harness backlog item ("`ccx serve --config`, applied
as the base every `thread/start` merges onto").

Classification: **impossible over the JSON wire** (correctly so — it is a
security property, not a bug); **needs-build** as a process-side default.

### f.7 Minor operational notes

- `serveMain.ts` writes its run-file to a **fixed** path,
  `$CCX_FLEET_ROOT/run/appserver.json`. Two `ccx serve` processes sharing a
  `CCX_FLEET_ROOT` (i.e. sharing `$HOME`) clobber each other's record. One
  server per pod makes this a non-issue; a sidecar arrangement does not.
- `CCX_FLEET_ROOT` is honoured for all state paths, so per-pod isolation
  needs only an env var.
- The health-check surface for a k8s probe is `server/status`
  (`{uptimeMs, threads, listeners}`) — but it is *behind* `initialize`, so
  a probe must hold the token and speak the protocol. A plain HTTP
  `GET /healthz` does not exist. Cheap kubelet liveness/readiness probing
  is therefore **needs-build** (a TCP-socket probe works but only proves
  the listener is up, not that the dispatcher is alive).

---

## Verdict for the round

The appserver **is** a viable cross-pod agent↔agent and control-plane seam
— the two properties that make it interesting are both real and were
verified over a network interface: decisions are *state* (any authorized
client can answer any park, including one raised before it connected), and
rejoining is *replay-first* (a fresh connection reconstructs the in-flight
turn without the original client). Those are exactly the properties a
one-way-mirror control plane wants, and they are shipped, not planned.

The gap between "works on my LAN" and "runs a cluster" is four items, in
priority order: **(1) per-identity authorization** — today's shared token
means possessing it is arbitrary code execution and full control of every
thread; **(2) TLS**, best solved by the mesh rather than the harness;
**(3) a discovery/ownership record** mapping `threadId` to a stable pod
name, which the Postgres board should own rather than the protocol; and
**(4) a decision on park durability**, since a pod restart destroys parks
irrecoverably while turns remain resumable through a shared session store.
None of the four is architecturally blocked; three of the four are built
*outside* `cc-harness`.

The single item that would most improve the seam from inside the harness
is not on the M2 list: a process-side default config for `ccx serve`
(f.6), so a pod can pin its session store and permission posture without a
bespoke entry point.

---

## Reproduction

Server (real engine):

```bash
cd CC-to-SDK/harness && npm run build
printf '<32-hex-secret>' > /tmp/p3/appserver.token && chmod 600 /tmp/p3/appserver.token
set -a; . ../.env; set +a
CCX_FLEET_ROOT=/tmp/p3/fleet node dist/cli/bin.js serve \
  --listen ws://0.0.0.0:9711 --token-file /tmp/p3/appserver.token
```

Server (DI fake engine, no credentials needed) and the four client modes
(`auth`, `surface`, `park`, `reconnect`) are the scripts
`fakeserve.mjs` / `client.mjs` / `multi.mjs` written for this probe; they
import `ws` and the built `dist/appserver/*` directly and are reproducible
from the transcripts quoted above. `P3_URL` selects the interface, so
pointing them at a pod IP or a `Service` DNS name is the cluster-side
follow-up.

## Sources

- `CC-to-SDK/harness/src/appserver/{server,peer,rpc,registry,broker,turns,subscribe}.ts`,
  `src/appserver/transport/ws.ts` — read and probed.
- `CC-to-SDK/harness/src/cli/{args,main,serveMain,attach}.ts`,
  `src/fleet/paths.ts` — bind policy, token policy, run-file, the
  UDS-vs-WS distinction.
- `CC-to-SDK/harness/src/permissions/{types,pending}.ts` — park lifecycle,
  `expireAfterMs: "never"`.
- `CC-to-SDK/harness/src/store/{postgresSessionStore,redisSessionStore,conformance}.ts`
  — shared-transcript backends.
- `CC-to-SDK/docs/parity/appserver.md` — the generated seam scorecard;
  its `shipped(M1)` / `planned(M2)` / `planned(M3)` split matches what the
  live method probe found.
- `CC-to-SDK/docs/parity/coverage.md` (domain 10) — "Agent app-server M1
  SHIPPED (2026-07-29)", live-accepted end to end.
- `CC-to-SDK/harness/test/live/appserver-m1.test.ts` — the real-model
  acceptance test (loopback-bound), cited for the model half this probe
  could not run.
- Command transcripts: this session, 2026-07-30, macOS Darwin 25.5.0,
  Node v24.18.0, `cc-harness@0.1.0`.
