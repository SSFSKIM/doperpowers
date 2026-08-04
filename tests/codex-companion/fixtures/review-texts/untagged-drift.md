# Codex Review

Target: branch diff against origin/main

The IMPACT cursor shares the daemon registry's filename namespace, polluting daemon telemetry and making non-daemon state addressable by daemon commands. The lane-aware wake behavior also leaves its behavior-shaping skill contract stale.

Full review comments:

- Move the sweep cursor outside the daemon registry
  After the first successful IMPACT pass, this creates a valid top-level `$DAEMON_HOME/impact-scan.json`, but daemon tooling treats every top-level `*.json` except `*.reply.json` as daemon metadata: `daemon-list.sh` adds it as a bogus fleet row, and `_resolve_uuid` resolves `impact-scan` as a daemon, allowing commands such as `daemon-retire.sh` to corrupt or delete the cursor. Store this state outside the registry namespace or make registry readers validate daemon metadata shape.

- Document the lane-aware wake state
  When a review ticket was parked from `in-review`, this now returns it to `in-review`, but the published command contract still says `board-answer.sh` always returns the ticket to `in-progress` ([SKILL.md:167](skills/issue-tracker/SKILL.md#L167)). Because skill content shapes agent behavior in this repository ([CLAUDE.md:34](CLAUDE.md#L34)), update the command table to describe the lane-aware return semantics.
