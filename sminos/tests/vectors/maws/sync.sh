#!/usr/bin/env bash
#
# Vendor MAWS's project-rule vectors (Interfaces §B of MAWS's
# docs/doperpowers/plans/2026-11-10-project-registry.md): copy
# apps/org-protocol/vectors/project-rule.json as it is at <commit> of a MAWS
# checkout beside this script, byte for byte, and rewrite PIN.json to name
# that commit and the copy's sha256. The copy and its pin are written by this
# script alone, in the change that makes sminos pass that version.
#
#   sync.sh <MAWS checkout> <commit>
set -euo pipefail

[ $# -eq 2 ] || { echo "usage: $0 <MAWS checkout> <commit>" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
VECTOR=apps/org-protocol/vectors/project-rule.json
COMMIT="$(git -C "$1" rev-parse --verify "$2^{commit}")"
TMP="$(mktemp "$HERE/.project-rule.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
git -C "$1" show "$COMMIT:$VECTOR" > "$TMP"
SHA="$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$TMP")"
chmod 644 "$TMP"
mv "$TMP" "$HERE/project-rule.json"
python3 - "$HERE/PIN.json" "$COMMIT" "$VECTOR" "$SHA" <<'PY'
import json, sys
path, commit, vector, sha = sys.argv[1:]
with open(path, "w") as f:
    json.dump({"repository": "SSFSKIM/MAWS", "commit": commit, "path": vector, "sha256": sha}, f, indent=2)
    f.write("\n")
PY
echo "project-rule.json at MAWS $COMMIT, sha256 $SHA"
