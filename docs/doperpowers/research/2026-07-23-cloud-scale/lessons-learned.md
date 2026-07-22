# Deep-read report — Cursor, "What we've learned building cloud agents" (Josh Ma, Jun 2, 2026)

Source text: `articles/What_we’ve_learned_building_cloud_agents_Cursor.txt`
Supplementary grounding: Cursor "Continually improving our agent harness" (Apr 30, 2026), Cursor "Bootstrapping Composer with autoinstall", ZenML LLMOps database entry on Cursor+Temporal (derived from a Temporal case study / conference talk).

---

## 1. Thesis in 3 sentences

Cloud agents are not "a local agent ported to a server" — they require an **operating layer**: environment construction, durable execution, decoupled state, and enterprise IT (secrets, network policy, credentials) built around the loop. The two decisive engineering moves were (a) treating the **full development environment as the primary determinant of output quality** (its absence degrades output silently, without errors) and (b) **moving the agent loop off the VM into Temporal**, which took them from ~one nine to past two nines of reliability at 50M+ actions/day. The direction of travel is to shrink deterministic harness logic and instead give the agent tools to observe and repair its own environment ("self-healing"), because as models improve, hardcoded scaffolding becomes the bottleneck.

## 2. Mechanisms & architecture

Every concrete mechanism in the article, with enough detail to rebuild:

**2.1 Full-environment doctrine.** Local agents inherit a working dev environment for free; cloud agents must have it reconstructed. Missing pieces do not crash — they produce *subtle output-quality degradation* that gets misattributed to the model. Repeated root-cause: "the cloud agent not having the environment it needs to execute or verify its work." Infrastructure they had to build for this:
- User-facing tools for building/declaring the agent environment.
- **Hibernate/resume of agent VMs between messages** (an agent conversation is long-lived; the VM is not kept hot between turns).
- Pipelines to **checkpoint, restore, and fork VM images** quickly and durably (fork = spawn N agents from one prepared image; checkpoint = resume without re-setup).
- Tight harness/client integrations so both agents and humans can inspect and interact with the environment.
- "Enterprise IT for agents": secret redaction, network policies, credential management, controlled network access (needed for creating PRs, pulling dependencies, research).

**2.2 Durable execution via Temporal (the central architecture lesson).**
- *v1 (failed)*: work-stealing architecture — worker nodes pick up agents and "loop them to completion." Direct transplant of the local model to servers. Fragile: **~one nine of reliability** in early beta. Exposure: inference-provider outages, pod replacement, EC2 nodes dying.
- *v2*: they realized they were rebuilding retry mechanisms, cross-machine scheduling, and durability across node failures — primitives Temporal already provides — and migrated the agent loop into Temporal. Result: survives inference blips, pod hibernation/resumption, and runs spanning **days or weeks**; **past two nines**.
- *Workflow shape (learned over time)*: moved from **"eternal" agent workflows to multiple shorter workflows that exit after completing a single task** — the stated reason is that eternal workflows make **version upgrades** hard (Temporal workflows must replay deterministically against new code). Per the Temporal case study: workflows are structured as discrete **"turns"**; a follow-up user prompt uses Temporal's **signal-with-start** — signal the workflow if running, else start a new one — creating the *illusion* of an infinitely-lived agent over finite workflows.
- *Activity decomposition*: they progressively **split activities so timeouts and retries are captured per-step** — driven by async tool calls, subagents, and inference-provider outages changing assumptions. Activities restart from last successful state without replaying expensive token sequences.
- *Deployment safety (case study)*: a **CI-based workflow-history replay system** — production workflow histories are replayed against proposed code changes; any non-determinism error fails CI. Migrated ECS→Kubernetes with the Temporal K8s controller, which waits until workers can actually service activities before shifting traffic (eliminated deploy-time downtime).
- *Subagents (case study)*: child workflows that reuse the parent's agent-loop activities but **skip VM provisioning** (they attach to existing environment state).

**2.3 Three-way state decoupling.** The agent loop, the machine state, and the conversation state are separate components:
- **Agent loop** lives in Temporal, not on the VM → pod lifecycles are managed independently; an agent can run across *different kinds of pods*, including **readonly VMs** and **prewarmed VMs**; an agent may start on one machine, spawn async subagents on several, or start locally and delegate to cloud; a **subagent may outlive its parent** or run on a different pod class.
- **Conversation state** is an **append-only storage + streaming layer** separated from the workflow. Per the case study: activities write conversation history to **content-addressable storage in S3 plus Redis streams**; clients read historical data from S3 and live data from Redis — never by querying the running workflow.
- **Retry-aware streaming**: if a loop step fails *after* streaming partial output and is retried, the client detects it, **rewinds its stream**, and displays the new data. (Partial output is presumed invalid on retry; the durable record is what the retried step ultimately commits.)

**2.4 Harness shrinkage ("knowing how to get out of the way").** A ratchet, restated with each model generation:
- Early: harness double-checked the agent's work after every task, force-committed, force-pushed.
- Multi-repo: was hardcoded harness behavior → now the harness just gives the agent the repo layout plus tools for branches/PRs and lets it decide.
- CI Autofix: harness used to fetch CI job failure logs and write them to the VM → now the agent gets the **GitHub CLI** and the harness's only deterministic help is **automatically writing large outputs to files the agent can search**; the notification to the agent got much simpler.
- Remaining scaffolding is explicitly *temporary and capability-gated*: computer use has a **dedicated subagent type** with its own model routing, custom prompting, and screen recording; the VNC + Chrome belong to the *environment* (shared between parent and subagent), so the parent can also drive them directly (e.g., run a Playwright script). Kept "because models aren't quite ready," but the **agent controls when to invoke it**.
- **Prompting difference for cloud**: cloud agents are prompted to be *more autonomous* because **the cost of blocking is much higher** — locally you see the agent waiting for permission; in the cloud it could sit for hours before anyone checks.

**2.5 Self-healing environments (forward-looking).** Replace the binary "hold its hand vs. get out of the way" with **tools for the agent to understand the system around it**: report missing secrets, blocked network access, or environment blockers — then act to repair. Named path: **autoinstall** (from the Composer RL post): a two-stage pipeline where one agent proposes ~10 verification commands + expected outputs for a repo, and a second agent configures the environment until 3 selected commands run with matching outputs; environments are discarded after 5 failed iterations. In the RL context this exists because broken environments make agents "waste tokens debugging setup instead of learning to solve problems."

**2.6 (Supplementary, harness post)** — error taxonomy in the harness (unknown bug vs. invalid arguments vs. unexpected environment vs. provider failure); a focused sprint drove tool-call reliability to 2–3 nines and cut unexpected tool errors by an order of magnitude; weekly cloud-agent automations that surface new/spiking issues and file tickets (agents doing ops on the agent platform).

## 3. Numbers — quoted exactly

- "our early beta of cloud agents often operated at **one 9 of reliability**" (case study: ~"90% success rate" for the homegrown system).
- "That migration alone took us **past two 9s of reliability**" (case study: activity success "exceed[s] 99%").
- "Temporal handles **more than 50 million actions per day** across **more than 7 million unique workflows**."
- "Internally, **more than 40% of our PRs come from cloud agents**, and growing."
- "runs that stretch across **days or even weeks**."
- "take on longer tasks... often take **hours instead of minutes**."
- Launched cloud agents "**a year ago**" (≈ mid-2025); post dated **Jun 2, 2026**.
- Autoinstall post: environments discarded after **5** failed setup iterations; Terminal-Bench 61.7% (Composer 2) vs 47.9% (Composer 1.5).
- Harness post: tool reliability "at least 2 or often 3 9s"; unexpected tool-call errors down "by an order of magnitude."
- No cost figures anywhere in this article.

## 4. Failure modes & operational lessons

1. **Silent quality degradation from incomplete environments** — the flagship failure mode. No crash, no error; only degraded output, misattributed to the model. Detection required repeated manual root-causing. Lesson: environment completeness needs *verification*, not vibes (hence autoinstall's "commands + expected outputs" contract).
2. **Work-stealing loop-on-VM architecture is fragile at scale** — one nine. Killers: inference-provider outages, pod replacement, node death. Lesson: don't rebuild retries/scheduling/durability yourself; the loop must be durable independent of any machine.
3. **Eternal workflows block version upgrades** — long-lived workflow code can't be changed safely mid-flight. Lesson: short task-scoped workflows + signal-with-start to fake continuity.
4. **Coarse activities hide failures** — async tool calls, subagents, and provider outages forced splitting activities so each step carries its own timeout/retry semantics.
5. **Retried steps orphan streamed partial output** — clients must detect retry, rewind, re-render. Streaming and durable state must be reconciled explicitly.
6. **Blocking is far more expensive in the cloud** — an agent waiting for permission can sit unnoticed for hours. Prompting/protocol must bias to autonomy or to *loud, routed* escalation.
7. **Hardcoded harness logic rots as models improve** — every deterministic behavior (multi-repo handling, CI log fetching, post-task double-checking) eventually became a ceiling and was replaced by tools + agent judgment.
8. **Deploy-time downtime from traffic shifting before workers ready** (case study) — fixed with Temporal K8s controller readiness detection; non-determinism regressions caught by replaying production histories in CI.

## 5. Transfer analysis for OUR substrate

Our system: board-as-SSOT (park states, pre-code gate, adversarial review, tiered merge — frozen), workers as host processes on one VM with file-based registry, JSONL session logs as durable resume artifacts, hundreds–thousands of runs/hour/project target.

- **STEAL — Durable-execution engine for the dispatch/worker loop (Temporal or equivalent).** This is the article's strongest, best-quantified claim: loop-on-machine = one nine; loop-in-durable-engine = two-plus nines, 50M actions/day. Our file-based daemon registry keyed (host, pid, session) is exactly their v1 work-stealing shape and will hit the same wall at multi-host scale. The worker *process* stays disposable (our doctrine already says this); what changes is that retry/timeout/heartbeat/reassignment stops being our bash-and-registry code and becomes engine primitives. Directly compatible with "compute is disposable."
- **STEAL — Short task-scoped workflows, not eternal ones; signal-with-start for continuity.** Maps perfectly onto tickets: one workflow per ticket-turn (dispatch→PR or park), not one per worker lifetime. Upgradability of the pipeline code while thousands of runs are in flight is a real requirement at our target scale, and this is the known solution.
- **STEAL — Environment completeness as a *verified contract* (autoinstall pattern).** Before an implementer starts, the environment should pass N repo-specific commands with expected outputs (build, test, lint). At hundreds of runs/hour we cannot afford Cursor's failure mode: silent quality degradation across a whole fleet, misread as "the model got worse." This also gives the pre-code gate a machine-checkable environmental leg (note: the *gate itself* is frozen semantics; this adds an input to it, doesn't change it).
- **STEAL — Snapshot/fork of prepared environments; prewarmed pools.** At thousands of runs/hour/project, per-run `git clone` + dependency install is the dominant latency and cost. Checkpoint a repo's prepared image (deps installed, caches hot), fork per worker. Their hibernate/resume matters less for us (our workers are batch-shaped, not conversation-shaped), but fork-from-checkpoint is directly load-bearing.
- **ADAPT — Decoupling loop / machine / conversation state.** We already have the doctrine (durable log = identity of work; compute disposable). The adaptation: our JSONL session logs currently live *on the worker's volume* — at multi-host scale they must move to shared storage (their answer: append-only content-addressed S3 + Redis streams for live tails). Keep JSONL as the format; change where it lives and make writes append-only through an API rather than local disk. Also adopt their retry rule: partial output from a failed step is invalid; the durable record is what the retried step commits — our resume logic must tolerate replayed/duplicate tail entries (idempotent append or step-scoped truncation).
- **ADAPT — "Enterprise IT for agents": secret redaction, network policy, credential management.** They frame it as product infrastructure; for us (enterprise-internal, non-adversarial tenants) it is mostly per-team credential scoping and egress policy per repo class. Needed, but a simpler build than theirs.
- **ADAPT — Autonomy-biased prompting because blocking is expensive.** We already solved the semantic half better than they did: park states (needs-human / needs-info / interactive-preferred) are a *routed* alternative to silent blocking. The adaptation is operational: parks must emit events/notifications with SLOs, because at thousands of runs/hour a park queue nobody watches is exactly their "agent sits for hours" failure multiplied.
- **ADAPT — Readonly VMs for a worker class.** Their readonly-pod optimization maps to our review workers: reviewers need read+execute, not write+push. A readonly (or snapshot-discard) sandbox class for reviewers is cheaper, safer, and strengthens the adversarial-independence property.
- **REJECT — Shrinking the pre-code checks because "models got smarter."** Their harness-shrinkage ratchet applies to *mechanical* scaffolding (log fetching, forced commits). Our pre-code gate, adversarial review, and tiered merge are *semantic governance*, frozen by the human, and Cursor's own trajectory doesn't argue against them — they shrank means, not accountability. Do not let this article be read as license to thin the gate.
- **REJECT — Conversation-centric product plumbing (client stream rewind UX, hibernate-between-user-messages).** Driven by their interactive chat product. Our workers are ticket-batch shaped; the board and PR are the interface. We need durable logs and idempotent resume, not live-stream rewind for humans.
- **REJECT (for now) — Dedicated computer-use subagent scaffolding.** Their own framing is that it's a temporary capability crutch. Not on our critical path; if a ticket needs browser verification, that's a tool in the worker's environment, not substrate.

## 6. Tensions with our frozen semantics / settled doctrine

- **No contradiction with "durable log = identity of work; compute disposable" — but a sharpening.** Cursor's stronger claim: the durable identity should live in a *transactional execution engine* (workflow history), with the conversation log as a **byproduct written to shared storage**, not the resume mechanism itself. Our doctrine makes the JSONL log both the identity *and* the resume vehicle. At one host that's fine; at multi-host scale, resume-by-replaying-a-file-a-fresh-process-picks-up has no arbiter for "who owns this run now" — that's precisely the work-stealing architecture they measured at one nine. **Flag: scale doesn't force a semantic change, but it forces the doctrine's *implementation* to split: identity/ownership → durable-execution engine; narrative/resume-context → append-only log in shared storage.** The board remains SSOT for ticket state; the engine is SSOT for run ownership; the log is context.
- **Potential semantic-layer pressure (flagging loudly as instructed, though I judge it survivable): the park states at fleet scale.** Cursor's answer to "blocking is expensive" was to prompt agents to *not stop*. Ours is to stop *into a named state*. At hundreds–thousands of runs/hour, if even a few percent of runs park, the park queues become a human-throughput bottleneck — the semantic layer holds only if the substrate adds park-queue routing, batching, and SLOs. That's substrate work, not a redesign of the states — but it's the point where scale pushes hardest on frozen semantics.
- **Harness-shrinkage vs. constraint-minimization doctrine: agreement, not tension.** Their trajectory (remove deterministic double-checking, hand judgment to the agent, keep only capability-gated scaffolding) independently confirms our golden rule — hard gates only for validated failure states. Their one retained hard scaffold (computer-use subagent) is justified by an observed capability gap, exactly our standard.
- **"More than 40% of our PRs come from cloud agents"** validates the premise that review capacity, not implementation capacity, becomes the constraint — supporting our independent-adversarial-review species as the thing to scale hardest, though the article itself says nothing about how they review that volume.

## 7. Open questions the article raises but does not answer

1. **Cost.** Zero economics: per-run VM cost, hibernate vs. keep-warm tradeoff, Temporal Cloud bill at 50M actions/day. (Their "Agent swarms and the new model economics" post likely covers some — sibling reader's territory.)
2. **Sandbox/isolation tech.** "Dedicated VMs" — but Firecracker? full VMs? gVisor? How fast is checkpoint/restore/fork, and what does "durably" mean for image pipelines?
3. **Who reviews the 40%?** No mention of review architecture, merge authority, or quality gates on agent PRs — the entire back half of our semantic layer is absent from their account.
4. **Scheduling/fairness.** How is work admitted and prioritized across users/repos at 7M workflows/day? Queue design, backpressure, and starvation are unaddressed (Temporal task queues presumably, but policy is unstated).
5. **Environment-completeness detection in production** (as opposed to RL training): is autoinstall actually wired into the product's pre-run path, or still research?
6. **Subagent-outlives-parent semantics**: who owns the result, and how does it rejoin the parent's durable record?
7. **What "one 9" cost them concretely** — no incident narratives, MTTR, or data on user-visible failures pre-migration.

## 8. Links followed

1. https://cursor.com/blog/continually-improving-agent-harness — related post (not in-content, but load-bearing for section "getting out of the way"): harness internals — error taxonomy, model-specific edit formats, dynamic context fetching, tool reliability driven to 2–3 nines, guardrail removal as models improved.
2. https://cursor.com/blog/bootstrapping-composer-with-autoinstall — the article's only true in-content citation: the two-stage autoinstall pipeline (propose verification commands → configure until 3 commands match expected output; discard after 5 failed iterations) grounding the "self-healing environments" section.
3. https://www.zenml.io/llmops-database/building-and-operating-agentic-ai-coding-products-at-scale-with-temporal — found via WebSearch; richest supplement: turn-scoped workflows, signal-with-start, child workflows skipping VM provisioning, S3+Redis content-addressed conversation storage, CI replay of production workflow histories, ECS→K8s with Temporal controller, 90%→99%+ activity success.
4. WebSearch grounding of the 50M actions/7M workflows/40%-of-PRs figures — corroborated by the ZenML entry and third-party commentary; consistent, no contradiction found.
