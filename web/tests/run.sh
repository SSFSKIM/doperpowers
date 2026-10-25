#!/usr/bin/env bash
# The web plugin's whole suite (the `web` gate): the clipper's tests, the
# check that the committed bundle (bin/clip.mjs) is what its source and
# lockfile build, and the mod's tests. Tests that need Chromium or pdftotext
# skip, with the reason printed, where those are absent or WEB_CHROME=none.
set -euo pipefail

web="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== the clipper's tests"
(cd "$web/clipper" && npm ci --no-audit --no-fund && npm test)

echo "== the bundle matches its source"
(cd "$web/clipper" && npm run build)
git -C "$web" diff --exit-code -- bin/clip.mjs

echo "== the mod's tests"
bash "$web/tests/mods/run.sh"
