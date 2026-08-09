#!/usr/bin/env bash
# harness.sh — bring up a REAL A1 board-service on a scratch Postgres, so the
# A2 integration tier can drive the toolkit's verbs over an actual socket
# against the actual state machine (the unit tier drives a fixture mock).
#
# Usage:
#   harness.sh start   # scratch Postgres + service on 127.0.0.1:8917, then
#                      #   writes .harness/env.sh (source it) and .harness/creds.env
#   harness.sh stop    # tears both down and removes .harness/
#
# Both verbs are idempotent. `start` tears down any previous instance first —
# which also means ONE instance at a time per checkout: the container name and
# the service port are fixed, so a second concurrent `start` reclaims the first
# one's. (A2_PG_CONTAINER / A2_SERVICE_PORT override both if you need two.)
#
# Exit codes: 0 up (or down), 77 PREREQUISITE MISSING — the reason is printed
# as `SKIP: …` and the caller is expected to skip the tier, not fail it. Any
# other non-zero is a real failure.
#
# Postgres substrate: a throwaway `postgres:16` CONTAINER, not a local cluster.
# This machine has no psql/initdb/pg_ctl at all (no Homebrew postgres, no
# Postgres.app) while the Docker daemon is running and already holds the image,
# so `createdb` against a local server was not an option here. The container is
# the scratch database — it is created by `start`, carries no volume, and is
# `docker rm -f`'d by `stop`, so nothing survives the run. Set A2_PG_IMAGE to
# use a different tag.
#
# Principals are minted with SQL, not HTTP: the A1 API has NO principal-creation
# route (API.md § 2 — eighteen routes, pinned by a drill, and none of them mints
# one). ADMIN_TOKEN bootstraps the single `human`/`admin` row at boot; everything
# else is an insert into board.principal carrying the unsalted sha256 of the
# token, which is exactly what src/auth.js mintToken/createPrincipal do.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$HERE/.harness"
PG_IMAGE="${A2_PG_IMAGE:-postgres:16}"
PG_CONTAINER="${A2_PG_CONTAINER:-a2-harness-pg}"
PG_DB="board_a2_test"
PG_PASSWORD="a2-harness-scratch"
SERVICE_PORT="${A2_SERVICE_PORT:-8917}"
SERVICE_URL="http://127.0.0.1:$SERVICE_PORT"
# The reconciler's poll period is also /healthz's freshness unit (ready needs a
# WHOLE pass inside 2x it), and the first pass only fires after one period — at
# the 5000ms default a green probe is ~10s away for no reason on a scratch box.
RECONCILE_INTERVAL_MS="${A2_RECONCILE_INTERVAL_MS:-1000}"

skip() {
  echo "SKIP: $* — the A2 integration tier needs a runnable A1 board-service" >&2
  exit 77
}
die() {
  echo "harness: $*" >&2
  exit 1
}

preflight() {
  [ -n "${ARKHO_DIR:-}" ] || skip "ARKHO_DIR is not set (name an arkho checkout)"
  [ -f "$ARKHO_DIR/board-service/src/main.js" ] \
    || skip "no board-service/src/main.js under ARKHO_DIR=$ARKHO_DIR"
  for tool in node npm docker curl shasum openssl; do
    command -v "$tool" >/dev/null 2>&1 || skip "\`$tool\` is not on PATH"
  done
  # board-service declares engines node>=22 and uses top-level await in main.js.
  local major
  major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$major" -ge 22 ] || skip "node $major is older than board-service's engines>=22"
  docker info >/dev/null 2>&1 \
    || skip "the Docker daemon is not running (this machine has no local Postgres either)"
}

# psql, from inside the scratch container — there is no client on the host.
# `-h 127.0.0.1` is load-bearing, not decoration: the postgres image runs a
# TEMPORARY server on the unix socket while it initialises the cluster, and a
# socket probe goes green against THAT one — then it is shut down and the real
# server takes over, so a service booted on the socket's say-so dies mid-schema
# with "Connection terminated unexpectedly". The temporary server never listens
# on TCP, so asking over TCP is asking the server that will still be there.
pg() {
  docker exec -i -e PGPASSWORD="$PG_PASSWORD" "$PG_CONTAINER" \
    psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d "$PG_DB" -qtA "$@"
}
pg_ready() { pg -c 'select 1' </dev/null; }

sha256_of() { printf '%s' "$1" | shasum -a 256 | awk '{print $1}'; }

stop_quiet() {
  if [ -f "$STATE/service.pid" ]; then
    local pid tries=50
    pid="$(cat "$STATE/service.pid")"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
      while [ "$tries" -gt 0 ] && kill -0 "$pid" 2>/dev/null; do
        tries=$((tries - 1))
        sleep 0.1
      done
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
    fi
  fi
  docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$STATE"
}

wait_for() { # wait_for <seconds> <what> <cmd...>
  local budget="$1" what="$2"
  shift 2
  local deadline=$((SECONDS + budget))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 0.25
  done
  die "$what did not come up within ${budget}s"
}

# Read the body into a variable rather than piping into grep: under `pipefail`
# a short-circuiting `grep -q` can SIGPIPE its producer and turn a green probe
# into a random failure.
healthz_green() {
  local body
  body="$(curl -sf --max-time 3 "$SERVICE_URL/healthz")" || return 1
  case "$body" in *'"ok":true'*) return 0 ;; *) return 1 ;; esac
}

start() {
  preflight
  stop_quiet
  # A leftover service from a crashed run would hold the port, and the probe
  # below would go green against ITS database — a confusing pass, not a failure.
  if healthz_green; then
    die "something is already serving $SERVICE_URL/healthz — kill it (or set A2_SERVICE_PORT) and retry"
  fi
  mkdir -p "$STATE"

  docker run -d --name "$PG_CONTAINER" \
    -e POSTGRES_PASSWORD="$PG_PASSWORD" -e POSTGRES_DB="$PG_DB" \
    -p 127.0.0.1::5432 "$PG_IMAGE" >/dev/null \
    || die "could not start the scratch Postgres container from $PG_IMAGE"
  # From here on a `start` that dies owns a running container (and possibly a
  # service process), so every failure exit has to tear them down — otherwise
  # the next run inherits somebody's half-built cluster. Released on success.
  trap stop_quiet EXIT
  wait_for 60 "the scratch Postgres" pg_ready

  local pgport dsn
  pgport="$(docker port "$PG_CONTAINER" 5432/tcp | head -1 | awk -F: '{print $NF}')"
  [ -n "$pgport" ] || die "could not read the scratch Postgres port"
  dsn="postgresql://postgres:$PG_PASSWORD@127.0.0.1:$pgport/$PG_DB"

  cd "$ARKHO_DIR/board-service"
  if [ ! -d node_modules ]; then
    npm ci >"$STATE/npm-ci.log" 2>&1 || {
      sed 's/^/  | /' "$STATE/npm-ci.log" >&2
      die "npm ci failed in $ARKHO_DIR/board-service"
    }
  fi

  # 48 hex chars = the 192 bits main.js documents; it enforces >=32 chars.
  local admin_token
  admin_token="$(openssl rand -hex 24)"
  # All three URLs are the same local DSN: the pooled/direct/migration split
  # exists for Supavisor + least-privilege roles in production, and neither
  # applies to a scratch superuser cluster.
  DATABASE_URL="$dsn" DIRECT_DATABASE_URL="$dsn" MIGRATION_DATABASE_URL="$dsn" \
    ADMIN_TOKEN="$admin_token" PORT="$SERVICE_PORT" \
    RECONCILE_INTERVAL_MS="$RECONCILE_INTERVAL_MS" \
    node src/main.js >"$STATE/service.log" 2>&1 &
  echo "$!" >"$STATE/service.pid"

  local deadline=$((SECONDS + 60)) pid
  pid="$(cat "$STATE/service.pid")"
  until healthz_green; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "harness: board-service died during boot —" >&2
      sed 's/^/  | /' "$STATE/service.log" >&2
      exit 1
    fi
    [ "$SECONDS" -lt "$deadline" ] || {
      echo "harness: /healthz never went green within 60s —" >&2
      sed 's/^/  | /' "$STATE/service.log" >&2
      exit 1
    }
    sleep 0.25
  done

  local automation_token human_token
  automation_token="$(openssl rand -hex 24)"
  human_token="$(openssl rand -hex 24)"
  pg <<SQL >/dev/null || die "could not mint the harness principals"
insert into board.principal (kind, name, token_hash, capabilities) values
  ('automation', 'a2-harness-automation', '$(sha256_of "$automation_token")',
   '{dispatch,sweep,ingest,gateway}'),
  ('human', 'a2-harness-human', '$(sha256_of "$human_token")', '{}');
SQL

  ( umask 077
    cat >"$STATE/creds.env" <<CREDS
# generated by harness.sh — scratch credentials, thrown away by \`harness.sh stop\`
BOARD_AUTOMATION_TOKEN=$automation_token
BOARD_HUMAN_TOKEN=$human_token
CREDS
  )
  cat >"$STATE/env.sh" <<ENV
# generated by harness.sh — source this, then drive the toolkit's verbs
export BOARD_API_URL='$SERVICE_URL'
export BOARD_CREDENTIALS_FILE='$STATE/creds.env'
export ADMIN_TOKEN='$admin_token'
export BOARD_PG_DSN='$dsn'
export BOARD_HARNESS_DIR='$STATE'
ENV
  trap - EXIT
  echo "harness: board-service up at $SERVICE_URL (scratch pg on :$pgport) — source $STATE/env.sh"
}

case "${1:-}" in
  start) start ;;
  stop) stop_quiet ;;
  *)
    grep '^#' "$0" | grep -v '^#!' | sed 's/^# \{0,1\}//' >&2
    exit 2
    ;;
esac
