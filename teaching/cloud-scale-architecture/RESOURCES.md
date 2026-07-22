# Resources

## Primary (this repo — highest trust, the actual design record)

- **The spec** — `docs/doperpowers/specs/2026-07-23-cloud-scale-reference-architecture-design.md`
  (design of record; Decision Log carries every rejected alternative)
- **Research synthesis** — `docs/doperpowers/2026-07-23-cloud-scale-research.md`
  (all load math, vendor limits, verdicts; review-corrected)
- **Full agent reports** — `docs/doperpowers/research/2026-07-23-cloud-scale/*.md`
  (10 deep-read/deep-research reports with per-claim confidence notes)
- **Lineage docs** — `docs/doperpowers/2026-07-11-symphony-comparison.md`,
  `docs/doperpowers/2026-07-12-managed-agents-steals.md` (the single-host
  decisions this architecture re-judged)

## External primary sources (verified during research)

- Cursor, *What we've learned building cloud agents* — cursor.com/blog/cloud-agent-lessons
  (the one-nine→two-nines Temporal migration; the founding failure story)
- Cursor, *Agent swarms and the new model economics* — cursor.com/blog (economics frame)
- Anthropic, *Scaling Managed Agents* — anthropic.com/engineering/managed-agents
  (session/harness/sandbox decoupling; + platform.claude.com self-hosted-sandboxes docs)
- Google TAP — research.google.com/pubs/archive/45861.pdf + SWE-at-Google ch. 23
- Uber SubmitQueue — EuroSys 2019, "Keeping Master Green at Scale"
- Firecracker snapshot caveats — github.com/firecracker-microvm/firecracker
  docs/snapshotting/snapshot-support.md
- GKE Agent Sandbox — docs.cloud.google.com/kubernetes-engine/docs/how-to/agent-sandbox
- Linear rate limits — linear.app/developers/rate-limiting
- GitHub secondary limits — docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

## Communities (wisdom)

- Temporal community forum (durable execution war stories)
- r/kubernetes, Kubernetes Slack #sig-scheduling (Kueue/fairness practice)
- Hatchet Discord (Postgres-queue practitioners)
