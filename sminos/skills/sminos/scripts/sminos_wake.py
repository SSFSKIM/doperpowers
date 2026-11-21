#!/usr/bin/env python3
"""sminos_wake — what a wake of a stopped thread reads and says, with no
effect of its own (T2 of
docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md, D2;
Interfaces §1 and §2 of docs/doperpowers/plans/2026-11-20-sminos-threads-t2.md).

- The engine's row of a session (row_of): its saved options, read with no
  lock and believed only for the moment; a row that cannot be read is
  UNREADABLE, never "no row", since the difference decides whether a first
  wake's flags may meet the engine's copy answer.
- The last turn's mode and model (last_turn), read backwards from the
  transcript's tail within TAIL_BOUND for a daemon's tick, or whole for a
  wake about to launch, each reading kept by the transcript's stat.
- The flags of a first wake (first_flags, first_wake), the names of what it
  does not carry, and the line a woken session reads after the message that
  woke it (line_note, line_text).
- Why a thread is not woken (not_woken), and whether a wake that failed is
  due again (wake_due), from the record's `waking` (sminos_threads, §7).

Nothing here launches, signals, locks or writes; the wake itself is
`sminos.resume_session`.
"""
import json
import os
import re
import sys
import time
import uuid

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import sminos  # noqa: E402


class _Unreadable:
    def __repr__(self):
        return "UNREADABLE"

    def __bool__(self):
        return False


UNREADABLE = _Unreadable()
# The modes that ask for approval (D2, "Not woken"); any other value, an unknown one included, does not (the owner).
ASKING = ("default", "manual", "plan", "acceptEdits")
REASONS = ("config", "transcript", "cwd", "protected", "mode")
TAIL_BOUND = 4 << 20      # how far back from its end a tick reads a transcript for the last turn
WAKE_RETRY = 60           # seconds after a first failed wake before the next; doubled per failure (§4)
WAKE_RETRY_MAX = 3600     # the most it waits
# How long a job a wake's banner named (`waking.job`) is taken for one still starting when its process has not been
# seen: three times the wake's own wait for it (SMINOS_UUID_POLL polls of SMINOS_POLL_INTERVAL, 30 of 2 s).
WAKE_GRACE = 180
_CHUNK = 1 << 16
_ROWS = {}                # row path → (its stat key, what it parsed to: any JSON value, or UNREADABLE)
_TURNS = {}               # transcript path → (its stat key, {"bounded": turn, "whole": turn})


# ------------------------------------------------------------ the row


def row_of(session):
    """The engine's row of the session (E8): `jobs/<first eight>/state.json`
    under the session's config dir, as a dict whose `sessionId` is the
    session. None: a `jobs` directory exists and holds no row for it.
    UNREADABLE: a file that does not parse or is no object, one whose
    `sessionId` is another session's, or a config dir with no `jobs`
    directory (an engine that keeps its rows elsewhere)."""
    session = str(session or "")
    if not sminos.UUID_RE.fullmatch(session):
        return UNREADABLE
    jobs = os.path.join(sminos.session_config_dir(session), "jobs")
    path = os.path.join(jobs, session[:8], "state.json")
    try:
        st = os.stat(path)
    except FileNotFoundError:
        _ROWS.pop(path, None)
        return None if os.path.isdir(jobs) else UNREADABLE
    except OSError:
        return UNREADABLE
    key = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    held = _ROWS.get(path)
    if held is None or held[0] != key:
        try:
            with open(path, encoding="utf-8") as f:
                parsed = json.load(f)
        except (OSError, ValueError):
            parsed = UNREADABLE
        held = _ROWS[path] = (key, parsed)
    # The file is every session's whose id begins with these eight: whose it is, is asked at each lookup.
    row = held[1]
    if not isinstance(row, dict) or row.get("sessionId") != session:
        return UNREADABLE
    return json.loads(json.dumps(row))


def row_options(row):
    """The row's `respawnFlags`, [] when it has none (or none of strings)."""
    flags = row.get("respawnFlags") if isinstance(row, dict) else None
    return list(flags) if isinstance(flags, list) and all(isinstance(t, str) for t in flags) else []


def row_failed(row):
    return isinstance(row, dict) and row.get("state") == "failed"


def _option(tokens, name):
    """The value of the last `name` among option tokens (`--name value` or `--name=value`), else ""."""
    value = ""
    for i, tok in enumerate(tokens):
        if tok == name and i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
            value = tokens[i + 1]
        elif tok.startswith(name + "="):
            value = tok[len(name) + 1:]
    return value


option = _option   # the value of an option among argv tokens, for the wake's launch (sminos.wake)


def options_mode(tokens):
    """The permission mode a list of options runs under, "" when it names none."""
    return _option(tokens, "--permission-mode") or (
        "bypassPermissions" if "--dangerously-skip-permissions" in tokens else "")


# ------------------------------------------------------------ the last turn


def last_turn(session, whole=False):
    """The mode and the model the session's last turn ran under (E14):
    `permissionMode` on its last prompt row (never a `permission-mode`
    metadata row: stale at a process's start), and `message.model` on its
    last assistant row whose `requestId` is set (a hook's row, `msg_hook_`,
    is no turn), sidechains aside. Each is the value; "" when the
    transcript was read to its start and holds none (or there is no
    transcript); None when not found within TAIL_BOUND, never with
    `whole`. Each reading is kept by the transcript's stat, so a tick reads
    a transcript only once it changed, and only its tail."""
    return _turn_at(transcript_file(session, whole), whole) or {"mode": "", "model": ""}


def transcript_file(session, whole=False):
    """The session's transcript on this machine as it is now, or "": the
    index's path (sminos.transcript_path; `whole`, a miss looked for again,
    transcript_now), and a path whose file has gone since it was indexed
    (the engine moved it, or it was deleted) looked for again in a fresh
    listing, never taken for a conversation."""
    path = sminos.transcript_now(session) if whole else sminos.transcript_path(session)
    if path and not os.path.isfile(path):
        path = sminos._transcript(session, 0.0)
    return path if path and os.path.isfile(path) else ""


def _turn_at(path, whole):
    """The last turn read from the transcript at `path`; None when there is no file there now."""
    if not path:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    held = _TURNS.get(path)
    if held is None or held[0] != key:
        held = _TURNS[path] = (key, {})
    got = held[1]
    if "whole" in got:
        return dict(got["whole"])
    if not whole and "bounded" in got:
        return dict(got["bounded"])
    turn = _read_turn(path, None if whole else TAIL_BOUND)
    if turn is None:
        return None
    got["whole" if whole or None not in turn.values() else "bounded"] = turn
    return dict(turn)


def _read_turn(path, budget):
    mode = model = None
    try:
        with open(path, "rb") as f:
            end = f.seek(0, os.SEEK_END)
            pos, head = end, b""
            while pos > 0 and (budget is None or end - pos < budget) and (mode is None or model is None):
                size = min(_CHUNK, pos) if budget is None else min(_CHUNK, pos, budget - (end - pos))
                pos -= size
                f.seek(pos)
                parts = (f.read(size) + head).split(b"\n")
                head = parts[0]
                for line in reversed(parts[1:]):
                    mode, model = _row_turn(line, mode, model)
                    if mode is not None and model is not None:
                        break
            if pos == 0 and (mode is None or model is None):
                mode, model = _row_turn(head, mode, model)
    except OSError:
        return None
    start = pos == 0
    return {"mode": mode if mode is not None else ("" if start else None),
            "model": model if model is not None else ("" if start else None)}


def _row_turn(line, mode, model):
    if not line or (mode is not None or b'"permissionMode"' not in line) and (
            model is not None or b'"assistant"' not in line):
        return mode, model
    try:
        r = json.loads(line)
    except ValueError:
        return mode, model   # a partial last line, or no row
    if not isinstance(r, dict) or r.get("isSidechain"):
        return mode, model
    if mode is None and r.get("type") == "user" and isinstance(r.get("permissionMode"), str) and r["permissionMode"]:
        mode = r["permissionMode"]
    msg = r.get("message")
    if model is None and r.get("type") == "assistant" and r.get("requestId") and isinstance(msg, dict) \
            and isinstance(msg.get("model"), str) and msg["model"] and msg["model"] != "<synthetic>" \
            and not str(msg.get("id") or "").startswith("msg_hook_"):
        model = msg["model"]
    return mode, model


# ------------------------------------------------------------ the flags


def asks(mode):
    """Whether a mode asks for approval: default, manual, plan, acceptEdits."""
    return mode in ASKING


def mode_flag(mode):
    """The `--permission-mode` value for a mode as a transcript or a row
    writes it: the mode itself, but `default`, which is passed as `manual`
    (E24)."""
    return "manual" if mode == "default" else mode


def _capped(mode, ceiling):
    """The mode, lowered to the ceiling when above it in sminos.PERMISSION_MODES'
    order (`manual` read as `default`); a mode outside that order is passed as
    it is, and a ceiling outside it is read as `default`, never as no cap (a
    spawn is refused under one, sminos_rpc.admit_spawn)."""
    order = sminos.PERMISSION_MODES
    m = "default" if mode == "manual" else mode
    c = "default" if ceiling == "manual" or ceiling not in order else ceiling
    if m in order and order.index(m) > order.index(c):
        return c
    return mode


def _launch(record):
    """(the record's launch, its options as recorded or None, those options' strings)."""
    launch = record.get("launch") if isinstance(record.get("launch"), dict) else {}
    options = launch.get("options") if isinstance(launch.get("options"), list) else None
    return launch, options, [t for t in options or [] if isinstance(t, str)]


def first_mode(record, turn, ceiling, accepted_bypass):
    """(the mode a first wake would run the thread under before the cap,
    the mode it passes): the last turn's, else the launch's recorded
    `--permission-mode`; lowered to the ceiling; `bypassPermissions` then
    lowered to `auto` unless the disclaimer was accepted (E22). ("", "")
    when neither is known. Reads nothing but the record and the turn
    given, so a check of eligibility touches no file the launch names."""
    mode = turn.get("mode") or _option(_launch(record)[2], "--permission-mode")
    if not mode:
        return "", ""
    passed = _capped(mode, ceiling)
    if passed == "bypassPermissions" and not accepted_bypass:
        passed = "auto"
    return mode, passed


def first_flags(record, turn, ceiling, accepted_bypass):
    """(flags, names not carried) for a first wake of the thread (§2):
    `--permission-mode` (the last turn's, else the launch's; capped by the
    machine's ceiling; `bypassPermissions` lowered to `auto` unless the
    engine's disclaimer was accepted, E22), `--model` (the last turn's,
    else the launch's), `--effort` and `--settings` (the launch's; a
    settings file that is gone is not passed, a relative one is read
    against the launch's directory), in that order. Never `--add-dir`,
    `--output-style` or a name. Not carried: every option of
    `launch.options` not passed and every name of `launch.dropped`; None
    when the record does not say what was dropped (no `options`, or a
    launch noted before T2)."""
    launch, options, opts = _launch(record)
    flags = []
    mode = first_mode(record, turn, ceiling, accepted_bypass)[1]
    if mode:
        flags += ["--permission-mode", mode_flag(mode)]
    model = turn.get("model") or _option(opts, "--model")
    if model:
        flags += ["--model", model]
    effort = _option(opts, "--effort")
    if effort:
        flags += ["--effort", effort]
    settings = _option(opts, "--settings")
    cwd = str(launch.get("cwd") or "")
    if settings and (os.path.isabs(os.path.expanduser(settings)) or cwd):
        path = os.path.join(cwd, os.path.expanduser(settings))
        if os.path.isfile(path):
            flags += ["--settings", os.path.abspath(path)]
    dropped = launch.get("dropped")
    if options is None or not isinstance(dropped, list):
        return flags, None
    names = sminos.threads_module().LAUNCH_OPTIONS
    passed = set(flags[::2])
    missing = []
    for name in [t for t in opts if t in names and t not in passed] + [d for d in dropped if isinstance(d, str)]:
        if name not in missing:
            missing.append(name)
    return flags, missing


def bypass_accepted(session):
    """Whether the user's settings in the session's config dir hold the
    engine's accepted bypass disclaimer (`skipDangerousModePermissionPrompt`,
    E22), without which a background launch in that mode is refused."""
    try:
        d = sminos.json_at(os.path.join(sminos.session_config_dir(session), "settings.json"))
    except (OSError, ValueError):
        return False
    return isinstance(d, dict) and d.get("skipDangerousModePermissionPrompt") is True


def passes_flags(record, session, row, flagless=False):
    """Whether a wake passes a first wake's flags (§3, W4): with no row
    (`None`) yes; with a readable one no; with one that cannot be read yes,
    unless the engine said the session keeps saved options (the record's
    `waking.saved`) or this is the pass after that answer (`flagless`, the
    wake's own retry). The one decision not_woken and the launch share."""
    if isinstance(row, dict):
        return False
    if row is None:
        return True
    return not flagless and not sminos.threads_module().waking(record, session).get("saved")


def first_wake(record, session):
    """first_flags for the session as a wake about to launch reads it: its
    last turn read whole, the machine's ceiling (sminos_policy), and the
    disclaimer of its config dir."""
    policy = sminos.sibling_module("sminos_policy").machine_policy()
    return first_flags(record, last_turn(session, whole=True), policy["ceiling"], bypass_accepted(session))


def wake_argv(session, flags):
    """The engine's arguments for a wake: never a positional after them (D2)."""
    return ["--bg", "--resume", session] + list(flags)


# ------------------------------------------------------------ the line


LINE_HEAD = sminos.LINE_START + (
    "A note from sminos on this machine, not from the sender above: you were woken in the background by this "
    "message, and your human is not watching this session unless they have attached to it since.")


def line_note(first, options, turn, not_carried=None, opened=""):
    """What `waking.line` holds for a wake about to launch (§7): `first`
    whether it is a first wake; `options` what it runs under (a first
    wake's flags, a later one's row options); the last turn's model beside
    them; for a first wake the names not carried (None: not known); how
    the thread was opened, the record's `opened`; and `at`, when it was
    written, before the launch, which no process of that launch started
    before. Its `short`, the job the launch's banner named, is added once
    the banner is read (sminos_threads.wake_job, wake_line_bound)."""
    options = [t for t in options or [] if isinstance(t, str)]
    return {"id": uuid.uuid4().hex[:12], "first": bool(first), "mode": options_mode(options),
            "model": _option(options, "--model"), "turn_model": str((turn or {}).get("model") or ""),
            "not_carried": (list(not_carried) if not_carried is not None else None) if first else [],
            "opened": str(opened or ""), "at": sminos.now(ms=True)}


def same_model(a, b):
    """Whether two names are one model as far as sminos can tell: the same
    name once lower-cased and a `[…]` suffix (a context window) dropped.
    An alias (`haiku`) is not resolved to the id it serves, which changes
    with the engine (E10: a row saved as `haiku` woke on 5.5 after a
    terminal turn on 4.5), so an alias and an id are two names, and the
    line says both."""
    a, b = (re.sub(r"\[[^\]]*\]$", "", str(x).strip().lower()) for x in (a, b))
    return bool(a) and a == b


def line_text(note):
    """The one paragraph of sminos's own that closes the first text pushed
    after a wake (D2, step 3), from its note (line_note): one line, whatever
    the names it says hold, since a reader finds it by its LINE_START at a
    line's start after the last frame."""
    mode, model = str(note.get("mode") or ""), str(note.get("model") or "")
    line = LINE_HEAD + (" You run in %s mode on %s." % (mode_flag(mode), model) if mode and model
                        else " You run under your saved options.")
    turn_model = str(note.get("turn_model") or "")
    if not note.get("first") and model and turn_model and not same_model(model, turn_model):
        line += (" Your last turn ran on %s; a background run keeps the options it last ran with in the "
                 "background." % turn_model)
    if note.get("first"):
        # A first wake is only a wake with no engine row: a spawned seat whose row is gone is one too, and never ran
        # in a terminal; a note with no `opened` (older code's) is not a human's.
        if note.get("opened") == "human":
            line += " The environment variables of the terminal or app you were opened in may differ here."
        missing = note.get("not_carried")
        if missing is None:
            line += " Other options you were last started with may not be carried here."
        elif missing:
            line += " Options you were last started with that are not carried here: %s." % ", ".join(missing)
    return " ".join(line.splitlines())


# ------------------------------------------------------------ not woken, and the schedule


def thread_cwd(record):
    """The thread's directory, absolute: a seat's where its session runs
    (sminos.seat_cwd), a thread its human opened its launch's; "" for none."""
    cwd = ""
    if record.get("opened") == "spawned":
        seat = sminos.reload_seat(record["thread"])
        cwd = sminos.seat_cwd(seat) if seat else ""
    if not cwd:
        cwd = str((record.get("launch") or {}).get("cwd") or "")
    return os.path.abspath(os.path.expanduser(cwd)) if cwd else ""


def not_woken(record, session, whole=False, flagless=False):
    """Why the thread is not woken (D2, "Not woken"), the first of REASONS
    that holds, else "": `config` (the session runs under another config
    dir), `transcript` (no conversation of it here), `cwd` (its directory
    missing or not a directory; one this process may not look at is taken
    on its word), `protected` (on macOS, a thread its human opened in a
    protected folder or in a directory that holds one: protected), `mode`
    (the mode its row runs it under, or its last
    turn's, asks for approval, or a first wake's lowered to the ceiling
    would: mode_case; a mode not found within the bound does not ask,
    `whole` reads on; `flagless`, the wake's retry with no flag, as
    passes_flags). Reads the record given, the files it names and
    policy_inputs, never the engine's job list, and takes no lock."""
    if sminos.foreign_config(session):
        return "config"
    path = transcript_file(session, whole)
    if not path:
        return "transcript"
    cwd = thread_cwd(record)
    if not cwd or (not sminos.read_refused(cwd) and not os.path.isdir(cwd)):
        return "cwd"
    if protected(record, cwd):
        return "protected"
    case = _mode_case(record, session, path, whole, flagless)
    if case is None:
        return "transcript"   # gone since it was found
    return "mode" if case else ""


def protected(record, cwd):
    """Whether a background launch of the thread in its directory `cwd`
    would stop at a prompt for its human (not_woken's `protected`): on
    macOS, a thread its human opened whose directory is in a protected
    folder (sminos.protected_folder) or holds one (sminos.protected_held,
    launch_refused's rule), whichever process asks. A spawned thread is
    resumed there as before T2. Decided from the path's string alone."""
    return sminos.TCC and record.get("opened") == "human" and bool(
        sminos.protected_folder(cwd) or sminos.protected_held(cwd))


def mode_case(record, session, whole=False, flagless=False):
    """Which mode keeps the thread from being woken (`not_woken`'s `mode`):
    "own" when a mode the thread would run under asks for approval of
    itself (its row's, its last turn's, or a first wake's before the cap:
    the launch's when no turn says one); "ceiling" when none does but the
    mode a first wake passes, lowered to the machine's ceiling, asks (the
    plan's Decision Log, "A first wake's capped mode decides `mode`"): the
    words a sender reads name the owner's remedy then, which raising the
    ceiling meets; "" for neither (or no transcript). A first wake is one
    passes_flags answers yes for (`flagless`, the wake's retry)."""
    return _mode_case(record, session, transcript_file(session, whole), whole, flagless) or ""


def _mode_case(record, session, path, whole, flagless):
    turn = _turn_at(path, whole)
    if turn is None:
        return None
    row = row_of(session)
    modes = [turn["mode"]] + ([options_mode(row_options(row))] if isinstance(row, dict) else [])
    if any(asks(m) for m in modes):
        return "own"
    if turn["mode"] is not None and passes_flags(record, session, row, flagless):
        policy = sminos.sibling_module("sminos_policy").machine_policy()
        own, passed = first_mode(record, turn, policy["ceiling"], True)
        if asks(own):
            return "own"
        if asks(passed):
            return "ceiling"
    return ""


def policy_inputs():
    """The files `not_woken` reads beyond the record's own (the machine's
    policy and the user settings whose `defaultMode` is its ceiling when it
    names none): what a memory of its answers is keyed on with them."""
    return [sminos.sibling_module("sminos_policy").policy_path(),
            os.path.join(sminos.home_dir(), ".claude", "settings.json")]


_KEPT = {}   # session → (its inputs' key but the directory's, the directory, its key, the reason, whether it is sure)


def _stat(path):
    try:
        st = os.stat(path) if path else None
    except OSError:
        return None
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_mode) if st else None


def _dir_key(record, cwd):
    """The thread's directory as the memory keys it: its stat, or, for one
    not_woken does not look into (a path this process may not read, and a
    thread held `protected`: protected), the path and the guard's answer,
    with what not_woken looks at of it, whether it is a directory, only
    where this process may look; never a look inside, nor its stat, which
    any file written in $HOME moves."""
    if cwd and (sminos.withheld(cwd) or protected(record, cwd)):
        return ("guarded", None if sminos.withheld(cwd) else os.path.isdir(cwd))
    return _stat(cwd)


def _inputs(record, session):
    """Every input not_woken reads but the thread's directory itself, as one
    value: the record, the config dir the session runs under, its
    transcript and that file's stat, a seat's file (where its directory is
    read), the engine's row as row_of reads it (the row file's stat, and
    with no file whether its `jobs` directory is there: no row is None in
    one and UNREADABLE without it, which passes_flags tells apart), and the
    files the ceiling is read from."""
    path = transcript_file(session)
    seat = sminos.meta_path(record["thread"]) if record.get("opened") == "spawned" else ""
    jobs = os.path.join(sminos.session_config_dir(session), "jobs")
    row = os.path.join(jobs, str(session)[:8], "state.json")
    return (json.dumps(record, sort_keys=True, default=str), sminos.foreign_config(session), path, _stat(path),
            _stat(seat), _stat(row) or os.path.isdir(jobs), tuple(_stat(f) for f in policy_inputs()))


def hold_reason(record, session):
    """not_woken as a view or a tick reads it (the bounded reading), kept by
    the stat of every input it reads (hold_key): a stopped thread asked
    about every tick reads nothing again until a file it rests on moved.
    An answer of "" whose last turn's mode was not found within the bound
    is not sure, and is asked again each time (from the turns kept, so it
    costs no reading): a wake's whole reading of the same transcript
    (W2) answers it from then on."""
    key = _inputs(record, session)
    held = _KEPT.get(session)
    if held is not None and held[0] == key and held[4] and held[2] == _dir_key(record, held[1]):
        return held[3]
    reason = not_woken(record, session)
    cwd = thread_cwd(record)
    sure = bool(reason) or (_turn_at(transcript_file(session), False) or {}).get("mode") is not None
    _KEPT[session] = (key, cwd, _dir_key(record, cwd), reason, sure)
    return reason


def published_reason(record, session):
    """hold_reason as the thread's machine publishes it (X3's `why`): a
    bounded reading that found no mode is read on to the transcript's
    start, once (kept by the file's stat, so no later tick reads it again),
    so that what is published is what a wake, which reads it whole, would
    decide (the sweep reads it so as it marks the thread stopped)."""
    reason = hold_reason(record, session)
    if not reason and (_turn_at(transcript_file(session), False) or {}).get("mode", "") is None:
        last_turn(session, whole=True)
        reason = hold_reason(record, session)
    return reason


def hold_key(record, session):
    """What hold_reason's answer rests on, as one value: its inputs and the
    thread's directory's key (_dir_key). Equal keys, the same answer (the
    daemon's memory of a pass that held, sminos_daemon.deliver_owed)."""
    key = _inputs(record, session)
    held = _KEPT.get(session)
    cwd = held[1] if held is not None and held[0] == key else thread_cwd(record)
    return key + (cwd, _dir_key(record, cwd))


def _seconds(name, default):
    try:
        v = float(os.environ.get("SMINOS_" + name, default))
    except ValueError:
        return float(default)
    return v if v >= 0 else float(default)


def deadline(record, session):
    """When a wake of the session falls due again (§4), in epoch seconds:
    WAKE_RETRY * 2 ** (failed - 1) seconds, at most WAKE_RETRY_MAX
    (SMINOS_WAKE_RETRY, SMINOS_WAKE_RETRY_MAX), after the last failure its
    record's `waking` names for it; None when it names none, or a failure
    whose time cannot be read (which holds nothing back)."""
    w = sminos.threads_module().waking(record, session)
    failed = w.get("failed")
    if type(failed) is not int or failed <= 0:
        return None
    at = sminos._ts_epoch(w.get("at"))
    if at is None:
        return None
    return at + min(_seconds("WAKE_RETRY", WAKE_RETRY) * 2.0 ** min(failed - 1, 64),
                    _seconds("WAKE_RETRY_MAX", WAKE_RETRY_MAX))


def starting(record, session, now=None):
    """The job a wake of the session accepted (`waking.job`: the banner
    named this session's job, its process not seen yet), while WAKE_GRACE
    (SMINOS_WAKE_GRACE) has not passed since: {"short", "at"}; None
    otherwise. While it is there no wake stops that job or launches again
    (sminos.wake) and the sweep neither marks the thread stopped nor ends
    it; past it, the job is one lingering as any other."""
    job = sminos.threads_module().waking(record, session).get("job")
    if not isinstance(job, dict) or not job.get("short"):
        return None
    at = sminos._ts_epoch(job.get("at"))
    if at is None or (time.time() if now is None else now) - at >= _seconds("WAKE_GRACE", WAKE_GRACE):
        return None
    return job


def wake_due(record, session, now=None):
    """Whether a wake of the session is due (§4): no deadline, or past it."""
    due = deadline(record, session)
    return due is None or (time.time() if now is None else now) >= due


def due_at(record, session):
    """The deadline while it is ahead (the daemon's memory of a held pass
    keeps it); None when a wake is due now."""
    due = deadline(record, session)
    return due if due is not None and time.time() < due else None
