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
- An open entry is its record's: the hook leaves it to the reconciliation
  and writes nothing, update() leaves the record alone, a purge stops
  behind one it cannot finish, deletes the file that carries the journal
  last, and a retried one ends once; an older copy's writes only while the
  retirement read is still in effect, in the project whose membership is;
  lane A alone makes a thread, to every lookup; §1's order with a record
  set aside; what list --json shows of a seat; a publication in a fresh
  process reads no record set aside.

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
import threading
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
import endpoint_standin  # noqa: E402 — the endpoint's `audience` frame, for the hub fixture

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
        have = []
        if os.path.exists(path):
            with open(path) as f:
                have = [json.loads(line) for line in f]
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
        # A retire's hold, against a process started before it, follows the retirement in effect.
        self.assertEqual(sminos.retirement_holds(own, {"pid": 1}),
                         effect["kind"] == "retired" and effect.get("reason") in ("retire", "continued"),
                         "retirement_holds")
        # rejoin_former's guard, for a session whose writer under this machine's name now is another.
        got["rejoin_former"] = sminos.daemon_module().joined_elsewhere(own, "elsewhere/" + sid)
        for reader, member in got.items():
            self.assertEqual(member, expected, reader)
        # The visibility snapshot, through its own guard (a view listing the session, so the guard
        # under the writer file's lock decides): a joined again only for a member.
        listed = types.SimpleNamespace(
            info=sminos._projection(log), members=[types.SimpleNamespace(
                session=sid, local=True, alias="v", name_source="user", kind="interactive", state=None)])
        with mock.patch.object(sminos, "view_of", return_value=listed):
            wrote = sminos.sibling_module("sminos_visibility").snapshot(sid, self.p)
        self.assertEqual(bool(wrote), expected, "sminos_visibility.snapshot")
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
        self.addCleanup(holder.stdout.close)
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
        self.addCleanup(proc.wait)
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


# ------------------------------------------------------------ M1's review: the journal's edges


class OpenEntry(Machine):
    """A record whose entry is open is the entry's: the hook leaves it to the
    reconciliation, an update leaves it alone."""

    def kill_after_begin(self):
        real = threads.begin

        def begin(*a, **k):
            if real(*a, **k) is not None:
                raise Killed()
            return None
        return mock.patch.object(threads, "begin", side_effect=begin)

    def returning(self):
        """A thread ended and run again, its return cut after the record's write."""
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        self.end(proc)
        self.reconcile()
        self.session(sid=sid)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        t = threads.get(tid)
        self.assertEqual((t["pending"]["op"], t.get("ended")), ("return", None))
        return sid, tid

    def joins_after_end(self, sid):
        own = self.own(sid)
        last_end = max(i for i, e in enumerate(own) if e["kind"] == "retired")
        return [e for e in own[last_end:] if e["kind"] == "joined"]

    def record_bytes(self, tid):
        with open(os.path.join(threads.store_dir(), tid + ".json"), "rb") as f:
            return f.read()

    def test_a_hook_meeting_an_open_entry_defers_it_to_the_reconciliation_and_writes_nothing(self):
        sid, tid = self.returning()
        before = self.record_bytes(tid)
        with mock.patch.object(sminos, "_RECORD_DEADLINE", time.time() + 30):   # as run_record sets it
            for event, source in (("SessionStart", "startup"), ("SessionStart", "resume"), ("UserPromptSubmit", "")):
                self.hook(sid, event=event, source=source)
        self.assertEqual(self.joins_after_end(sid), [], "no joined around the entry")
        self.assertEqual(self.record_bytes(tid), before, "and no write of its record")
        self.reconcile()
        [j] = self.joins_after_end(sid)
        self.assertTrue(j.get("op"), "the reconciliation's replay appends the return's own joined")
        self.assertIsNone(threads.get(tid).get("pending"))

    def test_a_join_whose_writer_lock_sees_an_entry_begun_meanwhile_appends_nothing(self):
        sid, tid = self.returning()
        guard = sminos.record_settled(threads.get(tid), None)
        self.assertFalse(guard(self.own(sid)), "the record is read again under the writer file's lock")

    def test_a_hook_meeting_an_open_end_with_a_publication_owed_appends_nothing(self):
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.cli("retire", sid[:8])
        self.assertEqual(threads.get(tid)["pending"]["op"], "end")
        # The record now publishes owners the member's joined does not carry: an owner update owed.
        member = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
        records.establish(sid, {**records.default_provenance("launch"), "owners": [member], "principal": member,
                                "origin": {"kind": "terminal"}})
        self.assertTrue(sminos.published_provenance(sid), "a publication is owed")
        before = list(self.own(sid))
        with mock.patch.object(sminos, "_RECORD_DEADLINE", time.time() + 30):   # as run_record sets it
            for event, source in (("SessionStart", "resume"), ("UserPromptSubmit", ""), ("Stop", "")):
                self.hook(sid, event=event, source=source)
        self.assertEqual(self.own(sid), before, "nothing appended around the open end")
        self.reconcile()
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["kind"], e["reason"], bool(e.get("op"))), ("retired", "retire", True))
        self.assertEqual([x for x in self.own(sid)[len(before):] if x["kind"] == "joined"], [],
                         "and the replay's end comes with no joined before it")

    def test_update_leaves_a_record_with_an_open_entry_alone(self):
        sid, tid = self.returning()
        self.assertFalse(threads.update(tid, {"stopped": sminos.now()}))
        self.assertNotIn("stopped", threads.get(tid))

    def test_the_returns_alias_is_copied_into_the_record_as_its_entry_clears(self):
        sid, tid = self.returning()
        entry = threads.get(tid)["pending"]
        [owed] = entry["events"]
        self.reconcile()
        self.assertEqual(threads.get(tid)["alias"], owed["alias"])


class SeatPurge(Machine):
    def seat(self, alias="w"):
        sid, proc = self.session()
        code, out = self.cli("seat", "add", "g", alias, "--session", sid)
        self.assertEqual(code, 0, out)
        return sid, sminos.load_seat(next(sminos.record_files()))["seat_id"]

    def failing_appends(self):
        return mock.patch.object(sminos, "_append", side_effect=OSError("disk full"))

    def test_a_retire_whose_event_failed_then_remove_stops_behind_the_entry_and_appends_nothing_around_it(self):
        sid, seat_id = self.seat()
        before = list(self.own(sid))
        with self.failing_appends():
            code, out = self.cli("retire", "g/w")
            self.assertNotEqual(code, 0, out)
            self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["pending"]["op"], "end")
            code, out = self.cli("remove", "g/w")
        self.assertNotEqual(code, 0, out)
        self.assertIn("next reading verb finishes it", out)
        self.assertTrue(os.path.exists(sminos.meta_path(seat_id)), "the record that holds the entry stays")
        self.assertEqual(self.own(sid), before, "no event outside the journal")
        code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(sminos.meta_path(seat_id)))
        retired = [e for e in self.own(sid) if e["kind"] == "retired"]
        self.assertEqual([(e["reason"], bool(e.get("op")), e["thread"]) for e in retired],
                         [("retire", True, seat_id)], "one retired, the retire's own, and none for the purge")

    def test_a_purge_of_an_ended_seat_cut_inside_its_file_cleanup_is_finished_by_the_replay(self):
        sid, seat_id = self.seat()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        for path in sminos.seat_files(seat_id)[1:]:
            with open(path, "a"):
                pass
        real, calls = os.unlink, []

        def unlink(path, *a, **k):
            if path in sminos.seat_files(seat_id):
                calls.append(path)
                if len(calls) == 2:
                    raise Killed()
            return real(path, *a, **k)
        with mock.patch.object(threads.os, "unlink", side_effect=unlink), self.assertRaises(Killed):
            self.cli("remove", "g/w")
        self.assertNotIn(sminos.meta_path(seat_id), calls, "the record is deleted last")
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["pending"]["last"], "purge")
        self.reconcile()
        self.assertEqual([p for p in sminos.seat_files(seat_id) if os.path.exists(p)], [])
        self.assertEqual(len([e for e in self.own(sid) if e["kind"] == "retired"]), 1,
                         "the session was no member: the purge owed no event")


class SeatPurgeRetried(SeatPurge):
    def test_a_remove_cut_after_its_stamped_event_and_retried_through_the_verb_ends_once(self):
        sid, seat_id = self.seat()
        real = threads._change

        def change(tid, mutate, *a, **k):
            if mutate.__name__ == "clear":
                raise Killed()
            return real(tid, mutate, *a, **k)
        with mock.patch.object(threads, "_change", side_effect=change), self.assertRaises(Killed):
            self.cli("remove", "g/w")
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["pending"]["last"], "purge")
        code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(sminos.meta_path(seat_id)))
        retired = [e for e in self.own(sid) if e["kind"] == "retired"]
        self.assertEqual([(e["reason"], bool(e.get("op")), e.get("thread")) for e in retired],
                         [("retire", True, seat_id)], "one retired, stamped: none after the replay")


class OlderWritesScope(Machine):
    def at(self, seconds):
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + seconds)) + ".000Z"

    def reopened_elsewhere(self):
        other = self.project_of(self.repo("other"))
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        # An older CLI's retire, then the session reopened and joined in the other project, a second later.
        self.write_own(sid, [{"kind": "retired", "by": "old", "reason": "retire", "pid": proc.pid,
                              "ts": self.at(5)}])
        self.write_own(sid, [self.old_joined(sid, alias="there", thread=tid, cwd=other.root, ts=self.at(6))], other)
        return other, sid, tid

    def test_an_older_retire_in_a_project_the_session_has_since_left_ends_nothing(self):
        other, sid, tid = self.reopened_elsewhere()
        self.reconcile(self.p)
        t = threads.get(tid)
        self.assertFalse(threads.record_ended(t))
        self.assertEqual(self.human_files(), [tid + ".json"], "not set aside")
        self.assertTrue(self.is_member(sid, other))

    def test_the_project_is_checked_again_under_the_records_lock(self):
        other, sid, tid = self.reopened_elsewhere()
        real, seen = sminos.membership_here, []

        def first_stale(project, s):
            seen.append(s)
            return True if len(seen) == 1 else real(project, s)
        with mock.patch.object(sminos, "membership_here", side_effect=first_stale):
            self.reconcile(self.p)
        self.assertGreaterEqual(len(seen), 2, "asked again as the end is begun")
        self.assertFalse(threads.record_ended(threads.get(tid)))

    def test_a_retirement_no_longer_in_effect_by_the_records_lock_ends_nothing(self):
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        self.write_own(sid, [{"kind": "retired", "by": "old", "reason": "retire", "pid": proc.pid}])   # an older CLI's
        latest, joined, effect = sminos._memberships(sminos.log_read(self.p))   # the reconciliation's reading
        self.assertEqual(effect[sid]["reason"], "retire")
        # Reopened and joined again in the same project before the rule acts.
        fields = sminos.joined_fields("again", "user", self.root, session_kind="interactive", session=sid)
        self.assertTrue(sminos.lifecycle(self.p, sid, "joined", **fields))
        sminos.older_writes(self.p, threads.human_threads(), effect, joined, set())
        self.assertFalse(threads.record_ended(threads.get(tid)))
        self.assertEqual(self.human_files(), [tid + ".json"], "not set aside")
        self.assertTrue(self.is_member(sid))


class LaneAndOrder(Machine):
    def test_seat_add_session_on_a_lane_b_session_makes_no_thread(self):
        sid, _ = self.session()
        records.establish(sid, records.default_provenance())
        records.set_controller(sid, "B")
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        raw = sminos.load_seat(next(sminos.record_files()))
        self.assertNotIn("opened", raw)
        self.assertIsNone(threads.thread_of(sid))
        self.assertIsNone(threads.get(raw["seat_id"]))
        self.assertEqual([t for t in threads.all_threads(ended=True) if t["thread"] == raw["seat_id"]], [])
        self.assertEqual(threads.stamp(sid), "")
        self.assertTrue(all("thread" not in j for j in self.joins(sid)))

    def test_a_thread_whose_session_turned_lane_b_ends_stamped_when_its_process_ends(self):
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        records.set_controller(sid, "B")
        self.end(proc)
        self.reconcile()
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["kind"], e["reason"], e["thread"]), ("retired", "ended", tid))

    def test_an_ended_human_opened_record_answers_before_an_older_copys_seat_for_its_current_session(self):
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        self.end(proc)
        self.reconcile()
        self.assertEqual(self.human_files(aside=True), [tid + ".json"])
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        self.assertEqual(threads.thread_of(sid)["thread"], tid)

    def test_a_reopened_human_opened_session_an_older_copy_seated_returns_under_its_own_thread(self):
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        self.end(proc)
        self.reconcile()
        self.assertTrue(threads.record_ended(threads.get(tid)))
        seat_id = str(uuidlib.uuid4())   # the seat record an older copy writes for it
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        self.session(sid=sid)
        self.reconcile()
        # What a remote reader sees: the log's latest joined of the session.
        j = self.joins(sid)[-1]
        self.assertEqual((j["thread"], bool(j.get("op"))), (tid, True), "the journaled return, stamped as its own")
        self.assertFalse(threads.record_ended(threads.get(tid)))
        self.assertEqual(self.human_files(), [tid + ".json"])
        self.assertNotIn("opened", sminos.load_seat(sminos.meta_path(seat_id)), "the older copy's seat left as is")
        self.assertTrue(self.is_member(sid))

    def seated_after_its_end(self, lane, older_joined):
        """A human-opened thread ended; the seat an older copy writes for its
        session; the session reopened in `lane`, with or without the older
        copy's unstamped `joined` already in the log; then a reconciliation."""
        sid, proc = self.session()
        self.reconcile()
        tid = threads.stamp(sid)
        self.end(proc)
        self.reconcile()
        self.assertTrue(threads.record_ended(threads.get(tid)))
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        self.session(sid=sid)
        if lane == "B":
            records.set_controller(sid, "B")
        if older_joined:
            self.write_own(sid, [self.old_joined(sid, alias="w", seat=seat_id, name_source="seat")])
        before = len(self.own(sid))
        self.reconcile()
        return sid, tid, seat_id, self.own(sid)[before:]

    def test_one_choice_of_thread_at_the_join_and_at_the_adoption_in_either_lane(self):
        for lane in ("A", "B"):
            for older_joined in (False, True):
                with self.subTest(lane=lane, older_joined=older_joined), self.fresh_machine_after():
                    sid, tid, seat_id, new = self.seated_after_its_end(lane, older_joined)
                    joins = [e for e in new if e["kind"] == "joined"]
                    self.assertNotIn(seat_id, [e.get("thread") for e in self.own(sid)], "never the seat's id")
                    self.assertNotIn("opened", sminos.load_seat(sminos.meta_path(seat_id)), "the seat left as is")
                    self.assertTrue(self.is_member(sid))
                    if lane == "A":
                        [j] = joins
                        self.assertEqual((j["thread"], bool(j.get("op"))), (tid, True), "the journaled return")
                        self.assertFalse(threads.record_ended(threads.get(tid)))
                        self.assertEqual(self.human_files(), [tid + ".json"])
                    else:
                        self.assertTrue(all("thread" not in e for e in joins), "a lane B session revives none")
                        self.assertEqual(len(joins), 0 if older_joined else 1)
                        self.assertTrue(threads.record_ended(threads.get(tid)), "the ended record stays ended")
                        self.assertEqual(self.human_files(aside=True), [tid + ".json"])

    @contextlib.contextmanager
    def fresh_machine_after(self):
        """Each case on a machine of its own, whatever the case before did."""
        try:
            yield
        finally:
            self.stop_all()
            self.procs = []
            self.setUp()

    def test_list_json_pairs_a_human_threads_id_with_human_though_its_joined_names_a_seat(self):
        sid, tid, seat_id, _ = self.seated_after_its_end("A", True)
        code, out = self.cli("list", "--json")
        self.assertEqual(code, 0, out)
        rows = json.loads(out[:out.rindex("]") + 1])
        [row] = [r for r in rows if r["session"] == sid]
        self.assertEqual((row["thread"], row["opened"]), (tid, "human"))
        j = self.joins(sid)[-1]
        self.assertEqual(j["seat"], seat_id, "the legacy seat field kept on the event")

    def test_a_seat_bound_after_its_sessions_legacy_bg_joined_is_restated_as_spawned(self):
        sid, _ = self.session(kind="bg")
        self.write_own(sid, [{**self.old_joined(sid, alias="bgjob"), "session_kind": "bg"}])   # before the binding
        seat_id = str(uuidlib.uuid4())   # the launcher binds the seat
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "worker", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        self.reconcile()
        j = self.joins(sid)[-1]
        self.assertEqual((j["thread"], j["seat"], j["alias"]), (seat_id, seat_id, "worker"))
        code, out = self.cli("list", "--json")
        self.assertEqual(code, 0, out)
        [row] = [r for r in json.loads(out[:out.rindex("]") + 1]) if r["session"] == sid]
        self.assertEqual((row["thread"], row["opened"]), (seat_id, "spawned"))

    def test_a_rebuilt_seats_sessions_are_oldest_first_with_its_current_last(self):
        early, first, second, before, current = (str(uuidlib.uuid4()) for _ in range(5))
        seat_id = str(uuidlib.uuid4())
        # An occupant older than the history's window, in the log alone.
        self.write_own(early, [self.old_joined(early, alias="worker", seat=seat_id, name_source="seat")])
        time.sleep(0.01)
        first_ended = sminos.now(ms=True)
        time.sleep(0.01)
        self.write_own(second, [self.old_joined(second, alias="worker", seat=seat_id, name_source="seat")])
        # The current session continues one the engine handed it from (a lineage chain).
        self.write_own(before, [self.old_joined(before, alias="worker"),
                                {"kind": "retired", "by": "", "reason": "continued", "to": current}])
        self.session(sid=current)
        self.write_own(current, [self.old_joined(current, alias="worker", seat=seat_id, name_source="seat")])
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": current, "alias": "worker", "group": "g",
                                  "cwd": self.root, "status": "idle",
                                  "history": [{"current": first, "short": first[:8], "status": "idle",
                                               "ended": first_ended},
                                              {"current": second, "short": second[:8], "status": "idle"}]})
        self.reconcile()
        self.assertEqual(threads.get(seat_id)["sessions"], [early, first, second, before, current])


class Surfaces(Machine):
    def test_list_json_carries_thread_and_opened_and_none_of_the_records_internal_keys(self):
        sid, _ = self.session()
        self.cli("seat", "add", "g", "w", "--session", sid)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        threads.note_launch(seat_id, self.root, ["--model", "opus"])
        sminos.meta_set(seat_id, {"sessions": [str(uuidlib.uuid4()), sid]})
        for private in (True, False):
            with self.subTest(private=private):
                view = sminos.view_of(self.p)
                [m] = [m for m in view.members if m.session == sid]
                row = sminos.member_json(m, self.p, private=private)
                self.assertEqual((row["thread"], row["opened"]), (seat_id, "spawned"))
                self.assertEqual(sorted(set(row["seat"]) & set(threads.SEAT_KEYS)), [])

    def test_the_first_publication_after_an_archive_change_in_a_fresh_process_reads_no_record_set_aside(self):
        for _ in range(20):   # an archive of unrelated ended threads
            s, proc = self.session()
            self.reconcile()
            self.end(proc)
            self.reconcile()
        sid, _ = self.session()
        records.establish(sid, records.default_provenance())
        records.set_controller(sid, "B")
        member, member_proc = self.session()
        self.reconcile()
        self.end(member_proc)
        self.reconcile()   # the archive changed just now: one more record set aside
        self.assertEqual(len(self.human_files(aside=True)), 21)
        probe = (
            "import json, os, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import sminos, sminos_threads as threads\n"
            "read = []\n"
            "real_at, real_list = threads._human_at, os.listdir\n"
            "aside = os.path.realpath(threads.aside_dir())\n"
            "def at(path):\n"
            "    if os.path.realpath(os.path.dirname(path)) == aside: read.append(path)\n"
            "    return real_at(path)\n"
            "def listdir(path='.'):\n"
            "    if os.path.realpath(str(path)) == aside: read.append(str(path))\n"
            "    return real_list(path)\n"
            "threads._human_at, os.listdir = at, listdir\n"
            "p = sminos.resolve_project(sys.argv[2])\n"
            "n = sminos.daemon_module().publish_state(p, sminos.view_of(p), {})\n"
            "print(json.dumps({'published': n, 'read': read}))\n")
        r = subprocess.run([sys.executable, "-B", "-c", probe, SCRIPTS, self.root], capture_output=True, text=True,
                           cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertGreaterEqual(got["published"], 1)
        self.assertEqual(got["read"], [], "the stamp reads only the live stores")
        sminos.forget_caches()
        self.assertNotIn("thread", [e for e in self.own(sid) if e["kind"] == "state"][-1])



# ------------------------------------------------------------ M2: one thread across its session ids


OWNED = {**records.default_provenance("launch"), "owners": ["m-ann"], "principal": "m-ann",
         "access": "org-view", "shares": [{"member": "m-bob", "grade": "view"}]}
REACH = ("owners", "access", "shares")


def reach_of(sid):
    rec = records.read(sid) or {}
    return tuple(json.dumps(rec.get(k), sort_keys=True) for k in REACH)


class Sessions(Machine):
    """M2's sessions: a hand-off as the engine leaves it, a refill, and a
    second registry that holds only the log (another machine)."""

    def handoff_transcript(self, old, new):
        """The old session's transcript as the engine leaves it at a hand-off
        to a background job (`continued-in`, then nothing of a turn)."""
        d = os.path.join(os.environ["HOME"], ".claude", "projects", "p-work")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, old + ".jsonl"), "a") as f:
            for r in ({"type": "user", "sessionId": old, "cwd": self.root,
                       "message": {"role": "user", "content": "keep going"}},
                      {"type": "assistant", "uuid": "h-" + old[:4], "message": {
                          "role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}},
                      {"type": "continued-in", "sessionId": old, "continuedInSessionId": new}):
                f.write(json.dumps(r) + "\n")
        # The engine wrote the transcript long before; here it is new, so the index is listed again.
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        sminos.forget_caches()

    def member(self, name="handy", charge="owns the hand-off", owned=True):
        """A human-opened member with a name, an in-charge line and an owner of its own."""
        sid, proc = self.session(name=name)
        if owned:
            records.establish(sid, OWNED)
        self.reconcile()
        sminos.lifecycle(self.p, sid, "renamed", alias=name, name_source="user")
        if charge:
            sminos.lifecycle(self.p, sid, "in-charge", text=charge, source="set")
        sminos.forget_caches()
        return sid, proc, threads.stamp(sid)

    def job(self, old, name="handyjob"):
        sid = str(uuidlib.uuid4())
        self.handoff_transcript(old, sid)
        _, proc = self.session(kind="bg", sid=sid, name=name)
        self.peer_set(proc, nameSource="auto")
        return sid, proc

    def row(self, sid, p=None):
        return next((m for m in sminos.view_of(p or self.p).members if m.session == sid), None)

    def stamps(self, sid, p=None):
        return {e.get("thread") for e in self.own(sid, p) if e["kind"] in ("joined", "retired")}

    def kill_after_begin(self, nth=1):
        """The process dies after the `nth` journaled operation it begins."""
        real, begun = threads.begin, []

        def begin(*a, **k):
            entry = real(*a, **k)
            if entry is not None:
                begun.append(entry)
                if len(begun) == nth:
                    raise Killed()
            return entry
        return mock.patch.object(threads, "begin", side_effect=begin)

    def after_begin(self, op, then):
        """then(entry) runs once, right after the first `op` entry is begun:
        what another process does meanwhile."""
        real, done = threads.begin, []

        def begin(*a, **k):
            entry = real(*a, **k)
            if entry is not None and entry["op"] == op and not done:
                done.append(entry)
                then(entry)
            return entry
        return mock.patch.object(threads, "begin", side_effect=begin)

    def rewrite(self, tid, change):
        """A human-opened record changed in its file, as another process's write leaves it."""
        path = threads._human_path(tid)
        with open(path) as f:
            rec = json.load(f)
        change(rec)
        sminos.write_json(path, rec)
        sminos.forget_caches()

    def kill_before_event(self, kind, session):
        """The process dies as it would append the entry's `kind` event of
        `session` (of any session, for None)."""
        real = threads._owe

        def owe(project, entry, event, appended, append):
            if event["kind"] == kind and session in (None, event["session"]):
                raise Killed()
            return real(project, entry, event, appended, append)
        return mock.patch.object(threads, "_owe", side_effect=owe)

    def kill_at_change(self, which):
        """The process dies at the finish's write named `which`: "delete" (an
        absorption's other record) or "clear" (the entry's last step)."""
        real = threads._change

        def change(tid, mutate, *a, **k):
            if (which == "clear" and mutate.__name__ == "clear") or (which == "delete" and mutate.__name__ == "<lambda>"):
                raise Killed()
            return real(tid, mutate, *a, **k)
        return mock.patch.object(threads, "_change", side_effect=change)

    def assert_finished(self, tid, sessions):
        """The entry finished: none open, no event twice; a second
        reconciliation appends nothing."""
        self.assertIsNone(threads.get(tid).get("pending"))
        for sid in sessions:
            ops = [(e["kind"], e["op"]) for e in self.own(sid) if e.get("op")]
            self.assertEqual(len(ops), len(set(ops)), "no event appended twice")
        before = {sid: list(self.own(sid)) for sid in sessions}
        self.reconcile()
        self.assertEqual({sid: list(self.own(sid)) for sid in sessions}, before, "the next one does nothing")

    def fresh(self):
        """A fresh machine, for the next subtest."""
        self.stop_all()
        self.procs = []
        self.setUp()

    @contextlib.contextmanager
    def elsewhere(self, edit=None):
        """Another machine whose registry holds only this project's log: no
        engine records, no seats, no thread records, another name. `edit(p)`
        changes its copy of the log first (what has reached it so far)."""
        saved = {k: os.environ.get(k) for k in ("HOME", "SMINOS_HOME", "DAEMON_HOST")}
        there = tempfile.mkdtemp(dir=BASE)
        log = os.path.join(self.p.home, "log")
        os.environ.update(HOME=os.path.join(there, "h"), SMINOS_HOME=os.path.join(there, "s"),
                          DAEMON_HOST="otherhost")
        os.makedirs(os.path.join(os.environ["HOME"], ".claude", "sessions"))
        os.makedirs(os.environ["SMINOS_HOME"])
        sminos.forget_caches()
        p = self.project_of(self.root)
        shutil.copytree(log, os.path.join(p.home, "log"), dirs_exist_ok=True)
        if edit is not None:
            edit(p)
        sminos.forget_caches()
        try:
            yield p
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            sminos.forget_caches()

    def reached(self, p, name):
        """The session the name reaches as a tag (`say`'s resolution) from project `p`."""
        t = sminos.leading_tags("@%s hi" % name)[0]
        return sminos._resolve_tag(p, t)[1].session

    def target(self, name):
        """The session `send` aims at for `name` (find_target), from the project's checkout."""
        here = os.getcwd()
        os.chdir(self.root)
        try:
            got = sminos.find_target(name)
        finally:
            os.chdir(here)
        return got[2].session if got[0] == "member" else (got[2] or got[1]["current"])

    def refill(self, seat_id, alias="worker", brief="", cwd=None):
        """spawn_fresh onto the seat (a `sminos fill` without --resume): the
        engine's start and the launcher's wait replaced, the new session's
        own launch provenance pending as a spawn leaves it."""
        new = {"sid": str(uuidlib.uuid4())}

        cwd = cwd or self.root

        def start(args, at, settings):
            new["sid"], new["proc"] = self.session(root=cwd, kind="bg", sid=new["sid"], started=ms_ago(0))
            return new["sid"][:8], "banner"

        def poll(short, max_iter=None):
            if "meanwhile" in new:
                new["meanwhile"]()
            return new["sid"], "idle", cwd

        out = io.StringIO()
        with mock.patch.object(sminos, "run_claude_bg", side_effect=start), \
                mock.patch.object(sminos, "poll_uuid", side_effect=poll), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            here = os.getcwd()
            os.chdir(self.root)
            try:
                sminos.spawn_fresh(seat_id, alias, "g", "", brief, "a task", cwd, "", "", "", "", False, [],
                                   "spawned")
            finally:
                os.chdir(here)
        sminos.forget_caches()
        return new["sid"], new["proc"], out.getvalue()

    def seated(self, alias="worker", charge="keeps the seat"):
        """A seat holding a session with an owner of its own and an in-charge line; its process gone."""
        sid, proc = self.session()
        records.establish(sid, OWNED)
        code, out = self.cli("seat", "add", "g", alias, "--session", sid)
        self.assertEqual(code, 0, out)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        if charge:
            sminos.lifecycle(self.p, sid, "in-charge", text=charge, source="set")
        self.end(proc)
        return sid, seat_id


class HandOff(Sessions):
    def test_a_human_opened_session_handed_to_a_background_job_goes_on_as_its_thread(self):
        old, oproc, tid = self.member()
        job, _ = self.job(old)
        self.reconcile()   # the job is seen while the interactive process still exits
        self.end(oproc)
        self.reconcile()
        t = threads.get(tid)
        self.assertEqual((t["current"], t["sessions"]), (job, [old, job]))
        self.assertEqual(self.human_files(), [tid + ".json"], "one record")
        last = threads.in_effect(self.own(old))
        self.assertEqual((last["reason"], last["to"], last["thread"]), ("continued", job, tid))
        self.assertEqual(self.stamps(job), {tid})
        self.assertEqual(self.stamps(old), {tid})
        self.assertEqual(reach_of(job), reach_of(old), "the job's record has the old one's owners, access and shares")
        rows = [m for m in sminos.view_of(self.p).members]
        self.assertEqual([(m.session, m.alias, m.charge) for m in rows], [(job, "handy", "owns the hand-off")])
        self.assertEqual(rows[0].former, (old,))
        with self.elsewhere() as p:
            rows = [m for m in sminos.view_of(p).members]
            self.assertEqual([(m.session, m.alias, m.charge, m.thread, m.former) for m in rows],
                             [(job, "handy", "owns the hand-off", tid, (old,))], "the same from the log alone")
            self.assertEqual(rows[0].owners, ("m-ann",))

    def test_the_process_that_handed_it_off_still_running_writes_nothing_and_a_new_process_is_a_thread_of_its_own(
            self):
        old, oproc, tid = self.member()
        job, _ = self.job(old)
        self.reconcile()
        self.reconcile()
        own = self.own(old)
        self.assertEqual(threads.in_effect(own)["reason"], "continued", "no joined of its own while it exits")
        self.hook(old)
        self.assertEqual(self.own(old), own, "nor from its hook")
        self.assertEqual(self.human_files(), [tid + ".json"], "no record of its own")
        self.end(oproc)
        _, again = self.session(sid=old, started=ms_ago(-1))
        self.reconcile()
        mine = threads.thread_of(old)
        self.assertNotEqual(mine["thread"], tid, "a thread of its own")
        self.assertEqual((mine["opened"], mine["current"], mine["sessions"]), ("human", old, [old]))
        self.assertEqual(threads.in_effect(self.own(old))["thread"], mine["thread"])
        self.assertEqual((threads.get(tid)["current"], threads.get(tid)["sessions"]), (job, [old, job]),
                         "the thread that went on keeps the session")

    def test_a_hand_off_killed_after_its_records_write_is_finished_by_the_next_reconciliation(self):
        old, oproc, tid = self.member()
        job, _ = self.job(old)
        self.end(oproc)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        self.assertEqual(threads.get(tid)["pending"]["op"], "advance")
        self.assertNotEqual(reach_of(job), reach_of(old), "nothing carried yet")
        self.reconcile()
        self.assert_finished(tid, (old, job))
        self.assertEqual(reach_of(job), reach_of(old), "the replay carries the reach")
        self.assertEqual(self.stamps(job), {tid})
        self.assertEqual(threads.in_effect(self.own(old))["to"], job)

    def test_a_hand_off_killed_after_the_old_sessions_retirement_is_finished_by_the_next_reconciliation(self):
        old, oproc, tid = self.member()
        job, _ = self.job(old)
        self.end(oproc)
        with self.kill_before_event("joined", job), self.assertRaises(Killed):
            self.reconcile()
        self.assertEqual(threads.in_effect(self.own(old))["reason"], "continued")
        self.reconcile()
        self.assert_finished(tid, (old, job))
        self.assertEqual(len([e for e in self.own(old) if e.get("reason") == "continued"]), 1)
        self.assertEqual(threads.in_effect(self.own(job))["thread"], tid)

    def test_a_hand_off_whose_continued_an_older_copy_wrote_is_finished_the_same_way(self):
        old, oproc, tid = self.member()
        job = str(uuidlib.uuid4())
        self.end(oproc)
        self.write_own(old, [{"kind": "retired", "by": "", "reason": "continued", "to": job}])   # unstamped
        self.session(kind="bg", sid=job)
        self.reconcile()
        t = threads.get(tid)
        self.assertEqual((t["current"], t["sessions"], t.get("pending")), (job, [old, job], None))
        self.assertEqual(len([e for e in self.own(old) if e["kind"] == "retired"]), 1, "not retired again")
        self.assertEqual(threads.in_effect(self.own(job))["thread"], tid)
        self.assertEqual(reach_of(job), reach_of(old))
        self.assertEqual(self.human_files(), [tid + ".json"])


    def test_a_membership_decided_after_the_hand_off_read_it_stands(self):
        for change in ("retired", "moved"):
            with self.subTest(change=change):
                self.fresh()
                other = self.project_of(self.repo("other"))
                old, oproc, tid = self.member()
                job, _ = self.job(old)
                self.end(oproc)
                real, done = threads.begin, []

                def begin(*a, _change=change, _old=old, _there=other, **k):
                    if a[1] == "advance" and not done:
                        # An older copy's write, between the hand-off's read of `old` and its record's lock.
                        done.append(_change)
                        if _change == "retired":
                            self.write_own(_old, [{"kind": "retired", "by": "keeper", "reason": "retire"}])
                        else:
                            self.write_own(_old, [self.old_joined(_old, alias="handy", cwd=_there.root)], p=_there)
                    return real(*a, **k)
                with mock.patch.object(threads, "begin", side_effect=begin):
                    self.reconcile()
                self.assertTrue(done)
                t = threads.get(tid)
                self.assertEqual((t["current"], t["sessions"], t.get("pending")), (old, [old], None),
                                 "the thread did not advance over the newer decision")
                self.assertFalse([e for e in self.own(old) if e.get("reason") == "continued"], "no continued")
                self.assertNotIn(tid, self.stamps(job), "the job joined no thread of the old session's")

    def test_the_hooks_hand_off_of_a_predecessor_from_before_threads_waits_no_longer_than_its_deadline(self):
        old = str(uuidlib.uuid4())
        self.write_own(old, [self.old_joined(old, alias="older")])   # a member from before threads: no record
        job, _ = self.job(old)
        os.makedirs(threads.store_dir(), exist_ok=True)
        holder = subprocess.Popen([sys.executable, "-c",
                                   "import fcntl,sys,time\nf=open(sys.argv[1],'a')\nfcntl.flock(f,fcntl.LOCK_EX)\n"
                                   "print('held',flush=True)\ntime.sleep(30)",
                                   os.path.join(threads.store_dir(), ".lock")], stdout=subprocess.PIPE, text=True)
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "held")
        err = io.StringIO()
        began = time.time()
        with mock.patch.object(sminos, "_RECORD_DEADLINE", time.time() + 0.3), contextlib.redirect_stderr(err):
            self.assertEqual(sminos.hand_off(self.p, old, job), [])
        self.assertLess(time.time() - began, 5, "bounded by the hook's deadline")
        self.assertIn("waits", err.getvalue())
        self.assertEqual(self.human_files(), [], "nothing made")
        holder.kill()
        holder.wait()
        self.reconcile()
        tid = threads.thread_of(job)["thread"]
        self.assertEqual(threads.get(tid)["sessions"], [old, job], "the next reconciliation adopts and hands off")

    def test_the_jobs_hook_making_its_record_around_the_advance_never_leaves_two_threads(self):
        for seat in (False, True):
            for when in ("before", "after"):
                with self.subTest(seat=seat, when=when):
                    self.fresh()
                    if seat:
                        old, tid = self.seated(alias="keeper")
                        _, oproc = self.session(sid=old)
                    else:
                        old, oproc, tid = self.member()
                    job, _ = self.job(old)
                    self.end(oproc)
                    made, real = [], threads.begin

                    def begin(*a, _job=job, _when=when, _made=made, **k):
                        # The job's own hook, between the hand-off's check and its record's write, or after it.
                        if a[1] == "advance" and not _made and _when == "before":
                            _made.append(threads.ensure(_job)["thread"])
                        entry = real(*a, **k)
                        if entry is not None and not _made and _when == "after":
                            _made.append(threads.ensure(_job)["thread"])
                        return entry
                    with mock.patch.object(threads, "begin", side_effect=begin):
                        self.reconcile()
                    self.reconcile()
                    self.assertTrue(made)
                    if when == "after":
                        self.assertEqual(made[0], tid, "the hook's ensure answers the thread that took the job")
                    else:
                        self.assertNotEqual(made[0], tid)
                        self.assertIsNone(threads.get(made[0]), "a record made first is absorbed")
                    self.assertEqual(threads.thread_of(job)["thread"], tid)
                    self.assertEqual(threads.get(tid)["sessions"], [old, job])
                    self.assertEqual(self.human_files(), [] if seat else [tid + ".json"], "one record")
                    self.assert_finished(tid, (old, job))
                    with self.elsewhere() as p:
                        rows = [m for m in sminos.view_of(p).members if m.session in (old, job)]
                        self.assertEqual([(m.session, m.thread) for m in rows], [(job, tid)])

    def test_a_record_for_a_session_a_seat_holds_is_the_seats_whatever_was_read_before_the_lock(self):
        sid, _ = self.session()
        code, out = self.cli("seat", "add", "g", "worker", "--session", sid)
        self.assertEqual(code, 0, out)
        with mock.patch.object(threads, "thread_of", return_value=None):   # read before the seat took it
            got = threads.ensure(sid)
        self.assertEqual((got["opened"], got["thread"]), ("spawned", sid))
        self.assertEqual(self.human_files(), [], "no record of its own beside the seat")

    def test_a_session_another_seat_holds_takes_no_seat_by_a_new_seat_or_a_repoint(self):
        old, seat_a = self.seated()
        new, _, _ = self.refill(seat_a)
        self.assertNotEqual(new, seat_a, "its id is no seat's id")
        code, out = self.cli("seat", "add", "g", "second", "--session", new)
        self.assertEqual(code, 4, out)
        self.assertIn("takes no seat", out)
        self.assertFalse(os.path.exists(sminos.meta_path(new)), "no seat B")
        code, out = self.cli("seat", "add", "g", "third")
        self.assertEqual(code, 0, out)
        third = next(s for s in sminos.seats() if s["alias"] == "third")
        code, out = self.cli("seat", "add", "g", "third", "--session", new)
        self.assertEqual(code, 4, out)
        self.assertEqual(sminos.load_seat(sminos.meta_path(third["seat_id"]))["current"], "", "not repointed")
        self.assertEqual([s["seat_id"] for s in sminos.seats() if s["current"] == new], [seat_a])

    def test_a_plain_repoint_claims_the_session_as_every_claim_does(self):
        old, seat_a = self.seated()
        new, _, _ = self.refill(seat_a)
        code, out = self.cli("seat", "add", "g", "third")
        self.assertEqual(code, 0, out)
        third = next(s for s in sminos.seats() if s["alias"] == "third")["seat_id"]
        with open(sminos.meta_path(third), "rb") as f:
            before = f.read()
        with mock.patch.object(sminos, "seat_project", return_value=None):   # its project not read here: no journal
            code, out = self.cli("seat", "add", "g", "third", "--session", new)
        self.assertEqual(code, 4, out)
        self.assertIn("takes no seat", out)
        with open(sminos.meta_path(third), "rb") as f:
            self.assertEqual(f.read(), before, "nothing written")
        self.assertEqual([s["seat_id"] for s in sminos.seats() if s["current"] == new], [seat_a])

    def test_seat_add_and_an_adoption_meanwhile_never_both_take_the_session(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                self.fresh()
                if existing:
                    old, seat_id = self.seated()
                sid, _ = self.session()
                real = sminos.agent_row

                def adopt_meanwhile(*a, _sid=sid, **k):
                    # A reconciliation's adoption, after seat add read the session as no human-opened thread's.
                    if not self.human_files():
                        threads.ensure(_sid)
                    return real(*a, **k)
                with mock.patch.object(sminos, "agent_row", side_effect=adopt_meanwhile):
                    code, out = self.cli("seat", "add", "g", "worker", "--session", sid)
                self.assertEqual(code, 4, out)
                self.assertIn("takes no seat", out)
                mine = threads.thread_of(sid)
                self.assertEqual((mine["opened"], mine["sessions"]), ("human", [sid]), "its history as it was")
                held = [s for s in sminos.seats() if s["current"] == sid]
                self.assertEqual(held, [], "no seat holds it")
                if existing:
                    self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["current"], old)


    def test_a_local_read_spanning_a_hand_off_shows_one_row(self):
        old, oproc, tid = self.member()
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        real = sminos._store_whole

        def torn(project, store, **k):
            # The old session's file read before its retirement was appended, the job's after its joined.
            sig, events = real(project, store, **k)
            return sig, [e for e in events if not (e.get("session") == old and e["kind"] == "retired")]
        sminos.forget_caches()
        with mock.patch.object(sminos, "_store_whole", side_effect=torn):
            rows = [m for m in sminos.view_of(self.p).members if m.thread == tid]
        sminos.forget_caches()
        self.assertEqual([(m.session, m.thread_sessions) for m in rows], [(job, (old,))])


class LateHandOff(Sessions):
    """The engine's hand-off record written after the job's first join: the
    job has a record of its own by then, which the thread absorbs."""

    def late(self, seat=False):
        if seat:
            old, seat_id = self.seated(alias="keeper")
            _, oproc = self.session(sid=old)
            tid = seat_id
        else:
            old, oproc, tid = self.member(name="tardy")
        job = str(uuidlib.uuid4())
        self.session(kind="bg", sid=job, name="tardyjob")
        self.reconcile()
        mine = threads.thread_of(job)
        self.assertEqual((mine["opened"], mine["sessions"]), ("human", [job]), "a member of its own first")
        self.handoff_transcript(old, job)
        self.end(oproc)
        return old, job, tid, mine["thread"]

    def assert_absorbed(self, old, job, tid, theirs):
        t = threads.get(tid)
        self.assertEqual((t["current"], t["sessions"]), (job, [old, job]))
        self.assertIsNone(threads.get(theirs), "the job's own record is gone")
        self.assertEqual(threads.in_effect(self.own(job))["thread"], tid)
        self.assertEqual(threads.in_effect(self.own(old))["to"], job)
        self.assertEqual(reach_of(job), reach_of(old), "its owners its predecessor's, by the continuation")
        self.assertEqual(len([m for m in sminos.view_of(self.p).members if m.session in (old, job)]), 1)
        with self.elsewhere() as p:
            rows = [m for m in sminos.view_of(p).members if m.session in (old, job)]
            self.assertEqual([(m.session, m.thread) for m in rows], [(job, tid)], "one thread from the log alone")

    def test_a_human_opened_predecessor_absorbs_the_jobs_record(self):
        old, job, tid, theirs = self.late()
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        self.assert_finished(tid, (old, job))

    def test_a_seat_absorbs_the_jobs_record(self):
        old, job, tid, theirs = self.late(seat=True)
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        self.assertEqual(sminos.load_seat(sminos.meta_path(tid))["current"], job)
        self.assert_finished(tid, (old, job))

    def test_an_absorption_cut_at_each_step_is_finished_the_same_and_the_jobs_record_stays_until_the_last(self):
        for cut in ("begin", "retirement", "delete", "clear"):
            with self.subTest(cut=cut):
                self.fresh()
                old, job, tid, theirs = self.late()
                if cut == "begin":
                    killer = self.kill_after_begin()
                elif cut == "retirement":
                    killer = self.kill_before_event("joined", job)
                else:
                    killer = self.kill_at_change(cut)
                with killer, self.assertRaises(Killed):
                    self.reconcile()
                self.assertEqual(threads.get(tid)["pending"]["op"], "absorb")
                if cut != "clear":
                    self.assertIsNotNone(threads.get(theirs), "the job's record is there until the entry's last step")
                self.reconcile()
                self.assert_absorbed(old, job, tid, theirs)
                self.assert_finished(tid, (old, job))


    def test_an_absorption_whose_guards_fail_records_no_hand_off_and_carries_nothing(self):
        for why in ("ended", "another"):
            with self.subTest(why=why):
                self.fresh()
                old, oproc, tid = self.member(name="tardy")
                job = str(uuidlib.uuid4())
                _, jproc = self.session(kind="bg", sid=job, name="tardyjob")
                self.reconcile()
                theirs = threads.thread_of(job)["thread"]
                if why == "ended":
                    self.end(jproc)
                    self.reconcile()
                    self.assertTrue(threads.record_ended(threads.get(theirs)))
                else:
                    path = os.path.join(threads.store_dir(), theirs + ".json")
                    with open(path) as f:
                        rec = json.load(f)
                    rec["sessions"] = [str(uuidlib.uuid4()), job]
                    with open(path, "w") as f:
                        json.dump(rec, f)
                    sminos.forget_caches()
                    threads._FILES.clear()
                self.handoff_transcript(old, job)
                self.end(oproc)
                self.reconcile()
                self.assertFalse([e for e in self.own(old) if e.get("reason") == "continued"], "no continued")
                self.assertNotEqual(reach_of(job), reach_of(old), "no owner, access or share of the old session")
                self.assertEqual(records.read(job)["owners"], ["@machine"])
                self.assertNotEqual(threads.thread_of(job)["thread"], tid, "two threads")
                self.assertEqual(threads.get(tid)["current"], old)
                with open(os.path.join(sminos.root(), "daemon.log")) as f:
                    said = [line for line in f if "cannot be absorbed" in line]
                self.assertEqual(len(said), 1, "daemon.log says so once")
                self.reconcile()
                with open(os.path.join(sminos.root(), "daemon.log")) as f:
                    self.assertEqual(len([line for line in f if "cannot be absorbed" in line]), 1)


    def test_a_jobs_record_that_changes_between_the_check_and_the_hold_is_never_deleted(self):
        for change in ("entry", "another"):
            with self.subTest(change=change):
                self.fresh()
                old, job, tid, theirs = self.late()
                stranger = str(uuidlib.uuid4())

                def meanwhile(entry, change=change, theirs=theirs, stranger=stranger):
                    if change == "entry":   # an operation of its own begun, in a project not read here
                        self.rewrite(theirs, lambda r: r.update(pending={
                            "id": "e" * 32, "op": "end", "at": sminos.now(), "project": "elsewhere", "events": []}))
                    else:                   # it holds another session by now
                        self.rewrite(theirs, lambda r: r.update(sessions=[stranger, job]))
                with self.after_begin("absorb", meanwhile):
                    self.reconcile()
                self.assertIsNotNone(threads.get(theirs), "the job's record is not deleted")
                self.assertFalse([e for e in self.own(old) if e.get("reason") == "continued"], "nothing appended")
                self.assertNotIn(tid, self.stamps(job))
                if change == "entry":
                    self.assertEqual(threads.get(tid)["pending"]["op"], "absorb", "the absorption waits for it")
                    self.assertEqual(threads.get(theirs)["pending"]["id"], "e" * 32, "its own entry, untouched")
                    self.assertNotEqual(reach_of(job), reach_of(old), "nothing carried while it waits")
                    self.rewrite(theirs, lambda r: r.pop("pending"))   # that operation finished, changing nothing
                    self.reconcile()
                    self.assert_absorbed(old, job, tid, theirs)
                    self.assert_finished(tid, (old, job))
                    continue
                t = threads.get(tid)
                self.assertEqual((t["current"], t["sessions"], t.get("pending")), (old, [old], None),
                                 "the advance undone: two threads")
                self.assertEqual(threads.get(theirs)["sessions"], [stranger, job])
                self.assertNotEqual(reach_of(job), reach_of(old), "nothing of the old session's reach")
                with open(os.path.join(sminos.root(), "daemon.log")) as f:
                    self.assertEqual(len([line for line in f if "cannot be absorbed" in line]), 1)

    def two_finishers(self, tid, pause, meanwhile=lambda: None):
        """A finisher paused where `pause(name)` says, a second one started
        meanwhile; whether the second finished while the first was paused."""
        gate, paused, first = threading.Event(), threading.Event(), []

        def stop_here():
            if threading.current_thread() in first:
                paused.set()
                self.assertTrue(gate.wait(10))

        def run():
            with contextlib.redirect_stderr(io.StringIO()):
                sminos.finish_thread(tid, project=self.p)
        with pause(stop_here):
            a = threading.Thread(target=run)
            first.append(a)
            a.start()
            self.assertTrue(paused.wait(10))
            meanwhile()
            b = threading.Thread(target=run)
            b.start()
            b.join(0.5)
            raced = not b.is_alive()
            gate.set()
            a.join(10)
            b.join(10)
        sminos.forget_caches()
        return raced

    def test_a_second_finisher_waits_and_acts_only_for_the_entry_still_open(self):
        for cut in ("hold", "clear"):
            with self.subTest(cut=cut):
                self.fresh()
                old, job, tid, theirs = self.late()
                with self.kill_after_begin(), self.assertRaises(Killed):
                    self.reconcile()
                ended = {"at": sminos.now(), "reason": "ended", "by": "", "pid": None}

                def pause(stop):
                    if cut == "hold":
                        real = threads._hold

                        def hold(*a, **k):
                            stop()
                            return real(*a, **k)
                        return mock.patch.object(threads, "_hold", side_effect=hold)
                    real_change = threads._change

                    def change(tid_, mutate, *a, **k):
                        if mutate.__name__ == "clear":
                            stop()
                        return real_change(tid_, mutate, *a, **k)
                    return mock.patch.object(threads, "_change", side_effect=change)

                def meanwhile():
                    if cut == "hold":   # the job's record ends: a finisher holding now loses it and undoes
                        self.rewrite(theirs, lambda r: r.update(ended=ended))
                raced = self.two_finishers(tid, pause, meanwhile)
                self.assertFalse(raced, "the second finisher waits for the first")
                t = threads.get(tid)
                continued = [e for e in self.own(old) if e.get("reason") == "continued"]
                self.assertIsNone(t.get("pending"))
                if t["current"] == job:
                    self.assertEqual(len(continued), 1)
                    self.assertIsNone(threads.get(theirs))
                else:   # undone: nothing appended or carried under the cancelled entry
                    self.assertEqual((cut, t["sessions"], continued), ("hold", [old], []))
                    self.assertNotEqual(reach_of(job), reach_of(old))
                    self.assertIsNotNone(threads.get(theirs))
                    continue
                self.assert_finished(tid, (old, job))

    def test_a_reservation_is_an_open_entry_to_every_writer_and_one_left_by_a_dead_absorption_is_released(self):
        old, job, tid, theirs = self.late()
        with self.kill_before_event("retired", old), self.assertRaises(Killed):
            self.reconcile()
        held = threads.get(theirs)["pending"]
        self.assertEqual((held["op"], held["by"], held["id"]), (threads.RESERVED, tid, threads.get(tid)["pending"]["id"]))
        self.assertFalse(threads.update(theirs, {"channels": ["c"]}), "update() leaves a held record alone")
        self.assertIsNone(threads.begin(theirs, "end", self.p, []), "no operation starts on it")
        self.assertEqual(threads.thread_of(job)["thread"], tid, "the lookup answers the absorbing thread")
        self.assertTrue(sminos.entry_open(job), "the hook reads it as an open entry")
        # A mark whose absorption is gone (its entry cleared some other way) is released, nothing else changed.
        self.rewrite(theirs, lambda r: r["pending"].update(id="f" * 32))
        self.reconcile()
        self.reconcile()   # the absorption waits on a mark not its own until that mark is released
        self.assert_absorbed(old, job, tid, theirs)

    def test_what_the_jobs_own_record_named_and_published_before_its_absorption_is_not_the_threads(self):
        old, job, tid, theirs = self.late()
        sminos.lifecycle(self.p, job, "renamed", alias="tardyjob2", name_source="user")
        sminos.lifecycle(self.p, job, "state", state="blocked", machine=sminos.host_name())
        sminos.lifecycle(self.p, job, "titled", title="a title of its own")
        self.assertEqual(self.stamps(job), {theirs})
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        with self.elsewhere() as p:
            [m] = [m for m in sminos.view_of(p).members if m.session == job]
            self.assertEqual((m.alias, m.thread), ("tardy", tid), "the thread's name, not its own record's")
            self.assertNotEqual(m.state, "blocked", "nor what it published as that record")
            self.assertNotEqual(m.title, "a title of its own")


class Refill(Sessions):
    def test_a_refill_keeps_the_thread_and_takes_its_reach_from_its_own_launch(self):
        old, seat_id = self.seated()
        new, _, out = self.refill(seat_id)
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["current"], seat["sessions"], seat.get("pending")), (new, [old, new], None), out)
        last = threads.in_effect(self.own(old))
        self.assertEqual((last["reason"], last["thread"], "to" in last), ("replaced", seat_id, False))
        self.assertEqual(threads.in_effect(self.own(new))["thread"], seat_id)
        self.assertEqual(records.read(new)["owners"], ["@machine"], "its own launch's, never its predecessor's")
        self.assertNotEqual(reach_of(new), reach_of(old))
        [row] = [m for m in sminos.view_of(self.p).members if m.session == new]
        self.assertEqual((row.alias, row.thread, row.charge), ("worker", seat_id, "keeps the seat"))
        self.assertEqual(row.thread_sessions, (old,))
        self.assertEqual(row.former, ())
        with self.elsewhere() as p:
            [there] = [m for m in sminos.view_of(p).members if m.session == new]
            self.assertEqual((there.alias, there.thread, there.charge), ("worker", seat_id, "keeps the seat"))
            self.assertNotIn("m-ann", there.owners, "read on another machine's copy of the log too")

    def test_a_refill_killed_at_each_write_is_finished_by_the_next_reconciliation(self):
        for cut in ("launch", "poll", "joined"):
            with self.subTest(cut=cut):
                self.fresh()
                old, seat_id = self.seated()
                killer = {"launch": self.kill_after_begin(1), "poll": self.kill_after_begin(2),
                          "joined": self.kill_before_event("joined", None)}[cut]
                with killer, self.assertRaises(Killed):
                    self.refill(seat_id)
                entry = threads.get(seat_id)["pending"]
                self.assertEqual(entry["op"], "advance")
                if cut == "launch":
                    self.assertEqual(entry["events"][0]["reason"], "replaced",
                                     "the write that detached the old session owes its retirement")
                else:
                    self.assertEqual(threads.in_effect(self.own(old))["reason"], "replaced")
                self.reconcile()
                seat = sminos.load_seat(sminos.meta_path(seat_id))
                last = threads.in_effect(self.own(old))
                self.assertEqual((last["reason"], last["thread"], "to" in last), ("replaced", seat_id, False))
                self.assertEqual(len([e for e in self.own(old) if e.get("reason") == "replaced"]), 1)
                if cut == "launch":
                    self.assertEqual((seat["current"], seat["sessions"]), ("", [old]),
                                     "as its launch left it: the new session is the poll's to name")
                    self.assert_finished(seat_id, (old,))
                    continue
                new = seat["current"]
                self.assertEqual(seat["sessions"], [old, new])
                self.assertEqual(threads.in_effect(self.own(new))["thread"], seat_id)
                self.assertIn("--permission-mode", threads.get(seat_id)["launch"].get("options") or [],
                              "the new launch's options, in the advance's own write")
                self.assert_finished(seat_id, (old, new))

    def failing_retirement(self, failing=None):
        """Appends of a `retired` fail (a full disk, a lock) while `failing`
        (a list, default always) is non-empty: the launch's entry stays open."""
        real, failing = sminos._append, [True] if failing is None else failing

        def append(project, writer, events, **k):
            if failing and any(e.get("kind") == "retired" for e in events):
                raise OSError("no space left")
            return real(project, writer, events, **k)
        return mock.patch.object(sminos, "_append", side_effect=append)

    def legacy_seat(self):
        """A seat from before threads holding a session whose latest joined is unstamped and names the seat."""
        old = str(uuidlib.uuid4())
        seat_id = old
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": old, "short": old[:8], "name": "worker",
                                  "alias": "worker", "group": "g", "cwd": self.root, "worktree": "", "role": "",
                                  "brief": "", "status": "idle", "history": [], "attempts": 1})
        self.write_own(old, [self.old_joined(old, alias="worker", seat=seat_id, name_source="seat")])
        return old, seat_id

    def test_a_poll_behind_a_launch_entry_that_cannot_finish_waits_in_it_and_is_not_lost(self):
        for retired in (False, True, "legacy"):
            with self.subTest(retired=retired):
                self.fresh()
                old, seat_id = self.legacy_seat() if retired == "legacy" else self.seated()
                if retired is True:
                    code, out = self.cli("retire", "g/worker")
                    self.assertEqual(code, 0, out)
                    self.assertIn("ended", sminos.load_seat(sminos.meta_path(seat_id)))
                with self.failing_retirement():
                    new, _, out = self.refill(seat_id)
                    raw = sminos.load_seat(sminos.meta_path(seat_id))
                    self.assertNotIn("ended", raw, "the launch's write lifts the end")
                    entry = raw["pending"]
                    self.assertEqual(entry["events"][0]["reason"], "replaced")
                    self.assertEqual(entry["next"]["fields"]["current"], new, "the poll's advance waits in it")
                    self.assertIn("--permission-mode", entry["next"]["fields"]["launch"]["options"])
                    self.assertIn("waits behind the displaced session's retirement", out)
                    # A read meanwhile: the seat vacant by its record; the old session a member still, by the
                    # log, unless it was retired before.
                    view = sminos.view_of(self.p)
                    rows = [m.session for m in view.members + view.rows
                            if m.thread == seat_id or (m.session and m.session == old)
                            or (m.seat or {}).get("seat_id") == seat_id]
                    self.assertEqual(rows, [""] if retired is True else [old], "one row of the thread")
                    if retired == "legacy":
                        [m] = [m for m in view.members if m.session == old]
                        self.assertEqual(m.thread, "", "the legacy joined names no thread: X7 reads no stamp there")
                self.reconcile()
                seat = sminos.load_seat(sminos.meta_path(seat_id))
                self.assertEqual((seat["current"], seat["sessions"], seat.get("pending")), (new, [old, new], None))
                self.assertIn("--permission-mode", threads.get(seat_id)["launch"]["options"])
                self.assertEqual(threads.in_effect(self.own(old))["reason"], "replaced")
                self.assertEqual(threads.in_effect(self.own(new))["thread"], seat_id)
                self.assert_finished(seat_id, (old, new))

    def test_a_poll_whose_launch_entry_finished_meanwhile_begins_its_advance_itself(self):
        old, seat_id = self.seated()
        failing, real = [True], threads.follow

        def follow(*a, **k):
            # A replay finishes the launch's entry between the poll's refused begin and its queueing.
            failing.clear()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertTrue(sminos.finish_thread(seat_id))
            got = real(*a, **k)
            self.assertFalse(got, "the entry it would queue behind is gone")
            return got
        with self.failing_retirement(failing), mock.patch.object(threads, "follow", side_effect=follow):
            new, _, out = self.refill(seat_id)
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["current"], seat["sessions"], seat.get("pending")), (new, [old, new], None), out)
        self.assertNotIn("waits behind", out)
        self.assertEqual(threads.in_effect(self.own(new))["thread"], seat_id)
        self.assert_finished(seat_id, (old, new))

    def test_a_queued_advance_and_a_replay_are_one_at_a_time_in_either_order(self):
        for first in ("follow", "replay"):
            with self.subTest(first=first):
                self.fresh()
                old, seat_id = self.seated()
                with self.kill_after_begin(1), self.assertRaises(Killed):
                    self.refill(seat_id)
                entry = threads.get(seat_id)["pending"]
                later = str(uuidlib.uuid4())
                joined = {"kind": "joined", "session": later, **sminos.joined_fields(
                    "worker", "seat", self.root, "", "", seat_id, "", "seat", session=later)}

                def queue():
                    return threads.follow(seat_id, entry["id"], "advance", self.p, [joined],
                                          fields={"current": later})
                if first == "follow":
                    self.assertTrue(queue())
                    self.reconcile()
                    self.assertEqual(threads.get(seat_id)["current"], later, "begun by the write that cleared it")
                    self.assertEqual(threads.in_effect(self.own(later))["thread"], seat_id)
                    continue
                gate, paused, got = threading.Event(), threading.Event(), []
                real_change = threads._change

                def change(tid_, mutate, *a, **k):
                    if mutate.__name__ == "clear" and threading.current_thread() is not main:
                        paused.set()
                        self.assertTrue(gate.wait(10))
                    return real_change(tid_, mutate, *a, **k)
                main = threading.current_thread()
                with mock.patch.object(threads, "_change", side_effect=change):
                    a = threading.Thread(target=lambda: sminos.finish_thread(seat_id, project=self.p))
                    a.start()
                    self.assertTrue(paused.wait(10))
                    b = threading.Thread(target=lambda: got.append(queue()))
                    b.start()
                    b.join(0.5)
                    self.assertTrue(b.is_alive(), "the queueing waits for the finisher")
                    gate.set()
                    a.join(10)
                    b.join(10)
                sminos.forget_caches()
                self.assertEqual(got, [False], "the entry it read is gone: its caller begins its own advance")
                self.assertIsNone(threads.get(seat_id).get("pending"), "nothing queued into a cleared entry")

    def fill(self, seat_id):
        """spawn_fresh onto the seat, its launch stubbed: (exit code or None, whether it launched)."""
        with mock.patch.object(sminos, "run_claude_bg", side_effect=RuntimeError("launched")) as launch, \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                sminos.spawn_fresh(seat_id, "worker", "g", "", "", "a task", self.root, "", "", "", "", False, [],
                                   "spawned")
                code = None
            except SystemExit as e:
                code = e.code
            except RuntimeError:
                code = None
        return code, launch.called

    def test_a_fill_over_an_operation_of_the_seat_that_cannot_be_finished_launches_nothing(self):
        for log in ("blocked", "recovered"):
            with self.subTest(log=log):
                self.fresh()
                old, seat_id = self.seated()
                with mock.patch.object(sminos, "_append", side_effect=OSError("disk full")):
                    code, out = self.cli("retire", "--purge", "g/worker")
                    self.assertNotEqual(code, 0, out)
                    entry = threads.get(seat_id)["pending"]
                    self.assertEqual(entry.get("last"), "purge", out)
                    if log == "blocked":
                        code, launched = self.fill(seat_id)
                if log == "recovered":   # the fill's own preflight finishes the purge: no seat is left to fill
                    code, launched = self.fill(seat_id)
                    self.assertEqual((code, launched), (sminos.EXIT_UNKNOWN, False))
                    self.assertFalse(os.path.exists(sminos.meta_path(seat_id)), "no file recreated")
                    self.assertEqual(list(sminos.record_files()), [])
                    continue
                self.assertEqual((code, launched), (sminos.EXIT_UNKNOWN, False))
                self.assertEqual(threads.get(seat_id)["pending"]["id"], entry["id"], "the purge's entry, untouched")
                self.assertNotIn("next", threads.get(seat_id)["pending"])
                self.reconcile()
                self.assertFalse(os.path.exists(sminos.meta_path(seat_id)), "the purge, finished by the replay")

    def test_a_launch_entry_finished_by_another_process_is_this_launchs_all_the_same(self):
        for when in ("launch", "poll"):
            with self.subTest(when=when):
                self.fresh()
                old, seat_id = self.seated()
                failing, real = [True], threads.begin
                done = []

                def begin(thread_id, op, project, events, **k):
                    entry = real(thread_id, op, project, events, **k)
                    poll = any(e["kind"] == "joined" for e in events)
                    if done:
                        return entry
                    if when == "launch" and entry is not None and not poll:
                        # A concurrent finisher completes the launch's entry before this process finishes it.
                        done.append(1)
                        failing.clear()
                        with contextlib.redirect_stderr(io.StringIO()):
                            self.assertTrue(sminos.finish_thread(seat_id))
                    if when == "poll" and entry is None and poll:
                        # A replay clears the launch's entry right after the poll's refused begin.
                        done.append(1)
                        failing.clear()
                        with contextlib.redirect_stderr(io.StringIO()):
                            self.assertTrue(sminos.finish_thread(seat_id))
                    return entry
                with self.failing_retirement(failing), mock.patch.object(threads, "begin", side_effect=begin):
                    new, _, out = self.refill(seat_id)
                self.assertTrue(done)
                seat = sminos.load_seat(sminos.meta_path(seat_id))
                self.assertEqual((seat["current"], seat["sessions"], seat.get("pending")), (new, [old, new], None),
                                 out)
                self.assertEqual(len([e for e in self.own(old) if e.get("reason") == "replaced"]), 1, "once")
                self.assertEqual(threads.in_effect(self.own(new))["thread"], seat_id)
                self.assert_finished(seat_id, (old, new))

    def test_a_queue_drained_across_projects_appends_into_each_projects_own_view(self):
        old, seat_id = self.seated()
        other = self.project_of(self.repo("other"))
        with self.failing_retirement():
            new, _, out = self.refill(seat_id, cwd=other.root)
        self.assertIn("next", threads.get(seat_id)["pending"], out)
        sminos.forget_caches()
        here = sminos.view_of(self.p)   # this invocation drains the queue: `replaced` here, `joined` there
        self.assertIsNone(threads.get(seat_id).get("pending"))
        self.assertNotIn(new, here.info, "the other project's joined is not this view's")
        self.assertFalse([m for m in here.members if m.session == new])
        there = sminos.view_of(other)
        self.assertEqual([m.thread for m in there.members if m.session == new], [seat_id])
        self.assertEqual(threads.in_effect([e for e in here.events if e.get("session") == old])["reason"],
                         "replaced")

    def test_a_refill_into_another_project_owes_the_displaced_sessions_retirement_in_its_own(self):
        for cut in (None, "launch"):
            with self.subTest(cut=cut):
                self.fresh()
                other = self.project_of(self.repo("other"))
                old, seat_id = self.seated()
                if cut:
                    with self.kill_after_begin(1), self.assertRaises(Killed):
                        self.refill(seat_id, cwd=other.root)
                    self.assertEqual(threads.get(seat_id)["pending"]["project"], self.p.id)
                    self.reconcile()
                else:
                    new, _, out = self.refill(seat_id, cwd=other.root)
                    self.assertEqual(threads.in_effect(self.own(new, other))["thread"], seat_id, out)
                    # Names resolve within one project (§4): there, by its thread id and its current session.
                    for name in (seat_id, new, new[:8]):
                        self.assertEqual(self.reached(other, name), new, name)
                        self.assertEqual(self.target(name), new, name)
                last = threads.in_effect(self.own(old))
                self.assertEqual((last["reason"], last["thread"]), ("replaced", seat_id))
                self.assertTrue(last.get("op"), "owed by the launch's entry, in the old session's own project")
                self.assertFalse(self.own(old, other), "nothing of it in the project the seat moved to")
                self.assertIsNone(threads.get(seat_id).get("pending"))

    def test_a_former_occupant_withdrawn_from_this_reader_lends_the_later_one_nothing(self):
        old, seat_id = self.seated()
        new, _, _ = self.refill(seat_id)

        def withdraw(p):
            # The hub's notice of a change that withdrew this reader from the old session (P5 O18 D6).
            path = next(os.path.join(p.home, "log", n) for n in os.listdir(os.path.join(p.home, "log"))
                        if n.endswith(".jsonl") and old in n and "~" not in n)
            with open(path) as f:
                last = [json.loads(line) for line in f][-1]
            with open(path, "a") as f:
                f.write(json.dumps({"ts": sminos.now(ms=True), "writer": last["writer"], "seq": last["seq"] + 1,
                                    "kind": "unlisted", "session": old, "policyRev": 2}) + "\n")
        with self.elsewhere() as p:
            [m] = [m for m in sminos.view_of(p).members if m.session == new]
            self.assertEqual((m.thread_sessions, m.charge), ((old,), "keeps the seat"), "the control")
        with self.elsewhere(withdraw) as p:
            self.assertFalse([m for m in sminos.view_of(p).members if m.session == old])
            [m] = [m for m in sminos.view_of(p).members if m.session == new]
            self.assertEqual((m.alias, m.thread), ("worker", seat_id))
            self.assertEqual(m.thread_sessions, (), "the withdrawn session is no part of its history here")
            self.assertNotEqual(m.charge, "keeps the seat", "nor is its in-charge line")

    def test_seat_add_over_a_held_seat_is_a_refill_too(self):
        old, seat_id = self.seated()
        new, _ = self.session()
        code, out = self.cli("seat", "add", "g", "worker", "--session", new)
        self.assertEqual(code, 0, out)
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["current"], seat["sessions"]), (new, [old, new]))
        last = threads.in_effect(self.own(old))
        self.assertEqual((last["reason"], last["thread"], "to" in last), ("replaced", seat_id, False))
        self.assertEqual(threads.in_effect(self.own(new))["thread"], seat_id)
        self.assertNotEqual(reach_of(new), reach_of(old))


class Naming(Sessions):
    """The thread id, and each session id it has had, as `@short`,
    `@alias#short` and a full id: the current session, here and from a
    registry that holds only the log."""

    def names(self, alias, ids):
        out = []
        for sid in ids:
            out += [sid, sid[:8], "%s#%s" % (alias, sid[:8])]
        return out

    def assert_reached(self, alias, ids, current, who=True, edit=None, here=True):
        for p_here in (True, False) if here else (False,):
            ctx = contextlib.nullcontext(self.p) if p_here else self.elsewhere(edit)
            with ctx as p:
                for name in self.names(alias, ids):
                    with self.subTest(name=name, here=p_here):
                        self.assertEqual(self.reached(p, name), current, "say")
                        self.assertEqual(self.target(name), current, "send")
                if who:
                    for sid in ids:
                        hits = [(m.session, how) for _, m, how in sminos.who_matches(sid[:8])]
                        self.assertIn(current, [s for s, _ in hits], "who %s" % sid[:8])
                        self.assertEqual(len(hits), 1, hits)

    def test_after_a_hand_off_the_thread_id_and_each_former_session_id_reach_the_current_session(self):
        old, oproc, tid = self.member()
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.assert_reached("handy", (tid, old, job), job)

    def test_after_a_refill_the_thread_id_and_each_former_session_id_reach_the_current_session(self):
        old, seat_id = self.seated()
        new, _, _ = self.refill(seat_id)
        self.assert_reached("worker", (seat_id, old, new), new)

    def test_a_refill_whose_new_joined_arrived_before_the_old_retirement_names_the_current_session_alone(self):
        old, seat_id = self.seated()
        new, _, _ = self.refill(seat_id)

        def not_yet(p):
            # What has reached the other machine: the new session's joined, not yet the old one's `replaced`.
            for n in os.listdir(os.path.join(p.home, "log")):
                path = os.path.join(p.home, "log", n)
                if not n.endswith(".jsonl"):
                    continue
                with open(path) as f:
                    kept = [line for line in f if json.loads(line).get("reason") != "replaced"]
                with open(path, "w") as f:
                    f.writelines(kept)
        with self.elsewhere(not_yet) as p:
            self.assertEqual(sminos.view_of(p).info[old]["latest"]["kind"], "joined", "both joined, in this log")
            rows = [(m.session, m.thread_sessions) for m in sminos.view_of(p).members if m.thread == seat_id]
            self.assertEqual(rows, [(new, (old,))], "one row: the latest joined, the other its thread's")
        self.assert_reached("worker", (seat_id, old, new), new, edit=not_yet, here=False)

    def test_who_names_the_session_a_commit_line_named_as_the_one_it_went_on_as(self):
        old, seat_id = self.seated()
        new, _, _ = self.refill(seat_id)
        line = "Sminos-Session: worker#%s (work on testhost)" % old[:8]
        subprocess.run(["git", "-C", self.root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "--allow-empty", "-m", "a change\n\n" + line], check=True)
        with self.elsewhere():
            code, out = self.cli("who", "HEAD")
        self.assertEqual(code, 0, out)
        self.assertIn("went on as worker#%s" % new[:8], out)

    def test_an_adopted_member_and_an_adopted_refilled_seat_are_named_by_a_session_with_no_stamped_event(self):
        older = str(uuidlib.uuid4())
        sid, _ = self.session()
        self.write_own(older, [self.old_joined(older), {"kind": "retired", "by": "", "reason": "continued",
                                                        "to": sid}])
        self.write_own(sid, [self.old_joined(sid)])
        first, current = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        self.session(sid=current)
        seat_id = first   # a seat's id is its first session's
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": current, "alias": "worker", "group": "g",
                                  "cwd": self.root, "status": "idle",
                                  "history": [{"current": first, "short": first[:8], "status": "idle"}]})
        self.write_own(first, [self.old_joined(first, alias="worker", seat=seat_id, name_source="seat"),
                               {"kind": "retired", "by": "", "reason": "replaced"}])
        self.write_own(current, [self.old_joined(current, alias="worker", seat=seat_id, name_source="seat")])
        self.reconcile()
        self.assertFalse(threads.stamped(self.own(older)[0]))
        for p_here in (True, False):
            with (contextlib.nullcontext(self.p) if p_here else self.elsewhere()) as p:
                with self.subTest(here=p_here):
                    self.assertEqual(self.reached(p, older[:8]), sid)
                    self.assertEqual(self.reached(p, first[:8]), current)
                    self.assertEqual(self.reached(p, "worker#" + first[:8]), current)


class FormerRunsAgain(Sessions):
    """A former session of a thread that runs again is a thread of its own,
    and nothing it writes then changes what the first thread shows."""

    def shown(self, p, sid):
        m = next(m for m in sminos.view_of(p).members if m.session == sid)
        return (m.alias, m.charge, m.thread, tuple(a for a, _ in m.former_aliases))

    def check(self, again, went_on, tid, shown):
        mine = threads.thread_of(again)
        self.assertNotEqual(mine["thread"], tid)
        self.assertEqual((mine["opened"], mine["sessions"]), ("human", [again]))
        self.assertEqual(threads.get(tid)["current"], went_on)
        sminos.lifecycle(self.p, again, "renamed", alias="second-life", name_source="user")
        sminos.lifecycle(self.p, again, "in-charge", text="a new line of its own", source="set")
        sminos.forget_caches()
        self.assertEqual(self.shown(self.p, went_on), shown, "nothing the first thread shows changes")
        for name in (again, again[:8]):
            self.assertEqual(self.target(name), again, "send: its id names it, here too")
        self.assertEqual([m.session for _, m, _ in sminos.who_matches(again[:8])], [again], "and who")
        with self.elsewhere() as p:
            self.assertEqual(self.shown(p, went_on), shown)
            for name in (again, again[:8]):
                self.assertEqual(self.reached(p, name), again, "its id names it, not the thread that went on")
                self.assertEqual(self.target(name), again, "send")
            self.assertEqual(self.reached(p, "second-life"), again)

    def test_a_handed_off_session_resumed_by_id(self):
        old, oproc, tid = self.member()
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        shown = self.shown(self.p, job)
        self.assertEqual(shown[1], "owns the hand-off")
        self.session(sid=old, started=ms_ago(-1))
        self.reconcile()
        self.check(old, job, tid, shown)

    def test_a_replaced_seat_session_resumed_in_a_terminal(self):
        old, seat_id = self.seated()
        new, _, _ = self.refill(seat_id)
        shown = self.shown(self.p, new)
        self.assertEqual(shown[1], "keeps the seat")
        self.session(sid=old, started=ms_ago(-1))
        self.reconcile()
        self.check(old, new, seat_id, shown)


class Hub(Sessions):
    """M2's different-audience fixture: a machine cut over to its endpoint
    (identity.json, the capabilities `access` and `reach`), and `work` one
    of org-1's hub projects, so a private session's own events go under its
    stream (`<writer>~<digest>`), which needs the endpoint's audience at its
    record's policyRev, and fail closed without it."""

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(os.environ["SMINOS_HOME"], "daemon"), mode=0o700)
        os.environ["MAWS_USER_DATA"] = os.path.join(self.home, "m")
        self.addCleanup(os.environ.pop, "MAWS_USER_DATA", None)
        sminos.write_json(sminos.sibling_module("sminos_rl10").identity_path(), {
            "org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": {}, "ref": "machine-ref-1",
            "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z", "build": "b"},
            mode=0o600)
        self.au = sminos.audience_module()
        self.au.keep_capabilities(["access", "reach"])
        code, out = self.cli("project", "init", "--name", "work")
        self.assertEqual(code, 0, out)
        smns = os.path.join(self.root, ".smns")
        with open(smns) as f:
            d = json.load(f)
        d["hub"] = {"url": "http://127.0.0.1:9", "org": "org-1"}
        with open(smns, "w") as f:
            json.dump(d, f)
        self.p = self.project_of(self.root)
        self.assertEqual(sminos.project_kind(self.p), "hub")

    def heard(self, sid):
        """The endpoint's audience for the session at its record's policyRev, as the uplink keeps it."""
        rec = records.read(sid)
        members = list(rec["owners"]) + [x["member"] for x in rec.get("shares") or []]
        self.assertTrue(self.au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(
            sid, rec["owners"], members, rec["policyRev"])}))

    def private(self, sid):
        records.set_policy(sid, lambda a, shares: ("private", shares))
        self.heard(sid)

    def plain(self, sid):
        """The session's events under its plain writer: what a reader of the project's whole log reads."""
        return [e for e in sminos.log_read(self.p) if e["writer"] == sminos.writer_id(sid)]

    def streams(self, sid):
        """{writer: its events} of the session's audience streams, each as a reader admitted to it alone reads it."""
        out = {}
        for e in sminos.log_read(self.p):
            if e["writer"] != sminos.writer_id(sid) and sminos.writer_session(e["writer"]) == sid:
                out.setdefault(e["writer"], []).append(e)
        return out

    def quiet(self):
        return contextlib.redirect_stderr(io.StringIO())


class PrivateHandOff(Hub):
    """A hand-off from a private session: the job's first publication is
    under the predecessor's reach, or there is none yet."""

    def handing(self):
        old, oproc, tid = self.member()
        self.private(old)
        job, _ = self.job(old)
        records.establish(job, records.default_provenance("hook"))   # its own hook's record, the defaults
        self.end(oproc)
        return old, job, tid

    def assert_published_under_its_reach(self, old, job, tid):
        self.assertFalse([e for e in self.plain(job) if e["kind"] == "joined"], "no joined on the plain stream")
        with self.quiet():
            self.reconcile()
        self.assertFalse([e for e in self.plain(job) if e["kind"] == "joined"], "nor once its reach is carried")
        self.assertEqual(reach_of(job), reach_of(old))
        self.assertEqual(threads.get(tid)["pending"]["carry"], [old, job], "open: no audience for the job yet")
        self.heard(job)
        self.reconcile()
        self.assert_finished(tid, (old, job))
        self.assertFalse(self.plain(job), "nothing of the job's under its plain writer")
        [(writer, events)] = self.streams(job).items()
        self.assertEqual(events[0]["kind"], "joined", "its first publication, on its private stream")
        self.assertEqual(events[0]["thread"], tid)

    def test_a_policy_write_that_fails_keeps_the_entry_open_and_publishes_nothing(self):
        old, job, tid = self.handing()
        with mock.patch.object(records, "establish", side_effect=OSError("disk full")), self.quiet():
            self.reconcile()
        self.assertEqual(records.read(job)["owners"], ["@machine"], "the job's record as it was")
        self.assertFalse([e for e in self.plain(job) if e["kind"] == "joined"], "nothing of the job published")
        self.assertFalse([e for e in self.own(old) if e.get("reason") == "continued"])
        entry = threads.get(tid)["pending"]
        self.assertEqual((entry["op"], entry["carry"]), ("advance", [old, job]), "the entry stays open")
        self.assert_published_under_its_reach(old, job, tid)

    def test_the_module_carries_before_it_appends_whoever_finishes(self):
        old, job, tid = self.handing()
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        with self.quiet():
            threads.finish(tid)   # the module's own finish, no step passed in
        self.assertEqual(reach_of(job), reach_of(old), "carried by the module itself")
        self.assertFalse([e for e in self.plain(job) if e["kind"] == "joined"])

    def test_a_cursor_or_override_that_cannot_be_written_keeps_the_entry_open(self):
        for what in ("cursor_save", "write_override"):
            with self.subTest(what=what):
                self.fresh()
                old, oproc, tid = self.member()
                if what == "write_override":
                    sminos.write_override(old, self.p.id)
                job, _ = self.job(old)
                self.end(oproc)
                with mock.patch.object(sminos, what, side_effect=OSError("read-only")), self.quiet():
                    self.reconcile()
                self.assertEqual(threads.get(tid)["pending"]["carry"], [old, job], "open")
                self.assertFalse([e for e in self.own(job) if e["kind"] == "joined" and e.get("thread") == tid])
                self.reconcile()
                self.assert_finished(tid, (old, job))
                self.assertEqual(threads.in_effect(self.own(job))["thread"], tid)

    def test_a_retirement_an_older_copy_wrote_still_carries_the_reach_first(self):
        old, job, tid = self.handing()
        self.write_own(old, [{"kind": "retired", "by": "", "reason": "continued", "to": job}])   # unstamped
        self.assert_published_under_its_reach(old, job, tid)


class ThreadIdNamesNoSession(Hub):
    """A thread's id told to a reader of a later session's stream alone,
    whose reach is not the earlier one's."""

    def test_a_human_opened_threads_stamp_names_no_session_of_it_and_a_refilled_seats_is_its_seat_field(self):
        old, oproc, tid = self.member()
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.assertEqual(threads.get(tid)["sessions"], [old, job])
        self.private(job)   # its reach changes: what follows is for its new audience alone
        sminos.lifecycle(self.p, job, "renamed", alias="handy-later", name_source="user")
        sminos.lifecycle(self.p, job, "in-charge", text="a line for the later audience", source="set")
        [(writer, later)] = self.streams(job).items()
        self.assertEqual([e["kind"] for e in later if e["kind"] != "state"][-2:], ["renamed", "in-charge"])
        self.assertEqual({e.get("thread") for e in later}, {tid})
        self.assertFalse({e.get("thread") for e in later} & {old, job},
                         "a reader of the later stream alone finds no session's id in `thread`")
        seat_old, seat_id = self.seated()
        new, _, _ = self.refill(seat_id)
        self.private(new)
        sminos.lifecycle(self.p, new, "in-charge", text="the refilled seat's own line", source="set")
        joined = [e for e in sminos.log_read(self.p) if e.get("session") == new and e["kind"] == "joined"]
        self.assertTrue(joined)
        for e in joined:
            self.assertEqual(e["thread"], e["seat"], "a refilled seat's `thread` is what `seat` publishes")
        [(writer, later)] = self.streams(new).items()
        self.assertEqual({e.get("thread") for e in later}, {seat_id})


class OtherStarts(Sessions):
    """A /clear, a fork and an in-session /resume start another thread; a
    compaction is the same session (pinned: nothing is built for them)."""

    def continued(self):
        return [e for e in sminos.log_read(self.p) if e.get("reason") == "continued"]

    def test_a_clear_under_a_new_id_in_the_same_process_is_another_thread(self):
        old, proc, tid = self.member()
        new = str(uuidlib.uuid4())
        self.peer_set(proc, sessionId=new)   # the engine's record names the new session after a /clear
        self.hook(new, source="clear", env={"CLAUDE_CODE_SESSION_ID": new, "CLAUDE_PID": str(proc.pid)})
        self.reconcile()
        mine = threads.thread_of(new)
        self.assertNotEqual(mine["thread"], tid)
        self.assertEqual(mine["sessions"], [new])
        self.assertEqual(self.continued(), [])
        self.assertEqual(records.read(new)["owners"], ["@machine"], "nothing carried from the old record")
        self.assertNotEqual(reach_of(new), reach_of(old))
        with self.elsewhere() as p:
            info = sminos._projection(sminos.log_read(p))
            self.assertEqual((sminos.row_thread(info[old]), sminos.row_thread(info[new])), (tid, mine["thread"]))
            self.assertEqual(sminos.lineage(new, info), [], "no link to the session it came from")

    def test_an_in_session_resume_of_another_session_is_another_thread(self):
        target, tproc, ttid = self.member(name="target", charge="")
        self.end(tproc)
        self.reconcile()
        left, proc, ltid = self.member(name="left", charge="", owned=False)
        target_reach = reach_of(target)
        before = {s: list(self.own(s)) for s in (left, target)}
        # The engine's record still names the session left while the target's SessionStart hooks run.
        self.hook(target, source="resume", env={"CLAUDE_CODE_SESSION_ID": target, "CLAUDE_PID": str(proc.pid)})
        self.assertEqual({s: list(self.own(s)) for s in (left, target)}, before,
                         "nothing written for the session left under the target's id, or the reverse")
        self.peer_set(proc, sessionId=target)
        self.reconcile()
        self.assertEqual(threads.in_effect(self.own(target))["kind"], "joined")
        self.assertEqual(threads.in_effect(self.own(target))["thread"], ttid, "the target is its own thread again")
        self.assertNotEqual(ttid, ltid)
        self.assertEqual(self.continued(), [])
        self.assertEqual(reach_of(target), target_reach, "it keeps its own owners")

    def test_a_fork_is_a_thread_of_its_own(self):
        old, proc, tid = self.member()
        fork, fproc = self.session(name="handy")
        self.hook(fork, source="fork", env={"CLAUDE_CODE_SESSION_ID": fork, "CLAUDE_PID": str(fproc.pid)})
        self.reconcile()
        mine = threads.thread_of(fork)
        self.assertNotEqual(mine["thread"], tid)
        self.assertEqual(self.continued(), [])
        self.assertEqual(records.read(fork)["owners"], ["@machine"], "its record owners from its own evidence")

    def test_a_compaction_is_the_same_session_and_thread_and_writes_nothing(self):
        sid, proc, tid = self.member()
        before = list(self.own(sid))
        self.hook(sid, source="compact", env={"CLAUDE_CODE_SESSION_ID": sid, "CLAUDE_PID": str(proc.pid)})
        self.reconcile()
        self.assertEqual(self.own(sid), before)
        self.assertEqual(threads.stamp(sid), tid)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
