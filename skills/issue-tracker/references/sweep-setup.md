# Arming the board sweep (unattended dispatch)

`scripts/board-sweep.sh` is the unattended tick: every ~5 minutes it
recovers dead workers, cancels workers on closed tickets, dispatches
implement workers onto ELIGIBLE tickets (cap-bounded), attaches the review
loop to open PRs, dispatches a land worker when a human has Approved a
`confident-ready` PR, and relays fresh `needs-human` ticket comments to the
parked worker that asked. It is mechanical (no model calls) and idempotent —
overlapping or repeated ticks are safe, and all state lives in GitHub and
the daemon registry.

Arming the sweep IS the opt-in: nothing runs until you install a timer for
it. One timer per consumer repo (the sweep is scoped by `LOCAL_REPO`).

## launchd (macOS — recommended)

A launchd **user agent** runs in your login session, which keeps TCC
(privacy) grants intact for the daemons the sweep spawns — the known
failure mode of cron-context spawning on macOS. Save as
`~/Library/LaunchAgents/com.user.doperpowers-board-sweep.plist`
(adjust the three UPPERCASE placeholders):

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
        <key>LAND_ENABLED</key><string>true</string>
        <key>IMPLEMENT_MAX_CONCURRENT</key><string>5</string>
      </dict>
      <key>StandardOutPath</key><string>/tmp/board-sweep-launchd.log</string>
      <key>StandardErrorPath</key><string>/tmp/board-sweep-launchd.log</string>
    </dict></plist>

`bash -lc` loads your login profile, so `gh`, `python3`, and `claude`
resolve exactly as they do in your terminal. `AUTO_MERGE_ENABLED` /
`LAND_ENABLED` arm the two merge tiers for workers the sweep dispatches —
drop either line to keep that tier in its default (off / dry-run) mode.

Arm / un-arm / observe:

    launchctl load  ~/Library/LaunchAgents/com.user.doperpowers-board-sweep.plist
    launchctl unload ~/Library/LaunchAgents/com.user.doperpowers-board-sweep.plist
    tail -f ~/.claude/orchestrating-daemons/sweep.log

The sweep's own log (per-pass actions and skips, self-truncating at 1 MB)
is `$DAEMON_HOME/sweep.log`; the launchd file above only catches
environment-level failures.

## cron (any Unix)

    */5 * * * * DOPERPOWERS_HOME=$HOME/.claude/plugins/marketplaces/doperpowers LOCAL_REPO=/path/to/repo AUTO_MERGE_ENABLED=true LAND_ENABLED=true bash -lc '$DOPERPOWERS_HOME/skills/issue-tracker/scripts/board-sweep.sh'

macOS caveat: plain cron runs outside your login session — daemons spawned
from it can lose TCC grants (observed: fleet-wide `exit 1 before init`).
Prefer the launchd user agent on macOS; verify the first live tick's spawns
actually run before trusting a cron arming.

## Knobs

| env | default | meaning |
|---|---|---|
| `IMPLEMENT_MAX_CONCURRENT` | 5 | implement/spike worker slots (review/land workers never count) |
| `SWEEP_STALL_MINUTES` | 45 | a live worker silent this long is resumed with a nudge |
| `SWEEP_RECOVERY_CAP` | 3 | lifetime sweep-initiated resumes per daemon, then park `needs-human` |
| `WORKER_ENGINE` | codex | default model route; an `engine:*` ticket/PR label wins |
| `AUTO_MERGE_ENABLED` | false | review worker's trivial-tier self-merge |
| `LAND_ENABLED` | false (dry-run) | land worker merges for real |

## The event path (lower latency, needs a runner)

The sweep is the transport that needs nobody's permission. When the repo
also has a registered self-hosted runner (label `claude-review` — see
doperpowers:reviewing-prs `references/runner-setup.md`), GitHub events can
dispatch the latency-sensitive lanes directly; the sweep stays as catch-up:

- PR opened → review worker: `reviewing-prs/references/pr-review-dispatch.yml`
- issue becomes ready → implement worker: `implementing-tickets/references/issue-dispatch.yml`
- PR review approved → land worker: `reviewing-prs/references/land-on-approve.yml`

All three templates keep the same security posture: no checkout of PR code,
`permissions: {}`, numeric-only interpolation, actor allowlist.
