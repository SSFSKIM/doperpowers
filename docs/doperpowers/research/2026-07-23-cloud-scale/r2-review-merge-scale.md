# R2 — Landing hundreds of changes/hour safely: merge queues, auto-land criteria, agent review at scale

Round-2 deep research for the cloud-scale reference architecture. Feeds: auto-land tier design,
merge-queue capacity math, human escalation-queue design. Semantic layer (pre-code gate, park
states, independent adversarial review, tiered merge authority) treated as frozen; flags in §3.

---

## 1. Findings per question

### Q1 — Merge/submit queue prior art at scale

**Google TAP + submit queue (monorepo).** The only published system verifiably operating at our
target rate on a single repo. TAP handles **>50,000 changes/day (>1 change/second average, ≈2,000/hour)**
and runs **>4 billion test cases/day**. Mechanism: it *gives up per-change verification* — changes are
**batched together**, and when a batch fails, TAP **automatically bisects the batch** (splits it and
re-runs against individual changes) to isolate the culprit. Average wait to submit a change: **~11 minutes**.
Flake handling is a first-class concern: Google reports ~1.5% of test runs flaky, and TAP simply does not
run every affected target at every change. (Sources: "Taming Google-Scale Continuous Testing" Memon/Gao;
SWE-at-Google book ch. 23; xgwang.me summary; Google Testing Blog.)

**Uber SubmitQueue (EuroSys 2019, "Keeping Master Green at Scale").** The best-published *algorithm*
for optimistic queuing. Numbers: before it, Uber's mainline was green only **52%** of the time; after,
**100%**. Scales to thousands of daily commits on monorepos. Mechanisms:
- **Speculation tree**: a binary decision tree of "assume change A passes / fails" branches; builds for
  the most probable paths run in parallel ahead of decisions.
- **Success-prediction model**: logistic regression on ~100 features, **97% accurate** at predicting
  whether a change will pass — this is what makes speculation cheap (you almost always speculate on
  the all-pass path).
- **Conflict analyzer**: two changes are independent iff they touch no common **build targets** (target
  hash comparison); independent changes verify and land fully in parallel.
- Result: with *n* worker slots for *n* changes/hour, turnaround is within **1.2x of an oracle** that
  knows all outcomes in advance.
- Key hazard number: at just **16 concurrent changes in flight, conflict probability is ~40%** —
  confirming round-1's "PR-vs-PR conflicts become routine" at far lower concurrency than our target.
- Baseline math the paper opens with: 1,000 changes/day with 30-minute builds, run serially, is a
  20-day backlog — serial queues are structurally dead at this scale.

**Chromium CQ.** ~300 committers/day averaging 3 CLs each (~**900 CQ attempts/day**, ~40/hour); each
attempt spawns **~100 builds**. Flake policy is explicit and quantified: retries increase the chance a
flaky test *lands* only **sublinearly**, but reduce flake impact on *unrelated* CLs **exponentially** —
so CQ retries failures, and if a run fails due to identified infra flake it does **not** reject the CL.
Dry-run mode (full verification, no submit) is a separate first-class product.

**GitHub merge queue (hosted ceiling).** Configurable: merge-group **build concurrency 1–100**,
**min/max group size 1–100**, timeout to merge undersized groups. Semantics: FIFO; a PR whose merge
group fails CI is **removed from the queue** and all subsequent groups are **recreated without it**
(cascading rebuild — cost is quadratic-ish in failure rate × queue depth). Jumping the queue rebuilds
all in-flight groups. No published max queue size or throughput guidance; no speculation, no
target-level independence analysis. Third-party analyses (Mergify) note the native queue is effectively
sequential without careful batch configuration.

**GitLab merge trains.** Hard cap: **20 pipelines running in parallel per train**; extra MRs queue
behind. Same failure semantics (drop + recreate behind).

**bors/Rust (pessimistic baseline).** Full serial testing with ~2h CI caps rust-lang at **~10 merges/day**;
the community's workaround is **rollups** — humans batch a dozen "small, low-risk" PRs into one bors
run. I.e., even a volunteer OSS project independently reinvented (a) batching and (b) a *risk-class
label* ("rollup-safe") as the price of throughput.

**Shopify (industrial mid-scale).** 1,000+ developers on one Rails monolith: **~400 commits/day merged**
via merge queue with a **predictive branch** (optimistic speculation-lite), **40 deploys/day**; >90% of
PRs to the core app go through the queue; failing PRs auto-removed to keep master green.

**Capacity math takeaway.** Published per-repo sustained rates: bors ~0.4/hr → Chromium ~40/hr →
Shopify ~17/hr merged (400/day) → Google monorepo ~2,000/hr. Our target ("hundreds of runs/hour per
project", some fraction of which are landings) sits between Chromium and Google — a regime where **only
batching + auto-bisection (TAP) or speculation + build-target independence (SubmitQueue) have public
proof**. Hosted primitives (GitHub queue at ≤100 concurrency with drop-and-rebuild semantics, GitLab at
20 parallel) have no published deployment at that rate, and their failure semantics degrade sharply as
per-PR failure probability rises — which matters because agent-authored PRs will have a higher CI-failure
rate than the human-authored PRs these queues were tuned for.

### Q2 — Auto-land criteria in practice

**Google Rosie / LSC global approvals (SWE book ch. 22).** The closest published thing to machine
merge authority: Rosie shards a large-scale change along ownership boundaries, runs each shard through
an independent test-mail-submit pipeline, and **pattern-based tooling automatically approves shards
that meet expectations**; the remainder route to a small set of **global approvers** (humans with
repo-wide approval rights). Auto-approval is scoped to *mechanically verifiable, pattern-conforming*
changes; humans throttle the rest. Also note: Rosie's throughput is deliberately limited by *reviewer
bandwidth*, and Google solved reviewer discovery with an owners-weighting service — human attention is
managed as the scarce resource.

**Renovate/Mend merge confidence (dependency auto-merge).** The most widely deployed auto-land policy
in industry. Guardrails: automerge only after required tests pass; confidence badges computed from
crowd adoption/regression signals; npm packages can't reach "High" confidence until **≥3 days old**
(unpublish window); recommended scope = "updates where you would have clicked merge without reading
the changelog" — devDependencies, patch bumps, pinned digests — conditional on good test coverage.
This is change-class-based auto-land: the class, not the diff, carries the risk assessment.

**Meta TestGen-LLM / Assured LLMSE (FSE 2024, Mark Harman et al.).** The only published case of
LLM-authored code passing through a *guardrail chain designed to justify landing*: generated test
improvements must (1) build, (2) **pass reliably on repeated runs** (flake filter), (3) **measurably
increase coverage** — only then are they offered; **73% of guardrail-passing recommendations were
accepted** by Meta engineers for production. The doctrine: restrict autonomous authorship to change
classes whose improvement is *machine-verifiable*, then the human accept step is cheap. Follow-on (ACH,
mutation-guided generation) keeps the same shape.

**Meta Conveyor (OSDI 2023) — post-land authority.** **97% of container-service deployment pipelines
run with zero manual intervention** (55% continuous — every passing change straight to production; 42%
on fixed schedule). Deployment authority at Meta is already almost fully automated; humans are on the
exception path only.

**Who auto-lands general LLM-authored code with no human? Nobody, publicly.** Anthropic runs its
multi-agent Code Review on nearly every internal PR but states it **does not approve PRs
automatically**. Google states AI-generated changes (80% of CLs in its AI migration workstream were
AI-authored) are **approved by engineers**. OpenAI's Codex team shipped **~1M lines with zero manually
written lines**, but humans steered via PRs (~3.5 PRs/engineer/day) with "minimal blocking merge
gates" — minimal gates, still human-merged. Our auto-land tier for general agent changes goes beyond
any published practice; the published precedents (Rosie patterns, Renovate classes, TestGen guardrails)
all bound auto-land by **verifiable change-class**, not by a size heuristic alone.

### Q3 — LLM/agent code review at scale

**Cursor Bugbot (primary source: cursor.com "Building a better Bugbot", "Bugbot out of beta").**
Scale: **>2M PRs reviewed/month** (customers incl. Rippling, Discord, Samsara, Airtable, Sierra);
beta alone: >1M PRs, >1.5M issues flagged. Quality trajectory: bugs flagged per run **0.4 → 0.7**;
resolution rate (flagged bug fixed before merge — their precision-usefulness proxy) **52% → 70–79%**;
resolved bugs per PR **0.2 → 0.5**; >35% of autofix patches merged. Architecture history is the
important part for us: v1 was an *ensemble* — **8 parallel passes with randomized diff ordering,
bucketing of similar findings, majority voting, category filters, then a separate validator model for
false-positive detection, then dedup against prior runs**. They later collapsed this into a single
fully-agentic reviewer with tool access and dynamic context, and flipped prompting from "restrained"
to "aggressive — chase every suspicious pattern" *because the validator stage absorbs the false
positives*. 40 major experiments; many "obvious" changes regressed metrics. Lesson: generate-loud +
verify-hard beats generate-quiet; the verifier is what makes recall affordable.

**Anthropic Code Review (claude.com/blog/code-review; InfoQ).** Runs on nearly every internal PR.
Same shape independently converged: **parallel bug-hunting agents → verification agents filter false
positives → severity ranking → one high-signal comment**. Reported internal numbers: **<1% of findings
marked incorrect** by engineers; PRs receiving substantive review comments rose **16% → 54%**;
explicitly **does not auto-approve**. Secondary reporting: >90% of code for new Claude features is
agent-authored; typical engineer merges ~8x more code/day than 2024.

**OpenAI.** Codex **reviews 100% of internal PRs**; engineers merge **70% more PRs/week**; OpenAI's
stated observation: teams get value from agent review *in proportion to test quality* — the reviewer
leans on the harness.

**Academic/industry studies.** Human baseline: consistent code review catches ~60–65% of issues.
LLM-reviewer studies (2025–26): best methods reach 0.93–0.94 accuracy on industrial static-analysis
triage but **recall stays below the 90% enterprise bar**; **ensembles raise sensitivity but raise
false-positive load** — matching round-1's decorrelated-lens claim, with the addendum that a
*verification/judging stage* is required to keep the FP economics sane (Meta ACH's LLM-judge ensemble
hit **>98% precision filtering weak catches**). Cautionary systemic datum: HackerOne paused the
Internet Bug Bounty in March 2026 under AI-amplified report volume — unfiltered LLM findings can DoS
a human triage tier; the validator stage is not optional at scale.

### Q4 — Rollback/detection as a substitute for pre-merge review depth

**Meta staged exposure.** Land → employee dogfood (push-blocking alerts) → **2% production canary** →
100%, tiered over hours; tens-to-hundreds of diffs pushed every few hours; despite 15x mobile-team
growth, critical release issues stayed roughly constant. Pre-merge testing is deliberately *not* the
last line; cheap post-land detection layers are.

**Kayenta (Netflix+Google, open source).** Automated canary judge: statistical tests per metric,
weighted aggregate **score 0–100**, classified into **success (auto-promote) / marginal (route to
human) / failure (auto-rollback)**. This is a *published, production three-way authority tier at
deploy time* — structurally identical to our merge-authority tiers, one stage later.

**Meta Conveyor.** 97% fully automated pipelines with dependency analysis to block faulty releases and
health-check-driven progression across millions of machines — post-land detection at full industrial
scale, no human in the loop for the healthy path.

**Decision framework.** No published crisp threshold ("below blast radius X, skip review depth Y").
The structural argument that emerges instead: Google/Meta spend pre-merge effort roughly *proportional
to what post-land detection cannot catch* (privacy, security, API contracts, data corruption —
irreversible or slow-manifesting harms), and rely on canary+revert for everything whose failure is
fast-manifesting and reversible. Renovate's 3-day-age rule is the same logic inverted (wait until the
ecosystem's post-release detection has run). For our design: auto-land depth can be reduced for
changes that are (a) behind flags/canary, (b) fast-detectable, (c) cheaply revertible — and must NOT
be reduced for schema/data/security/config changes regardless of diff size.

### Q5 — Human review-queue design

**Google's SLO.** Public eng-practices: **one business day maximum** to first response; internally
(ICSE 2018 case study) median **<1h to initial feedback** for small changes, **<4h median to approval**
overall (vs 14.7–19.8h at other studied companies); **>80% of changes have at most one reviewer**;
enabled by a strong small-CL culture and ownership/readability making a single reviewer sufficient.

**Small units + stacking.** Analyses of 1.5M PRs: PRs <200 lines approved **~3x faster**; 200–400-line
PRs show **40% fewer defects**; each +100 lines adds ~25 min review time; at 1,000+ lines defect
detection drops ~70%. Stacked diffs (Meta/Phabricator lineage, Graphite) let reviewers take one small
layer at a time and let different humans review different layers in parallel.

**Specialized approver roles.** Google's LSC process created **global approvers** — a small,
high-context set of humans who approve repo-wide mechanical changes — rather than distributing that
load to every owner; Rosie's owners-weighting service routes each shard to the person best able to
review it, and Rosie's overall rate is throttled to reviewer bandwidth.

**Synthesis for our human tier at dozens of escalations/day:** (1) hard first-response SLO (Google
proves 1-business-day max, sub-hour median is achievable when units are small); (2) escalations must
arrive pre-verified and severity-ranked (Anthropic/Bugbot pattern) so the human reads one high-signal
summary, not raw agent output; (3) a dedicated escalation-approver rotation (global-approver analog)
with routing weighted by ownership/context, not broadcast; (4) size caps on what may escalate as a
single unit — oversized escalations decompose (stacked layers), or they poison the queue math.

---

## 2. Implications for our tiered merge authority

| Design question | Evidence | Implication for us |
|---|---|---|
| Can auto-land carry the overwhelming majority? | Meta: 97% of deploy pipelines fully automated; Google TAP lands 50k/day with no per-change human test gate; Renovate/Rosie auto-approve whole change classes | Yes — precedented, but every precedent bounds auto-land by **verifiable change-class + guardrail chain** (build, repeated-pass flake filter, measurable-improvement check, blast-radius class), not by "small diff" alone |
| Auto-land tier boundary | TestGen-LLM: build + pass-5x + coverage-up ⇒ 73% human acceptance; Renovate: class+confidence+age; Rosie: pattern-conformance | Define the tier as a **whitelist of machine-verifiable change classes** with per-class guardrails; anything not classifiable is by definition not auto-landable |
| Merge-queue capacity per repo | Serial: bors ~10/day. GitHub queue: ≤100 concurrency, drop-and-rebuild on failure. GitLab: 20 parallel. Shopify: 400/day. TAP: >2,000/hour via batch+bisect; SubmitQueue: 1.2x oracle via speculation+target-independence | At hundreds of landings/hour we must build TAP/SubmitQueue-style queuing (batch + auto-bisect, or speculate + build-target independence). Hosted queues top out around low-hundreds/day with agent-level failure rates. This is substrate — open for redesign |
| Conflict rate planning number | Uber: 16 concurrent changes ⇒ ~40% conflict probability | Neutral merge-resolver agents (round-1) are not an edge case; budget them as a steady-state worker species. Prefer build-target-level independence detection to file-level |
| Flake handling | TAP doesn't run every test per change; Chromium: retries hurt sublinearly/help exponentially, infra-flake never rejects a CL; SubmitQueue's 97% pass-predictor | Queue must own a flake policy (retry + quarantine + never-blame-the-innocent-PR); without it, queue throughput collapses at scale |
| Lens-stacking ROI | Bugbot v1: 8 passes + majority vote + validator; later: 1 aggressive agent + validator; Meta judge-ensemble 98% precision; academic: ensembles ↑ sensitivity but ↑ FP load | ROI of stacked lenses is real but **conditional on a downstream verifier stage**; budget the verifier as a distinct component, and expect single-agent-with-tools + verifier to beat naive N-model voting (Cursor's measured evolution) |
| Reviewer precision achievable | Anthropic <1% findings marked incorrect (with verification stage); Bugbot 70–79% resolution rate | High-precision agent review at full PR volume is production-proven at two frontier labs + one vendor at 2M PRs/month |
| Human tier throughput | Google: <1h median first response, >80% single-reviewer, 1-day SLO; small-PR 3x approval speed; global-approver role | Human tier survives dozens/day if: escalations are small, pre-verified, severity-ranked, routed to a dedicated rotation with SLO — all four are published practice |
| Post-land safety net | Kayenta success/marginal/fail scoring; Meta 2% canary; Conveyor dependency-analysis gating | Auto-land tier should be coupled to staged exposure + auto-revert; pre-merge depth is reserved for harms canaries can't catch (security/data/contracts) |

## 3. Flags — where scale pressure touches the frozen semantic layer

Phrased as options for the human; none of these is a recommendation to change the frozen layer.

1. **Post-land detection reads like a fourth authority tier.** Kayenta's success/marginal/fail and
   Meta's canary ladder are, functionally, merge-authority decisions made *after* landing (auto-promote /
   escalate-to-human / auto-revert). Options: (a) treat rollout as pure substrate and keep the
   two-tier merge semantics untouched; (b) explicitly extend tiered merge authority with an
   "auto-land-under-watch" class whose landing is conditional on canary verdict — a semantic-layer
   amendment. Evidence says every org at this scale has (b) in substance, whatever they call it.
2. **Batch verification weakens per-change gating.** TAP-style batching (the only proven mechanism at
   hundreds/hour on one repo) means an individual bad change can transiently enter the batch and be
   bisected out, rather than being individually verified pre-land. If the frozen layer is read as
   "every change is individually verified before merge," scale pressures that reading. Options:
   (a) accept batch semantics with auto-bisection as satisfying the intent; (b) pay the
   SubmitQueue-style speculation cost to keep true per-change verification; (c) per-repo choice by
   risk class.
3. **No public precedent for human-free merge of general agent code.** Anthropic, Google, and OpenAI
   all keep a human approval per change even at >90% agent authorship; published auto-land is always
   class-bounded (deps, LSC shards, guardrailed tests). Our auto-land tier as designed goes beyond
   public practice. Not a reason to retreat — but the human should know the tier's safety case rests
   on our own guardrail design (change-class whitelist + verifier stage + canary/revert), not on
   industry precedent.
4. **Escalation-queue DoS risk.** HackerOne's 2026 pause under AI-amplified report volume shows an
   unthrottled agent-finding stream can break a human triage tier. The frozen human tier survives only
   if the verifier stage in front of it is treated as load-bearing infrastructure with its own quality
   SLO (false-escalation rate), which the semantic layer currently implies but does not name.

## 4. Confidence notes

- **High confidence** (primary or peer-reviewed): TAP numbers (Google paper + SWE book); SubmitQueue
  mechanics and 1.2x-oracle/52%→100% (EuroSys 2019 via acolyer + ACM); GitHub/GitLab queue semantics
  (official docs); Rosie/global approvers (SWE book ch. 22); TestGen-LLM 73%/guardrails (arXiv/FSE);
  Conveyor 97%/55% (OSDI 23); Kayenta scoring (Netflix TechBlog/Google Cloud blog); Google review
  medians and 1-day SLO (ICSE 2018 paper, eng-practices); Bugbot architecture + 2M/month + resolution
  trajectory (Cursor's own engineering blog, fetched); Shopify 400/day (Shopify engineering blog);
  bors rollups ~10/day (rust-lang forge/internals).
- **Medium confidence** (vendor blog claims not independently audited): Anthropic Code Review "<1%
  findings incorrect", 16%→54%; OpenAI "100% of PRs reviewed", "70% more PRs/week", 1M-line harness
  project (OpenAI page itself returned 403; figures from search snippets + secondary summaries of the
  same post).
- **Low confidence / unverified**: "90% of Anthropic code agent-written" (press aggregation);
  Chromium ~900 CLs/day (derived from an older design doc's 300 devs × 3 CLs); stacked-diff defect
  statistics (Graphite marketing analysis of 1.5M PRs, methodology not public); Meta mobile revert
  rates (Rossi FSE'16 PDF fetched but text not extractable — revert-percentage figures NOT obtained;
  the "critical issues ~constant despite 15x growth" claim is from Meta's blog, not the paper).
- Not found despite searching: any published quantitative threshold for when post-merge detection
  substitutes for pre-merge review depth; independent (non-Cursor) audit of Bugbot quality; GitHub
  merge queue real-world throughput ceilings.

## 5. Sources

Merge/submit queues:
- https://research.google.com/pubs/archive/45861.pdf (Taming Google-Scale Continuous Testing)
- https://abseil.io/resources/swe-book/html/ch23.html (SWE at Google, CI/TAP)
- https://xgwang.me/google-ci/ (TAP summary: 50k changes/day, 11-min wait)
- https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html
- https://blog.acolyer.org/2019/04/18/keeping-master-green-at-scale/ (Uber SubmitQueue)
- https://dl.acm.org/doi/10.1145/3302424.3303970 (SubmitQueue, EuroSys 2019)
- https://www.uber.com/blog/bypassing-large-diffs-in-submitqueue/
- https://chromium.googlesource.com/chromium/src/+/HEAD/docs/infra/cq.md
- https://www.chromium.org/developers/testing/commit-queue/design/
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- https://gitlab-docs-d6a9bb.gitlab.io/ee/ci/pipelines/merge_trains.html
- https://xampprocky.github.io/rust-forge/release/rollups.html and https://internals.rust-lang.org/t/batched-merge-rollup-feature-has-landed-on-bors/1019
- https://shopify.engineering/successfully-merging-work-1000-developers

Auto-land criteria:
- https://abseil.io/resources/swe-book/html/ch22.html (LSC, Rosie, global approvers)
- https://docs.renovatebot.com/key-concepts/automerge/ and https://docs.renovatebot.com/merge-confidence/
- https://arxiv.org/abs/2402.09171 (TestGen-LLM / Assured LLMSE)
- https://engineering.fb.com/2025/02/05/security/revolutionizing-software-testing-llm-powered-bug-catchers-meta-ach/
- https://www.usenix.org/conference/osdi23/presentation/grubic (Conveyor)
- https://research.google/blog/safely-repairing-broken-builds-with-ml/
- https://research.google/blog/accelerating-code-migrations-with-ai/

Agent review at scale:
- https://cursor.com/blog/building-bugbot and https://cursor.com/blog/bugbot-out-of-beta
- https://claude.com/blog/code-review and https://www.infoq.com/news/2026/04/claude-code-review/
- https://openai.com/index/harness-engineering/ (403 on direct fetch; via summaries incl. https://zby.github.io/commonplace/sources/harness-engineering-leveraging-codex-agent-first-world/)
- https://openai.com/index/codex-now-generally-available/
- https://arxiv.org/pdf/2601.18844 (LLM triage of static-analysis findings, industry study)
- https://arxiv.org/pdf/2604.19049 (adversarial stage-gated multi-agent review)

Rollback/canary:
- https://engineering.fb.com/2017/08/31/web/rapid-release-at-massive-scale/
- https://netflixtechblog.com/automated-canary-analysis-at-netflix-with-kayenta-3260bc7acc69
- https://cloud.google.com/blog/products/gcp/introducing-kayenta-an-open-automated-canary-analysis-tool-from-google-and-netflix
- https://www.eecg.toronto.edu/~stumm/Papers/Rossi-FSE-16.pdf (Facebook mobile CD; text not extracted)

Human review queues:
- https://sback.it/publications/icse2018seip.pdf (Modern Code Review: A Case Study at Google)
- https://google.github.io/eng-practices/review/reviewer/speed.html
- https://newsletter.pragmaticengineer.com/p/stacked-diffs-and-tooling-at-meta
- https://graphite.dev/guides/benefits-of-stacked-diffs-in-code-review
