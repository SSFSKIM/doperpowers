# Arming the board sweep (unattended dispatch)

`scripts/board-sweep.sh` is the unattended tick: every ~5 minutes it
recovers dead workers, cancels workers on closed tickets, dispatches
Executor workers onto ELIGIBLE tickets (cap-bounded), attaches the review
loop to open PRs, reports a ticket whose dependency has stopped moving, and
relays fresh `needs-human` ticket comments to the
parked worker that asked. It is mechanical (no model calls) and idempotent —
overlapping or repeated ticks are safe, and all state lives in GitHub and
the daemon registry.

Arming the sweep IS the opt-in: nothing runs until you install a timer for
it. One timer per consumer repo (the sweep is scoped by `LOCAL_REPO`).

The sweep assumes a PRIVATE, trusted board — the same posture the runner
templates state as "PRIVATE REPOS ONLY": RELAY treats any non-machine
comment on a parked ticket as the human's answer, so anyone who can
comment can steer a parked worker. RELAY also reads only the ticket's
newest comment — if a machine comment lands after your answer (or a very
long ticket outgrows one comments page), the answer is silently missed;
the remedy is to comment again.

## macOS and TCC — read this first

If the plugin checkout or the target repo lives under `~/Documents`,
`~/Desktop`, or `~/Downloads`, a launchd- or cron-launched shell CANNOT
read it — macOS folder protection denies with `Operation not permitted`
(verified live 2026-07-18: `launchctl submit -- /bin/ls ~/Documents/GitHub`
→ EPERM, while the identical sweep ran clean from a terminal). Pick one:

- **Grant access once**: System Settings → Privacy & Security → Full Disk
  Access (or Files and Folders → Documents) → add `/bin/bash`. The
  launchd agent below then works as-is. Broadest fix, one gesture; note
  it widens what ANY launchd bash job on this machine can read.
- **Terminal-session timer**: run the tick loop from any terminal/tmux
  session (TCC flows from the terminal app) —
  `while true; do board-sweep.sh; sleep 300; done` detached with nohup.
  Survives the session, not a reboot; re-arm after restarts. The mkdir
  lock + idempotence make it safe to ALSO leave the launchd agent loaded:
  whichever timer fires, one tick runs.
- **Relocate**: keep the plugin checkout and repo clone outside the
  protected folders; the launchd agent needs no grant at all.

## launchd (macOS)

A launchd **user agent** (not a system daemon) — save as
`~/Library/LaunchAgents/com.user.doperpowers-board-sweep.plist`
(set `LOCAL_REPO` — the one placeholder — to your repo clone's absolute
path):

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
      "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0"><dict>
      <key>Label</key><string>com.user.doperpowers-board-sweep</string>
      <key>StartInterval</key><integer>300</integer>
      <key>ProgramArguments</key><array>
        <string>/bin/bash</string>
        <string>-lc</string>
        <string>"${DOPERPOWERS_HOME:-$HOME/.claude/plugins/marketplaces/doperpowers}/skills/issue-tracker/scripts/board-sweep.sh"</string>
      </array>
      <key>EnvironmentVariables</key><dict>
        <key>LOCAL_REPO</key><string>/ABSOLUTE/PATH/TO/YOUR/REPO/CLONE</string>
        <key>AUTO_MERGE_ENABLED</key><string>true</string>
        <key>IMPLEMENT_MAX_CONCURRENT</key><string>5</string>
      </dict>
      <key>StandardOutPath</key><string>/tmp/board-sweep-launchd.log</string>
      <key>StandardErrorPath</key><string>/tmp/board-sweep-launchd.log</string>
    </dict></plist>

`bash -lc` loads your login profile, so `gh`, `python3`, and `claude`
resolve exactly as they do in your terminal. `AUTO_MERGE_ENABLED` arms
merging for the QA agents the sweep's seats dispatch on their own PRs —
drop the line to keep them in observation mode (review + park, no merge).

Arm / un-arm / observe:

    launchctl load  ~/Library/LaunchAgents/com.user.doperpowers-board-sweep.plist
    launchctl unload ~/Library/LaunchAgents/com.user.doperpowers-board-sweep.plist
    tail -f ~/.claude/sminos/sweep.log

The sweep's own log (per-pass actions and skips, self-truncating at 1 MB)
is `$DAEMON_HOME/sweep.log`; the launchd file above only catches
environment-level failures.

## cron (any Unix)

    */5 * * * * DOPERPOWERS_HOME=$HOME/.claude/plugins/marketplaces/doperpowers LOCAL_REPO=/path/to/repo AUTO_MERGE_ENABLED=true bash -lc '$DOPERPOWERS_HOME/skills/issue-tracker/scripts/board-sweep.sh'

macOS caveat: plain cron runs outside your login session — daemons spawned
from it can lose TCC grants (observed: fleet-wide `exit 1 before init`).
Prefer the launchd user agent on macOS; verify the first live tick's spawns
actually run before trusting a cron arming.

## Knobs

| env | default | meaning |
|---|---|---|
| `IMPLEMENT_MAX_CONCURRENT` | 5 | implement/spike worker slots — counted over IMPLEMENT/SPIKE-role workers from `ready-for-implementer` through `in-progress`; a seat whose ticket sits in `in-review` is reviewing its own PR and spends none, and a review stand-in is counted in its own registry |
| `ARCHITECT_MAX_CONCURRENT` | 1 | architect-lane slot cap — the Fable-spend lever; counted over ARCHITECT-role workers from `ready-for-architect` through `in-progress` (an Architect executes its own plan), separate from the implement cap. The default 1 now spans design plus build; raise it when queued design work waits on a long build |
| `ARCHITECT_MODEL` | fable | model pin for the architect route — plan authorship is the frontier tier |
| `IMPLEMENT_MODEL` | sol | model pin for the implement and spike routes — the worker tier. Pinned, not inherited: an operator whose own session runs the frontier model would otherwise pay frontier rates on both lanes and collapse the split's economics |
| `REVIEW_MODEL` | sol | model pin for the review stand-in seat the review dispatcher spawns on a PR nobody owns, the same tier and for the same reason |
| `SWEEP_STALL_MINUTES` | 45 | a live worker silent this long is resumed with a nudge |
| `SWEEP_RECOVERY_CAP` | 3 | lifetime sweep-initiated resumes per daemon, then park `needs-human` |
| `SWEEP_STALL_DEPENDENCY_MINUTES` | 2880 (48h) | a BLOCKER unworked and silent this long parks the ticket waiting on it, `needs-human`, with the blocker and the chain in the note. The other half of the same doctrine as the API board's `DEPENDENCY_STALL_MS`; raise it on a board with a weekly human cadence. A dependency CYCLE is reported at once — it needs no clock |
| `BOARD_STALL_ATTEMPTS` | 3 | *api binding.* Lifetime nudges per run for a worker whose turn died on a harness error (a 429, a hit usage limit, a 529). Spent, the tick ENDS that run — the ticket returns to needing-resume and the resume phase's successor path takes over |
| `BOARD_STALL_WINDOW_MIN` | 15 | *api binding.* Minutes to wait before the first nudge when the error states no reset time, and between nudges always |
| `BOARD_STALL_MAX_WAIT_MIN` | 360 | *api binding.* Ceiling on a stated reset time the tick will WAIT for. A weekly limit resets days out; honouring it would renew the lease and hold the ticket silently for all of them, so past the ceiling the ordinary window applies, the ladder runs out, and the outage reaches a human through `BOARD_STALL_CYCLES` below |
| `BOARD_STALL_CYCLES` | 3 | *api binding.* Harness-error ladders ONE TICKET may run out before the tick stops spending recovery on it. The per-run ladder above resets on every successor, so on its own it never accumulates — a fault that outlives its worker (an expired login, a multi-day weekly limit) would churn a fresh successor every hour and tell nobody. This count survives successors, is cleared only by a worker that answers as itself again, and ends at an env-issue plus a suppression |
| `AUTO_MERGE_ENABLED` | off | the review merges its confident verdicts (off = observation mode: review and park, no merge). Set it to `true`/`1`/`on`/`yes` to arm; anything else reads as off. Read by both dispatchers: the review dispatcher, which arms the stand-in it spawns on a PR nobody owns, and the execute dispatcher, which hands it to every Executor and Architect for the QA agent they dispatch on their own PR |
| `REVIEW_LEVEL` | medium | that review's level floor (`low`/`medium`/`high` run one reviewer, `xhigh`/`max` the panel). Read by both dispatchers, and an unknown value refuses the tick before any spawn |

## The event path (lower latency, needs a runner)

The sweep is the transport that needs nobody's permission. When the repo
also has a registered self-hosted runner (label `claude-review` — see
`references/runner-setup.md`), GitHub events can
dispatch the latency-sensitive lanes directly; the sweep stays as catch-up:

- PR opened → review stand-in: `references/pr-review-dispatch.yml`
- issue becomes ready → Executor worker: `references/issue-dispatch.yml`

Both templates keep the same security posture: no checkout of PR code,
`permissions: {}`, numeric-only interpolation, actor allowlist.
