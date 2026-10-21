#!/usr/bin/env python3
"""sminos_hub — this machine's enrollment at the desk hub (DX7 of the desk).

`sminos hub enroll` redeems a code the owner's browser built: a one-time
enrollment code, `smns-enroll-v1.` and the base64url of the JSON object {hub,
org, token, machine, key}, or a provisioning code, `smns-provision-v1.` over
{hub, org, token, prefix, key}, whose token is a reusable key's secret that
enrolls any name starting with its prefix (a VM's boot pipes it). The code
carries the org key, so it is read from a hidden prompt (or stdin when
piped), never from the command line, where the process listing shows it and
the shell's history keeps it; a code given as an argument is refused unread,
and no file is read for one. The CLI decodes either kind as the hub's
`decodeCode` does (tests/enroll_parity.py pins the two), redeems the token at
`POST <hub>/machine/enroll {token, machine}` for the machine's Access
service token, and stores what the uplink needs in `daemon/hub.json` (mode
0600, written whole): the hub, the org, the enrolled name, the service
token's id and secret, and the org key. The hub never sees the key; nothing
here prints or logs it, nor the secret.

`sminos hub check` asks the hub whether it still accepts that credential
and changes nothing; `sminos hub leave` revokes it at the hub and removes
hub.json. Both read the answer by one rule (`authenticated`): the Worker's
`403 not-enrolled` is a rejection at once, Access's 401 page only for a
credential past its propagation grace and again on a recheck, and anything
else decides nothing.

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
import contextlib
import fcntl
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
PROVISION_PREFIX = "smns-provision-v1."
# Each kind of code: its prefix, the words its refusals start with, its
# fields, the field that names a machine (or a name's start), and how a
# refusal calls that field.
KINDS = {
    "enroll": (CODE_PREFIX, "enrollment code", ("hub", "org", "token", "machine", "key"), "machine", "the machine name"),
    "provision": (PROVISION_PREFIX, "provisioning code", ("hub", "org", "token", "prefix", "key"), "prefix", "the prefix"),
}
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
    """A code DX7's decoder refuses; its whole message, in the hub's words
    (`enrollment code: no machine`, `provisioning code: no prefix`)."""


class Lost(Exception):
    """No answer came back from a redemption."""


def is_machine_name(name):
    return isinstance(name, str) and bool(MACHINE_RE.fullmatch(name)) and name.lower() not in RESERVED


def _no_constant(name):
    raise ValueError("%s is not JSON" % name)


def check_hub(hub, words):
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
        raise CodeRefused("%s: the hub is not a URL" % words)
    if not uplink.hub_admitted(hub):
        raise CodeRefused("%s: the hub is not https" % words)


def decode_code(text):
    """Either kind of code, tagged — {"kind": "enroll", hub, org, token,
    machine, key} or {"kind": "provision", hub, org, token, prefix, key} — or
    CodeRefused naming the first check that refuses it, in the order and the
    words of the hub's decodeCode, worded by the kind its prefix named."""
    kind = next((k for k, spec in KINDS.items() if isinstance(text, str) and text.startswith(spec[0])), None)
    if kind is None:
        raise CodeRefused("enrollment code: not smns-enroll-v1 or smns-provision-v1")
    prefix, words, fields, name_field, name_is = KINDS[kind]
    raw = codes.b64url_decode(text[len(prefix):])
    try:
        if raw is None:
            raise ValueError("not base64url")
        # TextDecoder's fatal UTF-8, which consumes one byte-order mark.
        d = json.loads(raw.decode("utf-8-sig"), parse_constant=_no_constant)
    except (ValueError, RecursionError):
        raise CodeRefused("%s: damaged" % words) from None
    if not isinstance(d, (dict, list)):
        raise CodeRefused("%s: damaged" % words)
    d = d if isinstance(d, dict) else {}  # an array is an object to JSON.parse, holding none of the fields
    for field in fields:
        if not isinstance(d.get(field), str) or d[field] == "":
            raise CodeRefused("%s: no %s" % (words, field))
    check_hub(d["hub"], words)
    if not is_machine_name(d[name_field]):
        raise CodeRefused("%s: %s is not admitted" % (words, name_is))
    key = codes.b64url_decode(d["key"])
    if key is None:
        raise CodeRefused("%s: the key is not base64url" % words)
    if len(key) != 32:
        raise CodeRefused("%s: the key is not 256 bits" % words)
    return {"kind": kind, **{field: d[field] for field in fields}}


# ------------------------------------------------------------- redemption


def redeem_once(hub, token, machine):
    """(status, answer object or None) of one `POST /machine/enroll`; Lost
    when no whole answer came back: none at all, a body cut short of its
    length, or a success whose body is no JSON object (an enrollment the hub
    may have made, whose secret this end never read)."""
    url = urllib.parse.urlsplit(hub)
    if url.scheme == "https":
        conn = uplink.HTTPSConnection(url.hostname, url.port, timeout=TIMEOUT)
    else:
        conn = uplink.HTTPConnection(url.hostname, url.port, timeout=TIMEOUT)
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


def refusal(status, answer, machine, code):
    """What to tell the human for an answer that is not an enrollment."""
    error, message = (answer or {}).get("error"), said((answer or {}).get("message"))
    return {
        "key-revoked": "this key was revoked at the hub: ask an admin for a new key",
        "key-expired": "this key has expired: ask an admin for a new key",
        "key-exhausted": "this key has enrolled all the machines it may: ask an admin for a new key or a higher cap",
        "prefix-mismatch": "this key does not enroll the name %s (%s): pass --name %s…" % (
            machine, message, code.get("prefix", "")),
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


@contextlib.contextmanager
def credential_lock():
    """Held while hub.json is written or removed: enroll's write and leave's
    check-and-remove never interleave."""
    path = daemon.daemon_path("hub.lock")
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def enrolled_hub():
    """This machine's hub, {url, org} (a .smns names only the org); exits
    when the machine is not enrolled."""
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
        sminos.die(str(e))
    if code["kind"] == "provision":
        # The key enrolls only names under its prefix (compared without case,
        # as the hub compares them): refused here, before anything is sent.
        machine = a.name or old
        if not is_machine_name(machine):
            sminos.die("this machine's name %s is not one the hub admits: pass --name %s…" % (machine, code["prefix"]))
        if not machine.lower().startswith(code["prefix"].lower()):
            sminos.die("the name %s does not start with this key's prefix %s: pass --name %s…" % (
                machine, code["prefix"], code["prefix"]))
    else:
        machine = a.name or (old if is_machine_name(old) else code["machine"])
    refuse_case_twin(machine, old, old_former)
    status, answer = redeem(code, machine)
    if status != 200 or answer is None:
        # name-taken has its own exit: a boot picks another name and runs the same code again.
        sminos.die(refusal(status, answer, machine, code), 3 if (answer or {}).get("error") == "name-taken" else 1)
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
    with credential_lock():
        sminos.write_json(path, {"hub": code["hub"], "org": code["org"], "machine": machine,
                                 "client_id": answer["client_id"], "client_secret": answer["client_secret"],
                                 "key": code["key"], "former": former, "enrolled": sminos.now()}, mode=0o600)
    sminos.forget_caches()
    sminos.daemon_log("hub: enrolled as %s at %s (org %s)%s" % (
        machine, code["hub"], code["org"], "" if machine == old else ", no longer as %s" % old))
    print("enrolled this machine as %s at %s (org %s); its credential is %s (mode 600)" % (
        machine, code["hub"], code["org"], path))
    if code["kind"] == "enroll" and not a.name and machine != code["machine"]:
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
    """What daemon/hub.json holds, read locally: exit 0 when a credential is
    held here, 1 when none. Whether the hub still accepts it is `check`'s."""
    d = held()
    if d is None:
        print("this machine is not enrolled at a hub (sminos hub enroll, then paste the code); it writes as %s"
              % sminos.host_name())
        sys.exit(1)
    former = d.get("former") if isinstance(d.get("former"), dict) else {}
    print("machine  %s\nhub      %s (org %s)\nformer   %s\nsince    %s" % (
        d.get("machine") or "?", d.get("hub") or "?", d.get("org") or "?",
        ", ".join("%s (%d sessions)" % (n, len(s) if isinstance(s, list) else 0) for n, s in former.items()) or "-",
        d.get("enrolled") or "?"))


# ------------------------------------------------------------- the hub's answer to the credential

ENROLLMENT_PATH = "/machine/enrollment"
# Access answers 401 with its own page to a service token it does not hold —
# deleted by a revocation, or minted and not yet at its edge (the deploy
# probe allows 60 s for that). So its 401 is a rejection only for a
# credential enrolled this long ago, and only when it holds on a recheck this
# long after the first (half as much again as the probe's bound, for a clock
# that jumped at boot and made `enrolled` read old).
ACCESS_GRACE_S = 600
ACCESS_RECHECK_S = 90
ACCESS_MARK = b"Cloudflare Access"


def recheck_after():
    try:
        return max(0.0, float(os.environ.get("SMINOS_ACCESS_RECHECK_S", ACCESS_RECHECK_S)))
    except ValueError:
        return ACCESS_RECHECK_S


def whole_body(resp):
    """The answer's body when it is known to be whole — read to the end its
    length declares, through a chunked body's last chunk, or to the close of a
    body with neither — and at most ANSWER_MAX bytes; else None. A bounded
    read stops at its bound, or returns what came before an early close,
    without raising: only the response's end being reached says the body is
    all there."""
    raw = resp.read(ANSWER_MAX)
    if not resp.isclosed() and resp.read(1):   # one byte more: the end (a chunked body's last chunk), or past the bound
        return None
    return raw if resp.isclosed() and not resp.length else None


def ask(cred, method, accepted):
    """One authenticated request to /machine/enrollment, read: ("accepted",
    answer), ("rejected", which), ("access", None) for Access's 401 page —
    which only `authenticated` decides — or ("other", what came). Only a
    whole answer is read as anything but other: a body cut short can say
    `not-enrolled`, or carry Access's mark, without being either."""
    url = urllib.parse.urlsplit(cred["hub"])
    conn = uplink.connection(cred, TIMEOUT)
    try:
        conn.request(method, url.path.rstrip("/") + ENROLLMENT_PATH,
                     headers={**uplink.admission(cred), "Accept": "application/json"})
        resp = conn.getresponse()
        raw = whole_body(resp)
    except http.client.IncompleteRead:
        return "other", "the hub's answer (%d) was cut short of its end" % resp.status
    except (OSError, http.client.HTTPException) as e:
        return "other", "the hub did not answer: %s" % (" ".join(str(e).split()) or type(e).__name__)
    finally:
        conn.close()
    if raw is None:
        return "other", "the hub's answer (%d) was not whole: cut short of its end, or longer than %d bytes" % (
            resp.status, ANSWER_MAX)
    if resp.status == 401:
        if ACCESS_MARK in raw:
            return "access", None
        return "other", "the hub answered 401 without Access's page: %s" % said(raw.decode("utf-8", "replace"))
    try:
        answer = json.loads(raw)
    except ValueError:
        answer = None
    if resp.status == 403 and isinstance(answer, dict) and answer.get("error") == "not-enrolled":
        return "rejected", "the hub answered not-enrolled"
    if resp.status == 200 and isinstance(answer, dict) and accepted(answer):
        return "accepted", answer
    return "other", "the hub answered %d %s" % (resp.status, said(raw.decode("utf-8", "replace")) or "with no body")


def authenticated(cred, method, accepted):
    """The hub's answer to the stored credential, by §6's rule, which `check`
    and `leave` share: ("accepted", answer); ("rejected", which) for the
    Worker's not-enrolled, at once, or for Access's 401 page to a credential
    past the propagation grace that holds on one recheck; else ("other", what
    came) — Access's 401 inside the grace among it, since a token minted
    minutes ago may not have reached Access's edge."""
    outcome, said_ = ask(cred, method, accepted)
    if outcome != "access":
        return outcome, said_
    enrolled = sminos._ts_epoch(cred.get("enrolled"))
    age = None if enrolled is None else time.time() - enrolled
    if age is None or age < ACCESS_GRACE_S:
        return "other", "Access answered 401 to a credential enrolled %s, which may not have reached Access's edge " \
                        "yet" % ("%d s ago" % age if age is not None else "at a time hub.json does not say")
    time.sleep(recheck_after())
    outcome, said_ = ask(cred, method, accepted)
    return ("rejected", "Access answered 401") if outcome == "access" else (outcome, said_)


def stored(undecided):
    """The credential hub.json holds, or None when this machine is not
    enrolled. A file it cannot use is said and ends the command with the
    verb's undecided exit: the hub cannot be asked about it, and nothing
    here replaces or removes it."""
    try:
        return uplink.load_credential()
    except uplink.CredentialBad as e:
        sminos.die("%s: the hub cannot be asked" % e, undecided)


def check(_a):
    """Whether the hub still accepts this machine's credential; changes
    nothing. Exit 0 accepted, 1 not enrolled here, 3 rejected, 4 undecided."""
    cred = stored(4)
    if cred is None:
        print("this machine is not enrolled at a hub")
        sys.exit(1)
    outcome, said_ = authenticated(cred, "GET", lambda a: a.get("org") == cred["org"]
                                   and a.get("machine") == cred["machine"])
    if outcome == "accepted":
        print("enrolled as %s at %s (org %s): accepted" % (cred["machine"], cred["hub"], cred["org"]))
    elif outcome == "rejected":
        sminos.die("the hub no longer accepts this machine's credential: %s" % said_, 3)
    else:
        sminos.die(said_, 4)


def leave(_a):
    """Ends this machine's enrollment at its hub; on the hub's acceptance, or
    its rejection of a credential already revoked, hub.json goes, and the
    daemon stops its uplink on its own. Anything else keeps it (exit 1)."""
    cred = stored(1)
    if cred is None:
        print("this machine is not enrolled at a hub: nothing to leave")
        return
    outcome, said_ = authenticated(cred, "DELETE", lambda a: a.get("revoked") == cred["machine"])
    if outcome == "other":
        sminos.die("%s — the credential is kept: run sminos hub leave again later" % said_, 1)
    if outcome == "accepted":
        line = "left the hub as %s" % cred["machine"]
    else:
        line = "the hub had already revoked %s" % cred["machine"]
    # The answer can take minutes (the recheck's wait); an enrollment that
    # replaced hub.json meanwhile is another, live credential, never this one's
    # to remove. The check and the removal are one step under enroll's lock.
    with credential_lock():
        try:
            now = uplink.load_credential()
        except uplink.CredentialBad:
            now = {}
        replaced = now is not None and (now.get("client_id"), now.get("client_secret")) != (
            cred["client_id"], cred["client_secret"])
        if now is not None and not replaced:
            os.remove(uplink.credential_path())
    sminos.forget_caches()
    sminos.daemon_log("hub: %s (%s, org %s)%s" % (line, cred["hub"], cred["org"],
                                                  "; hub.json was replaced meanwhile and is kept" if replaced else ""))
    if replaced:
        sminos.die("%s, but another enrollment replaced this machine's credential while leave ran (as %s): it is "
                   "kept — run sminos hub leave again to end that one" % (line, now.get("machine") or "?"), 1)
    print(line if outcome == "accepted" else line + "; the stale credential is removed")


def add_hub(path, smns, hub, a):
    """`project init --hub` where .smns exists: the hub field added, every
    other field kept as it is."""
    if a.name or a.remote:
        sminos.die("%s exists: --hub adds the hub to it and changes nothing else — drop --name and --remote" % path)
    if sminos.hub_wellformed(smns[3]) and smns[3]["org"] == hub["org"]:
        print("project %s is already a hub project of org %s" % (smns[1], hub["org"]))
        return
    if smns[3] is not None:
        sminos.die("project %s already names %s: its hub is not changed here" % (
            smns[1], "the hub of org %s" % smns[3]["org"] if sminos.hub_wellformed(smns[3])
            else "a hub that names no org, so it syncs through neither git nor a hub — fix its .smns by hand"), 1)
    # Under the mirror's sync lock: a sync of the project in flight ends
    # first, and every git phase after it reads the hub (ensure_mirrored), so
    # git and the uplink never feed this log at once. The registration both
    # read moves to this checkout under the same hold: a git phase run from
    # another checkout of the project finds the hub there.
    log = os.path.join(sminos.projects_root(), smns[0], "log")
    os.makedirs(log, mode=0o700, exist_ok=True)
    with daemon.sync_op(log):
        with open(path) as f:
            d = json.load(f)
        d["hub"] = {"org": hub["org"]}  # the URL is each machine's enrollment's (sminos.hub_here)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)  # committed: every clone reads it
        os.replace(tmp, path)
        sminos.forget_caches()
        sminos.project_path(sminos.resolve_project(os.path.dirname(path)), "log")
    print("project %s is now a hub project of org %s — commit .smns, so every clone syncs through the hub%s" % (
        smns[1], hub["org"],
        "; its remote %s is no longer synced live (it stays the log's archive)" % smns[2] if smns[2] else ""))


USAGE = "usage: sminos hub enroll [--name N] [--replace] (the code at its prompt, or on stdin) | show | check | leave"


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
    elif op in ("show", "check", "leave") and len(words) == 1:
        {"show": show, "check": check, "leave": leave}[op](None)
    else:
        sminos.die(USAGE)
