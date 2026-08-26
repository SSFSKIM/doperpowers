#!/usr/bin/env bash
# Unit tests for the agora CLI (skills/agora/scripts/agora).
# Pure shell + jq; every test runs against a throwaway $AGORA_HOME.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGORA="$SCRIPT_DIR/../../skills/agora/scripts/agora"
[ -x "$AGORA" ] || { echo "FAIL: agora CLI not found/executable at $AGORA"; exit 1; }

fails=0
ok()   { echo "ok $1"; }
fail() { echo "FAIL $1"; fails=$((fails + 1)); }

fresh() { # new isolated state root; echoes it
  mktemp -d "${TMPDIR:-/tmp}/agora-test.XXXXXX"
}

# Kill a backgrounded listen (script pid + its orphaned tail, matched by the
# unique temp path — macOS has no timeout(1) or setsid).
stop_listen() { # pid home
  kill "$1" 2>/dev/null || true
  pkill -f "tail -n .*$2" 2>/dev/null || true
  wait "$1" 2>/dev/null || true
}

unset AGORA_ALIAS || true

# --- join: idempotency, validation ------------------------------------------

h="$(fresh)"
AGORA_HOME="$h" "$AGORA" join g1 archi --desc "the architect" >/dev/null
j1="$(jq -r '.joined' "$h/groups/g1/nodes/archi.json")"
sleep 1
AGORA_HOME="$h" "$AGORA" join g1 archi --desc "revised" >/dev/null
j2="$(jq -r '.joined' "$h/groups/g1/nodes/archi.json")"
u2="$(jq -r '.updated' "$h/groups/g1/nodes/archi.json")"
d2="$(jq -r '.desc' "$h/groups/g1/nodes/archi.json")"
if [ "$j1" = "$j2" ] && [ "$u2" != "$j1" ] && [ "$d2" = "revised" ]; then
  ok "join is idempotent: joined preserved, updated/desc refreshed"
else
  fail "join idempotency (j1=$j1 j2=$j2 u2=$u2 d2=$d2)"
fi

rc=0; AGORA_HOME="$h" "$AGORA" join g1 'bad alias!' >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] && ok "join rejects bad charset (exit 2)" || fail "bad charset accepted (rc=$rc)"
rc=0; AGORA_HOME="$h" "$AGORA" join g1 human >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] && ok "join rejects reserved alias human" || fail "human join accepted (rc=$rc)"
rm -rf "$h"

# --- send: edge rules, fan-out, marking -------------------------------------

h="$(fresh)"
AGORA_HOME="$h" "$AGORA" join g archi >/dev/null
AGORA_HOME="$h" "$AGORA" join g impl-1 --parent archi >/dev/null
AGORA_HOME="$h" "$AGORA" join g impl-2 --parent archi >/dev/null

AGORA_HOME="$h" "$AGORA" send g --from archi --to impl-1 "start M1" >/dev/null \
  && ok "parent→child send allowed" || fail "parent→child send refused"
AGORA_HOME="$h" "$AGORA" send g --from impl-1 --to archi "ack" >/dev/null \
  && ok "child→parent send allowed" || fail "child→parent send refused"

rc=0; err="$(AGORA_HOME="$h" "$AGORA" send g --from impl-1 --to impl-2 "psst" 2>&1 >/dev/null)" || rc=$?
if [ "$rc" -eq 3 ] && printf '%s' "$err" | grep -q "archi"; then
  ok "sibling send refused with exit 3, error names real neighbors"
else
  fail "sibling send (rc=$rc err=$err)"
fi

AGORA_HOME="$h" "$AGORA" send g --from impl-1 --to impl-2 --off-edge "psst" >/dev/null
last_off="$(tail -n 1 "$h/groups/g/log.jsonl" | jq -r '.off_edge')"
[ "$last_off" = "true" ] && ok "--off-edge send succeeds and record is marked" \
  || fail "off-edge marking (off_edge=$last_off)"

AGORA_HOME="$h" "$AGORA" send g --from impl-1 --to human "escalating" >/dev/null \
  && ok "human is always a legal target" || fail "send to human refused"
AGORA_HOME="$h" "$AGORA" send g --to impl-1,impl-2 "operator ping" >/dev/null \
  && ok "human sender (default --from) bypasses edge rules" || fail "human bypass refused"

from_env="$(AGORA_ALIAS=archi AGORA_HOME="$h" "$AGORA" send g --to impl-1 "env from" >/dev/null \
  && tail -n 1 "$h/groups/g/log.jsonl" | jq -r '.from')"
[ "$from_env" = "archi" ] && ok "--from defaults from AGORA_ALIAS" || fail "AGORA_ALIAS default (got $from_env)"

logl="$(wc -l < "$h/groups/g/log.jsonl" | tr -d ' ')"
i1="$(wc -l < "$h/groups/g/inbox/impl-1.jsonl" | tr -d ' ')"
i2="$(wc -l < "$h/groups/g/inbox/impl-2.jsonl" | tr -d ' ')"
# sends so far: archi→impl-1, impl-1→archi, impl-1→impl-2(off), impl-1→human,
# human→both, archi→impl-1(env)  = 6 log lines; impl-1 inbox: 3; impl-2 inbox: 2
if [ "$logl" = 6 ] && [ "$i1" = 3 ] && [ "$i2" = 2 ]; then
  ok "fan-out: one log line per send, one inbox line per target"
else
  fail "fan-out counts (log=$logl impl-1=$i1 impl-2=$i2)"
fi
multi_log="$(grep 'operator ping' "$h/groups/g/log.jsonl")"
multi_i1="$(grep 'operator ping' "$h/groups/g/inbox/impl-1.jsonl")"
multi_i2="$(grep 'operator ping' "$h/groups/g/inbox/impl-2.jsonl")"
if [ "$(printf '%s' "$multi_log" | jq -r '.to|join(",")')" = "impl-1,impl-2" ] \
   && [ "$multi_log" = "$multi_i1" ] && [ "$multi_log" = "$multi_i2" ]; then
  ok "multi-target record carries full to-list, identical in log and inboxes"
else
  fail "multi-target record"
fi

echo "line one from stdin" | AGORA_HOME="$h" "$AGORA" send g --from archi --to impl-1 >/dev/null
stext="$(tail -n 1 "$h/groups/g/log.jsonl" | jq -r '.text')"
[ "$stext" = "line one from stdin" ] && ok "empty text args reads body from stdin" \
  || fail "stdin body (got: $stext)"

rc=0; AGORA_HOME="$h" "$AGORA" send g --from archi --to ghost "hi" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 4 ] && ok "unknown target refused (exit 4)" || fail "unknown target (rc=$rc)"
rm -rf "$h"

# --- listen: backlog, cursor, envelope, escaping ----------------------------

h="$(fresh)"
AGORA_HOME="$h" "$AGORA" join g archi >/dev/null
AGORA_HOME="$h" "$AGORA" join g impl --parent archi >/dev/null
AGORA_HOME="$h" "$AGORA" send g --from archi --to impl "first" >/dev/null
AGORA_HOME="$h" "$AGORA" send g --from archi --to impl 'has <tags> & "quotes"' >/dev/null

out="$h/listen1.out"
AGORA_HOME="$h" "$AGORA" listen g impl > "$out" 2>/dev/null &
lp=$!
disown "$lp" 2>/dev/null || true
sleep 1.5
stop_listen "$lp" "$h"
lines="$(grep -c '^<agora-message ' "$out" || true)"
cur="$(cat "$h/groups/g/cursor/impl" 2>/dev/null || echo none)"
if [ "$lines" = 2 ] && [ "$cur" = 2 ]; then
  ok "listen delivers backlog and checkpoints cursor"
else
  fail "listen backlog (lines=$lines cursor=$cur)"; cat "$out" >&2 || true
fi
if grep -q 'from="archi" to="impl"' "$out" && grep -q '&lt;tags&gt; &amp; &quot;quotes&quot;' "$out"; then
  ok "envelope carries provenance attrs; text is html-escaped, one line per message"
else
  fail "envelope format"; cat "$out" >&2 || true
fi

out2="$h/listen2.out"
AGORA_HOME="$h" "$AGORA" send g --from archi --to impl "third" >/dev/null
AGORA_HOME="$h" "$AGORA" listen g impl > "$out2" 2>/dev/null &
lp=$!
disown "$lp" 2>/dev/null || true
sleep 1.5
stop_listen "$lp" "$h"
lines2="$(grep -c '^<agora-message ' "$out2" || true)"
if [ "$lines2" = 1 ] && grep -q '>third<' "$out2"; then
  ok "restarted listen resumes from cursor (only the new message)"
else
  fail "cursor resume (lines=$lines2)"; cat "$out2" >&2 || true
fi
rm -rf "$h"

# --- topology + view --------------------------------------------------------

h="$(fresh)"
AGORA_HOME="$h" "$AGORA" join g archi --desc root >/dev/null
AGORA_HOME="$h" "$AGORA" join g impl --parent archi >/dev/null
AGORA_HOME="$h" "$AGORA" join g rev --parent impl >/dev/null
AGORA_HOME="$h" "$AGORA" join g lost --parent gone >/dev/null
AGORA_HOME="$h" "$AGORA" send g --from archi --to impl "one" >/dev/null
AGORA_HOME="$h" "$AGORA" send g --from rev --to archi --off-edge "skip level" >/dev/null

topo="$(AGORA_HOME="$h" "$AGORA" topology g)"
nn="$(printf '%s' "$topo" | jq '.nodes | length')"
edge_ok="$(printf '%s' "$topo" | jq '[.edges[] | select(.from=="archi" and .to=="impl")] | length')"
unread_impl="$(printf '%s' "$topo" | jq '.nodes[] | select(.alias=="impl") | .unread')"
offact="$(printf '%s' "$topo" | jq '[.off_edge_activity[] | select(.from=="rev" and .to=="archi" and .count==1)] | length')"
if [ "$nn" = 4 ] && [ "$edge_ok" = 1 ] && [ "$unread_impl" = 1 ] && [ "$offact" = 1 ]; then
  ok "topology JSON: nodes+unread, parent-derived edges, off-edge activity"
else
  fail "topology (nodes=$nn edge=$edge_ok unread=$unread_impl offact=$offact)"
  printf '%s\n' "$topo" >&2
fi

vout="$(AGORA_HOME="$h" "$AGORA" view g)"
if printf '%s' "$vout" | grep -q "└── rev" \
   && printf '%s' "$vout" | grep -q "dangling — parent 'gone'" \
   && printf '%s' "$vout" | grep -q "⚡ rev ⇢ archi (1)"; then
  ok "view renders tree, dangling section, off-edge traffic"
else
  fail "view rendering"; printf '%s\n' "$vout" >&2
fi

AGORA_HOME="$h" "$AGORA" leave g rev >/dev/null
left="$(AGORA_HOME="$h" "$AGORA" list g | grep -c '^rev ' || true)"
[ "$left" = 0 ] && [ -f "$h/groups/g/inbox/rev.jsonl" ] \
  && ok "leave removes membership, keeps history" || fail "leave semantics"
rm -rf "$h"

# ----------------------------------------------------------------------------

echo ""
if [ "$fails" -eq 0 ]; then
  echo "all agora tests passed"
else
  echo "$fails agora test(s) FAILED"
  exit 1
fi
