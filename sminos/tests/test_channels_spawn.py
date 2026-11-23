#!/usr/bin/env python3
"""`sminos spawn --channel` on the machine it is typed on (EN.G2's M1:
docs/doperpowers/plans/2026-11-23-sminos-environments-en-g2.md, acceptance
2, 4, 5, 6 and 11 for a spawn here; Interfaces §1).

- The statement: a new seat's, the one a thread's own add writes (after its
  `joined`, under its writer, the whole set), with nothing in the channel's
  log; the banner, then a line a channel; two values naming one channel
  counted once; a refill of a stopped seat already in another channel keeps
  both, its statement under the refill's new writer; with --wait the thread
  is placed before the wait begins.
- Refused before anything is launched: a name no log answers, several
  answer, or a project's (exit 4, find_channel's words); 129 channels; a
  channel this enrollment does not carry; a kept welcome that lists no
  `channels`, and one not kept yet, each in its own words.
- After the launch nothing is a refusal: each word a placement can fail
  with is a warning with the command that places it, exit 0, one launch;
  the limit; the machine's enrollment gone to another org meanwhile (one
  warning, no command); a registration made uncarried meanwhile.
- The placement itself (sminos_channels.place_spawned, as a VM runs it): one
  deadline for all of it, a registration's lock another process holds on
  the second channel costing that channel alone (`time`), the first applied.
- Nothing else changed: the merge base's parser and this one agree on every
  spelling of every flag of `spawn` but `--c`; a spawn without --channel
  prints, launches and writes what the merge base's does, but for ids.

Hermetic: test_channels_requests.Requests (test_threads.Machine, cut over to
an endpoint never run, its kept welcome listing `channels`); the launcher is
replaced in-process (run_claude_bg, poll_uuid) or, for the comparison with
the merge base, fake_claude.py on PATH.
Run: python3 -B sminos/tests/test_channels_spawn.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import glob
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_channels_requests import Requests  # noqa: E402
from test_channels_say import extracted  # noqa: E402
from test_channels_store import DESK, HUB, LOBBY, ROOM, channel_ids, sminos, threads  # noqa: E402
import sminos_audience as audience  # noqa: E402
import sminos_channels as channels  # noqa: E402

BASE_DIR = os.path.realpath(tempfile.mkdtemp(prefix="smsp."))
MERGE_BASE = "1b5b56f977cde0d79c9b42ba9ef5d5c2d6e9ba58"   # `git merge-base origin/main HEAD` when M1 was built
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts")


class Spawns(Requests):
    """A spawn run here in-process, its launch played: the child a live `bg` session of this machine."""

    def spawn(self, *argv, alias="w", meanwhile=None, session=None):
        """(exit, stdout, stderr, the child's session or None) of `sminos spawn <alias> "a task" <argv>` from a
        terminal (or `session`); `meanwhile(child)` runs while the launcher is polled for the session's id."""
        child = {}

        def start(args, cwd, settings):
            child["sid"], child["proc"] = self.session(kind="bg", root=cwd)
            child["task"] = args[-1]
            return child["sid"][:8], "banner"

        def poll(short, max_iter=None):
            if meanwhile is not None:
                meanwhile(child)
            return child["sid"], "working", self.root
        out, err = io.StringIO(), io.StringIO()
        here = os.getcwd()
        os.chdir(self.root)
        try:
            with mock.patch.object(sminos, "run_claude_bg", side_effect=start), \
                    mock.patch.object(sminos, "poll_uuid", side_effect=poll), \
                    mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": session} if session else {}), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                if not session:
                    os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
                try:
                    sminos.main(["spawn", alias, "a task", *argv])
                    code = 0
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 1
        finally:
            os.chdir(here)
            sminos.forget_caches()
        self.child = child
        return code, out.getvalue(), err.getvalue(), child.get("sid")

    def channel_events(self, cid):
        out = []
        for path in glob.glob(os.path.join(sminos.projects_root(), cid, "log", "*.jsonl")):
            with open(path) as f:
                out += [json.loads(line) for line in f if line.strip()]
        return out

    def seat_of(self, alias="w"):
        return next(s for s in sminos.seats(sminos.derive_group(self.root)) if s["alias"] == alias)


# ------------------------------------------------------------ the statement (acceptance 2)


class Placed(Spawns):
    def test_a_new_seat_is_placed_by_its_own_statement_after_its_joined_and_nothing_goes_into_the_channel(self):
        code, out, err, sid = self.spawn("--channel", "desk")
        self.assertEqual(code, 0, out + err)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("seat spawned: "), out)
        self.assertEqual(lines[1], "w#%s: in desk" % sid[:8], "the banner, then the channel's line")
        self.assertEqual(err, "")
        seat = self.seat_of()
        self.assertEqual(threads.get(seat["seat_id"])["channels"], [DESK])
        own = self.own(sid)
        kinds = [e["kind"] for e in own]
        self.assertLess(kinds.index("joined"), kinds.index("channels"), "the statement after the joined")
        st = [e for e in own if e["kind"] == "channels"]
        self.assertEqual(len(st), 1)
        self.assertEqual((st[0]["channels"], st[0]["writer"], st[0]["thread"]),
                         ([DESK], "%s/%s" % (sminos.host_name(), sid), seat["seat_id"]),
                         "the thread's whole set, under its own writer")
        self.assertNotIn("answers", st[0], "no request answered: its own add")
        self.assertEqual(self.channel_events(DESK), [], "no request in the channel's log")
        self.assertEqual([(p.id, m.session) for p, m in channels.roster(self.chan(DESK))], [(self.p.id, sid)])

    def test_two_values_naming_one_channel_count_once_and_two_channels_are_both_placed(self):
        code, out, err, sid = self.spawn("--channel", "desk", "--channel", DESK, "--channel", "lobby")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out.splitlines()[1:], ["w#%s: in desk" % sid[:8], "w#%s: in lobby" % sid[:8]])
        self.assertEqual(threads.get(self.seat_of()["seat_id"])["channels"], [DESK, LOBBY])

    def test_the_preamble_says_the_placement_is_asked_for_by_each_channels_id(self):
        self.spawn("--channel", "desk", "--channel", "lobby")
        task = self.child["task"]
        for cid, name in ((DESK, "desk"), (LOBBY, "lobby")):
            self.assertIn('You are being placed in the channel "%s", as your spawner asked: `sminos list %s` shows you '
                          'there once it is recorded, `sminos chat %s` reads it, and `sminos say --in %s "…"` speaks '
                          'in it.' % (name, cid, cid, cid), task)
        self.assertIn("is not your human's instruction.\n\nYou are being placed", task, "after the channels' paragraph")

    def test_a_placeholder_written_in_a_name_is_kept_as_written(self):
        for channels_asked in ((), ({"id": DESK, "name": "desk"},)):
            text = sminos.render_preamble("p{{CHANNELS}}q", "a{{BY}}b", "c{{PROJECT}}d", channels_asked)
            for literal in ("p{{CHANNELS}}q", "a{{BY}}b", "c{{PROJECT}}d"):
                self.assertIn(literal, text, (literal, channels_asked))

    def test_a_refill_of_a_stopped_seat_keeps_its_channel_and_states_under_the_new_writer(self):
        code, out, err, first = self.spawn("--channel", "lobby")
        self.assertEqual(code, 0, out + err)
        self.end(self.child["proc"])
        self.reconcile()
        code, out, err, second = self.spawn("--channel", "desk")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("seat re-filled: "), out)
        self.assertNotEqual(first, second)
        seat = self.seat_of()["seat_id"]
        self.assertEqual(threads.get(seat)["channels"], [LOBBY, DESK], "in both")
        st = [e for e in self.own(second) if e["kind"] == "channels"]
        self.assertEqual([(e["writer"], e["channels"]) for e in st][-1:],
                         [("%s/%s" % (sminos.host_name(), second), [LOBBY, DESK])], "under the refill's new writer")
        self.assertEqual([e for e in self.own(first) if e["kind"] == "channels" and DESK in e["channels"]], [],
                         "never under the displaced session's")

    def test_with_wait_the_thread_is_placed_before_the_wait_begins(self):
        seen = {}

        def watched(seat_id, short, alias, uuid_hint, guard):
            seen["channels"] = list(threads.get(seat_id)["channels"])
            return "idle"
        with mock.patch.object(sminos, "finish_turn", side_effect=watched):
            code, out, err, sid = self.spawn("--channel", "desk", "--wait")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(seen["channels"], [DESK])
        self.assertEqual(out.splitlines()[1], "w#%s: in desk" % sid[:8])


# ------------------------------------------------------------ refused before anything is launched (acceptance 4, 5)


class Refused(Spawns):
    def assert_refused(self, code, words, *argv):
        with mock.patch.object(sminos, "run_claude_bg") as launch:
            got, out, err, _ = self.spawn(*argv)
        self.assertEqual(got, code, out + err)
        self.assertIn(words, err)
        launch.assert_not_called()
        self.assertEqual(sminos.seats(sminos.derive_group(self.root)), [], "no seat")
        return err

    def test_a_name_no_log_answers_several_answer_or_a_projects(self):
        self.assert_refused(4, "no channel 'nowhere' is known on this machine", "--channel", "nowhere")
        sminos.register_if_absent(sminos.make_project(channel_ids(1)[0], "desk", "", "", HUB))
        sminos.forget_caches()
        self.assert_refused(4, "ambiguous name 'desk'", "--channel", "lobby", "--channel", "desk")
        self.assert_refused(4, "'%s' is a project, not a channel" % self.p.id, "--channel", self.p.id)

    def test_more_than_128_channels(self):
        ids = channel_ids(129)
        for cid in ids:
            sminos.register_if_absent(sminos.make_project(cid, "c" + cid[:8], "", "", HUB))
        sminos.forget_caches()
        argv = [w for cid in ids for w in ("--channel", cid)]
        self.assert_refused(1, "--channel names 129 channels, and a thread is in at most 128: nothing was spawned",
                            *argv)

    def test_128_channels_named_by_more_values_are_one_set(self):
        ids = channel_ids(128)
        for cid in ids:
            sminos.register_if_absent(sminos.make_project(cid, "c" + cid[:8], "", "", HUB))
        sminos.forget_caches()
        argv = [w for cid in ids + ids[:3] for w in ("--channel", cid)]
        with mock.patch.object(channels, "change", return_value=channels.Outcome("applied")) as change:
            code, out, err, _ = self.spawn(*argv)
        self.assertEqual(code, 0, err)
        self.assertEqual([c.args[1].id for c in change.call_args_list], ids, "each once, in the order named")

    def test_a_channel_this_enrollment_does_not_carry(self):
        sminos.write_json(os.path.join(sminos.projects_root(), ROOM, "project.json"),
                          {"project": ROOM, "name": "room", "remote": "", "root": "",
                           "hub": {"url": HUB["url"], "org": "org-2"}})
        sminos.forget_caches()
        self.assert_refused(1, "cannot spawn a thread into room: this machine's enrollment does not carry its log "
                               "(its registration on this machine names another org): nothing was spawned",
                            "--channel", "desk", "--channel", "room")

    def test_a_welcome_that_lists_no_channels_and_one_not_kept_yet_each_in_its_own_words(self):
        audience.keep_capabilities(["access"])
        err = self.assert_refused(1, "this machine's endpoint does not serve channels", "--channel", "desk")
        self.assertIn("Without --channel it is spawned in no channel", err)
        os.unlink(audience.audiences_path())
        err = self.assert_refused(1, "this machine has kept no welcome of its endpoint yet, so whether it serves "
                                     "channels is not known: nothing was spawned", "--channel", "desk")
        self.assertNotIn("does not serve", err)
        with open(audience.audiences_path(), "w") as f:
            f.write("{not json")
        self.assert_refused(1, "has kept no welcome of its endpoint yet", "--channel", "desk")

    def test_kept_capability_reads_three_ways(self):
        audience.keep_capabilities(["channels"])
        self.assertIs(audience.kept_capability("channels"), True)
        audience.keep_capabilities([])
        self.assertIs(audience.kept_capability("channels"), False)
        sminos.write_json(audience.audiences_path(), {"v": 1, "sessions": {}})
        self.assertIsNone(audience.kept_capability("channels"), "no welcome's capabilities in it")
        os.unlink(audience.audiences_path())
        self.assertIsNone(audience.kept_capability("channels"))
        self.assertFalse(audience.advertised("channels"), "advertised keeps its two answers")


# ------------------------------------------------------------ after the launch nothing is a refusal (acceptance 6)


class AfterLaunch(Spawns):
    def test_each_failed_word_is_a_warning_with_the_command_that_places_it(self):
        for word in sorted(channels.OWN_FAILED):
            with self.subTest(word=word), mock.patch.object(channels, "change",
                                                            return_value=channels.Outcome("failed", word)):
                code, out, err, sid = self.spawn("--channel", "desk", alias="w-" + word)
                self.assertEqual(code, 0, err)
                self.assertTrue(out.startswith("seat spawned: "), out)
                self.assertIn("sminos: warning: spawn completed, but w-%s#%s was not placed in desk (%s): sminos "
                              "channel add %s %s places it" % (word, sid[:8], channels.OWN_FAILED[word], DESK, sid),
                              err)
                self.assertNotIn(": in desk", out)

    def test_the_limit_is_said_and_the_spawn_stands(self):
        code, out, err, sid = self.spawn("--channel", "lobby")
        self.end(self.child["proc"])
        self.reconcile()
        with mock.patch.object(threads, "CHANNEL_LIMIT", 1):
            code, out, err, sid = self.spawn("--channel", "desk")
        self.assertEqual(code, 0, err)
        self.assertIn("was not placed in desk (it is in 128 channels, the limit): sminos channel add %s %s places it"
                      % (DESK, sid), err)
        self.assertEqual(threads.get(self.seat_of()["seat_id"])["channels"], [LOBBY])

    def test_an_enrollment_gone_to_another_org_meanwhile_is_one_warning_and_no_command(self):
        def meanwhile(child):
            self.identity(sminos.host_name())
            path = os.path.join(os.environ["SMINOS_HOME"], "daemon", "identity.json")
            with open(path) as f:
                d = json.load(f)
            d["org"] = "org-2"
            sminos.write_json(path, d, mode=0o600)
        code, out, err, sid = self.spawn("--channel", "desk", "--channel", "lobby", meanwhile=meanwhile)
        self.assertEqual(code, 0, err)
        self.assertIn("spawn completed, but none of the placements asked for was made: %s is no longer enrolled in "
                      "this org" % sminos.host_name(), err)
        self.assertNotIn("channel add", err)
        self.assertEqual(threads.get(self.seat_of()["seat_id"]).get("channels") or [], [])

    def test_a_registration_made_uncarried_meanwhile_is_that_channels_alone(self):
        def meanwhile(child):
            sminos.write_json(os.path.join(sminos.projects_root(), LOBBY, "project.json"),
                              {"project": LOBBY, "name": "lobby", "remote": "", "root": ""})
        code, out, err, sid = self.spawn("--channel", "lobby", "--channel", "desk", meanwhile=meanwhile)
        self.assertEqual(code, 0, err)
        self.assertIn("was not placed in lobby (its machine's enrollment does not carry it now): sminos channel add "
                      "%s %s places it" % (LOBBY, sid), err)
        self.assertEqual(out.splitlines()[1:], ["w#%s: in desk" % sid[:8]])


class Deadline(Spawns):
    """place_spawned as a VM runs it, onto a seat of this machine."""

    def test_a_lock_another_process_holds_on_the_second_channel_costs_it_alone_and_the_deadline_holds(self):
        code, out, err, sid = self.spawn()
        seat = self.seat_of()
        unknown = channel_ids(1)[0]   # not registered here: the placement registers it, under its lock
        home = os.path.join(sminos.projects_root(), unknown)
        os.makedirs(home)
        holder = subprocess.Popen([sys.executable, "-c", "import fcntl, sys, time\nf = open(sys.argv[1], 'a')\n"
                                   "fcntl.flock(f, fcntl.LOCK_EX)\nprint('held', flush=True)\ntime.sleep(60)",
                                   os.path.join(home, "project.json.lock")], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (holder.kill(), holder.wait(), holder.stdout.close()))
        self.assertEqual(holder.stdout.readline().strip(), "held")
        with mock.patch.dict(os.environ, {"SMINOS_PLACE_BUDGET": "1.5"}):
            began = time.monotonic()
            got, carried = channels.place_spawned(seat["seat_id"], sid, {"cwd": self.root, "group": seat["group"]},
                                         [{"id": DESK, "name": "desk"}, {"id": unknown, "name": "fresh"},
                                          {"id": LOBBY, "name": "lobby"}], HUB["org"])
            took = time.monotonic() - began
        self.assertEqual(got, [{"id": DESK, "state": "applied", "why": ""},
                               {"id": unknown, "state": "failed", "why": "time"},
                               {"id": LOBBY, "state": "failed", "why": "time"}])
        self.assertLess(took, 3.0, "one deadline for all of them")
        self.assertGreaterEqual(took, 1.4)
        self.assertEqual(sminos.registration(unknown), {}, "nothing registered without its lock")

    def hold(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        holder = subprocess.Popen([sys.executable, "-c", "import fcntl, sys, time\nf = open(sys.argv[1], 'a')\n"
                                   "fcntl.flock(f, fcntl.LOCK_EX)\nprint('held', flush=True)\ntime.sleep(60)",
                                   path], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (holder.kill(), holder.wait(), holder.stdout.close()))
        self.assertEqual(holder.stdout.readline().strip(), "held")

    def placed_under(self, budget, seat, sid, asked):
        said = io.StringIO()
        with mock.patch.dict(os.environ, {"SMINOS_PLACE_BUDGET": budget}), contextlib.redirect_stderr(said):
            began = time.monotonic()
            got, carried = channels.place_spawned(seat["seat_id"], sid, None, asked, HUB["org"])
            took = time.monotonic() - began
        self.assertIsNone(sminos.waits_deadline(), "the deadline is the placement's alone")
        self.assertIsNone(carried, "no seat, no carriage read")
        return got, took, said.getvalue()

    def test_a_lock_the_add_reaches_with_no_deadline_of_its_own_is_waited_for_until_the_placements(self):
        # The seat's project registered without its optional `remote`: the first path into its home after the
        # placement drops the caches rewrites project.json under its lock, which the statement's append reaches
        # with no deadline of its own. Held, the record's add is committed and its statement left to the next
        # reconciliation, as `channel add` leaves it: applied, said, and at the deadline.
        code, out, err, sid = self.spawn()
        seat = self.seat_of()
        reg = os.path.join(self.p.home, "project.json")
        with open(reg) as f:
            d = json.load(f)
        d.pop("remote", None)
        with open(reg, "w") as f:
            json.dump(d, f)
        self.hold(reg + ".lock")
        got, took, said = self.placed_under("0.3", seat, sid, [{"id": DESK, "name": "desk"}])
        self.assertEqual(got, [{"id": DESK, "state": "applied", "why": ""}])
        self.assertLess(took, 1.0, "the deadline holds for a lock the add reaches without one")
        self.assertIn("is left to the next reconciliation", said)
        self.assertEqual(threads.get(seat["seat_id"])["channels"], [DESK], "the record holds it")

    def test_a_lock_met_before_the_add_is_committed_is_time(self):
        # The seat store's lock, under which set_channels commits the add.
        code, out, err, sid = self.spawn()
        seat = self.seat_of()
        self.hold(os.path.join(sminos.root(), ".metalock"))
        got, took, said = self.placed_under("0.3", seat, sid, [{"id": DESK, "name": "desk"}])
        self.assertEqual(got, [{"id": DESK, "state": "failed", "why": "time"}])
        self.assertLess(took, 1.0)
        self.assertEqual(threads.get(seat["seat_id"])["channels"], [], "nothing committed")

    def test_a_channel_this_machine_does_not_know_is_registered_from_the_request_and_one_it_knows_kept(self):
        code, out, err, sid = self.spawn()
        seat = self.seat_of()
        fresh = channel_ids(1)[0]
        got, carried = channels.place_spawned(seat["seat_id"], sid, {"cwd": self.root, "group": seat["group"]},
                                     [{"id": fresh, "name": "fresh"}, {"id": DESK, "name": "elsewhere"}], HUB["org"])
        self.assertEqual([g["state"] for g in got], ["applied", "applied"])
        self.assertEqual((carried["project"].id, carried["not_carried"]), (self.p.id, ""), "carried: no word")
        reg = sminos.registration(fresh)
        self.assertEqual((reg["name"], reg["root"], reg["hub"]["org"]), ("fresh", "", HUB["org"]))
        self.assertEqual(sminos.registration(DESK)["name"], "desk", "its own registration kept")

    def test_a_seat_whose_project_is_not_carried_is_placed_nowhere(self):
        code, out, err, sid = self.spawn("--channel", "lobby")
        seat = self.seat_of()
        with mock.patch.object(sminos, "not_carried", side_effect=lambda p, org: "x" if p.id == self.p.id else ""):
            got, carried = channels.place_spawned(seat["seat_id"], sid, {"cwd": self.root, "group": seat["group"]},
                                         [{"id": DESK, "name": "desk"}], HUB["org"])
        self.assertEqual(got, [{"id": DESK, "state": "failed", "why": "project-not-carried"}])
        self.assertEqual((carried["project"].id, carried["not_carried"]), (self.p.id, "x"),
                         "the project and its carriage the outcome takes, from the same read")
        self.assertEqual(threads.get(seat["seat_id"])["channels"], [LOBBY], "what it held is kept")

    def test_a_seat_read_the_deadline_cuts_short_places_nothing_and_promises_no_reach(self):
        code, out, err, sid = self.spawn()
        seat = self.seat_of()

        def slow(seat, fresh=False):
            time.sleep(0.4)
            return self.p
        with mock.patch.object(sminos, "seat_project", side_effect=slow), \
                mock.patch.dict(os.environ, {"SMINOS_PLACE_BUDGET": "0.2"}):
            got, carried = channels.place_spawned(seat["seat_id"], sid, {"cwd": self.root, "group": seat["group"]},
                                                  [{"id": DESK, "name": "desk"}], HUB["org"])
        self.assertEqual(got, [{"id": DESK, "state": "failed", "why": "time"}])
        self.assertEqual(carried, {"project": None, "not_carried": channels.CARRIAGE_UNREAD})

    def test_a_purge_met_under_the_deadline_is_left_open_for_the_next_finisher(self):
        record = {"thread": "t", "current": "s", "opened": "spawned", "ended": {"pid": 123}}
        with mock.patch.object(sminos, "running_now", side_effect=AssertionError("no check under a deadline")):
            with sminos.waits_until(time.time() + 30):
                with self.assertRaises(sminos.LockBusy):
                    sminos.purge_stop(record, {"settle": "s"})
        with mock.patch.object(sminos, "running_now", return_value=None) as checked:
            sminos.purge_stop(record, {"settle": "s"})
        checked.assert_called_once_with("s")

    def test_anything_else_is_error_said_and_never_raised(self):
        code, out, err, sid = self.spawn()
        seat = self.seat_of()
        said = io.StringIO()
        with mock.patch.object(channels, "change", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stderr(said):
            got, carried = channels.place_spawned(seat["seat_id"], sid, None, [{"id": DESK, "name": "desk"}], HUB["org"])
        self.assertEqual(got, [{"id": DESK, "state": "failed", "why": "error"}])
        self.assertIn("placing the spawned thread failed: RuntimeError: boom", said.getvalue())


# ------------------------------------------------------------ nothing else changed (acceptance 11, a spawn)


SPAWN_FLAGS = {"--role": "r", "--brief": "b", "--cwd": "/x", "--worktree": "wt", "--stamp": "a=b",
               "--permission-mode": "plan", "--no-wait": None, "--on": "vm1", "--vm-project": "o/r",
               "--vm-confirmed": None, "--asked-from": "{}", "--model": "m", "--settings": "s", "--effort": "e",
               "--wait": None}
PARSE = """import json, sys
sys.path.insert(0, sys.argv[1])
import sminos
out = []
for argv in json.loads(sys.argv[2]):
    try:
        ns = vars(sminos.build_parser().parse_args(argv))
        ns.pop("fn", None)
        ns.pop("channel", None)
        out.append(ns)
    except SystemExit as e:
        out.append("exit %s" % e.code)
print(json.dumps(out, default=repr))"""


class SameAsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=BASE_DIR)
        cls.base = extracted(MERGE_BASE, cls.tmp)

    def parsed(self, launcher, argvs):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        done = subprocess.run([sys.executable, "-B", "-c", PARSE, os.path.dirname(launcher), json.dumps(argvs)],
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_every_spelling_of_every_flag_of_spawn_but_c(self):
        argvs, spelled = [], []
        for flag, value in SPAWN_FLAGS.items():
            for n in range(3, len(flag) + 1):
                word = flag[:n]
                spelled.append(word)
                argvs.append(["spawn", "a", "t", word] + ([] if value is None else [value]))
                if value is not None:
                    spelled.append(word + "=")
                    argvs.append(["spawn", "a", "t", "%s=%s" % (word, value)])
        base = self.parsed(self.base, argvs)
        here = self.parsed(os.path.join(SCRIPTS, "sminos"), argvs)
        differ = sorted({spelled[i] for i in range(len(argvs)) if base[i] != here[i]})
        self.assertEqual(differ, ["--c", "--c="], "only --c, ambiguous beside --channel")
        self.assertTrue(all(isinstance(here[i], str) for i in range(len(argvs)) if spelled[i] in ("--c", "--c=")))

    def scene(self, launcher):
        home = tempfile.mkdtemp(dir=BASE_DIR)
        env = dict(os.environ, HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"),
                   DAEMON_HOST="alpha", DAEMON_BOOT_ID="boot-current", SMINOS_DERIVE_EVERY="0", SMINOS_UUID_POLL="5",
                   SMINOS_POLL_INTERVAL="0.05", FAKE_CLAUDE_STATE=os.path.join(home, "claude"),
                   PATH=os.path.join(home, "bin") + os.pathsep + os.environ["PATH"])
        for k in ("CLAUDE_CODE_SESSION_ID", "MAWS_USER_DATA", "CLAUDE_CONFIG_DIR", "SMINOS_RL10"):
            env.pop(k, None)
        os.makedirs(os.path.join(env["HOME"], ".claude", "sessions"))
        os.makedirs(env["SMINOS_HOME"])
        os.makedirs(os.path.join(home, "bin"))
        os.symlink(os.path.join(HERE, "fake_claude.py"), os.path.join(home, "bin", "claude"))
        work = os.path.join(home, "work")
        subprocess.run(["git", "init", "-q", work], check=True)
        done = subprocess.run([launcher, "spawn", "w", "a task", "--brief", "its line"], cwd=work, env=env,
                              capture_output=True, text=True, timeout=120)
        with open(os.path.join(env["FAKE_CLAUDE_STATE"], "calls.log")) as f:
            launches = [json.loads(line) for line in f if '"--bg"' in line]
        norm = lambda t: re.sub(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}|\b[0-9a-f]{8,16}\b", "<id>",  # noqa: E731
                                t.replace(home, "<home>"))
        return done.returncode, norm(done.stdout), norm(done.stderr), norm(json.dumps(launches))

    def test_a_spawn_without_channel_prints_and_launches_what_the_merge_base_does(self):
        base = self.scene(self.base)
        here = self.scene(os.path.join(SCRIPTS, "sminos"))
        self.assertEqual(base[0], 0, base)
        self.assertEqual(here, base)


if __name__ == "__main__":
    unittest.main()
