#!/usr/bin/env bash
#
# Vendor one of MAWS's shared vector files: copy
# apps/org-protocol/vectors/<file> as it is at <commit> of a MAWS checkout
# beside this script, byte for byte, and rewrite the file's pin to name that
# commit and the copy's sha256. Each vendored file has a pin of its own, so
# vendoring one never moves another's: project-rule.json's is PIN.json
# (Interfaces §B of MAWS's docs/doperpowers/plans/2026-11-10-project-registry.md),
# and any other <name>.json's is <name>.PIN.json. A copy and its pin are
# written by this script alone, in the change that makes sminos pass that
# version.
#
#   sync.sh <MAWS checkout> <commit> [<file>]    (default: project-rule.json)
set -euo pipefail

[ $# -eq 2 ] || [ $# -eq 3 ] || { echo "usage: $0 <MAWS checkout> <commit> [<file>]" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
FILE="${3:-project-rule.json}"
case "$FILE" in
  */* | .* | *[!A-Za-z0-9._-]* | *.PIN.json | PIN.json) echo "sync.sh: not a vector file's name: $FILE" >&2; exit 2 ;;
  *.json) ;;
  *) echo "sync.sh: not a vector file's name: $FILE" >&2; exit 2 ;;
esac
if [ "$FILE" = project-rule.json ]; then PIN=PIN.json; else PIN="${FILE%.json}.PIN.json"; fi
VECTOR="apps/org-protocol/vectors/$FILE"
COMMIT="$(git -C "$1" rev-parse --verify "$2^{commit}")"
TMP="$(mktemp "$HERE/.${FILE%.json}.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
git -C "$1" show "$COMMIT:$VECTOR" > "$TMP"
SHA="$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$TMP")"
chmod 644 "$TMP"
mv "$TMP" "$HERE/$FILE"
python3 - "$HERE/$PIN" "$COMMIT" "$VECTOR" "$SHA" <<'PY'
import json, sys
path, commit, vector, sha = sys.argv[1:]
with open(path, "w") as f:
    json.dump({"repository": "SSFSKIM/MAWS", "commit": commit, "path": vector, "sha256": sha}, f, indent=2)
    f.write("\n")
PY
echo "$FILE at MAWS $COMMIT, sha256 $SHA"
