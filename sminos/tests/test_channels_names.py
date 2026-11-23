#!/usr/bin/env python3
"""Names through a channel (CH2's M1:
docs/doperpowers/plans/2026-11-22-sminos-channels-ch2.md, the milestone's
"Proves"; Interfaces §1, and §2's sentences for a verb's target).

- A verb's target named through a channel (`<channel>/<alias>`), the
  channel by its id, its `name#short` and its name, for a seat of this
  machine, a thread its human opened here and a thread of another machine:
  `charge`, `status`, `who --thread` and `retire` write where they write
  today, in the thread's own project, the channel's log left byte for byte
  as it was; a name a project and a channel both answer refused by
  `ambiguous_name` at a verb and at a tag.
- A bare `@alias` (B3): one answer in the project, one in a channel the
  sender shares (written in that thread's project, with `from_project` and
  the sender's copy), one in each (refused, each `alias#short`), two in two
  channels, one thread in two shared channels (once), and one in a channel
  the sender is not in (today's refusal, listing it elsewhere); a sender in
  no channel reads no roster.
- A name in id form through a channel, every row of §1's table: a thread's
  id (and its first eight) whose session has since become another thread's,
  a session's id one thread has had, a session's id two threads have had,
  a session whose one episode is unstamped with no statement, a seat made
  again over a purged seat's session, an ended seat, a thread that moved
  projects (in the channel there, and out of it), a thread that left the
  channel (`out`: a verb's target refused), a thread's id never in the
  channel, and one whose only statement of the channel never took effect.
- The readers behind it: `thread_of_row` (a stamp, an older copy's
  unstamped row read by its statement, a stamp and a statement that
  disagree), `claimants`, `once_in` and `shared_rows`.

The same verbs through the launcher are test-channels.sh's.
Hermetic: test_channels_roster.Roster (the machine cut over to an endpoint
that is never run); another machine's threads are its writers' events in a
project's log, as an import leaves them.
Run: python3 -B sminos/tests/test_channels_names.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import glob
import io
import json
import os
import sys
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_channels_roster import APP, Roster  # noqa: E402
from test_channels_store import DESK, HUB, LOBBY, sminos, threads  # noqa: E402
import sminos_channels as channels  # noqa: E402

DESK_SHORT = "desk#%s" % DESK[:8]


def refused(fn, *a, **k):
    """(exit code, stderr) of a call that must exit."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            fn(*a, **k)
        except SystemExit as e:
            return e.code, err.getvalue()
    raise AssertionError("did not exit: %r" % (a,))


class Names(Roster):
    def channel_bytes(self, cid=DESK):
        """Every file under the channel's home, with its bytes."""
        out = {}
        for path in glob.glob(os.path.join(os.environ["SMINOS_HOME"], "projects", cid, "**", "*"), recursive=True):
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    out[path] = f.read()
        return out

    def named(self, sid, root=None, alias="worker"):
        """A live session its human opened under the engine's name `alias`, joined on sight: (thread, session)."""
        sid_, proc = self.session(root=root, sid=sid, name=alias)
        self.reconcile(self.project_of(root) if root else None)
        return threads.thread_of(sid_)["thread"], sid_

    def joined(self, p, w, sid, alias, tid=None, **more):
        e = sminos.log_append(p, w, "joined", session=sid, alias=alias, name_source="user", machine=w.split("/")[0],
                              cwd="/w", worktree="", role="", seat=more.pop("seat", ""), by="",
                              session_kind="interactive", **({"thread": tid} if tid else {}), **more)
        time.sleep(0.002)
        sminos.forget_caches()
        return e

    def retired(self, p, w, sid, reason, **more):
        e, = sminos.log_append_batch(p, w, [{"kind": "retired", "session": sid, "reason": reason, "by": "", **more}],
                                     skip_src=False)
        time.sleep(0.002)
        sminos.forget_caches()
        return e

    def stated(self, p, w, sid, tid, chans):
        time.sleep(0.002)
        return self.state(p, w, sid, tid, list(chans))

    def alias_of(self, sid, p=None):
        sminos.forget_caches()
        return next(m.alias for m in sminos.view_of(p or self.p).members if m.session == sid)

    def reach(self, name, short="", cid=DESK):
        sminos.forget_caches()
        where, p, m = channels.reach_in(self.chan(cid), name, short)
        return where, (p.id if p else None), (m.session if m else None)


# ------------------------------------------------------------ a verb's target (find_target)


class Verbs(Names):
    def test_a_verb_names_each_kind_of_thread_through_the_channel_by_each_of_its_names(self):
        tid, sid = self.named(None, alias="minder")             # its human opened it here, in the machine's project
        self.placed(tid, sid, DESK)
        stid, ssid, _ = self.seat("keeper")                     # a seat of this machine
        self.placed(stid, ssid, DESK)
        ftid, fsid, fw = self.far("faraway")                    # another machine's, in app
        before = self.channel_bytes()
        for q in ("desk", DESK, DESK_SHORT):
            code, out = self.cli("charge", "%s/minder" % q, "minding via %s" % q)
            self.assertEqual(code, 0, (q, out))
            code, out = self.cli("status", "%s/keeper" % q, "keeping via %s" % q)
            self.assertEqual(code, 0, (q, out))
            self.assertIn("g/keeper now: keeping via %s" % q, out, "a seat's line, as for g/keeper")
            code, out = self.cli("charge", "%s/faraway" % q, "far via %s" % q)
            self.assertEqual(code, 0, (q, out))
            code, out = self.cli("who", "--thread", "%s/faraway" % q)
            self.assertEqual(code, 0, (q, out))
        sminos.forget_caches()
        lines = [e["text"] for e in sminos.log_read(self.p) if e["kind"] == "in-charge" and e["session"] == sid]
        self.assertEqual(lines, ["minding via %s" % q for q in ("desk", DESK, DESK_SHORT)], "in its own project")
        now = [e["text"] for e in sminos.log_read(self.p) if e["kind"] == "status" and e["session"] == ssid]
        self.assertEqual(now, ["keeping via %s" % q for q in ("desk", DESK, DESK_SHORT)])
        far = [e["text"] for e in sminos.log_read(self.app) if e["kind"] == "in-charge" and e["session"] == fsid]
        self.assertEqual(far, ["far via %s" % q for q in ("desk", DESK, DESK_SHORT)], "in app, its own project")
        self.assertEqual(self.channel_bytes(), before, "nothing in the channel's home")

    def test_retire_through_the_channel_retires_in_its_own_project_and_leaves_the_channels_log(self):
        tid, sid = self.named(None, alias="minder")
        self.placed(tid, sid, DESK)
        before = self.channel_bytes()
        code, out = self.cli("retire", "desk/minder")
        self.assertEqual(code, 0, out)
        self.assertIn("retired", [e["kind"] for e in self.own(sid)], "its retirement in its own project's log")
        self.assertEqual(self.channel_bytes(), before, "the channel's log byte for byte")

    def test_a_name_a_project_and_a_channel_both_answer_is_the_one_refusal_at_a_verb_and_a_tag(self):
        self.far("faraway")
        sminos.register_if_absent(sminos.make_project(channels.mint_channel_id(), "app", "", "", HUB))
        sminos.forget_caches()
        code, out = self.cli("charge", "app/faraway", "x")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("ambiguous name 'app'", out)
        code, out = self.cli("say", "@app/faraway hello")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("ambiguous name 'app'", out)

    def test_no_member_of_that_name_is_refused_naming_where_it_answers(self):
        self.far("faraway", chans=(LOBBY,))
        code, out = self.cli("charge", "desk/faraway", "x")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        far = next(m for m in sminos.view_of(self.app).members if m.alias == "faraway")
        self.assertIn("no member faraway in channel desk; elsewhere: app/faraway#%s" % far.short, out)

    def test_a_thread_that_left_the_channel_is_refused_as_a_verbs_target(self):
        tid, sid, w = self.far("leaver")
        self.stated(self.app, w, sid, tid, [])
        code, out = self.cli("charge", "desk/%s" % tid, "x")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("'desk/%s' names a thread through desk, which it is not in now: name it by its own name "
                      "(leaver#%s or %s)" % (tid, sid[:8], sid[:8]), out)

    def test_an_ended_seat_is_refused_as_a_verbs_target_and_said_unnamed(self):
        sid = str(uuidlib.uuid4())
        w = "beta/" + sid
        self.joined(self.app, w, sid, "olden", sid, seat=sid)
        self.stated(self.app, w, sid, sid, [DESK])
        self.retired(self.app, w, sid, "retire", thread=sid)
        self.assertEqual(self.reach(sid), ("out", None, None), "it was in the channel and has no row now")
        code, out = self.cli("status", "desk/%s" % sid, "x")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("names a thread through desk, which it is not in now: name it by its own name "
                      "(<alias>#<short> or <short>)", out)


# ------------------------------------------------------------ a bare @alias through a shared channel (B3)


class Bare(Names):
    def sender(self, *chans):
        tid, sid = self.named(None, alias="sender")
        if chans:
            self.placed(tid, sid, *chans)
        return tid, sid

    def say(self, sid, text):
        code, out = self.as_session(sid, "say", text)
        sminos.forget_caches()
        return code, out

    def says(self, p):
        sminos.forget_caches()
        return [e for e in sminos.log_read(p) if e["kind"] == "say"]

    def test_one_answer_in_a_shared_channel_reaches_it_in_its_own_project(self):
        _, sid = self.sender(DESK)
        ftid, fsid, _ = self.far("helper")
        before = self.channel_bytes()
        code, out = self.say(sid, "@helper the schema changed")
        self.assertEqual(code, 0, out)
        self.assertIn("recorded", out)
        e, = self.says(self.app)
        self.assertEqual([r["session"] for r in e["to"]], [fsid])
        self.assertEqual(e["from_project"], self.p.id, "a message to another project, as today")
        copy, = self.says(self.p)
        self.assertEqual(copy["copy"], "%s:%s:%d" % (APP, e["writer"], e["seq"]), "the sender's copy names it")
        self.assertEqual(self.channel_bytes(), before, "nothing in the channel's home")

    def test_one_answer_in_the_project_is_todays(self):
        _, sid = self.sender(DESK)
        _, mate = self.named(None, alias="mate")
        self.far("other", chans=(DESK,))
        code, out = self.say(sid, "@mate hello")
        self.assertEqual(code, 0, out)
        e, = self.says(self.p)
        self.assertEqual(([r["session"] for r in e["to"]], e.get("from_project")), ([mate], None))

    def test_one_in_each_and_two_in_two_channels_are_refused_each_as_alias_short(self):
        _, sid = self.sender(DESK, LOBBY)
        _, twin = self.named(None, alias="twin")
        _, ftwin, _ = self.far("twin")
        code, out = self.say(sid, "@twin hello")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("ambiguous @twin matches: ", out)
        self.assertIn("twin#%s" % twin[:8], out)
        self.assertIn("twin#%s" % ftwin[:8], out)
        _, a, _ = self.far("pair", chans=(DESK,))
        _, b, _ = self.far("pair", chans=(LOBBY,), machine="gamma")
        code, out = self.say(sid, "@pair hello")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("pair#%s" % a[:8], out)
        self.assertIn("pair#%s" % b[:8], out)
        self.assertEqual(self.says(self.p) + self.says(self.app), [], "nothing recorded")

    def test_a_thread_in_two_shared_channels_answers_once(self):
        _, sid = self.sender(DESK, LOBBY)
        _, both, _ = self.far("both", chans=(DESK, LOBBY))
        code, out = self.say(sid, "@both hello")
        self.assertEqual(code, 0, out)
        e, = self.says(self.app)
        self.assertEqual([r["session"] for r in e["to"]], [both])

    def test_one_in_a_channel_the_sender_is_not_in_is_todays_refusal_naming_it_elsewhere(self):
        _, sid = self.sender(DESK)
        _, loner, _ = self.far("loner", chans=(LOBBY,))
        code, out = self.say(sid, "@loner hello")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("no member @loner in project", out)
        self.assertIn("elsewhere: @app/loner#%s" % loner[:8], out)
        self.assertIn("a bare name reaches your project and the channels you are in; @short reaches anyone", out,
                      "the refusal names what a bare name reaches for a sender in a channel (CH2's M10)")

    def test_a_sender_in_no_channel_reads_no_roster(self):
        _, sid = self.sender()
        _, mate = self.named(None, alias="mate")
        self.far("helper")
        with mock.patch.object(channels, "rosters", side_effect=AssertionError("a roster was read")), \
                mock.patch.object(channels, "_sweep", side_effect=AssertionError("a roster was read")):
            code, out = self.say(sid, "@mate hello")
            self.assertEqual(code, 0, out)
            code, out = self.say(sid, "@helper hello")
            self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
            self.assertIn("no member @helper in project", out)
            code, out = self.cli("say", "@helper hello")   # a person at a terminal: no record at all
            self.assertEqual(code, sminos.EXIT_UNKNOWN, out)

    def test_shared_rows_hold_each_thread_once_and_read_nothing_for_a_thread_in_none(self):
        tid, sid = self.sender(DESK, LOBBY)
        _, both, _ = self.far("both", chans=(DESK, LOBBY))
        _, one, _ = self.far("one", chans=(LOBBY,))
        got = sorted(m.session for _, m in channels.shared_rows(sid))
        self.assertEqual(got, sorted([sid, both, one]))
        _, alone = self.named(None, alias="alone")
        with mock.patch.object(channels, "rosters", side_effect=AssertionError("a roster was read")):
            self.assertEqual(channels.shared_rows(alone), [])
            self.assertEqual(channels.shared_rows(""), [])


# ------------------------------------------------------------ a name in id form (§1's table)


class IdForm(Names):
    def handed_and_reused(self):
        """T1 held S1 and went on in S2 (a hand-off); S1 then joined again as another thread, T2. Both in DESK."""
        t1, t2, s1, s2 = (str(uuidlib.uuid4()) for _ in range(4))
        w1, w2 = "beta/" + s1, "beta/" + s2
        self.joined(self.app, w1, s1, "carrier", t1)
        self.stated(self.app, w1, s1, t1, [DESK])
        self.retired(self.app, w1, s1, "continued", to=s2, thread=t1)
        self.joined(self.app, w2, s2, "carrier", t1)
        self.stated(self.app, w2, s2, t1, [DESK])
        self.joined(self.app, w1, s1, "reuser", t2)
        self.stated(self.app, w1, s1, t2, [DESK])
        return t1, t2, s1, s2

    def test_a_threads_id_reaches_it_whatever_session_it_holds_and_a_shared_session_names_no_one(self):
        t1, t2, s1, s2 = self.handed_and_reused()
        self.assertEqual(self.reach(t1), ("in", APP, s2), "by its id: the thread, in the session it holds")
        self.assertEqual(self.reach(t1[:8]), ("in", APP, s2), "by its first eight")
        self.assertEqual(self.reach(t2), ("in", APP, s1))
        self.assertEqual(self.reach(s2), ("in", APP, s2), "a session one thread has had")
        self.assertEqual(channels.claimants(s1), {t1, t2})
        code, err = refused(channels.reach_in, self.chan(DESK), s1)
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("ambiguous %s in desk: the session it names has been more than one thread's: " % s1, err)
        self.assertIn("carrier#%s" % s2[:8], err)
        self.assertIn("reuser#%s" % s1[:8], err)
        self.assertIn("name the one you mean", err)

    def test_a_session_whose_one_episode_is_unstamped_with_no_statement_names_no_one(self):
        sid = str(uuidlib.uuid4())
        self.joined(self.app, "beta/" + sid, sid, "ancient")
        self.assertIsNone(channels.claimants(sid))
        code, err = refused(channels.reach_in, self.chan(DESK), sid)
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("ambiguous %s in desk" % sid, err)

    def test_an_older_copys_unstamped_row_is_its_statements_thread(self):
        sid, tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        w = "beta/" + sid
        self.joined(self.app, w, sid, "older")
        self.stated(self.app, w, sid, tid, [DESK])
        (p, m), = channels.roster(self.chan(DESK))
        self.assertEqual(channels.thread_of_row(p, m), (tid, sid))
        self.assertEqual(channels.claimants(sid), {tid})
        self.assertEqual(self.reach(tid), ("in", APP, sid))
        self.assertEqual(self.reach(sid), ("in", APP, sid))

    def test_a_row_whose_stamp_and_statement_disagree_is_addressed_as_no_thread(self):
        sid, tid, other = (str(uuidlib.uuid4()) for _ in range(3))
        w = "beta/" + sid
        self.joined(self.app, w, sid, "torn", tid)
        self.stated(self.app, w, sid, other, [DESK])
        (p, m), = channels.roster(self.chan(DESK))
        self.assertIsNone(channels.thread_of_row(p, m))
        ftid, fsid, _ = self.far("plain")
        (p, m), = [x for x in channels.roster(self.chan(DESK)) if x[1].session == fsid]
        self.assertEqual(channels.thread_of_row(p, m), (ftid, fsid))

    def test_a_seat_made_again_over_a_purged_seats_session_is_that_thread(self):
        sid = str(uuidlib.uuid4())
        w = "beta/" + sid
        self.joined(self.app, w, sid, "phoenix", sid, seat=sid)
        self.stated(self.app, w, sid, sid, [DESK])
        self.retired(self.app, w, sid, "retire", thread=sid)       # purged
        self.joined(self.app, w, sid, "phoenix", sid, seat=sid)    # made again over the session: the same id
        self.stated(self.app, w, sid, sid, [DESK])
        self.assertEqual(self.reach(sid), ("in", APP, sid))
        self.assertEqual(self.reach(sid[:8]), ("in", APP, sid))

    def test_a_thread_that_moved_projects_is_its_row_where_it_is_now(self):
        sid, tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        w = "beta/" + sid
        self.joined(self.app, w, sid, "mover", tid)
        self.stated(self.app, w, sid, tid, [DESK])
        self.retired(self.app, w, sid, "moved", project=self.p.id, thread=tid)
        self.joined(self.p, w, sid, "mover", tid)
        self.stated(self.p, w, sid, tid, [DESK])
        self.assertEqual(self.reach("mover"), ("in", self.p.id, sid))
        self.assertEqual(self.reach(tid), ("in", self.p.id, sid))
        self.stated(self.p, w, sid, tid, [])
        self.assertEqual(self.reach(tid), ("out", self.p.id, sid), "out of it in the project it moved to")

    def test_a_thread_that_left_is_out_with_its_row_and_by_its_alias_no_member(self):
        tid, sid, w = self.far("leaver")
        self.stated(self.app, w, sid, tid, [])
        self.assertIn(tid, channels.once_in(self.chan(DESK)))
        self.assertEqual(self.reach(tid), ("out", APP, sid))
        self.assertEqual(self.reach(tid[:8]), ("out", APP, sid))
        self.assertEqual(self.reach(sid), ("out", APP, sid), "by the session it has had, the same")
        code, err = refused(channels.reach_in, self.chan(DESK), "leaver")
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("no member leaver in channel desk", err)

    def test_a_threads_id_never_in_the_channel_is_the_unknown_name(self):
        tid, sid, _ = self.far("stranger", chans=(LOBBY,))
        self.assertNotIn(tid, channels.once_in(self.chan(DESK)))
        code, err = refused(channels.reach_in, self.chan(DESK), tid)
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("no member %s in channel desk; elsewhere: app/stranger#%s" % (tid, sid[:8]), err)

    def test_a_statement_that_never_took_effect_proves_nothing(self):
        tid, sid, w = self.far("pretender", chans=None)
        self.stated(self.app, "gamma/" + sid, sid, tid, [DESK])   # another writer's: never in effect
        self.assertNotIn(tid, channels.once_in(self.chan(DESK)))
        self.assertEqual(channels.roster(self.chan(DESK)), [])
        code, err = refused(channels.reach_in, self.chan(DESK), tid)
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("no member %s in channel desk" % tid, err)

    def test_once_in_counts_a_statement_under_a_joined_of_another_thread_for_nothing(self):
        sid, tid, other = (str(uuidlib.uuid4()) for _ in range(3))
        w = "beta/" + sid
        self.joined(self.app, w, sid, "torn", tid)
        self.stated(self.app, w, sid, other, [DESK])
        self.assertEqual(channels.once_in(self.chan(DESK)), set())

    def test_nothing_this_reader_can_read_is_the_unknown_name(self):
        nobody = str(uuidlib.uuid4())
        code, err = refused(channels.reach_in, self.chan(DESK), nobody)
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("no member %s in channel desk" % nobody, err)

    def test_a_local_thread_by_its_id_and_its_sessions_short(self):
        tid, sid = self.named(None, alias="minder")
        self.placed(tid, sid, DESK)
        self.assertEqual(self.reach(tid), ("in", self.p.id, sid))
        self.assertEqual(self.reach(sid[:8]), ("in", self.p.id, sid))
        self.assertEqual(self.reach("minder", sid[:8]), ("in", self.p.id, sid), "alias#short")


# ------------------------------------------------------------ the first review's findings (M1, round 1)


class Review1(Names):
    def batch(self, p, w, events):
        """Events of one writer appended in one take, each with the fields given (a `ts` among them)."""
        got = sminos.log_append_batch(p, w, events, skip_src=False)
        sminos.forget_caches()
        return got

    def test_1_a_bare_alias_takes_the_threads_roster_row_over_its_home_row_mid_refill(self):
        """A refill whose destination half (app) is read before the source's retirement (the sender's project):
        `desk/worker` and a bare `@worker` reach the same row, where the thread is now."""
        _, sid = self.named(None, alias="sender")
        self.placed(threads.thread_of(sid)["thread"], sid, DESK)
        tid, old, new = (str(uuidlib.uuid4()) for _ in range(3))
        self.joined(self.p, "beta/" + old, old, "worker", tid)
        self.stated(self.p, "beta/" + old, old, tid, [DESK])
        self.joined(self.app, "beta/" + new, new, "worker", tid)
        self.stated(self.app, "beta/" + new, new, tid, [DESK])
        self.assertEqual(self.reach("worker"), ("in", APP, new))
        code, out = self.as_session(sid, "say", "@worker the schema changed")
        self.assertEqual(code, 0, out)
        sminos.forget_caches()
        e, = [e for e in sminos.log_read(self.app) if e["kind"] == "say"]
        self.assertEqual([r["session"] for r in e["to"]], [new], "the successor, in its project")
        self.assertEqual([e for e in sminos.log_read(self.p) if e["kind"] == "say" and "copy" not in e], [])

    def test_2_a_statement_is_its_joineds_episodes_whatever_the_clock(self):
        """A statement, its session's retirement and a new unstamped join in one millisecond, in that writer
        order: the statement is the first episode's, and the second, unmarked with none, names no one thread."""
        sid, tid, succ = (str(uuidlib.uuid4()) for _ in range(3))
        w = "beta/" + sid
        self.joined(self.app, w, sid, "handed", tid)
        at = sminos.now(ms=True)
        self.batch(self.app, w, [
            {"kind": "channels", "session": sid, "thread": tid, "op": os.urandom(8).hex(), "channels": [DESK],
             "ts": at},
            {"kind": "retired", "session": sid, "reason": "continued", "to": succ, "by": "", "thread": tid, "ts": at},
            {**self.old_joined(sid, alias="again"), "session": sid, "ts": at}])
        self.joined(self.app, "beta/" + succ, succ, "handed", tid)
        self.stated(self.app, "beta/" + succ, succ, tid, [DESK])
        self.assertIsNone(channels.claimants(sid))
        code, err = refused(channels.reach_in, self.chan(DESK), sid)
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("cannot be told to one thread", err)

    def test_3a_an_older_copys_row_that_left_is_out_with_its_row(self):
        sid, tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        w = "beta/" + sid
        self.joined(self.app, w, sid, "older")
        self.stated(self.app, w, sid, tid, [DESK])
        self.assertEqual(self.reach(tid), ("in", APP, sid))
        self.stated(self.app, w, sid, tid, [])
        self.assertEqual(self.reach(tid), ("out", APP, sid), "readable: its row, by its statement's thread")

    def test_3b_a_stamped_successor_and_its_older_copys_predecessor_are_one_row(self):
        tid, old, new = (str(uuidlib.uuid4()) for _ in range(3))
        self.joined(self.p, "beta/" + old, old, "worker")
        self.stated(self.p, "beta/" + old, old, tid, [DESK])
        self.joined(self.app, "beta/" + new, new, "worker", tid)
        self.stated(self.app, "beta/" + new, new, tid, [DESK])
        self.assertEqual(self.sessions_of(DESK), [(APP, new)], "one thread, one row: the newest")

    def test_4_alias_short_is_the_alias_and_its_current_sessions_prefix_of_any_length(self):
        tid, sid, _ = self.far("faraway")
        self.assertEqual(self.reach("faraway", sid[:9]), ("in", APP, sid), "nine characters")
        self.assertEqual(self.reach("faraway", sid[:3]), ("in", APP, sid), "three")
        for short in (tid[:8], "0" * 8 if not sid.startswith("0") else "f" * 8):
            code, err = refused(channels.reach_in, self.chan(DESK), "faraway", short)
            self.assertEqual(code, sminos.EXIT_UNKNOWN, short)
            self.assertIn("no member faraway#%s in channel desk" % short, err)

    def test_4_a_hex_alias_binds_the_seat_not_its_session(self):
        stid, ssid, _ = self.seat("cafebabe")
        self.placed(stid, ssid, DESK)
        kind, seat, bound = sminos.find_target("desk/cafebabe")
        self.assertEqual((kind, seat["seat_id"], bound), ("seat", stid, ""), "an alias names the seat")
        kind, seat, bound = sminos.find_target("desk/cafebabe#%s" % ssid[:8])
        self.assertEqual((kind, bound), ("seat", ssid), "alias#short binds the session")

    def test_5_thread_of_row_answers_what_its_own_sweep_read_and_reads_nothing_again(self):
        """Round 2: a row keeps what the sweep that produced it read, however many sweeps came after."""
        tid, sid, _ = self.far("faraway")
        (p, m), = channels.roster(self.chan(DESK))
        sminos.forget_caches()
        channels.rosters()   # another sweep: the row above is not its own
        with mock.patch.object(channels, "_sweep", side_effect=AssertionError("swept again")), \
                mock.patch.object(sminos, "view_of", side_effect=AssertionError("a view read again")):
            self.assertEqual(channels.thread_of_row(p, m), (tid, sid))
            self.assertIsNone(channels.thread_of_row(p, sminos.Member(*m)), "a row no sweep produced: none")

    def test_minor_1_a_thread_outside_the_channel_named_by_nine_is_named_where_it_is(self):
        tid, sid, _ = self.far("stranger", chans=(LOBBY,))
        code, err = refused(channels.reach_in, self.chan(DESK), tid[:9])
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("no member %s in channel desk; elsewhere: app/stranger#%s" % (tid[:9], sid[:8]), err)

    def test_a_thread_prefix_two_roster_threads_share_is_refused_naming_both(self):
        t1, t2 = "abcdef01-2345-4000-8000-000000000001", "abcdef01-2345-4000-8000-000000000002"
        s1, s2 = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        for t, s, alias in ((t1, s1, "one"), (t2, s2, "two")):
            self.joined(self.app, "beta/" + s, s, alias, t)
            self.stated(self.app, "beta/" + s, s, t, [DESK])
        code, err = refused(channels.reach_in, self.chan(DESK), "abcdef01-2345")
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("ambiguous abcdef01-2345 in channel desk matches: one#%s, two#%s" % (s1[:8], s2[:8]), err)
        self.assertEqual(self.reach(t2), ("in", APP, s2), "the whole id tells them apart")


class Review2(Names):
    def test_1_a_refill_whose_rows_differ_in_alias_matches_only_where_the_thread_is_now(self):
        """The stale row (the sender's project) held `oldname` before it was renamed `worker`; the successor (app)
        is `helper` and never held either: neither old name reaches it, nothing crashes, and `@helper` does."""
        _, sid = self.named(None, alias="sender")
        self.placed(threads.thread_of(sid)["thread"], sid, DESK)
        tid, old, new = (str(uuidlib.uuid4()) for _ in range(3))
        self.joined(self.p, "beta/" + old, old, "oldname", tid)
        sminos.log_append(self.p, "beta/" + old, "renamed", session=old, alias="worker", name_source="user",
                          thread=tid)
        self.stated(self.p, "beta/" + old, old, tid, [DESK])
        self.joined(self.app, "beta/" + new, new, "helper", tid)
        self.stated(self.app, "beta/" + new, new, tid, [DESK])
        for name in ("oldname", "worker"):
            code, out = self.as_session(sid, "say", "@%s hello" % name)
            self.assertEqual(code, sminos.EXIT_UNKNOWN, (name, out))
            self.assertIn("no member @%s" % name, out)
        code, out = self.as_session(sid, "say", "@helper hello")
        self.assertEqual(code, 0, out)
        sminos.forget_caches()
        e, = [e for e in sminos.log_read(self.app) if e["kind"] == "say"]
        self.assertEqual([r["session"] for r in e["to"]], [new])

    def test_2_a_row_whose_stamp_and_statement_disagree_is_offered_as_no_recipient(self):
        """One valid statement of the channel, then a current one under another thread's id: by the thread's id the
        row is neither in nor out, and nothing is offered."""
        sid, tid, other = (str(uuidlib.uuid4()) for _ in range(3))
        w = "beta/" + sid
        self.joined(self.app, w, sid, "torn", tid)
        self.stated(self.app, w, sid, tid, [DESK])
        self.stated(self.app, w, sid, other, [DESK])
        self.assertIn(tid, channels.once_in(self.chan(DESK)))
        (p, m), = channels.roster(self.chan(DESK))
        self.assertIsNone(channels.thread_of_row(p, m))
        code, err = refused(channels.reach_in, self.chan(DESK), tid)
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertIn("%s: not reached through desk (its row's membership names two threads" % tid, err)
        code, out = self.cli("charge", "desk/%s" % tid, "x")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertNotIn("name it by its own name", out, "no direct recipient offered")

    def test_4_the_projection_and_the_channels_fold_split_episodes_by_one_step(self):
        sid, t1, t2 = (str(uuidlib.uuid4()) for _ in range(3))
        w = "beta/" + sid
        self.joined(self.app, w, sid, "a", t1)
        self.retired(self.app, w, sid, "replaced", thread=t1)
        self.joined(self.app, w, sid, "b")
        self.joined(self.app, w, sid, "c", t2)
        events = sminos.view_of(self.app).events
        real, calls = sminos.episode_step, []

        def counted(*a, **k):
            calls.append(a[1]["session"])
            return real(*a, **k)
        with mock.patch.object(sminos, "episode_step", counted):
            info = sminos._projection(events)
            n = len(calls)
            folded = channels._stated(events)
        self.assertEqual(n, 3, "the projection folds each joined by the step")
        self.assertEqual(len(calls), 6, "and so does the channels' fold")
        self.assertEqual([mark for mark, _ in folded["episodes"][sid]], [ep[1] for ep in info[sid]["episodes"]])


class Frontier(Names):
    """The frontier review's findings on a verb's and a tag's routes through a channel."""

    def torn(self, alias="torn", p=None):
        """A row of another machine in DESK whose `joined` is stamped with one thread and whose statement in effect
        names another: its session."""
        sid, tid, other = (str(uuidlib.uuid4()) for _ in range(3))
        w = "beta/" + sid
        self.joined(p or self.app, w, sid, alias, tid)
        self.stated(p or self.app, w, sid, other, [DESK])
        return sid

    def charges(self, p, sid):
        sminos.forget_caches()
        return [e for e in sminos.log_read(p) if e["kind"] == "in-charge" and e["session"] == sid]

    def test_f9_a_torn_row_named_through_the_channel_by_its_alias_is_no_verbs_target(self):
        sid = self.torn()
        for q in ("desk/torn", "desk/torn#%s" % sid[:8], "%s/torn" % DESK):
            code, out = self.cli("charge", q, "x")
            self.assertEqual(code, sminos.EXIT_UNKNOWN, (q, out))
            self.assertIn("names two threads", out, q)
            self.assertNotIn("name it by its own name", out, "no recipient offered")
            code, out = self.cli("who", "--thread", q)
            self.assertEqual(code, sminos.EXIT_UNKNOWN, (q, out))
        self.assertEqual(self.charges(self.app, sid), [], "nothing written in its project")

    def test_f9_a_bare_tag_reaches_no_torn_row_through_a_shared_channel(self):
        tid, ssid = self.named(None, alias="sender")
        self.placed(tid, ssid, DESK)
        self.torn()
        code, out = self.as_session(ssid, "say", "@torn hello")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("no member @torn in project", out)
        sminos.forget_caches()
        self.assertEqual([e for e in sminos.log_read(self.app) if e["kind"] == "say"], [], "nothing recorded")

    def test_f9_a_torn_row_of_the_senders_own_project_is_still_its_project_member(self):
        """Not a route through the channel: the sender's own project's member, as a sender in no channel reaches
        it."""
        tid, ssid = self.named(None, alias="sender")
        self.placed(tid, ssid, DESK)
        sid = self.torn(p=self.p)
        code, out = self.as_session(ssid, "say", "@torn hello")
        self.assertEqual(code, 0, out)
        sminos.forget_caches()
        e, = [e for e in sminos.log_read(self.p) if e["kind"] == "say"]
        self.assertEqual([r["session"] for r in e["to"]], [sid])

    def test_f14_an_older_copys_unstamped_row_is_its_statements_thread_at_a_verb(self):
        sid, tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        w = "beta/" + sid
        self.joined(self.app, w, sid, "older")
        self.stated(self.app, w, sid, tid, [DESK])
        kind, p, m = sminos.find_target("desk/older")
        self.assertEqual((kind, p.id, m.session, m.thread), ("member", APP, sid, tid))
        code, out = self.cli("who", "--thread", "desk/older")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["thread"], tid)
        t = channels._target("desk/older")
        self.assertEqual((t.thread, t.session, t.refusal), (tid, sid, ""), "channel add takes it as a thread")


class Frontier2(Names):
    """The frontier review's second reading, on wave 1's routes through a channel (G5, G6)."""

    def swapped(self, t1, s1, t2, s2):
        """S1 becomes T2's current session and S2 T1's: the session the name came to is another thread's now."""
        for tid, cur in ((t1, s2), (t2, s1)):
            def mutate(view, raw, cur=cur):
                raw["current"] = cur
                raw["sessions"] = list(dict.fromkeys(raw["sessions"] + [cur]))
                return True
            self.assertTrue(threads._change(tid, mutate))
        sminos.forget_caches()

    def test_g5_retire_purge_through_a_channel_acts_on_the_thread_the_name_resolved(self):
        t1, s1 = self.named(None, alias="victim")
        self.placed(t1, s1, DESK)
        t2, s2 = self.named(None, alias="bystander")
        real = sminos.find_target

        def found_then_moved(q):
            got = real(q)
            if q == "desk/victim":
                self.swapped(t1, s1, t2, s2)   # between the lookup and the verb
            return got
        with mock.patch.object(sminos, "find_target", found_then_moved):
            code, out = self.cli("retire", "desk/victim", "--purge")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("thread %s has no record of this machine with session %s any more" % (t1[:8], s1[:8]), out)
        self.assertIsNotNone(threads.get(t2), "the other thread's record is not purged")
        self.assertIsNotNone(threads.get(t1))

    def test_g5_remove_through_a_channel_acts_on_the_thread_the_name_resolved(self):
        t1, s1 = self.named(None, alias="victim")
        self.placed(t1, s1, DESK)
        t2, s2 = self.named(None, alias="bystander")
        real = sminos.find_target

        def found_then_moved(q):
            got = real(q)
            if q == "desk/victim":
                self.swapped(t1, s1, t2, s2)
            return got
        with mock.patch.object(sminos, "find_target", found_then_moved):
            code, out = self.cli("remove", "desk/victim")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIsNotNone(threads.get(t2), "the other thread's record is not removed")

    def test_g5_channel_add_through_a_channel_names_the_thread_the_name_resolved(self):
        """The same re-resolution in `_target`, which `channel add`, `channel remove` and `channel lead` read."""
        t1, s1 = self.named(None, alias="victim")
        self.placed(t1, s1, DESK)
        t2, s2 = self.named(None, alias="bystander")
        real = sminos.find_target

        def found_then_moved(q):
            got = real(q)
            self.swapped(t1, s1, t2, s2)
            return got
        with mock.patch.object(sminos, "find_target", found_then_moved):
            t = channels._target("desk/victim")
        self.assertEqual((t.thread, t.session), (t1, s2), "the thread named, as its record stands now")
        t = channels._target("victim#%s" % s1[:8])
        self.assertEqual(t.thread, t2, "a project's name is its session's thread now, as at the merge base")

    def test_g5_a_seat_through_a_channel_is_the_seats_thread_at_channel_add(self):
        """Review of wave 2: the seat branch carries the thread resolved too. The seat's session becomes another
        thread's current one after the lookup; `_target` (channel add, remove, lead) still names the seat."""
        stid, ssid, _ = self.seat("keeper")
        self.placed(stid, ssid, DESK)
        t2, s2 = self.named(None, alias="bystander")
        real = sminos.find_target

        def taken(tid, cur):
            def mutate(view, raw):
                raw["current"] = cur
                raw["sessions"] = list(dict.fromkeys(raw["sessions"] + [cur]))
                return True
            self.assertTrue(threads._change(tid, mutate))
            sminos.forget_caches()

        def found_then_moved(q):
            got = real(q)
            taken(t2, ssid)
            return got
        kind, seat, bound = sminos.find_target("desk/keeper#%s" % ssid[:8])
        self.assertEqual((kind, seat["seat_id"], bound, sminos.resolved_thread(seat)), ("seat", stid, ssid, stid),
                         "alias#short still binds the occupant")
        kind, seat, bound = sminos.find_target("desk/keeper")
        self.assertEqual((kind, bound, sminos.resolved_thread(seat)), ("seat", "", stid), "the alias binds the seat")
        with mock.patch.object(sminos, "find_target", found_then_moved):
            t = channels._target("desk/keeper")
        self.assertEqual(t.thread, stid, "the seat named, not the thread its session is current in now")
        kind, seat, bound = sminos.find_target("g/keeper")
        self.assertEqual((kind, seat["seat_id"], sminos.resolved_thread(seat)), ("seat", stid, None),
                         "a project's seat name binds no thread")
        self.assertEqual(channels._target("g/keeper").thread, t2,
                         "and reads its session's current record, as at the merge base")

    def test_g5_a_name_in_its_own_project_is_resolved_by_its_session_as_at_the_merge_base(self):
        """B11: the binding is the channel route's; a project's name hands retire_member no thread."""
        t1, s1 = self.named(None, alias="victim")
        self.placed(t1, s1, DESK)
        seen = []
        with mock.patch.object(sminos, "retire_member", lambda *a, **k: seen.append((a[0].id, k.get("thread_id")))):
            self.assertEqual(self.cli("retire", "victim")[0], 0)
            self.assertEqual(self.cli("retire", "desk/victim")[0], 0)
        self.assertEqual(seen, [(self.p.id, None), (self.p.id, t1)])

    def refilled_over(self, alias_seat, alias_old):
        """A channel peer in app whose thread id S is a session id that an unstamped member of the sender's project
        holds (a refilled seat's first session, back as an older copy's row): S."""
        s, s2 = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        self.joined(self.app, "beta/" + s2, s2, alias_seat, s)
        self.stated(self.app, "beta/" + s2, s2, s, [DESK])
        self.joined(self.p, "beta/" + s, s, alias_old)
        sminos.log_append(self.p, "beta/" + s, "state", session=s, state="idle", machine="beta")
        sminos.forget_caches()
        return s, s2

    def test_g6_a_project_member_whose_session_is_a_channel_peers_thread_id_is_still_reached(self):
        tid, ssid = self.named(None, alias="sender")
        self.placed(tid, ssid, DESK)
        s, _ = self.refilled_over("keeper", "olden")
        code, out = self.as_session(ssid, "say", "@olden hello")
        self.assertEqual(code, 0, out)
        sminos.forget_caches()
        e, = [e for e in sminos.log_read(self.p) if e["kind"] == "say"]
        self.assertEqual([r["session"] for r in e["to"]], [s])

    def test_g6_and_one_alias_both_answer_is_refused_as_ambiguous(self):
        tid, ssid = self.named(None, alias="sender")
        self.placed(tid, ssid, DESK)
        s, s2 = self.refilled_over("twin", "twin")
        code, out = self.as_session(ssid, "say", "@twin hello")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("ambiguous @twin matches: ", out)
        self.assertIn("twin#%s" % s[:8], out)
        self.assertIn("twin#%s" % s2[:8], out)


class Frontier3(Names):
    """The final reading (H3): every verb that resolved a seat through a channel (a ThreadSeat) acts on its
    thread, never on the canonical thread of the seat's session read again."""

    def reused(self):
        """G5's fixture: the seat keeper in DESK and a bystander its human opened; right after the lookup the
        seat's session becomes the bystander's current one. (seat id, seat's session, bystander's thread, a
        find_target that makes the change after it answers.)"""
        stid, ssid, _ = self.seat("keeper")
        self.placed(stid, ssid, DESK)
        t2, _ = self.named(None, alias="bystander")
        real = sminos.find_target

        def found_then_taken(q):
            got = real(q)

            def mutate(view, raw):
                raw["current"] = ssid
                raw["sessions"] = list(dict.fromkeys(raw["sessions"] + [ssid]))
                return True
            self.assertTrue(threads._change(t2, mutate))
            sminos.forget_caches()
            return got
        return stid, ssid, t2, found_then_taken

    def untouched(self, t2, ssid):
        t = threads.get(t2)
        self.assertIsNotNone(t, "the bystander's record is not purged")
        self.assertFalse(threads.record_ended(t), "nor ended")
        self.assertEqual(t["current"], ssid)

    def test_h3_retire_purge_of_a_seat_through_a_channel_never_ends_the_bystander(self):
        stid, ssid, t2, found = self.reused()
        with mock.patch.object(sminos, "find_target", found):
            code, out = self.cli("retire", "desk/keeper", "--purge")
        self.untouched(t2, ssid)
        self.assertEqual(code, 0, out)
        self.assertIsNone(sminos.reload_seat(stid), "the seat named is what was purged")

    def test_h3_remove_of_a_seat_through_a_channel_never_ends_the_bystander(self):
        stid, ssid, t2, found = self.reused()
        with mock.patch.object(sminos, "find_target", found):
            code, out = self.cli("remove", "desk/keeper")
        self.untouched(t2, ssid)
        self.assertEqual(code, 0, out)
        self.assertIsNone(sminos.reload_seat(stid), "the seat named is what was removed")

    def test_h3_retire_of_a_seat_through_a_channel_never_ends_the_bystander(self):
        stid, ssid, t2, found = self.reused()
        with mock.patch.object(sminos, "find_target", found):
            code, out = self.cli("retire", "desk/keeper")
        self.untouched(t2, ssid)
        self.assertEqual(code, 0, out)
        self.assertEqual(sminos.reload_seat(stid)["status"], "retired", "the seat named is what was retired")

    def test_h3_who_thread_of_a_seat_through_a_channel_is_the_seats_thread(self):
        stid, ssid, t2, found = self.reused()
        with mock.patch.object(sminos, "find_target", found):
            code, out = self.cli("who", "--thread", "desk/keeper")
        self.assertEqual(code, 0, out)
        got = json.loads(out.strip().splitlines()[-1])
        self.assertEqual((got["thread"], got["alias"]), (stid, "keeper"))

    def refilled_after(self, q_through):
        """The seat keeper in DESK, refilled with another session right after the lookup of `q_through`: (seat id,
        its first session, the session it holds after, a find_target that refills it after it answers)."""
        stid, ssid, _ = self.seat("keeper")
        self.placed(stid, ssid, DESK)
        new = str(uuidlib.uuid4())
        real = sminos.find_target

        def found_then_refilled(q):
            got = real(q)
            with open(sminos.meta_path(stid)) as f:
                raw = json.load(f)
            raw.update(current=new, sessions=raw["sessions"] + [new])
            sminos.write_json(sminos.meta_path(stid), raw, mode=0o600)
            sminos.forget_caches()
            return got
        return stid, ssid, new, found_then_refilled

    def test_r2_who_thread_of_a_seat_through_a_channel_refilled_after_the_lookup_is_refused(self):
        """Review of the last wave (R2): the thread read afresh and the session from the lookup's snapshot would be
        a target built from two states, the departed session's short handed to devcloud vm owner."""
        stid, ssid, new, found = self.refilled_after("desk/keeper")
        with mock.patch.object(sminos, "find_target", found):
            code, out = self.cli("who", "--thread", "desk/keeper")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertNotIn('"session": "%s"' % ssid, out)
        self.assertIn("name it again", out)

    def test_r2_a_projects_seat_name_refilled_after_the_lookup_is_read_as_at_the_merge_base(self):
        stid, ssid, new, found = self.refilled_after("g/keeper")
        with mock.patch.object(sminos, "find_target", found):
            code, out = self.cli("who", "--thread", "g/keeper")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["session"], ssid, "the lookup's snapshot, as before")

    def test_h3_a_projects_seat_name_reads_its_sessions_canonical_thread_as_at_the_merge_base(self):
        """B11: the binding is the channel route's alone."""
        stid, ssid, t2, found = self.reused()
        with mock.patch.object(sminos, "find_target", found):
            code, out = self.cli("who", "--thread", "g/keeper")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["thread"], t2)
        seen = []
        with mock.patch.object(sminos, "end_and_stop", lambda *a, **k: seen.append(k.get("thread_id"))), \
                mock.patch.object(sminos, "seat_owner_guard", lambda *a, **k: seen.append(k.get("thread_id"))):
            self.cli("retire", "g/keeper")
            self.cli("remove", "g/keeper")
        self.assertEqual(seen, [None] * 4, "no thread handed down for a project's name")


if __name__ == "__main__":
    unittest.main()
