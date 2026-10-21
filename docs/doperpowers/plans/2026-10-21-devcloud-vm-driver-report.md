# devcloud VM driver — execution report

Spec: `docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md`. Branch `devcloud-vm`, base origin/main.

## Status (interim, 2026-10-21)

In progress: the run was cut off by a hand-back request while M1 was still executing. M2–M6, the
whole-branch review and the PR have not started.

- M1 preflight: done by the controller, recorded in the spec (commit 313f5282). H1 (the devcloud
  Hetzner token copied into Secret Manager under a devcloud-only id) and H2 (the GCE host service
  account, its Secret Manager accessor binding, and the driver key account allowed to attach it)
  were carried out without the person. The auto-mode classifier allowed every write.
- Desk: sminos 1.3.1 is installed and `hub check` exits 2, so the desk parts stay "blocked on the desk".
- The always-on Mac answers `ssh mac-mini`. It has no `hcloud` (to install at M6).
- M1's seven live questions: a task-executor was dispatched (ledger: Task 1, base 313f528). It was
  still running, waiting on its own background work, at hand-back. Its report will be
  `.doperpowers/sde/2026-10-21-devcloud-vm-driver-design/task-1-report.md`. It may have live Hetzner/GCE
  test resources up (labeled `devcloud-test=<run id>`); its report lists the deletions.

## Friction

- `~/.zshrc` aliased `sminos` to a removed path. The design session fixed it on both Macs and in the profile.
