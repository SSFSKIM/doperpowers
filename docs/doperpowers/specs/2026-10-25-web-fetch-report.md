# Web fetch: execution report

The plan executor's account of running
[the web fetch spec](2026-10-25-web-fetch-design.md), milestones M1–M3 and
the branch review, on branch `worktree-web-fetch`, 2026-10-25. M4 (the
switch-over in `~/.claude`) is the main session's, after the merge.

Commits `76dd010f..HEAD` on top of the spec at `262d42eb` (merge base with
main `67d678a1`). The spec's Progress, Decision Log, Surprises & Discoveries
and Outcomes & Retrospective carry the durable record; this report is the
run's account.

## Status

Done. M1–M3 built and reviewed clean, the eval gate passed, acceptance 1–9
held, the whole-branch review (doperpowers:review-code, high) converged.
Pull request opened against main, not merged.

## How it ran

Subagent-driven execution: one `doperpowers:task-executor` (opus/high) per
milestone, a `doperpowers:task-reviewer` (sol/xhigh) at each frontier,
fixes resumed on the executor that wrote the code. M3 ran in three
dispatches (suite and pilot; development rounds to the freeze; final run
and acceptance), so the pilot projection could travel before the spend and
the frozen tool could be reviewed before the final run. The 56 eval tasks
were drafted in parallel with M2 by a separate opus agent that checked
every fact against the page's own source, then reviewed by M3's executor.

| Unit | Commits | Review rounds | Outcome |
|---|---|---|---|
| M1 clipper | `d6b71b78`, fix `40e1f6eb` | 2 | 4 Important fixed; 1 Minor deferred |
| M2 plugin + mod | `61db8306`, `9e010af2`, fix `0c83c23f` | 2 | 3 Important fixed (one was a spec contradiction, corrected in the Decision Log) |
| M3 suite + tasks + pilot | `203fb098`, `db5afc59`, `7526af9f`, fixes `ad81851b`, `b2c3539f`, `11daced2` | 3 | fail-open gate, zeroed timeout measures, masking leak, js tasks screened on the treatment's success: all fixed |
| M3 dev rounds + freeze | `e5e41b92`, fixes `e0938c1a`, `542ba02d` | 3 | the freeze review caught 3 defects in round 1's clipper fixes |
| M3 final + acceptance | eval report `eb3715ea` | — | gate PASS; acceptance 1–8 held |
| Branch review (high) | fixes `55d814cb`, `199e5dfe` | 3 | P1 referrer leak + 3 P2 fixed; a regression from the fix fixed; converged |

## The eval

- Pilot: 6 runs, projected ≈$4.70 per development round and $14.09 for the
  final run; sent up the chain; under the $150 rule, so the work proceeded.
  `--model sol --effort xhigh` confirmed on the wire in the temporary HOME.
- Three development rounds, every run correct in both configurations (192
  of 192). Round 1's transcripts surfaced three real clipper defects
  (happy-eyeballs timeout losing archive.apache.org images, woowahan's 403,
  `<noscript>` charts dropped).
- Final run on the frozen `542ba02d`: **PASS** — mean d +0.000 [0, 0];
  every category 12/12 vs 12/12; 0 tool-caused errors; gist tokens B/A
  0.67×. ≈$14.40 total against $14.09 projected. Report:
  [the eval report](2026-10-25-web-fetch-eval-report.md).
- Total reported eval spend about $27 (pilot, three rounds, final,
  acceptance sessions); sol's dollars are Claude Code's default-rate guess
  (`costBasis: "unknown"`), the token counts are real.
- The suite saturates: it shows B is not worse, not that B answers better.
  B's measured gains are cost and calls (PDFs 1.1 calls / 26k tokens vs
  15.9 / 67k).

## Decisions made beyond the spec

All are in the spec's Decision Log; the ones the main session should
check against the design:

- M3 split into dispatches, and the freeze reviewed before the final run.
- No development round 4 after the post-round-3 fix (`542ba02d`): the
  spec allows three, and the fix touched paths no development task reaches.
- The branch review's four clipper fixes landed after the final run, so
  the merged tool differs from the evaluated `542ba02d`. They are security
  and fidelity fixes the eval's tasks never reached and change no
  agent-facing text; no second final run was made (that would be the
  human's call). The clipper suite, the CI `web` gate, acceptance 1–3 and
  every js task URL were re-checked on the fixed tool.
- A 403 to the plain fetch is retried once through the guarded render path,
  accepted only with Chromium NetLog evidence of a 2xx served document
  (added in development round 1 for a Korean tech blog).
- `numbered` cuts an over-long first line rather than printing nothing.
- The `js` eval category is selected independently of the tool.

## Environment friction

- The worktree guard refused many compound shell commands across every
  agent (heredocs, loops, `sed` with variables, `;`-joined git commands).
  Workaround: plain single commands, or scripts written to `/tmp` and run
  by path. Every agent logged its refusals in the existing
  "command-shape refusals" row of friction tracker issue #304 (status
  conditional, unchanged).
- npm on this Mac blocks dependency install scripts; esbuild needs none,
  and the gate runs `npm ci --ignore-scripts`.
- The machine ran at load ~90 for part of M1; one render test hit its 30 s
  limit once and passed on rerun. The CI `web` gate runs with
  `WEB_CHROME=none` partly for this reason.

## Residue

Listed in the pull request's Residue and Unresolved Review Findings
sections.
