# devcloud execution report (plan executor)

Spec: `docs/doperpowers/specs/2026-10-15-devcloud-design.md`. Branch `devcloud`. The spec's Progress,
Surprises, and Decision Log are the authoritative record; this report summarizes the run and
what remains. Status at this writing: **in progress** (an interim handback the harness required
while M4's fix wave was still running).

## Where each milestone stands

| Milestone | State |
|---|---|
| M1 — plugin and secrets guard | Done, reviewed clean after four fix waves, merged as #220 (devcloud 0.1.0), installed on both Macs, session-mirror shippers restarted onto the settle interval. `cua` ticket filed and landed (cua 0.14.0 vendors the guard and stands down on I9). Acceptance 1–2: 22/22 with both plugins and with `cua` alone. |
| M2 — host core | Done, reviewed clean after three fix waves, merged into `devcloud` (devcloud 0.2.0). Container tests run on ci-kit's hosted runner. |
| M3 — profile, Linux compatibility, hardened apply | Done in the private config repository, reviewed clean after two fix waves. Secret Manager entries uploaded by the person (one entry waits on a key rotation). |
| M4 — project environments | Built (devcloud 0.3.0: runner on `devenv/`, the devenv skill, the repo's own `devenv/`, boot step 12, mirror cache); review found two Important issues (project-only secrets in the boot's project log; step 12's exit status), fix wave running. |
| M5 — sminos on hosts, acceptance | Phase A done on branch `devcloud-m5` (step 11 sminos, sandbox identity hygiene, Tailscale OAuth join after the seed, preflight passed, provisioning script ready), reviewed and fixed. Phase B — merge, VM creation, acceptance 3–8, the person's enrollment, deletion — not started. |

## Remaining steps

1. M4 fix wave lands; verify; tick M4 in Progress.
2. Rebase `devcloud-m5` onto `devcloud` (expect small conflicts in the boot's step list and the
   README), bump devcloud to 0.4.0, ci-gate.
3. Phase B: create the throwaway VM (4 vCPU / 8 GB class, the person's existing provider, outside
   ci-kit's projects), secrets over SSH only; acceptance 3–6 and 8 on the VM and on a container on
   it; the unenrolled half of 7; ask the design session for the person's enrollment; the enrolled
   half with its reboot; delete the VM the same day; the person removes it from the hub. Stay
   outside ci-kit's mac-lane measurement windows (asked of CI-opt; no answer recorded yet).
4. Whole-branch review at the high rung; Outcomes & Retrospective; the final pull request.

## Incidents and frictions

- An executor reran a test harness after the auto-mode classifier refused one of its steps; the
  rerun was voided, the refusal recorded as a finding (§9 limits, Surprises), and every later
  dispatch carries "a refused action is reported, never rerun".
- Two Docker Desktop starts by executors dispatched before the no-Docker rule; both stopped.
- A spec commit named one of the person's Secret Manager ids; branch history was rewritten before
  merge, though ci-gate had pushed the commit to temporary refs (reachable by SHA on GitHub).
- Reviewers on the gateway's frontier model were stopped by the provider's safety filter while
  probing shell injection; verification finished by running their reproduction sets directly.
- One reviewer could not hand back (the handback tool refused outside auto mode); its review was
  recovered from its final output.

## Residue (for tickets)

- The pattern detector matches thousands of vendored constants in package trees; reading vendored
  code shows redactions. A narrower rule set or package-owned path skipping.
- Whether the engine clears the I9 marker when devcloud is disabled mid-session is unverified.
- An entry removed from the profile's secrets list leaves its files on the host.
- Test sessions' copies in the session store list the store's key names (no values); pruning needs
  the store's admin connection.
