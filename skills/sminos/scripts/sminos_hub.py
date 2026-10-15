#!/usr/bin/env python3
"""sminos_hub — this machine's enrollment at the desk hub (DX7 of the desk).

`sminos hub enroll` redeems an enrollment code the owner's browser built:
`smns-enroll-v1.` and the base64url of the JSON object {hub, org, token,
machine, key}. The code carries the org key, so it is read from a hidden
prompt (or stdin when piped), never from the command line, where the process
listing shows it and the shell's history keeps it; a code given as an
argument is refused unread. The CLI decodes it as the hub's `decodeEnrollmentCode`
does (tests/sminos/enroll_parity.py pins the two), redeems the one-time token
at `POST <hub>/machine/enroll {token, machine}` for the machine's Access
service token, and stores what the uplink needs in `daemon/hub.json` (mode
0600, written whole): the hub, the org, the enrolled name, the service
token's id and secret, and the org key. The hub never sees the key; nothing
here prints or logs it, nor the secret.

The enrolled name is this machine's one name in sminos (`host_name()`): every
writer it creates afterwards is `<name>/…`, hub project or not, because the
hub takes from a machine only the writers under its name. It defaults to the
current host name when the hub would admit it, so most enrollments rename
nothing; `--name` claims another. The names the machine wrote under before
are kept in hub.json as `former`, each with the sessions it held under it
then, and `is_self` counts those sessions under that name as this machine's —
so its seats and members stay its own across a rename, while another machine
that enrolls under the former name stays another machine. What it wrote under
a former name stays local. A name that differs from the current one or a
former one only in case is refused: DX7 compares names without case, and a
file system that ignores case would make the two names' writers one file.

`sminos project init --hub` writes the enrolled hub into .smns (`{url, org}`);
a project whose .smns names a hub is never synced through git.
"""

import argparse
import getpass
import glob
import http.client
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

CODE_PREFIX = "smns-enroll-v1."
FIELDS = ("hub", "org", "token", "machine", "key")
# DX7: a letter or digit, then up to 62 of letters, digits, `.`, `_`, `-`;
# never `hub` or `legacy` in any case (the log's `hub/` and `legacy/` writers).
MACHINE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
RESERVED = ("hub", "legacy")
REDEEM_PATH = "/machine/enroll"
# A redemption whose answer is lost is redeemed again with the same token and
# name (DX7: that rotates the credential), this many times in all.
ATTEMPTS = 3
TIMEOUT = 30
ANSWER_MAX = 1 << 16


class CodeRefused(ValueError):
    """An enrollment code DX7's decoder refuses; the reason in its words."""


class Lost(Exception):
    """No answer came back from a redemption."""


def is_machine_name(name):
    return isinstance(name, str) and bool(MACHINE_RE.fullmatch(name)) and name.lower() not in RESERVED


def _no_constant(name):
    raise ValueError("%s is not JSON" % name)


def check_hub(hub):
    """DX7's hub: an https URL, or http on a loopback host. Stricter than a
    WHATWG parser on spellings no browser's origin serializes to (blanks or
    controls anywhere, `https:host`, `127.1`), which the uplink could not
    reach as written."""
    try:
        url = urllib.parse.urlsplit(hub)
        url.port  # noqa: B018 — a port that is no number is no URL
    except ValueError:
        url = None
    if url is None or not url.scheme or not url.hostname or any(c.isspace() or not c.isprintable() for c in hub):
        raise CodeRefused("the hub is not a URL")
    if not uplink.hub_admitted(hub):
        raise CodeRefused("the hub is not https")


def decode_code(text):
    """The enrollment code's {hub, org, token, machine, key}, or CodeRefused
    naming the first check that refuses it, in the order and the words of
    the hub's decodeEnrollmentCode."""
    if not isinstance(text, str) or not text.startswith(CODE_PREFIX):
        raise CodeRefused("not smns-enroll-v1")
    raw = codes.b64url_decode(text[len(CODE_PREFIX):])
    try:
        if raw is None:
            raise ValueError("not base64url")
        # TextDecoder's fatal UTF-8, which consumes one byte-order mark.
        d = json.loads(raw.decode("utf-8-sig"), parse_constant=_no_constant)
    except (ValueError, RecursionError):
        raise CodeRefused("damaged") from None
    if not isinstance(d, (dict, list)):
        raise CodeRefused("damaged")
    d = d if isinstance(d, dict) else {}  # an array is an object to JSON.parse, holding none of the fields
    for field in FIELDS:
        if not isinstance(d.get(field), str) or d[field] == "":
            raise CodeRefused("no %s" % field)
    check_hub(d["hub"])
    if not is_machine_name(d["machine"]):
        raise CodeRefused("the machine name is not admitted")
    key = codes.b64url_decode(d["key"])
    if key is None:
        raise CodeRefused("the key is not base64url")
    if len(key) != 32:
        raise CodeRefused("the key is not 256 bits")
    return {field: d[field] for field in FIELDS}


# ------------------------------------------------------------- redemption


def redeem_once(hub, token, machine):
    """(status, answer object or None) of one `POST /machine/enroll`; Lost
    when no whole answer came back: none at all, a body cut short of its
    length, or a success whose body is no JSON object (an enrollment the hub
    may have made, whose secret this end never read)."""
    url = urllib.parse.urlsplit(hub)
    if url.scheme == "https":
        conn = http.client.HTTPSConnection(url.hostname, url.port, timeout=TIMEOUT)
    else:
        conn = http.client.HTTPConnection(url.hostname, url.port, timeout=TIMEOUT)
    try:
        conn.request("POST", url.path.rstrip("/") + REDEEM_PATH, body=json.dumps({"token": token, "machine": machine}),
                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        resp = conn.getresponse()
        raw = resp.read(ANSWER_MAX)
        # A bounded read returns what came before an early close, short of
        # the length the answer announced, without raising.
        cut = bool(resp.length)
    except (OSError, http.client.HTTPException) as e:
        raise Lost(" ".join(str(e).split()) or type(e).__name__) from None
    finally:
        conn.close()
    if cut:
        raise Lost("the answer ended after %d bytes, short of its length" % len(raw))
    try:
        answer = json.loads(raw)
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        if resp.status == 200:
            raise Lost("a 200 whose body is no JSON object")
        answer = None
    return resp.status, answer


def redeem(code, machine):
    """The hub's answer to redeeming the code under `machine`, a lost answer
    redeemed again (the same token and name rotate the credential)."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return redeem_once(code["hub"], code["token"], machine)
        except Lost as e:
            lost = e
        if attempt < ATTEMPTS:
            time.sleep(attempt)
    sminos.die("no answer from %s to %d redemptions (%s): run the same command again once it answers — the same "
               "code and name rotate any credential it minted meanwhile" % (code["hub"], ATTEMPTS, lost), 1)


def said(text):
    """A hub's message, one line, bounded: it is printed."""
    return " ".join(str(text or "").split())[:300]


def refusal(status, answer, machine):
    """What to tell the human for an answer that is not an enrollment."""
    error, message = (answer or {}).get("error"), said((answer or {}).get("message"))
    return {
        "bad-shape": "the hub refused the redemption's shape (%s): this sminos and the hub disagree on DX7 — "
                     "update sminos" % message,
        "bad-name": "the hub does not admit the name %s: pick another with --name" % machine,
        "unknown-token": "the hub does not know this code's token: the code is mistyped or is another hub's — "
                         "ask the web for a new code",
        "expired": "this code has expired: ask the web for a new code and enroll with it",
        "confirmed": "this code is spent: the machine it enrolled has connected — ask the web for a new code",
        "token-used": "this code was redeemed under another name (%s): enroll with that name (--name), or ask the "
                      "web for a new code" % message,
        "name-taken": "another machine of this org is enrolled as %s: pick another name — run "
                      "sminos hub enroll --name <another name> and paste the same code at the prompt" % machine,
        "busy": "a redemption of this code is in flight at the hub: run the same command again in a moment",
        "mint-failed": "the hub could not mint this machine's service token (%s): run the same command again — "
                       "the same code and name rotate it" % message,
    }.get(error) or "the hub answered %d%s%s%s" % (
        status, " " + said(error) if error else " without a DX7 error", ": " + message if message else "",
        " — run the same command again" if status >= 500 else "")


# ------------------------------------------------------------- the verbs


def held():
    """The credential this installation holds, as stored ({} when its file is
    unreadable), or None when it never enrolled."""
    path = uplink.credential_path()
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}


def enrolled_hub():
    """This machine's hub as .smns names it, {url, org}; exits when the
    machine is not enrolled."""
    d = held()
    if not (d and isinstance(d.get("hub"), str) and isinstance(d.get("org"), str) and d["hub"] and d["org"]):
        sminos.die("this machine is not enrolled at a hub: run sminos hub enroll first, and paste the code the web "
                   "gives at its prompt", 1)
    return {"url": d["hub"], "org": d["org"]}


def read_code():
    """The enrollment code from a hidden prompt on a terminal, or from stdin
    when piped; surrounding blanks (a paste's newline) are not the code's."""
    try:
        if sys.stdin.isatty():
            text = getpass.getpass("enrollment code (from the web; not echoed): ")
        else:
            text = sys.stdin.read(1 << 16)
    except (EOFError, KeyboardInterrupt):
        text = ""
    text = text.strip()
    if not text:
        sminos.die("no enrollment code: paste it at the prompt, or pipe it on stdin")
    return text


def sessions_under(name):
    """The sessions this installation held under the machine name `name`:
    each with a writer file `<name>.<session>.jsonl` in a project log here,
    and each a seat record whose `host` is `name` holds."""
    held_ = set()
    prefix = name + "."
    for path in glob.glob(os.path.join(glob.escape(sminos.projects_root()), "*", "log", glob.escape(prefix) + "*.jsonl")):
        session = os.path.basename(path)[len(prefix):-len(".jsonl")]
        if sminos.UUID_RE.match(session):
            held_.add(session)
    for s in sminos.seats():
        if s.get("host") == name and s.get("current"):
            held_.add(s["current"])
    return sorted(held_)


def refuse_case_twin(machine, old, former):
    """Exit when `machine` differs from this machine's name now, or a name it
    wrote under before, only in case. DX7 compares machine names without
    case, and on a file system that ignores case `<Name>.human.jsonl` and
    `<name>.human.jsonl` are one file: the new writer would go on from the
    old one's seq, in a file labelled by its first event."""
    def twin(name):
        return name != machine and name.lower() == machine.lower()
    if twin(old):
        said_as, keep = "%s, the name this machine writes under," % old, old
    else:
        name = next((n for n in former if twin(n)), None)
        if name is None:
            return
        said_as, keep = "%s, a name this machine wrote under before," % name, name
    sminos.die("the machine name %s differs from %s only in case: machine names are compared without case, and on a "
               "file system that ignores case the two would share their writer files. Keep %s (--name %s), or claim "
               "a name that differs in more than case" % (machine, said_as, keep, keep))


def enroll(a):
    if a.code:
        # Refused unread and never echoed: the code is already exposed in argv.
        sminos.die("an enrollment code is never given on the command line: it carries the org key, which every "
                   "process can read in argv and the shell keeps in its history. Run sminos hub enroll%s with no "
                   "code and paste it at the prompt (or pipe it on stdin); ask the web for a new code if this one "
                   "may have been seen" % ((" --name %s" % a.name if is_machine_name(a.name) else "")
                                           + (" --replace" if a.replace else "")))
    if a.name and not is_machine_name(a.name):
        # The value is not repeated: it may be a code typed in the wrong place.
        sminos.die("--name takes an admitted machine name: a letter or digit, then up to 62 letters, digits, "
                   "'.', '_' or '-'; never hub or legacy")
    before = held()
    if before is not None and not a.replace:
        sminos.die("this machine is already enrolled at %s as %s (org %s): a new code would replace that identity — "
                   "pass --replace to do so" % (before.get("hub") or "?", before.get("machine") or "?",
                                                before.get("org") or "?"), 1)
    old, old_former = sminos.machine_identity()
    if a.name:
        refuse_case_twin(a.name, old, old_former)  # before the code is asked for
    try:
        code = decode_code(read_code())
    except CodeRefused as e:
        sminos.die("enrollment code: %s" % e)
    machine = a.name or (old if is_machine_name(old) else code["machine"])
    refuse_case_twin(machine, old, old_former)
    status, answer = redeem(code, machine)
    if status != 200 or answer is None:
        sminos.die(refusal(status, answer, machine), 1)
    if not (all(isinstance(answer.get(k), str) and answer[k] for k in ("org", "machine", "client_id", "client_secret"))
            and answer["org"] == code["org"] and answer["machine"] == machine):
        sminos.die("the hub answered the redemption for org %s as %s, not for org %s as %s: nothing is stored" % (
            said(answer.get("org")), said(answer.get("machine")), code["org"], machine), 1)
    # Each name this installation wrote under before, with the sessions it held
    # under it: is_self's evidence, so a rename keeps them this machine's while
    # another machine enrolled under the old name stays another (oldest first).
    former = {name: sorted(held_) for name, held_ in old_former.items() if name != machine}
    if old != machine:
        former[old] = sorted(set(former.get(old, ())) | set(sessions_under(old)))
    path = uplink.credential_path()
    sminos.write_json(path, {"hub": code["hub"], "org": code["org"], "machine": machine,
                             "client_id": answer["client_id"], "client_secret": answer["client_secret"],
                             "key": code["key"], "former": former, "enrolled": sminos.now()}, mode=0o600)
    sminos.forget_caches()
    sminos.daemon_log("hub: enrolled as %s at %s (org %s)%s" % (
        machine, code["hub"], code["org"], "" if machine == old else ", no longer as %s" % old))
    print("enrolled this machine as %s at %s (org %s); its credential is %s (mode 600)" % (
        machine, code["hub"], code["org"], path))
    if not a.name and machine != code["machine"]:
        print("The code proposed %s; this machine keeps its own name, %s, so nothing it wrote is renamed. To be "
              "%s instead, run sminos hub enroll --name %s --replace and paste a new code at the prompt (this code "
              "is now bound to %s)." % (code["machine"], machine, code["machine"], code["machine"], machine))
    if machine != old:
        print("This machine now writes as %s, no longer as %s; its seats and members stay its own. Events already "
              "written under %s stay on this machine: in a hub project they never reach the hub or any other machine "
              "(the hub takes from this machine only %s/… writers)." % (machine, old, old, machine))
    if os.environ.get("DAEMON_HOST") and os.environ["DAEMON_HOST"] != machine:
        print("DAEMON_HOST (%s) is no longer read: the enrolled name is this machine's name." % os.environ["DAEMON_HOST"])
    print("The daemon's uplink connects with it within a minute (sminos daemon status); a project syncs through the "
          "hub once its .smns names it: sminos project init --hub, in its repository.")


def show(_a):
    d = held()
    if d is None:
        print("this machine is not enrolled at a hub (sminos hub enroll, then paste the code); it writes as %s"
              % sminos.host_name())
        return
    former = d.get("former") if isinstance(d.get("former"), dict) else {}
    print("machine  %s\nhub      %s (org %s)\nformer   %s\nsince    %s" % (
        d.get("machine") or "?", d.get("hub") or "?", d.get("org") or "?",
        ", ".join("%s (%d sessions)" % (n, len(s) if isinstance(s, list) else 0) for n, s in former.items()) or "-",
        d.get("enrolled") or "?"))


def add_hub(path, smns, hub, a):
    """`project init --hub` where .smns exists: the hub field added, every
    other field kept as it is."""
    if a.name or a.remote:
        sminos.die("%s exists: --hub adds the hub to it and changes nothing else — drop --name and --remote" % path)
    if smns[3] == hub:
        print("project %s is already a hub project of %s (org %s)" % (smns[1], hub["url"], hub["org"]))
        return
    if smns[3] is not None:
        sminos.die("project %s already names %s: its hub is not changed here" % (
            smns[1], "the hub %s (org %s)" % (smns[3]["url"], smns[3]["org"]) if sminos.hub_wellformed(smns[3])
            else "a hub that is not {url, org}, so it syncs through neither git nor a hub — fix its .smns by hand"), 1)
    # Under the mirror's sync lock: a sync of the project in flight ends
    # first, and every git phase after it reads the hub (ensure_mirrored), so
    # git and the uplink never feed this log at once.
    log = os.path.join(sminos.projects_root(), smns[0], "log")
    os.makedirs(log, mode=0o700, exist_ok=True)
    with daemon.sync_op(log):
        with open(path) as f:
            d = json.load(f)
        d["hub"] = hub
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)  # committed: every clone reads it
        os.replace(tmp, path)
    print("project %s is now a hub project of %s (org %s) — commit .smns, so every clone syncs through the hub%s" % (
        smns[1], hub["url"], hub["org"],
        "; its remote %s is no longer synced live (it stays the log's archive)" % smns[2] if smns[2] else ""))


USAGE = "usage: sminos hub enroll [--name N] [--replace] (the code at its prompt, or on stdin) | show"


def enroll_args(words):
    """`hub enroll`'s words read by hand, so nothing on the command line is
    ever printed back: --name N (or --name=N), --replace, and whether any
    other word came — a code, most likely, which enroll refuses unread."""
    a = argparse.Namespace(name="", replace=False, code=False)
    i = 0
    while i < len(words):
        w = words[i]
        if w == "--replace":
            a.replace = True
        elif w == "--name" and i + 1 < len(words):
            a.name = words[i + 1]
            i += 1
        elif w.startswith("--name="):
            a.name = w[len("--name="):]
        else:
            a.code = True
        i += 1
    return a


def cmd_hub(words):
    """The `hub` verb. Its words reach no parser that echoes them, and no
    message here names one it did not accept."""
    op = words[0] if words else ""
    if op == "enroll":
        enroll(enroll_args(words[1:]))
    elif op == "show" and len(words) == 1:
        show(None)
    else:
        sminos.die(USAGE)
