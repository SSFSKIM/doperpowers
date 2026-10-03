#!/usr/bin/env bash
# cloud-env-setup's env-names: prints the variable names a .env assigns and nothing of any value —
# including the body of a quoted multiline value (a PEM key), whose lines have no `=` or look like
# assignments, and which `cut -d= -f1` would print whole.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TOOL="$REPO_ROOT/skills/cloud-env-setup/scripts/env-names"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
FAILURES=0
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  [PASS] $1"; }
expect() { # <label> <expected output> <actual output>
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected [$2] got [$3]"; fi
}
no_marker() { # <label> <output>
  if printf '%s' "$2" | grep -q MARKER; then fail "$1: a value leaked: [$2]"; else pass "$1: no value printed"; fi
}

echo "plain assignments:"
cat > "$WORK/plain.env" <<'E'
# a comment with KEY_IN_COMMENT=MARKERcomment
API_KEY=MARKERplain1

  export TOKEN = MARKERplain2
PORT=4310   # trailing comment
lowercase_ok=MARKERplain3
E
out="$("$TOOL" "$WORK/plain.env")"
expect "names in order, export and spacing handled" "API_KEY
TOKEN
PORT
lowercase_ok" "$out"
no_marker "plain" "$out"

echo "quoted multiline values:"
cat > "$WORK/pem.env" <<'E'
BEFORE=MARKERbefore
PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwMARKERbody1
MARKERbodyNoPlusOrSlashAAAA==
FAKE_NAME=MARKERlooksLikeAnAssignment
-----END PRIVATE KEY-----"
SINGLE='first line MARKERs1
SECOND_FAKE=MARKERs2
last line'
ESCAPED="a \" MARKERe1
STILL_INSIDE=MARKERe2"
AFTER=MARKERafter
E
out="$("$TOOL" "$WORK/pem.env")"
expect "only the assignment names, none from inside a value" "BEFORE
PRIVATE_KEY
SINGLE
ESCAPED
AFTER" "$out"
no_marker "multiline" "$out"

echo "an escaped apostrophe inside a single-quoted multiline value:"
cat > "$WORK/sq.env" <<'E'
PRIVATE_KEY='-----BEGIN PRIVATE KEY-----
it\'s MARKERsq1
FAKE_KEY_BODYAAAA==MARKERsq2
-----END PRIVATE KEY-----'
NEXT=1
E
out="$("$TOOL" "$WORK/sq.env")"
expect "an escaped delimiter does not close the value" "PRIVATE_KEY
NEXT" "$out"
no_marker "escaped single quote" "$out"
if printf '%s' "$out" | grep -q FAKE_KEY_BODY; then fail "a body fragment printed"; else pass "no body fragment printed"; fi

echo "single-line quoted values:"
cat > "$WORK/oneline.env" <<'E'
A="MARKERq1 it's fine"
B='MARKERq2 say "hi"'
C="MARKERq3"
E
out="$("$TOOL" "$WORK/oneline.env")"
expect "a closed quote on its own line ends the value" "A
B
C" "$out"
no_marker "oneline" "$out"

echo "unquoted PEM block:"
cat > "$WORK/bare.env" <<'E'
KEY=-----BEGIN RSA PRIVATE KEY-----
MARKERbareBodyAAAA==
INSIDE=MARKERbare2
-----END RSA PRIVATE KEY-----
NEXT=1
E
out="$("$TOOL" "$WORK/bare.env")"
expect "the block is skipped to its END line" "KEY
NEXT" "$out"
no_marker "bare" "$out"

echo "an unterminated quote:"
printf 'OPEN="MARKERu1\nLATER=MARKERu2\n' > "$WORK/open.env"
out="$("$TOOL" "$WORK/open.env")"
expect "everything after an unclosed quote is value" "OPEN" "$out"
no_marker "unterminated" "$out"

echo "missing file:"
if err="$("$TOOL" "$WORK/nope.env" 2>&1)"; then fail "a missing file exits non-zero"; else pass "a missing file exits non-zero"; fi
expect "and says which file" "env-names: $WORK/nope.env: no such file" "$err"

echo "default path is ./.env:"
out="$(cd "$WORK" && cp plain.env .env && "$TOOL")"
expect "reads .env in the working directory" "API_KEY
TOKEN
PORT
lowercase_ok" "$out"

if [ "$FAILURES" -gt 0 ]; then echo "FAILED: $FAILURES"; exit 1; fi
echo "all passed"
