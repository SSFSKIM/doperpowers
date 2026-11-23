#!/usr/bin/env python3
"""`sminos say --notice <program> --pools <text>` (EN.G2's M3:
docs/doperpowers/plans/2026-11-23-sminos-environments-en-g2.md, acceptance
9, 10 and 11 for `say`; Interfaces §4): a machine's notice recorded in the
log of every channel whose pool holds the machine, as this machine's copy
of the logs holds that pool when it is called.

- The form: `--pools` without `--notice`, inside a session, beside `--in`,
  beside a selector and before a text that opens with a tag, each refused as
  a usage error before anything is written; the merge base's parser and this
  one agree on every spelling of every flag of `say` but `--p`, now refused
  as ambiguous.
- Which channels: a machine in no pool (exit 0, nothing recorded); a pool
  held by hand alone and by a stopped thread alone; two channels written, one
  whose pool does not hold the machine left alone, and one passed over for a
  failure (its log not carried, its append failing: said on standard error,
  exit 1); a channel that has left this machine passed over without a word;
  one event a channel for one call, however the pool holds the machine.
- The event: kind `human` under the machine's human writer, `to` "*",
  `notice` the program, the text as given; delivered to no one, no thread
  woken, the lead not addressed, nothing in any project's log, devcloud
  never asked.
- The copy's two errors, pinned as stated: a hand-add's removal this copy
  does not hold yet still records; once it holds it, nothing is recorded
  there. A hand-add whose writer's row this machine may not read records
  nothing.
- Queued: a human writer waiting for its upstream head exits 0 with the
  waiting line and nothing in the log; the release appends one event, a
  second release none.

Hermetic: test_channels_say.Say (test_channels_delivery's Channel on a
machine cut over to an endpoint never run, its kept welcome listing
`channels`); another machine's threads are its writers' events in a hub
project's log, as an import leaves them; devcloud is its stand-in, which
records every call.
Run: python3 -B sminos/tests/test_channels_pools.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import glob
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import test_channels_say as said_tests  # noqa: E402 — the module, so its own test classes are not collected here
from test_channels_delivery import FAR  # noqa: E402
from test_channels_life import DESK, HUB, LOBBY, ROOM  # noqa: E402
from test_threads import BASE, SCRIPTS, sminos, threads  # noqa: E402
import sminos_channels as channels  # noqa: E402

FOREIGN = said_tests.FOREIGN   # a channel registered under another org: its log is not carried here
MERGE_BASE = "1b5b56f977cde0d79c9b42ba9ef5d5c2d6e9ba58"   # `git merge-base origin/main HEAD` when EN.G2 was built
TEXT = "devcloud on vm-one: idle 3d 4h; last active 2026-11-20T08:00Z; runs until down"


class Pools(said_tests.Say):
    """Say, with the machine's notice run as a host runs it: from no session, in-process."""

    def notice(self, *argv, text=TEXT):
        """(exit, stdout, stderr) of `sminos say --notice devcloud --pools <text>` at a terminal of this machine."""
        out, err = io.StringIO(), io.StringIO()
        here = os.getcwd()
        os.chdir(self.root)
        try:
            with mock.patch.dict(os.environ, {}), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
                try:
                    sminos.main(["say", *(argv or ("--notice", "devcloud", "--pools")), text])
                    code = 0
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 1
        finally:
            os.chdir(here)
            sminos.forget_caches()
        return code, out.getvalue(), err.getvalue()

    def notices(self, cid):
        """The marked events of the channel's log."""
        return [e for e in self.says(cid) if e.get("notice")]

    def far_in(self, cid, alias):
        """Another machine's live thread, a member of `app` and of the channel `cid` by its own writer's events
        there, as an import leaves them: (thread, session, writer)."""
        sid, tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        w = "%s/%s" % (FAR, sid)
        sminos.log_append(self.app, w, "joined", session=sid, alias=alias, name_source="user", machine=FAR,
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive", thread=tid,
                          owners=["m-far"])
        sminos.log_append(self.app, w, "state", session=sid, state="idle", machine=FAR)
        sminos.log_append(self.app, w, "channels", session=sid, thread=tid, op=os.urandom(8).hex(), channels=[cid])
        sminos.forget_caches()
        return tid, sid, w

    def by_hand(self, cid, writer, tid, op="add", machine=None):
        """A `channel-env` of the channel's log under `writer`, naming this machine, as an import leaves one."""
        time.sleep(0.002)   # the merged log's order is by time
        sminos.log_append(self.chan(cid), writer, "channel-env", op=op, machine=machine or sminos.host_name(),
                          thread=tid)
        sminos.forget_caches()

    def in_pool(self, cid):
        sminos.forget_caches()
        here = sminos.host_name().lower()
        return any(e["machine"].lower() == here for e in channels.pool(self.chan(cid)))

    def no_devcloud(self):
        self.assertFalse(os.path.exists(os.path.join(os.environ["HOME"], "devcloud-standin.calls")),
                         "devcloud was never asked")


# ------------------------------------------------------------ the form (§4)


class Form(Pools):
    def test_each_wrong_form_is_a_usage_error_before_anything_is_written(self):
        tid, sid, _ = self.live("reader")
        before = self.logs()
        cases = {
            "--pools without --notice": (("--pools",), None, "--pools"),
            "inside a session": (("--notice", "devcloud", "--pools"), sid, "a session is not one"),
            "beside --in": (("--notice", "devcloud", "--pools", "--in", "desk"), None, "--in"),
            "beside a selector": (("--notice", "devcloud", "--pools", "--project", "app"), None, "selector"),
            "beside --org": (("--notice", "devcloud", "--pools", "--org"), None, "selector"),
        }
        for why, (argv, session, words) in cases.items():
            with self.subTest(why):
                if session:
                    with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": session}):
                        code, out = self.cli("say", *argv, TEXT)
                else:
                    code, out, err = self.notice(*argv)
                    out += err
                self.assertEqual(code, 2, out)
                self.assertIn(words, out)
        for text in ("@reader " + TEXT, "@all " + TEXT, "@desk/reader " + TEXT):
            with self.subTest(text=text):
                code, out, err = self.notice(text=text)
                self.assertEqual(code, 2, out + err)
                self.assertIn("opens with a tag", err)
        self.assertEqual(self.logs(), before, "nothing was written")


SAY_FLAGS = {"--in": "x", "--notice": "devcloud", "--exit-held": None, "--project": "p", "--machine": "m",
             "--state": "idle", "--org": None, "--here": None}
PARSE = """import json, sys
sys.path.insert(0, sys.argv[1])
import sminos
out = []
for argv in json.loads(sys.argv[2]):
    try:
        ns = vars(sminos.build_parser().parse_args(argv))
        ns.pop("fn", None)
        ns.pop("pools", None)
        out.append(ns)
    except SystemExit as e:
        out.append("exit %s" % e.code)
print(json.dumps(out, default=repr))"""


class SameAsBase(unittest.TestCase):
    """Acceptance 11 for `say`'s parser. What a `say` without --pools prints and writes is
    test_channels_say.SameAsBase's, against an earlier base, which this child's merge base equals there."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=BASE)
        cls.base = said_tests.extracted(MERGE_BASE, cls.tmp)

    def parsed(self, launcher, argvs):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        done = subprocess.run([sys.executable, "-B", "-c", PARSE, os.path.dirname(launcher), json.dumps(argvs)],
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_every_spelling_of_every_flag_of_say_but_p(self):
        argvs, spelled = [], []
        for flag, value in SAY_FLAGS.items():
            for n in range(3, len(flag) + 1):
                word = flag[:n]
                spelled.append(word)
                argvs.append(["say", word] + ([] if value is None else [value]) + ["a text"])
                if value is not None:
                    spelled.append(word + "=")
                    argvs.append(["say", "%s=%s" % (word, value), "a text"])
        base = self.parsed(self.base, argvs)
        here = self.parsed(os.path.join(SCRIPTS, "sminos"), argvs)
        differ = sorted({spelled[i] for i in range(len(argvs)) if base[i] != here[i]})
        self.assertEqual(differ, ["--p", "--p="], "only --p, ambiguous beside --pools")
        self.assertTrue(all(here[i] == "exit 2" for i in range(len(argvs)) if spelled[i] in ("--p", "--p=")))
        self.assertNotIn("exit 2", [base[i] for i in range(len(argvs)) if spelled[i] in ("--p", "--p=")],
                         "the merge base took it for --project")


# ------------------------------------------------------------ which channels, and the event (§4; acceptance 9)


class Which(Pools):
    def test_a_machine_in_no_pool_records_nothing_and_exits_0(self):
        self.far_in(DESK, "faraway")
        self.assertFalse(self.in_pool(DESK))
        before = self.logs()
        code, out, err = self.notice()
        self.assertEqual((code, out, err), (0, channels.POOLS_NONE + "\n", ""))
        self.assertEqual(self.logs(), before, "nothing was recorded")
        self.no_devcloud()

    def test_two_channels_written_one_outside_left_alone_one_uncarried_passed_over_and_the_event(self):
        rtid, rsid, received = self.live("reader")                     # desk: a live thread of this machine
        self.lead_event(rtid, rsid)
        ftid, _, fw = self.far_in(LOBBY, "lobbyist")                   # lobby: by hand alone
        self.by_hand(LOBBY, fw, ftid)
        self.far_in(ROOM, "roomie")                                    # room: beta's alone
        sminos.register_if_absent(sminos.make_project(FOREIGN, "foreign", "", "", {"url": HUB["url"],
                                                                                    "org": "org-2"}))
        gtid, _, gw = self.far_in(FOREIGN, "foreigner")                # foreign: by hand, its log not carried
        self.by_hand(FOREIGN, gw, gtid)
        self.assertEqual([self.in_pool(c) for c in (DESK, LOBBY, ROOM, FOREIGN)], [True, True, False, True])
        code, out, err = self.notice()
        self.assertEqual(code, 1, out + err)
        self.assertEqual(sorted(line.rpartition(" in ")[2] for line in out.splitlines()), ["desk", "lobby"])
        self.assertTrue(all(line.startswith("recorded ") for line in out.splitlines()), out)
        self.assertEqual(err.splitlines(), [
            "sminos: warning: " + channels.POOLS_PASSED % ("foreign", "cannot say into foreign: this machine's "
                                                           "enrollment does not carry its log (its registration on "
                                                           "this machine names another org): nothing was written")])
        self.assertEqual(self.notices(FOREIGN), [])
        self.assertEqual(self.notices(ROOM), [], "a channel whose pool does not hold this machine")
        for cid in (DESK, LOBBY):
            [e] = self.notices(cid)
            self.assertEqual({k: e[k] for k in ("kind", "writer", "from", "to", "notice", "text")},
                             {"kind": "human", "writer": sminos.writer_id(), "from": "human", "to": "*",
                              "notice": "devcloud", "text": TEXT})
            self.assertNotIn("thread", e)
            self.assertNotIn("from_project", e)
        self.assertEqual(self.lead_now(), "reader", "desk has a lead, and the notice is addressed to no one")
        self.deliver(DESK)
        self.assertEqual(self.got(received, "idle 3d"), [], "no frame for it")
        self.assertEqual(self.woken_got(rsid, "idle 3d"), [], "no thread woken")
        self.assertEqual([e for _, e in self.project_says() if e.get("notice")], [], "no project's log")
        self.no_devcloud()

    def lead_event(self, tid, sid):
        sminos.log_append(self.chan(DESK), sminos.writer_id(), "channel-lead", thread=tid, session=sid)
        sminos.forget_caches()

    def lead_now(self):
        sminos.forget_caches()
        got = channels.lead_of(self.chan(DESK))
        return None if got is None else got[1].alias

    def test_a_pool_held_by_hand_alone_or_by_a_stopped_thread_alone(self):
        self.stopped(cid=LOBBY)
        ftid, _, fw = self.far_in(DESK, "faraway")
        self.by_hand(DESK, fw, ftid)
        code, out, err = self.notice()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(self.notices(DESK)), 1, "by hand alone")
        self.assertEqual(len(self.notices(LOBBY)), 1, "a stopped thread alone")

    def test_one_event_a_channel_however_the_pool_holds_the_machine(self):
        self.live("reader")
        self.stopped()
        ftid, _, fw = self.far_in(DESK, "faraway")
        self.by_hand(DESK, fw, ftid)
        code, out, err = self.notice()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(out.splitlines()), 1, out)
        self.assertEqual(len(self.notices(DESK)), 1)

    def test_an_append_that_fails_is_that_channels_alone(self):
        self.live("reader")
        self.stopped(cid=LOBBY)
        real = sminos.log_append

        def append(project, *args, **kw):
            if project.id == DESK:
                raise OSError("disk full")
            return real(project, *args, **kw)
        with mock.patch.object(sminos, "log_append", append):
            code, out, err = self.notice()
        self.assertEqual(code, 1, out + err)
        self.assertEqual(out.splitlines()[-1].rpartition(" in ")[2], "lobby", out)
        self.assertEqual(err.splitlines(), ["sminos: warning: " + channels.POOLS_PASSED % (
            "desk", "say could not be recorded: disk full")])
        self.assertEqual((self.notices(DESK), len(self.notices(LOBBY))), ([], 1))

    def test_a_channel_that_has_left_this_machine_is_passed_over_without_a_word(self):
        ftid, _, fw = self.far_in(DESK, "faraway")
        self.by_hand(DESK, fw, ftid)
        self.stopped(cid=LOBBY)
        real = sminos.has_left
        with mock.patch.object(sminos, "has_left", lambda p: p.id == DESK or real(p)):
            code, out, err = self.notice()
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual((self.notices(DESK), len(self.notices(LOBBY))), ([], 1))


# ------------------------------------------------------------ the copy's two errors (R23), pinned as stated


class Copy(Pools):
    def test_a_removal_this_copy_does_not_hold_yet_still_records_and_once_held_nothing_does(self):
        ftid, _, fw = self.far_in(DESK, "faraway")
        self.by_hand(DESK, fw, ftid)
        code, out, err = self.notice()
        self.assertEqual((code, len(self.notices(DESK))), (0, 1), out + err)
        # beta removes this machine by hand; the event is imported here only now.
        self.by_hand(DESK, fw, ftid, op="remove")
        code, out, err = self.notice()
        self.assertEqual((code, out), (0, channels.POOLS_NONE + "\n"), err)
        self.assertEqual(len(self.notices(DESK)), 1, "nothing more recorded there")

    def test_a_hand_add_whose_writers_row_this_machine_may_not_read_records_nothing(self):
        # A writer of beta's that is a member of no project this machine holds: its row is not read here.
        self.far_in(DESK, "faraway")
        unread = "%s/%s" % (FAR, uuidlib.uuid4())
        self.by_hand(DESK, unread, str(uuidlib.uuid4()))
        self.assertFalse(self.in_pool(DESK))
        code, out, err = self.notice()
        self.assertEqual((code, out), (0, channels.POOLS_NONE + "\n"), err)
        self.assertEqual(self.notices(DESK), [])


# ------------------------------------------------------------ queued behind the writer's head (acceptance 10)


class Queued(Pools):
    def test_a_writer_that_waits_for_its_head_queues_it_and_the_release_appends_it_once(self):
        self.stopped()
        plain = sminos.writer_id()
        sminos.mark_enrolled(sminos.host_name(), "2026-11-10T00:00:00.000Z")
        sminos.keep_headed(self.chan(DESK), [plain])
        sminos.forget_caches()
        self.assertTrue(sminos.waits_for_head(self.chan(DESK), plain))
        code, out, err = self.notice()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out, sminos.waits_line(self.chan(DESK), plain) + "\n")
        self.assertEqual(self.notices(DESK), [], "nothing in the log yet")
        sminos.release_queued(self.chan(DESK), plain)
        [e] = self.notices(DESK)
        self.assertEqual((e["notice"], e["to"], e["text"]), ("devcloud", "*", TEXT))
        sminos.release_queued(self.chan(DESK), plain)
        self.assertEqual(len(self.notices(DESK)), 1, "a second release adds none")


if __name__ == "__main__":
    unittest.main()
