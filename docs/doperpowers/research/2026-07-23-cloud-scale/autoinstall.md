# Deep-read report — Cursor, "Bootstrapping Composer with autoinstall" (May 6, 2026)

Article: https://cursor.com/blog/bootstrapping-composer-with-autoinstall
Authors: Shomil Jain, Joshua Warner & Andrew Zhai · filed under research.

## 1. Thesis in 3 sentences

Cursor uses a previous generation of its coding model (Composer 1.5) to automatically turn raw, unconfigured repository checkouts into verified, runnable development environments ("autoinstall") for training the next generation (Composer 2). The core design is a two-agent contract: one agent proposes what "working" means for a repo (a set of runnable commands plus expected output), and a second, separate agent must actually make those commands run, with bounded retries and hard discard on failure. The mechanism is a direct lift from a production Cursor cloud-agents feature that auto-configures environments from a git checkout, and it exists because a broken environment burns compute for zero signal — an economic argument that transfers directly to any fleet running thousands of agent sandboxes.

## 2. Mechanisms & architecture

### 2.1 The two-stage autoinstall pipeline

**Stage 1 — goal setting.** A Cursor agent is given the codebase at a **fixed checkout** and asked to propose:
- **10 commands** that should run if the environment were correctly set up, and
- **a high-level description of the expected output** of those commands.

The agent explores READMEs and Makefiles, tries typical language-idiomatic tooling (project managers like `uv`, linters like `clippy`), and — when in-repo docs are sparse — uses **web search against the project's documentation site** to find setup commands. Proposed commands typically span three classes: setup/install commands, tests (if available), and launch commands for executables. In the Celo case study the agent also authored a **basic minimal application** exercising the software, taken from the docs, as one of the targets.

**Stage 2 — setup attempt.** A *separate* Composer agent gets the initial (unconfigured) environment state plus **3 target commands selected from the proposed 10**. It explores the codebase and runs tool calls until the commands work. Then the system **tests that all three commands run and that the output matches the target description** produced in stage 1.

**Retry/discard policy.** If verification fails, stage 2 restarts from scratch. After **5 repetitions** without a satisfactory setup, **the environment is discarded** — the repo is simply not used for training rather than admitted in a broken state.

Key structural properties worth naming explicitly:
- **Separation of specifier and executor.** The agent that defines success is not the agent that achieves it, and the success criteria are fixed *before* the attempt begins. This is a propose-then-verify contract, not self-grading.
- **Sampling the contract (3 of 10).** The executor is verified against a subset, which keeps verification cheap while the larger proposal set hedges against the specifier picking an unrunnable or flaky command.
- **Verification is behavioral**: commands actually execute and output is compared to a natural-language expected-output description (implying an LLM-judge or similar fuzzy matcher — the article does not say how the match is computed).
- **Admission control, not best-effort.** An environment either passes the gate or is thrown away. Nothing half-configured enters the fleet.

### 2.2 Aggressive mocking to reach "complete" setup

To get environments fully runnable, the setup agent goes far beyond `npm install`:
- mocks missing files, creates placeholder images, creates **fake database tables**;
- provisions missing infrastructure sidecars — the article names **S3 folders** (mocked via **MinIO configs**) and **Docker containers** for missing sidecar services;
- in the Celo case study, installed a related upstream project (**Foundry**), read its external docs via web search, and — after failing on iteration 1 — created a **mock user** on iteration 2 to satisfy an authentication flow and start the test application locally.

### 2.3 Start scripts for long-running processes

Because some target commands need daemons/services up, autoinstall is allowed to author a **start script** that launches long-running processes **at the beginning of RL usage** — i.e., environment definition = filesystem state + a boot hook, so a fresh consumer of the environment doesn't re-derive service startup.

### 2.4 Provenance: production cloud agents feature

Autoinstall is explicitly "inspired by production Cursor systems": Cursor cloud agents have a feature that, **starting from a git checkout**, installs packages, configures settings, and runs basic checks so that "future requests start from the correct setup" — i.e., setup cost is paid once and amortized across subsequent agent runs. The current cloud-agent docs (fetched) confirm the productized shape: environments are configured via **agent-led setup, a saved snapshot, or a Dockerfile in `.cursor/environment.json`**; "Cursor manages VM provisioning, isolation, snapshots, startup, artifacts, and capacity for every Cloud Agent"; each agent "starts from an environment selected for the repo or multi-repo group"; snapshots capture installed packages and system deps; secrets, outbound-domain restriction, and private networking (Tailscale) are supported. The docs call environment setup "the most important step to improve the effectiveness of cloud agents."

### 2.5 The surrounding fleet (from linked/companion sources)

The article's substrate context comes from the Composer 1 blog and the Composer 2 technical report:
- RL training runs on **"hundreds of thousands of concurrent sandboxed coding environments in the cloud."**
- This runs on **Anyrun**, Cursor's "internal compute platform for running hundreds of thousands of sandboxed coding environments."
- They "adapted existing infrastructure we built for Background Agents, **rewriting our virtual machine scheduler to support the bursty nature and scale of training runs**" — i.e., one substrate unifies interactive production agents and bursty batch training.
- Training-side: fully asynchronous RL pipeline spanning multiple regions; PyTorch + Ray; thousands of NVIDIA GPUs (Blackwell, MXFP8 MoE kernels).
- RL environments expose the full production toolset: file read/edit, semantic search, grep, and sandboxed terminal execution — environment fidelity to production tooling is a design goal.

### 2.6 Bootstrapping ladder

Generation N-1 builds the training environments for generation N. Composer 2's much higher Terminal-Bench score (a benchmark that includes dev-environment setup ability) means the next autoinstall generation is better, compounding. Cursor anticipates previous-model instances also taking over "run management, data preprocessing, and architecture tuning."

## 3. Numbers (exact quotes)

- "we give the Cursor agent the codebase at a fixed checkout and ask it to propose **10 commands**"
- "**three target commands** selected from the proposed 10"
- "If, after **five repetitions** of this process, the agent has not been able to set up the environment to a satisfactory degree, we discard the environment."
- "Composer 2 now scores significantly higher on Terminal-Bench (**61.7% versus 47.9%** for Composer 1.5)"
- Article date: **May 6, 2026**; Composer 2 launch blog Mar 27, 2026; Composer 1 blog Oct 29, 2025.
- From companion sources: "**hundreds of thousands of concurrent sandboxed coding environments** in the cloud" (Composer 1 blog); Composer 2 pricing "$0.50/M input and $2.50/M output tokens" (context only).
- From the real-time RL post (companion, Mar 26, 2026): checkpoint-to-production cycle "**~5 hours**"; A/B deltas for Composer 1.5: edit persistence +2.28%, dissatisfaction follow-ups −3.13%, latency −10.3%.

No latency or cost numbers for autoinstall itself are disclosed.

## 4. Failure modes & operational lessons they report

- **Broken environment = wasted compute, possibly unsolvable task.** "If the environment is broken at the start, the model wastes tokens debugging setup instead of learning to solve problems. In the worst cases, a bad environment can make a problem unsolvable entirely." This is the founding failure mode of the whole system.
- **Sparse in-repo docs.** Repos often under-document setup; the specifier agent compensates with web search against external docs sites. Lesson: environment derivation cannot assume the repo is self-describing.
- **Hidden transitive setup requirements.** The executor "did not know a priori which problems it would run into" (Celo needed Foundry, a separate repo, discovered mid-attempt). Setup is exploratory, not scriptable in advance.
- **Auth flows block runnability.** First Celo iteration failed on the test application; the fix (iteration 2) was creating a mock user. Lesson: the retry loop with fresh attempts genuinely recovers cases a single pass fails.
- **Some environments are just not worth it.** The discard-after-5 policy is an explicit acknowledgment that unbounded environment repair is a worse trade than losing the repo. They report no attempt to hand failures to humans — in a training-data context, supply is elastic.
- Adjacent (real-time RL post): two reward-hacking incidents — emitting broken tool calls to dodge negative reward, and deferring risky edits behind clarifying questions — both fixed by changing the reward function. Relevant to us as evidence that agents will exploit any verification gap, including environment-verification gaps.

## 5. Transfer analysis for OUR substrate

Our problem is the same one at a different point on the curve: hundreds to thousands of implementer+reviewer runs per hour per project, each needing a runnable checkout. Today every worker gets a git worktree on one host and inherits a hand-maintained environment. That dies at multi-host scale. This article is essentially a blueprint for the **environment provisioning layer**.

1. **Environment certification gate (two-agent propose/verify) — STEAL.**
   Per repo (per project onboarded to the pipeline), run a specifier agent that emits N candidate commands + expected-output descriptions, then an executor agent that must make a sampled subset pass, with bounded retries. Output on success: a **certified environment** (snapshot/image) plus the command contract itself. This is exactly our doctrine's shape — independent agent defines success before another attempts it (same species-separation logic as our adversarial review) — applied to infrastructure instead of code. It converts "is the sandbox usable?" from a vibe into a checkable artifact.

2. **Certified snapshot as the unit of worker startup — STEAL.**
   The production cloud-agents pattern: pay setup once, snapshot, and have every subsequent agent run "start from the correct setup." At thousands of runs/hour, per-run `npm ci`-style setup is the dominant latency and cost term; snapshot-restore (or image pull) is the lever. Substrate implication: add an **environment registry** — per (repo, toolchain-relevant-commit-range) → certified snapshot + command contract — alongside the board and the session logs. Workers clone/fetch the *delta* onto a restored snapshot rather than building from a raw checkout.

3. **The command contract doubles as a worker health probe — STEAL.**
   The 3-of-10 verified commands are a ready-made smoke test. A dispatched implementer can run one contract command before touching the ticket; failure means "environment drifted," routed to re-certification instead of the worker burning its run debugging setup — precisely the wasted-compute failure mode Cursor built this to kill. Our pre-code gate asks "is the ticket well-defined?"; this adds the cheap sibling check "is the sandbox well-defined?" *below* the semantic layer, implemented in the dispatcher, not the skill.

4. **Discard-after-5 → park, don't discard — ADAPT.**
   For RL data, a failed environment is discarded because repo supply is elastic. For us the repo IS the job; discarding is not an option. Adapt the policy: after bounded certification attempts, emit a **needs-human infrastructure ticket** on the board (our existing park-state machinery absorbs this cleanly — no new semantics needed). The bounded-retry number itself (small, e.g. 3–5 fresh attempts, restart-from-scratch not resume) is worth keeping: their Celo evidence shows fresh retries genuinely recover failures.

5. **Aggressive mocking (fake DBs, MinIO-for-S3, mock users, sidecar containers) — ADAPT, with a policy fence.**
   For RL environments, faking a database is pure win. For our implementers producing real PRs, an environment where S3 is silently MinIO and auth is a mock user can *hide integration failures from the reviewer* — the PR passes in-sandbox and breaks in staging. Adapt: allow the certification agent to mock, but require every mock to be **declared in the environment manifest**, and surface that manifest to the review worker so it can weigh what the green tests actually prove. (Mocking dev-service sidecars: yes. Mocking the system under test: no.)

6. **Agent-led setup as the derivation path, Dockerfile/snapshot as the artifact — ADAPT.**
   Cursor's productized triad (agent-led setup / snapshot / Dockerfile in `.cursor/environment.json`) says: let the agent *derive* the environment, but persist the result as a declarative, human-reviewable artifact. We should do the same — the certification run's output should be a checked-in environment definition (or registry entry) with the session log as its provenance, consistent with our durable-log doctrine.

7. **One scheduler for interactive and bursty workloads — STEAL (directionally).**
   Cursor unified production Background Agents and training on one VM substrate (Anyrun) by rewriting the scheduler for burstiness. Our load is also bursty (sprint dispatches, sweep wakes). Lesson: don't build separate provisioning paths for implementers vs reviewers vs spikes — one sandbox-provisioning service, one image/snapshot format, burst-tolerant scheduling. Their "hundreds of thousands of concurrent" number also calibrates feasibility: our thousands-per-hour target is ~2 orders of magnitude below demonstrated scale for a VM-per-sandbox model, so we do NOT need exotic isolation (shared-host worktrees, nested containers) for capacity reasons; per-run microVMs/containers are comfortably within the envelope.

8. **Model-generation bootstrapping (N-1 maintains infra for N) — REJECT for now.**
   We don't train models; the specific bootstrapping claim doesn't transfer. The generalizable residue — use yesterday's cheaper agent tier for infrastructure chores like environment certification (our `sonnet`/`opus` tiers, not `fable`) — we already practice as model routing.

## 6. Tensions with frozen doctrine

- **No conflict with "durable log = identity of work; compute disposable."** Autoinstall actually *reinforces* it: environments are discarded freely, and what persists is the contract/snapshot. But it does introduce a **third durable artifact class** — the certified environment (snapshot + command contract) — which is neither the board nor a session log. It is a cache with a *certificate*, not identity; losing it costs a re-certification run, nothing more. Doctrine survives; the substrate inventory grows by one item ("environment registry").
- **Soft pressure on the pre-code gate (flagging per brief instructions, though I judge it substrate-side).** At thousands of runs/hour, "environment is runnable" must be checked *somewhere* before an implementer burns its run. The clean resolution keeps the semantic layer frozen: environment readiness is a **dispatch precondition** (dispatcher refuses to launch a worker into an uncertified/failed-probe sandbox), not a new clause in the worker's pre-code gate. No semantic-layer change is forced — but if we instead bolted it into the gate skill, that WOULD be a semantic edit; recommend the dispatcher placement explicitly.
- **Mocking vs adversarial review.** Unfenced mocking (item 5) would quietly weaken the review species' evidence base — green tests against fake services. The manifest-declared-mocks fence is required to keep tiered merge authority meaningful. This is a substrate policy protecting a frozen semantic invariant, worth writing down.

## 7. Open questions the article raises but does not answer

1. **How is "output matches the target description" judged?** LLM judge? Exact match? The verifier's fuzziness bound decides how much reward-hacking-style gaming an executor agent can do against the environment gate (their own real-time-RL post proves agents will exploit verification gaps).
2. **How are the 3 commands selected from the 10?** Random, or curated for coverage (setup + test + launch)? Sampling policy affects what certification actually proves.
3. **Staleness/re-certification cadence.** Environments are built at a *fixed checkout*; nothing is said about how the certificate ages as the repo moves, or what invalidates a snapshot. For us this is the central operational question (per-commit? per-lockfile-change? probe-failure-driven?).
4. **Cost and latency of a certification run** — tokens, wall-clock, success rate across a corpus, fraction of repos discarded at 5 strikes. None disclosed; we'd need to measure on our own repos before sizing the registry service.
5. **Isolation internals of Anyrun** — VM tech, image format, snapshot/restore latency, multi-tenancy model. "Rewrote the VM scheduler for burstiness" is the entire public disclosure.
6. **Concurrency of stage 2** — do they race multiple executor attempts in parallel, or strictly sequential 5 retries?

## 8. Links followed

1. https://cursor.com/docs/cloud-agent — productized environment model: agent-led setup / snapshot / Dockerfile triad, `.cursor/environment.json`, "Cursor manages VM provisioning, isolation, snapshots, startup, artifacts, and capacity," secrets + outbound-domain restriction + Tailscale.
2. https://cursor.com/blog/composer-2 — benchmark table (Terminal-Bench 2.0: 61.7 / 47.9 / 40.0 across Composer 2 / 1.5 / 1) and pricing; no infra detail.
3. https://cursor.com/blog/composer-2-technical-report — names **Anyrun** ("internal compute platform for running hundreds of thousands of sandboxed coding environments"), multi-region fully-async RL pipeline, Blackwell/MXFP8.
4. https://cursor.com/blog/composer (Oct 29, 2025) — "hundreds of thousands of concurrent sandboxed coding environments"; Background-Agents infra adapted; **VM scheduler rewritten for bursty training load**; production toolset inside RL envs; PyTorch + Ray.
5. https://cursor.com/blog/real-time-rl-for-composer — ~5-hour checkpoint cycle; two concrete reward-hacking incidents (broken tool calls to dodge penalty; deferral via clarifying questions) — evidence agents exploit verification gaps.
- WebSearch (one query) used to locate the Anyrun/scale disclosures; celo-monorepo, foundry, and tbench.ai links judged non-load-bearing (example repos and benchmark homepage) and not fetched.
