#!/usr/bin/env python3
"""The CPU an inbound backlog costs the uplink's main thread: the code check
(sminos_codes.failure, which writes each event's RFC 8785 text) and
HubLog.take (the check, then the append), per MiB of events as the hub sends
them (their JSON, UTF-8), measured against any copy of the scripts (a
checkout's, or another commit's exported with `git archive`), so a change is
measured before and after.

    python3 bench_codes.py <scripts-dir> [--mib M] [--reps N] [--only a4|mixed] [--no-take]

Two backlogs of M MiB (6 by default, the desk open-fast band's A4 pair):
- `a4`: bench_open.py's Uploader — `say` events of 64 KiB of ASCII text, one
  writer, sealed with the org key.
- `mixed`: a busy project's log — eleven writers (sessions of two machines
  and a `hub/<member>` writer), the kinds sminos writes, texts of log-normal
  length (median about 500 characters, up to 32 KiB), 30% of them Korean,
  with Markdown, quotes, backslashes, controls, emoji and U+2028/2029.

One JSON line per backlog: the best of N repetitions (time.process_time) of
the check, of canonical() alone, of json.dumps and json.loads over the same
events for scale, and of take() in frames of eight events into a fresh
project log under a temporary HOME and SMINOS_HOME.
"""

import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import time
import uuid

p = argparse.ArgumentParser()
p.add_argument("scripts")
p.add_argument("--mib", type=float, default=6.0)
p.add_argument("--reps", type=int, default=7)
p.add_argument("--only", choices=("a4", "mixed"))
p.add_argument("--no-take", action="store_true")
a = p.parse_args()

ROOT = tempfile.mkdtemp(prefix="bench-codes-")
os.environ["HOME"] = os.path.join(ROOT, "home")
os.environ["SMINOS_HOME"] = os.path.join(ROOT, "sminos")
os.makedirs(os.environ["HOME"])
sys.path.insert(0, os.path.abspath(a.scripts))
import sminos  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_hublog as hublog  # noqa: E402

KEY = bytes(range(32))
PID = "5a000000-0000-4000-8000-000000000000"
TS = "2026-10-21T03:00:00.000Z"
SIZE = int(a.mib * (1 << 20))


def wire(e):
    return len(json.dumps(e, ensure_ascii=False).encode("utf-8"))


def a4_backlog(pid):
    sid = str(uuid.UUID(int=1))
    writer = "bench-up-000001/%s" % sid
    out = []
    for seq in range(1, SIZE // (64 << 10) + 1):
        draft = {"ts": TS, "writer": writer, "seq": seq, "kind": "say", "session": sid, "to": [],
                 "text": ("backlog %d " % seq).ljust(64 << 10, "x")}
        out.append(codes.seal(KEY, "log", pid, draft, codes.b64url(random.Random(seq).randbytes(16))))
    return out


EN = ("The uplink's main thread takes frames in arrival order, so an open queued behind an inbound backlog "
      "waits while it verifies every event's code. ").split()
KO = ("업링크의 메인 스레드는 도착 순서대로 프레임을 처리하므로 백로그 뒤에 대기 중인 열기 요청은 모든 이벤트의 코드를 "
      "검증하는 동안 기다립니다").split()
EXTRA = ["\u2014", "\u2192", "\u201cquoted\u201d", '"q"', "\\path\\to", "`code`", "\t", "\u00e9", "\u00fc", "\U0001f600", "\U0001f680", "U+2028:\u2028", "\u2029", "\x7f",
         "\x00", "\x1b[0m", "<message>", "</message>", "**bold**", "- item\n", "\n\n", "```py\nx = 1\n```"]


def text_of(r, n):
    words, size = [], 0
    ko = r.random() < 0.3
    while size < n:
        x = r.random()
        w = r.choice(KO) if ko and x < 0.6 else (r.choice(EXTRA) if x > 0.93 else r.choice(EN))
        words.append(w)
        size += len(w) + 1
    return " ".join(words)[:n]


def mixed_backlog(pid):
    r = random.Random(7)
    member = "4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c"
    writers = (["macbook/%s" % uuid.UUID(int=r.getrandbits(128)) for _ in range(6)]
               + ["mini/%s" % uuid.UUID(int=r.getrandbits(128)) for _ in range(4)] + ["hub/" + member])
    seqs = {w: 0 for w in writers}
    out, size = [], 0
    while size < SIZE:
        w = r.choice(writers)
        seqs[w] += 1
        kind = r.choices(["say", "message", "question", "answered", "human", "in-charge", "join"],
                         [40, 25, 5, 5, 10, 10, 5])[0]
        n = min(int(r.lognormvariate(6.2, 1.2)), 32 << 10)
        draft = {"ts": TS, "writer": w, "seq": seqs[w], "kind": kind}
        sid = w.split("/")[1]
        if w.startswith("hub/"):
            draft.update(kind="human", member=member, to=["@all"], text=text_of(r, n))
        elif kind in ("say", "message", "human"):
            draft.update(session=sid, to=r.choice([[], ["@all"], ["host"]]), text=text_of(r, n),
                         src="%s#%d" % (uuid.UUID(int=r.getrandbits(128)), r.randint(0, 9)), **{"from": "smns-erb-71"})
        elif kind == "question":
            draft.update(session=sid, to="host", text=[text_of(r, n // 3) for _ in range(3)],
                         choices=[[text_of(r, 20) for _ in range(3)] for _ in range(3)],
                         src="toolu_%x" % r.getrandbits(64), **{"from": "smns-erb-71"})
        elif kind == "answered":
            draft.update(session=sid, src="toolu_%x" % r.getrandbits(64), text=text_of(r, n), **{"from": "smns-erb-71"})
        elif kind == "in-charge":
            draft.update(session=sid, alias="smns-erb-71", text=text_of(r, min(n, 200)))
        else:
            draft.update(session=sid, alias="smns-erb-71", cwd="/Users/new/Developer/GitHub/doperpowers",
                         model="claude-opus-5-5", pid=r.randint(100, 99999), started=1761000000.123)
        e = codes.seal(KEY, "log", pid, draft, codes.b64url(r.randbytes(16)))
        out.append(e)
        size += wire(e)
    return out


def best(fn):
    times = []
    for _ in range(a.reps):
        t = time.process_time()
        fn()
        times.append(time.process_time() - t)
    return min(times)


def fresh_project():
    d = tempfile.mkdtemp(dir=ROOT, prefix="repo-")
    with open(os.path.join(d, ".smns"), "w") as f:
        json.dump({"project": str(uuid.uuid4()), "name": os.path.basename(d), "remote": "", "hub": {"org": "org-1"}}, f)
    return sminos.resolve_project(d)


def take_once(events):
    project = fresh_project()
    # the same events, sealed for this project's id (its code covers the id)
    evs = [codes.seal(KEY, "log", project.id, {k: v for k, v in e.items() if k != "mac"}, e["mac"]["nonce"])
           for e in events]
    hl = hublog.HubLog(project, {"key": KEY, "machine": "testhost"})
    hl.nonce_index()
    t = time.process_time()
    appended = 0
    for i in range(0, len(evs), 8):  # the Uploader's eight events a POST, one `events` frame each
        got, rejected = hl.take(evs[i:i + 8])
        appended += got
        assert not rejected, rejected
    spent = time.process_time() - t
    assert appended == len(evs), (appended, len(evs))
    return spent


def measure(name, events):
    mib = sum(map(wire, events)) / (1 << 20)
    assert all(codes.failure(KEY, "log", PID, e) is None for e in events), "an event does not verify"
    out = {"backlog": name, "events": len(events), "mib": round(mib, 3), "python": sys.version.split()[0]}
    out["check"] = best(lambda: [codes.failure(KEY, "log", PID, e) for e in events]) / mib
    out["canonical"] = best(lambda: [codes.canonical(codes.covered("log", e)) for e in events]) / mib
    out["json_dumps"] = best(lambda: [json.dumps(e, ensure_ascii=False) for e in events]) / mib
    lines = [json.dumps(e, ensure_ascii=False) for e in events]
    out["json_loads"] = best(lambda: [json.loads(line) for line in lines]) / mib
    if not a.no_take:
        out["take"] = min(take_once(events) for _ in range(a.reps)) / mib
    print(json.dumps({k: round(v, 5) if isinstance(v, float) else v for k, v in out.items()}), flush=True)


try:
    if a.only in (None, "a4"):
        measure("a4", a4_backlog(PID))
    if a.only in (None, "mixed"):
        measure("mixed", mixed_backlog(PID))
finally:
    shutil.rmtree(ROOT, ignore_errors=True)
