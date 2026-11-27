"""What `task` asks of sminos (D5, Interfaces §10), as devcloud asks it
(`_sminos` and `session_creator` in devcloud/driver/context.py): the CLI is
found through TASK_SMINOS, then PATH, then the marketplace clone; each call
is bounded; silence, a non-zero exit or an answer of the wrong shape is no
answer."""
import json
import os
import pathlib
import re
import shutil
import subprocess

from record import one_line

TIMEOUT = 30
CLONE = ".claude/plugins/marketplaces/doperpowers/sminos/skills/sminos/scripts/sminos"
# As sminos writes the line (`session_address`): `alias#short (project on machine)` or `short (project on
# machine)`, a project name that may hold spaces and parentheses, a machine name that holds neither.
_ADDRESS = re.compile(r"^Sminos-Session: ((?:[^\n#]+#)?[0-9a-f]{8} \(.+ on [^\s()]+\))$", re.MULTILINE)
# sminos's ADDRESS_ALIAS_RE: an alias fit for the address line.
_ALIAS = re.compile(r"[^\s#()][^\n#()]{0,63}")
_THREAD_KEYS = {"thread": str, "session": str, "short": str, "alias": str, "machine": str, "ended": bool,
                "local": bool}


def find():
    """The sminos CLI's path, or None. TASK_SMINOS, when set, is the only
    place looked at."""
    named = os.environ.get("TASK_SMINOS")
    if named is not None:
        return named if named and os.access(named, os.X_OK) else None
    found = shutil.which("sminos")
    if found:
        return found
    clone = pathlib.Path(os.environ.get("HOME", "~")).expanduser() / CLONE
    return str(clone) if clone.exists() else None


def _run(args):
    cli = find()
    if not cli:
        return None
    try:
        return subprocess.run([cli] + args, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None


def session_id():
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or None


def address():
    """This session's address, or None: no session id, no sminos, or no
    `Sminos-Session:` line in its answer."""
    if not session_id():
        return None
    done = _run(["who"])
    if done is None or done.returncode != 0:
        return None
    m = _ADDRESS.search(done.stdout.strip())
    # An address is written into a record: a line break of any kind in it would start a key of its own.
    return m.group(1) if m and one_line(m.group(1)) else None


def thread(name):
    """`sminos who --thread=<name>`'s answer as a dict, or (None, why)."""
    done = _run(["who", "--thread=%s" % name])
    if done is None:
        return None, "no sminos answered" if find() else "no sminos CLI was found"
    if done.returncode != 0:
        said = done.stderr.strip().splitlines()
        return None, "exit %d%s" % (done.returncode, (": " + said[-1]) if said else "")
    try:
        data = json.loads(done.stdout)
    except ValueError:
        return None, "an answer that is not JSON"
    if not isinstance(data, dict) or not all(isinstance(data.get(k), t) for k, t in _THREAD_KEYS.items()):
        return None, "an answer of another shape"
    return data, ""


def thread_who(answer):
    """The part of a thread's address before its parentheses: `alias#short`,
    or `short` for a thread with no alias fit for the line."""
    alias, short = answer["alias"], answer["short"]
    return "%s#%s" % (alias, short) if alias and alias != short and _ALIAS.fullmatch(alias) else short


def thread_address(answer):
    """The address a thread's current session goes by, or None when the
    answer names no project."""
    project = answer.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("name"), str) or not project["name"]:
        return None
    address = "%s (%s on %s)" % (thread_who(answer), project["name"], answer["machine"])
    return address if one_line(address) else None


def say(text):
    """Send one message; True when sminos took it."""
    done = _run(["say", text])
    return done is not None and done.returncode == 0
