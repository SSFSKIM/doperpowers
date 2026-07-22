# Deep-read: Anthropic — "Scaling Managed Agents: Decoupling the brain from the hands" (Apr 08, 2026)

Reader note: this is a fresh re-read at the NEW target scale (hundreds–thousands of
implementer+reviewer runs/hour/project, multi-host, enterprise-internal). The old
single-host-scale rejections were deliberately not consulted; each mechanism is
re-judged on its merits below (§5).

---

## 1. Thesis in 3 sentences

Harnesses encode assumptions about what the model cannot do, and those assumptions
go stale as models improve, so Anthropic built Managed Agents as a "meta-harness":
a small set of stable interfaces (session, harness, sandbox) that outlast any
particular harness implementation — the OS analogy is explicit ("programs as yet
unthought of"; `read()` doesn't care if it's a 1970s disk pack or an SSD). The core
architectural move is decoupling the "brain" (Claude + harness loop) from the
"hands" (sandboxes/tools) and from the "session" (append-only durable event log),
so each component is cattle: a dead container is just a tool-call error, a dead
harness is rebooted from the session log, and credentials are structurally
unreachable from the sandbox where generated code runs. The payoff they claim is
operational (no more nursing pet containers, debuggable failure boundaries),
security-structural (tokens never co-resident with untrusted code), and
performance (lazy sandbox provisioning dropped TTFT p50 ~60% and p95 >90%).

## 2. Mechanisms & architecture

### 2.1 The three virtualized components

- **Session** — the append-only log of everything that happened. Durable, stored
  outside both harness and sandbox, in a service (not files inside a container).
- **Harness** — the loop that calls Claude and routes Claude's tool calls to
  infrastructure. Stateless; nothing in it needs to survive a crash.
- **Sandbox** — an execution environment where Claude runs code and edits files.
  Ephemeral; reachable only through the tool interface.

Each is an interface making few assumptions about the others; each can fail or be
replaced independently. They are "opinionated about the shape of these interfaces,
not about what runs behind them."

### 2.2 Interface contracts (as given in the article)

- `execute(name, input) → string` — how the harness calls ANY hand: a container,
  a custom tool, an MCP server, "a phone, or a Pokémon emulator." Container death
  surfaces as a tool-call error passed back to Claude, which may decide to retry.
- `provision({resources})` — reinitialize a fresh container from a standard
  recipe. No nursing; replacement, not repair.
- `wake(sessionId)` — boot a fresh harness onto an existing session.
- `getSession(id)` — fetch the event log back into the new harness; resume from
  the last event.
- `emitEvent(id, event)` — the harness durably records each event during the
  agent loop.
- `getEvents()` — positional-slice interrogation of the event stream: pick up
  where you last stopped reading, rewind a few events before a moment, reread
  context before a specific action.

### 2.3 The pet-container starting point (what they did first, and why it failed)

V1 put session + harness + sandbox in ONE container. Benefits: file edits are
direct syscalls, no service boundaries to design. Costs discovered:

1. **The container became a pet.** Container fails → session lost. Container
   unresponsive → an engineer nurses it.
2. **Undebuggable.** The only window in was the WebSocket event stream, which
   could not localize failures: a harness bug, a packet drop in the event stream,
   and a container going offline "all presented the same." Shelling into the
   container was effectively forbidden because it held user data — "that approach
   essentially meant we lacked the ability to debug."
3. **Locality assumption baked in.** The harness assumed everything Claude works
   on lives next to it. Customers wanting VPC-resident resources had to peer
   networks with Anthropic or run Anthropic's harness in their own environment.
4. **Eager provisioning tax.** Every session paid full container setup up front —
   clone the repo, boot the process, fetch pending events — even sessions that
   would never touch the sandbox. This dead time is TTFT.

### 2.4 Security boundary: credentials structurally unreachable from the sandbox

In the coupled design, untrusted generated code ran in the same container as
credentials, so "a prompt injection only had to convince Claude to read its own
environment"; with stolen tokens an attacker "can spawn fresh, unrestricted
sessions and delegate work to them." Their key argument: narrow token scoping is
itself a stale-able assumption about what Claude can't do with a limited token —
"Claude is getting increasingly smart." The structural fix: tokens never reachable
from where generated code runs. Two patterns:

1. **Auth bundled with the resource.** For Git: the repo's access token is used
   to clone during sandbox initialization and is wired into the local git remote.
   Push/pull work from inside the sandbox; the agent never handles the token.
2. **Vault + proxy for custom tools (MCP).** OAuth tokens live in a secure vault
   outside the sandbox. Claude calls MCP tools via a dedicated proxy; the proxy
   receives a session-associated token, fetches the real credentials from the
   vault, and makes the external call. "The harness is never made aware of any
   credentials" either.

### 2.5 The session is not the context window

Standard long-horizon techniques (compaction, memory tool, context trimming) all
make **irreversible** decisions about what to keep, and "it is difficult to know
which tokens the future turns will need." Compacted messages are recoverable only
if stored somewhere. Prior work (cited: Recursive Language Models, arXiv
2512.24601) stores context as an object in a REPL that the model slices with code.
Managed Agents takes the same benefit but stores context durably in the session
log rather than in a sandbox/REPL:

- `getEvents()` gives positional slices of the stream (see §2.2).
- **Fetched events can be transformed in the harness before entering Claude's
  context window** — including "context organization to achieve a high prompt
  cache hit rate" and arbitrary context engineering.
- Deliberate separation of concerns: the session guarantees only durability and
  interrogability; ALL context management lives in the harness, because "we can't
  predict what specific context engineering will be required in future models."
  Compaction thus becomes a non-destructive VIEW; the log keeps everything.

### 2.6 Many brains, many hands

- **Many brains** = start many stateless harnesses; connect hands only if needed.
  Sandboxes are provisioned by the brain **via a tool call, only when needed** —
  a session that doesn't need a container doesn't wait for one; inference starts
  as soon as the orchestration layer pulls pending events from the session log.
- **Many hands per brain**: Claude reasons about multiple execution environments
  and decides where to send work — "a harder cognitive task than operating in a
  single shell," which earlier models couldn't do (hence the original single
  container). As intelligence scaled, the single container became the limitation:
  when it failed, "we lost state for every hand that the brain was reaching into."
- **Hands passed between brains**: because no hand is coupled to any brain,
  "brains can pass hands to one another."
- Motivating quote for the whole harness-churn premise: Sonnet 4.5's "context
  anxiety" (wrapping up prematurely near the context limit) was fixed with harness
  context resets; on Opus 4.5 the behavior was gone and "the resets had become
  dead weight."

### 2.7 The productized contract (from the docs, not the article)

From platform.claude.com/docs/en/managed-agents/* — this is what the article's
architecture looks like as a shipped API, and it is directly relevant as a
reference design:

- **Four concepts:** Agent (model + system prompt + tools + MCP + skills),
  Environment (WHERE sessions run: Anthropic cloud sandbox or self-hosted),
  Session (running instance), Events (messages both directions). Event history
  persisted server-side, fetchable in full; SSE streaming; steer/interrupt
  mid-execution by sending user events. Beta header `managed-agents-2026-04-01`.
  Stateful by design → currently NOT eligible for Zero Data Retention or HIPAA BAA.
- **Self-hosted sandboxes = exactly "brain on their side, hands on yours":**
  orchestration/model on Anthropic's control plane; tool execution, filesystem,
  and network egress on your infra. Tool inputs/outputs still transit their
  control plane.
- **Dispatch is a work queue, not push-to-host:** workers CLAIM items by polling
  the environment's queue (always-on poller, or webhook-triggered on
  `session.status_run_started`). Long-poll `block_ms` 1–999 ms;
  `reclaim_older_than_ms` re-claims items claimed but never acknowledged (lease
  recovery for dead workers).
- **Two-credential split:** an *environment key* authenticates the worker to its
  queue only; the org API key stays off the worker host ("Setting
  ANTHROPIC_API_KEY on the worker host exposes an organization-scoped credential
  to agent tool calls").
- **Per-session ephemeral sandbox pattern:** poller injects
  `ANTHROPIC_SESSION_ID`, `ANTHROPIC_WORK_ID`, `ANTHROPIC_ENVIRONMENT_ID`,
  `ANTHROPIC_ENVIRONMENT_KEY` into a spawn script; a fresh sandbox (image with
  `ant beta:worker run` as entrypoint) handles ONE session and exits; host dir
  bind-mounted to `/workspace` captures deliverables.
- **Queue observability trio:** `depth` (waiting items — "scale your worker fleet
  or alert on backlog based on this value"), `pending` (claimed-not-acked — a
  sustained non-zero value means a worker stalled), `workers_polling` (workers
  seen in the last 30 s — liveness).
- **Custom tools:** agent emits `agent.custom_tool_use`, waits for
  `user.custom_tool_result`; unregistered tool leaves the session paused with
  stop reason `requires_action`. Tool-call backstop timeouts: ~120 s (Go worker
  default), ~2.5 min (Python), ~1 min (TypeScript MCP SDK default).
- Platform-specific self-hosted guides exist for AWS Lambda MicroVMs, Cloudflare,
  Daytona, E2B, GKE Agent Sandbox, Modal, Vercel, etc. — i.e., the sandbox side
  is a commodity slot.

## 3. Numbers (exact quotes)

- "our p50 TTFT dropped roughly 60% and p95 dropped over 90%" — from lazy,
  tool-call-driven sandbox provisioning alone.
- Published **Apr 08, 2026**. Beta header `managed-agents-2026-04-01`.
- Self-hosted worker queue: `block_ms` "must be between 1 and 999" ms (default
  999 ms long-poll); `workers_polling` window = last 30 seconds; Go worker
  "cancels a tool call that outlives its 120-second default."
- From the cited harness-design post (context for "task-specific harnesses excel
  in narrow domains"): solo general agent — 20 minutes, $9, broken app;
  task-specific harness — 6 hours, $200 ("over 20x more expensive"), working game.
- The article gives NO numbers for: sandbox provision latency, session-store
  scale, event counts, cost, concurrency limits, or fleet size.

## 4. Failure modes & operational lessons they report

1. **Pet container**: any container failure = session lost; unresponsive
   container = manual nursing.
2. **Failure aliasing**: with only a WebSocket event stream as the window, harness
   bug vs. event-stream packet drop vs. container-offline were indistinguishable.
3. **Privacy lockout of debugging**: the debug path (shell into container) was
   blocked because the container held user data → "we lacked the ability to
   debug." Lesson: separating harness from user-data sandbox is what makes the
   harness debuggable at all.
4. **Locality assumption → VPC pain**: harness-in-container forced network
   peering or running their harness in customer environments.
5. **Eager provisioning tax**: every session paid clone+boot+fetch up front even
   if the sandbox was never used; visible as TTFT.
6. **Credential co-residency**: prompt injection only needed to read the
   environment; scoping is a mitigation that decays as models improve.
7. **Irreversible context decisions**: compaction/trimming discard tokens future
   turns turn out to need; recoverable only if stored.
8. **Stale harness assumptions**: context-anxiety resets built for Sonnet 4.5
   became dead weight on Opus 4.5 — harness features must be re-validated per
   model generation.
9. **Single container as fan-in risk**: one brain reaching into many hands from
   one container = losing that container loses state for every hand.

## 5. Transfer analysis at the NEW scale

Substrate context: today we run host processes on one Hetzner VM, file-based
daemon registry keyed (host, pid, session), git worktrees, one detachable volume,
durable JSONL session logs, board as SSOT. Target: hundreds–thousands of
implementer+reviewer runs/hour/project, multi-host, enterprise-internal,
non-adversarial tenants.

### STEAL

- **Session/harness/sandbox decoupling as the substrate's core factoring.**
  This is our own doctrine (durable log = identity, compute disposable) carried
  to completion. At multi-host, our (host, pid, session) registry key is already
  dead — pid is meaningless across hosts. Sessions move from files-on-a-volume to
  a shared durable event store; any host can `wake(sessionId)`. The detachable
  volume is itself a pet at this scale.
- **Per-worker ephemeral sandbox provisioning** *(previously rejected —
  justified ONLY at the new scale)*. At a few workers on one box, worktrees on
  the host were strictly simpler. At 100s–1000s runs/hour multi-host, hand-tended
  host processes cannot be scheduled, quarantined, resource-capped, or bulk-reaped;
  the "provision from a standard recipe, never repair" posture is the only one
  that survives. The docs' pattern (poller spawns one fresh sandbox per session,
  bind-mount captures deliverables, sandbox exits) is a ready-made shape.
- **Queue-based dispatch with claim/ack/lease-reclaim + depth/pending/liveness
  metrics** (from the docs). This replaces the file-based daemon registry as the
  dispatch mechanism. `reclaim_older_than_ms` is exactly the dead-worker recovery
  our doctrine wants: a claimed-but-dead run's work item returns to the queue and
  a fresh process resumes from the durable session. `depth` drives autoscaling,
  `pending` detects stalls, `workers_polling` gives fleet liveness — three
  metrics, all substrate-level, none touching the semantic layer.
- **Auth-bundled-with-resource for git** (half of the previously rejected
  "credential vault" complex). Cheap at ANY scale and we should have taken it the
  first time: clone with a short-lived installation token wired into the remote
  at sandbox init; the agent never sees a token; nothing to leak in env or JSONL.
- **Failure-boundary observability**: harness logs must live OUTSIDE the sandbox
  that holds repo/user data, so that harness bug / transport drop / sandbox death
  are distinguishable and debugging never requires entering a data-bearing
  environment. At thousands of runs/hour, failure aliasing (their lesson #2) is
  the difference between an alert and an outage archaeology session.

### ADAPT

- **"Harness out of the container"** *(previously rejected; at the new scale:
  half-flips)*. Full decoupling assumes you own the harness. Ours is Claude Code
  CLI / Codex CLI — brain and hands are welded inside one process by the vendor.
  Two honest options: (a) **partial decouple** — treat CLI-process+sandbox as one
  disposable "hands+brain" unit, but ship the session JSONL out to the durable
  store continuously (session decoupled; harness+sandbox stay coupled); (b)
  **full decouple** — replace the CLI with an Agent-SDK-style harness we own, or
  adopt Managed Agents with self-hosted sandboxes outright. Recommendation: (a)
  now; the TTFT and lazy-provisioning wins of (b) matter mostly for
  gate-parked runs (see next item), and (b) sacrifices the mixed Claude/Codex
  fleet. Re-evaluate if harness ops dominate cost.
- **Lazy provisioning aligned with the pre-code gate.** Their biggest measured
  win (TTFT p50 −60%, p95 −90%) came from not provisioning eagerly. Our semantic
  layer has a natural analogue THEY don't: the pre-code gate. A meaningful
  fraction of runs end at the gate (park, decompose, reject) without needing a
  checkout. Run gate evaluation sandbox-less (ticket text + repo read via API);
  provision the worktree/sandbox only after the gate passes. At thousands of
  runs/hour this is real fleet capacity, and it needs no semantic change — it's
  the gate's existing two-phase structure expressed in the substrate.
- **MCP credential vault + proxy** *(previously rejected; at the new scale:
  adopt, scoped)*. With hundreds of autonomous runs/hour across multiple teams'
  repos, assume some run WILL be prompt-injected; token blast radius scales with
  run count × team count. Their structural argument (scoping decays as models
  get smarter) is correct. But we don't need their full generality: an egress
  proxy holding per-team credentials for the handful of internal services workers
  touch, keyed by run identity, is enough. Enterprise-internal means the vault
  can be the company's existing secrets manager.
- **getEvents() context-interrogation layer** *(previously rejected; at the new
  scale: adopt the storage half, skip the interrogation half)*. The load-bearing
  idea is **compaction must never rewrite the durable log** — compacted context
  is a derived view; the session store keeps everything and supports ranged
  reads. Multi-host forces sessions into shared storage anyway, so ranged reads
  come almost free. The fancy part (model-driven rewind/reread of positional
  slices) is only worth building when a harness we own can exploit it — defer.
- **Many hands per brain.** For implementers, mostly irrelevant (one ticket, one
  worktree). Where it earns adoption: a worker reaching into ADDITIONAL
  short-lived hands — a browser sandbox for verification, a test-runner pool —
  via a uniform `execute()`-shaped interface rather than bespoke plumbing.

### REJECT

- **Session-as-REPL-object (RLM-style)** — still research-flavored; even the
  article only adopts the weaker "durable interrogable log" form. Not substrate.
- **Hand-passing across the implement/review boundary.** Brains passing hands to
  one another is elegant, but a reviewer inheriting the implementer's sandbox
  would let implementation-environment state leak into review. Our semantic layer
  makes review a *separate adversarial species*; the reviewer must build/verify
  in a fresh environment. Reject here specifically; hand-passing WITHIN an
  implementer's own retry chain is fine.
- **Managed Agents (the product) as our substrate.** Tempting shortcut —
  self-hosted sandboxes are literally "their brain, our hands," and the sandbox
  side is a commodity slot with ten platform guides. But: beta API, no
  ZDR/HIPAA posture, session data on their control plane, and it forecloses the
  mixed Claude+Codex worker fleet. Treat it as the best-documented *reference
  design* for our own control plane, not as the control plane.

## 6. Tensions with our frozen semantics / settled doctrine

- **Confirms, does not contradict, the core doctrine.** "Durable log = identity
  of work, compute disposable" is exactly their session/harness split; the
  article extends it with the part we hadn't fully committed to: the HARNESS is
  also disposable, not just the container, and the log must live in a service,
  not on a host-attached volume. That volume is doctrine-compliant at one host
  and doctrine-violating at many.
- **One nuance to the doctrine**: we call session files "a resume optimization"
  subordinate to the board. Their design makes the session the *only* full
  record of what happened inside a run (the board can't hold event streams at
  thousands of runs/hour). Suggested refinement, not a reversal: board = SSOT of
  ticket STATE; session store = SSOT of run HISTORY; neither substitutes for the
  other. This is a substrate clarification, not a semantic-layer change.
- **Hand-sharing vs. review independence** (see §5 REJECT): the article's "brains
  can pass hands to one another" is the one mechanism that, if adopted naively,
  would erode a frozen semantic guarantee (independent adversarial review). Flagged;
  recommend declining it at that boundary regardless of efficiency pressure.
- **Scale-forced semantic change: NONE found.** Loudly: nothing in this article
  forces a change to the pre-code gate, park states, adversarial review, or
  tiered merge authority. The closest pressure points are (a) hand-sharing
  economics (decline) and (b) their steer/interrupt-mid-run interaction model,
  which our park states deliberately don't have (a run parks and STOPS) — their
  model is for interactive users, ours for autonomous throughput; no change needed.

## 7. Open questions the article raises but does not answer

1. **Sandbox provision latency and cost** — lazy provisioning shifts the wait to
   first-tool-call time; how long is `provision({resources})` and what does it do
   to time-to-first-EDIT (the metric that matters for coding workers, not TTFT)?
2. **Retry semantics and idempotency** — container death surfaces as a tool-call
   error and "Claude decides to retry," but a new container loses uncommitted
   state. Is the repo re-cloned? How much work is lost? And for harness-crash
   resume: if a tool executed but its result event was never emitted, does the
   rebooted harness re-execute (double git push)?
3. **Prompt-cache economics across harness reboots** — cache hits key on exact
   prefixes; a rebooted harness re-transforming `getEvents()` output presumably
   cold-starts the cache. What does harness-as-cattle cost in cache misses?
4. **Scheduler/placement** — "scaling to many brains just meant starting many
   stateless harnesses" says nothing about admission control, fairness across
   projects, or backpressure at thousands of runs/hour. The docs' queue `depth`
   is the only visible knob.
5. **Session store limits** — no numbers on event-log size, retention, read
   throughput, or cost at scale.
6. **Vault/proxy failure modes** — the MCP proxy is a new single point of failure
   and a latency tax on every credentialed call; unquantified.
7. **Multi-brain consistency on shared hands** — if brains pass hands around, who
   arbitrates concurrent access to one sandbox's filesystem?

## 8. Links followed

1. https://platform.claude.com/docs/en/managed-agents/overview — the productized
   contract: Agent/Environment/Session/Events, beta header, statefulness → no
   ZDR/HIPAA, steer/interrupt model, scheduled deployments.
2. https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes — the
   richest find: full worker protocol (claim/ack/reclaim queue, env-key vs
   API-key split, per-session ephemeral sandbox spawn, depth/pending/
   workers_polling metrics, tool timeout backstops).
3. https://arxiv.org/pdf/2512.24601 — Recursive Language Models: context as a
   REPL object the model slices with code; grounds §2.5 and the REJECT in §5.
4. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
   — the prior harness work: initializer/coding agent split, progress files,
   feature checklists; context-reset provenance for the "context anxiety" claim.
5. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
   — compaction/memory/trimming definitions; "overly aggressive compaction can
   result in loss of subtle but critical context" (the irreversibility failure).
6. https://www.anthropic.com/engineering/harness-design-long-running-apps — the
   task-specific-harness evidence ($9/20min broken vs $200/6h working;
   generator-evaluator separation; context resets over compaction).
