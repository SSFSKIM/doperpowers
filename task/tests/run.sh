#!/usr/bin/env bash
# The task plugin's suite (the `task` gate): the CLI against the stand-in gh
# and sminos in tests/standin/. No network, no real board.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"
python3 -B -m unittest discover -s "$here" -p 'test_*.py' "$@"
