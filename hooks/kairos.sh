#!/usr/bin/env bash
# kairos — SessionStart hook. A session launched with KAIROS=1 gets the kairos
# skill body injected at startup and again after every compaction, so
# proactive mode outlives the context that first carried it. Any other session
# gets nothing. The trigger is the environment, deliberately not a machine-wide
# flag: dispatched workers are sessions too, and a file would switch all of
# them. The body is read from the skill itself so `/kairos` and this hook can
# never drift apart.
set -euo pipefail

case "${KAIROS:-}" in 1|true|on) ;; *) exit 0 ;; esac

skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills/kairos/SKILL.md"
[ -f "$skill" ] || exit 0

# The body only: the frontmatter is the skill listing's, not the session's.
awk 'seen > 1 { print } /^---$/ { seen++ }' "$skill"
