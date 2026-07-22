# Deep-read report — Cursor, "Development environments for your cloud agents" (May 13, 2026)

Reader lens: environment spec / reproducibility for agent sandboxes at scale (see research-brief.md).
The announcement itself is thin; most engineering substance below comes from the in-content
links it cites (cloud-agent setup docs, the self-hosted cloud agents post, the automations post)
plus Cursor's companion post "What we've learned building cloud agents", surfaced while grounding
claims. Each source is attributed inline.

## 1. Thesis in 3 sentences

Cloud agents are only as useful as the development environment they run in: an agent that
cannot run tests, reach internal services, or hold credentials "cannot close the loop on its
work." Cursor's answer is environment-as-code — a per-repo (or multi-repo) Dockerfile +
`environment.json` spec, layered with snapshot caching, agent-led authoring of the spec itself,
and enterprise governance (versioning, rollback, audit, per-environment egress and secrets).
The direction of travel, stated explicitly, is environments that "evolve autonomously as your
codebase evolves" — environment drift is named as the unsolved problem.

## 2. Mechanisms & architecture

### 2.1 Environment specification (docs/cloud-agent/setup)

- Spec lives **in the repo** at `.cursor/environment.json`, fields:
  - `build.dockerfile` — relative path to a `.cursor/Dockerfile` (system deps, compilers,
    debuggers). Rule: "Do not COPY the full project; Cursor manages the workspace and checks
    out the correct commit" — the image is toolchain-only, source checkout is the platform's job.
  - `build.context` — defaults to `.cursor`; can reference repo root.
  - `install` — dependency setup command, **must be idempotent** (e.g. `pnpm install`).
  - `start` — post-install startup (e.g. `sudo service docker start`).
  - `terminals` — named tmux sessions for long-running app processes the agent can inspect.
  - `snapshot` — a VM snapshot ID to boot from instead of rebuilding.
- **Resolution order** when an agent starts: (1) `.cursor/environment.json` in the repo,
  (2) personal saved environment, (3) team saved environment — "predictable defaults at the
  team level while still letting individual users override."
- Base machines are Ubuntu/Debian Linux VMs; "each agent gets its own dedicated Linux VM with
  a full terminal, browser, and desktop." Default VM has "limited memory and CPU"; Enterprise
  can request custom resources (exact defaults unpublished).
- Docker-in-Docker supported (recommended: `fuse-overlayfs` storage driver, `iptables-legacy`,
  ubuntu user in docker group).
- Repo-level `AGENTS.md` with a "Cursor Cloud specific instructions" section steers the agent
  to task-appropriate commands and away from expensive operations in `install`.

### 2.2 Caching and snapshots (the reproducibility/latency machinery)

- **Layer caching** on Dockerfile builds: only changed layers rebuild; "Builds that hit the
  cache run 70% faster" (blog).
- **Automatic install checkpoint**: if `install` takes more than a few seconds, "Cursor will
  take an internal checkpoint snapshot and will attempt to start future cloud agents from this
  checkpoint." Idempotent install commands then do incremental work on the cached state.
  Caching is explicitly "best effort" — infrequently used repos boot slower.
- **User-saveable VM snapshots**: after an agent-driven setup session "you can save a snapshot
  of its virtual machine" and pin it via the `snapshot` field. Snapshots expire after **90 days
  of inactivity**; each start/resume extends expiry by 90 days (docs/community sources).
- **Graceful degradation**: "If your environment configuration fails, Cursor will default to a
  base image with clear warning signs so that your cloud agents can keep running instead of
  immediately failing." Status surfaces as "Environment ready (with warnings)"; the update
  command still runs during fallback so the env can self-recover.
- Companion lessons post lists the underlying plumbing they had to build: "Methods to
  efficiently hibernate and resume agent VMs between messages" and "Pipelines to quickly and
  durably checkpoint, restore, and fork VM images."

### 2.3 Multi-repo environments

- One environment can include multiple repositories: "Cursor clones each selected repo into
  the agent machine"; the env (and its scoped secrets) is reused across sessions. Built on
  multi-root workspaces (changelog 04-24-26: "a single agent session can now target a reusable
  workspace made of multiple folders"). Motivation: enterprise work "spans multiple codebases";
  an agent confined to one repo "can't reason across all the required context."

### 2.4 Secrets and credentials

- Secrets configured in a dashboard, injected as environment variables, **scoped per
  environment** — "secrets configured for one environment aren't accessible from any other."
- **Build secrets** (for private package registries) are "scoped to the build step and aren't
  passed to the running agent's environment."
- **Short-lived cloud credentials**: agents assume AWS IAM roles via
  `CURSOR_AWS_ASSUME_IAM_ROLE_ARN`; STS credentials "expire after 1 hour" and Cursor refreshes
  them when "missing, invalid, or within 15 minutes of expiration."
- TOTP 2FA supported in-sandbox (`oathtool --totp -b "$TOTP_SECRET"`).
- Private-network access via Cloudflare Tunnel (native) or Tailscale in userspace-networking
  mode.

### 2.5 Governance

- Every environment has a **version history** with review and rollback; rollback permission
  can be restricted to admins. An **audit log** captures every action on environments.
- **Per-environment egress allowlists**: one environment can be locked to an allowlist while
  another stays permissive.

### 2.6 Agent-led environment setup

- Cursor authors the Dockerfile itself: "inspect your repos, figure out the tools and
  dependencies required, and produce a configuration you can edit and version" — asking
  questions, flagging missing credentials, validating the result. Private beta for Enterprise.
- Agents are shown which environment **version** they are running in.

### 2.7 Fleet architecture (self-hosted cloud agents post, Mar 25, 2026)

- **Control plane / data plane split**: Cursor's cloud keeps "inference and planning" +
  "orchestration, model access, and the user experience"; customer infrastructure runs the
  workers that execute tool calls, so "code, secrets, and build artifacts remain entirely
  on-premises."
- Workers **connect outbound via HTTPS** — "no inbound ports, firewall changes, or VPN tunnels
  required." One command bootstraps a worker: `agent worker start`. Each agent session gets a
  dedicated worker; workers are "long-lived or single-use."
- Scaling: a **Helm chart and Kubernetes operator**; you declare a `WorkerDeployment` resource
  and "the controller handles scaling, rolling updates, and lifecycle management." Non-K8s
  users get a **fleet management API** for utilization monitoring and custom autoscaling.

### 2.8 State-layer doctrine (cloud-agent lessons post)

- "We've found it valuable to keep the agent loop, the machine state, and the conversation
  state as decoupled components."
- Conversation state: an "efficient append-only storage mechanism that streams conversation
  updates out to web and desktop clients."
- Orchestration runs on **Temporal**: "more than 50 million actions per day across more than
  7 million unique workflows."
- Workflow shape: "We've moved from 'eternal' agent workflows to multiple shorter ones that
  exit after completing a single task."
- Harness philosophy: "As models got smarter, we started moving logic out of the harness and
  into tools the agent controls"; cloud prompts push autonomy "because the cost of blocking is
  much higher."

### 2.9 Automations (trigger layer, Mar 5, 2026 post)

- Triggers: schedules/cron, Slack messages, new Linear issues, merged GitHub PRs, PagerDuty
  incidents, custom webhooks. On trigger, "the automated agent spins up a cloud sandbox,
  follows your instructions using the MCPs and models you've configured, and verifies its own
  output." Agents get "a memory tool that lets them learn from past runs."

## 3. Numbers (exact quotes)

| Figure | Source |
|---|---|
| "Builds that hit the cache run 70% faster" | env blog, May 13 2026 |
| STS credentials "expire after 1 hour"; refreshed "within 15 minutes of expiration" | setup docs |
| Snapshots expire after 90 days of inactivity; each use extends 90 days | docs/community |
| "Temporal handles more than 50 million actions per day across more than 7 million unique workflows" | lessons post |
| "more than 40% of our PRs come from cloud agents, and growing" | lessons post |
| Early beta "often operated at one 9 of reliability" | lessons post |
| Bugbot "triggered thousands of times a day, and has caught millions of bugs" | automations post |
| Money Forward: "nearly 1,000 engineers to create pull requests directly from Slack" | self-hosted post |
| Announcement date May 13, 2026; self-hosted Mar 25, 2026; automations Mar 5, 2026; multi-root workspaces changelog Apr 24, 2026 | page metadata |

Not published anywhere found: default VM CPU/memory, per-agent cost, concurrency limits,
cold-start latency, snapshot storage technology.

## 4. Failure modes & operational lessons they report

1. **Reliability started at "one 9"** — early cloud agents were fragile against "inference
   provider outages, pods needing to be replaced, and EC2 nodes going down." Their cure was
   the decoupling doctrine (loop / machine state / conversation state as separate components)
   plus Temporal-backed durable workflows.
2. **Eternal workflows don't survive** — long-lived agent workflows were replaced by "multiple
   shorter ones that exit after completing a single task." Task-scoped process lifetimes are a
   reliability primitive, not just an ergonomics choice.
3. **Environment build failure must not kill the run** — the fallback-to-base-image-with-
   warnings behavior exists because hard-failing on env build was worse than running degraded.
   They surface the degradation loudly ("clear warning signs", "ready (with warnings)").
4. **Cache is best-effort, not contract** — snapshots expire, infrequently used repos are slow;
   `install` idempotency is the invariant that makes cache misses safe.
5. **Environment drift is the standing wound** — "environments are configured at a point in
   time and rebuilt when they fall out of sync with the codebase"; autonomous env evolution is
   the stated roadmap, i.e. today humans (or the private-beta agent) re-sync manually.
6. **Environment quality dominates output quality** — "the single biggest factor in cloud
   agent output quality is ensuring it has a full development environment." Verification
   ability (tests, services, browser) is the point of the sandbox, not a nicety.

## 5. Transfer analysis for OUR substrate

- **STEAL — env spec in-repo, image = toolchain only.** `.cursor/environment.json` +
  Dockerfile with "don't COPY the project; platform checks out the commit" is exactly the
  contract we need: the environment is versioned with the code it serves, the substrate owns
  checkout. Our workers currently inherit one host's mutable state; at hundreds of runs/hour
  across teams that is untenable. Adopt the same three fields (build / install / start) and
  the repo→team resolution order.
- **STEAL — post-install checkpoint snapshots keyed on idempotent install.** The
  build-cache + auto-checkpoint-after-install + resume-from-snapshot ladder is the only
  credible answer to cold-start at our target rate (hundreds–thousands of worker runs/hour
  per project would otherwise mean hundreds of `npm ci`/hour per repo). The 90-day-inactivity
  expiry model (use extends life) is a sensible GC policy to copy.
- **STEAL — outbound-only workers + declarative fleet.** `agent worker start` with
  outbound-HTTPS-only, plus a K8s operator consuming a `WorkerDeployment` CRD, is the direct
  replacement for our file-based (host, pid, session) daemon registry. Worker identity moves
  from pidfiles to the orchestrator; registry becomes derived state, not SSOT — consistent
  with our doctrine that the board + durable log are the identity of work.
- **ADAPT — Temporal (or equivalent durable-workflow engine) for dispatch only.** Their 50M
  actions/day proves the pattern at 100x our scale. But keep it strictly as the dispatch/retry
  spine: our SSOT is the board and the session log. Do not let workflow-engine state become a
  second source of truth about ticket state (see Tensions).
- **ADAPT — fallback-to-base-image.** Degrade-don't-fail is right for their interactive
  product; for our autonomous pipeline a worker silently running in a degraded env can produce
  a plausible-but-untested PR. Adapt: on env-build failure, boot the fallback env but have the
  worker's pre-code gate treat "environment unverified" as gate-relevant input — verify the
  test loop actually runs before building; park the ticket (needs-human) if it doesn't. This
  reuses the frozen semantic layer rather than adding a new state.
- **ADAPT — per-environment scoped secrets + build secrets + STS-style short-lived creds.**
  For enterprise-internal multi-team isolation, environment-scoped secrets and per-env egress
  allowlists give us team/repo isolation without adversarial-tenant machinery — matching our
  "isolation matters, tenants not adversarial" posture. Prefer role-assumption with ~1h expiry
  over long-lived PATs for git/registry access.
- **ADAPT — agent-led environment authoring as a spike-lane ticket type.** Cursor's
  "inspect repos, produce a Dockerfile you can edit and version" is our spike lane wearing a
  different hat: an exploration ticket whose deliverable is an environment spec PR, which then
  flows through normal adversarial review. Also adopt their roadmap item proactively: when a
  worker hits env breakage caused by codebase drift, it should file an env-update ticket.
- **ADAPT — multi-repo environments.** Real enterprise need (their strongest customer quote is
  about exactly this). Constrains our ticket-store choice: the ticket schema must allow a
  ticket to declare an environment scope spanning repos — a point for Linear (org-level
  tickets) over GitHub issues (repo-bound). Environment defined per ticket-scope, cloned repos
  side by side in one workspace.
- **REJECT — control plane in someone else's cloud.** Their split (planning/inference in
  Cursor cloud, execution on-prem) is a product-trust boundary we don't have; we're
  enterprise-internal and should run both planes inside the enterprise. Keep the *shape*
  (planes decoupled, workers dumb and outbound-only) without the vendor boundary.
- **REJECT — dashboard-managed personal environment overrides as a default.** Personal env
  overrides make sense for interactive IDE users; for an autonomous fleet they are a
  reproducibility leak. Repo spec → team default only; no per-worker snowflakes.

## 6. Tensions with our frozen semantics / settled doctrine

- **Doctrine confirmed, not contradicted.** "Keep the agent loop, the machine state, and the
  conversation state as decoupled components" + append-only conversation storage + short
  task-scoped workflows is our "durable log is the identity of the work; compute is
  disposable" doctrine, independently converged on at 100x scale. Strong external validation.
- **One real tension — where does resumable identity live?** Cursor puts significant identity
  into *machine state* (hibernate/resume/fork VM images between messages): the VM snapshot,
  not just the log, is what makes an agent resumable cheaply. Our doctrine says the JSONL log
  alone identifies the work and any fresh process can resume. At hundreds of runs/hour,
  log-replay-only resume may be too slow/expensive, and we'll be pulled toward VM checkpoints
  as a *performance* identity layer. Resolution: keep snapshots strictly as cache (Cursor
  itself treats them as "best effort" and expirable) — a deleted snapshot must never lose
  work, only warm-start time. This preserves the doctrine but must be stated as an explicit
  invariant in the substrate spec, or snapshot state will quietly become load-bearing.
- **Second, smaller tension — Temporal-style engines want to own state.** A durable-workflow
  engine keeps authoritative execution state internally; naive adoption makes the workflow
  history a competing SSOT against the board. Constrain: workflow = dispatch + retry only;
  every semantically meaningful transition is written to the board, and the board wins on
  conflict.
- **No scale-forced semantic-layer change found.** Nothing in these sources pressures the
  pre-code gate, park states, adversarial review, or tiered merge authority. Closest call:
  degraded-environment fallback wants a new park state; it doesn't need one (route through
  the existing gate / needs-human, per §5).

## 7. Open questions the article raises but does not answer

1. What is the VM/snapshot technology (Firecracker? CoW block layers?) and the actual
   cold-start / snapshot-resume latency? "70% faster" is relative to an unstated baseline.
2. Default VM CPU/memory and per-team concurrency limits — unpublished; so is cost per
   agent-hour, which drives our warm-pool-vs-on-demand economics.
3. How is environment drift *detected*? "Rebuilt when they fall out of sync" — by what signal?
   Their autonomous-evolution roadmap implies they don't have a good answer yet either.
4. Multi-repo atomicity: when one logical change spans repos, how are the resulting multiple
   PRs coordinated/merged? (Directly relevant to our tiered merge authority at cross-repo
   scope — the article is silent.)
5. Scheduling/bin-packing of agent VMs onto hosts, and what happens to in-flight sessions when
   an EC2 node dies mid-task (they name the failure, not the recovery mechanics).
6. How the environment version an agent ran in is recorded against its output — is env-version
   part of the PR's provenance? (We should make it part of ours regardless.)

## 8. Links followed

1. https://cursor.com/docs/cloud-agent/setup — the real spec: environment.json fields,
   resolution order, snapshot/checkpoint mechanics, secrets/STS, DinD, networking.
2. https://cursor.com/blog/self-hosted-cloud-agents — control/data-plane split, outbound-only
   workers, `agent worker start`, K8s operator + `WorkerDeployment`, fleet API, Money Forward.
3. https://cursor.com/changelog/04-24-26#multi-root-workspaces-in-agents-window — confirms
   multi-repo = multi-root workspace foundation; no implementation detail.
4. https://cursor.com/blog/automations — trigger catalog (cron/Slack/Linear/PR/PagerDuty/
   webhooks), per-run sandbox spin-up, cross-run memory tool, Bugbot scale.
5. https://cursor.com/blog/cloud-agent-lessons — (surfaced via WebSearch) the failure-mode
   gold: one-9 reliability, decoupling doctrine, Temporal 50M actions/day, short workflows,
   VM hibernate/checkpoint/fork, 40% of PRs.
   Plus one WebSearch grounding snapshot expiry (90-day inactivity) and confirming default VM
   specs are unpublished.
