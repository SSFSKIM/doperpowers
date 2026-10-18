# devcloud execution report (plan executor)

Spec: `docs/doperpowers/specs/2026-10-15-devcloud-design.md`. Its Progress, Surprises, Decision Log and Outcomes are the authoritative record; this report summarizes the run. **Status: done.** All five milestones are reviewed clean and the whole-branch review at the high rung has converged. The final pull request takes `devcloud` to main.

## Milestones

| Milestone | Result |
|---|---|
| M1: the plugin and its secrets guard | Merged as #220 (devcloud 0.1.0) and installed on both Macs. The `cua` ticket (#154) landed as cua 0.14.0, which vendors the guard and stands down on I9. Acceptance 1–2: 22/22 with both plugins, 22/22 with `cua` alone. Four fix waves. |
| M2: host core | Image, boot program, materializer, pull-only config, supervisor, `devcloud` gate. Three fix waves at task review, plus two at the final review (services). |
| M3: profile, Linux compatibility, hardened apply | In the private config repository. Two fix waves. The person uploaded the Secret Manager entries; one entry waits on a key rotation. |
| M4: project environments | `devenv` runner on `devenv/`, the devenv skill, the repository's own `devenv/`, boot step 12, mirror cache (devcloud 0.3.0). Three fix waves. |
| M5: sminos on hosts, acceptance | Step 11's sminos part, sandbox identity hygiene, and the Tailscale OAuth join after the seed (devcloud 0.4.0). Acceptance 3–8 passed on a throwaway VM and on a sandbox container on it, including the enrolled half of 7. VM deleted the same day (21:05–22:34 UTC). |
| Final review (high rung) | Five service findings (journald redaction, stream scrubbing, owed restarts, boot-gated services, bounded stops), then one regression (a boot run by hand). Fixed. devcloud 0.4.1. |

## Incidents and frictions

- **A rerun after a refusal.** An executor reran a harness after the auto-mode classifier refused a step. The rerun was voided and the refusal recorded as a finding. Every later dispatch carried "a refused action is reported, never rerun".
- **Docker started against the rule.** Two executors started Docker Desktop before the no-Docker rule reached them; both were stopped. The real container acceptance then ran on the VM.
- **A secret's id leaked.** A spec commit named one of the person's Secret Manager ids. Branch history was rewritten before merge, but CI's temporary refs had already pushed the commit, so it stays reachable by SHA on GitHub.
- **Reviewers stopped mid-probe.** The provider's safety filter stopped two reviewers on the gateway's frontier model while they probed shell injection. Verification finished by running their reproduction sets directly.
- **A reviewer's report stuck.** One reviewer could not use the handback tool outside auto mode; its report was recovered from its final output.
- **Machine overload.** The MacBook ran at load ~600, with the cause outside our agents. Local timeouts that passed in isolation were treated as environmental; none was loosened.
- **Enrollment command bug.** The command as first given had root's shell expand `~` before switching users. It was corrected in the README and the report.
- **Uploads and enrollment by hand.** The person ran the Secret Manager uploads because the classifier refuses an agent reading credential sources into a store.

## Residue (for tickets)

- **Detector noise.** The pattern detector matches thousands of vendored constants in package trees, so reading vendored code shows redactions. Fix with a narrower rule set or by skipping package-owned paths.
- **Marker lifetime.** It is unverified whether the engine clears the I9 `$.state` marker when devcloud is disabled mid-session.
- **Orphaned secret files.** An entry removed from the profile's `secrets.toml` leaves its files on the host.
- **Session store copies.** The session store's copies of the acceptance test sessions list the store's key names, not their values. Pruning needs the store's admin connection.
- **Ephemeral tailnet nodes.** Throwaway and test hosts should probably join with `ephemeral=true`, so the tailnet node removes itself when the host goes away. Today every host joins non-ephemeral, and each torn-down VM leaves a manual node removal. This is a design question.
- **sminos daemon output.** The daemon's own user unit, written by `sminos daemon install`, sends its output to journald unscrubbed.
- **Driver note.** Sandbox containers need the tailnet's DNS (`--dns 100.100.100.100`) to resolve the gateway's name.
