# devcloud VM driver: execution report

- Spec: `docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md`
- Branch: `devcloud-vm`. The execution started from spec commit 11c928a7, and origin/main was merged in three times.
- Executed: 2026-10-21. A controller ran subagent-driven execution, with one task-executor per milestone and a task-reviewer at each frontier.

## Status

All six milestones are complete and reviewed clean. Acceptance 1–13 passed live on the default GCE account.

The whole-branch review ran at the high rung and took three rounds:
- 8 findings in the first round: 7 fixed, 1 deferred.
- 2 new findings in the second round, both fixed.
- The third round is the closing check.

The `devcloud`, `shell-lint` and `repo-checks` gates are green at every gated head. devcloud is now 0.7.0. Every live resource was deleted the same day.

The only open human step is H6: the parent's leftover `devcloud-m5` is still listed at the desk. It is the person's to remove on the desk's Machines page.

## Milestones

| | What | Commits (fixes) | Reviews |
|---|---|---|---|
| M1 | Spike: preflight and live facts (H1, H2 by the controller; H8 new) | spike only | none (spike) |
| M2 | Host side: leases, departure, release and its ledger, the closed port, enrollment, desk control | 810bc1b3 (b2a45d4f, 2b001c56, b2716a69) | 3 rounds |
| M3 | Driver core, provider protocol, Hetzner provider, reaper | b06944fc..2e7d699f (bd50512b, aee127fc) | 3 rounds; one finding accepted as best-effort |
| M4 | Images and project host files | 516d5215, 3b2c2284 (dbf3ea68, 96f2993c) | 2 rounds |
| M5 | GCE provider, adopt, open provider path | ea1464f5..5a6bf8c6 (844ff710, de23fa04, 66b2c551, 342a6ed5) | 3 rounds |
| M6 | Skill, always-on Mac, acceptance, release | 7cf40bdb..d7efe1e1 (c309ac4b, 1634e7b9, 554d3e42) | 2 rounds |
| Branch review | Seams of adopt, release and boot; image architecture | 1141f074..7e02bdad, bb8e39bf | 3 rounds |

The per-milestone reports (`task-1..7`) live in `.doperpowers/sde/2026-10-21-devcloud-vm-driver-design/`, which is gitignored. The spec's Progress, Surprises and Decision Log carry everything from them that matters.

## Live evidence (GCE default account unless named)

| Check | Result |
|---|---|
| Acceptance 1 | `up` from an image was ready in 3m22s, enrolled by the provisioning key with no code |
| Acceptance 6 | slow path 5m12s |
| Acceptance 3 | an operator prompt reached a seat as the human's words; a permission card on the desk was answered with Allow, and the tool call proceeded (relayed by the bridge) |
| Acceptance 4 | every cap refused an unconfirmed request; a confirmed fourth VM was created |
| Acceptance 5 | the warning reached the creating session after 8m22s and named the unpushed commit; the departure left the desk and the tailnet; the always-on Mac's scheduled reaper deleted the VM 15m30s after the lease end |
| Acceptance 7 | a hand-made Ubuntu server was adopted, then released with every ledgered path, unit and nft table gone; the original login worked over a new SSH, also after a reboot |
| Acceptance 13 | a profile provider passed the full open path: registered (H7, the person's approval), tested, used, a broken edit caught, and a passing edit adopted |
| Acceptance 12 | 0 profile values in the branch diff |
| Acceptance 2, 8, 9, 10, 11 | all pass |

The figures, the times and the deletion list are in the spec's Surprises and Progress, and in the M5 and M6 task reports.

## Human steps

| Step | Result |
|---|---|
| H1, H2 | done at M1 by the controller; the classifier allowed the writes |
| H3 | done early by the person |
| H4 | the `dc-` key exists; its `offline_revoke_s` is null by the owner's ruling (Decision Log) |
| H5 | not needed |
| H7 | approved by the person twice, for M5 and for M6 |
| H8 | answered: GCE became the default account |
| H9 | declined |
| H6 | **open** |

## Post-merge steps (the always-on Mac)

Until the merge, the always-on Mac's launchd reaper (`com.doperpowers.devcloud-reap`) runs a scratch checkout of this branch at `~/Developer/devcloud-vm-scratch`. After the merge:

1. Update the marketplace clone, so that it holds the merged devcloud.
2. From a login shell on that Mac, run `~/.claude/plugins/marketplaces/doperpowers/devcloud/bin/devcloud vm reap --install`.
3. Check that the plist's `ProgramArguments[0]` points into the clone.
4. Remove `~/Developer/devcloud-vm-scratch`.

`hcloud`, the driver key and `~/.local/state/devcloud/` stay where they are.

## Friction

- **IPv6.** The LAN of both Macs advertised IPv6 without routing it, so every Google API call first waited out the IPv6 attempt. The design session fixed the network, and the timings were measured again afterwards.
- **Outages.** The model gateway on the always-on Mac was refused for several hours, which stalled the agents; they were resumed rather than respawned. The always-on Mac was also offline for a while.
- **Leaked processes from main's tests.** Orphaned `sleep 0.05` loops from a SupervisorTest on main leaked; main fixed this in #318. A hook refused `pkill`, so the loops were killed by PID.
- **A desk key's prefix.** H4's first key had a prefix the VM did not accept, and the person made it again.
- **The profile's guardrail.** The person's profile has a Bash guardrail that pre-approved commands, so the desk's permission card did not appear. The person has since removed it. This is logged in the friction tracker (#304).
- **The pricing catalog fetch** hung or returned 401, and was abandoned. The gce provider reads catalog prices with a 7-day cache instead.

## PR

https://github.com/SSFSKIM/doperpowers/pull/333 is open, ready for review, and not merged. CI is green on its head 8bc33586: https://github.com/SSFSKIM/doperpowers/actions/runs/39683608925.

## Residue

These are in `docs/doperpowers/TECH-DEBT.md`, under "the devcloud VM driver", and in the PR's Residue section.
