#!/usr/bin/env python3
"""`sminos daemon owed` (O12 M7c): what this machine still owes, per project,
read from what the daemon and the uplink keep on disk — deliveries owed to a
local member not yet made, a person's words not yet settled on a cut-over
machine, and what is owed upstream and not yet taken (this machine's own
events, the settlements and RPC messages kept under daemon/, the host
store's unsent events, the delivery outcomes not yet posted). Events owed to
a closed session are counted on their own line and owe nothing. Bounded, no
message body, exit 0 only when nothing is owed, and read-only: it writes
nothing and takes no lock.

Also the uplink's half: the `taken` vector it keeps in each project's
uplink.json (the hub's `have` for this machine's writers, and each upload
the hub answered or the endpoint's socket took), which is how a process
beside it knows what of this machine's own events went up.

Hermetic: every test has its own HOME and SMINOS_HOME under one temporary
directory.
Run: python3 -B sminos/tests/test_owed.py
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
BASE = tempfile.mkdtemp(prefix="smo.", dir="/tmp")
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import sminos  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_outcomes as outcomes  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

KEY = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode()
S1 = "6e000001-0000-4000-8000-0000000000e1"
S2 = "6e000002-0000-4000-8000-0000000000e2"
S3 = "6e000003-0000-4000-8000-0000000000e3"
DEV = {"kind": "device", "member": "mem-1", "device": "dev-a", "keyId": "k-dev-a"}
SECRET = "the body nobody may print"


class Lane:
    """A Link's lane that keeps what it is sent; a send's continuation is
    told the frames `refuse` names refused (by id), else nothing."""

    def __init__(self):
        self.sent, self.refuse, self.held, self.hold_thens = [], {}, [], False

    def send(self, frames, then=None):
        self.sent += frames
        if then is not None:
            answer = {id(f): self.refuse[f["t"]] for f in frames if f["t"] in self.refuse}
            if self.hold_thens:
                self.held.append(lambda: then(answer))   # the main loop runs it later
            else:
                then(answer)

    def run_held(self):
        held, self.held = self.held, []
        for then in held:
            then()

    def posting(self):
        return False

    def queued(self):
        return 0

    def hold(self, _project):
        return None, []

    def release(self, _project):
        pass

    def close(self):
        pass


class Machine(unittest.TestCase):
    """A fresh installation per test, `testhost` enrolled in org-1 (DX2's
    hub.json); `cut_over` makes it a cut-over one."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"))
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        self.enrol()
        rl10._SAID.update(find=None, revoked=None)

    def enrol(self):
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json"),
                          {"hub": "http://127.0.0.1:9", "org": "org-1", "machine": "testhost", "client_id": "c",
                           "client_secret": "s", "key": KEY, "former": {}, "enrolled": "2026-10-01T00:00:00Z"},
                          mode=0o600)
        sminos.forget_caches()

    def cut_over(self):
        sminos.write_json(rl10.identity_path(), {
            "org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": {},
            "ref": "machine-ref-1", "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z",
            "build": "b"}, mode=0o600)
        sminos.forget_caches()

    def project(self, name, hub=True):
        pid = "6e00%04d-0000-4000-8000-%012d" % (len(name), abs(hash(name)) % 10 ** 12)
        p = sminos.make_project(pid, name, "", "", {"url": "http://127.0.0.1:9", "org": "org-1"} if hub else None)
        sminos.project_path(p, "log")
        sminos.forget_caches()
        return sminos.find_project(pid)

    def member(self, project, sid, alias, machine="testhost"):
        """A session of `machine` joined in the project (its own writer);
        this machine's joined taken by its upstream, as the uplink records."""
        e = sminos.log_append(project, "%s/%s" % (machine, sid), "joined", session=sid, alias=alias,
                              name_source="derived", machine=machine, cwd="/w", session_kind="interactive")
        if machine == "testhost":
            self.took(project, e)

    def retire(self, project, sid, reason="ended"):
        self.took(project, sminos.log_append(project, "testhost/%s" % sid, "retired", session=sid, by="",
                                             reason=reason))

    def took(self, project, e):
        held = self.taken_held(project).get("taken") or {}
        self.taken_state(project, taken={**held, e["writer"]: e["seq"]})

    def taken_path(self, project):
        return os.path.join(project.home, hublog.TAKEN_FILE)

    def taken_held(self, project):
        try:
            return json.loads(Path(self.taken_path(project)).read_text())
        except OSError:
            return {}

    def taken_state(self, project, **d):
        Path(self.taken_path(project)).write_text(json.dumps({**self.taken_held(project), **d}))

    def held(self, project):
        try:
            return json.loads(Path(project.home, sminos.UPLINK_STATE).read_text())
        except OSError:
            return {}

    def arrive(self, project, writer, seq, to, kind="human", signer=DEV, text=SECRET):
        """An event from outside, stored as an arrival over RL10 stores it."""
        e = {"ts": "2026-10-27T01:00:%02d.000Z" % seq, "writer": writer, "seq": seq, "kind": kind,
             "from": "alice", "to": [{"session": s, "alias": "m"} for s in to], "text": text}
        if signer is not None:
            e["verified"] = {"signer": signer}
        self.assertEqual(hublog.append_verbatim(project, e), "appended")
        return e

    def settle(self, project, sid, writer, seq):
        sminos.delivered_settle(project, sid, writer, seq)

    def uplink_state(self, project, **d):
        Path(project.home, sminos.UPLINK_STATE).write_text(json.dumps({**self.held(project), **d}))

    def owed(self):
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "daemon", "owed"],
                             capture_output=True, text=True, timeout=60)
        self.assertNotIn(SECRET, out.stdout + out.stderr, "no message body is ever printed")
        self.assertNotIn("Traceback", out.stderr)
        return out.returncode, out.stdout

    def line(self, out, name):
        got = [x for x in out.splitlines() if x.startswith(name + ": ") and "closed" not in x]
        self.assertEqual(len(got), 1, out)
        return got[0]


class Nothing(Machine):
    def test_nothing_owed_is_exit_0(self):
        p = self.project("quiet")
        self.member(p, S1, "m")
        self.assertEqual(self.owed(), (0, "nothing owed\n"))

    def test_a_project_with_nothing_owed_is_not_printed(self):
        quiet, busy = self.project("quiet"), self.project("busy")
        for p in (quiet, busy):
            self.member(p, S1, "m")
        self.arrive(busy, "hub/mem-1", 1, [S1])
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        self.assertNotIn("quiet", out)


class Deliveries(Machine):
    def test_one_owed_to_a_local_member_then_none(self):
        p = self.project("work")
        self.member(p, S1, "alpha")
        self.arrive(p, "hub/mem-1", 1, [S1])
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        line = self.line(out, "work")
        self.assertIn("deliveries 1 [hub/mem-1:1 → alpha]", line)
        self.assertNotIn("words", line, "a machine not cut over gates no words")
        self.settle(p, S1, "hub/mem-1", 1)
        self.assertEqual(self.owed(), (0, "nothing owed\n"))

    def test_another_machines_member_and_a_session_owed_nothing_are_not_ours(self):
        p = self.project("work")
        self.member(p, S2, "far", machine="mini")
        self.member(p, S1, "near")
        self.arrive(p, "hub/mem-1", 1, [S2])
        self.assertEqual(self.owed(), (0, "nothing owed\n"))

    def test_bounded_to_a_few_references_with_the_whole_count(self):
        p = self.project("work")
        self.member(p, S1, "alpha")
        for seq in range(1, 11):
            self.arrive(p, "hub/mem-1", seq, [S1])
        rc, out = self.owed()
        line = self.line(out, "work")
        self.assertIn("deliveries 10 [hub/mem-1:1 → alpha, hub/mem-1:2 → alpha, hub/mem-1:3 → alpha, …]", line)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertIn("oldest", line)


class Words(Machine):
    def test_a_words_gated_event_on_a_cut_over_machine_then_none(self):
        self.cut_over()
        p = self.project("work")
        self.member(p, S1, "alpha")
        self.arrive(p, "hub/mem-1", 1, [S1])
        self.arrive(p, "mini/" + S2, 1, [S1], kind="say")
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        line = self.line(out, "work")
        self.assertIn("words 1 [hub/mem-1:1 → alpha]", line)
        self.assertIn("deliveries 1 [%s:1 → alpha]" % S2[:8], line, "a peer's say is a plain delivery")
        self.settle(p, S1, "hub/mem-1", 1)
        self.settle(p, S1, "mini/" + S2, 1)
        self.assertEqual(self.owed(), (0, "nothing owed\n"))


class Closed(Machine):
    def test_owed_to_a_closed_session_is_its_own_line_and_owes_nothing(self):
        p = self.project("work")
        self.member(p, S1, "gone")
        self.retire(p, S1)
        self.arrive(p, "hub/mem-1", 1, [S1])
        rc, out = self.owed()
        self.assertEqual(rc, 0, out)
        closed = [x for x in out.splitlines() if x.startswith("work: ")]
        self.assertEqual(len(closed), 1, out)
        self.assertIn("closed sessions 1 [hub/mem-1:1 → gone]", closed[0])
        self.assertIn("nothing owed", out)

    def test_a_session_retired_otherwise_is_neither(self):
        p = self.project("work")
        self.member(p, S1, "moved")
        self.retire(p, S1, reason="moved")
        self.arrive(p, "hub/mem-1", 1, [S1])
        self.assertEqual(self.owed(), (0, "nothing owed\n"))


class Upload(Machine):
    def own(self, p, sid=S1, n=1):
        self.member(p, sid, "alpha")
        for i in range(n):
            sminos.log_append(p, "testhost/%s" % sid, "say", to=[], text=SECRET)

    def test_own_events_not_taken_then_taken(self):
        p = self.project("work")
        self.own(p, n=2)
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        self.assertIn("upload 2 [%s:2, %s:3]" % (S1[:8], S1[:8]), self.line(out, "work"),
                      "the joined the uplink took is not owed")
        self.taken_state(p, taken={"testhost/" + S1: 2})
        rc, out = self.owed()
        self.assertIn("upload 1 [%s:3]" % S1[:8], self.line(out, "work"))
        self.taken_state(p, taken={"testhost/" + S1: 3})
        self.assertEqual(self.owed(), (0, "nothing owed\n"))

    def test_a_project_with_no_upstream_owes_none(self):
        local = self.project("solo", hub=False)
        self.own(local)
        self.assertEqual(self.owed(), (0, "nothing owed\n"))

    def test_a_machine_not_enrolled_owes_nothing_upstream(self):
        p = self.project("work")
        self.own(p)
        os.unlink(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json"))
        self.assertEqual(self.owed(), (0, "nothing owed\n"))

    def test_on_a_cut_over_machine_too(self):
        self.cut_over()
        p = self.project("work")
        self.own(p)
        rc, out = self.owed()
        self.assertIn("upload 1 [%s:2]" % S1[:8], self.line(out, "work"))
        self.taken_state(p, taken={"testhost/" + S1: 2})
        self.assertEqual(self.owed(), (0, "nothing owed\n"))


class Kept(Machine):
    def test_settlements_and_rpc_messages_kept_under_daemon(self):
        p = self.project("work")
        frame = {"t": "session", "message": {"project": p.id, "machine": "testhost", "session": S1, "kind": "settled",
                                             "sub": None, "n": None, "body": {"request": "r1", "text": SECRET}}}
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "requests-owed.json"), {
            "version": 1, "owed": [{"session": S1, "request": "r1", "t": 5, "project": p.id, "frame": frame}]})
        op = {"t": "session", "message": {"project": p.id, "machine": "testhost", "session": S2, "kind": "compact",
                                          "sub": None, "n": None, "body": {"summary": SECRET}}}
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "rpcs-owed.json"),
                          {"version": 1, "owed": [op]})
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        self.assertIn("kept 2 [settled %s, compact %s]" % (S1[:8], S2[:8]), self.line(out, "work"))
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "requests.json"), {S1: [["r1", 5]]})
        rc, out = self.owed()
        self.assertIn("kept 1 [compact %s]" % S2[:8], self.line(out, "work"), "a settlement relayed is done with")
        for name in ("requests-owed.json", "rpcs-owed.json"):
            sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", name), {"version": 1, "owed": []})
        self.assertEqual(self.owed(), (0, "nothing owed\n"))


class Host(Machine):
    def test_the_host_stores_unsent_events_then_none(self):
        self.cut_over()
        p = self.project("work")
        w = "testhost/" + S1
        sminos._append(p, w, [{"kind": "message", "session": S1, "text": SECRET}], store=sminos.HOST_STORE)
        sminos._append(p, w, [{"kind": "message", "session": S1, "text": SECRET}], store=sminos.HOST_STORE)
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        self.assertIn("host 2 [%s:1, %s:2]" % (S1[:8], S1[:8]), self.line(out, "work"))
        self.uplink_state(p, host_sent={w: 2})
        self.assertEqual(self.owed(), (0, "nothing owed\n"))


class Outcomes(Machine):
    def test_delivery_outcomes_not_yet_posted(self):
        p = self.project("work")
        outcomes.Outbox(p).record({"writer": "hub/mem-1", "seq": 4}, S1, "delivered", "pushed")
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        self.assertIn("outcomes 1 [hub/mem-1:4 → %s]" % S1[:8], self.line(out, "work"))
        outcomes.Outbox(p).drop(1)
        self.assertEqual(self.owed(), (0, "nothing owed\n"))


class ReadOnly(Machine):
    def test_it_writes_nothing(self):
        self.cut_over()
        p = self.project("work")
        self.member(p, S1, "alpha")
        self.member(p, S3, "gone")
        self.retire(p, S3)
        self.arrive(p, "hub/mem-1", 1, [S1, S3])
        sminos.log_append(p, "testhost/" + S1, "say", to=[], text=SECRET)

        def tree():
            out = {}
            for d, _, files in os.walk(os.environ["SMINOS_HOME"]):
                for f in files:
                    st = os.stat(os.path.join(d, f))
                    out[os.path.join(d, f)] = (st.st_size, st.st_mtime_ns)
            return out
        before = tree()
        rc, _ = self.owed()
        self.assertEqual(rc, 1)
        self.assertEqual(tree(), before, "nothing written: no file made, changed or touched")


class Taken(Machine):
    """The uplink's `taken`: what a process beside it reads for the upload kind."""

    def link(self):
        cred = {"org": "org-1", "hub": "http://127.0.0.1:9", "machine": "testhost", "key": base64.urlsafe_b64decode(
            KEY + "=")}
        link = uplink.Link(cred, {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        return link

    def test_the_hubs_have_and_each_upload_it_took(self):
        p = self.project("work")
        w = "testhost/" + S1
        for _ in range(3):
            sminos.log_append(p, w, "say", to=[], text="x")
        hl = hublog.HubLog(p, {"key": base64.urlsafe_b64decode(KEY + "="), "machine": "testhost"})
        hl.on_have({"have": {w: 1, "hub/mem-1": 9}})
        self.assertEqual(hl.taken(), {w: 1}, "the hub's vector for this machine's writers, as it said it")
        hl.on_have({"have": {w: 0}})
        self.assertEqual(hl.taken(), {w: 1}, "never back")
        link = self.link()
        link.log_lane.refuse = {"events": "not-open"}
        link.upload(hl)
        self.assertEqual(hl.taken(), {w: 1}, "an upload the hub refused is not taken")
        hl.reset()
        hl.on_have({"have": {w: 1}})
        link.log_lane.refuse = {}
        link.upload(hl)
        self.assertEqual([e["seq"] for f in link.log_lane.sent[-1:] for e in f["events"]], [2, 3])
        self.assertEqual(hl.taken(), {w: 3}, "an upload answered is taken")
        self.assertEqual(self.owed(), (0, "nothing owed\n"))


class TakenBounds(Machine):
    """A writer the upstream refused, or asked again from a seq, bounds
    `taken` against an upload's continuation that runs after it: the 200 (or
    the socket's write) says the frame arrived, not that every event in it
    was taken."""

    def setUp(self):
        super().setUp()
        self.p = self.project("work")
        self.w = "testhost/" + S1
        for _ in range(3):
            sminos.log_append(self.p, self.w, "say", to=[], text="x")
        self.hl = hublog.HubLog(self.p, {"key": base64.urlsafe_b64decode(KEY + "="), "machine": "testhost"})
        self.hl.on_have({"have": {}})
        self.lane = self.link().log_lane
        self.lane.hold_thens = True

    link = Taken.link

    def upload(self):
        link = self.link()
        link.log_lane = link.session_lane = self.lane
        link.upload(self.hl)

    def test_a_refusal_before_the_continuation_holds(self):
        self.upload()
        self.hl.on_refused({"refusal": {"reason": "conflict", "writer": self.w, "seq": 1}})
        self.lane.run_held()
        self.assertEqual(self.hl.taken().get(self.w, 0), 0, "the refused writer is not taken past its refusal")
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        self.assertIn("upload 3", self.line(out, "work"))

    def test_a_refusal_after_the_continuation_lowers_it(self):
        self.upload()
        self.lane.run_held()
        self.assertEqual(self.hl.taken(), {self.w: 3})
        self.hl.on_refused({"refusal": {"reason": "conflict", "writer": self.w, "seq": 2}})
        self.assertEqual(self.hl.taken(), {self.w: 1})

    def test_a_resend_lowers_it_and_an_older_continuation_cannot_raise_it(self):
        self.upload()
        self.lane.run_held()
        self.assertEqual(self.hl.taken(), {self.w: 3})
        self.hl.on_resend({"writer": self.w, "from": 2})
        self.assertEqual(self.hl.taken(), {self.w: 1}, "the upstream lacks it from 2")
        rc, out = self.owed()
        self.assertIn("upload 2 [%s:2, %s:3]" % (S1[:8], S1[:8]), self.line(out, "work"))
        self.upload()   # the resend's upload
        self.hl.on_resend({"writer": self.w, "from": 2})   # asked again before its answer
        self.lane.run_held()
        self.assertEqual(self.hl.taken(), {self.w: 1}, "an upload sent before the latest resend takes nothing")
        self.upload()
        self.lane.run_held()
        self.assertEqual(self.hl.taken(), {self.w: 3}, "the one sent after it does")

    def test_a_later_have_does_not_pass_an_unresolved_bound(self):
        self.upload()
        self.hl.on_refused({"refusal": {"reason": "too-large", "writer": self.w, "seq": 2}})
        self.lane.run_held()
        self.hl.on_have({"have": {self.w: 3}})   # a vector the upstream drew before it refused
        self.assertEqual(self.hl.taken(), {self.w: 1})
        self.hl.reset()
        self.hl.on_have({"have": {self.w: 3}})   # a new stream's handshake: what it holds now
        self.assertEqual(self.hl.taken(), {self.w: 3})


class FormerNames(Machine):
    def test_a_host_event_under_a_former_name(self):
        self.cut_over()
        ident = json.loads(Path(rl10.identity_path()).read_text())
        ident["former"] = {"oldhost": [S1]}
        sminos.write_json(rl10.identity_path(), ident, mode=0o600)
        sminos.forget_caches()
        p = self.project("work")
        sminos._append(p, "oldhost/" + S1, [{"kind": "message", "session": S1, "text": SECRET}],
                       store=sminos.HOST_STORE)
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        self.assertIn("host 1 [%s:1]" % S1[:8], self.line(out, "work"))
        self.uplink_state(p, host_sent={"oldhost/" + S1: 1})
        self.assertEqual(self.owed(), (0, "nothing owed\n"))

    def test_the_archives_legacy_writers_while_it_writes_the_archive(self):
        p = self.project("work")
        sminos.log_append(p, "legacy/old-chat", "say", to=[], text=SECRET)
        self.assertEqual(self.owed(), (0, "nothing owed\n"), "not uploaded while another machine writes it")
        self.uplink_state(p, archive=True)
        rc, out = self.owed()
        self.assertIn("upload 1 [legacy/old-chat:1]", self.line(out, "work"))
        self.taken_state(p, taken={"legacy/old-chat": 1})
        self.assertEqual(self.owed(), (0, "nothing owed\n"))


class Uninspectable(Machine):
    """A state file that is there and cannot be read is no evidence that
    nothing is owed: named, never its body, and the exit is 1."""

    def assert_named(self, path):
        rc, out = self.owed()
        self.assertEqual(rc, 1, out)
        self.assertIn("%s: cannot be inspected" % path, out)
        self.assertNotIn("nothing owed", out)

    def unreadable(self, path):
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o600)

    def compaction(self, p):
        return {"t": "session", "message": {"project": p.id, "machine": "testhost", "session": S2, "kind": "compact",
                                            "sub": None, "n": None, "body": {"summary": SECRET}}}

    def test_an_unreadable_rpcs_file(self):
        p = self.project("work")
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", "rpcs-owed.json")
        sminos.write_json(path, {"version": 1, "owed": [self.compaction(p)]})
        self.unreadable(path)
        self.assert_named(path)

    def test_a_settlements_file_of_another_version_or_not_json(self):
        p = self.project("work")
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", "requests-owed.json")
        sminos.write_json(path, {"version": 9, "owed": [{"session": S1, "project": p.id, "text": SECRET}]})
        self.assert_named(path)
        Path(path).write_text('{"version": 1, "owed": [' + SECRET)
        self.assert_named(path)

    def test_an_absent_file_is_nothing(self):
        self.project("work")
        self.assertEqual(self.owed(), (0, "nothing owed\n"))

    def test_an_unreadable_uplink_state(self):
        p = self.project("work")
        self.uplink_state(p, host_sent={})
        self.unreadable(os.path.join(p.home, sminos.UPLINK_STATE))
        self.assert_named(os.path.join(p.home, sminos.UPLINK_STATE))

    def test_an_unreadable_outbox(self):
        p = self.project("work")
        outcomes.Outbox(p).record({"writer": "hub/mem-1", "seq": 4}, S1, "delivered", SECRET)
        self.unreadable(outcomes.Outbox(p).path)
        self.assert_named(outcomes.Outbox(p).path)

    def test_an_unreadable_delivery_record(self):
        p = self.project("work")
        self.member(p, S1, "alpha")
        self.arrive(p, "hub/mem-1", 1, [S1])
        self.settle(p, S1, "hub/mem-1", 1)
        path = os.path.join(p.home, "delivered", S1 + ".json")
        Path(path).write_text("{" + SECRET)
        self.assert_named(path)

    def test_an_unreadable_log_file(self):
        p = self.project("work")
        self.member(p, S1, "alpha")
        self.arrive(p, "hub/mem-1", 1, [S1])
        path = sminos.writer_path(p, "hub/mem-1")
        self.unreadable(path)
        self.assert_named(path)

    def test_an_unreadable_project_registration(self):
        p = self.project("work")
        path = os.path.join(p.home, "project.json")
        self.unreadable(path)
        self.assert_named(path)


class TakenRig(Machine):
    """A hub project with three events of one of this machine's writers, its
    log plane opened (an empty `have`), and a lane."""

    def setUp(self):
        super().setUp()
        self.p = self.project("work")
        self.w = "testhost/" + S1
        for _ in range(3):
            sminos.log_append(self.p, self.w, "say", to=[], text="x")
        self.hl = hublog.HubLog(self.p, {"key": base64.urlsafe_b64decode(KEY + "="), "machine": "testhost"})
        self.hl.on_have({"have": {}})
        self.lane = Taken.link(self).log_lane

    def upload(self):
        link = Taken.link(self)
        link.log_lane = link.session_lane = self.lane
        link.upload(self.hl)


class TakenResumes(TakenRig):
    """`taken` is the uplink's own view of what it no longer has to send:
    never more than its resume state, down as well as up."""

    def test_an_opening_have_sets_it_down_as_well(self):
        self.upload()
        self.assertEqual(self.hl.taken(), {self.w: 3}, "written to the endpoint")
        self.hl.reset()   # the endpoint died before it kept them; a new connection
        self.hl.on_have({"have": {}})
        self.assertEqual(self.hl.taken(), {}, "the handshake is the resume point")
        self.assertIsNotNone(self.hl.next_upload(), "which re-offers them")
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        self.assertIn("upload 3", self.line(out, "work"))

    def test_a_periodic_have_only_raises_it(self):
        self.upload()
        self.hl.on_have({"have": {self.w: 1}})
        self.assertEqual(self.hl.taken(), {self.w: 3})

    def test_a_conflict_survives_a_reconnect_and_is_its_own_kind(self):
        self.lane.hold_thens = True
        self.upload()
        self.hl.on_refused({"refusal": {"reason": "conflict", "writer": self.w, "seq": 2}})
        self.lane.run_held()
        self.hl.reset()
        self.hl.on_have({"have": {self.w: 3}})   # the upstream holds another event at 2
        self.assertEqual(self.hl.taken(), {self.w: 1})
        rc, out = self.owed()
        self.assertEqual(rc, 1)
        line = self.line(out, "work")
        self.assertIn("refused 1 [%s:2]" % S1[:8], line)
        self.assertIn("upload 2 [%s:2, %s:3]" % (S1[:8], S1[:8]), line)
        hublog.HubLog(self.p, {"key": None, "machine": "testhost"}).on_have({"have": {self.w: 3}})
        self.assertIn("refused 1", self.line(self.owed()[1], "work"), "persisted: another process, another stream")

    def test_another_refusal_is_not_kept_past_the_stream(self):
        self.upload()
        self.hl.on_refused({"refusal": {"reason": "too-large", "writer": self.w, "seq": 2}})
        self.hl.reset()
        self.hl.on_have({"have": {self.w: 1}})
        rc, out = self.owed()
        self.assertNotIn("refused", out)
        self.assertIn("upload 2", self.line(out, "work"))

    def test_the_upstream_holding_the_same_event_resolves_a_conflict(self):
        ep = __import__("endpoint_standin")
        hl = hublog.HubLog(self.p, {"key": None, "machine": "testhost"}, coded=False)
        hl.on_have({"have": {}})
        hl.on_refused({"refusal": {"reason": "conflict", "writer": self.w, "seq": 2}})
        self.assertIn("refused 1", self.line(self.owed()[1], "work"))
        stored = [e for e in sminos.log_read(self.p) if e["writer"] == self.w and e["seq"] == 2][0]
        echo = {"event": {**ep.upload_form(stored), "sig": {"kid": "k", "sig": "AQ"}, "attest": {}},
                "signer": {"kind": "machine", "name": "testhost", "ref": "r", "keyId": "k"}, "owners": []}
        self.assertEqual(hl.take([echo])[0], 0)
        self.assertNotIn("refused", self.owed()[1])


class TakenWrites(TakenRig):
    """A write of `taken` that fails never changes what the uplink does, and
    never leaves the file saying less is owed than is."""

    def failing(self):
        return mock.patch.object(hublog.HubLog, "write_taken", side_effect=OSError(28, "No space left on device"))

    def test_a_resend_happens_whatever_the_write_does_and_fails_safe(self):
        self.upload()
        self.assertEqual(self.hl.taken(), {self.w: 3})
        with self.failing():
            self.hl.on_resend({"writer": self.w, "from": 2})
        self.assertEqual(self.hl.sent[self.w], 1, "the resend is followed")
        self.assertIsNone(self.hl.drawing)
        self.assertFalse(os.path.exists(self.taken_path(self.p)), "a lowering not written takes the file away")
        rc, out = self.owed()
        self.assertIn("upload 3", self.line(out, "work"))
        self.assertIn("could not be written", Path(os.environ["SMINOS_HOME"], "daemon.log").read_text())

    def test_a_refusal_whatever_the_write_does(self):
        self.upload()
        with self.failing():
            self.hl.on_refused({"refusal": {"reason": "conflict", "writer": self.w, "seq": 2}})
        self.assertIn(self.w, self.hl.stuck)
        self.assertEqual(self.owed()[0], 1)

    def test_a_raise_not_written_leaves_it_lower(self):
        self.lane.hold_thens = True
        self.upload()
        with self.failing():
            self.lane.run_held()
            self.hl.on_have({"have": {self.w: 3}})
        self.assertEqual(self.owed()[0], 1)


class Enrollment(Machine):
    def assert_named(self, path):
        rc, out = self.owed()
        self.assertEqual(rc, 1, out)
        self.assertIn("%s: cannot be inspected" % path, out)

    def test_an_unreadable_hub_credential(self):
        self.project("work")
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json")
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o600)
        self.assert_named(path)

    def test_a_hub_credential_without_its_fields(self):
        self.project("work")
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json")
        Path(path).write_text(json.dumps({"hub": 1, "key": SECRET}))
        self.assert_named(path)

    def test_an_identity_that_is_not_one(self):
        self.project("work")
        self.cut_over()
        Path(rl10.identity_path()).write_text("{" + SECRET)
        self.assert_named(rl10.identity_path())


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
