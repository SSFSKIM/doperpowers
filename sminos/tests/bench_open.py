#!/usr/bin/env python3
"""bench_open — how long a session view takes to open, end to end through the
real uplink and the real hub code, and phase by phase in-process (the desk
open-fast spec, docs/doperpowers/specs/2026-10-20-desk-open-fast-design.md,
M2). An open runs from a browser client's `subscribe` to its receipt of the
`snapshot`: E. The machine's share, N, from the subscribe frame's arrival at
the uplink's reader to the snapshot's emission, is the plane's open line in
daemon.log, reported beside E as a diagnostic.

    bench_open.py --uplink --hub local --maws <MAWS worktree> [--live [--thinking] [--model M] | --synthetic-rows N]
                  --scenario S --opens N [--pause-stream 4 --backlog 4m] [--keep]
    bench_open.py --uplink --hub standin [...]
    bench_open.py --micro --session <id> --sminos-home <dir> [--home <dir>] [--opens N]

The full path (`--uplink`): this checkout's `sminos daemon uplink` under a
temporary HOME and SMINOS_HOME, enrolled at a hub this instrument starts —
`--hub local`, the hub's own Worker on a local runtime (`pnpm --filter
desk-hub local --state <tmp> --port <free>` in the `--maws` worktree), a
browser client on the project's socket (ws_client); or `--hub standin`,
hub_standin.py, its `/control/send` the client's subscribe and its stamped
`sessions` what the client receives. The session is fake_session.py's
scripted one by default; `--live` an isolated headless session as
mods/live-bridge-check.py isolates one (it spends haiku calls: run by hand,
with the gateway's keys in the environment; `--thinking` turns extended
thinking on); `--synthetic-rows N` a transcript of N rows shaped like a real
one, with no bridge. Every DX4 message the client received for an open goes
through the reference consumer (dx4_consumer.Consumer), and the inventory
says what is missing against the transcript on disk and the DX5 events the
session emitted (the fake session's posts, or a live session's probe
subscription), with the bridge's snapshot line placed among them for each
subscription the plane served (the uplink here runs under a bootstrap that
tees each subscription's first bridge lines, its sub beside them: nothing of
the uplink's behavior changes). What a run stands on — the hubs and their
browser clients, the sessions, the machine and its uplink — is bench_rig.py.

Scenarios: `idle` (opens between turns, after one uncounted open that builds
the index), `after-prompt` (each open made on the prompt row's notice),
`mid-message` (`--thinking` live, or the fake session's scripted message: the
open made on the first text chunk after the thinking block's `block-row`; it
counts only when the probe shows it inside that window, which each line
reports; a first live message with no thinking stops the run), `long-answer`
(the same window, opened at +1 s and re-subscribed at +7 s: an `end` before
the step's is said), `kill` (live: the child SIGKILLed mid-stream by the pid
its /status answers, the client subscribing again on each `end`, measured
from the kill to the successor's bridged snapshot), `restart` (the same open
on a fresh uplink, then after each restart), `held` (local hub: the pause
proxy between the uplink and the hub; a subscription streaming, a second
machine's upload of `--backlog` bytes fanned out down the uplink's stream,
the proxy pausing it on its first `events` frame for `--pause-stream`
seconds; the chunks' lag and the hub's answers in that window, and an open
1 s after it resumes).

Each open prints one JSON line — {"mode", "scenario", "load1", "E", "N",
"arrived", "taken", "build", "cpu_ms", "rows", "cut", "waits", "holes",
"dups", "gaps", "vanished", ...} — and each scenario a summary line: min /
p50 / max of E and N over the opens that count, and the load's range
(`load1` is the 1-minute load average, uptime's first figure).

The micro-benchmark (`--micro`): one Subscription made as Plane.subscribe
makes it and pumped as the uplink pumps it, in this process, against a
session's bridge and transcript under the named SMINOS_HOME (and HOME), the
open's phases stamped — the bench's plane_open.py, ported. It leaves out the
reader queue, the record scan, the ticks, the refreshes, the warmer and the
uplink's thread: its figure is N_micro, not N and not E. It writes nothing
under the directories it reads (the plane's log lines are kept here).
"""

import argparse
import base64
import bisect
import http.client
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid as uuidlib

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import dx4_consumer  # noqa: E402
from bench_rig import SCRIPTS, FakeKind, LiveKind, Rig, _read, call, read_tees, wait_for  # noqa: E402

SCENARIOS = ("idle", "after-prompt", "mid-message", "long-answer", "kill", "restart", "held")
LEAVES_OUT = "the reader queue, the record scan, the ticks, the refreshes, the warmer and the uplink's thread"

PROMPTS = {
    "settle": "Reply with the single word: ready. Use no tools.",
    "after-prompt": "Say hello in five words. Use no tools.",
    "mid-message": ("Think the plot through step by step before you answer. Then write a 400-word story about a "
                    "lighthouse keeper who finds a message in a bottle. Plain prose, no headings. Use no tools."),
    "long-answer": ("Think the plot through step by step before you answer. Then write a 900-word story about a "
                    "lighthouse keeper who finds a message in a bottle. Plain prose, no headings. Use no tools."),
    "kill": "Write a 450-word story about a lighthouse keeper. Plain prose, no headings. Use no tools.",
}


# ------------------------------------------------------------- what is read


OPEN_LINE = re.compile(
    r"plane: open (?P<sub>\S+) of (?P<sid>[0-9a-f]{8})(?:/(?P<agent>\S+))?: (?P<outcome>.*?) after "
    r"(?P<N>-?\d+\.\d+) s from the subscribe's arrival \((?P<bridge>.*?); build: (?P<build>.*?), "
    r"cut (?P<cut>on disk|not on disk|null); waits (?P<waits>\d+)\)$")
BRIDGE_CLAUSE = re.compile(r"bridge: snapshot arrived (-?\d+\.\d+) s, taken (-?\d+\.\d+) s")
BUILD_CLAUSE = re.compile(r"(\w+) (\d+) ms (\d+) rows")


def parse_open_line(line):
    """The plane's open line (the spec's section 5) as figures, or None."""
    m = OPEN_LINE.search(line.rstrip("\n"))
    if not m:
        return None
    out = {"sub": m["sub"], "outcome": m["outcome"], "N": float(m["N"]), "arrived": None, "taken": None,
           "bridge": m["bridge"], "build": None, "cpu_ms": None, "rows": None, "cut": m["cut"],
           "waits": int(m["waits"])}
    b = BRIDGE_CLAUSE.fullmatch(m["bridge"])
    if b:
        out["arrived"], out["taken"] = float(b[1]), float(b[2])
    k = BUILD_CLAUSE.fullmatch(m["build"])
    if k:
        out["build"], out["cpu_ms"], out["rows"] = k[1], int(k[2]), int(k[3])
    else:
        out["build"] = m["build"]
    return out


def open_lines(path):
    """Every open line in a daemon.log, by sub (the last, should one repeat)."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                if "plane: open " in line:
                    rec = parse_open_line(line)
                    if rec:
                        out[rec["sub"]] = rec
    except FileNotFoundError:
        pass
    return out


def stats(xs):
    """min / p50 / max of the figures that are there."""
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {"n": 0, "min": None, "p50": None, "max": None}
    return {"n": len(xs), "min": round(xs[0], 3), "p50": round(statistics.median(xs), 3), "max": round(xs[-1], 3)}


def size_arg(text):
    """`4m`, `512k`, `1000000`: bytes."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmM]?)", text.strip())
    if not m:
        raise argparse.ArgumentTypeError("a size is a number with an optional k or m: %r" % text)
    return int(float(m[1]) * {"": 1, "k": 1 << 10, "m": 1 << 20}[m[2].lower()])


def load1():
    return round(os.getloadavg()[0], 2)


def uptime():
    return subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()


def event_key(e):
    """A DX5 event as the child fans it out, less the subscriber's own `n`."""
    return json.dumps({k: v for k, v in e.items() if k != "n"}, sort_keys=True)


def place_snapshots(backbone, tees):
    """One ordered DX5 stream with the bridge's snapshot line for each
    subscription the plane served placed in it, as the inventory reads it:
    `backbone` the session's events in the child's order, [(at, event)];
    `tees` [{"sub", "lines": [(at, line), ...]}], each subscription's first
    bridge lines, its snapshot first. The child takes a snapshot and adds its
    subscriber under the lock that applies events, so a snapshot stands just
    before the first event its subscriber was sent: placed there when that
    event is in the backbone (the nearest copy in time), else by its arrival
    stamp. Returns (events, {sub: "event" | "time"})."""
    positions = {}
    for i, (_, e) in enumerate(backbone):
        positions.setdefault(event_key(e), []).append(i)
    stamps = [at for at, _ in backbone]
    inserts, how = [], {}
    for t in tees:
        lines = t.get("lines") or []
        if not lines or not isinstance(lines[0][1], dict) or lines[0][1].get("type") != "snapshot":
            continue
        snap_at, snap = lines[0]
        pos = None
        for at, e in lines[1:]:
            found = positions.get(event_key(e)) if isinstance(e, dict) else None
            if found:
                pos = min(found, key=lambda i: abs(backbone[i][0] - at))
                how[t["sub"]] = "event"
                break
        if pos is None:
            pos = bisect.bisect_right(stamps, snap_at)
            how[t["sub"]] = "time"
        inserts.append((pos, snap_at, {**snap, "sub": t["sub"]}))
    inserts.sort(key=lambda x: (x[0], x[1]))
    out, k = [], 0
    for i, (_, e) in enumerate(backbone):
        while k < len(inserts) and inserts[k][0] <= i:
            out.append(inserts[k][2])
            k += 1
        out.append(e)
    out += [x[2] for x in inserts[k:]]
    return out, how


def steps_seen(events, since=0.0, agent=None):
    """What a probe saw of each model request of a loop since `since`:
    (turnId, agentId, step) → {"kinds": {index: kind}, "named": {index: at
    of its block-row}, "thinking_named" (the first thinking block's
    block-row), "text_after" (the first text chunk after it), "end" (its
    step end, or its turn's completion cutting it off), "chunks"}."""
    out = {}
    turns_done = {}
    for at, e in events:
        if at < since or not isinstance(e, dict) or (e.get("agentId") or None) != agent:
            continue
        kind = e.get("type")
        if kind == "turn" and e.get("phase") == "complete":
            turns_done.setdefault(e.get("turnId"), at)
            continue
        key = (e.get("turnId"), e.get("agentId"), e.get("step"))
        if kind not in ("chunk", "block-row", "step"):
            continue
        s = out.setdefault(key, {"kinds": {}, "named": {}, "thinking_named": None, "text_after": None, "end": None,
                                 "chunks": 0, "start": None})
        if kind == "chunk":
            c = e.get("chunk") or {}
            s["chunks"] += 1
            s["kinds"].setdefault(c.get("index"), c.get("kind"))
            if c.get("kind") == "text" and s["thinking_named"] is not None and s["text_after"] is None:
                s["text_after"] = at
        elif kind == "block-row":
            s["named"].setdefault(e.get("index"), at)
            if s["kinds"].get(e.get("index")) == "thinking" and s["thinking_named"] is None:
                s["thinking_named"] = at
        elif kind == "step":
            if e.get("phase") == "start":
                s["start"] = s["start"] or at
            elif e.get("phase") == "end" and s["end"] is None:
                s["end"] = at
    for key, s in out.items():
        if s["end"] is None and key[0] in turns_done:
            s["end"] = turns_done[key[0]]
    return out


def in_window(named, end, at):
    """Whether an open made at `at` fell after the thinking block's
    block-row and before its step's end."""
    return named is not None and end is not None and named < at < end


# ------------------------------------------------------------- an open


class Open:
    def __init__(self, sub, sent, consumer):
        self.sub, self.sent, self.consumer = sub, sent, consumer
        self.snap_at = None
        self.end_at = None
        self.taken = 0
        self.chunks = []      # (arrival, the bridge's stamp `t`, ms) of each chunk message


class Bench:
    """The opens of one run, and what each prints."""

    def __init__(self, rig, kind, a):
        self.rig, self.kind, self.a = rig, kind, a
        self.records = []
        self.mode = "uplink"

    # ---- the uplink, connected

    def connected(self, since):
        """Once the hub relayed a presence of the session said after `since`."""
        b = self.rig.browser

        def said():
            b.poll()
            return any(at >= since and m.get("kind") == "presence" and m.get("session") == self.kind.sid
                       for at, m in b.msgs)
        wait_for("the session's presence through the hub", 60, said, 0.1)

    def start(self):
        rig = self.rig
        rig.sminos("daemon", "tick")   # the project's .smns read, a scripted session's record joined
        t = rig.start_uplink()
        rig.browser = rig.hub.browser(rig)
        self.kind.start()
        self.connected(t - 1)

    def restart(self):
        self.rig.stop_uplink()
        t = self.rig.start_uplink()
        self.connected(t)
        return t

    # ---- one open

    def open(self, previous=None, agent=None):
        sub, sent = self.rig.browser.subscribe(self.kind.sid, agent)
        return Open(sub, sent, dx4_consumer.Consumer(agent, previous))

    def feed(self, o):
        b = self.rig.browser
        b.poll()
        mine = [(at, m) for at, m in b.msgs if m.get("sub") == o.sub]
        for at, m in mine[o.taken:]:
            o.consumer.take(m)
            if m.get("kind") == "snapshot" and o.snap_at is None:
                o.snap_at = at
            elif m.get("kind") == "end" and o.end_at is None:
                o.end_at = at
            elif m.get("kind") == "chunk":
                t = (m.get("body") or {}).get("t")
                o.chunks.append((at, t))
        o.taken = len(mine)

    def until(self, o, pred, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.feed(o)
            if pred():
                return True
            time.sleep(0.02)
        self.feed(o)
        return pred()

    def opened(self, o, seconds=30):
        self.until(o, lambda: o.snap_at is not None or o.end_at is not None, seconds)
        return o

    def close(self, o):
        if o.end_at is None:
            self.rig.browser.unsubscribe(o.sub)

    def open_line(self, sub, seconds=10):
        try:
            return wait_for("the open line of %s" % sub, seconds, lambda: open_lines(self.rig.daemon_log()).get(sub), 0.05)
        except TimeoutError:
            return None

    def record(self, scenario, o, counted=True, **extra):
        """The open's line: E, the open line's figures, the consumer's and the inventory's findings."""
        line = self.open_line(o.sub) or {}
        backbone = self.kind.dx5()
        tees = [t for t in read_tees(self.rig.tee)]
        events, how = place_snapshots(backbone, tees)
        check = dx4_consumer.Inventory.from_sources(self.kind.transcript(), events).check(o.consumer)
        kinds = o.consumer.error_kinds()
        rec = {"mode": self.mode, "hub": self.rig.hub.name, "session": self.kind.name, "scenario": scenario,
               "load1": load1(), "E": None if o.snap_at is None else round(o.snap_at - o.sent, 3),
               "N": line.get("N"), "arrived": line.get("arrived"), "taken": line.get("taken"),
               "build": line.get("build"), "cpu_ms": line.get("cpu_ms"), "rows": line.get("rows"),
               "cut": line.get("cut"), "waits": line.get("waits"),
               "holes": len(check["holes"]), "dups": len(check["dups"]), "gaps": kinds.count("gap"),
               "vanished": len(check["vanished"]), "undrawn": len(check["undrawn"]),
               "residual": len(check["residual"]), "partial": len(check["partial"]),
               "errors": sorted(set(kinds)), "outcome": line.get("outcome"),
               "ended": None if o.end_at is None else (o.consumer.end or {}).get("reason"),
               "placed": how.get(o.sub), "counted": counted, **extra}
        self.records.append(rec)
        print(json.dumps(rec), flush=True)
        return rec

    def summary(self, scenario):
        mine = [r for r in self.records if r["scenario"] == scenario and r.get("counted")]
        loads = [r["load1"] for r in mine]
        out = {"summary": scenario, "mode": self.mode, "hub": self.rig.hub.name, "session": self.kind.name,
               "opens": len(mine), "E": stats(r["E"] for r in mine), "N": stats(r["N"] for r in mine),
               "load1": {"min": min(loads, default=None), "max": max(loads, default=None)},
               "uptime": uptime()}
        extra = [r for r in self.records if r["scenario"] == scenario and not r.get("counted")]
        if extra:
            out["not_counted"] = len(extra)
        print(json.dumps(out), flush=True)
        return out


# ------------------------------------------------------------- the scenarios


def settle(bench):
    """A live session with one turn behind it, so it has rows and is idle."""
    k = bench.kind
    if k.name == "live":
        t0 = k.prompt(PROMPTS["settle"])
        wait_for("the settling turn", 180, lambda: k.turn_done(t0), 0.2)
        time.sleep(1.0)


def sc_idle(bench, a):
    settle(bench)
    o = bench.opened(bench.open())
    bench.until(o, lambda: False, 0.5)
    bench.record("idle", o, counted=False, note="the warm-up open: builds the index")
    bench.close(o)
    for _ in range(a.opens):
        time.sleep(0.5)
        o = bench.opened(bench.open())
        bench.until(o, lambda: False, 0.5)
        bench.record("idle", o)
        bench.close(o)


def last_row_held(bench, o):
    """Whether the consumer holds the transcript's last row on disk."""
    inv = dx4_consumer.Inventory.from_sources(bench.kind.transcript(), [])
    return bool(inv.rows) and inv.rows[-1]["uuid"] in o.consumer.held


def sc_after_prompt(bench, a):
    settle(bench)
    k = bench.kind
    for _ in range(a.opens):
        time.sleep(0.5)
        if k.name == "live":
            t0 = k.prompt(PROMPTS["after-prompt"])
            wait_for("the prompt row's notice", 60, lambda: any(
                e.get("type") == "row-seen" and not e.get("agentId") for _, e in k.events(t0)), 0.005)
            o = bench.opened(bench.open())
            bench.until(o, lambda: k.turn_done(t0), 120)
            bench.until(o, lambda: last_row_held(bench, o), 5)
        else:
            u = str(uuidlib.uuid4())
            k.fake.user_row("hi", disk=False, uuid=u)
            threading.Timer(0.1, lambda: k.fake.write_row(None, {
                "type": "user", "uuid": u, "agentId": None, "message": {"role": "user", "content": "hi"}})).start()
            o = bench.opened(bench.open())
            m = k.fake.message()
            m.text(0, "Hello again.")
            m.row(0)
            m.end()
            bench.until(o, lambda: last_row_held(bench, o), 5)
        bench.record("after-prompt", o)
        bench.close(o)


def fake_thinking_message(fake, think_s, answer_s, on_text, every=0.1):
    """A scripted model request with thinking: its thinking block streams
    and is named by its block-row (the row not on disk: the engine flushes
    a message's rows when it ends), then its text streams for `answer_s`
    (`on_text()` at the first text chunk), then the text's block-row, both
    rows on disk, the step's end. The chunks carry the wall clock's `t`."""
    m = fake.message()
    chunk = [0]

    def post(kind, index, text):
        m.post([{"type": "chunk", **m.ids(), "chunkIndex": chunk[0], "chunk": {"kind": kind, "index": index,
                                                                                "text": text},
                 "t": int(time.time() * 1000)}])
        m.up_to[index] = chunk[0]
        chunk[0] += 1
        m.next_chunk = chunk[0]

    thought = ""
    for i in range(max(1, int(think_s / every))):
        piece = "considering %d. " % i
        thought += piece
        post("thinking", 0, piece)
        time.sleep(every)
    a_uuid, b_uuid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
    m.settled.add(0)
    m.post([{"type": "block-row", "uuid": a_uuid, **m.ids(), "index": 0, "t": int(time.time() * 1000)}])
    said = ""
    n = max(1, int(answer_s / every))
    for i in range(n):
        piece = "word%d " % i
        said += piece
        post("text", 1, piece)
        if i == 0:
            on_text()
        time.sleep(every)
    m.settled.add(1)
    m.post([{"type": "block-row", "uuid": b_uuid, **m.ids(), "index": 1, "t": int(time.time() * 1000)}])
    for uid, content in ((a_uuid, {"type": "thinking", "thinking": thought}), (b_uuid, {"type": "text", "text": said})):
        fake.write_row(None, {"type": "assistant", "uuid": uid, "agentId": None,
                              "message": {"role": "assistant", "content": [content]}})
    m.end()
    return m


def thinking_trial(bench, scenario, opens_at, answer_s):
    """One message with thinking and the opens of a window scenario: the
    first at the first text chunk after the thinking block's block-row
    (`opens_at` None) or at those offsets from it, each later one a
    re-subscribe that resumes the one before. Returns (opens, the probe's
    view of the step, the step key) or None when the message had no
    thinking."""
    k = bench.kind
    trigger = threading.Event()
    t0 = time.time()
    if k.name == "live":
        k.prompt(PROMPTS[scenario])

        def text_after():
            for key, s in steps_seen(k.events(t0), t0).items():
                if s["text_after"] is not None:
                    return key, s
            return None

        def ended_without():
            return k.turn_done(t0) and text_after() is None

        wait_for("a text chunk after a thinking block's block-row, or the turn's end", 240,
                 lambda: text_after() or ended_without(), 0.005)
        found = text_after()
        if found is None:
            return None
        key, s = found
        named = s["thinking_named"]
    else:
        th = threading.Thread(target=fake_thinking_message, args=(k.fake, 0.5, answer_s, trigger.set), daemon=True)
        th.start()
        trigger.wait(30)
        found = [(key, s) for key, s in steps_seen(k.dx5(), t0).items() if s["thinking_named"] is not None]
        key, s = found[-1]
        named = s["thinking_named"]
    opens = []
    previous = None
    for offset in (opens_at or (None,)):
        if offset is not None:
            delay = named + offset - time.time()
            if delay > 0:
                time.sleep(delay)
        if opens:
            bench.close(opens[-1])
            previous = opens[-1].consumer
        o = bench.opened(bench.open(previous=previous))
        o.offset = offset
        opens.append(o)
    return opens, key


def step_view(bench, key, since):
    events = bench.kind.dx5()
    return steps_seen(events, since).get(key) or {}


def sc_window(bench, a, scenario):
    """mid-message and long-answer: opens counted only inside the thinking-to-end window."""
    settle(bench)
    k = bench.kind
    long_ = scenario == "long-answer"
    counted, trials = 0, 0
    while counted < a.opens and trials < max(a.opens * 3, a.opens + 2):
        trials += 1
        t0 = time.time()
        got = thinking_trial(bench, scenario, (1.0, 7.0) if long_ else None, 12.5 if long_ else 2.3)
        if got is None:
            if trials == 1:
                print(json.dumps({"stopped": scenario, "why": "the first message streamed no thinking block before "
                                  "its text: the model or the budget gave no thinking (try --model sonnet)"}),
                      flush=True)
                return
            continue
        opens, key = got
        last = opens[-1]

        def done():
            s = step_view(bench, key, t0)
            return s.get("end") is not None and (k.name != "live" or k.turn_done(t0))
        bench.until(last, done, 240)
        bench.until(last, lambda: last_row_held(bench, last), 6)
        for o in opens[:-1]:
            bench.feed(o)
        s = step_view(bench, key, t0)
        named, end = s.get("thinking_named"), s.get("end")
        window = None if named is None or end is None else round(end - named, 3)
        inside = all(in_window(named, end, o.sent) for o in opens)
        if long_:
            inside = inside and window is not None and window >= 7.0
        for o in opens:
            early = o.end_at is not None and end is not None and o.end_at < end
            bench.record(scenario, o, counted=inside, window=window, trial=trials,
                         at=None if named is None else round(o.sent - named, 3),
                         **({"offset": o.offset, "end_before_step_end": early,
                             "window_12s": window is not None and window >= 12.0} if long_ else {}))
        bench.close(last)
        if inside:
            counted += 1
        if k.name == "live":
            wait_for("the trial's turn end", 240, lambda: k.turn_done(t0), 0.2)
        time.sleep(1.0)
    print(json.dumps({"windows": scenario, "trials": trials, "counted": counted, "missed": trials - counted}),
          flush=True)


def sc_kill(bench, a):
    k = bench.kind
    if k.name != "live":
        sys.exit("bench_open: --scenario kill needs --live (the mod respawns the child)")
    settle(bench)
    for _ in range(a.opens):
        o = bench.opened(bench.open())
        t0 = k.prompt(PROMPTS["kill"])
        wait_for("the answer streaming", 120, lambda: sum(
            1 for _, e in k.events(t0) if e.get("type") == "chunk" and (e.get("chunk") or {}).get("kind") == "text")
            >= 20, 0.005)
        pid = k.live.status()["pid"]
        killed = time.time()
        os.kill(pid, signal.SIGKILL)
        successor, chain = None, []
        current = o
        deadline = time.time() + 30
        while time.time() < deadline and successor is None:
            bench.until(current, lambda: current.end_at is not None, max(0.1, deadline - time.time()))
            if current.end_at is None:
                break
            if chain:
                chain[-1]["ended"] = round(current.end_at - killed, 3)
            nxt = bench.opened(bench.open(previous=current.consumer))
            line = bench.open_line(nxt.sub, 5) or {}
            # Each re-subscribe the kill took: when it went and its snapshot came, after the kill, and how.
            chain.append({"sent": round(nxt.sent - killed, 3),
                          "snapshot": None if nxt.snap_at is None else round(nxt.snap_at - killed, 3),
                          "outcome": line.get("outcome"), "N": line.get("N")})
            if nxt.snap_at is not None and line.get("outcome") == "bridge snapshot":
                successor = nxt
            current = nxt
        if successor is None:
            print(json.dumps({"kill": "no bridged snapshot within 30 s of the kill", "chain": chain}), flush=True)
        else:
            bench.until(successor, lambda: k.turn_done(t0), 180)
            bench.record("kill", successor, E_kill=round(successor.snap_at - killed, 3), resubscribes=len(chain),
                         chain=chain)
            bench.close(successor)
        wait_for("the turn's end", 180, lambda: k.turn_done(t0), 0.2)
        time.sleep(1.0)


def sc_restart(bench, a):
    for i in range(max(1, a.opens)):
        if i:
            bench.restart()
        time.sleep(0.5)
        o = bench.opened(bench.open(), 120)
        bench.until(o, lambda: False, 0.3)
        bench.record("restart", o, moment="first start" if i == 0 else "after restart %d" % i)
        bench.close(o)


class Uploader:
    """A second machine of the org at the local hub: its own stream (read
    and dropped), a hello for the project, then `events` uploads of its own
    writer, sealed with the org key, which the hub fans out down every other
    machine's stream that opened the project."""

    def __init__(self, hub, project):
        sys.path.insert(0, SCRIPTS)
        import sminos_codes
        self.codes = sminos_codes
        self.hub, self.project = hub, project
        self.machine = "bench-up-" + uuidlib.uuid4().hex[:6]
        self.cred = hub.mint(self.machine)
        self.headers = {"CF-Access-Client-Id": self.cred["client_id"],
                        "CF-Access-Client-Secret": self.cred["client_secret"]}
        u = urllib.parse.urlsplit(hub.url)
        self.stream = http.client.HTTPConnection(u.hostname, u.port, timeout=30)
        self.stream.request("GET", "/machine/stream", headers={**self.headers, "Accept": "text/event-stream"})
        r = self.stream.getresponse()
        if r.status != 200:
            raise RuntimeError("the uploader's stream was refused: %s" % r.status)
        self.generation = None
        while self.generation is None:
            line = r.fp.readline()
            if line.startswith(b"data: "):
                f = json.loads(line[6:])
                if f.get("t") == "welcome":
                    self.generation = f["generation"]
        self.r = r
        threading.Thread(target=self.drain, daemon=True).start()

    def drain(self):
        try:
            while self.r.fp.readline():
                pass
        except (OSError, ValueError, AttributeError):   # AttributeError: closed under it (fp gone)
            pass

    def post(self, frames):
        body = "".join(json.dumps(f) + "\n" for f in frames).encode()
        return call(self.hub.url, "POST", "/machine/frames", body,
                    {**self.headers, "X-Desk-Generation": str(self.generation), "Content-Type": "application/x-ndjson"},
                    timeout=60)

    def upload(self, size, per_event=64 << 10, per_post=8):
        """`size` bytes of events in POSTs of `per_post` events; each POST's (status, answer)."""
        status, body = self.post([{"t": "hello", "project": self.project, "name": "benchproj", "have": {}}])
        if status != 200:
            raise RuntimeError("the uploader's hello: %s %s" % (status, body))
        key = base64.urlsafe_b64decode(self.hub.key + "=" * (-len(self.hub.key) % 4))
        sid = str(uuidlib.uuid4())
        writer = "%s/%s" % (self.machine, sid)
        n = max(1, size // per_event)
        answers, seq = [], 0
        while seq < n:
            batch = []
            for _ in range(min(per_post, n - seq)):
                seq += 1
                draft = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()), "writer": writer, "seq": seq,
                         "kind": "say", "session": sid, "to": [], "text": ("backlog %d " % seq).ljust(per_event, "x")}
                batch.append(self.codes.seal(key, "log", self.project, draft, self.codes.b64url(os.urandom(16))))
            answers.append(self.post([{"t": "events", "project": self.project, "events": batch}]))
        return answers

    def close(self):
        try:
            self.stream.close()
        except OSError:
            pass


def sc_held(bench, a):
    rig, k = bench.rig, bench.kind
    if rig.hub.name != "local" or k.name != "fake":
        sys.exit("bench_open: --scenario held runs on --hub local with the fake session")
    proxy = rig.proxy
    control = proxy["control"]
    o = bench.opened(bench.open())
    stop = threading.Event()
    m = k.fake.message()

    def stream():
        i = 0
        while not stop.is_set():
            m.post([{"type": "chunk", **m.ids(), "chunkIndex": i,
                     "chunk": {"kind": "text", "index": 0, "text": "c%d " % i}, "t": int(time.time() * 1000)}])
            m.texts[0] = m.texts.get(0, "") + "c%d " % i
            m.up_to[0] = i
            i += 1
            m.next_chunk = i
            time.sleep(0.1)

    th = threading.Thread(target=stream, daemon=True)
    th.start()
    bench.until(o, lambda: bool(o.chunks), 10)
    streams_before = call(control, "GET", "/control/state")[1]["streams"]
    status, armed = call(control, "POST", "/control/arm", {"on": "next-events", "seconds": a.pause_stream})
    if status != 200 or armed.get("state") != "armed":
        sys.exit("bench_open: the proxy did not arm: %s %s" % (status, armed))
    up = Uploader(rig.hub, rig.project)
    t_up = time.time()
    answers = up.upload(a.backlog)
    t_answered = time.time()
    try:
        st = wait_for("the proxy's pause", 30, lambda: (lambda s: s if s["state"] in ("paused", "resumed") else None)(
            call(control, "GET", "/control/state")[1]), 0.02)
    except TimeoutError:
        sys.exit("bench_open: the proxy never paused: the upload's answers %s, the proxy %s" % (
            [(s_, str(b_)[:200]) for s_, b_ in answers], call(control, "GET", "/control/state")[1]))
    paused_at = st["paused_at"]
    st = wait_for("the proxy's resume", a.pause_stream + 30, lambda: (lambda s: s if s["state"] == "resumed" else None)(
        call(control, "GET", "/control/state")[1]), 0.05)
    resumed_at = st["resumed_at"]
    bench.until(o, lambda: False, max(0.0, resumed_at + 1.0 - time.time()))
    o2 = bench.opened(bench.open())
    bench.until(o2, lambda: False, 1.0)
    stop.set()
    th.join(5)
    u = m.row(0)
    m.end()
    bench.until(o, lambda: u in o.consumer.held, 10)
    bench.feed(o2)
    lags = [round(at - t / 1000.0, 3) for at, t in o.chunks if isinstance(t, (int, float))
            and paused_at <= t / 1000.0 <= resumed_at]
    posts = rig.hub.requests(paused_at, resumed_at + 0.5)
    final = call(control, "GET", "/control/state")[1]
    bench.record("held", o, counted=False, role="the subscription streaming through the pause",
                 window=round(resumed_at - paused_at, 3), held_bytes=final.get("held"), backlog=a.backlog,
                 upload_answers=[s for s, _ in answers], upload_s=round(t_answered - t_up, 3),
                 chunk_lag_max=max(lags, default=None), chunks_in_window=len(lags),
                 posts_in_window=len(posts), posts_not_200=[p for p in posts if p["status"] != 200],
                 post_ms_max=max((p["ms"] for p in posts), default=None),
                 stream_survived=final.get("streams") == streams_before and o.end_at is None)
    bench.record("held", o2, role="the open 1 s after the resume", at=round(o2.sent - resumed_at, 3))
    bench.close(o)
    bench.close(o2)
    up.close()


# ------------------------------------------------------------- the micro-benchmark


def micro(a):
    """N_micro: one Subscription made as Plane.subscribe makes it, pumped as
    the uplink pumps it (a wake, else every POLL), its phases stamped."""
    os.environ["SMINOS_HOME"] = os.path.abspath(a.sminos_home)
    if a.home:
        os.environ["HOME"] = os.path.abspath(a.home)
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(os.environ["HOME"], ".claude")
    sys.path.insert(0, SCRIPTS)
    import sminos as S
    import sminos_bridge as B
    import sminos_plane as P
    marks = []
    T0 = [time.monotonic()]

    def mark(what, detail=None):
        marks.append((round(time.monotonic() - T0[0], 4), what, detail))

    def wrap(obj, name, label, detail=None):
        orig = getattr(obj, name)

        def f(*args, **kwargs):
            mark(label + ":start")
            r = orig(*args, **kwargs)
            mark(label + ":end", detail(r) if detail else None)
            return r
        setattr(obj, name, f)

    put = P.BridgeReader.put

    def put_(self, item):
        if item[0] != "line" or (isinstance(item[1], dict) and item[1].get("type") == "snapshot"):
            mark("reader:" + item[0], item[1].get("type") if isinstance(item[1], dict) else str(item[1])[:80])
        put(self, item)

    P.BridgeReader.put = put_
    wrap(P, "build", "build", lambda r: r[0])
    wrap(P, "look", "look")
    wrap(S, "transcript_now", "locate", lambda r: bool(r))
    said = []
    P.log = lambda line: (said.append(line), mark("log", line))
    transcripts, disk = P.Transcripts(), P.Disk()
    records = []
    for i in range(a.opens):
        marks.clear()
        said.clear()
        woken = threading.Event()
        T0[0] = time.monotonic()
        received = time.time()
        reader = None
        if os.path.exists(B.endpoint(a.session)):
            reader = P.BridgeReader(B.endpoint(a.session), woken.set)
            reader.start()
        sub = P.Subscription("micro", "micro", a.session, None, "micro-%d" % i, reader=reader,
                             locate=lambda: S.transcript_now(a.session),
                             presence=lambda: {"record": None, "bridge": reader is not None}, alive=lambda: True,
                             transcripts=transcripts, wake=woken.set, disk=disk, received=received)
        mark("subscription")
        snap = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and snap is None and not sub.ended:
            woken.wait(0.25)
            woken.clear()
            for msg in sub.pump():
                if msg["kind"] in ("snapshot", "end"):
                    snap = (round(time.monotonic() - T0[0], 4), msg["kind"])
                    mark(msg["kind"])
        sub.close()
        line = parse_open_line("plane: " + said[0]) if said else {}
        rec = {"mode": "micro", "scenario": "micro", "load1": load1(), "N_micro": snap[0] if snap else None,
               "outcome": snap[1] if snap else None, "build": (line or {}).get("build"),
               "cpu_ms": (line or {}).get("cpu_ms"), "rows": (line or {}).get("rows"),
               "cut": (line or {}).get("cut"), "waits": (line or {}).get("waits"),
               "phases": marks[:], "line": said[0] if said else None, "leaves_out": LEAVES_OUT}
        records.append(rec)
        print(json.dumps(rec), flush=True)
        time.sleep(0.2)
    loads = [r["load1"] for r in records]
    print(json.dumps({"summary": "micro", "mode": "micro", "opens": len(records),
                      "N_micro": stats(r["N_micro"] for r in records),
                      "load1": {"min": min(loads, default=None), "max": max(loads, default=None)},
                      "uptime": uptime(), "leaves_out": LEAVES_OUT}), flush=True)


# ------------------------------------------------------------- main


def run(a):
    print(json.dumps({"start": a.scenario, "hub": a.hub, "session": "live" if a.live else
                      ("synthetic" if a.synthetic_rows else "fake"), "uptime": uptime()}), flush=True)
    rig = Rig(a)
    kind = None
    try:
        kind = LiveKind(rig, a) if a.live else FakeKind(rig, a.synthetic_rows)
        if a.scenario == "held":
            ports_file = os.path.join(rig.root, "proxy.json")
            rig.spawn([sys.executable, os.path.join(HERE, "pause_proxy.py"), rig.hub.url, ports_file],
                      log="proxy.out")
            ports = json.loads(wait_for("the pause proxy", 10, lambda: _read(ports_file)))
            rig.proxy = {"proxy": "http://127.0.0.1:%d" % ports["proxy"],
                         "control": "http://127.0.0.1:%d" % ports["control"]}
            rig.point_uplink_at(rig.proxy["proxy"])
        bench = Bench(rig, kind, a)
        bench.start()
        {"idle": sc_idle, "after-prompt": sc_after_prompt, "kill": sc_kill, "restart": sc_restart, "held": sc_held,
         "mid-message": lambda b, x: sc_window(b, x, "mid-message"),
         "long-answer": lambda b, x: sc_window(b, x, "long-answer")}[a.scenario](bench, a)
        bench.summary(a.scenario)
    finally:
        if kind is not None:
            kind.close()
        rig.close()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--uplink", action="store_true", help="the full path: the real uplink and a hub")
    mode.add_argument("--micro", action="store_true", help="one Subscription in-process: N_micro")
    p.add_argument("--hub", choices=("local", "standin"), default="standin")
    p.add_argument("--maws", help="the MAWS worktree whose apps/desk-hub runs as the local hub")
    p.add_argument("--live", action="store_true", help="an isolated headless session (spends haiku calls)")
    p.add_argument("--thinking", action="store_true", help="with --live: extended thinking on")
    p.add_argument("--model", default="haiku", help="with --live: the session's model")
    p.add_argument("--synthetic-rows", type=int, metavar="N", help="a synthetic transcript of N rows, no bridge")
    p.add_argument("--scenario", choices=SCENARIOS, default="idle")
    p.add_argument("--opens", type=int, default=5)
    p.add_argument("--pause-stream", type=float, default=4.0, metavar="S")
    p.add_argument("--backlog", type=size_arg, default=4 << 20, metavar="B")
    p.add_argument("--keep", action="store_true", help="leave the run's temporary directory")
    p.add_argument("--session", help="--micro: the session id")
    p.add_argument("--sminos-home", help="--micro: the SMINOS_HOME its bridge and the plane read")
    p.add_argument("--home", help="--micro: the HOME whose .claude holds its transcript")
    a = p.parse_args()
    if a.micro:
        if not (a.session and a.sminos_home):
            p.error("--micro needs --session and --sminos-home")
        return micro(a)
    if a.live and a.synthetic_rows:
        p.error("--live and --synthetic-rows are two different sessions")
    if a.thinking and not a.live:
        p.error("--thinking is a live session's")
    run(a)


if __name__ == "__main__":
    main()
