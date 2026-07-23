# Managed Agents as the A0 worker substrate — viability research

> **Date:** 2026-07-23. **Scenario:** 10–20 person AI-native startup, zero-ops
> posture, $1–5k/month infra ex-tokens. **Anchor A0:** ~50–200 concurrent runs,
> ~250–1,000 starts/hour (~5,000 runs/day), ~12 min mean run. Workers today:
> Claude Code harness sessions loaded with the doperpowers skills plugin,
> talking to a ticket-board API, doing git work in a sandbox.
>
> **Question:** can Anthropic's Managed Agents (or any comparable managed
> brain+hands runtime) BE the worker substrate at A0 — replacing self-managed
> sandboxes entirely — given the hard requirement that OUR harness/protocol
> (skills + board client + git flow) must run, not the vendor's agent product?
>
> **Method note:** July-2026 doc state, gathered via live fetches of
> platform.claude.com / developers.openai.com / cursor.com docs plus a
> dedicated docs-research agent. Every load-bearing claim is tagged
> **[documented]**, **[vendor-claimed]** (third-party or marketing, not in
> official docs), or **[absent]** (undocumented — itself a finding).

---

## 0. Verdict up front

**Not-viable as a drop-in substrate; viable-with-caveats only as a protocol
port — which is a rebuild, not a substrate swap.**

The decisive structural fact: **nobody in the market sells "your harness on
our runtime."** Every managed brain+hands product — Anthropic Managed Agents,
OpenAI Codex cloud, Cursor Cloud Agents, Devin — couples the managed runtime
to the vendor's own agent loop. Managed Agents is explicitly "a pre-built,
configurable agent harness"; you configure an Agent (model + system prompt +
tools + MCP + skills), you do not bring a loop. Our worker IS a harness
(Claude Code + doperpowers skills + board scripts + git flow); a substrate
that replaces the harness replaces the worker.

What keeps it at "viable-with-caveats" rather than flat rejection: Managed
Agents is the only offering where a meaningful fraction of our protocol could
be *ported* rather than abandoned — custom SKILL.md bundles upload and land in
the sandbox **[documented]**, the board client fits either sandbox-side bash +
network egress or MCP/custom tools **[documented]**, and the price at A0
(~$2.4k/mo runtime at the officially documented $0.08/session-hour) fits the
budget. But the port crosses a beta API with undocumented
concurrency caps, no ZDR/HIPAA, session data on Anthropic's control plane, an
unstated harness identity whose skill-triggering behavior our tuned skills
were never evaluated against, and it forecloses the mixed Claude+Codex review
fleet. Details and the flip conditions in §7.

One offering complicates the clean "nobody sells your-harness-on-our-runtime"
line: **Claude Code on the web** runs actual Claude Code on Anthropic-managed
VMs and installs repo-declared plugins from a marketplace at session start —
our harness, our skills, verbatim. What it lacks is a fleet contract: dispatch
is an experimental per-routine webhook with unquantified per-plan daily
allowances, billed against claude.ai subscription usage, in research preview.
The architecturally right substrate exists; it is not sold at A0 volume. §1.6c.

## 1. Anthropic Managed Agents — July 2026 state

Sources: [overview](https://platform.claude.com/docs/en/managed-agents/overview),
[skills](https://platform.claude.com/docs/en/managed-agents/skills),
[tools](https://platform.claude.com/docs/en/managed-agents/tools),
[sessions](https://platform.claude.com/docs/en/managed-agents/sessions),
[environments](https://platform.claude.com/docs/en/managed-agents/environments),
[cloud sandbox reference](https://platform.claude.com/docs/en/managed-agents/cloud-sandboxes-reference),
[self-hosted sandboxes](https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes),
[reference](https://platform.claude.com/docs/en/managed-agents/reference),
[API and data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention).

### 1.1 What runs

- **A proprietary Anthropic harness** — not Claude Code, not the Agent SDK.
  Overview: "Pre-built, configurable agent harness that runs in managed
  infrastructure … Instead of building your own agent loop, tool execution,
  and runtime, you get a fully managed environment." **[documented]** Whether
  it shares code with Claude Code is unstated **[absent]** — and irrelevant to
  us either way: the customer-visible contract is configuration, not the loop.
- **No bring-your-own-harness.** The customer configures Agent = model +
  system prompt + tools + MCP servers + skills; the loop, compaction, prompt
  caching, and tool routing are Anthropic's. **[documented — by omission of
  any harness-customization surface]**
- Beta: all endpoints require header `managed-agents-2026-04-01`; public beta
  since 2026-04-08; still not GA as of July 2026. **[documented]**
- Also available on Claude Platform on AWS "with some differences in feature
  availability and session behavior." **[documented, differences unenumerated]**

### 1.2 Skills, plugins, custom tools

- **Custom skills: yes.** SKILL.md + supporting files uploaded as a zip via
  the Skills API (`POST /v1/skills` → versioned `skill_*` id), referenced on
  the agent config, downloaded into the sandbox at `/workspace/skills/<name>/`.
  **[documented]** Whether skill auto-triggering matches Claude Code's
  behavior (description-driven invocation, the thing doperpowers skills are
  tuned against) is unstated **[absent]**.
- **Claude Code plugins: no.** Nothing in the Managed Agents docs mentions
  plugins, plugin manifests, hooks, or slash commands. **[absent — this is a
  finding: the plugin layer has no bridge.]** For this fork the gap is
  narrower than for stock superpowers (we removed the SessionStart bootstrap;
  skills load from `skills/` and are invoked via the Skill tool), but the
  Skill-tool invocation surface itself is a Claude Code feature with no
  documented Managed Agents equivalent.
- **Custom tools: yes, two paths.** (a) Client-side custom tools: agent emits
  `agent.custom_tool_use` on the SSE stream, your application executes and
  returns `user.custom_tool_result` — the board API client fits here with the
  board credential held entirely outside the sandbox. (b) MCP servers (remote
  HTTP; or wrapped locally in self-hosted environments). **[documented]**
  (c) Or plainly: sandbox bash + network egress to the board API — but then
  the board token lives in the sandbox with generated code, exactly the
  co-residency their own architecture argues against.

### 1.3 Sandbox properties (Anthropic-hosted)

- Ubuntu 22.04 LTS, x86_64, up to 8 GB RAM, up to 10 GB disk; CPU spec
  undocumented. Python/Node/Go/Rust/Java/Ruby/PHP/GCC preinstalled; package
  lists (pip/npm/cargo/gem/go/apt) configurable; **base image not
  customizable**. **[documented]**
- **Network egress:** API-created environments default `unrestricted` (with a
  safety blocklist); `limited` mode with a domain allowlist available;
  Studio-created default `limited`. **[documented]** Board API reachability is
  therefore fine either way.
- **Secrets:** vault-mediated credentials for MCP OAuth are documented;
  general secret injection into the sandbox environment is *not* a documented
  first-class feature. **[partially documented / absent]**
- **Git: preinstalled.** The [cloud sandbox reference](https://platform.claude.com/docs/en/managed-agents/cloud-sandboxes-reference)
  lists `git`, `curl`/`wget`, `ssh`/`scp`, `gh`-adjacent tooling under system
  utilities. **[documented]** What is NOT documented: any first-class GitHub
  integration or credential-injection mechanism for the hosted sandbox — no
  equivalent of Claude Code on the web's GitHub proxy (§1.6c). Private-repo
  clone/push requires the operator to deliver a token into the sandbox (env,
  skill file, or MCP-mediated), i.e. token-co-resident-with-generated-code —
  the exact posture the Managed Agents article argues against. **[absent —
  material finding for our git flow.]**
- **Self-hosted sandboxes:** brain on Anthropic's control plane, hands on your
  infra; workers claim tool executions from a per-environment queue
  (`block_ms` long-poll, `reclaim_older_than_ms` lease recovery,
  depth/pending/workers_polling metrics); environment key on the worker, org
  API key never on the worker host. **[documented]** Note: choosing this
  option *reintroduces the self-managed sandbox fleet* the scenario is trying
  to eliminate — at A0 it answers a compliance question, not the zero-ops one.

### 1.4 Persistence and resume

- Event history persisted server-side in full; sessions are stateful
  resources; fetchable; SSE streaming; steer mid-run by sending user events;
  `user.interrupt` to stop mid-turn; resume an idle session by sending a new
  user event; sessions seedable with up to 50 `initial_events`.
  **[documented]**
- No branching/checkpoint API beyond the event log itself. **[absent]**
- Because sessions are stateful: **not eligible for Zero Data Retention or
  HIPAA BAA** — session transcripts, sandbox state, and outputs live on
  Anthropic's control plane until explicitly deleted. **[documented]**

### 1.5 Limits

- API rate limits: 300 req/min on create endpoints (agents, sessions,
  environments), 1,200 req/min on read endpoints. **[documented]** At A0's
  ~4–17 session-creates/min this is ample headroom (~18–75× under the cap).
- **Concurrent-session cap per org: undocumented. [absent — a material
  finding: nothing tells us 200 concurrent sessions is allowed, and nothing
  tells us it isn't. A0 cannot be committed to without an answer from
  Anthropic.]**
- Max session duration / idle timeout: undocumented. **[absent]** (12-min
  runs are well inside anything plausible.)
- Data residency: Managed Agents absent from the data-residency feature
  lists. **[absent — assume US/default-region only until stated.]**
- Beta wording: "Behaviors may be refined between releases to improve
  outputs" — the harness can change under our tuned skills without notice.
  **[documented]**

### 1.6 Follow-up findings (official pricing, git, harness identity, Claude Code on the web)

**(a) Official pricing rate — CONFIRMED at $0.08/session-hour.** The official
[pricing page](https://platform.claude.com/docs/en/about-claude/pricing) has a
"Claude Managed Agents pricing" section: billed on exactly two dimensions —
tokens at standard model rates (prompt-caching multipliers apply; web search
$10/1k; Batch discount, fast mode, and `inference_geo` do NOT apply) and
**"Session runtime | $0.08 per session-hour | `running` status duration"**,
metered to the millisecond; `idle`, `rescheduling`, and `terminated` time is
free; "Session runtime replaces the Code Execution container-hour billing
model … You are not separately billed for container hours." **[documented —
upgrades §3 from vendor-claimed to documented; the $0.25 third-party figure is
wrong.]**

**(b) Harness identity — unstated.** No official doc names the runtime as
Claude Code or the Agent SDK; the overview only contrasts Managed Agents with
"custom agent loops" on the Messages API. **[absent — treat the harness as
proprietary and version-opaque; its behaviors "may be refined between
releases".]**

**(c) Claude Code on the web as a dispatchable runtime** — sources:
[Claude Code on the web docs](https://code.claude.com/docs/en/claude-code-on-the-web),
[routine fire API](https://platform.claude.com/docs/en/api/claude-code/routines-fire).

- **It runs actual Claude Code** on Anthropic-managed isolated VMs
  (~4 vCPU / 16 GB RAM / 30 GB disk per session, "may change over time"),
  research preview for Pro/Max/Team/Enterprise seats. **[documented]**
- **Our plugin loads.** Config carryover is explicit: repo `CLAUDE.md`, repo
  `.claude/settings.json` hooks, repo `.claude/skills|agents|commands`, and
  "Plugins declared in `.claude/settings.json` … installed at session start
  from the marketplace you declared." User-level `~/.claude` does NOT carry
  over. **[documented — the only vendor runtime that runs the doperpowers
  plugin as-is, per consumer repo.]**
- **Credentials are structurally right**: a GitHub proxy authenticates git and
  `gh` "so your token never enters the container" (`GH_TOKEN` reads
  `proxy-injected`) — auth-bundled-with-resource, the pattern our credential
  doctrine (§2.4 of the cloud-scale synthesis) already adopted. Network
  egress: limited by default, trusted-domain allowlist, custom per-environment
  domains; setup scripts + environment caching. **[documented]**
- **Programmatic dispatch exists but is not a fleet API.** The routine fire
  endpoint (`POST /v1/claude_code/routines/{id}/fire`, beta header
  `experimental-cc-routine-2026-04-01`) starts a run of a pre-saved routine
  with a freeform `text` payload (≤65,536 chars) and returns a session id/URL.
  Explicitly **experimental**; per-routine bearer token minted in the web UI
  ("no public API for token management"); no idempotency key; no output
  streaming or completion wait; and — decisive for A0 — **"routine runs count
  against a per-account daily allowance that varies by plan"** (numbers
  unpublished **[absent]**), drawing down the same claude.ai subscription
  usage as interactive sessions, 429 + `Retry-After` at the cap, metered
  "extra usage" overage for orgs. "There is no separate compute charge for the
  cloud VM"; rate limits are shared with all other Claude usage on the
  account. **[documented]**
- Net: per-ticket dispatch with a rendered prompt fits the `text` payload
  mechanically, but 5,000 runs/day against unpublished per-account daily
  allowances on subscription seats is not a purchasable contract — it is a
  consumer-product ceiling we would be squatting under. **[assessment]**

## 2. The hard-requirement test: does OUR protocol run?

Mapping the doperpowers worker's needs onto Managed Agents:

| worker need (today, Claude Code) | Managed Agents answer | grade |
|---|---|---|
| Claude Code harness loop | replaced by Anthropic's proprietary harness | **fail — definitional** |
| skills plugin (14 skills, SKILL.md, scripts) | custom skills upload; scripts land in sandbox; triggering semantics unverified | port, unproven |
| Skill-tool invocation / progressive disclosure | no documented equivalent | **[absent]** |
| hooks / plugin manifest / slash commands | no plugin support at all | **[absent]** |
| board API client (`board-*.sh` via gh/curl) | sandbox bash + egress (token co-resident), or re-plumb as custom tools/MCP (token outside sandbox) | port, real work |
| git clone/branch/commit/push to private repo | git preinstalled; no documented credential-injection — token must enter the sandbox | port, credential posture degrades |
| session resume after park (FD-9 answer-relay) | server-side event log + send-event resume — actually *stronger* than JSONL-on-host | pass |
| mixed Claude+Codex fleet (decorrelated review lenses) | Claude models only | **fail** |
| worker protocol dispatch (rendered prompt per ticket) | session create with system prompt + initial_events | pass |
| behavior stability (skills evaluated against harness) | beta harness, "behaviors may be refined between releases" | risk |

The two definitional failures are the verdict: the product's unit of value is
*its* harness. Everything else is a port whose cost is real but bounded — the
port target is genuinely the closest in the market (skills are a first-class
concept nowhere else).

## 3. Pricing at A0

**A0 arithmetic:** 5,000 runs/day × 12 min = 1,000 run-hours/day ≈ **30,000
run-hours/month**; mean concurrency ≈ 42, peak 200.

### Managed Agents

- Billing = tokens at standard model rates + **$0.08 per session-hour** of
  `running` status, metered to the millisecond; idle/rescheduling/terminated
  time free; the runtime charge replaces container-hour billing (no separate
  sandbox compute line); no flat fee. **[documented — official
  [pricing page](https://platform.claude.com/docs/en/about-claude/pricing),
  "Claude Managed Agents pricing" section; the $0.25/session-hour figure
  circulating in one third-party guide is contradicted by the official page.]**
- At A0: $0.08 × 30,000 running-hours = **$2,400/mo** — fits the $1–5k budget
  (and 12-min runs spend some of their wall clock idle-waiting, which is
  unmetered, so this is an upper bound at fixed run count).
  Web search $10/1k searches additive; Batch discount, fast mode, and
  data-residency multipliers do not apply to sessions. **[documented]**
- Beta pricing, no GA commitment. **[documented as beta]**

### Baseline: Claude Code on rented SaaS sandboxes (self-managed orchestration)

- E2B and Daytona both price **$0.0504/vCPU-hr** (per-second billing); Modal
  ≈ $0.1419/physical-core-hr (~3× for CPU work). **[documented on vendor
  pricing pages; cross-confirmed by
  [Northflank's 2026 comparison](https://northflank.com/blog/ai-sandbox-pricing)]**
- A 2 vCPU / 4–8 GB slot ≈ $0.10–0.15/hr all-in → 30,000 hr/mo ≈
  **$3,000–4,500/mo** + plan fee (E2B Pro $150/mo). Fits the budget.
  Northflank-class PaaS or Hetzner bare metal cut this to ~$500–1,500/mo but
  buy back the ops the scenario forbids.
- Running Claude Code headless inside E2B/Daytona/Modal/Cloudflare/Fly
  sandboxes is a well-trodden 2026 pattern with vendor guides on all sides
  ([Modal](https://modal.com/resources/best-sandbox-claude-agent-sdk),
  [Daytona](https://www.daytona.io/dotfiles/claude-coding-live-with-cloudflare-daytona),
  [Qovery guide](https://www.qovery.com/blog/claude-code-sandbox-guide)).
  **[documented pattern, though "fleet at 200 concurrent" specifically is our
  own extrapolation — the round-2 cloud-scale research validated the same
  vendors at 1,000 concurrent price points.]**

**Cost verdict: a wash, slight edge to Managed Agents.** ~$2.4k vs ~$3–4.5k
per month on 30k run-hours — both inside budget. Token spend (excluded here)
is identical in both worlds and almost certainly dominates both. Price does
not decide this question; capability and risk do.

## 4. Comparables against the hard requirement

| offering | what actually runs | our harness? | programmatic dispatch | A0 cost order | verdict as OUR substrate |
|---|---|---|---|---|---|
| **Anthropic Managed Agents** | Anthropic's proprietary harness, Claude models, hosted or self-hosted hands | no — port target only | yes (API, SSE, webhooks, scheduled deployments) | ~$2.4–7.5k/mo + tokens | closest, still a rebuild |
| **OpenAI Codex cloud** | Codex agent in OpenAI-managed `universal` container; setup script + AGENTS.md + domain allowlist are the only customization; secrets stripped before agent phase | no — agent phase IS Codex | yes (SDK/API; credits) | credits ~$0.20–1.80/task ⇒ $1–9k/day at 5k tasks — and that includes tokens **[vendor-claimed rates]** | no |
| **Cursor Cloud Agents** | Cursor's agent; "the agent loop still runs in Cursor's cloud" even in self-hosted-pool mode ([docs](https://cursor.com/docs/cloud-agent/choose-runtime)) | no | yes (Cloud Agents API, fleet management API) | plan + usage credits | no |
| **Devin (Cognition) API** | Devin, period | no | yes (sessions API) | $2.25/ACU ≈ $9/active-hr ⇒ ~$270k/mo at 30k hr — two orders over budget | no, twice over |
| **Claude Code on the web / cloud sessions** | **actual Claude Code** on Anthropic-managed VMs (4 vCPU/16 GB); repo-declared plugins install at session start; GitHub proxy keeps tokens out of the container | **yes — the only one** | routine fire API: experimental, per-routine token, unpublished per-plan daily run allowance | subscription usage + metered overage; no VM compute charge | right architecture, no fleet contract — §1.6c |
| **Generic sandbox clouds (E2B/Daytona/Modal/Cloudflare/Fly)** | whatever you start — incl. Claude Code + our plugin | yes | yes (their APIs + our dispatcher) | ~$3–4.5k/mo | **this is the baseline, not a vendor substrate** — it does not "replace self-managed," it IS self-managed with rented hands |

The pattern is uniform: **brain+hands products bundle their brain.** The only
runtimes that run our harness are (a) rented raw sandboxes — self-managed
orchestration by definition — and (b) Claude Code's own cloud offering, which
runs the harness perfectly but sells no fleet-scale dispatch contract (§1.6c).

## 5. Vendor-claimed vs verified — the honesty ledger

Verified against official docs this session:
- Managed Agents harness-not-yours framing, four concepts, beta header, ZDR/
  HIPAA ineligibility, custom-skill upload flow, custom-tool SSE flow, cloud
  sandbox specs (Ubuntu 22.04/8GB/10GB), egress modes, 300/1,200 req-min API
  limits, event-log persistence and resume, self-hosted queue protocol.
- Managed Agents official pricing: $0.08/session-hour + tokens, idle free, no
  separate container-hour billing.
- Codex cloud container flow (setup script w/ internet, agent phase egress
  off-by-default, secrets stripped before agent phase, 12-hour container
  cache, proxy-fronted egress).
- Cursor: agent loop stays in Cursor's cloud across all runtime options.
- Claude Code on the web: plugin/skill/CLAUDE.md carryover matrix, GitHub
  proxy credential model, 4 vCPU/16 GB/30 GB VM ceilings, routine fire API
  contract (experimental beta header, per-routine token, 65,536-char payload,
  429 semantics), subscription-usage billing with no VM compute charge.

Vendor-claimed / third-party only (treat as directional):
- Codex per-task credit ranges (~$0.20–1.80/task); Devin ACU≈15min
  equivalence; Cursor plan-credit mechanics.

Absent from documentation (findings, not gaps to assume away):
- Managed Agents: org-level concurrent-session cap; max session duration;
  Claude Code plugin support; skill auto-trigger semantics; harness identity;
  data residency; hosted-sandbox git credential injection; CPU spec.
- Claude Code on the web: the per-plan daily routine-run allowance numbers;
  any org-level concurrency guarantee.
- If custom-plugin support mattering to a purchase this size is undocumented,
  the operative reading is: **it does not exist until Anthropic says it
  does.**

## 6. What the A0 scenario changes vs the fleet-scale rejection

The 2026-07-23 cloud-scale research rejected Managed Agents as substrate at
hundreds-to-thousands of runs/hour ("beta API, session data on their control
plane, forecloses the mixed fleet — reference design, not the control
plane"). A0 is 10–50× smaller and adds zero-ops + tight budget, which
genuinely reweighs two things:

1. **Economics flip from irrelevant to attractive.** At fleet scale the
   answer was own hardware ($5–15k/mo vs $73k+ SaaS). At A0, hosted-sandbox
   pricing (~$2.4k/mo) beats hiring any fraction of a platform engineer, and
   the $0.08 runtime rate bundles exactly the state/checkpoint/recovery
   machinery the fleet design budgets weeks for.
2. **The session store comes for free.** Decision-agenda item 8 (session-store
   technology) is answered by the product: server-side append-only event log
   with resume — the one substrate plane we had no research track for.

What A0 does NOT change: the harness-identity problem is scale-invariant. A
20-person startup is *more* dependent on the tuned-skill behavior surviving
contact with the runtime, not less — it has no eval bench headcount to
re-validate 14 skills against a beta harness that "may be refined between
releases."

## 7. Verdict and flip conditions

**Not-viable now as the A0 worker substrate in the stated sense** (replacing
self-managed sandboxes while our harness/protocol runs). Managed Agents does
not run Claude Code or plugins **[absent from docs]**; every comparable fails
the same test harder; and the one vendor runtime that DOES run our harness —
Claude Code on the web, plugins and all — offers only an experimental
per-routine webhook under unpublished per-plan daily allowances on
subscription billing: the right architecture with no fleet contract (§1.6c).

**Viable-with-caveats as a protocol port** — a deliberate rebuild targeting
their harness: skills re-uploaded as Managed Agents custom skills, board ops
re-plumbed as custom tools (credential outside the sandbox — an upgrade over
today's `GH_TOKEN`-in-env), git via sandbox bash (credential posture
*degrades*: no documented injection mechanism, token co-resident with
generated code), dispatch via session API, resume via event log. Slightly
cheaper than the sandbox baseline ($2.4k vs $3–4.5k/mo). Accepting: beta
churn under tuned skills, Claude-only fleet, no ZDR/HIPAA, session data on
Anthropic's control plane, and an unknown concurrency ceiling that must be
answered by Anthropic before committing A0 traffic.

**Recommended posture for the A0 spec:** self-managed-orchestration on rented
sandboxes (Claude Code on E2B/Daytona-class, ~$3–4.5k/mo, zero-ops-adjacent:
no hosts, but we own dispatch/board/telemetry — which we own in every world)
as the substrate; Managed Agents adopted narrowly where it is genuinely ahead
(the durable session store pattern; possibly gate-phase sandbox-less runs).
Re-evaluate at GA.

**Flip conditions — any one of these reopens the question:**
1. Managed Agents documents Claude Code (or bring-your-own-harness) as the
   session runtime, or ships plugin support.
2. Claude Code on the web's dispatch surface graduates: a stable session-create
   API (not per-routine webhooks), published org-level concurrency/daily
   quotas sized for thousands of runs/day, and API-key (not seat) billing.
   This is the nearest flip — the harness, plugin loading, and credential
   proxy already exist; only the commercial/dispatch contract is missing —
   and it would flip the verdict to **viable-now**.
3. Anthropic publishes org concurrency caps + GA + data-residency/retention
   controls for Managed Agents AND the team decides the review fleet can be
   Claude-only (a semantic-layer call — decorrelated review lenses are a
   frozen-layer concern, the human's to trade).
4. Managed Agents ships a documented git-credential injection mechanism
   (GitHub-proxy-equivalent) for hosted sandboxes — removes the one place the
   port makes our security posture worse instead of better.

**Biggest residual uncertainty:** the undocumented ceilings — Managed Agents'
org-level concurrent-session cap and Claude Code on the web's per-plan daily
run allowance. Both are one sales conversation away from resolved, and either
answer could move its offering a tier in this verdict.
