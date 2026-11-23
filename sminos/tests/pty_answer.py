#!/usr/bin/env python3
"""A command on a controlling pty of its own, a person typing an answer at
its `[y/N]` prompt: what drives `confirmed` (sminos_visibility), which reads
/dev/tty itself, for the suites of CH2's M8.

As a module: run(argv, answer, cwd=None, env=None, deadline=60,
meanwhile=None) → (exit code, what it printed, whether it prompted).
`meanwhile()` runs once the prompt is shown and before the answer is
typed (what changes while a person reads it). At the deadline, or when
anything raises meanwhile, the child is killed and reaped, and at the
deadline the exit code is None: a prompt that never comes,
or a command that never ends, fails its test instead of hanging it.

As a script: pty_answer.py <answer> <command> [args...] prints what the
command printed and exits with its code, 124 (said on stderr) at the
deadline (PTY_ANSWER_DEADLINE seconds, 60 by default).
"""
import os
import pty
import select
import signal
import sys
import time


LAST_PID = None   # the child the last run started (for a test that it was reaped)


def run(argv, answer, cwd=None, env=None, deadline=60, meanwhile=None):
    global LAST_PID
    pid, fd = pty.fork()
    if pid == 0:
        try:
            if cwd:
                os.chdir(cwd)
            os.execvpe(argv[0], argv, os.environ if env is None else env)
        finally:
            os._exit(127)
    LAST_PID = pid
    out, prompted, end, code, reaped = b"", False, time.monotonic() + deadline, None, False
    try:
        while time.monotonic() < end:
            if not select.select([fd], [], [], 0.2)[0]:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:   # the child closed its side: it has ended
                break
            if not chunk:
                break
            out += chunk
            if not prompted and b"[y/N]" in out:
                prompted = True
                if meanwhile is not None:
                    meanwhile()
                os.write(fd, answer.encode() + b"\n")
        while time.monotonic() < end:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                code, reaped = os.waitstatus_to_exitcode(status), True
                break
            time.sleep(0.05)
    finally:
        # Whatever ended the wait (the deadline, or an exception: meanwhile's, a read's), the child is not left
        # running or unreaped.
        if not reaped:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
        os.close(fd)
    return code, out.decode("utf-8", "replace").replace("\r\n", "\n"), prompted


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: pty_answer.py <answer> <command> [args...]")
    deadline = float(os.environ.get("PTY_ANSWER_DEADLINE") or 60)
    code, out, _ = run(sys.argv[2:], sys.argv[1], deadline=deadline)
    sys.stdout.write(out)
    if code is None:
        sys.stderr.write("pty_answer: no end within %ss: killed\n" % deadline)
        sys.exit(124)
    sys.exit(code)


if __name__ == "__main__":
    main()
