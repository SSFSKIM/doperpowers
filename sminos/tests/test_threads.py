#!/usr/bin/env python3
"""Every member a thread, under today's lifecycle (T1's M1:
docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md, the milestone's
"What it proves"; Interfaces §1–§3, §6 and §8).

- The record at a first join: a human-opened session's in the thread store
  under a minted id, a spawned one's in its seat record, none for lane B;
  every lifecycle event of a thread stamped.
- A spawn's child, its launcher paused: no record and no `joined` until its
  seat names it; the launcher that failed, and the one slower than the
  spawner's bound, whose seat absorbs the record made meanwhile.
- Adoption of members and seats from before threads, and what is not
  adopted.
- The reader rule: MAWS's vectors (`vectors/maws/channel-rule.json`, at its
  pin) through the reducer and through the readers of membership.
- The journal: an end and a return cut at each step, finished by the next
  reconciliation, no event twice; an older copy's writes.
- `seat add --session`, the hook's bounded lock, the launch's options, the
  lane change, the plane's idle read.

Hermetic: HOME and SMINOS_HOME are temporary, fresh for each test; the
sessions are `sleep` processes with engine records the test writes.
Run: python3 -B sminos/tests/test_threads.py
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts")
BASE = os.path.realpath(tempfile.mkdtemp(prefix="smth."))
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "MAWS_LANE",
            "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR", "SMINOS_LAUNCH", "CLAUDE_PID",
            "MAWS_LAUNCHED_BY"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), DAEMON_HOST="testhost",
                  SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, SCRIPTS)

import sminos  # noqa: E402
import sminos_records as records  # noqa: E402
import sminos_threads as threads  # noqa: E402

VECTORS = os.path.join(HERE, "vectors", "maws", "channel-rule.json")
PIN = os.path.join(HERE, "vectors", "maws", "channel-rule.PIN.json")


class Killed(BaseException):
    """A process dying at a step: nothing after it runs."""


def ms_ago(seconds):
    return int((time.time() - seconds) * 1000)


class Machine(unittest.TestCase):
    """A fresh installation per test: a git repository `work` (a local
    project), and sessions whose engine records name live `sleep`s."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"))
        os.makedirs(os.path.join(os.environ["HOME"], ".claude", "sessions"))
        os.makedirs(os.environ["SMINOS_HOME"])
        self.home = home
        self.procs = []
        self.addCleanup(self.stop_all)
        self.root = self.repo("work")
        self.p = self.project_of(self.root)

    def stop_all(self):
        for proc in self.procs:
            proc.kill()
            proc.wait()
        sminos.forget_caches()

    def repo(self, name):
        path = os.path.join(self.home, name)
        subprocess.run(["git", "init", "-q", path], check=True)
        return path

    def project_of(self, root):
        sminos.forget_caches()
        p = sminos.resolve_project(root)
        sminos.project_path(p, "log")
        return p

    def session(self, root=None, kind="interactive", sid=None, started=None, name=None):
        """A live session of this machine: its engine record names a `sleep`."""
        sid = sid or str(uuidlib.uuid4())
        proc = subprocess.Popen(["sleep", "600"])
        self.procs.append(proc)
        rec = {"pid": proc.pid, "sessionId": sid, "cwd": root or self.root, "kind": kind,
               "name": name or "s-" + sid[:4], "nameSource": "derived", "status": "idle"}
        if started is not None:
            rec["startedAt"] = started
        with open(self.peer_path(proc.pid), "w") as f:
            json.dump(rec, f)
        sminos.forget_caches()
        return sid, proc

    def peer_path(self, pid):
        return os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % pid)

    def peer_set(self, proc, **fields):
        path = self.peer_path(proc.pid)
        with open(path) as f:
            rec = json.load(f)
        rec.update(fields)
        with open(path, "w") as f:
            json.dump(rec, f)
        sminos.forget_caches()

    def end(self, proc):
        proc.kill()
        proc.wait()
        try:
            os.unlink(self.peer_path(proc.pid))
        except OSError:
            pass
        sminos.forget_caches()

    def reconcile(self, p=None):
        sminos.forget_caches()
        return sminos.reconcile(p or self.p)

    def own(self, sid, p=None):
        return sminos._own_events(p or self.p, sid)

    def joins(self, sid, p=None):
        return [e for e in self.own(sid, p) if e["kind"] == "joined"]

    def is_member(self, sid, p=None):
        return threads.member(self.own(sid, p))

    def human_files(self, aside=False):
        d = threads.aside_dir() if aside else threads.store_dir()
        return sorted(n for n in os.listdir(d) if n.endswith(".json")) if os.path.isdir(d) else []

    def write_own(self, sid, events, p=None):
        """Events in the session's own writer file, as an older sminos (or a
        test) leaves them: ts in order, seqs after the file's last."""
        p = p or self.p
        writer = sminos.writer_id(sid)
        path = sminos.writer_path(p, writer)
        have = [json.loads(line) for line in open(path)] if os.path.exists(path) else []
        seq = max((e["seq"] for e in have), default=0)
        with open(path, "a") as f:
            for e in events:
                seq += 1
                time.sleep(0.002)
                f.write(json.dumps({"ts": sminos.now(ms=True), "writer": writer, "seq": seq,
                                    "session": sid, **e}) + "\n")
        sminos.forget_caches()

    def old_joined(self, sid, alias="old", **more):
        return {"kind": "joined", "alias": alias, "name_source": "user", "machine": sminos.host_name(),
                "cwd": self.root, "worktree": "", "role": "", "seat": "", "by": "", "session_kind": "interactive",
                **more}

    def cli(self, *argv, cwd=None):
        out, err = io.StringIO(), io.StringIO()
        here = os.getcwd()
        os.chdir(cwd or self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    sminos.main(list(argv))
                    code = 0
                except SystemExit as e:
                    code = e.code or 0
        finally:
            os.chdir(here)
            sminos.forget_caches()
        return code, out.getvalue() + err.getvalue()

    def hook(self, sid, event="SessionStart", source="startup", env=None, transcript=None):
        """The record hook's work for one session (record_session), in this
        process, under the session's environment `env`."""
        tpath = transcript or os.path.join(self.home, "t-%s.jsonl" % sid)
        sminos.forget_caches()
        with mock.patch.dict(os.environ, env or {}):
            sminos.record_session(self.p, sid, tpath, event, "", source)
        sminos.forget_caches()


# ------------------------------------------------------------ the record at a first join


class FirstJoin(Machine):
    def test_a_session_joining_on_sight_has_a_record_in_the_thread_store_under_an_id_that_is_no_sessions(self):
        sid, _ = self.session()
        self.reconcile()
        [name] = self.human_files()
        t = threads.thread_of(sid)
        self.assertEqual(name, t["thread"] + ".json")
        self.assertNotEqual(t["thread"], sid)
        self.assertEqual((t["opened"], t["current"], t["sessions"]), ("human", sid, [sid]))
        self.assertEqual(list(sminos.record_files()), [], "nothing in the seat store")
        [j] = self.joins(sid)
        self.assertEqual(j["thread"], t["thread"])
        self.assertEqual(t["alias"], j["alias"], "the record keeps the alias's copy")
        with open(os.path.join(threads.store_dir(), name)) as f:
            self.assertEqual(oct(os.fstat(f.fileno()).st_mode & 0o777), "0o600")

    def test_a_spawned_one_has_the_thread_keys_in_its_seat_record_and_nothing_in_the_thread_store(self):
        sid, _ = self.session()
        code, out = self.cli("seat", "add", "g", "worker", "--session", sid)
        self.assertEqual(code, 0, out)
        [path] = list(sminos.record_files())
        with open(path) as f:
            raw = json.load(f)
        self.assertEqual((raw["opened"], raw["sessions"], raw["channels"]), ("spawned", [sid], []))
        self.assertEqual(self.human_files(), [])
        [j] = self.joins(sid)
        self.assertEqual(j["thread"], raw["uuid"])
        self.reconcile()
        self.assertEqual(len(self.joins(sid)), 1)

    def test_a_lane_b_session_has_neither_and_its_events_are_unstamped(self):
        sid, _ = self.session()
        records.establish(sid, records.default_provenance())
        records.set_controller(sid, "B")
        self.reconcile()
        self.assertEqual(self.human_files(), [])
        self.assertIsNone(threads.thread_of(sid))
        [j] = self.joins(sid)
        self.assertNotIn("thread", j)

    def test_every_lifecycle_event_of_a_thread_is_stamped(self):
        sid, _ = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        sminos.lifecycle(self.p, sid, "renamed", alias="named", name_source="user")
        sminos.lifecycle(self.p, sid, "state", state="idle", machine="testhost")
        self.assertEqual({e["kind"]: e.get("thread") for e in self.own(sid)},
                         {"joined": tid, "renamed": tid, "state": tid})
        self.assertEqual(threads.thread_of(sid)["alias"], "named")

    def test_list_json_shows_each_members_thread(self):
        sid, _ = self.session()
        code, out = self.cli("list", "--json")
        self.assertEqual(code, 0, out)
        rows = json.loads(out[:out.rindex("]") + 1])
        [row] = [r for r in rows if r["session"] == sid]
        self.assertEqual((row["thread"], row["opened"]), (threads.stamp(sid), "human"))


# ------------------------------------------------------------ a spawn's child


class SpawnsChild(Machine):
    """spawn_fresh in this process with the stub's two steps replaced: the
    engine's start (run_claude_bg: the child's process and engine record,
    started now) and the launcher's wait for the session's id (poll_uuid),
    inside which the test plays what happens before the launcher goes on."""

    def spawn(self, meanwhile, banner_ok=True):
        launch = uuidlib.uuid4().hex
        child = {"sid": str(uuidlib.uuid4())}

        def start(args, cwd, settings):
            child["sid"], child["proc"] = self.session(kind="bg", sid=child["sid"], started=ms_ago(0))
            return (child["sid"][:8] if banner_ok else ""), "banner"

        def poll(short, max_iter=None):
            meanwhile(child, launch)
            return child["sid"], "working", self.root

        out = io.StringIO()
        with mock.patch.object(records, "new_launch", return_value=launch), \
                mock.patch.object(sminos, "run_claude_bg", side_effect=start), \
                mock.patch.object(sminos, "poll_uuid", side_effect=poll), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            here = os.getcwd()
            os.chdir(self.root)
            try:
                sminos.spawn_fresh(None, "worker", "g", "", "", "a task", self.root, "", "", "", "", False,
                                   [], "spawned")
            except SystemExit:
                child["exit"] = True
            finally:
                os.chdir(here)
        sminos.forget_caches()
        return child, launch

    def child_hook(self, child, launch, claim=True):
        env = {"SMINOS_LAUNCH": launch, "CLAUDE_PID": str(child["proc"].pid)}
        if claim:
            with mock.patch.dict(os.environ, env):
                sminos.claim_launch({"session_id": child["sid"], "hook_event_name": "SessionStart",
                                     "source": "startup"})
        self.hook(child["sid"], env=env)

    def assert_nothing_for(self, sid):
        self.assertEqual(self.human_files(), [])
        self.assertEqual(self.joins(sid), [])

    def assert_one_seat(self, sid):
        [path] = list(sminos.record_files())
        seat = sminos.load_seat(path)
        self.assertEqual(seat["current"], sid)
        self.assertEqual(self.human_files(), [])
        stamps = [j.get("thread") for j in self.joins(sid)]
        self.assertTrue(stamps)
        self.assertEqual(stamps[-1], seat["seat_id"])
        self.assertTrue(self.is_member(sid))
        return seat

    def test_its_own_hook_and_another_processes_reconciliation_make_no_record_while_the_launcher_waits(self):
        def meanwhile(child, launch):
            self.child_hook(child, launch)
            self.assert_nothing_for(child["sid"])
            self.reconcile()
            self.assert_nothing_for(child["sid"])

        child, _ = self.spawn(meanwhile)
        seat = self.assert_one_seat(child["sid"])
        self.assertEqual(len(self.joins(child["sid"])), 1, "one joined, stamped with the seat's id")
        self.assertEqual(seat["opened"], "spawned")

    def test_the_same_when_the_hooks_binding_cannot_be_written(self):
        def meanwhile(child, launch):
            self.child_hook(child, launch, claim=False)   # bind failed: the launch is pending and unbound
            self.assertTrue(os.path.exists(records.pending_path(launch)))
            self.assert_nothing_for(child["sid"])
            self.reconcile()
            self.assert_nothing_for(child["sid"])

        child, _ = self.spawn(meanwhile)
        self.assert_one_seat(child["sid"])

    def test_a_banner_the_launcher_cannot_read_leaves_no_record_while_young_then_it_joins_as_a_session_with_no_seat(
            self):
        child, launch = self.spawn(lambda child, launch: None, banner_ok=False)
        self.assertTrue(child.get("exit"))
        self.assertEqual(list(sminos.record_files()), [])
        self.child_hook(child, launch, claim=False)
        self.reconcile()
        self.assert_nothing_for(child["sid"])
        self.peer_set(child["proc"], startedAt=ms_ago(threads.spawner_bound() + 5))
        self.child_hook(child, launch, claim=False)
        t = threads.thread_of(child["sid"])
        self.assertEqual(t["opened"], "human")
        self.assertTrue(self.is_member(child["sid"]))

    def test_a_launcher_paused_past_the_bound_absorbs_the_record_made_meanwhile(self):
        def meanwhile(child, launch):
            self.peer_set(child["proc"], startedAt=ms_ago(threads.spawner_bound() + 5))
            self.child_hook(child, launch)
            self.assertEqual(len(self.human_files()), 1)
            self.assertEqual(threads.thread_of(child["sid"])["opened"], "human")

        child, _ = self.spawn(meanwhile)
        self.assert_one_seat(child["sid"])
        self.assertEqual(threads.thread_of(child["sid"])["opened"], "spawned")


# ------------------------------------------------------------ adoption


class Adoption(Machine):
    def test_a_member_from_before_threads_is_adopted_with_one_stamped_joined_and_no_second_at_the_next(self):
        sid, _ = self.session()
        self.write_own(sid, [self.old_joined(sid)])
        self.reconcile()
        joins = self.joins(sid)
        self.assertEqual(len(joins), 2)
        self.assertEqual(joins[-1]["thread"], threads.stamp(sid))
        self.assertEqual(joins[-1]["alias"], "old", "joined again as it was")
        self.reconcile()
        self.assertEqual(len(self.joins(sid)), 2)

    def test_a_seat_from_before_threads_is_adopted_too(self):
        sid, _ = self.session()
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "worker", "group": "g", "cwd": self.root,
                                  "status": "idle", "history": []})
        self.write_own(sid, [self.old_joined(sid, alias="worker", seat=seat_id, name_source="seat",
                                             session_kind="seat")])
        self.reconcile()
        joins = self.joins(sid)
        self.assertEqual([j.get("thread") for j in joins], [None, seat_id])
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["opened"], "spawned")
        self.reconcile()
        self.assertEqual(len(self.joins(sid)), 2)

    def test_an_unstamped_joined_written_after_it_is_stamped_again_once(self):
        sid, _ = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        self.write_own(sid, [self.old_joined(sid)])   # an older copy's hooks, from a session started before
        self.reconcile()
        self.reconcile()
        self.assertEqual([j.get("thread") for j in self.joins(sid)], [tid, None, tid])

    def test_retired_by_hand_or_moved_by_join_after_an_unstamped_joined_is_not_joined_again_in_either_project(self):
        other = self.project_of(self.repo("other"))
        retired, proc = self.session()
        self.write_own(retired, [self.old_joined(retired), {"kind": "retired", "by": "x", "reason": "retire",
                                                            "pid": proc.pid}])
        moved = str(uuidlib.uuid4())
        self.write_own(moved, [self.old_joined(moved), {"kind": "retired", "by": "", "reason": "moved",
                                                        "project": other.id}])
        for p in (self.p, other, self.p):
            self.reconcile(p)
        self.assertEqual(len(self.joins(retired)), 1)
        self.assertEqual(len(self.joins(moved)), 1)
        self.assertEqual(self.joins(moved, other), [])
        self.assertFalse(self.is_member(retired) or self.is_member(moved))

    def test_an_adopted_refilled_seats_sessions_hold_its_earlier_occupants(self):
        first, second, current = (str(uuidlib.uuid4()) for _ in range(3))
        sid, _ = self.session(sid=current)
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": current, "alias": "worker", "group": "g",
                                  "cwd": self.root, "status": "idle",
                                  "history": [{"current": first, "short": first[:8], "status": "idle"}]})
        for s in (second, current):
            self.write_own(s, [self.old_joined(s, alias="worker", seat=seat_id, name_source="seat")])
        self.reconcile()
        self.assertEqual(threads.get(seat_id)["sessions"], [first, second, current])

    def test_an_adopted_members_sessions_hold_its_continuation_chain(self):
        old = str(uuidlib.uuid4())
        sid, _ = self.session()
        self.write_own(old, [self.old_joined(old), {"kind": "retired", "by": "", "reason": "continued", "to": sid}])
        self.write_own(sid, [self.old_joined(sid)])
        self.reconcile()
        self.assertEqual(threads.thread_of(sid)["sessions"], [old, sid])


# ------------------------------------------------------------ the reader rule


class ReaderRule(Machine):
    def setUp(self):
        super().setUp()
        with open(VECTORS, "rb") as f:
            raw = f.read()
        with open(PIN) as f:
            pin = json.load(f)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), pin["sha256"], "the copy is its pin's")
        self.rule = json.loads(raw)
        self.assertEqual(self.rule["version"], 1)

    def case_events(self, case, n):
        return [dict(step["event"]) for step in case["steps"][:n]]

    def test_the_vectors_retired_cases_through_the_reducer(self):
        self.assertEqual(len(self.rule["retired"]), 5)
        for case in self.rule["retired"]:
            for n, step in enumerate(case["steps"], 1):
                with self.subTest(case=case["name"], step=n):
                    self.assertEqual(threads.member(self.case_events(case, n)), step["member"])

    def test_the_vectors_retired_cases_through_each_reader(self):
        for case in self.rule["retired"]:
            for n, step in enumerate(case["steps"], 1):
                with self.subTest(case=case["name"], step=n):
                    self.check_readers(case["steps"][:n], step["member"])

    def check_readers(self, steps, expected):
        sminos.forget_caches()
        sid = str(uuidlib.uuid4())
        events = []
        for step in steps:
            e = dict(step["event"])
            if e["kind"] == "joined":
                e.update(self.old_joined(sid, alias="v"))
                e.pop("thread", None)
                if "thread" in step["event"]:
                    e["thread"] = step["event"]["thread"]
            elif e.get("reason") == "moved":
                e["project"] = "6f00aaaa-0000-4000-8000-000000000000"
            events.append(e)
        self.write_own(sid, events)
        own = self.own(sid)
        log = sminos.log_read(self.p)
        got = {
            "latest_membership": sminos.latest_membership(own) == "joined",
            "_memberships": sminos._memberships(log)[0].get(sid) == "joined",
            "_projection": (sminos._projection(log)[sid]["latest"] or {}).get("kind") == "joined",
            "_lineage_scan": sminos._lineage_scan(log)[2].get(sid) == "joined",
            "recorded_project": sminos.recorded_project(sid) is not None,
            "owed_in": sid in self.owed_members(sid),
        }
        # The readers that act on a reconciliation's view read the projection it is made of (no
        # reconciliation here: it would act on a session whose process is gone).
        closed = sminos.sibling_module("sminos_outcomes").closed_sessions(
            types.SimpleNamespace(info=sminos._projection(log)))
        effect = threads.in_effect(own)
        self.assertEqual(sid in closed, effect["kind"] == "retired" and effect.get("reason") == "ended",
                         "closed_sessions")
        for reader, member in got.items():
            self.assertEqual(member, expected, reader)
        # Clear the log for the next step.
        shutil.rmtree(os.path.join(self.p.home, "log"))
        sminos.project_path(self.p, "log")

    def owed_members(self, sid):
        """The sessions `daemon owed` counts as members (owed_in's test), for an event addressed to `sid`."""
        daemon = sminos.daemon_module()
        sminos.log_append(self.p, "testhost/human", "say", to=[{"session": sid, "alias": "v"}], text="hi")
        out = daemon.owed_in(self.p, False, {}, [])
        return {sid} if out[0]["deliveries"] or out[0]["words"] else set()

    def test_a_session_moved_then_an_older_copys_ended_every_reader_answers_the_destination(self):
        other = self.project_of(self.repo("other"))
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        self.end(proc)
        # Moved: the destination's joined not yet written; then an older copy's ended, unstamped.
        self.write_own(sid, [{"kind": "retired", "by": "", "reason": "moved", "project": other.id, "thread": tid},
                             {"kind": "retired", "by": "", "reason": "ended"}])
        sminos._LAST.clear()
        self.assertEqual(sminos.last_project(sid).id, other.id)
        self.assertTrue(sminos.moved_here(other, sid))
        effect = threads.in_effect(self.own(sid))
        self.assertEqual((effect["reason"], effect["project"]), ("moved", other.id))
        self.assertEqual(sminos._projection(sminos.log_read(self.p))[sid]["latest"]["reason"], "moved")

    def test_a_session_continued_then_an_older_copys_ended_its_successor_is_still_found(self):
        old, new = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        self.write_own(old, [self.old_joined(old, thread="t-1"),
                             {"kind": "retired", "by": "", "reason": "continued", "to": new, "thread": "t-1"},
                             {"kind": "retired", "by": "", "reason": "ended"}])
        self.assertEqual(sminos.handed_to(self.p, new), old)
        self.assertEqual(sminos.lineage_of(self.p, new), [old])
        info = sminos._projection(sminos.log_read(self.p))
        self.assertEqual(sminos.lineage(new, info), [old])

    def test_a_guard_under_a_writer_files_lock_reads_through_the_reducer(self):
        sid, _ = self.session()
        self.reconcile()
        self.write_own(sid, [{"kind": "retired", "by": "", "reason": "ended"}])   # an older copy's
        got = sminos.lifecycle(self.p, sid, "renamed", guard=lambda evs: sminos.latest_membership(evs) == "joined",
                               alias="later", name_source="user")
        self.assertEqual(len(got), 1, "a later event of the session's own is still appended")
        self.assertTrue(self.is_member(sid))
        self.reconcile()
        self.assertEqual(len(self.joins(sid)), 1, "and the older ended does not make this code join it again")


# ------------------------------------------------------------ today's transitions, record and log agreeing


class Transitions(Machine):
    def test_its_process_gone_it_ends_stamped_and_its_record_is_set_aside(self):
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        self.end(proc)
        self.reconcile()
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["kind"], e["reason"], e["thread"]), ("retired", "ended", tid))
        self.assertEqual(self.human_files(), [])
        self.assertEqual(self.human_files(aside=True), [tid + ".json"])
        t = threads.get(tid)
        self.assertEqual((t["ended"]["reason"], t.get("pending")), ("ended", None))

    def test_run_again_it_returns_under_the_same_thread(self):
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        self.end(proc)
        self.reconcile()
        self.session(sid=sid)
        self.reconcile()
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["kind"], e["thread"]), ("joined", tid))
        self.assertEqual(self.human_files(), [tid + ".json"])
        self.assertEqual(self.human_files(aside=True), [])
        self.assertFalse(threads.record_ended(threads.get(tid)))

    def test_retired_by_hand_it_ends_with_the_process_it_saw_and_holds_against_it(self):
        sid, proc = self.session(name="hand")
        self.reconcile()
        tid = threads.stamp(sid)
        code, out = self.cli("retire", sid[:8])
        self.assertEqual(code, 0, out)
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["reason"], e["pid"], e["thread"]), ("retire", proc.pid, tid))
        t = threads.get(tid)
        self.assertEqual((t["ended"]["reason"], t["ended"]["pid"]), ("retire", proc.pid))
        self.assertEqual(self.human_files(aside=True), [tid + ".json"])
        self.reconcile()
        self.assertFalse(self.is_member(sid), "the process the retire saw runs on, and does not return it")
        self.end(proc)
        _, proc2 = self.session(sid=sid)
        self.reconcile()
        self.assertTrue(self.is_member(sid), "a new process returns it")
        self.assertEqual(threads.in_effect(self.own(sid))["thread"], tid)

    def test_moved_by_join_both_logs_carry_the_stamp(self):
        other = self.project_of(self.repo("other"))
        sid, _ = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("join", other.name)
        self.assertEqual(code, 0, out)
        here, there = threads.in_effect(self.own(sid)), threads.in_effect(self.own(sid, other))
        self.assertEqual((here["reason"], here["thread"]), ("moved", tid))
        self.assertEqual((there["kind"], there["thread"]), ("joined", tid))
        self.assertEqual(threads.thread_of(sid)["thread"], tid, "one record")

    def test_a_seat_retired_and_purged_ends_by_its_record(self):
        sid, _ = self.session()
        self.cli("seat", "add", "g", "w1", "--session", sid)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        code, out = self.cli("retire", "g/w1")
        self.assertEqual(code, 0, out)
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["status"], seat["ended"]["reason"], seat.get("pending")), ("retired", "retire", None))
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["reason"], e["thread"]), ("retire", seat_id))
        sid2, _ = self.session()
        self.cli("seat", "add", "g", "w2", "--session", sid2)
        code, out = self.cli("remove", "g/w2")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(list(sminos.record_files())), 1, "the removed seat's record is gone")
        self.assertEqual(threads.in_effect(self.own(sid2))["reason"], "retire")


# ------------------------------------------------------------ the journal


class Journal(Machine):
    """An end and a return, the process killed after the record's write,
    and after the events (where an end's settlement and last step follow)."""

    def kill_after_begin(self):
        real = threads.begin

        def begin(*a, **k):
            if real(*a, **k) is not None:
                raise Killed()
            return None
        return mock.patch.object(threads, "begin", side_effect=begin)

    def kill_before_last_step(self):
        real = threads._change

        def change(tid, mutate, *a, **k):
            if mutate.__name__ == "clear":
                raise Killed()
            return real(tid, mutate, *a, **k)
        return mock.patch.object(threads, "_change", side_effect=change)

    def ended_thread(self):
        sid, proc = self.session()
        self.reconcile()
        return sid, proc, threads.stamp(sid)

    def assert_settled(self, sid, tid, kind, reason=None):
        evs = [e for e in self.own(sid) if e.get("op")]
        ops = [(e["kind"], e["op"]) for e in evs]
        self.assertEqual(len(ops), len(set(ops)), "no event appended twice")
        e = threads.in_effect(self.own(sid))
        self.assertEqual(e["kind"], kind)
        if reason:
            self.assertEqual(e["reason"], reason)
        self.assertIsNone(threads.get(tid).get("pending"))
        before = list(self.own(sid))
        self.reconcile()
        self.assertEqual(self.own(sid), before, "a second reconciliation does nothing")
        self.assert_second_registry_agrees(sid)

    def assert_second_registry_agrees(self, sid):
        """A registry that holds only the log reads the same membership."""
        first = threads.member(self.own(sid))
        copy_home = tempfile.mkdtemp(dir=BASE)
        shutil.copytree(os.path.join(self.p.home, "log"), os.path.join(copy_home, "log"))
        events = []
        for name in os.listdir(os.path.join(copy_home, "log")):
            with open(os.path.join(copy_home, "log", name)) as f:
                events += [json.loads(line) for line in f if line.strip()]
        own = sorted((e for e in events if e.get("session") == sid), key=lambda e: (e["ts"], e["seq"]))
        self.assertEqual(threads.member(own), first)

    def test_an_end_killed_after_the_records_write(self):
        sid, proc, tid = self.ended_thread()
        self.end(proc)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        t = threads.get(tid)
        self.assertEqual(t["pending"]["op"], "end")
        self.assertEqual(self.human_files(), [tid + ".json"], "never set aside while its entry is open")
        self.assertTrue(self.is_member(sid))
        self.reconcile()
        self.assert_settled(sid, tid, "retired", "ended")
        self.assertEqual(self.human_files(aside=True), [tid + ".json"])

    def test_an_end_killed_after_its_event(self):
        sid, proc, tid = self.ended_thread()
        self.end(proc)
        with self.kill_before_last_step(), self.assertRaises(Killed):
            self.reconcile()
        self.assertFalse(self.is_member(sid))
        self.assertEqual(self.human_files(), [tid + ".json"], "never set aside while its entry is open")
        self.reconcile()
        self.assert_settled(sid, tid, "retired", "ended")
        self.assertEqual(self.human_files(aside=True), [tid + ".json"])

    def test_a_return_killed_after_the_records_write(self):
        sid, proc, tid = self.ended_thread()
        self.end(proc)
        self.reconcile()
        self.session(sid=sid)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        t = threads.get(tid)
        self.assertEqual((t["pending"]["op"], t.get("ended")), ("return", None))
        self.assertEqual(self.human_files(), [tid + ".json"], "brought back in the record's write")
        self.reconcile()
        self.assert_settled(sid, tid, "joined")

    def test_a_return_killed_after_its_event(self):
        sid, proc, tid = self.ended_thread()
        self.end(proc)
        self.reconcile()
        self.session(sid=sid)
        with self.kill_before_last_step(), self.assertRaises(Killed):
            self.reconcile()
        self.assertTrue(self.is_member(sid))
        self.reconcile()
        self.assert_settled(sid, tid, "joined")

    def test_an_older_copys_unstamped_retire_ends_its_record_and_a_return_cut_short_is_finished_as_a_return(self):
        sid, proc, tid = self.ended_thread()
        self.write_own(sid, [{"kind": "retired", "by": "old", "reason": "retire", "pid": proc.pid}])
        self.reconcile()
        t = threads.get(tid)
        self.assertEqual((t["ended"]["reason"], t["ended"]["by"], t["ended"]["pid"]), ("retire", "old", proc.pid))
        self.assertEqual(self.human_files(aside=True), [tid + ".json"])
        self.end(proc)
        self.session(sid=sid)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        self.reconcile()
        self.assert_settled(sid, tid, "joined")
        self.assertFalse(threads.record_ended(threads.get(tid)), "not ended again")
        self.assertEqual(self.human_files(), [tid + ".json"])

    def test_an_older_copys_unstamped_ended_after_a_stamped_joined_changes_nothing(self):
        sid, proc, tid = self.ended_thread()
        self.write_own(sid, [{"kind": "retired", "by": "", "reason": "ended"}])
        before = len(self.own(sid))
        self.reconcile()
        self.assertEqual(len(self.own(sid)), before)
        self.assertTrue(self.is_member(sid))
        self.assertFalse(threads.record_ended(threads.get(tid)))


# ------------------------------------------------------------ seat add, the hook's lock


class SeatAdd(Machine):
    def test_seat_add_session_on_a_human_opened_thread_is_refused(self):
        sid, _ = self.session()
        self.reconcile()
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertNotEqual(code, 0)
        self.assertIn("its record already keeps it", out)
        self.assertEqual(list(sminos.record_files()), [])

    def test_seat_add_session_on_a_session_with_no_thread_makes_the_seat_as_today(self):
        sid = str(uuidlib.uuid4())
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        self.assertIn("seat g/w added", out)
        self.assertEqual(threads.thread_of(sid)["opened"], "spawned")

    def test_a_session_with_both_a_human_record_and_a_seat_an_older_copy_made_answers_as_human_opened(self):
        sid, _ = self.session()
        self.reconcile()
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        self.assertEqual(threads.thread_of(sid)["opened"], "human")


class HookLock(Machine):
    def test_a_record_write_from_the_hook_that_cannot_have_its_lock_in_time_is_skipped_and_made_by_the_next_reconciliation(
            self):
        sid, _ = self.session()
        os.makedirs(threads.store_dir(), exist_ok=True)
        holder = subprocess.Popen([sys.executable, "-c",
                                   "import fcntl,sys,time\nf=open(sys.argv[1],'a')\nfcntl.flock(f,fcntl.LOCK_EX)\n"
                                   "print('held',flush=True)\ntime.sleep(30)",
                                   os.path.join(threads.store_dir(), ".lock")], stdout=subprocess.PIPE, text=True)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "held")
        with mock.patch.object(sminos, "_RECORD_DEADLINE", time.time() + 0.3):
            self.hook(sid)
        self.assertEqual(self.human_files(), [])
        [j] = self.joins(sid)
        self.assertNotIn("thread", j, "joined, the record left for later")
        holder.kill()
        holder.wait()
        self.reconcile()
        self.assertEqual(len(self.human_files()), 1)
        self.assertEqual(self.joins(sid)[-1]["thread"], threads.stamp(sid))


# ------------------------------------------------------------ a launch's options


class LaunchOptions(Machine):
    def test_what_launch_options_keep(self):
        sid = str(uuidlib.uuid4())
        argv = ["claude", "--model", "opus", "--settings", "/a dir/with space.json", "--settings", '{"env":{}}',
                "--resume", sid, "--permission-mode=auto", "--name", "x", "--add-dir", "/one", "/t w o",
                "--agent", "notes-" + sid, "--dangerously-skip-permissions", "a prompt"]
        self.assertEqual(threads.launch_options(argv),
                         ["--model", "opus", "--settings", "/a dir/with space.json", "--permission-mode", "auto",
                          "--add-dir", "/one", "/t w o", "--dangerously-skip-permissions"])

    def test_a_process_argument_vector_keeps_its_boundaries(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "--model", "a b",
                                 "--settings", "/p q/s.json"])
        self.addCleanup(proc.kill)
        time.sleep(0.3)
        argv = threads.process_argv(proc.pid)
        self.assertEqual(argv[-4:], ["--model", "a b", "--settings", "/p q/s.json"])
        self.assertEqual(threads.launch_options(argv), ["--model", "a b", "--settings", "/p q/s.json"])

    def test_the_hook_notes_them_and_an_unreadable_vector_leaves_options_absent(self):
        sid, proc = self.session()
        self.hook(sid, env={"CLAUDE_PID": str(proc.pid)})
        launch = threads.thread_of(sid)["launch"]
        self.assertEqual(launch["options"], [], "a sleep has no option of the list")
        self.assertEqual(launch["cwd"], self.root)
        self.hook(sid, source="resume", env={"CLAUDE_PID": "999999"})
        self.assertNotIn("options", threads.thread_of(sid)["launch"])


# ------------------------------------------------------------ the lane, the plane


class Lane(unittest.TestCase):
    def test_a_lane_change_sends_gone_first(self):
        import sminos_uplink as uplink
        sent = []
        link = types_link(uplink, sent)
        sid = str(uuidlib.uuid4())
        m = sminos.Member(session=sid, short=sid[:8], alias="a", name_source="derived", machine="testhost",
                          local=True, state="idle", state_age=None, charge="", charge_source="", status="", by="",
                          worktree="", seat=None)
        pid = "6f00bbbb-0000-4000-8000-000000000000"
        link.plane.member_rows = {pid: {sid: m}}
        link.member_known = {pid: object()}
        link.members_sent = {sid: {"t": "member", "session": sid, "project": pid, "lane": "A"}}
        with mock.patch.object(link, "fresh_frame", return_value={"t": "member", "session": sid, "project": pid,
                                                                   "lane": "B"}):
            link.publish_members(0)
        self.assertEqual([(f["session"], f.get("gone"), f.get("lane")) for f in sent],
                         [(sid, True, None), (sid, None, "B")])


def types_link(uplink, sent):
    class LaneStub:
        def send(self, frames, then=None):
            sent.extend(frames)

        def queued(self):
            return 0

    link = uplink.Link.__new__(uplink.Link)
    link.plane = mock.Mock()
    link.plane.bridges.answers.return_value = None
    link.frames, link.members_sent, link.members_unsent = {}, {}, set()
    link.session_lane = LaneStub()
    return link


class PlaneRead(Machine):
    def test_the_planes_idle_read_sees_a_members_row_move_when_only_its_thread_record_changed(self):
        import sminos_plane as plane
        sid, _ = self.session()
        self.reconcile()
        pl = plane.Plane.__new__(plane.Plane)
        pl.members, pl.live, pl.inputs_read = {self.p.id: {sid}}, {}, {}
        [(_, inputs)] = pl.stale({self.p.id: self.p}, False)
        pl.inputs_read[self.p.id] = inputs
        self.assertEqual(pl.stale({self.p.id: self.p}, False), [], "nothing moved")
        threads.update(threads.stamp(sid), {"stopped": sminos.now()})
        self.assertEqual([p.id for p, _ in pl.stale({self.p.id: self.p}, False)], [self.p.id])


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
