#!/usr/bin/env python3
"""Probe (not a check): how a message the bridge delivers into a session
fares when the session is busy, and when the human stops the turn.

Each scenario delivers a message asking the model to include a word in its
reply, and reports what became of it: the bridge's `delivered` outcomes, the
turns that started, whether the model said the word, the input box after an
Esc, the transcript's user rows (uuid, parent, origin) and queue-operation
rows. A busy delivery goes in as a row read at the next tool round; an Esc
before the model answered hands the prompt back to the input box and the
human's edited resend goes in where it stood, which leaves a row given after
it on a branch no request reads (the bridge gives it again as the next turn
starts); a delivery made after an Esc meets the engine's refusal of plugin
prompts until the human speaks, so the bridge answers not-ok and sminos sends
it as an inbox frame, which starts a turn; a row given mid-turn that an Esc
left unread wakes the session through its inbox.

The two wake scenarios deliver through the CLI (`sminos send`, the path a
human's message takes) and say ok or FAIL: a turn starts after the delivery
and the model says the word, with no prompt from the human.

It spends model calls (haiku, short prompts). Isolation is
live-bridge-check.py's.

    tests/mods/live-delivery-cancel-probe.py [--keep] [SCENARIO...]

    busy        delivered mid-Bash; the turn runs on
    bash-esc    delivered mid-Bash, then Esc; the human asks for the word
    restore     delivered as the turn starts, Esc before any answer, edit, resend
    after-esc   Esc before any answer, delivered while the prompt is back in the box, edit, resend
    cli-after-esc  Esc mid-Bash; idle, delivered through the CLI: a turn starts and reads it
    esc-wake    delivered through the CLI mid-Bash, Esc before a request read it: the session wakes and reads it
"""

import glob
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(LB)

SCENARIOS = {"busy": "KIWI", "bash-esc": "MANGO", "restore": "PAPAYA", "after-esc": "PEAR",
             "cli-after-esc": "LYCHEE", "esc-wake": "GUAVA"}
ASK = "If an earlier message asked you to include a word, reply with that word only; otherwise reply NONE."


def is_main(e, kind, phase=None):
    return e.get("type") == kind and e.get("agentId") is None and (phase is None or e.get("phase") == phase)


class Probe(LB.Live):
    seq = 0

    def setup(self):
        super().setup()
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": ["Bash"]}}, f)

    def command(self, body):
        return LB.request(self.endpoint(), "POST", "/command?wait=8000", body, timeout=15)

    def deliver(self, word):
        Probe.seq += 1
        key = {"writer": "probe/w", "seq": Probe.seq}
        s, body = self.command({"op": "deliver", "key": key, "text": "Include the word %s in your reply." % word})
        print("   deliver answered: %s %s" % (s, body and body.get("result")), flush=True)
        return key

    def idle(self, seconds=150):
        deadline = time.time() + seconds
        calm = None
        while time.time() < deadline:
            s, body = self.command({"op": "ping"})
            if s == 200 and body["result"]["state"]["mainTurn"] is None:
                calm = calm or time.time()
                if time.time() - calm >= 3:
                    return
            else:
                calm = None
            time.sleep(0.5)
        raise TimeoutError("the session did not go idle")

    def rows(self):
        out = []
        for p in glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl")):
            with open(p) as f:
                out += [json.loads(l) for l in f if l.strip()]
        return out

    def text_since(self, t):
        return "".join(e["chunk"].get("text", "") for e in self.seen(
            lambda e: e.get("type") == "chunk" and e.get("agentId") is None and e["chunk"].get("kind") == "text", t))

    def show_pane(self, word):
        pane = self.pane()
        print("   pane after Esc (last lines):\n" + "\n".join("     " + l for l in pane.rstrip().splitlines()[-6:]), flush=True)
        print("   the input box holds the delivered text: %s" % (word in pane.rstrip().splitlines()[-3:-2][0] if len(pane.rstrip().splitlines()) > 3 else False), flush=True)

    def resend(self):
        self.keys("-l", " Keep it short.")
        time.sleep(0.3)
        self.keys("Enter")
        time.sleep(3)

    def report(self, name, t, key, word, before):
        self.idle()
        time.sleep(2)
        outcomes = [(e.get("outcome"), e.get("reason"), (e.get("uuid") or "")[:8]) for e in self.seen(
            lambda e: e.get("type") == "delivered" and e.get("key") == key, t)]
        starts = [str(e.get("text"))[:60] for e in self.seen(lambda e: is_main(e, "turn", "start"), t)]
        rows = self.rows()[before:]
        qops = [(r.get("operation"), r.get("reason")) for r in rows if r.get("type") == "queue-operation"]
        users = []
        for r in rows:
            if r.get("type") != "user":
                continue
            c = r["message"]["content"]
            text = c if isinstance(c, str) else " ".join(b.get("text", b.get("type")) for b in c)
            users.append((r.get("uuid", "")[:8], (r.get("parentUuid") or "")[:8], (r.get("origin") or {}).get("kind"), text[:60]))
        said = self.text_since(t)
        print("== %s" % name)
        print("   delivered outcomes: %s" % outcomes)
        print("   main turns started: %s" % starts)
        print("   model said %s: %s" % (word, word in said))
        print("   queue ops: %s" % qops)
        print("   user rows (uuid, parent, origin, text):")
        for u in users:
            print("     %s" % (u,))
        print("   model text (end): %r" % said[-160:], flush=True)

    def bash_turn(self, t):
        m = "SLEPT%d" % int(t)
        self.prompt("Run exactly this Bash command, then reply in one short sentence: "
                    "python3 -c 'import time; time.sleep(12); print(\"%s\")'" % m)
        LB.wait_for("the Bash call", 90, lambda: self.seen(
            lambda e: is_main(e, "tool", "call") and e.get("tool") == "Bash" and m in json.dumps(e.get("input")), t))
        time.sleep(1.5)

    def busy(self, word):
        t, before = time.time(), len(self.rows())
        self.bash_turn(t)
        key = self.deliver(word)
        sent = time.time()
        LB.wait_for("the next request", 60, lambda: self.seen(lambda e: is_main(e, "step", "start"), sent))
        with self.lock:
            at = next(w for w, e in self.events if w >= sent and is_main(e, "step", "start"))
        print("   the next request began %.1f s after the delivery" % (at - sent), flush=True)
        self.report("busy", t, key, word, before)

    def bash_esc(self, word):
        t, before = time.time(), len(self.rows())
        self.bash_turn(t)
        key = self.deliver(word)
        time.sleep(1.5)
        self.keys("Escape")
        time.sleep(3)
        self.idle()
        self.prompt(ASK)
        time.sleep(3)
        self.report("bash-esc", t, key, word, before)

    def restore(self, word):
        t, before = time.time(), len(self.rows())
        self.prompt("Write a 150-word poem about rivers. Use no tools.")
        LB.wait_for("the turn's start", 30, lambda: self.seen(lambda e: is_main(e, "turn", "start"), t))
        key = self.deliver(word)
        self.keys("Escape")
        print("   a chunk before the Esc: %s" % bool(self.seen(lambda e: e.get("type") == "chunk" and e.get("agentId") is None, t)))
        time.sleep(3)
        self.show_pane(word)
        self.resend()
        self.report("restore", t, key, word, before)

    def after_esc(self, word):
        t, before = time.time(), len(self.rows())
        self.prompt("Write a 150-word poem about lakes. Use no tools.")
        LB.wait_for("the turn's start", 30, lambda: self.seen(lambda e: is_main(e, "turn", "start"), t))
        self.keys("Escape")
        print("   a chunk before the Esc: %s" % bool(self.seen(lambda e: e.get("type") == "chunk" and e.get("agentId") is None, t)))
        time.sleep(2)
        key = self.deliver(word)
        time.sleep(2)
        self.show_pane(word)
        self.resend()
        self.report("after-esc", t, key, word, before)

    def send(self, word):
        """A human's message through the CLI, as `sminos send` delivers it."""
        r = subprocess.run([self.sminos(), "send", LB.NAME, "Include the word %s in your reply." % word],
                           cwd=self.work, env=self.local_env(), capture_output=True, text=True, timeout=60)
        print("   sminos send exited %d: %s" % (r.returncode, (r.stdout + r.stderr).strip().replace("\n", " | ")), flush=True)
        return r

    def woke(self, name, sent, word, cli):
        """Waits for a main turn started after `sent` that says the word, and says ok or FAIL."""
        try:
            LB.wait_for("a turn that says %s" % word, 120, lambda: word in self.text_since(sent))
        except TimeoutError:
            pass
        self.idle()
        starts = [str(e.get("text"))[:90] for e in self.seen(lambda e: is_main(e, "turn", "start"), sent)]
        said = word in self.text_since(sent)
        print("== %s" % name)
        print("   main turns started after the delivery: %s" % starts)
        print("   %s  a turn started after the delivery" % ("ok  " if starts else "FAIL"))
        print("   %s  the model said %s, with no prompt from the human" % ("ok  " if said else "FAIL", word))
        if cli is not None:
            stopped = "was stopped (Esc)" in cli.stderr + cli.stdout
            print("   the CLI said the session was stopped: %s" % stopped, flush=True)
        self.results.append((name, bool(starts) and said, ""))

    def cli_after_esc(self, word):
        t = time.time()
        self.bash_turn(t)
        self.keys("Escape")
        time.sleep(3)
        self.idle()
        sent = time.time()
        r = self.send(word)
        self.woke("cli-after-esc", sent, word, r)

    def esc_wake(self, word):
        t = time.time()
        self.bash_turn(t)
        sent = time.time()
        r = self.send(word)
        LB.wait_for("the delivered row", 20, lambda: self.seen(
            lambda e: e.get("type") == "delivered" and e.get("outcome") == "entered", sent))
        self.keys("Escape")
        read = self.seen(lambda e: is_main(e, "step", "start"), sent)
        print("   a request began between the delivery and the Esc: %s" % bool(read), flush=True)
        time.sleep(1)
        self.woke("esc-wake", sent, word, r)

    def run(self, scenarios):
        self.setup()
        self.start_session()
        sock_dir = os.path.join(self.smh, "bridge")
        found = LB.wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                                if n.endswith(".sock") and not n.startswith(".")]
                            if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        LB.wait_for("the endpoint to answer", 20, self.status)
        threading.Thread(target=self.subscribe_forever, daemon=True).start()
        LB.wait_for("the subscription", 10, lambda: self.subscriptions > 0)
        for s in scenarios:
            getattr(self, s.replace("-", "_"))(SCENARIOS[s])
            self.idle()


def main():
    args = [a for a in sys.argv[1:] if a != "--keep"]
    scenarios = args or list(SCENARIOS)
    for s in scenarios:
        if s not in SCENARIOS:
            sys.exit("unknown scenario %s (one of %s)" % (s, ", ".join(SCENARIOS)))
    p = Probe("--keep" in sys.argv[1:])
    print("delivery cancel probe (%s):" % p.root, flush=True)
    try:
        p.run(scenarios)
    except Exception as e:  # noqa: BLE001
        print("  the probe stopped: %s: %s" % (type(e).__name__, e))
        print("  pane:\n" + "\n".join("    " + l for l in p.pane().rstrip().splitlines()[-25:]))
    finally:
        p.cleanup()
    failed = [r[0] for r in p.results if not r[1]]
    if p.results:
        print("wake scenarios: %s" % ("all ok" if not failed else "FAILED: " + ", ".join(failed)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
