# Routine triage fast path — design record

**What.** An event-driven fast path for ida-solution feedback triage, built
on Claude Code cloud routines: a feedback INSERT fires a cloud session that
runs the `triaging-feedback` skill's **Worker mode** and files the board
ticket within minutes. E2E-verified 2026-07-12 with two dogfood rows
(ida-solution #517 — risk-surface case correctly parked `needs-human`;
#519 — synthetic data correctly recognized, not fabricated; both closed as
test artifacts).

**Why it exists next to the poller.** The poller
(`skills/triaging-feedback/`) is the authoritative state machine — atomic
claim/lease, code-enforced gate, `triage_state` writeback — but it is
10-minute polling on a host that must exist (VM tenant:
`infra/worker-host/` §5, not yet provisioned). The routine is the inverse
trade: zero infra, minutes-level latency, prompt-enforced protocol, a daily
run cap. They compose instead of competing:

- **Routine = fast path.** Fires per row, files the ticket.
- **Poller = reconciler.** Rows the routine missed (cap overflow, fire
  failures) stay `pending` and get swept; rows the routine handled are
  recognized by the `<!-- feedback:<id> -->` marker (`findExisting`) and
  written back without a duplicate ticket. GitHub is the shared
  idempotency store — no coordination channel was added.

## Wiring (consumer side, lives in ida-solution's Supabase)

`public.feedback` AFTER INSERT trigger `feedback_fire_triage` →
`net.http_post` to
`POST /v1/claude_code/routines/<trig_id>/fire` with
`{"text": row_to_json(new)}` (fire token from Supabase Vault). The routine's
cloud environment preinstalls the doperpowers plugin; the routine
instructions are two sentences (payload contract + "invoke
doperpowers:triaging-feedback, follow Worker mode") plus a fail-loud guard
(skill missing → report, never improvise). Plugin-side contract shipped as
`06a4bec` (Worker mode section), `fb819ab` (connector fallback — register
via built-in issue tools when no `gh` credential), later extended by
`a5cc33c`/`351bf0d` (dev-code trust path).

## Facts that will bite later

- **Cloud sessions ignore checked-in `.claude/settings.json` plugin
  declarations** (auto-install is tied to the interactive trust dialog).
  Environment setup script with `claude plugin marketplace add` +
  `claude plugin install` works headlessly — verified by isolated local
  test. Do NOT `npm ci` in the setup script: its cwd is not the repo
  (snapshots build repo-independent).
- **Plugin version freezes at snapshot time.** To pick up skill changes,
  touch the setup script (comment edit) to force a rebuild; cache also
  expires ~weekly.
- **The DB trigger swallows fire failures** (`exception → return new`
  protects the INSERT), so the only health signal is
  `net._http_response` — watch for 429 (daily cap: 15 runs/day on Max,
  shared with subscription usage) and 401 (token rotated but Vault stale).
- **Fire is not idempotent** (each POST = new session); the INSERT trigger
  makes it naturally once-per-row. Webhook-style retries would need the
  marker search to hold the line.
- **Vault quirk:** the secret's *name* is the routine-id string, its
  *value* is the fire token. Rotation = `vault.update_secret` value only
  (and the smoke-test copy in the operator's `~/.zshrc`). Regenerating the
  token in the routine UI revokes the old one.
- **Connector scope:** the GitHub proxy credential reaches every repo the
  connected account sees (pushes restricted to the working branch). Wider
  than the issues-only PAT the design wanted; accepted because the org
  gates fine-grained PATs. Narrowing path: org-approved PAT (bundle with
  the runner request, ida-solution#302).

## Escalation triggers

- Feedback volume approaching ~15/day → provision the VM poller
  (`infra/worker-host/`), demote the routine to overflow/latency helper or
  retire it.
- An observed gate violation by the routine (fabricated citation,
  ready-for-agent on a risk surface) → the prompt-enforced tier failed;
  poller-only until the protocol is hardened (same posture as TECH-DEBT
  #7's escalation).
