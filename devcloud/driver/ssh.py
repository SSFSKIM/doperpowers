"""SSH to the hosts (§8.3): this driver Mac's own key, made on first use, its
public half written to the profile's `driver-keys/<machine>.pub`, and a
`known_hosts` of the driver's own whose entries are keyed by the server
(`HostKeyAlias`), never by its address — Hetzner gives a deleted server's
address to the next one within minutes."""

import collections
import os
import pathlib
import selectors
import signal
import subprocess
import time

Result = collections.namedtuple("Result", "code out err marker")
Result.__new__.__defaults__ = (False,)
# The code a run reports when its own timeout ended it, as ssh reports a lost connection.
LOST = 255


class Ssh:
    def __init__(self, paths, machine, run=subprocess.run, popen=subprocess.Popen):
        self.paths = paths
        self.machine = machine
        self._run = run
        self._popen = popen

    # --- the key --------------------------------------------------------------

    def ensure_key(self):
        """This driver's public key, made on first use; written to the
        profile's driver-keys/<machine>.pub when that file lacks it."""
        key = self.paths.key
        if not key.exists():
            key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"devcloud-{self.machine}",
                       "-f", str(key)], check=True, capture_output=True, timeout=60)
        public = pathlib.Path(f"{key}.pub").read_text().strip()
        mine = self.paths.profile / "driver-keys" / f"{self.machine}.pub"
        if not mine.exists() or mine.read_text().strip() != public:
            mine.parent.mkdir(parents=True, exist_ok=True)
            mine.write_text(public + "\n")
        return public

    # --- connections ----------------------------------------------------------

    def argv(self, target, alias, user="root", connect_timeout=10, tty=False, person=False):
        """`person`: the person's own SSH identity (their agent and default
        keys) instead of the driver's key, for a machine to adopt, which
        knows only theirs, and for checking its release (§6.5)."""
        identity = [] if person else ["-i", str(self.paths.key), "-o", "IdentitiesOnly=yes"]
        argv = ["ssh", *identity, "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={self.paths.known_hosts}",
                "-o", f"HostKeyAlias={alias}", "-o", f"ConnectTimeout={connect_timeout}",
                "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3", "-o", "LogLevel=ERROR"]
        argv += ["-t"] if tty else ["-T"]
        return argv + ["--", f"{user}@{target}"]

    def run(self, target, alias, command, *, user="root", input=None, timeout=60, connect_timeout=10,
            person=False):
        """`command` (one shell line) on the host; `input` (bytes) on its stdin."""
        argv = self.argv(target, alias, user, connect_timeout, person=person) + [command]
        try:
            done = self._run(argv, input=input if input is not None else b"", capture_output=True,
                             timeout=timeout)
        except subprocess.TimeoutExpired as expired:
            return Result(LOST, _text(expired.stdout), _text(expired.stderr) + "\n(timed out)")
        return Result(done.returncode, _text(done.stdout), _text(done.stderr))

    def stream(self, target, alias, command, *, user="root", timeout=600, marker=None):
        """`command`'s stdout read as it comes, so a line `marker` is seen
        even when the connection drops right after it (the departure's
        `ready-to-logout`, §4.2)."""
        argv = self.argv(target, alias, user) + [command]
        proc = self._popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           start_new_session=True)
        out, err, seen = [], [], False
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ, out)
        sel.register(proc.stderr, selectors.EVENT_READ, err)
        end = time.monotonic() + timeout
        open_streams = 2
        while open_streams:
            left = end - time.monotonic()
            if left <= 0:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                return Result(LOST, "".join(out), "".join(err) + "\n(timed out)", seen)
            for key, _ in sel.select(timeout=min(left, 1.0)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    sel.unregister(key.fileobj)
                    open_streams -= 1
                    continue
                key.data.append(chunk.decode(errors="replace"))
                if marker and key.data is out and marker in "".join(out):
                    seen = True
        return Result(proc.wait(), "".join(out), "".join(err), seen)

    def interactive(self, target, alias, command, *, user="root"):
        argv = self.argv(target, alias, user, tty=command is None or os.isatty(0))
        return subprocess.call(argv + ([command] if command is not None else []))

    def forget(self, alias):
        """Drops the server's host key, at its deletion."""
        if self.paths.known_hosts.exists():
            self._run(["ssh-keygen", "-R", alias, "-f", str(self.paths.known_hosts)], capture_output=True,
                      timeout=30)
            old = pathlib.Path(f"{self.paths.known_hosts}.old")
            if old.exists():
                old.unlink()


def _text(data):
    if data is None:
        return ""
    return data.decode(errors="replace") if isinstance(data, bytes) else data
