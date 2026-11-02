#!/usr/bin/env python3
"""Live check of the lane B receipts (O12 M4b): sminos's real send and
delivery path into a marked `claude -p` whose bridge activated `gate`, under
live-observer-check.py's stand-in of MAWS's gate host and its scripted
stand-in of the Messages API (nothing spent, no key).

What only a running engine shows, pinned so a release that breaks it fails
loudly:
- activation (decisions C7): a fresh process records `gate` under
  $SMINOS_HOME/holder-deliveries/launches/ before its first hello; /status
  says `receipts: gate`; the bridge mod handled the classic SessionStart with
  its source and a young process age;
- the marker (C6): `[sminos receipt <id> attempt <n>]` survives the engine's
  inbox rendering into the session.append row, turn.start's text and the
  api conversation (`$.session.messages({as: 'api'})`), a wake's too, as a
  diagnostic mod loaded beside sminos's reads them;
- the order of writes: the receipt is on disk, prepared, before the inbox
  write, and pushed after it;
- proceed: a peer turn under a fence answered `proceed` names its receipt as
  the turn frame's `delivery`; the receipt settles at the admission report,
  not at the handoff, and the delivery cursor with it;
- stop: no main request, the receipt and the cursor stay owed; the matching
  disarm releases it, and the same id comes again as attempt 2, a wake, which
  is admitted and settled;
- an unarmed admission and a lease-expiry admission settle;
- reload: an admission report the child never acknowledged (the child
  stopped) survives a module reload and is replayed to the next child;
- resume: a stopped receipt is retried by a new `claude --resume` process
  with the same id, a wake while its row is retained, the full body after a
  rewind (`--resume-session-at`) dropped it;
- the existing-process side: a process running the M4a plugin (doperpowers
  d6bd2d35), a peer delivered and a fence armed, hot-reloaded to this
  plugin stays `legacy`, observed with its new childPid and its fence, and
  hands deliveries off with no receipt; a process with no M4a observer
  (the plugin before M4a, origin/main 17944939 at 1.31.0) reloaded to this
  plugin says no hello and stays legacy.

One engine runs at a time; everything it starts is isolated as
live-observer-check.py isolates it, plus this check's own `sminos daemon
run` (the deliverer that retries), and stopped at the end. No suite runs it:
run it by hand at a milestone, with Python 3.10+.

    sminos/tests/mods/live-receipts-check.py [--keep]     # --keep: leave the temp dir
"""

import calendar
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_observer_check", os.path.join(HERE, "live-observer-check.py"))
OC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OC)
LB = OC.LB
now, wait_for, is_in = OC.now, OC.wait_for, OC.is_in

MARKER_RE = re.compile(r"\[sminos receipt ([0-9a-f]{24}\.[0-9a-f]{16}) attempt ([1-9][0-9]*)\]")
M4A = "d6bd2d35"          # doperpowers: the M4a observer's head (sminos 1.32.0)
PRE_M4A = "17944939"      # doperpowers origin/main: sminos 1.31.0, no observer
PROBE = """const say = ($: any, text: string) => { try { $.ui.log('T7_PROBE ' + text, { to: 'debug' }) } catch {} }
const head = (c: any) => (typeof c === 'string' ? c : JSON.stringify(c)).slice(0, 600)
export const register = (on: any) => {
  on('classic.SessionStart', { source: /^/ }, async ($: any, e: any, next: any) => { say($, 'sessionstart ' + JSON.stringify({ source: e.source })); return next(e) })
  on('session.append', { door: /^/ }, async ($: any, e: any, next: any) => {
    if (e.agentId === undefined && (e.door === 'prompt' || e.door === 'delivery' || e.door === 'queue')) say($, 'append ' + JSON.stringify({ door: e.door, origin: e.origin, text: head(e.message?.content) }))
    return next(e)
  })
  on('turn.start', { turnId: /^/ }, async ($: any, e: any, next: any) => {
    if (e.agentId === undefined) {
      say($, 'turnstart ' + JSON.stringify({ turnId: e.turnId, text: String(e.text).slice(0, 600) }))
      try {
        const api = await $.session.messages({ as: 'api' })
        const marks = []
        for (const m of api) if (m && m.role === 'user') { const t = typeof m.content === 'string' ? m.content : JSON.stringify(m.content); for (const x of t.matchAll(/\\[sminos receipt [0-9a-f.]+ attempt [0-9]+\\]/g)) marks.push(x[0]) }
        say($, 'api ' + JSON.stringify({ turnId: e.turnId, marks }))
      } catch (err) { say($, 'api-error ' + String(err)) }
    }
    return next(e)
  })
}
"""


class Watch:
    """The receipt layer's files and the delivery records as they change,
    polled every 10 ms: each change with its monotonic and wall time."""

    def __init__(self, smh):
        self.smh = smh
        self.rows = []
        self.cond = threading.Condition()
        self.seen = {}
        self.stop = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _files(self):
        out = {}
        for d, _, files in os.walk(self.smh):
            base = os.path.basename(d)
            parent = os.path.basename(os.path.dirname(d))
            kind = ("receipt" if base == "holder-deliveries" else "mode" if base == "launches" and parent == "holder-deliveries"
                    else "delivered" if base == "delivered" else "cursor" if base == "cursors" else None)
            if kind is None:
                continue
            for f in files:
                if f.endswith(".json"):
                    p = os.path.join(d, f)
                    try:
                        with open(p) as fh:
                            out[p] = (kind, fh.read())
                    except OSError:
                        pass
        return out

    def _run(self):
        while not self.stop.is_set():
            files = self._files()
            with self.cond:
                for p, (kind, text) in files.items():
                    if self.seen.get(p) != text:
                        try:
                            obj = json.loads(text)
                        except ValueError:
                            continue
                        self.seen[p] = text
                        self.rows.append({"t": now(), "wall": time.time(), "kind": kind, "path": p, "obj": obj})
                        self.cond.notify_all()
                for p in [p for p in self.seen if p not in files]:
                    del self.seen[p]
                    self.rows.append({"t": now(), "wall": time.time(), "kind": "removed", "path": p, "obj": None})
                    self.cond.notify_all()
            time.sleep(0.01)

    def receipt(self, rid):
        """Every state of receipt `rid`, then its removal."""
        with self.cond:
            path = next((r["path"] for r in self.rows if r["kind"] == "receipt" and (r["obj"] or {}).get("id") == rid), None)
            return [r for r in self.rows if r["path"] == path] if path else []

    def wait(self, what, seconds, pred):
        deadline = now() + seconds
        with self.cond:
            while True:
                got = [r for r in self.rows if pred(r)]
                if got:
                    return got[0]
                left = deadline - now()
                if left <= 0:
                    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))
                self.cond.wait(min(left, 0.5))

    def latest(self, kind):
        with self.cond:
            out = {}
            for r in self.rows:
                if r["kind"] == kind:
                    out[r["path"]] = r["obj"]
                elif r["kind"] == "removed":
                    out.pop(r["path"], None)
            return out


def state_of(r):
    o = r["obj"]
    if o is None:
        return "removed"
    a = o.get("attempt") or {}
    return "attempt %s %s %s%s%s%s" % (a.get("n"), a.get("body"), a.get("state"), " handed" if o.get("handed") else "",
                                       " released(%s)" % o["released"]["attempt"] if o.get("released") else "",
                                       " admitted" if o.get("admitted") else "")


class Receipts(OC.Observer):
    def __init__(self, keep):
        super().__init__(keep)
        self.watch = Watch(self.smh)
        self.daemon = None
        self.launches = 0
        self.probe = os.path.join(self.root, "probe")
        self.debugs = []

    # -- isolation, the probe, the daemon

    def setup(self, stub_url):
        super().setup(stub_url)
        os.makedirs(os.path.join(self.probe, ".claude-plugin"))
        os.makedirs(os.path.join(self.probe, "hooks"))
        with open(os.path.join(self.probe, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"name": "t7-receipt-probe", "version": "0.1.0", "description": "T7: logs prompt rows, turn starts and the api conversation's receipt markers"}, f)
        with open(os.path.join(self.probe, "hooks", "hooks.json"), "w") as f:
            json.dump({"modules": ["./register.ts"]}, f)
        with open(os.path.join(self.probe, "hooks", "register.ts"), "w") as f:
            f.write(PROBE)
        self.watch.start()

    def start_daemon(self):
        log = open(os.path.join(self.root, "daemon.out"), "wb")
        self.daemon = subprocess.Popen([self.sminos(), "daemon", "run"], cwd=self.work, env=self.local_env(), stdout=log,
                                       stderr=subprocess.STDOUT)

    def stage_rev(self, rev, dest):
        """The sminos plugin at doperpowers `rev`, staged as a --plugin-dir."""
        tmp = os.path.join(self.root, "arch-%s" % rev)
        os.makedirs(tmp)
        repo = os.path.dirname(LB.PLUGIN_ROOT)
        arch = subprocess.run(["git", "-C", repo, "archive", rev, "sminos"], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", tmp], input=arch, check=True)
        LB.stage(os.path.join(tmp, "sminos"), dest, LB.PLUGIN_PARTS)
        shutil.rmtree(tmp)

    def upgrade_in_place(self, dest):
        """This plugin's parts over a staged older one, in place: the engine's plugin-dir watch reloads it."""
        for part in LB.PLUGIN_PARTS:
            shutil.rmtree(os.path.join(dest, part), ignore_errors=True)
        LB.stage(self.plugin, dest, LB.PLUGIN_PARTS)
        with open(os.path.join(dest, "hooks", "mods", "bridge.tsx"), "a") as f:
            f.write("\n// live-receipts-check: upgraded in place\n")

    def start_engine(self, plugin, session, resume=False, at=None):
        self.launches += 1
        debug = os.path.join(self.root, "debug-%d.log" % self.launches)
        self.debugs.append(debug)
        argv = [OC.ENGINE, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--include-partial-messages", "--replay-user-messages", "--include-hook-events",
                "--model", "haiku", "--setting-sources", "user,project,local", "--permission-mode", "default"]
        argv += ["--resume", session] if resume else ["--session-id", session]
        if at:
            argv += ["--resume-session-at", at]
        argv += ["--plugin-dir", plugin, "--plugin-dir", self.probe, "--debug-file", debug, "-n", OC.NAME]
        self.engine = OC.Engine()
        self.stderr = open(os.path.join(self.root, "engine-%d.stderr" % self.launches), "wb")
        self.engine.start(argv, self.engine_env, self.work, self.stderr)
        self.claude = self.engine.proc.pid
        self.session = session
        return self.claude

    def end_engine(self):
        p = self.engine.proc
        kids = self.bridges()
        try:
            p.stdin.close()
        except OSError:
            pass
        try:
            p.wait(15)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(5)
        for pid, _ in kids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    # -- reading

    def probe_lines(self, kind=None):
        out = []
        for d in self.debugs:
            try:
                with open(d, errors="replace") as f:
                    for line in f:
                        if "T7_PROBE " in line:
                            body = line.split("T7_PROBE ", 1)[1].strip()
                            k, _, rest = body.partition(" ")
                            if kind is None or k == kind:
                                try:
                                    out.append((line[:24], k, json.loads(rest)))
                                except ValueError:
                                    out.append((line[:24], k, rest))
            except OSError:
                pass
        return out

    def debug_matching(self, pattern):
        out = []
        for d in self.debugs:
            try:
                with open(d, errors="replace") as f:
                    out += [l.strip()[:300] for l in f if re.search(pattern, l)]
            except OSError:
                pass
        return out

    def alias(self):
        r = self.cli("list", "--json")
        try:
            rows = json.loads(r.stdout)
            rows = rows if isinstance(rows, list) else rows.get("members", [])
            return next((m.get("alias") for m in rows if m.get("session") == self.session), None) or OC.NAME
        except ValueError:
            return OC.NAME

    def say(self, words):
        alias = self.alias()
        t = now()
        r = self.cli("say", "@%s %s" % (alias, words))
        return t, r.returncode, (r.stdout + r.stderr).strip()[:240]

    def mode_record(self, pid):
        for path, obj in self.watch.latest("mode").items():
            if obj.get("pid") == pid:
                return path, obj
        return None, None

    def delivered(self):
        return self.watch.latest("delivered")

    def owed(self, key):
        """The delivery record's entry for the receipt key's writer, and whether its seq is settled."""
        for obj in self.delivered().values():
            w = obj.get(key["writer"]) if isinstance(obj, dict) else None
            if isinstance(w, dict):
                return w, int(w.get("settled") or 0) >= key["seq"]
        return None, False

    def receipt_of(self, rid):
        rows = self.watch.receipt(rid)
        return rows[-1]["obj"] if rows and rows[-1]["obj"] else None

    def settled(self, rid, seconds=40):
        """Wait for receipt `rid` to be removed (settled) and its cursor settled."""
        rows = self.watch.receipt(rid)
        key = rows[0]["obj"]["key"]
        gone = self.watch.wait("receipt %s removed" % rid[:12], seconds,
                               lambda r: r["kind"] == "removed" and r["path"] == rows[0]["path"])
        w = wait_for("the cursor of %s settled" % rid[:12], 10, lambda: (lambda e: e if e[1] else None)(self.owed(key)))
        return gone, w[0], key

    def peer_turn_frame(self, fence, mark, seconds=40):
        return self.gate.wait("turn {fence %d}" % fence, seconds, is_in("turn", fence=fence), mark)

    def new_receipt(self, since, seconds=30):
        r = self.watch.wait("a new receipt", seconds, lambda r: r["kind"] == "receipt" and r["t"] >= since and r["obj"].get("attempt", {}).get("n") == 1
                            and not any(x["path"] == r["path"] and x["t"] < since for x in self.watch.rows))
        return r["obj"]["id"]

    def marks_for(self, rid):
        """Where the marker of `rid` was seen: append rows, turn.start texts, api conversation."""
        found = {"append": [], "turnstart": [], "api": []}
        for _, k, o in self.probe_lines():
            if k in found and isinstance(o, dict):
                text = o.get("text") if k != "api" else " ".join(o.get("marks") or [])
                for m in MARKER_RE.finditer(text or ""):
                    if m.group(1) == rid:
                        found[k].append(int(m.group(2)))
        return found

    # -- the run

    def run(self):
        url = self.stub.start()
        self.setup(url)
        self.gate.listen()
        self.start_daemon()
        self.start_engine(self.plugin, self.session)
        print("  engine %s (pid %d), session %s" % (OC.ENGINE, self.claude, self.session), flush=True)
        self.activation()
        self.proceed_case()
        self.stop_case()
        # the api conversation as a later turn's start reads it: at its own turn.start the row is not in it yet
        own = [o for _, k, o in self.probe_lines("api") if isinstance(o, dict)][:1]
        self.marker_survives(self.proceed_rid, 1, "the delivery")
        self.note("the api conversation read at the delivery's own turn.start (the row is not in it yet: why T6's index-0 rule reads turn.start's text)", [json.dumps(own)])
        self.unarmed_case()
        self.lease_expiry_case()
        self.reload_case()
        self.resume_case()
        self.upgrade_case()
        self.no_observer_case()

    def activation(self):
        hello = self.hello_after(0, 60)
        pid = self.claude
        path, rec = wait_for("the mode record", 10, lambda: (lambda pr: pr if pr[1] else None)(self.mode_record(pid)))
        first = next(r for r in self.watch.rows if r["path"] == path)
        # the hello's wall time, from the watch row's pair of clocks; the record's own `since` is its write
        hello_wall = first["wall"] + (hello["t"] - first["t"])
        since = calendar.timegm(time.strptime(rec["since"][:19], "%Y-%m-%dT%H:%M:%S")) + float("0" + rec["since"][19:23])
        st = wait_for("/status with receipts", 20, lambda: (lambda s: s if s and (s.get("holder") or {}).get("receipts") else None)(self.status()))
        self.check("C7: a fresh process records gate before its first hello; /status says receipts: gate",
                   rec.get("mode") == "gate" and rec.get("by") == "activation" and rec.get("launch") and since < hello_wall
                   and st["holder"]["receipts"] == "gate",
                   "record %s written (its since) %.3f s before the hello reached the stand-in host: %s; /status holder receipts %s" % (
                       os.path.basename(path), hello_wall - since, json.dumps(rec), st["holder"].get("receipts")))
        starts = [o for _, k, o in self.probe_lines("sessionstart")]
        fresh = self.debug_matching(r"the process is a fresh one")
        age = re.search(r"its age ([0-9.]+) s", fresh[0]) if fresh else None
        self.check("C7: the classic SessionStart reached the mods with its source; the bridge took the process for a fresh one, young",
                   starts and starts[0].get("source") == "startup" and age and float(age.group(1)) < 60,
                   "SessionStart %s; bridge: %s" % (starts[:1], fresh[:1]))
        reqs = [r for r in self.stub.since(0) if r["path"] == "/v1/messages"]
        self.check("no model request with no prompt (zero inference so far)", not reqs, "%d model requests" % len(reqs))
        self.hello = hello

    def proceed_case(self):
        g, stub = self.gate, self.stub
        f = self.next_fence()
        gm, sm, em = g.mark(), stub.mark(), self.engine.mark()
        g.policy[f] = "proceed"
        self.arm(f)
        self.armed(f, gm)
        said, rc, out = self.say("[[T3:PEER]] proceed case")
        rid = self.new_receipt(said)
        turn = self.peer_turn_frame(f, gm)
        req = stub.wait("the peer turn's request", 20, sm, plan="PEER")
        self.result_after(em, 60)
        proceed = g.wait("proceed", 5, lambda e: e["dir"] == "out" and e["frame"].get("t") == "proceed" and e["frame"].get("fence") == f, gm)
        gone, w, key = self.settled(rid)
        states = self.watch.receipt(rid)
        pushed = next((r for r in states if r["obj"] and r["obj"]["attempt"]["state"] == "pushed"), None)
        admitted = next((r for r in states if r["obj"] and r["obj"].get("admitted")), None)
        prepared = states[0]
        self.check("proceed: the peer turn's frame names its receipt as delivery; one request after the proceed",
                   turn["frame"].get("delivery") == rid and turn["frame"].get("origin") == "peer" and req["t"] >= proceed["t"]
                   and len(stub.since(sm, "main")) == 1,
                   "say rc %d (%s); turn %s; request #%d %.3f s after the proceed" % (rc, out[:80], json.dumps(turn["frame"]), req["n"], req["t"] - proceed["t"]))
        handoff_owed = pushed is not None and not pushed["obj"].get("admitted")
        self.check("proceed: the receipt settles at the admission report, not at the handoff; the cursor with it",
                   handoff_owed and admitted is not None and admitted["t"] >= proceed["t"] and gone["t"] >= admitted["t"] and w["settled"] >= key["seq"],
                   "receipt %s: %s; delivered %s" % (rid[:12], ", ".join("%+.3f s %s" % (r["t"] - said, state_of(r)) for r in states), json.dumps(w)))
        self.order_of_writes(rid, prepared, pushed)
        self.proceed_rid = rid

    def order_of_writes(self, rid, prepared, pushed):
        rows = [(ts, o) for ts, k, o in self.probe_lines("append") if isinstance(o, dict) and rid in (o.get("text") or "")]
        engine_at = rows[0][0] if rows else None
        wall = lambda r: time.strftime("%H:%M:%S", time.gmtime(r["wall"])) + ".%03d" % int((r["wall"] % 1) * 1000)
        ok = prepared["obj"]["attempt"]["state"] == "prepared" and pushed is not None and prepared["t"] < pushed["t"] and engine_at \
            and wall(prepared) < engine_at[11:23]
        self.check("the receipt is prepared on disk before the inbox write, marked pushed after it",
                   ok, "prepared at %s (UTC), pushed at %s; the engine's row appended at %s" % (
                       wall(prepared), wall(pushed) if pushed else None, engine_at))

    def marker_survives(self, rid, attempt, what):
        try:
            found = wait_for("the probe's lines for %s" % rid[:12], 10, lambda: (lambda f: f if all(f.values()) else None)(self.marks_for(rid)), every=0.5)
        except TimeoutError:
            found = self.marks_for(rid)
        self.check("C6: the marker of %s survives the inbox rendering: in the session.append row, turn.start's text and the api conversation" % what,
                   attempt in found["append"] and attempt in found["turnstart"] and attempt in found["api"],
                   "attempts seen: %s" % json.dumps(found))

    def stop_case(self):
        g, stub = self.gate, self.stub
        f = self.next_fence()
        gm, sm, em = g.mark(), stub.mark(), self.engine.mark()
        g.policy[f] = "stop"
        self.arm(f)
        self.armed(f, gm)
        said, rc, out = self.say("[[T3:PEER]] stop case")
        rid = self.new_receipt(said)
        turn = self.peer_turn_frame(f, gm)
        _, _, result = self.result_after(em, 60)
        time.sleep(3.0)
        rec = self.receipt_of(rid)
        key = rec["key"]
        w, settled = self.owed(key)
        self.check("stop: no main request; the receipt and the cursor stay owed",
                   not stub.since(sm, "main") and result.get("result") == OC.STOP_REASON and turn["frame"].get("delivery") == rid
                   and not rec.get("admitted") and not settled,
                   "turn %s; main requests %d; receipt %s; delivered %s" % (json.dumps(turn["frame"]), len(stub.since(sm, "main")),
                                                                            state_of({"obj": rec}), json.dumps(w)))
        sm2, em2 = stub.mark(), self.engine.mark()
        disarmed = g.send({"t": "disarm", "fence": f})
        rel = self.watch.wait("the release of %s" % rid[:12], 20, lambda r: r["kind"] == "receipt" and (r["obj"] or {}).get("id") == rid
                              and (r["obj"] or {}).get("released"))
        retry = self.watch.wait("attempt 2 of %s" % rid[:12], 40, lambda r: r["kind"] == "receipt" and (r["obj"] or {}).get("id") == rid
                                and (r["obj"].get("attempt") or {}).get("n") == 2)
        gone, w2, _ = self.settled(rid, 60)
        self.result_after(em2, 60)
        self.check("stop: the matching disarm releases it; the same id comes again as attempt 2, a wake, admitted and settled",
                   rel["t"] >= disarmed and retry["obj"]["attempt"]["body"] == "wake" and gone["t"] > retry["t"]
                   and len(stub.since(sm2, "main")) >= 1,
                   "released %.3f s after the disarm; attempt 2 (%s) %.3f s later; settled %.3f s after it; delivered %s; requests %s" % (
                       rel["t"] - disarmed, retry["obj"]["attempt"]["body"], retry["t"] - rel["t"], gone["t"] - retry["t"],
                       json.dumps(w2), [(r["plan"], r.get("head", "")[:50]) for r in stub.since(sm2, "main")]))
        self.marker_survives(rid, 2, "the wake")
        self.note("the wake as the engine rendered it", [json.dumps(o)[:500] for _, k, o in self.probe_lines("append")
                                                          if isinstance(o, dict) and ("%s attempt 2" % rid) in (o.get("text") or "")][:1])

    def unarmed_case(self):
        sm, em = self.stub.mark(), self.engine.mark()
        gm = self.gate.mark()
        said, rc, out = self.say("[[T3:PEER]] unarmed case")
        rid = self.new_receipt(said)
        self.result_after(em, 60)
        gone, w, key = self.settled(rid)
        self.check("an unarmed admission settles its receipt and cursor",
                   len(self.stub.since(sm, "main")) == 1 and not self.gate.find(is_in("turn"), gm),
                   "receipt %s settled %.3f s after the say; delivered %s" % (rid[:12], gone["t"] - said, json.dumps(w)))

    def lease_expiry_case(self):
        g, stub = self.gate, self.stub
        f = self.next_fence()
        gm, sm, em = g.mark(), stub.mark(), self.engine.mark()
        armed_at = self.arm(f, lease=2000)
        self.armed(f, gm)
        said, rc, out = self.say("[[T3:PEER]] lease case")
        rid = self.new_receipt(said)
        turn = self.peer_turn_frame(f, gm)
        req = stub.wait("the lease-expiry request", 30, sm)
        self.result_after(em, 60)
        gone, w, key = self.settled(rid)
        g.send({"t": "disarm", "fence": f})
        self.check("a lease-expiry admission (no reply; the lease and margin pass) settles its receipt and cursor",
                   turn["frame"].get("delivery") == rid and req["t"] - armed_at >= 2.0 + OC.OBSERVER_MARGIN_S - 0.3,
                   "turn %s; request %.3f s after the arm (lease 2 s + margin 5 s); settled; delivered %s" % (
                       json.dumps(turn["frame"]), req["t"] - armed_at, json.dumps(w)))

    def reload_case(self):
        """An admission report the child never acknowledges (the child stopped) survives a module reload."""
        child = self.bridges()[0][0]
        sm, em, gm = self.stub.mark(), self.engine.mark(), self.gate.mark()
        # The child stopped (SIGSTOP; the reload's SIGKILL ends it, and cleanup's otherwise): its route answers nothing.
        os.kill(child, signal.SIGSTOP)
        said, _, _ = self.say("[[T3:PEER]] reload case")
        rid = self.new_receipt(said)
        self.result_after(em, 60)
        time.sleep(3.0)
        rec = self.receipt_of(rid)
        unacked = rec is not None and not rec.get("admitted")
        touched = now()
        with open(os.path.join(self.plugin, "hooks", "mods", "bridge.tsx"), "a") as f:
            f.write("\n// live-receipts-check: a change that reloads the module\n")
        hello = self.hello_after(gm, 90)
        try:
            os.kill(child, signal.SIGCONT)
        except OSError:
            pass
        gone, w, key = self.settled(rid, 30)
        self.check("reload: an admission report the stopped child never acknowledged survives the reload and is replayed",
                   unacked and gone["t"] > hello["t"] and len(self.stub.since(sm, "main")) == 1,
                   "admitted under the stopped child, unacknowledged 3 s later (%s); reload's hello %.3f s after the change (child %s); "
                   "settled %.3f s after the hello; delivered %s" % (
                       state_of({"obj": rec}) if rec else None, hello["t"] - touched, hello["frame"].get("childPid"),
                       gone["t"] - hello["t"], json.dumps(w)))

    def resume_case(self):
        g, stub = self.gate, self.stub
        # a stopped receipt, then the process ends
        f = self.next_fence()
        gm, em = g.mark(), self.engine.mark()
        g.policy[f] = "stop"
        self.arm(f)
        self.armed(f, gm)
        said, rc, out = self.say("[[T3:PEER]] resume case")
        rid = self.new_receipt(said)
        self.peer_turn_frame(f, gm)
        self.result_after(em, 60)
        self.end_engine()
        # a new process resumes it: the row is retained, a wake
        sm, gm2 = stub.mark(), g.mark()
        old = self.claude
        self.start_engine(self.plugin, self.session, resume=True)
        hello = self.hello_after(gm2, 60)
        _, rec = wait_for("the resumed process's mode record", 10, lambda: (lambda pr: pr if pr[1] else None)(self.mode_record(self.claude)))
        retry = self.watch.wait("the resumed attempt of %s" % rid[:12], 60, lambda r: r["kind"] == "receipt" and (r["obj"] or {}).get("id") == rid
                                and (r["obj"].get("attempt") or {}).get("pid") == self.claude)
        gone, w, key = self.settled(rid, 60)
        starts = [o for _, k, o in self.probe_lines("sessionstart")]
        self.check("resume: a new process (SessionStart %s) activates gate with the stopped row retained; the same id, a wake, admitted and settled" % (
                       starts[-1].get("source") if starts else None),
                   rec.get("mode") == "gate" and rid in (rec.get("retained") or []) and retry["obj"]["attempt"]["body"] == "wake"
                   and retry["obj"]["attempt"]["n"] == 2 and self.claude != old and len(stub.since(sm, "main")) >= 1,
                   "pid %d → %d; record %s; attempt %s; settled %.3f s after the hello; delivered %s" % (
                       old, self.claude, json.dumps(rec), json.dumps(retry["obj"]["attempt"]), gone["t"] - hello["t"], json.dumps(w)))
        # another stopped receipt, then a resume at a message before its row: a rewind, the full body
        anchor = self.last_assistant_uuid()
        f = self.next_fence()
        gm, em = g.mark(), self.engine.mark()
        g.policy[f] = "stop"
        self.arm(f)
        self.armed(f, gm)
        said, rc, out = self.say("[[T3:PEER]] rewind case")
        rid2 = self.new_receipt(said)
        self.peer_turn_frame(f, gm)
        self.result_after(em, 60)
        self.end_engine()
        sm, gm2 = stub.mark(), g.mark()
        self.start_engine(self.plugin, self.session, resume=True, at=anchor)
        try:
            self.hello_after(gm2, 60)
            retry = self.watch.wait("the rewound attempt of %s" % rid2[:12], 60, lambda r: r["kind"] == "receipt" and (r["obj"] or {}).get("id") == rid2
                                    and (r["obj"].get("attempt") or {}).get("pid") == self.claude)
            gone, w, key = self.settled(rid2, 60)
            _, rec = self.mode_record(self.claude)
            full = [o for _, k, o in self.probe_lines("append") if isinstance(o, dict) and ("%s attempt 2" % rid2) in (o.get("text") or "")]
            self.check("resume after a rewind (--resume-session-at a message before the row): the same id, the full body, admitted and settled",
                       rid2 not in (rec.get("retained") or []) and retry["obj"]["attempt"]["body"] == "full" and full and "rewind case" in full[0].get("text", ""),
                       "anchor %s; record retained %s; attempt %s; the row %s" % (
                           anchor, rec.get("retained"), json.dumps(retry["obj"]["attempt"]), json.dumps(full[:1])[:300]))
        except TimeoutError as e:
            self.check("resume after a rewind: the same id, the full body, admitted and settled", False, "%s; stderr %s" % (
                e, open(self.stderr.name, errors="replace").read()[-300:]))
        self.end_engine()

    def last_assistant_uuid(self):
        """The newest assistant message of the main conversation in the transcript: a resume at it drops what came after."""
        for d, _, files in os.walk(os.path.join(self.cfg, "projects")):
            for f in files:
                if f == self.session + ".jsonl":
                    with open(os.path.join(d, f)) as fh:
                        rows = [json.loads(l) for l in fh if l.strip()]
                    asst = [r for r in rows if r.get("type") == "assistant" and not r.get("isSidechain")]
                    return asst[-1]["uuid"] if asst else None
        return None

    def upgrade_case(self):
        g, stub = self.gate, self.stub
        dest = os.path.join(self.root, "pa")
        self.stage_rev(M4A, dest)
        session = str(uuid.uuid4())
        gm = g.mark()
        self.start_engine(dest, session)
        hello = self.hello_after(gm, 60)
        pid = self.claude
        em, sm = self.engine.mark(), stub.mark()
        said, rc, out = self.say("[[T3:PEER]] before the upgrade")
        self.result_after(em, 60)
        _, rec1 = wait_for("the M4a process's mode record", 10, lambda: (lambda pr: pr if pr[1] else None)(self.mode_record(pid)))
        f = self.next_fence()
        g.policy[f] = "proceed"
        gm2 = g.mark()
        self.arm(f)
        self.armed(f, gm2)
        touched = now()
        self.upgrade_in_place(dest)
        again = self.hello_after(gm2, 90)
        st = wait_for("/status after the upgrade", 20, lambda: (lambda s: s if s and (s.get("holder") or {}).get("ready") else None)(self.status()))
        _, rec2 = self.mode_record(pid)
        em, sm, gm3 = self.engine.mark(), stub.mark(), g.mark()
        said, rc, out = self.say("[[T3:PEER]] after the upgrade")
        self.result_after(em, 60)
        req = stub.wait("the request after the upgrade", 5, sm)
        receipts = [r for r in self.watch.rows if r["kind"] == "receipt" and r["t"] >= said]
        turns = g.find(is_in("turn"), gm3)
        kept = self.debug_matching(r"fence\(s\) held again for a whole lease and margin")
        expired = self.debug_matching(r"fence .*#%d: no answer within its lease and the margin" % f)
        self.check("an M4a process upgraded in place: legacy, observed with its new childPid, its fence kept; it hands off with no receipt",
                   rec1.get("mode") == "legacy" and rec2.get("mode") == "legacy" and again["frame"].get("pid") == pid
                   and again["frame"].get("childPid") != hello["frame"].get("childPid") and not receipts and kept and expired
                   and st["holder"].get("receipts") in ("legacy", None),
                   "before: %s; reload's hello %.3f s after the change %s; /status receipts %s; after: %s; receipts made %d" % (
                       json.dumps(rec1), again["t"] - touched, json.dumps(again["frame"]), st["holder"].get("receipts"),
                       json.dumps(rec2), len(receipts)))
        self.note("after the upgrade: the kept fence (the M4a module's, of the old child's epoch) holds the next request to its whole lease and margin; no turn goes for it on the new connection", [
            "the request %.3f s after the reload's hello; turn frames meanwhile %s" % (req["t"] - again["t"], [e["frame"] for e in turns])] + kept[:1] + expired[:1])
        self.end_engine()

    def no_observer_case(self):
        g = self.gate
        dest = os.path.join(self.root, "p0")
        self.stage_rev(PRE_M4A, dest)
        session = str(uuid.uuid4())
        gm = g.mark()
        self.start_engine(dest, session)
        pid = self.claude
        em = self.engine.mark()
        self.prompt("PLAIN")
        self.result_after(em, 60)
        time.sleep(2)
        touched = now()
        self.upgrade_in_place(dest)
        unobserved = r"the process is an existing one|an existing process no observer served"
        wait_for("the upgraded module's bridge child", 90, lambda: (lambda b: b if b and self.debug_matching(unobserved) else None)(self.bridges()))
        time.sleep(8)
        em = self.engine.mark()
        said, _, _ = self.say("[[T3:PEER]] no observer")
        self.result_after(em, 60)
        hellos = g.find(lambda e: is_in("hello")(e) and e["frame"].get("pid") == pid, gm)
        _, rec = wait_for("the mode record", 10, lambda: (lambda pr: pr if pr[1] else None)(self.mode_record(pid)))
        receipts = [r for r in self.watch.rows if r["kind"] == "receipt" and r["t"] >= said]
        self.check("a process with no M4a observer, reloaded to M4b: no hello, legacy, no receipt",
                   not hellos and rec.get("mode") == "legacy" and not receipts,
                   "hellos from pid %d: %d (in the %.0f s after the reload, and through a delivery); bridge: %s; record %s" % (
                       pid, len(hellos), now() - touched, [l.split("(to debug): ")[-1][:200] for l in self.debug_matching(unobserved)][:2], json.dumps(rec)))
        self.end_engine()

    def versions(self):
        rows = super().versions()
        rows.append("M4a plugin for the upgrade: doperpowers %s; pre-M4a plugin: doperpowers %s" % (M4A, PRE_M4A))
        return rows

    def cleanup(self):
        self.watch.stop.set()
        if self.daemon is not None and self.daemon.poll() is None:
            self.daemon.terminate()
            try:
                self.daemon.wait(10)
            except subprocess.TimeoutExpired:
                self.daemon.kill()
        super().cleanup()


def main():
    if sys.version_info < (3, 10):
        sys.exit("live-receipts-check: Python 3.10+ (sminos refuses older)")
    obs = Receipts("--keep" in sys.argv[1:])
    print("live receipts check (%s):" % obs.root, flush=True)
    try:
        obs.run()
    except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
        import traceback
        traceback.print_exc()
        obs.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
    finally:
        try:
            obs.note("receipts and delivery records as they changed",
                     ["%+8.3f s  %-9s %s %s" % (r["t"] - obs.t0, r["kind"], os.path.basename(r["path"]),
                                               state_of(r) if r["kind"] == "receipt" else json.dumps(r["obj"])[:200])
                      for r in obs.watch.rows])
            obs.note("versions", obs.versions())
        except Exception as e:  # noqa: BLE001
            print("  (versions not read: %s)" % e)
        obs.cleanup()
    failed = [r for r in obs.results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(obs.results) - len(failed), len(obs.results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
