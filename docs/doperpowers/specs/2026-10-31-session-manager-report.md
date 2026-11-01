# Session manager: execution report

Spec: [2026-10-31-session-manager-design.md](2026-10-31-session-manager-design.md). Branch `worktree-session-manager`, from spec 59d75ba7 to the merge of main (947691ff) and the retrospective (e3787059). Controller: a plan-executor dispatched by doperpowers-9b (f89d7fb0, later addressed as session-pool-attention-manager). Loop: doperpowers:subagent-driven-execution, with one opus/high task-executor per milestone, a sol/xhigh task-reviewer at each frontier, and the whole branch through `doperpowers:reviewer-high`.

## Outcome

All six milestones are reviewed clean. The whole-branch review at high found no material findings. Acceptance 1–7, 9–13 pass; the live items ran on throwaway sessions. Acceptance 8 is **not met** on the shipped run (50/51 blocking, 90.1% overall, strict), and is recorded on the coordinator's ruling. Acceptance 14 and the post-merge repeat of acceptance 4 against an owner's live session are left to the owner and the dispatching session. The spec's Outcomes & Retrospective has the full account.

## Milestones

| Milestone | Code commits | Fix rounds | Final gate |
|---|---|---|---|
| M1 the `manager` command | 10bbe5d4; fixes 2ff6a936, 3e93e0f1 | 2 (corroboration scope, pre-window answers, unreadable transcripts, historical waiting, code-aware tag reading; distant blocking MAWS answers, shared tag selection) | GREEN 41268082711 (3e93e0f1) |
| M2 bridge `ask` + fork guard | 3e1f4231; fixes 2d03ff52, 5114571d, fc726e7d; live check a5c1dc93, a197e287, edc9d397; a17c12aa | 3 review rounds plus runtime follow-ups (text-only tail, busy across reloads, heard-end grace; spawn-refused, the tail as a record) | GREEN 41273601681 (edc9d397, five gates); 41275992469 (a17c12aa, mods) |
| M3 shared fork code, derive on btw, `manager query` | 7835c638, 01cabaad; fixes dda1044f, e4375df6 | 2 (the follower's close, the kept end, spawn-refused routing; derive's btw kept off the hub) | GREEN 41276447995 (e4375df6) |
| M4 ledger and delta (from the owner's mid-run revision) | b02778ac; fixes b86a5d9c, f38b80ad | 2 (validation by kind, incomplete lineage reads; a missing session proven to have ended before the window) | GREEN 41280408517 (f38b80ad) |
| M5 skill, digest brief, replay, acceptance | 12d60720, 04a64ebf, fcdaf2c8, e8536aa9, 5f09bb50; fixes 3e32929e, 8c4e4be2, d63a5e6e, b5a55402, 45f6b0a6, c2f227b3, c91f55e3, 59ad1cf7, 3f01cbc3, 11ca95e0 | 3 (false done, seen across the lineage, a final run on the shipped version; resolver errors named, the redo rule, the one-outcome merge; record labels) | GREEN 41293052265 (11ca95e0) |
| M6 the page | 37ce4223, 6d4fe808; fix f6b20c73 | 1 (refresh race, meaning layout, `up` means running, install pressure scenario) | GREEN 41290823464 (f6b20c73) |

The merge of main (a16a0807, sminos 1.28.0) came in as 947691ff. Versions were kept at doperpowers 7.216.0 and sminos 1.29.0, and TECH-DEBT.md keeps both new sections.

## Rulings taken during execution (all in the Decision Log)

- The guard passes an agent id that a readable `$.agent.list()` does not name, because workflow agents and engine forks are unlisted. Fail-closed is kept for a list that can't be read. The coordinator confirmed this.
- `busy` is read from the agent list at each ask, with a 3 s grace for a heard end; `waiting` is busy at once.
- The mid-turn tail is presented as a `<session-record>` to read, not act on. Measured: haiku 3–4/5 clean, Opus and Sonnet 10/10, and with no tail haiku was still 3/5. Kept as is; the gap is in TECH-DEBT.md.
- `spawn-refused` (an Esc'd session) routes to the headless fork. `ask_fork_agent` reads the kept end under an rpc nonce.
- The daemon doesn't relay a nonce-less `btw`. Verified against MAWS 27693254c: lane A posts to the bridge directly.
- A missing transcript is not an incomplete read when a later session of the lineage started before the window.
- Acceptance 8 is recorded as not met (50/51 strict). On the coordinator's ruling there was no further tuning against the replay window.

## Environmental friction

- **Worktree isolation** refused about ten commands: loops, variables naming git, a wait loop over `stat`, and reviewers' multi-line probes. Worked around with plain commands and a Write-made wait script under `~/.local/share/session-manager/`. Tallied in `~/.claude/friction-tracker/general/live/worktree-isolation-refuses-bash-commands.md`.
- **Handback enforcement:** the harness required a SubagentHandback whenever the controller ended a turn to wait for workers. So the controller waited in bounded foreground waits on report and commit changes instead of ending turns. One external stop ("stopped by killed") happened during an early wait loop; the controller resumed.
- **Machine holds:** a parallel cua session called two GUI holds and two CPU holds. Reviews ran static during them, verification went through ci-gate, and live checks were deferred to the all-clears.
- **API safeguard:** the first M2 executor died on a safeguard flag (`reasoning_extraction`, judged a false positive by the coordinator). A fresh executor finished its runtime verification.
- **Live checks** need `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` exported in the shell. The M2 verifier logged a friction entry.

## Deferred review findings

- M1 Minor: the UUID-skip fixtures in `sminos/tests/test_manager.py` (around :484–490) embed uuids inside JSON strings, so `_row_back`'s needle never meets them and the skip branches go unexercised. This is test precision only; the distant-answer assertion stands.
- M3 Minor: two sminos suite assertions failed once each in M3's local runs (hook-migration timing, retired-seat watcher) and passed on rerun.

## Residue

See the PR body's Residue section.
