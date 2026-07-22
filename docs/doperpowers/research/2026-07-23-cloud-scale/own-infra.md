# Deep-read report: Cursor — "Run cloud agents in your own infrastructure"

Article: cursor.com/blog/self-hosted-cloud-agents, published **Mar 25, 2026**, Katia Bazzi, 4 min read.
The blog post itself is thin marketing; nearly all engineering substance below comes from the
official docs it links to (self-hosted pool guide, self-hosted Kubernetes guide) and the
companion "Development environments for your cloud agents" post. Sources are marked inline.

---

## 1. Thesis in 3 sentences

Enterprises in regulated spaces cannot let code, secrets, or build artifacts leave their
network, so Cursor split its cloud-agent product into a **hosted control plane** (orchestration,
model inference, planning, UX) and a **customer-hosted data plane** ("workers" that execute
every tool call — clone, shell, file edits, builds, tests — inside the customer's network).
The worker is a single process that dials **outbound-only HTTPS** to Cursor's cloud, so no
inbound ports, firewall changes, or VPN tunnels are needed; each agent session claims exactly
one dedicated worker. At scale this becomes a **warm pool** managed by a Kubernetes operator
(`WorkerDeployment` with a desired ready-replica count) or, off Kubernetes, by customer
autoscaling built on a fleet-management API that reports connected/in-use counts.

## 2. Mechanisms & architecture

### 2.1 The plane split (blog + pool docs)

- **Control plane (Cursor's cloud):** the agent loop itself — inference, planning, session
  state, the dashboard/UX, team permissions, artifact display. "Cursor's agent harness handles
  inference and planning, then sends tool calls to the worker for execution on your machine.
  Results flow back to Cursor for the next round of inference." (blog)
- **Data plane (customer network):** a `agent worker start` process per session. It clones
  repos, runs commands, edits files, executes builds/tests, and reaches internal services
  (caches, package registries, internal endpoints) "just like an engineer or service account
  would." (blog)
- **Critical data-boundary nuance (pool docs, not the blog):** repos, build caches, secrets,
  tool execution, and build outputs stay local — but **"file chunks the model reads during
  inference are sent to Cursor"** as model context, and Cloud Agent artifacts (screenshots,
  videos, log references) are uploaded to an AWS S3 bucket
  (`cloud-agent-artifacts.s3.us-east-1.amazonaws.com`) for PR embeds and dashboard previews.
  The marketing line "your codebase ... never leave[s] your environment" is therefore about
  bulk storage and execution, not about the token stream: whatever the model reads transits
  the control plane. Anyone copying this architecture must state that boundary honestly.

### 2.2 Worker process & lifecycle (pool docs)

- Started with one command; requirements per machine: `agent` CLI
  (`curl https://cursor.com/install -fsS | bash`), `git` on PATH, a cloned repo with a
  configured remote, plus access to whatever build tools/registries/secrets/internal services
  the agent needs.
- **Connection model:** worker initiates a **long-lived HTTPS connection** to
  `api2.cursor.sh` (or `api2direct.cursor.sh`). No inbound ports, public IPs, or VPN.
- **Modes:**
  - `--pool`: registers for centralized assignment. "Each Cloud Agent session claims one
    worker at a time" — workers are never shared across concurrent sessions.
  - Default (no `--pool`): multi-use / shared assignment.
- **Single-use-with-grace lifecycle:** `--idle-release-timeout <seconds>` (example: 600)
  keeps the worker alive briefly after a session completes so follow-up messages can reuse
  it, then the process **exits with code 0**; in Kubernetes the pod restart policy replaces
  it with a fresh worker. Long-lived vs single-use is thus a config choice, and the clean
  path at scale is *fresh worker per session*.
- **Routing by labels:** key-value labels on workers; reserved labels `repo=<owner/repo>`
  (auto-derived from the git remote, cannot be set manually) and `pool=<name>` (set only via
  `--pool-name`). Custom labels via repeatable `--label k=v`, or JSON/TOML file
  (`--labels-file`, `CURSOR_WORKER_LABELS_FILE`). Every pool request implicitly matches on
  `repo=`; named-pool requests add `pool=`. This is how one fleet serves many repos/teams.
- **Multi-repo workers:** up to **20** `--worker-dir` paths per worker; first path is the
  primary shown in the dashboard.
- **Health/metrics:** `--management-addr :8080` exposes `/healthz` (200 while process runs),
  `/readyz` (200 when idle, **503 while a session is active** — i.e. readiness doubles as
  a "claimed" signal), and Prometheus `/metrics`:
  - gauges: `cursor_self_hosted_worker_connected`, `..._session_active`,
    `..._last_activity_unix_seconds`
  - counters: `..._connect_attempts_total`, `..._connect_retry_total`,
    `..._session_ends_total` **labeled by end reason**: `stream_end`, `stream_error`,
    `session_closed`, `session_error`, `connection_timeout`, `session_aborted`.

### 2.3 Kubernetes operator path (self-hosted-k8s docs)

- Helm-installed controller:
  `helm upgrade --install worker-set-controller oci://public.ecr.aws/j6w0t2f5/cursor/worker-set-controller-chart --namespace cursord --create-namespace --version 0.1.0-6c804a0 --set imageTag=6c804a0 --set env.enableAuthManagement=true`
  (optional `rbac.singleNamespace=true` to confine RBAC).
- **`WorkerDeployment` CRD:** key fields — `readyReplicas` (desired count of *ready/idle*
  workers, e.g. 5), container `image`, resource requests (documented minimum to boot:
  **1 CPU, 2Gi memory**), worker args (`--worker-dir`, `--management-addr 0.0.0.0:8080`,
  labels like `--label team=backend --label env=production`).
- **Auth management:** a Kubernetes secret holds the **service-account API key**, labeled
  `workers.cursor.com/worker-deployment=<name>`; the controller exchanges it for
  **short-lived tokens mounted at `/var/run/cursor/token`** and **rotates them without pod
  restarts** (workers pass `--auth-token-file`, which is re-read on reconnect).
- **Scaling & updates semantics:** scale by patching `readyReplicas`
  (`kubectl patch wd my-workers --type merge -p '{"spec":{"readyReplicas": 20}}'`).
  Because `readyReplicas` counts *idle* workers, claimed workers don't reduce the warm pool.
  **"Busy workers are never terminated"** during scale-down or rolling updates; rolling
  updates replace idle pods in batches and let active sessions run to completion.
- Prereqs: Kubernetes v1.24+, helm v3, Cursor Enterprise plan with the feature enabled.

### 2.4 Non-Kubernetes fleets (pool docs; cursor/cookbook)

- **Fleet management API** at `api.cursor.com/v0/private-workers` (service-account key only;
  personal/user/team/org keys can neither start pool workers nor manage capacity):
  - `GET /v0/private-workers?status=idle&limit=50` — list (status all|in_use|idle,
    limit 1–100 default 50, paginated).
  - `GET /v0/private-workers/summary` — `teamSummary.totalConnected` / `.inUse`; docs show
    autoscaling on `utilization = inUse/totalConnected >= 0.9`.
  - `GET /v0/private-workers/pw_<id>` — single worker.
- The `cursor/cookbook` repo (github.com/cursor/cookbook, `self-hosted-cloud-agent/`) ships
  three reference paths: **EC2 + Docker** (one worker container on one host, smallest
  footprint), **ECS/Fargate** (CloudWatch metrics + ECS Service Auto Scaling), **EKS + Helm**
  (the operator above).

### 2.5 Credentials & extension surface

- **Worker auth:** service-account API key via `CURSOR_API_KEY`, `--api-key`, or
  `--auth-token-file` (rotation-friendly). Dashboard has org-level toggles:
  "Allow Self-Hosted Agents" (opt-in per run) vs "Require Self-Hosted Agents" (mandatory
  routing — a policy lever ensuring no run silently falls back to vendor-hosted compute).
- **Environment build secrets** (dev-environments post): environments are Dockerfile-defined;
  "build secrets are scoped to the build step and aren't passed to the running agent's
  environment"; "secrets configured for one environment aren't accessible from any other";
  egress allowlists restrict outbound network per environment; an audit log captures every
  admin action on environments; cached Docker-layer builds run **70% faster**.
- **MCP routing rule (pool docs):** stdio/command MCP servers run **on the worker** (so they
  get private-network access); HTTP/SSE MCP servers run **on Cursor's backend** (OAuth
  handled there). Hooks (`.cursor/hooks.json`) and skills (`.cursor/skills/`,
  `.agents/skills/`) run on the worker; extra skills can be baked into the worker image.
- **Triggering:** Slack (`@Cursor self_hosted=true` / `pool=<name>` — the Money Forward
  workflow), GitHub comments (`@cursoragent self_hosted=true`, OWNER/COLLABORATOR gated),
  Linear issue body `pool=<name>`.

## 3. Numbers (exact quotes / values)

- Publication date: **Mar 25, 2026** ("Today, we're making self-hosted cloud agents generally
  available").
- Money Forward: "a workflow that enables **nearly 1,000 engineers** to create pull requests
  directly from Slack using Cursor's self-hosted cloud agents."
- "For organizations scaling to **thousands of workers**, we provide a Helm chart and
  Kubernetes operator." (blog)
- Pool caps (pool docs): "up to **10 workers per user and 50 per team**" — evidently the
  self-serve tier; the thousands-of-workers Helm tier is the enterprise arrangement
  ("For larger company-wide deployments, reach out to our team").
- Worker pod minimum: **1 CPU / 2Gi memory** "minimum to boot" (k8s docs).
- `--idle-release-timeout 600` (600 s grace) in both docs' examples.
- Up to **20** `--worker-dir` paths per worker.
- Fleet API list: limit **1–100**, default **50**.
- Docs autoscale example threshold: utilization **>= 0.9**.
- Dev environments: cached builds **"70% faster"**.
- Chart/controller version at time of docs: `0.1.0-6c804a0`; Kubernetes **v1.24+**.
- Named customers: Brex, Money Forward, Notion.
- No latency or cost numbers are published anywhere in the article or docs.

## 4. Failure modes & operational lessons reported

The docs give an explicit blocked-endpoint failure table (pool docs):

| Blocked | Effect |
|---|---|
| `api2.cursor.sh` / `api2direct.cursor.sh` | Worker cannot start or continue sessions (control-plane link is the single hard dependency) |
| Artifact S3 bucket | Artifact uploads fail; PR embeds and dashboard previews missing; **"the agent session and other tool calls keep working"** — graceful degradation |
| Tool-specific outbound hosts | Only that tool/integration fails; agent continues |

Operational lessons embedded in the design (they don't narrate incidents, but the mechanisms
imply the lessons):

- **Session-end reason taxonomy** (`stream_end`, `stream_error`, `session_closed`,
  `session_error`, `connection_timeout`, `session_aborted`) — they found it necessary to
  distinguish clean completion from stream errors from timeouts from aborts, per worker,
  as a counter metric. Connection retry counters exist because the long-lived outbound
  connection drops in practice.
- **Never kill a busy worker:** scaling and rolling updates only touch idle pods; readiness
  (503-while-busy) is the mechanism that makes this enforceable by a generic orchestrator.
- **Exit-0-and-replace** as the hygiene mechanism: rather than trusting cleanup, a finished
  worker terminates and the controller replaces it with a fresh pod — state contamination
  between sessions is prevented structurally.
- **Token rotation without restarts** (`--auth-token-file` re-read on reconnect): long-lived
  fleets outlive any static credential, so rotation had to be a first-class worker feature.
- **Organizational lesson (the "why" section):** Brex, Money Forward, and Notion had each
  "diverted engineering resources towards building and maintaining their own background
  agents"; the pitch is that the control plane (orchestration, model access, UX) is the
  expensive-to-maintain part and the data plane is the part enterprises actually need to own.
  Notion: running in their own cloud "saves our team from needing to maintain multiple
  stacks." Brex: the point of self-hosting is **access to internal test suites and validation
  tools** — i.e., verification quality, not just compliance.

## 5. Transfer analysis for OUR substrate

Context: we are enterprise-internal, we own *both* planes, our semantic layer (pre-code gate,
park states, adversarial review, tiered merge) is frozen, and our current substrate is one
Hetzner VM with host processes, per-worker git worktrees, and one detachable volume holding
registry + JSONL session logs.

1. **STEAL — outbound-only worker connection.** Workers dial the control plane over
   long-lived HTTPS; no inbound ports on worker hosts, ever. This is the single most
   transferable decision: it makes worker hosts fungible across networks/clouds/on-prem,
   removes VPN/firewall coordination from scaling, and means adding a host = running one
   command with a token. Our current file-registry-on-shared-volume model inverts this
   (the dispatcher must reach into hosts); at multi-host we should flip to workers
   registering themselves outbound with a central dispatcher.

2. **STEAL — warm pool with `readyReplicas` semantics + one-session-per-worker claim.**
   Desired state counts *idle* workers, not total; a claim removes a worker from the ready
   set and the controller backfills. At hundreds–thousands of runs/hour, cold-starting an
   environment per ticket is the latency killer (their companion post exists precisely
   because env setup is the bottleneck; 70% cached-build savings). Pre-warmed workers with
   the repo already cloned, claimed at dispatch, is the right shape for our implementer
   *and* reviewer fleets — with separate pools per species (labels make that trivial).

3. **STEAL — readiness-as-claim + never-terminate-busy + exit-0-and-replace.**
   `/readyz` 503 while busy lets any generic orchestrator (Kubernetes or our own) do
   scale-down and rolling upgrades without killing in-flight ticket runs; finished workers
   exit and are replaced fresh, so no cross-ticket contamination. This is directly consonant
   with our doctrine (compute disposable) and gives it an enforcement mechanism.

4. **STEAL — label-based routing with reserved system labels.** `repo=` auto-derived (not
   settable — prevents spoofing/misrouting), `pool=` for named fleets, free-form labels for
   team/env. This is exactly the multi-team/multi-repo isolation shape our brief asks for:
   one control plane, per-team pools, non-adversarial tenants. Also steal the *policy toggle*
   idea (their Allow/Require switch): a per-org "require pool X" rule that dispatch enforces.

5. **STEAL — fleet API as the autoscaling contract.** `totalConnected`/`inUse` summary +
   per-worker status list, deliberately minimal, so autoscaling can be built on *any*
   infrastructure (their EC2/ECS/EKS trio proves the API is the portable layer, not the
   operator). Our reference architecture should define the same two numbers per pool as its
   scaling contract and treat Kubernetes as one optional consumer.

6. **STEAL — session-end reason taxonomy + worker Prometheus metrics.** Our daemon registry
   currently knows (host, pid, session); it does not classify *why* runs end. Adopting their
   six-reason counter (clean end / stream error / closed / error / timeout / aborted) per
   worker gives the board pipeline the observability to distinguish infra failures from
   agent failures — which feeds directly into whether a ticket re-dispatches or parks
   needs-human.

7. **ADAPT — the brain-in-cloud split itself.** Cursor runs the agent loop (inference,
   planning, session state) in the control plane and ships only tool calls to the worker.
   For them this is forced: the model and harness are their product. For us, workers run
   full Claude Code / Codex CLI processes — the loop lives *on* the worker. We should NOT
   move the loop into our control plane (that would mean reimplementing the harness), but we
   should adopt the *consequence* of their split: **session identity and durable state live
   centrally, the executor is stateless**. Concretely: JSONL session logs stream to central
   durable storage (object store / log service) rather than living on a per-host volume, so
   any host can resume any session. That is our existing doctrine, upgraded to multi-host.

8. **ADAPT — single-use workers with idle grace.** Their `--idle-release-timeout` keeps a
   worker alive briefly for follow-up messages. Our equivalent: after a ticket run ends,
   keep the worker claimed for a short window in case review bounces the PR straight back
   (a cheap same-worker fix-up), then release/destroy. Tune the window to our review-loop
   latency rather than copying 600 s.

9. **ADAPT — token rotation via re-read file.** Steal the mechanism (controller-managed
   short-lived tokens at a mounted path, re-read on reconnect, no restarts), but our
   credential problem is bigger than theirs: our workers hold *write* credentials to repos
   and merge authority is tiered. Their model says: worker holds only (a) a pool-join token
   and (b) whatever the environment image bakes in. We should go further — per-ticket,
   least-privilege, short-lived repo credentials minted at claim time, with merge-capable
   credentials issued only to the landing path, never to implementers.

10. **REJECT — routing artifacts through a third-party S3 bucket.** Fine for a vendor
    product; pointless for us — we own both planes, artifacts go to our own object store.
    But keep the degradation rule: artifact-store outage must never fail the run.

11. **REJECT — their data boundary as a privacy claim.** "Code never leaves your
    environment" is not true at the token level even in their own docs (file chunks read by
    the model are sent to Cursor). For us this is moot internally, but if our reference
    architecture ever uses external model APIs, we must document the same boundary honestly:
    the model context window is an egress path no data-plane design closes.

12. **REJECT — 10/user, 50/team caps as any kind of sizing guidance.** Those are their
    self-serve product limits; our target (hundreds–thousands of runs/hour/project) lives
    entirely in their "contact our team / thousands of workers" tier, about which they
    publish no architecture. The blog proves the tier exists; it does not teach us how to
    build it.

## 6. Tensions with our frozen semantics / settled doctrine

- **No semantic-layer change is forced.** Nothing here touches the pre-code gate, park
  states, adversarial review, or tiered merge; this article is purely substrate. (Loudly:
  no flag raised.)
- **Doctrine consonance with one displacement.** "Durable log is the identity of the work;
  compute disposable" — Cursor agrees on compute disposability (exit-0-and-replace) but
  locates work identity in the **control-plane session**, not in any file the worker host
  owns. Our current implementation has the doctrine right but the topology wrong for
  multi-host: identity-carrying JSONL logs live on the worker host's volume. Scale doesn't
  change the semantics; it changes *where the log must live* (central, durable, host-independent).
- **Board-as-SSOT vs their dashboard-as-SSOT:** in Cursor's world the vendor dashboard is
  the run ledger and the fleet API only reports capacity, not work items. Our board remains
  SSOT for *tickets*; the lesson is to keep the fleet/capacity ledger **separate** from the
  work ledger (they never conflate them), which endorses our board/registry split rather
  than contradicting it.
- **Chattiness cost of their split:** every tool call round-trips control plane ↔ worker
  over the WAN. They publish zero latency numbers for this. Since we keep the loop on the
  worker, we don't inherit this cost — a point in favor of NOT copying their split literally.

## 7. Open questions the article raises but does not answer

1. **Mid-session worker death:** if a claimed worker dies (host loss, OOM), does the session
   resume on a fresh worker from control-plane state, or does the run fail? The metrics
   taxonomy (`connection_timeout`, `session_error`) implies detection, but recovery behavior
   is undocumented — and it's exactly our resume-from-durable-log question.
2. **Repo freshness in warm pools:** workers start with a pre-cloned repo; who fetches/
   updates it between claim and first tool call, and how stale can a pooled worker's clone be?
3. **Tool-call round-trip latency** over the long-lived HTTPS connection — no numbers at all;
   for a build-heavy loop this determines whether the split is even viable.
4. **Isolation within the worker:** the worker executes arbitrary agent commands with the
   host's network identity ("just like an engineer or service account would") — what confines
   a prompt-injected agent on a worker that can reach internal endpoints? Egress allowlists
   exist for *managed* environments; the self-hosted docs leave this to the customer.
5. **What the thousands-of-workers control plane looks like** — scheduler throughput, claim
   latency, fairness across pools — entirely unpublished.
6. **Cost model** for keeping large warm pools of 1-CPU/2-Gi-minimum (realistically much
   larger for builds) workers idle at high `readyReplicas`.

## 8. Links followed

1. `https://cursor.com/docs/cloud-agent/self-hosted` — resolved to managed-cloud-agent docs;
   added the managed-side connectivity menu (AWS PrivateLink / Cloudflare Tunnel / Tailscale,
   per-team egress allowlists) and the pointer to the pool guide.
2. `https://cursor.com/blog/cloud-agent-development-environments` — Dockerfile-defined
   environments, build secrets scoped to build step, per-environment secret isolation,
   egress allowlists, audit log, 70%-faster cached builds.
3. `https://cursor.com/docs/cloud-agent/self-hosted-guides/pool.md` — **404** (moved).
4. `https://cursor.com/docs/cloud-agent/self-hosted.md` — **404**.
5. `https://cursor.com/docs/cloud-agent/self-hosted-k8s` — the operator: Helm chart,
   `WorkerDeployment`/`readyReplicas`, token mount + rotation, health endpoints,
   never-terminate-busy, outbound endpoint list, 1 CPU/2Gi minimum.
6. `https://docs.anyweb.dev/docs/cloud-agent/self-hosted-pool` (mirror of Cursor's
   self-hosted pool guide; canonical page 404'd) — the richest source: exact data-flow
   boundary (file chunks to Cursor, artifacts to S3), pool/claim semantics, labels, fleet
   management API, metrics + session-end taxonomy, failure table, 10/50 caps, CLI reference,
   MCP stdio-vs-HTTP routing.
   Plus one WebSearch to locate the moved docs (surfaced `cursor/cookbook` on GitHub with
   EC2/ECS/EKS reference deployments).
