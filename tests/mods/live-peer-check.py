#!/usr/bin/env python3
"""Live check that a peer's message reaches a bridged session as a peer's.

What only a running engine shows, in a terminal session with the bridge mod:
- a peer session's `sminos send` (a `say` in the log, written by a session)
  reaches the idle session through its inbox socket, never the bridge: the
  session starts a turn on it, its transcript keeps the row with origin
  `peer` named by the frame's sender (the engine read the peer envelope's
  `from-name`), wrapped as the engine wraps a peer message, and no row
  carries it as the human's words; and the session, which has no sminos
  skill to read (its SKILL.md is left out of the plugin copy), answers the
  peer through the reply line the frame closes with (`sminos say @<short>`),
  recorded in the project's log;
- a peer's `sminos say` during a running turn is read in that turn, at its
  next tool round;
- the owner's `sminos send` (sminos run with no session) still reaches the
  same session through the bridge, as the human's words (origin `plugin`,
  `asUser`).

It spends model calls (haiku, short prompts), so no suite runs it: run it by
hand with the model gateway's keys in the environment. Isolation is
live-bridge-check.py's, whose class it extends: a temporary HOME whose
.claude is the session's config dir, a temporary SMINOS_HOME, a copy of the
worktree's plugin, a tmux server of its own, the gateway keys in a 0600 env
file removed at the end.

    tests/mods/live-peer-check.py [--keep]     # --keep: leave the temp dir (its transcript included)
"""

import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
NAME = LB.NAME
wait_for = LB.wait_for
PEER = "scout"
PEER_SID = str(uuid.uuid4())
# The engine's peer wrapping as a reader finds it (MAWS's parsePeerMessage reads the same):
# an optional header, then the envelope sminos wrote, named by its sender.
ENVELOPE = re.compile(r'(?:^|\n)<cross-session-message from-name="%s">\n' % PEER)


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text") or "" for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


class Peer(LB.Live):
    def setup(self):
        super().setup()
        # Bash runs without a dialog: the reply and the mid-turn check need it.
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": ["Bash"]}}, f)
        # No sminos context: the session reaches the CLI only through the frame.
        os.unlink(os.path.join(self.plugin, "skills", "sminos", "SKILL.md"))
        # The peer, a member of the project: a live process the engine's
        # session registry names (as a session's record would), joined on sight.
        os.makedirs(os.path.join(self.cfg, "sessions"), exist_ok=True)
        holder = subprocess.Popen(["sleep", "3600"])
        self.procs.append(holder)
        with open(os.path.join(self.cfg, "sessions", "%d.json" % holder.pid), "w") as f:
            json.dump({"pid": holder.pid, "sessionId": PEER_SID, "cwd": self.work, "kind": "interactive",
                       "name": PEER, "nameSource": "user", "status": "idle"}, f)

    def peer_log(self):
        """The project log's events addressed to the peer."""
        out = []
        for p in glob.glob(os.path.join(self.smh, "projects", "*", "log", "*.jsonl")):
            with open(p) as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if any(isinstance(r, dict) and r.get("session") == PEER_SID for r in e.get("to") or []):
                        out.append(e)
        return out

    def cli(self, *args, peer=False):
        env = self.local_env()
        if peer:
            env["CLAUDE_CODE_SESSION_ID"] = PEER_SID
        return subprocess.run([self.sminos(), *args], cwd=self.work, env=env, capture_output=True, text=True,
                              timeout=120)

    def rows(self):
        out = []
        for p in glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl")):
            with open(p) as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        return out

    def carrying(self, word):
        """The transcript's rows whose message or attachment carries `word`."""
        return [r for r in self.rows() if r.get("type") in ("user", "attachment") and word in json.dumps(
            [r.get("message"), r.get("attachment")])]

    def main_text(self, since):
        return "".join(e["chunk"].get("text") or "" for e in self.seen(
            lambda e: e.get("type") == "chunk" and e.get("agentId") is None and e["chunk"].get("kind") == "text", since))

    def turn_starts(self, since, word):
        return self.seen(lambda e: e.get("type") == "turn" and e.get("phase") == "start" and e.get("agentId") is None
                         and word in str(e.get("text")), since)

    def idle(self, seconds=120):
        def quiet():
            try:
                s, body = LB.request(self.endpoint(), "POST", "/command?wait=8000", {"op": "ping"}, timeout=15)
            except OSError:
                return False
            return s == 200 and body["result"]["state"]["mainTurn"] is None
        calm = None
        deadline = time.time() + seconds
        while time.time() < deadline:
            if quiet():
                calm = calm or time.time()
                if time.time() - calm >= 2:
                    return
            else:
                calm = None
            time.sleep(0.5)
        raise TimeoutError("the session did not go idle")

    def describe(self, rows):
        return [(r.get("type"), (r.get("origin") or {}).get("kind"), (r.get("origin") or {}).get("name"),
                 (r.get("attachment") or {}).get("type")) for r in rows]

    def run(self):
        self.setup()
        self.start_session()
        sock_dir = os.path.join(self.smh, "bridge")
        found = wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                             if n.endswith(".sock") and not n.startswith(".")]
                         if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        wait_for("the endpoint to answer", 20, self.status)
        threading.Thread(target=self.subscribe_forever, daemon=True).start()
        wait_for("the subscription", 10, lambda: self.subscriptions > 0)
        self.idle()

        # -- a peer's send to the idle session
        t = time.time()
        r = self.cli("send", NAME, "Reply with exactly the word PEACH.", "--from", PEER, peer=True)
        wait_for("the peer's turn", 90, lambda: self.turn_starts(t, "PEACH"))
        self.wait_turn_end(t)
        rows = self.carrying("Reply with exactly the word PEACH")
        users = [r for r in rows if r.get("type") == "user"]
        texts = [text_of((r.get("message") or {}).get("content")) for r in users]
        asuser = [r for r in users if (r.get("origin") or {}).get("asUser") is True]
        bridged = self.seen(lambda e: e.get("type") == "delivered", t)
        self.check("a peer's send to the idle session starts a turn on it, through its inbox and not the bridge",
                   r.returncode == 0 and "sent" in r.stdout and not bridged,
                   "%s; bridge deliveries %s; answered %r" % (r.stdout.strip(), bridged, self.main_text(t)[-40:]))
        self.check("its row is a peer message named by its sender, wrapped as the engine wraps one, never the human's",
                   len(users) == 1 and (users[0].get("origin") or {}).get("kind") == "peer"
                   and (users[0].get("origin") or {}).get("name") == PEER and ENVELOPE.search(texts[0] or "")
                   and not asuser,
                   "rows %s; text %r" % (self.describe(rows), (texts[0] if texts else "")[:200]))
        replies = [e for e in self.peer_log() if e.get("kind") == "say"
                   and str(e.get("writer", "")).endswith("/" + self.session)]
        self.check("the session, with no sminos context, answers the peer through the frame's reply line",
                   texts and ('say "@%s <your reply>"]' % PEER_SID[:8]) in texts[0]
                   and any("PEACH" in str(e.get("text")) for e in replies),
                   "replies %s" % [(e.get("from"), e.get("text")) for e in replies])
        self.check("the pane draws it as a message from another session, not as a prompt",
                   not re.search(r"❯ *\[sminos message from %s" % PEER, self.pane()),
                   "pane tail %r" % self.pane().rstrip().splitlines()[-6:])
        self.idle()

        # -- a peer's say during a running turn
        marker = "lpc%d" % os.getpid()
        t = time.time()
        self.prompt("Run exactly this Bash command, then run it once more, then reply with one short sentence: "
                    "python3 -c 'import time; time.sleep(6); print(\"%s\")'" % marker)
        wait_for("the Bash call", 90, lambda: self.seen(
            lambda e: e.get("type") == "tool" and e.get("phase") == "call" and e.get("agentId") is None
            and marker in json.dumps(e.get("input")), t))
        r = self.cli("say", "@%s Also include the word GRAPE in your final sentence." % NAME, peer=True)
        self.wait_turn_end(t, 180)
        self.idle(180)
        starts = self.seen(lambda e: e.get("type") == "turn" and e.get("phase") == "start" and e.get("agentId") is None, t)
        rows = self.carrying("Also include the word GRAPE")
        self.check("a peer's say during a turn is read in that turn, as a peer's",
                   r.returncode == 0 and "GRAPE" in self.main_text(t) and len(starts) == 1 and rows
                   and all((x.get("origin") or {}).get("asUser") is not True for x in rows),
                   "%s; %d turn(s); rows %s; answered %r" % (r.stdout.strip(), len(starts), self.describe(rows),
                                                            self.main_text(t)[-80:]))

        # -- the owner's send: the human's words, through the bridge
        t = time.time()
        r = self.cli("send", NAME, "Reply with exactly the word PLUM.")
        wait_for("the owner's turn", 90, lambda: self.turn_starts(t, "PLUM"))
        self.wait_turn_end(t)
        users = [x for x in self.carrying("Reply with exactly the word PLUM") if x.get("type") == "user"]
        origin = users[0].get("origin") if users else None
        self.check("the owner's send still reaches the session through the bridge, as the human's words",
                   r.returncode == 0 and len(users) == 1 and isinstance(origin, dict) and origin.get("asUser") is True
                   and self.seen(lambda e: e.get("type") == "delivered" and e.get("outcome") == "submitted", t)
                   and "PLUM" in self.main_text(t),
                   "%s; origin %s" % (r.stdout.strip(), origin))
        if self.keep:
            print("  transcript: %s" % glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl")))


def main():
    live = Peer("--keep" in sys.argv[1:])
    print("live peer check (%s):" % live.root, flush=True)
    try:
        live.run()
    except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
        live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
        print("  pane at the failure:\n" + "\n".join("    " + l for l in live.pane().rstrip().splitlines()[-25:]))
    finally:
        live.cleanup()
    failed = [r for r in live.results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(live.results) - len(failed), len(live.results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
