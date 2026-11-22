#!/usr/bin/env python3
"""The wire check of test-older-cli.sh (CH1's M8: "the checker, baselined on
the store as the older copy left it, clean over an uplink run on it").

    older_channel_wire.py baseline <file> <channel id>...
        channel_wire.baseline of the store ($SMINOS_HOME) as it is now, kept
        in <file>: taken after the older copy's verb and before this code
        reads the store.
    older_channel_wire.py check <file> <machine> <channel id>...
        The store enrolled as <machine> and cut over to an endpoint stand-in
        in $MAWS_USER_DATA (the older-copy suite's machines are not enrolled
        before this), a real uplink run on it until every event of this
        machine's writers in each channel's log is up; then one line for each
        such writer, "<writer's session or `human`> <kind>...", in the order
        the stand-in first received them (its frames in order, and each
        frame's events in order), and "breaches <n>" with each breach of
        channel_wire.published (the frames) and channel_wire.written (the
        store) after it, one a line.

Run with this code's scripts first on sys.path ($SMINOS_SCRIPTS).
"""
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.environ.get("SMINOS_SCRIPTS") or os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts"))
sys.path.insert(0, HERE)

import channel_wire as wire  # noqa: E402
import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

ORG, URL = "org-1", "http://127.0.0.1:9"


def keep(path, before):
    with open(path, "w") as f:
        json.dump([[cid, w, seq, e] for (cid, w, seq), e in before.items()], f)


def kept(path):
    with open(path) as f:
        return {(cid, w, seq): e for cid, w, seq, e in json.load(f)}


def own_events(cid, machine):
    return [e for e in wire._log_events(os.environ["SMINOS_HOME"], cid)
            if e["writer"].split("/")[0].split(".")[0] == machine]


def first_received(ep, cid):
    """[(writer, [kind...])]: each writer's events in a channel's log in the order the stand-in first received
    them, across its frames and within each frame (a position sent again is counted where it first came), the
    writers by name: the upload order itself, never the positions sorted."""
    seen, out = set(), {}
    with ep.cv:
        frames = [f for _, f in ep.received if f.get("t") == "events" and f.get("project") == cid]
    for f in frames:
        for e in f.get("events") or []:
            key = (e.get("writer"), e.get("seq"))
            if key not in seen:
                seen.add(key)
                out.setdefault(e.get("writer"), []).append(str(e.get("kind")))
    return sorted(out.items())


def check(path, machine, ids):
    before = kept(path)
    sminos.write_json(rl10.identity_path(), {
        "org": ORG, "hub": URL, "name": machine, "former": {}, "ref": "machine-ref-1",
        "enrolled": "2026-11-10T00:00:00.000Z", "cutover": "2026-11-10T00:00:01.000Z", "build": "b"}, mode=0o600)
    sminos.forget_caches()
    org = {"projects": [{"id": p.id, "name": p.name, "kind": "hub", "retired": False} for p in sminos.known_logs()],
           "machines": [{"name": machine, "online": False}], "complete": True}
    ep = endpoint_standin.Endpoint(os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint"), org=org,
                                   identity={"org": ORG, "hub": URL, "name": machine, "former": [],
                                             "ref": "machine-ref-1", "enrolled": endpoint_standin.iso()})
    ep.start()
    halt, box = threading.Event(), {}
    thread = threading.Thread(target=lambda: box.update(kept=uplink.run_rl10(halt.is_set, halt)), daemon=True)
    thread.start()
    try:
        want = {(cid, e["writer"], e["seq"]) for cid in ids for e in own_events(cid, machine)}
        ep.wait_until(lambda: all(seq in ep.logs.get(cid, {}).get(w, {}) for cid, w, seq in want), timeout=60)
        time.sleep(0.5)   # what a tick after the uploads sends
        for cid in ids:
            for w, kinds in first_received(ep, cid):
                who = "human" if w.endswith("/human") else w.split("/", 1)[1]
                print(who, " ".join(kinds))
        breaches = wire.published(ep.received, ids, before) + wire.written(os.environ["SMINOS_HOME"], ids, machine,
                                                                           before)
        print("breaches %d" % len(breaches))
        for b in breaches:
            print(b)
    finally:
        halt.set()
        thread.join(30)
        if box.get("kept") is not None:
            box["kept"].close()
        ep.stop()


def main(argv):
    if argv[:1] == ["baseline"]:
        keep(argv[1], wire.baseline(os.environ["SMINOS_HOME"], argv[2:]))
    elif argv[:1] == ["check"]:
        check(argv[1], argv[2], argv[3:])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
