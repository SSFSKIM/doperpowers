#!/usr/bin/env python3
"""A command on a controlling pty of its own, a person typing an answer at
its `[y/N]` prompt: what drives `confirmed` (sminos_visibility), which reads
/dev/tty itself, for the suites of CH2's M8.

As a module: run(argv, answer, cwd=None, env=None, deadline=60,
meanwhile=None) → (exit code, what it printed, whether it prompted).
`meanwhile()` runs once the prompt is shown and before the answer is
typed (what changes while a person reads it). At the deadline the child is
killed and reaped, and the exit code is None: a prompt that never comes,
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


def run(argv, answer, cwd=None, env=None, deadline=60, meanwhile=None):
    pid, fd = pty.fork()
    if pid == 0:
        try:
            if cwd:
                os.chdir(cwd)
            os.execvpe(argv[0], argv, os.environ if env is None else env)
        finally:
            os._exit(127)
    out, prompted, end, code = b"", False, time.monotonic() + deadline, None
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
        else:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            pid = None
        if pid is not None:
            left = end - time.monotonic()
            while left > 0:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    code = os.waitstatus_to_exitcode(status)
                    break
                time.sleep(0.05)
                left = end - time.monotonic()
            else:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
    finally:
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
