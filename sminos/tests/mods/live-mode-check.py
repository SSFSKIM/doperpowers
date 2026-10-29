#!/usr/bin/env python3
"""Live check that the bridge carries the session's permission mode (#160).

What only a running engine shows, in a terminal session with the bridge mod:
- a session that has neither switched its mode nor taken a prompt reports
  none: `read status` carries no `permissionMode` (the classic SessionStart
  input carries no mode);
- a Shift+Tab in the terminal, with no prompt and no model call, reaches
  `read status` and the heartbeat as it happens, through the engine's own
  `permission_mode_changed` collector record, in the engine's word — the
  record is the engine's telemetry, not a declared mode API, so a release
  that stops raising it fails here first;
- a prompt reports the mode it is submitted under.

The Shift+Tab checks spend nothing; the prompt spends one haiku call, so no
suite runs it: run it by hand with the model gateway's keys in the
environment. Isolation is live-bridge-check.py's, whose class it extends: a
temporary HOME whose .claude is the session's config dir, a temporary
SMINOS_HOME, a copy of the worktree's plugin, a tmux server of its own, the
gateway keys in a 0600 env file removed at the end.

    sminos/tests/mods/live-mode-check.py [--keep]     # --keep: leave the temp dir
"""

import importlib.util
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for
MODE_KEYS = ("permissionMode", "permissionModeAt", "permissionModeFrom")
RECORD = "permission_mode_changed"


class Mode(LB.Live):
    def read_status(self):
        s, body = LB.request(self.endpoint(), "POST", "/command?wait=8000", {"op": "read", "what": "status"}, timeout=15)
        return body.get("result") if s == 200 and body and body.get("ok") else None

    def mode(self):
        r = self.read_status() or {}
        return {k: r[k] for k in MODE_KEYS if k in r}

    def switch(self, before):
        """One Shift+Tab: the mode `read status` reports once it moved off
        `before`, how long that took, and whether a heartbeat carried it."""
        t = time.time()
        self.keys("BTab")
        now = wait_for("the switch to reach read status", 10,
                       lambda: (lambda m: m if m.get("permissionMode") not in (None, before) else None)(self.mode()),
                       every=0.05)
        took = time.time() - t
        beat = wait_for("a heartbeat carrying it", 8, lambda: self.seen(
            lambda e: e.get("type") == "heartbeat" and (e.get("state") or {}).get("permissionMode") == now["permissionMode"], t))
        return now, took, bool(beat)

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
        time.sleep(1.0)

        first = self.mode()
        self.check("a session that has neither switched nor taken a prompt reports no mode", first == {},
                   "read status: %s" % (first or "no permissionMode"))

        seen, mode = [], None
        for _ in range(6):
            now, took, beat = self.switch(mode)
            seen.append((now, took, beat))
            mode = now["permissionMode"]
            if mode == "default" and len(seen) > 1:
                break
        by_record = all(n.get("permissionModeFrom") == RECORD for n, _, _ in seen)
        self.check("each Shift+Tab reaches read status as it happens, by the engine's %s record" % RECORD,
                   seen and by_record and max(t for _, t, _ in seen) < 5,
                   "; ".join("%s from %s in %.2f s" % (n.get("permissionMode"), n.get("permissionModeFrom"), t) for n, t, _ in seen))
        self.check("each switch rides a heartbeat", all(b for _, _, b in seen), "%d of %d" % (sum(b for _, _, b in seen), len(seen)))
        self.check("the cycle comes back to the engine's word for manual, default", mode == "default",
                   " -> ".join(n.get("permissionMode") for n, _, _ in seen))

        before = self.mode()
        t = time.time()
        self.prompt("Reply with the single word ok. Use no tools.")
        self.wait_turn_end(t)
        after = self.mode()
        self.check("a prompt reports the mode it is submitted under",
                   after.get("permissionMode") == "default" and after.get("permissionModeFrom") == "UserPromptSubmit"
                   and after.get("permissionModeAt", 0) > before.get("permissionModeAt", 0),
                   "before %s, after %s" % (before, after))


def main():
    live = Mode("--keep" in sys.argv[1:])
    print("live mode check (%s):" % live.root, flush=True)
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
