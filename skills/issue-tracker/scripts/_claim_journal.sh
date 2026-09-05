#!/usr/bin/env bash
# _claim_journal.sh — the API dispatchers' shared claim journal: how a claimed
# run is recorded before it is handed to a worker, and how a crash mid-handover
# is reconciled afterwards. Sourced by execute-dispatch.sh and
# review-dispatch.sh, which had verbatim copies of both halves.
#
# THE JOURNAL DIRECTORY IS SHARED ($DAEMON_HOME/board-claims) and every entry
# names its lane. A dispatcher touches only its OWN lanes: replaying a qagent
# nonce from the implement side would hand a review assignment an executor
# prompt, and ending a qagent run would strand the review dispatcher's ticket.
# A lane nobody recognizes is skipped for the same reason — not acting is the
# safe direction. The sweep's `successor` lane is outside both, and the sweep
# reconciles it itself.
#
# _claim_nonce needs nothing. _reconcile_claims needs all of:
#   CLAIM_LANES                  comma-separated lanes this dispatcher owns
#   _claim_one_with_nonce L N C  replay one claim under an existing nonce
#   _claim_lane_cap L            the lane cap to replay that lane under
#   _claim_drop_journal N        remove a nonce's journal (and its body file)
#   _claim_retire_worker U       retire a spawned session by uuid; rc 0 only
#                                when the CLI accepted it
#   _claim_suppress_dir          print the suppression directory (the sweep's
#                                failed-cycle counts live beside its records)
#   _api_py                      the API-client python runner (_binding.sh)
#   DAEMON_HOME                  registry root

# The nonce a claim is filed under. uuidgen is NOT a declared dependency of
# anything else here and a host without util-linux has none of it; python3 is
# a hard dependency of every script in this family, so it is the fallback.
# AN EMPTY NONCE IS FATAL, never a claim to make anyway: the nonce IS the
# journal filename, so an empty one journals to ".json"/".body.md" and the
# next claim to take that path deletes a granted run's only recovery record.
_claim_nonce() {
  local n
  n="$(uuidgen 2>/dev/null || true)"
  [ -n "$n" ] || n="$(python3 -c "import uuid; print(uuid.uuid4())" 2>/dev/null || true)"
  [ -n "$n" ] || { echo "error: no claim nonce could be minted (neither uuidgen nor python3 produced one) — refusing to claim" >&2
                   return 1; }
  printf '%s\n' "$n"
}

# Release a claimed run and SAY WHETHER IT LANDED. The dispatchers' own
# _api_end_run swallows every failure (`|| true`), which is right where the
# journal is already gone and there is nothing left to retry from — and wrong
# in the reconciler, where the journal is the only retry handle there is.
# A typed run-ended answer counts as landed: the run is already over.
_claim_end_run() {  # <run-id> <reason> — rc 0 only when the run is released
  T_RUN="$1" T_REASON="$2" _api_py - <<'PY'
import os
import _board_api as A
try:
    A.end_run(os.environ["T_RUN"], os.environ["T_REASON"])
except A.RunEnded:
    pass
PY
}

# One journal entry, written whole. json.dump rather than printf: the run id is
# whatever the server sent, and a non-integer one (a string id, a null slipping
# through) rendered into a bare `"run_id": %s` slot produces a file no reader
# can parse — and an unparseable journal is a claimed run nobody can reconcile.
# `ticket` and `daemon` land BEFORE the spawn on purpose; see _reconcile_claims.
# `pid` is this dispatcher's, so a concurrent peer can tell a journal whose
# writer is still working from one a crash left behind. `control` is the review
# lane's control directory, where the startup barrier and the worker ack live;
# it is what separates a reviewer that crossed the barrier from one waiting on
# a barrier nobody will publish. The execution lanes have no barrier and pass
# none.
_journal_write() {  # <path> <lane> <run-id ('' = null)> <spawn-completed 0|1> [ticket] [daemon] [control-dir]
  J_PATH="$1" J_LANE="$2" J_RUN="$3" J_DONE="$4" J_TICKET="${5:-}" J_DAEMON="${6:-}" \
  J_CONTROL="${7:-}" J_PID="$$" python3 - <<'PY'
import json, os
e = os.environ
run = e["J_RUN"]
if run == "":
    run = None
else:
    try:
        run = int(run)
    except ValueError:
        pass
j = {"lane": e["J_LANE"], "run_id": run, "spawn_completed": e["J_DONE"] == "1",
     "pid": int(e["J_PID"])}
if e["J_TICKET"]:
    j["ticket"] = e["J_TICKET"]
if e["J_DAEMON"]:
    j["daemon"] = e["J_DAEMON"]
if e["J_CONTROL"]:
    j["control"] = e["J_CONTROL"]
with open(e["J_PATH"], "w") as f:
    json.dump(j, f)
    f.write("\n")
PY
}

# A run the SERVER has ended is over locally too. Without this the meta keeps
# its run id and its lane, and the dispatchers' local cap counts it — so a
# normally released run occupies a dispatch slot forever while never appearing
# in needing-resume (nothing reclaimed it; it simply finished).
#
# The RUN ASSOCIATION is stripped, and only that: the session is still a real
# session, it just no longer speaks for a run. The bearer goes with it — a
# token for an ended run authenticates nothing, and keeping it is only a secret
# still lying at rest. `lane` and `role` STAY, deliberately: the reclaim path
# reaches this same branch (a reclaimed run answers renew with 409 run-ended),
# and the successor claimed for that ticket inherits its lane from exactly this
# meta. The slot is freed by the run id going away, not the lane — the
# dispatchers count OPEN RUNS, which is what a cap is about.
_retire_run_locally() {  # <meta path> <run id>
  T_PATH="$1" T_RUN="$2" T_DHOME="$DAEMON_HOME" python3 - <<'PY'
import fcntl, json, os
env = os.environ
lock = open(os.path.join(env["T_DHOME"], ".metalock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX)
try:
    path = env["T_PATH"]
    with open(path) as f:
        m = json.load(f)
    # Only if the meta STILL names the run that ended. A successor persist can
    # re-point this very meta at a fresh run between the renew and this write,
    # and clearing that one would strand a live run nothing could speak for.
    if str(m.get("run_id") or "") != env["T_RUN"]:
        raise SystemExit(0)
    for k in ("run_id", "run_bearer", "fence", "bind_confirmed", "nonce"):
        m.pop(k, None)
    m["run_ended_at"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ",
                                                    __import__("time").gmtime())
    mode = os.stat(path).st_mode & 0o777
    tmp = path + ".tmp"
    # Unlink first: os.open(..., mode) does NOT re-mode an existing inode, so a
    # leftover 0644 tmp from an earlier crash would be truncated and rewritten
    # world-readable. (This writer removes the bearer rather than adding one,
    # but the rule is the writer's, not the payload's.)
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "w") as f:
        json.dump(m, f, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
PY
}

# Startup pass over the claim journal: every entry a crash could have left
# mid-handoff is either finished or released. One python pass classifies them
# against the registry (a journal that names a run the registry knows was in
# fact handed off); the shell performs only the two actions that leave this
# machine.
#
# ENDING A RUN IS THE ONLY DESTRUCTIVE ACTION HERE, and it is taken only when
# the evidence says no session exists. A run id alone never proves that: it
# reaches a meta through board-bind, the LAST step of the handover, so the whole
# spawn window shows up as "run claimed, registry silent" while a detached
# worker is already running. Ending there kills a live run and frees the ticket
# for a second worker. The daemon name in the journal closes that window;
# anything else the registry cannot speak to is held, and the server lease
# reclaim — not this dispatcher — resolves it.
#
# A JOURNAL WHOSE WRITER IS STILL ALIVE IS NOT A CRASH. Nothing serializes two
# dispatch processes (an operator's `--sweep` beside the tick's), and a peer's
# claim is journalled BEFORE its POST goes out — so replaying that nonce while
# its response is in flight makes A1 rotate the bearer under the peer, and both
# callers spawn from their own answers. A journal younger than
# BOARD_CLAIM_INFLIGHT_GRACE seconds whose pid is still running is left alone.
_reconcile_claims() {
  local actions lines line act nonce lane run extra
  # The registry is machine-global; the lane count and the live-run set below
  # are not. Another api-bound repo's workers sit in the same $DAEMON_HOME, and
  # counting them made this dispatcher's lane look full (so it declined to
  # claim) and a neighbour's run look live (so a stranded one was never ended).
  # Empty under any binding that has no repo dimension — meta_is_mine then
  # filters nothing, which is the pre-change behaviour.
  local _cj_board="" _cj_repo=""
  if [ "${BOARD_BINDING:-gh}" = api ]; then
    _cj_board="api:$BOARD_API_URL"; _cj_repo="${BOARD_REPO:-}"
  fi
  actions="$(T_DHOME="$DAEMON_HOME" T_LANES="$CLAIM_LANES" \
             T_SUPPRESS="$(_claim_suppress_dir)" \
             T_BOARD="$_cj_board" T_BOARD_REPO="$_cj_repo" \
             T_GRACE="${BOARD_CLAIM_INFLIGHT_GRACE:-120}" _api_py - <<'PY'
import glob, json, os, time
from _board_api import meta_is_mine
home = os.environ["T_DHOME"]
lanes = set(os.environ["T_LANES"].split(","))
suppress = os.environ.get("T_SUPPRESS") or ""
grace = float(os.environ["T_GRACE"])
# run id -> the uuid of the meta carrying it. The uuid is needed by the
# `stranded` arm, which has a worker to retire and not merely a run to end.
live = {}
names = set()
blind = []
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        # A meta we cannot read is a session we cannot rule out. Say so, and
        # let every end below downgrade to a hold.
        blind.append(p)
        continue
    if not meta_is_mine(m, os.environ.get("T_BOARD", ""),
                        os.environ.get("T_BOARD_REPO", "")):
        continue
    if m.get("run_id"):
        live[str(m["run_id"])] = str(m.get("uuid") or os.path.basename(p)[:-5])
    # ONLY A RUNNING SESSION IS EVIDENCE OF A SPAWN. Daemon names are
    # deterministic per ticket and lane (`<ticket>-api-<lane>`) and a retired
    # daemon keeps its meta, so a HISTORICAL entry into the same lane left a
    # name that falsely proved the NEXT claim had spawned — closing its journal
    # and leaving the new run ownerless until the lease expired.
    if m.get("name") and m.get("status") in ("working", "blocked"):
        names.add(str(m["name"]))


def alive(pid):
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


# The plan rows are 0x1f-separated, not tab-separated: TAB IS IFS WHITESPACE,
# so a run of tabs collapses into one delimiter and every column after an empty
# one shifts left — and these rows carry empty columns by design (a replayed
# claim has no run, a held one no daemon). 0x1f is IFS-non-whitespace and
# cannot occur in a nonce, a lane, a run id or a pid.
for p in blind:
    print("unreadable\x1f%s\x1f\x1f\x1f" % p)
for p in sorted(glob.glob(os.path.join(home, "board-claims", "*.json"))):
    try:
        j = json.load(open(p))
    except Exception:
        # Silently skipping this hid a claimed run forever. It is reported and
        # left alone: a journal nobody can read is not a journal anybody may
        # act on. Its lane is unknowable too, so no lane filter can apply —
        # both dispatchers report it and neither touches it.
        print("unreadable\x1f%s\x1f\x1f\x1f" % p)
        continue
    if j.get("spawn_completed") or j.get("lane") not in lanes:
        continue
    nonce = os.path.basename(p)[:-5]
    lane = j.get("lane") or ""
    run = j.get("run_id")
    daemon = j.get("daemon") or ""
    control = j.get("control") or ""
    # A journalled control dir with no ack in it is a handover that has not
    # crossed its startup barrier — the review lane's durability line. Until it
    # does, the delivery may still be undone (see the two arms below).
    ack_pending = bool(control) and not os.path.exists(
        os.path.join(control, "bind-ready.json.ack"))
    if run and str(run) in live and ack_pending and not alive(j.get("pid")):
        # A BOUND RUN WHOSE WORKER NEVER CROSSED ITS STARTUP BARRIER. The
        # review handover is bind -> publish the barrier -> wait for the ack,
        # and the journal is marked only after the ack; a crash before the
        # publish therefore leaves exactly this: a meta carrying the run and a
        # control dir with no ack in it. Repairing the marker here would be a
        # lie — the reviewer waits out its 120-second barrier bound and ends
        # without reviewing anything, so the ticket would stay owned by a
        # session that can never start and the tick would renew its lease
        # forever. The uuid rides along: there is a worker to retire, not just
        # a run to end.
        #
        # THE WRITER MUST BE DEAD. This is the one arm that retires a session
        # somebody else may be mid-handover on, and a peer dispatcher between
        # its bind and its ack has exactly this journal — so liveness, not the
        # mtime grace the inflight arm below uses, since a handover legitimately
        # outlives that grace while it waits for the ack. Pid reuse errs into
        # `repaired`, which sends nothing.
        print("stranded\x1f%s\x1f%s\x1f%s\x1f%s" % (nonce, lane, run, live[str(run)]))
    elif run and str(run) in live and ack_pending:
        # The same shape with the writer STILL ALIVE: a peer between its bind
        # and the ack it is waiting on. Sealing that journal would close a
        # record somebody else is still writing, and the delivery is not
        # durable yet — if the ack never lands, the arm above retires the
        # worker and releases the run. Left entirely alone, counter included.
        print("inflight\x1f%s\x1f%s\x1f%s\x1f%s" % (nonce, lane, run, j.get("pid")))
    elif run and str(run) in live:
        # the spawn DID complete — its worker is in the registry — and only
        # the marker write was lost. Repair it in place; nothing to send.
        #
        # THE RESET COMES FIRST AND THE SEAL SECOND. A sealed journal is
        # skipped by every later pass, so anything left until after that write
        # happens once or never: the dispatcher clears the ticket's
        # failed-cycle count one line ahead of its own marker write, and this
        # arm — the crash that lost that write — does the same. Both steps are
        # idempotent, so a crash between them costs nothing: the journal is
        # still open and the next pass redoes both.
        ticket = str(j.get("ticket") or "")
        failed = ""
        if ticket and suppress:
            try:
                os.remove(os.path.join(suppress, ".attempts-" + ticket))
            except FileNotFoundError:
                # ENOENT ANSWERS TWO OPPOSITE QUESTIONS: the counter is
                # already gone (the reset is done), or the directory holding
                # it cannot be seen at all — an operator BOARD_SUPPRESS_DIR
                # whose volume unmounted, a path that moved. Sealing on the
                # second reading loses the same way EACCES did: the mount
                # comes back carrying the count, and the journal that would
                # have cleared it is closed forever.
                #
                # REACHABILITY tells them apart, not the directory alone. The
                # sweep creates it the first time it counts anything, so on a
                # registry that has never had a failed cycle it legitimately
                # does not exist — treating that as a fault would stall every
                # repair on every healthy fleet. A directory whose PARENT is
                # gone too is a path this process cannot see.
                parent = os.path.dirname(suppress.rstrip("/")) or "."
                if not (os.path.isdir(suppress) or os.path.isdir(parent)):
                    failed = "the suppression directory is unreachable"
            except OSError as e:
                # A REMOVAL THAT FAILED IS NOT A REMOVAL — a read-only or
                # unmounted registry, a permission change. The count is still
                # standing, and sealing on top of it hides that from every
                # later pass. Skip the seal: the journal stays open and the
                # next one retries the pair.
                failed = e.strerror or str(e)
        if failed:
            print("resetfailed\x1f%s\x1f%s\x1f%s\x1f%s %s"
                  % (nonce, lane, run, ticket, failed))
            continue
        j["spawn_completed"] = True
        with open(p, "w") as f:
            json.dump(j, f)
        print("repaired\x1f%s\x1f%s\x1f%s\x1f%s" % (nonce, lane, run, ticket))
    elif run and daemon and daemon in names and not alive(j.get("pid")):
        # A session by that name exists but no meta carries the run: the spawn
        # landed and the bind did not. That worker holds NOTHING — `claude --bg`
        # drops the spawn env prefix before its own shells run, and the bind is
        # what would have put a bearer at rest — so it can never act as the run,
        # and every verb it runs would go out as the operator instead (dp#35).
        # It is retired and the run released, like `stranded`.
        #
        # THE WRITER MUST BE DEAD, for the same reason that arm says so: this
        # one now retires a session, and a peer dispatcher between its own spawn
        # and its own bind has exactly this journal. Nothing is sealed here
        # either — a release that fails must leave the journal open, or the
        # retry handle is gone.
        print("orphaned\x1f%s\x1f%s\x1f%s\x1f%s" % (nonce, lane, run, daemon))
    elif run and daemon and daemon in names:
        # The same shape with the writer STILL ALIVE: a peer mid-handover, in
        # the seconds between its spawn and its bind. Left entirely alone.
        print("inflight\x1f%s\x1f%s\x1f%s\x1f%s" % (nonce, lane, run, j.get("pid")))
    elif run and blind:
        print("held\x1f%s\x1f%s\x1f%s\x1f" % (nonce, lane, run))
    elif (time.time() - os.path.getmtime(p) < grace) and alive(j.get("pid")):
        # Another dispatch process is mid-handover on this nonce right now.
        print("inflight\x1f%s\x1f%s\x1f%s\x1f%s" % (nonce, lane, run or "", j.get("pid")))
    elif run:
        print("end\x1f%s\x1f%s\x1f%s\x1f" % (nonce, lane, run))
    else:
        print("replay\x1f%s\x1f%s\x1f\x1f" % (nonce, lane))
PY
)" || { echo "claim reconciliation failed — skipping it this tick" >&2; return 0; }
  [ -n "$actions" ] || return 0
  # Read the whole plan BEFORE acting on it. The actions below run children
  # (a replayed claim, an end, a spawn) that inherit this stdin, and one of
  # them consuming the rest of the plan would silently drop reconciliation
  # steps — the class of bug that is invisible until the tick that needed them.
  lines=()
  while IFS= read -r line; do
    [ -n "$line" ] && lines+=("$line")
  done <<<"$actions"
  for line in ${lines[@]+"${lines[@]}"}; do
    IFS=$'\x1f' read -r act nonce lane run extra <<<"$line"
    case "$act" in
      unreadable)
        echo "reconcile: unreadable json at $nonce — left untouched; no claim under it can be reconciled until it is repaired or removed by hand" >&2 ;;
      repaired)
        # The failed-cycle reset that belongs to this repair already ran, in
        # the same process, ahead of the seal — see the arm above.
        echo "reconcile: $nonce did spawn (run $run) — marker repaired${extra:+ (#$extra)}" ;;
      resetfailed)
        echo "reconcile: $nonce did spawn (run $run) but the failed-cycle reset failed (#$extra) — the marker is NOT written, so the next pass retries both steps; the ticket would otherwise escalate early on a much later fault" >&2 ;;
      stranded)
        # The one handoff crash that leaves a LIVE-LOOKING run nobody will ever
        # work: bound, but the startup barrier never opened. Retire the worker
        # and end the run so the ticket goes back on the queue. The end is
        # checked, not best-effort — see the `end` arm below.
        echo "reconcile: $nonce bound run $run to session $extra but the startup barrier never opened — retiring that worker and ending the run so the ticket returns to the queue" >&2
        _claim_retire_worker "$extra" || true
        if _claim_end_run "$run" abandoned; then
          # A retire stops a turn; it does not make the seat forget. This
          # record still names the run, its fence and its BEARER — and a
          # session resolves its own run context out of exactly those fields,
          # so a hand-resumed seat would authenticate with a revoked token on
          # every verb instead of falling back cleanly. The strip is the same
          # one the sweep applies when a run ends under it.
          [ ! -f "$DAEMON_HOME/$extra.json" ] \
            || _retire_run_locally "$DAEMON_HOME/$extra.json" "$run" \
            || echo "reconcile: run $run ended, but $extra's record could not be stripped of it — clear run_bearer/bind_confirmed there by hand" >&2
          _claim_drop_journal "$nonce"
        else
          echo "reconcile: releasing run $run failed — the journal is KEPT so the next tick can retry the release" >&2
        fi ;;
      orphaned)
        # The bind is what puts a bearer at rest, and `claude --bg` dropped the
        # one on the spawn prefix — so this worker can never speak for the run,
        # and every verb it runs would act as the operator on a ticket its own
        # claimed run still owns. Leaving it live was the older answer and it
        # rested on the opposite premise (that the bearer was in its
        # environment). Retire it, release the run, drop the journal — the
        # `stranded` shape, for the same reason.
        #
        # The retire is best-effort by name, and it does not have to land for
        # this to be safe: the client refuses to resolve any principal at all on
        # a dispatched seat whose bind never landed, so an orphan that outlives
        # its retirement can still only stop, never write as somebody else.
        # There is nothing to strip locally — a record carrying the run is what
        # would have made this `repaired` rather than `orphaned`.
        echo "reconcile: $nonce spawned $extra for run $run but never bound it — that worker can never speak for the run (no bearer reached it and none is at rest), so retiring it and releasing the run rather than leaving it to write as the operator" >&2
        # THE RELEASE IS WHAT FREES THE TICKET, so it may not outrun the retire.
        # Ending a run whose worker is still running hands its ticket to a
        # successor beside a live predecessor — the divergence the retire exists
        # to prevent. A refused retire keeps the journal, like a refused release.
        if ! _claim_retire_worker "$extra"; then
          echo "reconcile: $nonce — $extra could not be retired, so run $run is NOT released (freeing the ticket beside a live worker is the one outcome worse than leaving it); the journal is KEPT for the next tick" >&2
        elif _claim_end_run "$run" abandoned; then
          _claim_drop_journal "$nonce"
        else
          echo "reconcile: releasing run $run failed — the journal is KEPT so the next tick can retry the release" >&2
        fi ;;
      held)
        echo "reconcile: $nonce claimed run $run — holding it; the registry has an unreadable meta, so a live session cannot be ruled out. The server lease reclaim owns this one." >&2 ;;
      inflight)
        echo "reconcile: $nonce is in flight under a live dispatcher (pid $extra) — left alone" ;;
      end)
        # Claimed but never handed off. The response WAS received, so a replay
        # would rotate nothing; the lease would otherwise strand the ticket
        # until the server's own reclaim.
        echo "reconcile: $nonce claimed run $run but never spawned — ending it"
        # THE JOURNAL IS THE ONLY RETRY HANDLE. A transport or service outage
        # fails the release while the run stays open and keeps owning the
        # ticket — and dropping the journal anyway removed the one record a
        # later tick could retry from, so "it retries next tick" was never
        # true and the ticket waited on the server lease instead. Same shape
        # as the successor-journal release in _sweep_api.sh.
        if _claim_end_run "$run" abandoned; then
          _claim_drop_journal "$nonce"
        else
          echo "reconcile: releasing run $run failed — the journal is KEPT so the next tick can retry the release" >&2
        fi ;;
      replay)
        # The nonce persisted but no run id ever did: the response was lost in
        # flight. Replaying THIS nonce is the only legal replay there is.
        echo "reconcile: $nonce never reached a run — replaying the claim"
        _claim_one_with_nonce "$lane" "$nonce" "$(_claim_lane_cap "$lane")" || true ;;
    esac
  done
}
