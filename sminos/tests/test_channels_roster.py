#!/usr/bin/env python3
"""The roster, the listing and the pool (CH1's M5:
docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, the milestone's
"Proves"; Interfaces §5's roster and answers, §2's `channel-env`, §8's
listing and `channel show`).

- The roster: each row its thread's own row in its own project's view, two
  projects spanned, an ended row absent, a row a reader may no longer read
  (a narrowing's notice) absent, an ended thread back in it once reopened;
  read only by the listing and `channel show` (a thread in no channel reads
  none).
- `list`: a bare list from a thread prints its project's section as before,
  the `+N hidden` line under it, then a `# <name>` section for each channel
  of its set by name, stopped and gone members shown there and folded in
  the project's section; two members of one alias labelled apart;
  `--channel` with `--machine`, `--state` and words, in text and in
  `--json`; `--org` ending with a section for each channel that has a
  member and none for one whose last member left; `--json` carrying
  `channels` on a row in one and on no other.
- What became of a request (answers, answer_of): several requests for one
  target, an answer followed by a restatement, an answer left in a project
  the thread then moved from, an unrelated thread's statement naming the
  same channel and id, and a statement with the request's thread stamp
  under a writer that thread never had, neither taken; a request whose id
  another writer used first shown as not carried out; `channel show` with
  each of applied, refused and pending, an expired request not shown.
- The pool: its counts, a machine added and removed by hand, and an env
  event from a writer no longer in the roster, one whose thread id is
  another thread's and one with none, each ignored; `channel env` refused
  before anything is written without the capability, from a terminal, from
  a thread not in the channel and for a machine the org does not list.

The same verbs through the launcher are test-channels.sh's.
Hermetic: test_channels_requests.Requests (test_threads.Machine, the machine
cut over to an endpoint that is never run, its kept welcome listing
`channels`); another machine's members are its writers' events in a hub
project's log, as an import leaves them.
Run: python3 -B sminos/tests/test_channels_roster.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import glob
import json
import os
import sys
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_channels_requests import O, Requests  # noqa: E402
from test_channels_store import DESK, HUB, LOBBY, ROOM, sminos, threads  # noqa: E402
import sminos_audience as audience  # noqa: E402
import sminos_channels as channels  # noqa: E402

APP = "7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d"   # a hub project (version 4)


def logs(home):
    """Every log file under every project here, with its bytes: what a refusal must leave as it was."""
    out = {}
    for path in glob.glob(os.path.join(home, "projects", "*", "log", "*.jsonl")):
        with open(path, "rb") as f:
            out[path] = f.read()
    return out


class Roster(Requests):
    """Requests, with a hub project `app` beside the machine's own, and another machine's members staged in
    its log as an import leaves them."""

    def setUp(self):
        super().setUp()
        self.app_root = os.path.join(self.home, "app")
        os.makedirs(self.app_root)
        with open(os.path.join(self.app_root, ".smns"), "w") as f:
            json.dump({"project": APP, "name": "app", "hub": {"org": HUB["org"]}}, f)
        self.app = self.project_of(self.app_root)
        self.assertEqual(self.app.id, APP)

    def far(self, alias, state="idle", chans=(DESK,), machine="beta", p=None, rev=None):
        """Another machine's thread, a member of `p` (app) by its own writer's events there: (thread, session,
        writer)."""
        p = p or self.app
        sid, tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        w = "%s/%s" % (machine, sid)
        sminos.log_append(p, w, "joined", session=sid, alias=alias, name_source="user", machine=machine, cwd="/w",
                          worktree="", role="", seat="", by="", session_kind="interactive", thread=tid,
                          **({"policyRev": rev} if rev else {}))
        if state:
            sminos.log_append(p, w, "state", session=sid, state=state, machine=machine)
        if chans is not None:
            self.state(p, w, sid, tid, list(chans))
        sminos.forget_caches()
        return tid, sid, w

    def state(self, p, w, sid, tid, chans, **more):
        """A statement under `w`, as its machine writes one."""
        e = sminos.log_append(p, w, "channels", session=sid, thread=tid, op=os.urandom(8).hex(), channels=chans,
                              **more)
        sminos.forget_caches()
        return e

    def placed(self, tid, sid, *cids):
        for cid in cids:
            self.assertEqual(channels.change(tid, cid, "add", sid).state, "applied")
        sminos.forget_caches()

    def as_session(self, sid, *argv, cwd=None):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            return self.cli(*argv, cwd=cwd)

    def sessions_of(self, cid):
        sminos.forget_caches()
        return [(p.id, m.session) for p, m in channels.roster(self.chan(cid))]

    def org(self, *machines):
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "org.json"), {
            "projects": [], "machines": [{"name": n} for n in machines], "at": sminos.now(ms=True)})
        sminos.forget_caches()


# ------------------------------------------------------------ the roster (§5)


class Rows(Roster):
    def test_a_row_is_the_threads_own_row_in_its_own_project_across_projects(self):
        tid, sid, _ = self.human()                       # in the machine's project
        here_t, here_s, _ = self.human(root=self.app_root)   # in app
        self.placed(tid, sid, DESK)
        self.placed(here_t, here_s, DESK, LOBBY)
        far_t, far_s, _ = self.far("faraway", state="stopped")
        self.far("gone-off", chans=(LOBBY,))
        rows = channels.rosters()
        self.assertEqual(sorted((p.id, m.session) for p, m in rows[DESK]),
                         sorted([(self.p.id, sid), (APP, here_s), (APP, far_s)]), "each row in its own project")
        self.assertEqual({m.state for p, m in rows[DESK] if m.session == far_s}, {"stopped"}, "a stopped one there")
        self.assertNotIn(ROOM, rows, "a channel no row states has no roster")
        self.assertEqual([m.alias for _, m in channels.roster(self.chan(DESK))],
                         sorted(m.alias for _, m in rows[DESK]), "by alias")
        self.assertEqual(set(self.sessions_of(LOBBY)), {(APP, here_s), (APP, self.far_sid_of("gone-off"))})

    def far_sid_of(self, alias):
        sminos.forget_caches()
        return next(m.session for m in sminos.view_of(self.app).members if m.alias == alias)

    def test_an_ended_row_is_absent_and_a_row_the_reader_may_no_longer_read_leaves(self):
        far_t, far_s, w = self.far("faraway", rev=1)
        gone_t, gone_s, gw = self.far("retiring")
        self.assertEqual({s for _, s in self.sessions_of(DESK)}, {far_s, gone_s})
        sminos.log_append(self.app, gw, "retired", session=gone_s, reason="retire", by="", thread=gone_t)
        sminos.forget_caches()
        self.assertEqual({s for _, s in self.sessions_of(DESK)}, {far_s}, "an ended thread is in no roster")
        # It went private: the hub serves the notice to the readers its change withdrew, at a policyRev past the
        # snapshot this reader holds; it is none of the project's members to this reader, nor of the roster.
        sminos.log_append(self.app, w, "unlisted", session=far_s, policyRev=2)
        sminos.forget_caches()
        self.assertEqual(self.sessions_of(DESK), [], "a thread this reader may no longer read is absent")

    def test_an_ended_thread_leaves_the_roster_and_is_back_in_it_reopened(self):
        tid, sid, proc = self.human()
        self.placed(tid, sid, DESK)
        self.assertEqual(self.sessions_of(DESK), [(self.p.id, sid)])
        self.ended_by_its_process(sid, proc)
        self.assertTrue(threads.record_ended(threads.get(tid)))
        self.assertEqual(self.sessions_of(DESK), [], "ended: out of the roster")
        self.assertEqual(threads.get(tid)["channels"], [DESK], "its record keeps the set")
        self.session(sid=sid)   # its human reopens it
        self.reconcile()
        self.assertFalse(threads.record_ended(threads.get(tid)))
        self.assertEqual(self.sessions_of(DESK), [(self.p.id, sid)], "reopened, in the channels it was in")

    def test_the_roster_is_kept_for_the_views_it_read_and_read_again_once_one_is_dropped(self):
        tid, sid, _ = self.human()
        self.placed(tid, sid, DESK)
        sminos.forget_caches()
        first = channels.rosters()
        self.assertIs(channels.rosters(), first, "the same views, the same roster")
        channels.change(tid, DESK, "remove", sid)   # a lifecycle append drops that project's view
        self.assertNotIn(DESK, channels.rosters())


# ------------------------------------------------------------ list (§8)


class Listing(Roster):
    def caller(self):
        """A live thread its human opened in app, in DESK and LOBBY (LOBBY first), and app's other rows."""
        tid, sid, _ = self.human(root=self.app_root)
        self.placed(tid, sid, LOBBY, DESK)
        self.far("stopper", state="stopped")
        self.far("ghost", state="gone", machine="gamma")
        return tid, sid

    def test_a_bare_list_prints_its_project_then_each_channel_by_name(self):
        tid, sid = self.caller()
        _, mine, _ = self.human()   # in the machine's project, in DESK
        self.placed(threads.thread_of(mine)["thread"], mine, DESK)
        code, out = self.as_session(sid, "list", cwd=self.app_root)
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        self.assertEqual(lines[0], "app", out)
        hidden = next(i for i, l in enumerate(lines) if l.startswith("+2 hidden"))
        desk, lobby = lines.index("# desk"), lines.index("# lobby")
        you = next(i for i, l in enumerate(lines) if l.startswith("you: "))
        self.assertLess(hidden, desk, "the project's +N hidden line stays directly under its rows")
        self.assertTrue(all(not l.startswith("#") for l in lines[1:hidden]))
        self.assertLess(desk, lobby, "by name, not by the order added")
        self.assertLess(lobby, you)
        project_rows = "\n".join(lines[1:hidden])
        self.assertNotIn("stopper", project_rows, "folded in the project's section")
        section = lines[desk + 1:lobby]
        self.assertEqual(len(section), 4, out)
        for alias, word in (("stopper", "stopped"), ("ghost", "gone")):
            row = next(l for l in section if alias in l)
            self.assertIn(word, row, "shown in the channel's section")
            self.assertIn("app", row.split(), "with its project's column")
        self.assertIn(sminos.host_name(), "\n".join(section))
        mine_row = next(l for l in section if mine[:8] in l)
        self.assertIn(" %s " % self.p.name, mine_row, "a row of another project, with its project")
        self.assertEqual([l for l in lines[lobby + 1:you] if l.strip()], [lines[lobby + 1]], "lobby: the caller")

    def test_a_thread_in_no_channel_reads_no_roster_and_prints_what_it_printed(self):
        tid, sid, _ = self.human(root=self.app_root)
        self.far("stopper", state="stopped", chans=())
        _, before = self.as_session(sid, "list", cwd=self.app_root)
        with mock.patch.object(channels, "rosters", side_effect=AssertionError("a roster was read")), \
                mock.patch.object(channels, "roster", side_effect=AssertionError("a roster was read")):
            code, out = self.as_session(sid, "list", cwd=self.app_root)
            self.assertEqual(code, 0, out)
            self.assertEqual(out, before)
            code, out = self.as_session(sid, "list", "--json", cwd=self.app_root)
        self.assertEqual(code, 0, out)
        self.assertTrue(all("channels" not in r for r in json.loads(out)), "no row carries the key")
        self.assertFalse([l for l in before.splitlines() if l.startswith("#")], "no section")

    def test_two_members_of_one_alias_are_labelled_apart(self):
        _, a, _ = self.far("twin")
        _, b, _ = self.far("twin", machine="gamma")
        code, out = self.cli("channel", "show", "desk")
        self.assertEqual(code, 0, out)
        self.assertIn("twin [%s]" % a[:8], out)
        self.assertIn("twin [%s]" % b[:8], out)

    def test_channel_filters_with_machine_state_and_words(self):
        tid, sid = self.caller()
        far_t, far_s, w = self.far("seeker", machine="beta")
        sminos.log_append(self.app, w, "status", session=far_s, text="hunting the needle")
        sminos.forget_caches()
        code, out = self.cli("list", "--channel", "desk")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines()[0], "# desk")
        for alias in ("stopper", "ghost", "seeker", sid[:8]):
            self.assertIn(alias, out, "every row of the roster, none folded")
        self.assertNotIn("hidden", out, "nothing folded, nothing said hidden")
        code, out = self.cli("list", "--channel", "desk", "--machine", "beta")
        self.assertEqual(code, 0, out)
        self.assertIn("seeker", out)
        self.assertIn("stopper", out)
        self.assertNotIn("ghost", out)
        code, out = self.cli("list", "--channel", "desk", "--state", "gone")
        self.assertEqual(code, 0, out)
        self.assertIn("ghost", out)
        self.assertNotIn("stopper", out)
        code, out = self.cli("list", "app", "needle", "--channel", "desk")   # a first word names a project, as today
        self.assertEqual(code, 0, out)
        self.assertIn("seeker", out)
        self.assertNotIn("ghost", out)
        code, out = self.cli("list", "--channel", "desk", "--channel", "lobby")
        self.assertEqual(code, 0, out)
        self.assertLess(out.index("# desk"), out.index("# lobby"), "one section per channel named")
        code, out = self.cli("list", "--channel", "desk", "--channel", "lobby", "--json")
        self.assertEqual(code, 0, out)
        rows = json.loads(out)
        self.assertEqual(sorted(r["session"] for r in rows), sorted(set(r["session"] for r in rows)),
                         "a flat list: a row in both once")
        self.assertIn(sid, [r["session"] for r in rows])
        self.assertTrue(all(DESK in r["channels"] or LOBBY in r["channels"] for r in rows))
        code, out = self.cli("list", "--channel", "nowhere")
        self.assertEqual(code, 4, out)

    def test_org_ends_with_a_section_for_each_channel_with_a_member(self):
        tid, sid, _ = self.human(root=self.app_root)
        self.placed(tid, sid, DESK)
        code, out = self.cli("list", "--org")
        self.assertEqual(code, 0, out)
        self.assertIn("# desk", out)
        self.assertNotIn("# lobby", out, "a channel with no member has no section")
        self.assertNotIn("# room", out)
        self.assertGreater(out.index("# desk"), out.index(sid[:8]), "after today's table")
        code, out = self.cli("list", "--org", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual([r["channels"] for r in json.loads(out) if r["session"] == sid], [[DESK]])
        channels.change(tid, DESK, "remove", sid)
        code, out = self.cli("list", "--org")
        self.assertEqual(code, 0, out)
        self.assertNotIn("# desk", out, "its last member left")
        code, out = self.cli("find", "app")
        self.assertNotIn("#", out.replace(sid[:8], ""))

    def test_list_json_carries_channels_only_on_a_row_in_one(self):
        tid, sid, _ = self.human(root=self.app_root)
        _, other, _ = self.human(root=self.app_root)
        self.placed(tid, sid, DESK, LOBBY)
        code, out = self.cli("list", "--json", cwd=self.app_root)
        self.assertEqual(code, 0, out)
        rows = {r["session"]: r for r in json.loads(out)}
        self.assertEqual(rows[sid]["channels"], [DESK, LOBBY], "in the order added")
        self.assertNotIn("channels", rows[other])
        code, out = self.as_session(sid, "list", "--json", cwd=self.app_root)
        self.assertEqual(len(json.loads(out)), 2, "the sections add nothing to it")


# ------------------------------------------------------------ what became of a request (§5's answers)


class Answers(Roster):
    def test_several_requests_for_one_target_each_answered_by_its_own_statement(self):
        tid, sid, _ = self.human()
        first = self.request(DESK, "add", sid, tid)
        second = self.request(LOBBY, "add", sid, tid)
        third = self.request(DESK, "remove", sid, tid)
        self.carry(DESK)
        self.carry(LOBBY)
        sminos.forget_caches()
        got = {r["id"]: (channels.answer_of(self.chan(c), r) or {}).get("answers") for c, r in
               ((DESK, first), (LOBBY, second), (DESK, third))}
        self.assertEqual(got, {first["id"]: {"channel": DESK, "id": first["id"]},
                               second["id"]: {"channel": LOBBY, "id": second["id"]},
                               third["id"]: {"channel": DESK, "id": third["id"]}})
        self.assertEqual(len(channels.answers()[(DESK, first["id"])]), 1)

    def test_an_answer_stands_after_a_restatement_and_a_move(self):
        tid, sid, _ = self.human()
        e = self.request(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK), {e["id"]: O("applied")})
        self.placed(tid, sid, LOBBY)    # a restatement: the statement in effect no longer answers it
        self.assertNotIn("answers", self.statements(sid)[-1])
        sminos.forget_caches()
        self.assertEqual(channels.answer_of(self.chan(DESK), e)["result"], "applied")
        code, out = self.as_session(sid, "join", "app")
        self.assertEqual(code, 0, out)
        self.reconcile(self.app)
        sminos.forget_caches()
        self.assertFalse(threads.member(self.own(sid)), "it left the project its answer lies in")
        a = channels.answer_of(self.chan(DESK), e)
        self.assertIsNotNone(a, "an answer left in a project the thread moved from")
        self.assertEqual(a["writer"], sminos.writer_id(sid))
        code, out = self.cli("channel", "show", "desk")
        self.assertRegex(out, r"add +%s#%s +by .+ +applied" % (r"\S+", sid[:8]))

    def test_neither_another_threads_statement_nor_the_stamp_under_another_writer_answers(self):
        tid, sid, _ = self.human()
        e = self.remote(DESK, "add", sid, tid)   # pending: the endpoint's word
        self.assertEqual(self.carry(DESK), {e["id"]: O("pending", "endpoint")})
        answer = {"answers": {"channel": DESK, "id": e["id"]}, "result": "applied"}
        other_t, other_s, ow = self.far("bystander", chans=())
        self.state(self.app, ow, other_s, other_t, [DESK], **answer)             # its own thread's stamp
        forger_t, forger_s, fw = self.far("forger", chans=())
        self.state(self.app, fw, forger_s, tid, [DESK], **answer)                # the target's stamp, its writer
        self.assertEqual(len(channels.answers()[(DESK, e["id"])]), 2, "both are in the index")
        self.assertIsNone(channels.answer_of(self.chan(DESK), e), "neither answers the request")
        code, out = self.cli("channel", "show", "desk", "--json")
        self.assertEqual([r["state"] for r in json.loads(out)["requests"]], ["pending"])
        self.carry(DESK, words=self.words(DESK, e, "deliver", sid))
        sminos.forget_caches()
        self.assertEqual(channels.answer_of(self.chan(DESK), e)["writer"], sminos.writer_id(sid))

    def test_a_request_under_an_id_another_writer_used_first_reads_not_carried_out(self):
        tid, sid, _, other = self.two()
        self.request(DESK, "add", sid, tid, rid="same-id")
        self.request(DESK, "remove", sid, tid, writer=sminos.writer_id(other), rid="same-id")
        self.carry(DESK)
        code, out = self.cli("channel", "show", "desk", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual([(r["op"], r["state"]) for r in json.loads(out)["requests"]],
                         [("add", "applied"), ("remove", "duplicate")])
        code, out = self.cli("channel", "show", "desk")
        self.assertIn("not carried out: another request in this channel used its id first", out)

    def test_show_prints_the_roster_across_projects_each_outcome_and_the_pool(self):
        tid, sid, _ = self.human()
        here_t, here_s, _ = self.human(root=self.app_root)
        self.placed(here_t, here_s, DESK)
        applied = self.request(DESK, "add", sid, tid)
        refused_t, refused_s, _ = self.human()
        refused = self.remote(DESK, "add", refused_s, refused_t)
        pending_t, pending_s, _ = self.human()
        pending = self.remote(DESK, "add", pending_s, pending_t)
        far_t, far_s, _ = self.far("faraway", chans=())
        elsewhere = self.request(DESK, "add", far_s, far_t)
        self.request(DESK, "add", pending_s, pending_t, ts="2026-11-01T00:00:00.000Z")   # expired: not shown
        self.carry(DESK, words=self.words(DESK, refused, "refuse", refused_s))
        code, out = self.cli("channel", "show", "desk")
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        self.assertEqual(lines[0], "# desk  %s" % DESK)
        self.assertEqual([l for l in lines if not l.startswith(" ")], ["# desk  %s" % DESK, "members", "requests",
                                                                        "pool"])
        members = lines[lines.index("members") + 1:lines.index("requests")]
        self.assertEqual(len(members), 2, out)
        self.assertTrue(any(self.p.name in l.split() and sid[:8] in l for l in members), out)
        self.assertTrue(any("app" in l.split() and here_s[:8] in l for l in members), out)
        requests = lines[lines.index("requests") + 1:lines.index("pool")]
        self.assertEqual(len(requests), 4, "the expired one is not shown")
        words = {r: next(l for l in requests if s[:8] in l) for r, s in
                 (("applied", sid), ("refused", refused_s), ("pending", pending_s), ("elsewhere", far_s))}
        self.assertTrue(words["applied"].endswith("applied"), (words, out))
        self.assertTrue(words["refused"].endswith("refused: its machine does not let you message it"), words)
        self.assertIn("pending on %s since %s" % (sminos.host_name(), pending["ts"][:19]), words["pending"])
        self.assertIn("pending on beta since %s" % elsewhere["ts"][:19], words["elsewhere"])
        self.assertEqual(lines[lines.index("pool") + 1:], ["  %s  2 live, 0 stopped" % sminos.host_name()])
        code, out = self.cli("channel", "show", "desk", "--json")
        self.assertEqual(code, 0, out)
        shown = json.loads(out)
        self.assertEqual((shown["id"], shown["name"]), (DESK, "desk"))
        self.assertEqual(sorted((m["project"], m["session"]) for m in shown["members"]),
                         sorted([(self.p.name, sid), ("app", here_s)]))
        self.assertEqual([(r["id"], r["state"], r["reason"], r["machine"]) for r in shown["requests"]],
                         [(applied["id"], "applied", None, None), (refused["id"], "refused", "not-reachable", None),
                          (pending["id"], "pending", None, sminos.host_name()),
                          (elsewhere["id"], "pending", None, "beta")])
        self.assertEqual(set(shown["requests"][0]), {"id", "op", "thread", "session", "target", "by", "ts", "state",
                                                     "reason", "machine"})
        self.assertEqual(shown["pool"], [{"machine": sminos.host_name(), "live": 2, "stopped": 0, "by_hand": False}])
        code, out = self.cli("channel", "show", "room")
        self.assertEqual(code, 0, out)
        self.assertIn("members\n  (none)\nrequests\n  (none)\npool\n  (none)", out)
        code, out = self.cli("channel", "show", "app")
        self.assertEqual(code, 4, out)


# ------------------------------------------------------------ the pool and channel env (§2, §8)


class Pool(Roster):
    def setUp(self):
        super().setUp()
        self.org(sminos.host_name(), "beta", "gamma", "delta", "epsilon")

    def pool(self):
        sminos.forget_caches()
        return [(r["machine"], r["live"], r["stopped"], r["by_hand"]) for r in channels.pool(self.chan(DESK))]

    def test_counts_and_a_machine_added_and_removed_by_hand(self):
        tid, sid, _ = self.human(root=self.app_root)
        self.placed(tid, sid, DESK)
        self.far("one", machine="beta")
        self.far("two", state="stopped", machine="beta")
        self.far("three", state="gone", machine="gamma")
        self.far("waiter", state="waiting", machine="gamma")
        host = sminos.host_name()
        self.assertEqual(self.pool(), [("beta", 1, 1, False), ("gamma", 1, 1, False), (host, 1, 0, False)])
        code, out = self.as_session(sid, "channel", "env", "add", "desk", "delta", cwd=self.app_root)
        self.assertEqual(code, 0, out)
        [env] = [e for e in sminos.view_of(self.chan(DESK)).events if e["kind"] == "channel-env"]
        self.assertEqual({k: env[k] for k in ("op", "machine", "thread")}, {"op": "add", "machine": "delta",
                                                                           "thread": tid})
        self.assertEqual(env["writer"], sminos.own_stream(self.chan(DESK), sid)[0], "its own stream there")
        self.assertEqual(self.pool(), [("beta", 1, 1, False), ("delta", 0, 0, True), ("gamma", 1, 1, False),
                                       (host, 1, 0, False)])
        code, out = self.cli("channel", "show", "desk")
        self.assertIn("  delta  0 live, 0 stopped, added by hand", out)
        self.as_session(sid, "channel", "env", "add", "desk", "beta", cwd=self.app_root)
        self.as_session(sid, "channel", "env", "remove", "desk", "delta", cwd=self.app_root)
        self.assertEqual(self.pool(), [("beta", 1, 1, True), ("gamma", 1, 1, False), (host, 1, 0, False)])

    def test_an_env_event_whose_writer_left_names_another_thread_or_none_is_ignored(self):
        tid, sid, _ = self.human(root=self.app_root)
        self.placed(tid, sid, DESK)
        left_t, left_s, left_w = self.far("leaver", machine="beta")
        other_t, other_s, other_w = self.far("other", machine="gamma")
        c = self.chan(DESK)
        sminos.log_append(c, left_w, "channel-env", op="add", machine="delta", thread=left_t)
        sminos.forget_caches()
        self.assertIn(("delta", 0, 0, True), self.pool(), "honoured while its writer is in the roster")
        self.state(self.app, left_w, left_s, left_t, [])   # it left the channel
        self.assertNotIn("delta", [m for m, *_ in self.pool()], "its writer no longer in the roster")
        sminos.log_append(c, other_w, "channel-env", op="add", machine="epsilon", thread=tid)   # another's thread
        sminos.log_append(c, other_w, "channel-env", op="add", machine="epsilon")              # none
        sminos.log_append(c, other_w, "channel-env", op="add", machine="epsilon", thread="")
        sminos.forget_caches()
        self.assertNotIn("epsilon", [m for m, *_ in self.pool()], "each ignored")

    def test_env_is_refused_before_anything_is_written(self):
        tid, sid, _ = self.human(root=self.app_root)
        self.placed(tid, sid, DESK)
        _, outsider, _ = self.human(root=self.app_root)
        before = logs(os.environ["SMINOS_HOME"])
        cases = {
            "a machine the org does not list": (sid, ("add", "desk", "zeta"), 1, "zeta"),
            "from a thread not in the channel": (outsider, ("add", "desk", "beta"), 1, "is not in desk"),
            "from a terminal": (None, ("add", "desk", "beta"), 1, "from a session"),
            "an unknown channel": (sid, ("add", "nowhere", "beta"), 4, "nowhere"),
        }
        for why, (who, argv, want, words) in cases.items():
            with self.subTest(why):
                code, out = (self.as_session(who, "channel", "env", *argv, cwd=self.app_root) if who
                             else self.cli("channel", "env", *argv, cwd=self.app_root))
                self.assertEqual(code, want, out)
                self.assertIn(words, out)
                if want == 1:
                    self.assertIn("nothing was written", out)
        audience.keep_capabilities([])
        sminos.forget_caches()
        code, out = self.as_session(sid, "channel", "env", "add", "desk", "beta", cwd=self.app_root)
        self.assertEqual(code, 1, out)
        self.assertIn(channels.CAPABILITY_REFUSAL, out)
        self.assertEqual(logs(os.environ["SMINOS_HOME"]), before, "no log file changed")
        code, out = self.cli("channel", "show", "desk")
        self.assertEqual(code, 0, "show is a read: no capability is needed")


if __name__ == "__main__":
    unittest.main()
