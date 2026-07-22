# Deep-read report — Cursor, "Agent swarms and the new model economics" (Wilson Lin, Jul 20 2026, 17 min)

Primary text: `articles/Agent_swarms_and_the_new_model_economics_Cursor.txt`
Companion sources fetched: `scaling-agents` / `self-driving-codebases` (the earlier browser-swarm posts), `cloud-agent-lessons` (their production cloud-agent infra), `github.com/cursor/minisqlite` (published artifact). Details in §8.

---

## 1. Thesis in 3 sentences

A swarm of planner agents (frontier models, decompose-only) and worker agents (cheap models, execute-only), organized as a dynamically-grown task tree over a purpose-built high-throughput version control system, can build large software (SQLite in Rust from the 835-page manual alone) with quality roughly invariant to the model mix — while cost varies ~8x ($1,339 vs $10,565) depending on how you route frontier tokens. The scaling win comes from **context efficiency** (planners never see implementation detail, workers never see the big picture), not from parallelism per se, and the hard engineering is a set of coordination mechanisms — split-brain prevention, doc-mediated decision reconciliation, neutral merge-resolver agents, megafile decomposition, licensed intentional breakage, stacked decorrelated review — that suppress the failure modes appearing at 1,000 commits/second. The scarce input going forward is the spec: the swarm behaves like a probabilistic compiler that lowers intent into code, and everything in the harness exists to close the meaning-preservation gap.

## 2. Mechanisms & architecture

### 2.1 Two-role tree ("trees and leaves")
- **Planner agents** (smartest models): split a goal into pieces and delegate. They *never implement*. From the earlier posts: a root planner owns the whole user instruction; planners can spawn sub-planners for areas; a judge agent decides at cycle end whether to continue.
- **Worker agents** (fast/cheap models): execute exactly one narrow piece. They *never plan*. Workers operate independently (in the browser-era system: on their own repo copies), submit "handoffs" containing findings and concerns, and do **not** communicate cross-worker (deliberately, to avoid coordination overhead — the Coase argument: coordination costs grow faster than the work, so you tier into bounded units).
- The topology is **not fixed**; the tree grows to cover the problem's contours, so compute and context scale with task complexity. This generalized across browser-building, math, GPU-kernel optimization, vuln-fixing in OSS, raising test coverage, and synthetic-data generation ("billions of tokens").
- **Memory rationale**: a single long-running agent must hold ancestors + current position + global goal simultaneously and drifts (either loses the big picture or does the leaf badly). Splitting roles means each context stays clean. Cursor claims this context efficiency, not parallelism, is the actual scaling unlock, and that it helps even at moderate task sizes.

### 2.2 Orchestration lineage (from companion posts — what they tried and abandoned)
1. **Flat self-coordination via shared files + locks**: 20 agents degraded to effective throughput of 2–3; most time spent waiting on locks agents mismanaged.
2. **Optimistic concurrency control** (reads free, writes fail if state changed): mechanically fine, behaviorally toxic — *agents became risk-averse*, avoiding hard tasks and making small safe changes so their writes wouldn't fail. (A genuinely novel lesson: contention-control policy shapes agent psychology.)
3. **Hierarchical planner→worker pipeline with a judge between cycles**: the design that stuck; plus periodic fresh starts to combat drift/tunnel vision.
4. (Production cloud agents, separate lineage): migrated from a **work-stealing architecture to Temporal** for durable execution; shifted from "eternal" agent workflows to **shorter task-completion workflows**; a separate append-only storage/streaming layer for conversation state with stream-rewind on retry; VM hibernation/resume between messages; checkpoint/restore/fork pipelines for VM images; prewarmed and readonly VMs; secret redaction, network policies, subagent spawning across pods.

### 2.3 Custom VCS
- Git's coarse locks capped the browser swarm at ~**1,000 commits/hour**. The new system peaks at ~**1,000 commits/second** on a from-scratch VCS.
- Throughput is not the only reason to own the layer: **every change passes through the VCS, so it is where collisions first become visible**, and several coordination mechanisms are implemented *inside* it (megafile blocking, conflict interception). The VCS is the coordination substrate, not just storage.
- Internals (data model, storage, conflict detection) are not disclosed.

### 2.4 Coordination mechanisms (each maps failure mode → fix)
- **Split-brain design** (two planners independently implement the same concept differently): fixed *by prompting* — planners make design decisions themselves rather than delegating them, and must ensure no two delegated subtrees decide the same question. (Decision ownership lives at the parent node.)
- **Contention between planners** (two planners fight through back-and-forth edits — "two pictures of reality; merge tooling can't fix a disagreement"): agents record decisions in **shared design docs**; code depending on a decision carries a **compile-checked reference** back to its doc; when planners contradict each other, a **reconciler agent merges the docs** and the references propagate the resolution downstream mechanically.
- **Merge conflicts** (workers are bad at absorbing another agent's context; they overwrite or abandon): a **neutral third-party merge-resolver agent** intervenes on every conflict and resolves on behalf of all parties — impartial and efficient, explicitly modeled on human merge queues.
- **Megafiles** (popular files grow unboundedly because no single agent owns keeping them small; expensive to transport/diff/merge, collision hotspots): workers can **flag** a bloated file → new commits to it are **blocked** → an outside agent decomposes it into modules.
- **Ossification** (models trained on human-in-loop codebases have learned not to touch core code): they **license intentional breakage** — an agent judging a core change worthwhile may patch outside its scope and leave a comment explaining why; the compiler propagates breakage; every agent hitting a resulting build error reads the comment and updates its own piece. (Compiler as broadcast channel.)
- **Review lenses**: many reviewer variants tried — full worker transcript vs output-only vs codebase-only; different models/training/personality. **No single lens catches everything, but decorrelated lenses stack** (their analogy: self-driving reaches above-human reliability with no single perfect component). Review compute is **high-return because review is much cheaper than the work it audits**; they credit stacked review as a major contributor to sustained run quality.
- **Stigmergy / Field Guide**: an agent-owned folder whose `index.md` is auto-injected into every agent at start; agents curate it themselves under only a **line budget**. Rationale: weights are frozen, so *surprises* are what's worth capturing to shorten the next trajectory. Early experiment, promising; expected to matter more on codebases agents don't fully own. (Earlier-era freshness mechanisms: scratchpad *rewriting* rather than appending, auto-summarization at context limits, self-reflection prompts.)

### 2.5 Evaluation protocol
- Task: implement the whole 835-page SQLite manual in Rust; withheld: source, test suites, SQLite binary, internet.
- Grading: **sqllogictest** (millions of queries with known answers), swarm never told it existed; after each run they **manually audited for cheating/shortcuts and for even build-out** (not just where tests look).
- Agents chose their own strategies (broad-foundation-late-spike vs deep-early-plateau), so trends matter more than point scores.

## 3. Numbers (exact quotes)

**Dates**: article Jul 20, 2026; "Introducing Grok 4.5" Jul 8, 2026; "What we've learned building cloud agents" Jun 2, 2026; browser swarm "earlier this year".

**Throughput / contention (old harness vs new, Grok 4.5, same task/budget):**
- Old VCS: "peaked at roughly 1,000 commits per hour on Git". New: "peaks at around 1,000 commits per second".
- "The old run produced 68,000 commits in its first two hours, roughly 70 times the new run's pace."
- Conflicts: old "more than 70,000 conflicts before we paused it, accelerating rather than stabilizing"; new "fewer than a thousand over its full four hours".
- Hottest file: old "7,771 conflicts, touched by 1,173 different agents"; new "the most contested file in the whole codebase saw 47".
- Structure: old "sprawled to 54 crates, including three separate SQL packages"; new "settled on nine crates early and never added another".

**Quality / code size:**
- New runs at 4-hour cutoff: "between 73% and 85%"; old runs "11% to 77%". "Every new configuration went on to pass 100% of the suite" (wall-clock for 100% not given). Grok 4.5 new: "reached 80% in four hours"; old Grok run "paused before its second hour". "The Fable 5 hybrid passed about two-thirds of the suite within the first hour."
- Fable 5 mix: old 64,305 lines of engine code vs new **9,908** (both 100%). Opus mix: old 19,013 lines @97% vs new **4,645 @100%**. (Harness quality is visible as ~6.5x code-size compression at equal or better score.)

**Economics:**
- Total run cost range: "$1,339 for the Opus 4.8 hybrid to $10,565 for GPT-5.5 alone" (~7.9x).
- Token structure: "workers carrying at least 69% of the tokens, and over 90% in most" runs.
- Cost inversion: Opus-as-planner "produced a small fraction of the tokens but roughly two-thirds of the cost".
- Worker-fleet comparison: GPT-5.5 workers alone "$9,373"; Composer 2.5 worker fleet "$411" (~23x).
- Planner externality: Fable 5 planner billed slightly less than Opus 4.8 planner "despite roughly twice the per-token price, because it used far fewer planning tokens. But the Fable run's workers went through several times as many tokens, and the run as a whole came out substantially more expensive."
- Footnote 2: GPT-5.6 Sol was dropped — "more sensitive to literal and emphasized wording", produced "runaway spirals unlike anything the other models produced"; no time to tune per-model prompts without invalidating the comparison.

**Companion-post numbers (browser era / production cloud):**
- Browser project: "1 million lines of code" across ~1,000 files; "trillions of tokens"; peak ~1,000 commits/hour; "10M tool calls" over "one week"; several hundred simultaneous agents on a **single large VM**; **disk I/O became the primary bottleneck** (monolith compilation = many GB/s of artifacts) after RAM.
- Other swarm projects: 266K additions/193K deletions (3-week Solid→React migration); 7.4K commits/550K LoC (Java LSP); 14.6K commits/1.2M LoC (Win7 emulator); 12K commits/1.6M LoC (Excel clone).
- Production cloud agents: Temporal handles ">50 million actions per day across more than 7 million unique workflows"; reliability went from "one 9" to "past two 9s" post-migration; ">40% of our PRs come from cloud agents".

**Published artifact check**: `github.com/cursor/minisqlite` exists (solo Opus 4.8 run; 162 stars at fetch). Its README describes ~200K lines of Rust across **14 crates**, 5,650 tests (~90s), strictly layered one-seam-per-layer crates with boundaries mechanically enforced by `seams.rs` tests; no OS-level file locking (in-process coordination only). Note the mismatch with the article's hybrid-run numbers (9 crates, 4.6–9.9K engine lines) — the public repo is the *solo* run, graded only informally per footnote 1, and 200K presumably counts tests. Treat article code-size numbers as engine-only, run-specific.

## 4. Failure modes & operational lessons

1. **Lock-based self-coordination collapses** (20 agents → throughput of 2–3) and **OCC induces risk-aversion** — agents adapt behaviorally to whatever contention regime you impose. Contention policy is a behavior-shaping instrument, not a neutral mechanism.
2. **Split-brain duplication is a prompting/ownership problem, not a tooling problem** — solved by making decision ownership non-delegable at the parent.
3. **Planner-vs-planner contention is a semantic disagreement**; merge tooling cannot fix it. It requires an explicit decision artifact (design docs) plus a reconciler plus a mechanical propagation channel (compile-checked references).
4. **Workers cannot resolve merge conflicts** — they overwrite or abandon. A neutral third-party resolver is a distinct agent species.
5. **Megafiles are a tragedy of the commons** — nobody owns keeping shared files small; requires flag→freeze→decompose machinery.
6. **Ossification is a training artifact** — models learned deference to core code; autonomy requires explicitly licensing scoped breakage with recorded rationale, using the compiler as the broadcast medium.
7. **Commit volume is a vanity metric**: 68K commits in 2h read as productivity but were thrash (70K+ accelerating conflicts). Conflict rate and hottest-file contention are the real health signals. Old run was **paused by humans** before hour 2 — spiral detection was manual.
8. **No single review lens suffices; decorrelation is the multiplier.** Review is cheap relative to audited work — overspend on it.
9. **Model heterogeneity is a prompt-compatibility risk** (GPT-5.6 Sol spirals). Harness prompts are per-model tuned artifacts.
10. **Errors are budgeted, not forbidden** (browser era): accept small stable error rates, let downstream agents fix cascades, snapshot a "green" branch + fixup pass before release.
11. Production infra: "eternal" workflows are the wrong shape — short task-completion workflows on a durable-execution engine took them from one 9 to two 9s. Failure domains survived: inference-provider outages, pod replacement, EC2 node failure, multi-week runs.

## 5. Transfer analysis for OUR substrate

Framing: their swarm is a *single-goal intra-run* system; ours is a *ticket-board inter-run* system. Our unit of concurrency (ticket → worktree → PR) is far coarser than theirs (commit), which changes what transfers. At the target scale (hundreds–thousands of worker runs/hour/project) we sit between their two regimes: well above human tempo, well below 1,000 commits/sec *within one repo* — unless many workers land on the same repo hot spots, which they will.

- **STEAL — Planner/worker cost split as the dispatch-tier policy.** Their strongest economic result: quality was mix-invariant, cost varied 8x, and the winning shape is *frontier model at the decision points, cheap model for the token bulk* (Composer fleet $411 vs GPT-5.5 fleet $9,373). Our semantic layer already has the decision points isolated: pre-code gate, decomposition, park/escalate judgments, review verdicts → frontier tier; implementation inside a gated, well-scoped ticket → cheap tier. The substrate must make model tier a *per-phase* routing decision, not a per-worker one, and meter it. Corollary (Fable-planner lesson): evaluate planner/gate models on **total downstream run cost**, not the planner's own bill — a decomposition that spawns verbose worker trajectories is expensive even if the decomposer was cheap.
- **STEAL — Durable-execution engine for dispatch (Temporal or equivalent).** Their production migration (work-stealing → Temporal, one 9 → two 9s, 50M actions/day) is the single most directly applicable substrate datum. It replaces our file-based (host,pid,session) daemon registry at multi-host scale and is *doctrinally consonant*: the workflow event history is exactly "durable log as identity of work; compute disposable". Keep workflows short (per ticket-phase: gate → implement → open-PR → review → land), not eternal per-worker.
- **STEAL — Review is underpriced; buy more of it.** "Review is much cheaper than the work it audits" and decorrelated lenses stack. Within our frozen "independent adversarial review", implement the review worker as N decorrelated lenses (different model, different evidence diet: transcript-blind vs transcript-aware vs codebase-only) whose findings union into one verdict. This is an implementation enrichment, not a semantic change.
- **STEAL — Field Guide (stigmergy) as a first-class substrate object.** Per-repo, agent-curated, auto-injected index with a hard line budget, capturing *surprises* specifically. We already have the embryo (memory directory, living-spec Surprises sections); the deltas to adopt: agent-owned curation as an explicit duty, auto-injection at worker start, and the line budget as the only constraint. Their prediction that it matters most "on codebases agents don't fully own" describes our enterprise multi-team target exactly.
- **ADAPT — Neutral merge-resolver as a third agent species.** At hundreds of PRs/hour per repo, PR-vs-PR conflicts and semantic drift between concurrently-landed tickets become routine. Don't make implementers rebase-and-absorb (they'll overwrite or abandon, per Cursor); dispatch a neutral resolver agent on merge-queue conflicts. Adapt, not steal: ours operates at PR/merge-queue granularity on git, not inside a custom VCS.
- **ADAPT — Megafile flag→freeze→decompose as an auto-registered board ticket.** The mechanism translates cleanly: any worker can flag a hotspot file; the substrate freezes it (merge-queue rule) and auto-registers a decomposition ticket. Gives us their tragedy-of-the-commons fix without new infrastructure.
- **ADAPT — Decision docs with checked references.** Their compile-checked doc references are the industrialized version of our ADR habit. Adaptation: decisions recorded as ADRs; code carries lint/CI-checked references; a reconciler duty (could be a review-lens or a maintenance ticket) merges contradicting ADRs. Full compile-checking is language-dependent — start with CI lint.
- **ADAPT — Contention telemetry as the health dashboard.** Their spiral was visible in conflict-rate acceleration and hottest-file stats, and was caught *manually*. At our scale: per-repo conflict rate, hottest-file contention, PR-rework rate, and commit-churn ratio as automatic circuit-breakers (pause dispatch to a repo that's spiraling). Directly answers "how do we detect swarm-scale failure" for the board pipeline.
- **ADAPT — Ossification license.** Our pre-code gate scopes tickets tightly; that reproduces the ossification trap (nobody touches core). Adaptation: an implementer may make an out-of-scope core patch **only** with a recorded rationale (comment + ticket link), and CI breakage routes to affected owners as auto-registered fix tickets. Weaker than their compiler-broadcast (we have humans and review in the loop) but preserves the license.
- **REJECT — Custom VCS.** Justified only at ~1,000 commits/sec into one tree with coordination logic embedded in the VCS. Our concurrency unit is the ticket/PR; git + worktrees + a merge queue holds at our scale. Revisit only if we ever run intra-ticket swarms dense enough that git lock contention appears in telemetry (their browser-era evidence: git chokes around ~1K commits/hour *with hundreds of agents on one branch* — we are nowhere near that per-branch).
- **REJECT — Dynamic planner-tree topology replacing the board.** Their tree is the right shape for one monolithic goal; our board is the right shape for a stream of independent tickets, and it is our frozen SSOT. Where a ticket is tree-shaped, we already have the answer at the semantic layer (decomposing-goals → child tickets). Do not import sub-planner spawning as a substrate feature.
- **REJECT (for now) — No-human-in-loop error budgeting per commit.** Their "accept stable error rates, fix downstream" works inside a run that ends with a green-branch fixup pass. Our landed PRs are consumed by humans and other teams continuously; tiered merge authority (frozen) is our error-budget mechanism. Don't relax it on this evidence.
- **Capacity-planning datum (companion post): disk I/O, not CPU/RAM, was their single-host ceiling** (many GB/s of compile artifacts, several hundred agents on one large VM). For our multi-host design: budget NVMe throughput per worker-slot and expect build artifacts, not model I/O, to be the binding local resource; this also argues for shared remote build caches.
- **Per-model prompt profiles.** The GPT-5.6 Sol footnote (runaway spirals from wording sensitivity) means worker/planner prompts must be versioned per model family in the substrate config. We already route through a gateway to GPT Sol-class models — treat this footnote as a live warning, not trivia.

## 6. Tensions with our frozen layer / settled doctrine

- **Durable log = identity of work: REINFORCED, with a nuance.** Temporal-style event history and their append-only conversation store are the same doctrine at scale; their eternal→short-workflow shift matches "compute disposable". Nuance: in their swarm the *VCS*, not any board, is where the true state of work lives and where collisions surface ("every change passes through the VCS, so it is where collisions first become visible"). For us the board stays SSOT because tickets are coarse — but the article implies a second, finer coordination ledger (the merge queue / VCS event stream) whose telemetry the board never sees. Our substrate should treat merge-queue/VCS events as a first-class signal feed into the board, or the board's picture of "in-progress" will be fictional at scale.
- **Tiered merge authority vs throughput — flagging loudly, though it's a capacity constraint, not a semantic redesign.** At hundreds–thousands of runs/hour/project, the human escalation tier becomes the system bottleneck by construction. Cursor's answer was to remove humans from the loop entirely inside a run; ours cannot. The substrate must therefore (a) make the auto-land tier carry the overwhelming majority of merges, (b) queue/budget the human tier explicitly with SLAs, and (c) use stacked review lenses to widen what safely qualifies as auto-landable. If human-tier volume still exceeds human capacity, *that* is the point where scale pressures the semantic layer (e.g., a fourth authority tier: multi-lens unanimous auto-land for medium changes). Flag for the human; no change proposed now.
- **Independent adversarial review (frozen) vs their evidence that no single lens catches everything.** Not a contradiction — but the frozen layer's singular "a review worker" reading is weaker than what their data supports. Resolution stays substrate-side: one review *verdict*, many decorrelated lenses beneath it.
- **A third species exists.** Our semantic layer names two species (implementer, reviewer). Cursor's system required neutral coordination agents (merge-resolver, doc-reconciler, megafile-decomposer). These don't fit either species — they are substrate maintenance agents with no ticket of their own. Either model them as auto-registered maintenance tickets (keeps semantic layer intact) or acknowledge a third species. Recommend the former; flagging the choice.
- **Their split-brain fix mildly contradicts maximal decomposition.** They *forbid* planners from delegating design decisions. Our decomposing-goals doctrine already keeps cross-cutting decisions at the parent, but at swarm scale this must be enforced (no two child tickets may own the same question), not just encouraged — a gate-check candidate.

## 7. Open questions (candidates for follow-up deep research)

1. **Custom VCS internals**: data model, conflict-detection granularity, how coordination hooks (megafile freeze, resolver dispatch) are embedded, storage/replication. Nothing disclosed. Is anything comparable available off-the-shelf (e.g., merge-queue systems, Jujutsu/Sapling at high write rates)?
2. **Scheduler mechanics of the new harness**: how planners/workers are spawned, capped, and throttled; tree depth/width limits; judge cadence; how the 4-hour budget was enforced; what "paused" mechanically means.
3. **Review-lens composition**: which lens mix they settled on, verdict-aggregation rule, and the measured marginal value per added lens (they assert stacking, no numbers).
4. **Field Guide mechanics**: line-budget size, eviction/curation protocol, measured effect size; does injection ever poison runs (bad guide entries propagating)?
5. **Cost accounting basis**: do the dollar figures include infra/VCS/compute or tokens only? Composer 2.5 internal pricing makes cross-shop comparison shaky.
6. **Integrity verification at scale**: they manually audited runs for cheating and even build-out. What does *automated* holdout-integrity checking look like when we run thousands of runs/hour? (Directly relevant to our review workers.)
7. **Time-to-100%**: all new configs eventually passed 100% — over what wall-clock and cost beyond the 4-hour comparison window?
8. **Solo-run discrepancy**: public minisqlite (solo Opus, 14 crates, ~200K lines incl. tests) vs hybrid-run stats (9 crates, 4.6–9.9K engine lines). Does the planner/worker split itself *compress* codebases (worker held to explicit instructions), or is this run-to-run noise? If the split compresses output, that's another argument for it beyond cost.
9. **Behavioral economics of contention regimes**: OCC made agents risk-averse. What claim/lease semantics keep board-scale agents bold but safe? Nobody has published on this.

## 8. Links followed

1. `https://cursor.com/blog/scaling-agents` — the earlier browser-swarm post: orchestration lineage (locks → OCC → hierarchy + judge), OCC-induced risk aversion, browser-project scale numbers (1M LoC, trillions of tokens, project list), model-role observations, "prompts matter more than harness/model".
2. `https://cursor.com/blog/cloud-agent-lessons` — production infra: Temporal migration (50M actions/day, 7M workflows, one 9 → two 9s), VM hibernation/checkpoint/fork, prewarmed VMs, append-only conversation storage with stream rewind, network/credential policy, >40% of Cursor's own PRs from cloud agents. The most substrate-relevant source of the set.
3. `https://cursor.com/blog/self-driving-codebases` — swarm-era details: ~1,000 commits/hour peak, 10M tool calls/week, several hundred agents on one large VM, disk-I/O bottleneck, scratchpad-rewriting freshness mechanisms, error-budget philosophy, prompting findings (constraints beat instructions; concrete quantity ranges).
4. `https://github.com/cursor/minisqlite` — artifact verification: repo exists (solo Opus 4.8 run), ~200K lines Rust/14 crates/5,650 tests, mechanically enforced layer seams, no cross-process file locking; surfaced the code-size discrepancy noted in §3/§7.

Not followed: Wikipedia (Stigmergy, Coase) — definitional only; `grok-4-5`, `warp-decode`, `multi-agent-kernels` — related-post navigation, marketing/inference-side, not load-bearing for substrate; sqllogictest wiki — sufficiently described in-article; the X post — announcement only. No fetch failures.
