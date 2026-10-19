#!/usr/bin/env python3
"""Live check of an async question across a resume, against the engine itself.

What only a running engine shows, pinned so a release that breaks it fails
loudly: a `--bg` job's async question (the ask mod's) is pending on its
bridge; the job is stopped with the question open; `claude --bg --resume
<session>`, with nothing else on the line, continues it under its own id; and
the question is pending on the new bridge again, under its call's id, and
answered from outside it reaches the model. The engine runs the SessionStart
hooks, where the ask mod reads the open asks back, while the plugin's
session.start still waits on its tool registrations (2.1.303), so the bridge
starts after the asks are read: it raises them itself.

It spends model calls (haiku, short prompts), so no suite runs it: run it by
hand with the model gateway's keys in the environment. Isolation is
live-control-check.py's (whose class it extends).

    sminos/tests/mods/live-ask-resume-check.py [--keep]
"""

import glob
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_control_check", os.path.join(HERE, "live-control-check.py"))
LC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LC)
LB = LC.LB
wait_for = LC.wait_for
NAME = "arlive"
ASK_TOOL = "mcp__sminos__AskUserQuestion"
PROMPT = ("Call your question tool once, with async true: which color do I prefer, Red or Blue. "
          "Then end your turn saying waiting.")
DELIVERY = "The human responded to your async AskUserQuestion (call %s)"


def text_of(row):
    """A user row's text: its string content, or its text blocks joined."""
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


class AskResume(LC.Control):
    def setup(self):
        super().setup()
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": ["Bash", ASK_TOOL]}}, f)

    def holders(self, sid):
        """The engine's records of live processes holding the session."""
        out = []
        for p in glob.glob(os.path.join(self.cfg, "sessions", "*.json")):
            try:
                with open(p) as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            if rec.get("sessionId") == sid and LB._alive(rec.get("pid", 0)):
                out.append(rec)
        return out

    def bridge(self, sock, url):
        try:
            s, body = LB.request(sock, "GET", url, timeout=5)
        except OSError:
            return None
        return body if s == 200 else None

    def pending(self, sock):
        return ((self.bridge(sock, "/requests") or {}).get("pending")) or []

    def run(self):
        self.setup()
        self.claude(["--bg", "--plugin-dir", self.plugin, "--model", "haiku", "-n", NAME, PROMPT])
        rec = wait_for("the job's record", 60, lambda: self.record(NAME))
        sid = rec["sessionId"]
        self.jobs.append(rec.get("jobId"))
        sock = os.path.join(self.smh, "bridge", sid + ".sock")
        asked = wait_for("the async question on the bridge", 180, lambda: [
            p for p in self.pending(sock) if p.get("async") is True and p.get("tool") == ASK_TOOL])
        rid = asked[0]["request"]
        self.idle(sock)
        first = (self.bridge(sock, "/status") or {}).get("pid")
        self.check("the job's async question is pending on its bridge", len(asked) == 1 and first,
                   "request %s, bridge pid %s" % (rid, first))

        self.claude(["stop", rec.get("jobId")], timeout=120)
        wait_for("the job's end", 120, lambda: not self.holders(sid))
        r = self.claude(["--bg", "--resume", sid], timeout=120)
        held = wait_for("the resumed job holding the session", 120, lambda: self.holders(sid))
        self.jobs += [h.get("jobId") for h in held]
        wait_for("the resumed job's bridge", 60, lambda: (self.bridge(sock, "/status") or {}).get("pid") not in (None, first)
                 and (self.bridge(sock, "/status") or {}).get("ready") is True)
        self.check("the stopped job comes back under its own id", [h.get("kind") for h in held] == ["bg"],
                   "%s; holders %s" % (r.stdout.strip().splitlines()[:1], [(h.get("kind"), h.get("jobId")) for h in held]))
        try:
            again = wait_for("the question pending again", 30, lambda: [p for p in self.pending(sock) if p.get("request") == rid])
        except TimeoutError:
            again = []
        self.check("on its resume, the open question is pending on the bridge again, under its call's id",
                   again and again[0].get("async") is True and again[0].get("tool") == ASK_TOOL,
                   "pending %s" % [p.get("request") for p in self.pending(sock)])
        if not again:
            return

        # `sminos answer … 2` takes the second option, whatever its label: the
        # delivery quotes the question too, so it is matched as `="<label>"`.
        label = asked[0]["input"]["questions"][0]["options"][1]["label"]
        r = self.cli("answer", NAME, rid, "2")
        settled = wait_for("its settlement", 60, lambda: [
            s for s in (self.bridge(sock, "/requests") or {}).get("settled") or [] if s.get("request") == rid])
        delivered = wait_for("the answer delivered to the model", 120, lambda: [
            row for row in self.transcript_rows(sid) if row.get("type") == "user"
            and DELIVERY % rid in text_of(row) and '="%s"' % label in text_of(row)])
        self.check("answered from outside after the resume, it is settled answered and reaches the model",
                   r.returncode == 0 and settled[-1].get("outcome") == "answered" and settled[-1].get("by") == "cli"
                   and delivered,
                   "%s; option 2 %r; settled %s" % (r.stdout.strip(), label, settled[-1]))


def main():
    live = AskResume("--keep" in sys.argv[1:])
    print("live ask-resume check (%s):" % live.root, flush=True)
    try:
        live.run()
    except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
        live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
    finally:
        live.cleanup()
    failed = [r for r in live.results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(live.results) - len(failed),
                                         len(live.results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
