#!/usr/bin/env python3
"""What a wake reads and says, the record's field, and the test engine
(T2's M1: docs/doperpowers/plans/2026-11-20-sminos-threads-t2.md, the
milestone's "Proves"; Interfaces §1, §2, §7 and §8).

- The engine's row of a session: found, not found, and unreadable in each
  of its three forms (a file that does not parse, another session's, no
  `jobs` directory).
- The last turn's mode and model, read backwards from the transcript's
  tail: past hook rows and metadata rows, beyond the bound (`None`, then
  the value on the whole reading), and with no turn at all.
- Each mode's flag; the flags of a first wake and what it does not carry;
  the line a woken session reads.
- Each reason a thread is not woken, and their order; `wake_due`'s schedule;
  `waking` ignored when it names another session, and its writers.
- The test engine of §8, driven through the argument vectors
  `docs/doperpowers/research/2026-11-17-sminos-channels/wake-spike-2.md`
  records, in both its forms (the Python twin and the shell stub of
  run-sminos-tests.sh, which hands a wake to the twin): a wake with no
  message, a frame pushed and its turn, a later wake, a copy and each of
  its notes, a worker that fails before it starts, and each switch.

Hermetic: HOME and SMINOS_HOME are temporary, fresh for each test
(test_threads.Machine); the engine is `wake_engine.py`, first on PATH, its
state a directory of the test's.
Run: python3 -B sminos/tests/test_wake.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import Machine, sminos, threads  # noqa: E402
import sminos_policy  # noqa: E402
import sminos_wake as wake  # noqa: E402
import wake_engine  # noqa: E402

ENGINE = os.path.join(HERE, "wake_engine.py")
RUNNER = os.path.join(HERE, "run-sminos-tests.sh")


def line_of(content):
    """(the text before it, the line) when a text an inbox took carries a wake's line as §2 lays it out: the
    envelope's body is the pushed text, an empty line, the line (one line opening with `[sminos] `), then the reply
    line alone when the frame names a session to answer; None when it carries none so placed."""
    body = re.fullmatch(r"<cross-session-message[^>]*>\n(.*)\n</cross-session-message>", content, re.S).group(1)
    m = re.fullmatch(r"(.*[^\n])\n\n(\[sminos\] [^\n]*)(?:\n\[To reply, run in Bash: [^\n]*\])?", body, re.S)
    return (m.group(1), m.group(2)) if m else None


def wait_for(pred, timeout=10, step=0.02):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(step)
    return pred()


def rows(*items):
    return "".join(json.dumps(r) + "\n" for r in items)


def prompt(mode, text="work"):
    return {"type": "user", "permissionMode": mode, "message": {"role": "user", "content": text}}


def answer(model, rid="req_1"):
    return {"type": "assistant", "requestId": rid,
            "message": {"id": "msg_" + rid, "model": model, "role": "assistant",
                        "content": [{"type": "text", "text": "ok"}]}}


def hook_row(model):
    return {"type": "assistant", "requestId": None,
            "message": {"id": "msg_hook_1", "model": model, "role": "assistant", "content": []}}


class Wakes(Machine):
    """A machine whose sessions have transcripts and, when a test writes one, an engine row; its
    policy's ceiling `bypassPermissions` unless a test sets another (ceiling)."""

    def setUp(self):
        super().setUp()
        self.ceiling("bypassPermissions")

    def ceiling(self, mode=None):
        """The machine's policy file naming `mode` as its ceiling; None: no policy file."""
        path = sminos_policy.policy_path()
        if mode is None:
            if os.path.exists(path):
                os.unlink(path)
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"ceiling": mode}, f)

    def config(self):
        return os.path.join(os.environ["HOME"], ".claude")

    def transcript(self, sid, text=""):
        d = os.path.join(self.config(), "projects", "p-work")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, sid + ".jsonl")
        with open(path, "a") as f:
            f.write(text)
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        sminos.forget_caches()
        return path

    def row(self, sid, body=None, raw=None):
        d = os.path.join(self.config(), "jobs", sid[:8])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "state.json"), "w") as f:
            f.write(raw if raw is not None else json.dumps({"sessionId": sid, "state": "working", **(body or {})}))
        return os.path.join(d, "state.json")

    def human(self, sid=None, cwd=None, options=None, dropped=None, **more):
        """A human-opened thread's record as the module returns it (not_woken reads what it is given)."""
        sid = sid or str(uuidlib.uuid4())
        launch = {"cwd": self.root if cwd is None else cwd, "at": sminos.now()}
        if options is not None:
            launch["options"] = options
        if dropped is not None:
            launch["dropped"] = dropped
        return {"thread": str(uuidlib.uuid4()), "opened": "human", "sessions": [sid], "current": sid,
                "alias": "alpha", "launch": launch, "channels": [], **more}


# ------------------------------------------------------------ the row (§1)


class Row(Wakes):
    def test_a_row_found_not_found_and_unreadable_in_each_form(self):
        sid = str(uuidlib.uuid4())
        self.assertIs(wake.row_of(sid), wake.UNREADABLE, "a config dir with no jobs directory")
        os.makedirs(os.path.join(self.config(), "jobs"))
        self.assertIsNone(wake.row_of(sid), "a jobs directory with no row for it")
        self.row(sid, {"respawnFlags": ["--permission-mode", "auto", "--model", "haiku"], "state": "failed"})
        row = wake.row_of(sid)
        self.assertEqual((row["sessionId"], wake.row_options(row), wake.row_failed(row)),
                         (sid, ["--permission-mode", "auto", "--model", "haiku"], True))
        self.row(sid, raw="{not json")
        self.assertIs(wake.row_of(sid), wake.UNREADABLE, "a file that does not parse")
        other = sid[:8] + str(uuidlib.uuid4())[8:]
        self.row(sid, raw=json.dumps({"sessionId": other}))
        self.assertIs(wake.row_of(sid), wake.UNREADABLE, "a row of another session under its first eight")
        self.row(sid, raw=json.dumps(["a", "list"]))
        self.assertIs(wake.row_of(sid), wake.UNREADABLE, "a file that is no object")

    def test_a_row_is_its_own_session_s_in_either_order_of_lookups(self):
        sid = str(uuidlib.uuid4())
        other = sid[:8] + str(uuidlib.uuid4())[8:]
        self.row(sid, {"respawnFlags": ["--model", "a"]})
        self.assertEqual(wake.row_options(wake.row_of(sid)), ["--model", "a"])
        self.assertIs(wake.row_of(other), wake.UNREADABLE, "the owner looked up first")
        wake._ROWS.clear()
        self.assertIs(wake.row_of(other), wake.UNREADABLE)
        self.assertEqual(wake.row_options(wake.row_of(sid)), ["--model", "a"], "the other id looked up first")

    def test_a_row_without_flags_or_state(self):
        sid = str(uuidlib.uuid4())
        self.row(sid, {"respawnFlags": "not a list"})
        row = wake.row_of(sid)
        self.assertEqual((wake.row_options(row), wake.row_failed(row)), ([], False))
        self.assertEqual(wake.row_options({"respawnFlags": ["--model", 3]}), [])

    def test_the_row_is_read_again_once_it_changed(self):
        sid = str(uuidlib.uuid4())
        self.row(sid, {"respawnFlags": ["--model", "a"]})
        self.assertEqual(wake.row_options(wake.row_of(sid)), ["--model", "a"])
        time.sleep(0.01)
        self.row(sid, {"respawnFlags": ["--model", "bb"]})
        self.assertEqual(wake.row_options(wake.row_of(sid)), ["--model", "bb"])
        os.unlink(os.path.join(self.config(), "jobs", sid[:8], "state.json"))
        self.assertIsNone(wake.row_of(sid))

    def test_a_session_under_another_config_dir_is_read_there(self):
        sid = str(uuidlib.uuid4())
        other = os.path.join(self.home, "other-config")
        with mock.patch.object(sminos, "session_config_dir", lambda s: other):
            self.assertIs(wake.row_of(sid), wake.UNREADABLE)
            os.makedirs(os.path.join(other, "jobs", sid[:8]))
            with open(os.path.join(other, "jobs", sid[:8], "state.json"), "w") as f:
                json.dump({"sessionId": sid, "respawnFlags": ["--model", "x"]}, f)
            self.assertEqual(wake.row_options(wake.row_of(sid)), ["--model", "x"])


# ------------------------------------------------------------ the last turn (§1)


class LastTurn(Wakes):
    def test_a_tail_that_ends_in_hook_and_metadata_rows(self):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt("plan"), answer("claude-a"), prompt("auto"), answer("claude-b", "req_2"),
                                  {"type": "permission-mode", "permissionMode": "default"},
                                  hook_row("claude-hook"),
                                  {"type": "assistant", "isSidechain": True, "requestId": "req_9",
                                   "message": {"id": "msg_9", "model": "claude-sub"}},
                                  {"type": "custom-title", "customTitle": "alpha"}))
        self.assertEqual(wake.last_turn(sid), {"mode": "auto", "model": "claude-b"})
        self.assertEqual(wake.last_turn(sid, whole=True), {"mode": "auto", "model": "claude-b"})

    def test_a_partial_last_line_is_no_row(self):
        sid = str(uuidlib.uuid4())
        path = self.transcript(sid, rows(prompt("acceptEdits"), answer("claude-a")))
        with open(path, "a") as f:
            f.write('{"type": "user", "permissionMode": "pl')
        self.assertEqual(wake.last_turn(sid), {"mode": "acceptEdits", "model": "claude-a"})

    def test_a_prompt_beyond_the_bound_is_unknown_until_the_whole_reading(self):
        sid = str(uuidlib.uuid4())
        filler = rows(*({"type": "progress", "data": "x" * 200} for _ in range(40)))
        self.transcript(sid, rows(prompt("plan")) + filler + rows(answer("claude-c")) + filler)
        with mock.patch.object(wake, "TAIL_BOUND", 4096):
            self.assertEqual(wake.last_turn(sid), {"mode": None, "model": None})
            self.assertEqual(wake.last_turn(sid, whole=True), {"mode": "plan", "model": "claude-c"})
            # The whole reading is kept by the transcript's stat: a tick's bounded reading takes it.
            with mock.patch("builtins.open", side_effect=AssertionError("read again")):
                self.assertEqual(wake.last_turn(sid), {"mode": "plan", "model": "claude-c"})
            self.transcript(sid, rows({"type": "progress"}))
            self.assertEqual(wake.last_turn(sid), {"mode": None, "model": None}, "a changed stat reads again")

    def test_the_bounded_reading_is_cached_by_the_stat(self):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt("auto"), answer("claude-a")))
        self.assertEqual(wake.last_turn(sid)["mode"], "auto")
        with mock.patch("builtins.open", side_effect=AssertionError("read again")):
            self.assertEqual(wake.last_turn(sid)["mode"], "auto")

    def test_a_transcript_deleted_or_moved_after_it_was_found(self):
        sid = str(uuidlib.uuid4())
        path = self.transcript(sid, rows(prompt("auto"), answer("m")))
        rec = self.human(sid=sid)
        self.assertEqual((wake.not_woken(rec, sid), wake.not_woken(rec, sid, whole=True)), ("", ""))
        moved = os.path.join(self.config(), "projects", "elsewhere", sid + ".jsonl")
        os.makedirs(os.path.dirname(moved))
        os.rename(path, moved)
        self.assertEqual(sminos.transcript_path(sid), path, "the index still names the old path")
        for whole in (False, True):
            self.assertEqual(wake.transcript_file(sid, whole), moved)
            self.assertEqual(wake.not_woken(rec, sid, whole=whole), "")
            self.assertEqual(wake.last_turn(sid, whole=whole), {"mode": "auto", "model": "m"})
        os.unlink(moved)
        for whole in (False, True):
            with self.subTest(whole=whole):
                self.assertEqual(wake.transcript_file(sid, whole), "")
                self.assertEqual(wake.not_woken(rec, sid, whole=whole), "transcript")
                self.assertEqual(wake.mode_case(rec, sid, whole=whole), "")

    def test_a_transcript_with_no_turn_and_none_at_all(self):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows({"type": "summary"}, hook_row("claude-hook"),
                                  {"type": "permission-mode", "permissionMode": "plan"}))
        self.assertEqual(wake.last_turn(sid), {"mode": "", "model": ""})
        self.assertEqual(wake.last_turn(str(uuidlib.uuid4()), whole=True), {"mode": "", "model": ""})


# ------------------------------------------------------------ the flags (§1, §2)


class Flags(Wakes):
    def test_each_mode_its_flag_and_which_ask(self):
        self.assertEqual([wake.mode_flag(m) for m in ("default", "manual", "plan", "acceptEdits", "auto",
                                                      "dontAsk", "bypassPermissions", "newMode")],
                         ["manual", "manual", "plan", "acceptEdits", "auto", "dontAsk", "bypassPermissions",
                          "newMode"])
        self.assertEqual([m for m in ("default", "manual", "plan", "acceptEdits", "auto", "dontAsk",
                                      "bypassPermissions", "newMode", "", None) if wake.asks(m)],
                         ["default", "manual", "plan", "acceptEdits"])

    def test_a_launch_with_every_kept_option(self):
        settings = os.path.join(self.root, "s.json")
        open(settings, "w").close()
        argv = ["claude", "--permission-mode", "plan", "--model", "opus", "--effort", "high", "--settings", settings,
                "--add-dir", "/one", "/two", "--agent", "notes", "--fallback-model", "sonnet",
                "--dangerously-skip-permissions", "--settings", '{"env":{"A":"1"}}', "-n", "alpha"]
        rec = self.human(options=threads.launch_options(argv), dropped=threads.launch_dropped(argv))
        turn = {"mode": "auto", "model": "claude-opus-5"}
        flags, missing = wake.first_flags(rec, turn, "bypassPermissions", False)
        self.assertEqual(flags, ["--permission-mode", "auto", "--model", "claude-opus-5", "--effort", "high",
                                 "--settings", settings])
        self.assertEqual(missing, ["--add-dir", "--agent", "--fallback-model", "--dangerously-skip-permissions",
                                   "--settings"], "the second --settings was inline: dropped, so named")
        argv_out = wake.wake_argv(rec["current"], flags)
        self.assertEqual(argv_out[:3], ["--bg", "--resume", rec["current"]])
        self.assertEqual(argv_out[3:], flags, "nothing after the flags: no positional")

    def test_a_settings_file_that_is_gone_and_a_relative_one(self):
        rec = self.human(options=["--settings", "gone.json"], dropped=[])
        self.assertEqual(wake.first_flags(rec, {"mode": "", "model": ""}, "auto", False),
                         ([], ["--settings"]))
        with open(os.path.join(self.root, "rel.json"), "w") as f:
            f.write("{}")
        rec = self.human(options=["--settings", "rel.json"], dropped=[])
        self.assertEqual(wake.first_flags(rec, {"mode": "", "model": ""}, "auto", False),
                         (["--settings", os.path.join(self.root, "rel.json")], []))
        rec = self.human(cwd="", options=["--settings", "rel.json"], dropped=[])
        self.assertEqual(wake.first_flags(rec, {"mode": "", "model": ""}, "auto", False)[0], [],
                         "a relative path with no directory to read it against is not passed")

    def test_a_mode_above_the_ceiling_is_lowered_to_it(self):
        rec = self.human(options=[], dropped=[])
        for mode, ceiling, flag in (("bypassPermissions", "auto", "auto"), ("dontAsk", "acceptEdits", "acceptEdits"),
                                    ("auto", "default", "manual"), ("auto", "manual", "manual"),
                                    ("plan", "auto", "plan"), ("default", "auto", "manual"),
                                    ("newMode", "plan", "newMode"), ("auto", "newCeiling", "manual")):
            with self.subTest(mode=mode, ceiling=ceiling):
                self.assertEqual(wake.first_flags(rec, {"mode": mode, "model": ""}, ceiling, True)[0],
                                 ["--permission-mode", flag])

    def test_bypass_becomes_auto_unless_the_disclaimer_was_accepted(self):
        rec = self.human(options=["--permission-mode", "bypassPermissions"], dropped=[])
        turn = {"mode": "bypassPermissions", "model": ""}
        self.assertEqual(wake.first_flags(rec, turn, "bypassPermissions", False)[0], ["--permission-mode", "auto"])
        self.assertEqual(wake.first_flags(rec, turn, "bypassPermissions", True)[0],
                         ["--permission-mode", "bypassPermissions"])
        self.assertFalse(wake.bypass_accepted(rec["current"]))
        with open(os.path.join(self.config(), "settings.json"), "w") as f:
            json.dump({"skipDangerousModePermissionPrompt": True}, f)
        self.assertTrue(wake.bypass_accepted(rec["current"]))

    def test_with_no_turn_the_launch_decides_and_with_nothing_recorded_nothing_is_passed(self):
        rec = self.human(options=["--permission-mode", "bypassPermissions", "--model", "opus"], dropped=[])
        self.assertEqual(wake.first_flags(rec, {"mode": "", "model": None}, "auto", False),
                         (["--permission-mode", "auto", "--model", "opus"], []))
        self.assertEqual(wake.first_flags(self.human(), {"mode": "", "model": ""}, "auto", False), ([], None),
                         "no options read: what was not carried is not known")
        self.assertEqual(wake.first_flags(self.human(options=[]), {"mode": "", "model": ""}, "auto", False),
                         ([], None), "a launch noted before T2 has no dropped")

    def test_first_wake_reads_the_whole_turn_the_ceiling_and_the_disclaimer(self):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt("bypassPermissions"), answer("claude-x")))
        rec = self.human(sid=sid, options=["--effort", "low"], dropped=[])
        with mock.patch.object(sminos_policy, "machine_policy", lambda: {"read_only": False, "ceiling": "dontAsk"}):
            self.assertEqual(wake.first_wake(rec, sid),
                             (["--permission-mode", "dontAsk", "--model", "claude-x", "--effort", "low"], []))

    def test_the_not_carried_list_with_a_dropped_inline_option(self):
        argv = ["claude", "--settings", '{"env":{}}', "--mcp-config", "/a.json", "{\"x\":1}", "--model", "m",
                "--agent", "a-" + str(uuidlib.uuid4())]
        self.assertEqual(threads.launch_options(argv), ["--model", "m"], "the list's contract stands")
        self.assertEqual(threads.launch_dropped(argv), ["--settings", "--mcp-config", "--agent"])
        rec = self.human(options=threads.launch_options(argv), dropped=threads.launch_dropped(argv))
        self.assertEqual(wake.first_flags(rec, {"mode": "auto", "model": ""}, "auto", False),
                         (["--permission-mode", "auto", "--model", "m"], ["--settings", "--mcp-config", "--agent"]))


class Noted(Wakes):
    def test_the_hook_notes_what_it_dropped_and_an_unreadable_vector_neither(self):
        sid, proc = self.session()
        self.reconcile()
        argv_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "--model", "m",
                                      "--settings", '{"env":{}}'])
        self.addCleanup(argv_proc.wait)
        self.addCleanup(argv_proc.kill)
        time.sleep(0.3)
        self.hook(sid, env={"CLAUDE_PID": str(argv_proc.pid)})
        launch = threads.thread_of(sid)["launch"]
        self.assertEqual((launch["options"], launch["dropped"]), (["--model", "m"], ["--settings"]))
        self.hook(sid, env={"CLAUDE_PID": "1"})
        launch = threads.thread_of(sid)["launch"]
        self.assertNotIn("options", launch)
        self.assertNotIn("dropped", launch)

    def test_a_spawn_notes_its_options_and_drops_none(self):
        launched = threads.launch_of(self.root, ["--model", "opus"], [])
        self.assertEqual((launched["options"], launched["dropped"]), (["--model", "opus"], []))
        self.assertNotIn("dropped", threads.launch_of(self.root, ["--model", "opus"]))


# ------------------------------------------------------------ the line (§2)


class Line(Wakes):
    HEAD = ("[sminos] A note from sminos on this machine, not from the sender above: you were woken in the "
            "background by this message, and your human is not watching this session unless they have attached "
            "to it since.")

    TERMINAL = " The environment variables of the terminal or app you were opened in may differ here."

    def test_a_first_wake_names_what_it_did_not_carry(self):
        note = wake.line_note(True, ["--permission-mode", "auto", "--model", "claude-a"],
                              {"mode": "auto", "model": "claude-a"}, ["--add-dir", "--agent"], "human")
        self.assertEqual(set(note), {"id", "first", "mode", "model", "turn_model", "not_carried", "opened", "at"})
        self.assertEqual(wake.line_text(note), self.HEAD + " You run in auto mode on claude-a." + self.TERMINAL + (
            " Options you were last started with that are not carried here: --add-dir, --agent."))

    def test_a_first_wake_whose_launch_does_not_say_and_one_that_dropped_nothing(self):
        note = wake.line_note(True, [], {"mode": "", "model": ""}, None, "human")
        self.assertEqual(wake.line_text(note), self.HEAD + " You run under your saved options." + self.TERMINAL + (
            " Other options you were last started with may not be carried here."))
        note = wake.line_note(True, ["--permission-mode", "manual", "--model", "m"], {"mode": "default"}, [], "human")
        self.assertTrue(wake.line_text(note).endswith(" You run in manual mode on m." + self.TERMINAL))

    def test_only_a_thread_its_human_opened_is_told_of_its_terminal(self):
        """A first wake means no engine row, which a spawned seat whose row is gone meets too: it never ran in a
        terminal, so only what was not carried is said; a note older code wrote, with no `opened`, reads as one."""
        for opened in ("spawned", None):
            with self.subTest(opened=opened):
                note = wake.line_note(True, ["--permission-mode", "auto", "--model", "claude-a"], {}, ["--agent"],
                                      *([opened] if opened else []))
                if opened is None:
                    note.pop("opened")
                self.assertEqual(wake.line_text(note), self.HEAD + (
                    " You run in auto mode on claude-a. Options you were last started with that are not carried"
                    " here: --agent."))
                self.assertNotIn("terminal", wake.line_text(dict(note, not_carried=None)))
        self.assertEqual(wake.line_note(False, [], {}, opened="human")["opened"], "human")
        self.assertNotIn("terminal", wake.line_text(wake.line_note(False, [], {}, opened="human")), "a later wake")

    def test_a_later_wake_says_the_row_s_model_and_the_turn_s_when_they_differ(self):
        row = {"respawnFlags": ["--permission-mode", "default", "-n", "x", "--model", "opus"]}
        note = wake.line_note(False, wake.row_options(row), {"mode": "auto", "model": "claude-sonnet-5"})
        self.assertEqual(wake.line_text(note), self.HEAD + (
            " You run in manual mode on opus. Your last turn ran on claude-sonnet-5; a background run keeps the"
            " options it last ran with in the background."))
        same = wake.line_note(False, ["--model", "claude-haiku-4-5", "--permission-mode", "auto"],
                              {"mode": "auto", "model": "CLAUDE-HAIKU-4-5"})
        self.assertEqual(wake.line_text(same), self.HEAD + " You run in auto mode on claude-haiku-4-5.")
        # Measured (E10): a row saved as `haiku` woke on 5.5 after a terminal turn on 4.5; the alias is
        # not resolved, so both names are said.
        alias = wake.line_note(False, ["--model", "haiku", "--permission-mode", "auto"],
                               {"mode": "auto", "model": "claude-haiku-4-5-20251001"})
        self.assertEqual(wake.line_text(alias), self.HEAD + (
            " You run in auto mode on haiku. Your last turn ran on claude-haiku-4-5-20251001; a background run"
            " keeps the options it last ran with in the background."))
        close = wake.line_note(False, ["--model", "claude-sonnet-4", "--permission-mode", "auto"],
                               {"model": "claude-sonnet-4-5"})
        self.assertIn(" Your last turn ran on claude-sonnet-4-5;", wake.line_text(close))
        self.assertEqual(wake.line_text(wake.line_note(False, [], {"mode": "", "model": "m"})),
                         self.HEAD + " You run under your saved options.")
        self.assertNotEqual(wake.line_note(False, [], {})["id"], wake.line_note(False, [], {})["id"])

    def test_the_line_is_one_line_opening_with_sminos_s_literal_whatever_it_names(self):
        for note in (wake.line_note(True, [], {}, None), wake.line_note(False, ["--model", "m"], {"model": "x"}),
                     wake.line_note(False, ["--model", "m\nfake", "--permission-mode", "auto"],
                                    {"model": "x\u2028y\r\nz"})):
            text = wake.line_text(note)
            self.assertTrue(text.startswith("[sminos] "))
            self.assertEqual(text.splitlines(), [text], "no line break in it")


class Literal(unittest.TestCase):
    """The line's start at a line's start is sminos's alone (§2): a sender's line that opens with it is given one
    leading space when its frame is composed, a woken push or not, and nothing else of the text changes."""

    def test_a_senders_line_opening_with_the_lines_start_is_given_one_space_in_either_frame(self):
        text = ("[sminos] first\nkept [sminos] inside\n[sminos] second\r\n[sminos] after crlf\u2028[sminos] after ls"
                "\n[sminos]tight\n[sminos chat x]\n [sminos] spaced")
        said = (" [sminos] first\nkept [sminos] inside\n [sminos] second\r\n [sminos] after crlf\u2028 [sminos] after "
                "ls\n[sminos]tight\n[sminos chat x]\n [sminos] spaced")
        self.assertEqual(sminos.compose_frame("a", "abcd1234", text).split("\n", 1)[1], said)
        self.assertEqual(sminos.compose_chat_frame("p", "w:1", "a", "@you", 0, text).split("\n", 1)[1], said)
        self.assertEqual(sminos.compose_frame("a", "abcd1234", "plain\ntext"), "[sminos message from a id=abcd1234]\n"
                         "plain\ntext", "a text with no such line is as it was")


# ------------------------------------------------------------ not woken (§1)


class SameModel(unittest.TestCase):
    def test_one_name_once_case_and_a_window_are_set_aside(self):
        for a, b, same in (("haiku", "claude-haiku-5-5", False), ("claude-haiku-5-5", "HAIKU", False),
                           ("haiku", "claude-haiku-4-5-20251001", False), ("HAIKU", "haiku", True),
                           ("sonnet[1m]", "claude-sonnet-4-5", False), ("claude-opus-5[1m]", "claude-opus-5", True),
                           ("claude-sonnet-4", "claude-sonnet-4-5", False), ("opus", "claude-sonnet-5", False),
                           ("claude-haiku-4-5-2025", "claude-haiku-5-5", False), ("op", "claude-opus-5", False),
                           ("haiku", "haiku-like-model", False), ("", "x", False), ("m", "m", True)):
            with self.subTest(a=a, b=b):
                self.assertIs(wake.same_model(a, b), same)


class NotWoken(Wakes):
    def woken_by_mode(self, mode, row_mode=None):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt(mode), answer("m")))
        if row_mode is not None:
            self.row(sid, {"respawnFlags": ["--permission-mode", row_mode]})
        return wake.not_woken(self.human(sid=sid), sid)

    def test_each_reason_and_none(self):
        sid = str(uuidlib.uuid4())
        rec = self.human(sid=sid)
        self.assertEqual(wake.not_woken(rec, sid), "transcript")
        self.transcript(sid, rows(prompt("auto"), answer("m")))
        self.assertEqual(wake.not_woken(rec, sid), "")
        self.assertEqual(wake.not_woken(self.human(sid=sid, cwd=os.path.join(self.home, "gone")), sid), "cwd")
        self.assertEqual(wake.not_woken(self.human(sid=sid, cwd=""), sid), "cwd")
        a_file = os.path.join(self.home, "a-file")
        open(a_file, "w").close()
        self.assertEqual(wake.not_woken(self.human(sid=sid, cwd=a_file), sid), "cwd")
        with mock.patch.object(sminos, "foreign_config", lambda s: "/elsewhere"):
            self.assertEqual(wake.not_woken(rec, sid), "config")

    def test_a_mode_that_asks_in_the_last_turn_or_in_the_row(self):
        for mode in ("default", "plan", "acceptEdits", "manual"):
            with self.subTest(mode=mode):
                self.assertEqual(self.woken_by_mode(mode), "mode")
        for mode in ("auto", "dontAsk", "bypassPermissions", "someNewMode"):
            with self.subTest(mode=mode):
                self.assertEqual(self.woken_by_mode(mode), "")
        self.assertEqual(self.woken_by_mode("auto", row_mode="default"), "mode", "the row's mode asks")
        self.assertEqual(self.woken_by_mode("plan", row_mode="auto"), "mode", "the last turn's asks")
        self.assertEqual(self.woken_by_mode("auto", row_mode="bypassPermissions"), "")

    def test_a_mode_not_found_within_the_bound_does_not_ask_until_the_whole_reading(self):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt("plan")) + rows(*({"type": "progress", "data": "x" * 200}
                                                           for _ in range(40))))
        rec = self.human(sid=sid)
        with mock.patch.object(wake, "TAIL_BOUND", 2048):
            self.assertEqual(wake.not_woken(rec, sid), "")
            self.assertEqual(wake.not_woken(rec, sid, whole=True), "mode")

    def test_protected_on_macos_alone_and_for_a_thread_its_human_opened(self):
        desktop = os.path.join(os.environ["HOME"], "Desktop", "proj")
        os.makedirs(desktop)
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt("plan"), answer("m")))
        rec = self.human(sid=sid, cwd=desktop)
        with mock.patch.object(sminos, "TCC", True), mock.patch.object(sminos, "_own_cwd", lambda: desktop):
            self.assertEqual(wake.not_woken(rec, sid), "protected", "protected is checked before mode")
            spawned = dict(rec, opened="spawned")
            with mock.patch.object(sminos, "reload_seat", lambda tid: None):
                self.assertEqual(wake.not_woken(spawned, sid), "mode", "a spawned thread there is resumed")
        with mock.patch.object(sminos, "TCC", False):
            self.assertEqual(wake.not_woken(rec, sid), "mode", "off macOS no folder is protected")

    def test_protected_for_a_directory_that_holds_a_protected_folder(self):
        """The engine's startup scans its directory's children, so a launch in $HOME (or any folder above a
        protected one, / and /Volumes among them) reaches into ~/Downloads: launch_refused's rule, whichever process
        asks, its own working directory there or not."""
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt("auto"), answer("m")))
        home = os.environ["HOME"]
        with mock.patch.object(sminos, "TCC", True):
            # /Volumes where the machine has one: on Linux it is gone, which `cwd` answers first.
            for where in (home, os.path.dirname(home), "/") + (("/Volumes",) if os.path.isdir("/Volumes") else ()):
                for here in (self.root, where):
                    with self.subTest(where=where, here=here), mock.patch.object(sminos, "_own_cwd", lambda: here):
                        self.assertEqual(wake.not_woken(self.human(sid=sid, cwd=where), sid), "protected")
            self.assertEqual(wake.not_woken(self.human(sid=sid), sid), "", "a directory beside them holds none")
            with mock.patch.object(sminos, "reload_seat", lambda tid: None):
                self.assertEqual(wake.not_woken(dict(self.human(sid=sid, cwd=home), opened="spawned"), sid), "",
                                 "a spawned thread there is resumed")
        with mock.patch.object(sminos, "TCC", False):
            self.assertEqual(wake.not_woken(self.human(sid=sid, cwd=home), sid), "")

    def test_the_kept_answer_for_a_directory_that_holds_one_is_its_path_s(self):
        """hold_reason keeps `protected` for $HOME by the guard's answer and whether the directory is there, not
        by its stat, which any file written in $HOME moves."""
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt("auto"), answer("m")))
        home = os.environ["HOME"]
        rec = self.human(sid=sid, cwd=home)
        with mock.patch.object(sminos, "TCC", True), mock.patch.object(sminos, "_own_cwd", lambda: self.root):
            self.assertEqual(wake.hold_reason(rec, sid), "protected")
            key = wake.hold_key(rec, sid)
            with open(os.path.join(home, ".history"), "w") as f:
                f.write("a file written in $HOME")
            self.assertEqual(wake.hold_key(rec, sid), key)
            self.assertEqual(wake.hold_reason(rec, sid), "protected")
            gone = os.path.join(self.home, "elsewhere", "h")
            os.makedirs(os.path.join(gone, "Desktop"))
            rec = self.human(sid=sid, cwd=os.path.dirname(gone))
            with mock.patch.object(sminos, "protected_folders", lambda: [os.path.join(gone, "Desktop")]):
                self.assertEqual(wake.hold_reason(rec, sid), "protected")
                shutil.rmtree(os.path.dirname(gone))
                self.assertEqual(wake.hold_reason(rec, sid), "cwd", "the directory gone: the key moved with it")

    def test_a_directory_this_process_may_not_look_at_is_taken_on_its_word(self):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt("auto"), answer("m")))
        gone = os.path.join(os.environ["HOME"], "Documents", "not-here")
        rec = self.human(sid=sid, cwd=gone)
        with mock.patch.object(sminos, "TCC", True), mock.patch.object(sminos, "_own_cwd", lambda: self.root):
            self.assertEqual(wake.not_woken(rec, sid), "protected", "not looked at: taken as there, then protected")
        with mock.patch.object(sminos, "TCC", False):
            self.assertEqual(wake.not_woken(rec, sid), "cwd")

    def test_the_order_of_the_reasons(self):
        sid = str(uuidlib.uuid4())
        desktop = os.path.join(os.environ["HOME"], "Desktop", "p")
        os.makedirs(desktop)
        rec = self.human(sid=sid, cwd=desktop)
        with mock.patch.object(sminos, "TCC", True), mock.patch.object(sminos, "_own_cwd", lambda: self.root):
            with mock.patch.object(sminos, "foreign_config", lambda s: "/elsewhere"):
                self.assertEqual(wake.not_woken(rec, sid), "config", "config before transcript")
            self.assertEqual(wake.not_woken(rec, sid), "transcript", "transcript before cwd and protected")
            self.transcript(sid, rows(prompt("plan")))
            self.assertEqual(wake.not_woken(self.human(sid=sid, cwd=desktop + "-gone"), sid), "protected",
                             "a folder not looked at is not missing")
            self.assertEqual(wake.not_woken(rec, sid), "protected", "protected before mode")
        self.assertEqual(wake.not_woken(self.human(sid=sid, cwd=os.path.join(self.home, "x")), sid), "cwd",
                         "cwd before mode")
        self.assertEqual(wake.REASONS, ("config", "transcript", "cwd", "protected", "mode"))

    def test_a_seat_s_directory_is_where_its_session_runs(self):
        sid, proc = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        self.transcript(sid, rows(prompt("auto"), answer("m")))
        seat_id = next(s["seat_id"] for s in sminos.seats())
        rec = threads.get(seat_id)
        self.assertEqual(wake.not_woken(rec, sid), "")
        sminos.meta_set(seat_id, {"cwd": os.path.join(self.home, "moved-away")})
        sminos.forget_caches()
        self.assertEqual(wake.not_woken(threads.get(seat_id), sid), "cwd")


class CappedMode(Wakes):
    """The plan's Decision Log, "A first wake's capped mode decides `mode`"."""

    def thread(self, turn_mode="auto"):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt(turn_mode), answer("m")))
        return self.human(sid=sid), sid

    def test_a_ceiling_that_asks_holds_a_first_wake_for_mode(self):
        rec, sid = self.thread("auto")
        self.ceiling("default")
        self.assertEqual((wake.not_woken(rec, sid), wake.mode_case(rec, sid)), ("mode", "ceiling"))
        self.assertEqual(wake.not_woken(rec, sid, whole=True), "mode")
        self.ceiling(None)
        self.assertEqual(wake.mode_case(rec, sid), "ceiling", "no policy file: the settings' defaultMode, else default")
        with open(os.path.join(self.config(), "settings.json"), "w") as f:
            json.dump({"permissions": {"defaultMode": "auto"}}, f)
        self.assertEqual((wake.not_woken(rec, sid), wake.mode_case(rec, sid)), ("", ""), "the settings' ceiling raised")
        self.ceiling("plan")
        self.assertEqual(wake.mode_case(rec, sid), "ceiling", "a policy's ceiling is read before the settings'")

    def test_a_readable_row_is_not_capped(self):
        rec, sid = self.thread("auto")
        self.ceiling("default")
        self.row(sid, {"respawnFlags": ["--permission-mode", "auto"]})
        self.assertEqual((wake.not_woken(rec, sid), wake.mode_case(rec, sid)), ("", ""))
        self.row(sid, raw="{not json")
        self.assertEqual((wake.not_woken(rec, sid), wake.mode_case(rec, sid)), ("mode", "ceiling"),
                         "an unreadable row: a first wake would pass flags")

    def test_a_raised_ceiling_wakes_and_the_turn_s_own_mode_is_its_own_case(self):
        rec, sid = self.thread("auto")
        self.ceiling("auto")
        self.assertEqual(wake.not_woken(rec, sid), "")
        rec, sid = self.thread("plan")
        self.ceiling("bypassPermissions")
        self.assertEqual((wake.not_woken(rec, sid), wake.mode_case(rec, sid)), ("mode", "own"))
        self.ceiling("default")
        self.assertEqual(wake.mode_case(rec, sid), "own", "its own mode asks, whatever the ceiling")

    def test_a_wake_that_passes_no_flag_is_not_capped(self):
        rec, sid = self.thread("auto")
        self.ceiling("default")
        self.row(sid, raw="{not json")
        self.assertEqual((wake.not_woken(rec, sid, flagless=True), wake.mode_case(rec, sid, flagless=True)),
                         ("", ""), "the wake's retry with no flag, after the engine kept the saved options")
        rec["waking"] = {"session": sid, "saved": True, "failed": 0, "at": 0, "line": None}
        self.assertEqual((wake.not_woken(rec, sid), wake.mode_case(rec, sid)), ("", ""),
                         "the engine said the session keeps its saved options")
        self.assertEqual([wake.passes_flags(rec, sid, row) for row in (None, {"respawnFlags": []}, wake.UNREADABLE)],
                         [True, False, False])
        del rec["waking"]
        self.assertEqual([wake.passes_flags(rec, sid, row) for row in (None, {"respawnFlags": []}, wake.UNREADABLE)],
                         [True, False, True])

    def test_the_kept_reason_moves_with_what_row_of_reads(self):
        """A `jobs` directory made where there was none turns an unreadable row into no row (row_of), which a
        first wake's flags follow (passes_flags): the kept answer and the daemon's key move with it."""
        rec, sid = self.thread("auto")
        self.ceiling("default")
        rec["waking"] = {"session": sid, "saved": True, "failed": 0, "at": 0, "line": None}
        self.assertIs(wake.row_of(sid), wake.UNREADABLE, "no jobs directory")
        self.assertEqual((wake.hold_reason(rec, sid), wake.published_reason(rec, sid)), ("", ""),
                         "the engine keeps its saved options: no flag passed, nothing capped")
        key = wake.hold_key(rec, sid)
        os.makedirs(os.path.join(self.config(), "jobs"))
        self.assertIsNone(wake.row_of(sid))
        self.assertEqual(wake.not_woken(rec, sid), "mode", "no row: a first wake, capped by the ceiling")
        self.assertNotEqual(wake.hold_key(rec, sid), key)
        self.assertEqual((wake.hold_reason(rec, sid), wake.published_reason(rec, sid)), ("mode", "mode"))

    def test_a_launch_mode_that_asks_is_its_own_whatever_the_ceiling(self):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows({"type": "summary"}))
        rec = self.human(sid=sid, options=["--permission-mode", "plan"], dropped=[])
        self.assertEqual((wake.not_woken(rec, sid), wake.mode_case(rec, sid)), ("mode", "own"),
                         "no turn: the launch's plan asks; raising the ceiling cannot help")

    def test_the_mode_check_touches_no_file_the_launch_names(self):
        rec, sid = self.thread("auto")
        settings = os.path.join(self.root, "launch-settings.json")
        with open(settings, "w") as f:
            f.write("{}")
        rec["launch"]["options"], rec["launch"]["dropped"] = ["--settings", "launch-settings.json"], []
        self.ceiling("default")
        looked = []
        real = os.path.isfile
        with mock.patch.object(os.path, "isfile", lambda p: looked.append(os.path.abspath(p)) or real(p)):
            self.assertEqual(wake.mode_case(rec, sid), "ceiling")
            self.assertEqual(wake.first_mode(rec, wake.last_turn(sid), "default", True), ("auto", "default"))
        self.assertNotIn(settings, looked)
        self.assertIn("--settings", wake.first_wake(rec, sid)[0], "the launch reads it")

    def test_an_unknown_mode_beyond_the_bound_is_not_capped_until_the_whole_reading(self):
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows(prompt("auto")) + rows(*({"type": "progress", "data": "x" * 200}
                                                           for _ in range(40))))
        rec = self.human(sid=sid)
        self.ceiling("default")
        with mock.patch.object(wake, "TAIL_BOUND", 2048):
            self.assertEqual(wake.not_woken(rec, sid), "")
            self.assertEqual(wake.not_woken(rec, sid, whole=True), "mode")

    def test_the_files_it_reads_beyond_the_record(self):
        self.assertEqual(wake.policy_inputs(), [sminos_policy.policy_path(),
                                                os.path.join(os.environ["HOME"], ".claude", "settings.json")])


# ------------------------------------------------------------ the schedule and the field (§4, §7)


class Schedule(Wakes):
    def test_wake_due_at_each_count_and_time(self):
        sid = str(uuidlib.uuid4())
        at = "2026-11-20T10:00:00.000Z"
        t0 = sminos._ts_epoch(at)
        self.assertTrue(wake.wake_due(self.human(sid=sid), sid))
        for failed, wait in ((1, 60), (2, 120), (3, 240), (6, 1920), (7, 3600), (40, 3600)):
            with self.subTest(failed=failed):
                rec = self.human(sid=sid, waking={"session": sid, "failed": failed, "at": at})
                self.assertFalse(wake.wake_due(rec, sid, now=t0 + wait - 1))
                self.assertTrue(wake.wake_due(rec, sid, now=t0 + wait))
        with mock.patch.dict(os.environ, {"SMINOS_WAKE_RETRY": "2", "SMINOS_WAKE_RETRY_MAX": "5"}):
            rec = self.human(sid=sid, waking={"session": sid, "failed": 2, "at": at})
            self.assertEqual((wake.wake_due(rec, sid, now=t0 + 3.9), wake.wake_due(rec, sid, now=t0 + 4)),
                             (False, True))
            rec = self.human(sid=sid, waking={"session": sid, "failed": 9, "at": at})
            self.assertTrue(wake.wake_due(rec, sid, now=t0 + 5))
        rec = self.human(sid=sid, waking={"session": sid, "failed": 1, "at": "not a time"})
        self.assertTrue(wake.wake_due(rec, sid, now=t0), "a failure whose time cannot be read holds nothing")
        rec = self.human(sid=sid, waking={"session": sid, "saved": True})
        self.assertTrue(wake.wake_due(rec, sid, now=t0))

    def test_waking_is_ignored_when_it_names_another_session(self):
        sid, other = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        at = sminos.now(ms=True)
        rec = self.human(sid=sid, waking={"session": other, "failed": 3, "at": at, "line": {"id": "x"}})
        self.assertEqual(threads.waking(rec), {})
        self.assertTrue(wake.wake_due(rec, sid))
        rec = self.human(sid=sid, waking={"session": sid, "failed": 3, "at": at})
        self.assertFalse(wake.wake_due(rec, sid))
        self.assertTrue(wake.wake_due(rec, other), "asked for a session it was not written for")
        self.assertEqual(threads.waking(rec, other), {})


class Field(Wakes):
    def opened_record(self):
        sid, proc = self.session()
        self.reconcile()
        return sid, threads.thread_of(sid)["thread"]

    def test_the_writers_of_a_human_opened_record(self):
        sid, tid = self.opened_record()
        line = {"id": "l1", "first": True, "mode": "auto", "model": "m", "turn_model": "m", "not_carried": None}
        self.assertTrue(threads.wake_line(tid, sid, line))
        self.assertEqual(threads.waking(threads.get(tid)), {"session": sid, "line": line})
        self.assertTrue(threads.wake_failed(tid, sid, "l1"))
        w = threads.waking(threads.get(tid))
        self.assertEqual((w["failed"], "line" in w), (1, False))
        self.assertTrue(threads.wake_line(tid, sid, dict(line, id="l2")))
        self.assertTrue(threads.wake_failed(tid, sid, "other"))
        w = threads.waking(threads.get(tid))
        self.assertEqual((w["failed"], w["line"]["id"]), (2, "l2"), "another wake's line stays")
        self.assertIsNotNone(sminos._ts_epoch(w["at"]))
        self.assertTrue(threads.wake_done(tid, sid, saved=True))
        self.assertEqual(threads.waking(threads.get(tid)), {"session": sid, "saved": True, "line": dict(line, id="l2")})
        self.assertFalse(threads.wake_line_sent(tid, sid, "l1"), "only the line of that id")
        self.assertTrue(threads.wake_line_sent(tid, sid, "l2"))
        self.assertTrue(threads.wake_forget(tid, sid))
        self.assertNotIn("waking", threads.get(tid), "a field with nothing but its session is removed")
        self.assertFalse(threads.wake_forget(tid, sid))

    def test_a_failure_before_any_line_was_written_is_counted(self):
        # A wake that fails before its line (W3's stop that did not take) passes no line id: counted, `at` set.
        sid, tid = self.opened_record()
        self.assertTrue(threads.wake_failed(tid, sid, None))
        w = threads.waking(threads.get(tid))
        self.assertEqual((w["failed"], "line" in w), (1, False))
        self.assertIsNotNone(sminos._ts_epoch(w["at"]))
        line = {"id": "l1", "first": True, "mode": "auto", "model": "m", "turn_model": "m", "not_carried": None}
        self.assertTrue(threads.wake_line(tid, sid, line))
        self.assertTrue(threads.wake_failed(tid, sid, None))
        w = threads.waking(threads.get(tid))
        self.assertEqual((w["failed"], w["line"]["id"]), (2, "l1"), "a line of another wake stays")

    def test_a_writer_for_a_session_that_does_not_fill_the_thread_writes_nothing(self):
        sid, tid = self.opened_record()
        other = str(uuidlib.uuid4())
        self.assertFalse(threads.wake_line(tid, other, {"id": "x"}))
        self.assertFalse(threads.wake_failed(tid, other, "x"))
        self.assertNotIn("waking", threads.get(tid))

    def test_a_field_written_for_an_earlier_occupant_is_started_again(self):
        sid, tid = self.opened_record()
        threads.wake_failed(tid, sid, "x")
        path = threads._human_path(tid)
        with open(path) as f:
            raw = json.load(f)
        raw["waking"]["session"] = str(uuidlib.uuid4())
        with open(path, "w") as f:
            json.dump(raw, f)
        self.assertTrue(threads.wake_failed(tid, sid, "x"))
        self.assertEqual(threads.waking(threads.get(tid))["failed"], 1)

    def advance(self, tid, to):
        self.assertIsNotNone(threads.begin(tid, "advance", self.p, [], fields={"current": to}))
        self.assertTrue(threads.finish(tid))

    def test_an_earlier_occupant_back_finds_none_of_its_old_field(self):
        sid, tid = self.opened_record()
        other = str(uuidlib.uuid4())
        threads.wake_failed(tid, sid, "x")
        threads.wake_done(tid, sid, saved=True)
        threads.wake_line(tid, sid, {"id": "l1"})
        self.assertTrue(threads.waking(threads.get(tid)))
        self.advance(tid, other)
        self.assertNotIn("waking", threads.get(tid), "dropped when another session fills the thread")
        self.advance(tid, sid)
        self.assertEqual((threads.get(tid)["current"], threads.waking(threads.get(tid))), (sid, {}))

    def test_a_seat_refilled_and_given_its_occupant_again(self):
        old, proc = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", old)
        self.assertEqual(code, 0, out)
        seat_id = next(s["seat_id"] for s in sminos.seats())
        threads.wake_failed(seat_id, old, "x")
        threads.wake_done(seat_id, old, saved=True)
        self.end(proc)
        seat = sminos.reload_seat(seat_id)
        new, nproc = self.session()
        self.assertTrue(sminos.refill_seat(self.p, seat, old, new, ""))
        self.assertNotIn("waking", sminos.load_seat(sminos.meta_path(seat_id)), "a refill drops it")
        threads.wake_failed(seat_id, new, "y")
        self.end(nproc)
        self.assertTrue(sminos.refill_seat(self.p, sminos.reload_seat(seat_id), new, old, ""))
        self.assertEqual(threads.waking(threads.get(seat_id)), {}, "the old occupant back reads nothing of before")

    def test_an_older_copy_s_move_of_a_seat_drops_it(self):
        old, proc = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", old)
        self.assertEqual(code, 0, out)
        seat_id = next(s["seat_id"] for s in sminos.seats())
        threads.wake_failed(seat_id, old, "x")
        other = str(uuidlib.uuid4())
        path = sminos.meta_path(seat_id)
        with open(path) as f:
            raw = json.load(f)
        raw["current"] = other   # an older copy's refill writes `current` and nothing else
        with open(path, "w") as f:
            json.dump(raw, f)
        sminos.forget_caches()
        self.assertNotIn("waking", threads.get(seat_id))
        threads.note_launch(seat_id, self.root)   # a write repairs the moved seat under its lock
        self.assertNotIn("waking", sminos.load_seat(path))

    def test_no_write_through_an_open_entry(self):
        sid, tid = self.opened_record()
        path = threads._human_path(tid)
        with open(path) as f:
            raw = json.load(f)
        raw["pending"] = {"id": "e1", "op": "end"}
        with open(path, "w") as f:
            json.dump(raw, f)
        self.assertFalse(threads.wake_line(tid, sid, {"id": "x"}))
        self.assertNotIn("waking", threads.get(tid))

    def test_a_seat_holds_it_and_list_json_shows_none_of_it(self):
        sid, proc = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        seat_id = next(s["seat_id"] for s in sminos.seats())
        self.assertTrue(threads.wake_failed(seat_id, sid, "x"))
        self.assertEqual(threads.waking(threads.get(seat_id))["failed"], 1)
        code, out = self.cli("list", "--json")
        self.assertEqual(code, 0, out)
        self.assertNotIn('"waking"', out)
        self.assertNotIn('"failed": 1', out)

    def test_two_writers_at_once_count_both(self):
        sid, tid = self.opened_record()
        barrier = threading.Barrier(2)

        def fail():
            barrier.wait()
            threads.wake_failed(tid, sid, "x")
        ts = [threading.Thread(target=fail) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(threads.waking(threads.get(tid))["failed"], 2)


# ------------------------------------------------------------ the test engine (§8)


def stub_text():
    """The shell stub as run-sminos-tests.sh writes it (its heredoc)."""
    with open(RUNNER) as f:
        text = f.read()
    m = re.search(r"cat > \"\$STUB_BIN/claude\" <<'STUB'\n(.*?)\nSTUB\n", text, re.S)
    return m.group(1) + "\n"


class Engine(Wakes):
    """The Python twin first on PATH."""
    FORM = "twin"

    def setUp(self):
        super().setUp()
        self.state = os.path.join(self.home, "e")
        os.makedirs(self.state)
        bindir = os.path.join(self.home, "bin")
        os.makedirs(bindir)
        exe = os.path.join(bindir, "claude")
        self.install(exe)
        env = {"PATH": bindir + os.pathsep + os.environ["PATH"], "WAKE_ENGINE_STATE": self.state}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(wake_engine.stop_all, self.state)
        self.addCleanup(self.no_violations)
        # Never the real engine: the stand-in first on PATH, or the test stops here.
        if shutil.which("claude") != exe:
            self.fail("the claude first on PATH is %s, not the test engine" % shutil.which("claude"))

    def no_violations(self):
        """Every test's teardown (T2's M2): no resume carried a message."""
        self.assertEqual(wake_engine.violations(self.state), [], "a resume carried a message")

    def install(self, exe):
        os.symlink(ENGINE, exe)

    def claude(self, *argv, cwd=None, timeout=60):
        p = subprocess.run(["claude"] + list(argv), cwd=cwd or self.root, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout, p.stderr

    def switch(self, name, value=""):
        with open(os.path.join(self.state, name), "w") as f:
            f.write(str(value))

    def opened(self, mode="auto", name="term-a"):
        """A session that ran in a terminal and exited: its transcript, named by its human, and no row."""
        sid = str(uuidlib.uuid4())
        self.transcript(sid, rows({"type": "custom-title", "customTitle": name, "sessionId": sid},
                                  prompt(mode), answer("claude-term")))
        return sid

    def record(self, sid):
        sminos.forget_caches()
        return next((r for r in sminos.peer_records() if r.get("sessionId") == sid
                     and sminos.pid_alive(r.get("pid"))), None)

    def jobs(self):
        code, out, err = self.claude("agents", "--json", "--all")
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def job(self, short):
        return next((j for j in self.jobs() if j["id"] == short), None)

    def turns(self, sid):
        path = sminos.transcript_now(sid)
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def inputs(self, sid):
        try:
            with open(os.path.join(self.state, "inputs", sid)) as f:
                return [json.loads(line) for line in f if line.strip()]
        except OSError:
            return []

    def push(self, sid, text):
        rec = wait_for(lambda: self.record(sid))
        self.assertIsNotNone(rec, "a process holds %s" % sid[:8])
        sock = wait_for(lambda: sminos.socket_ok(sminos.socket_path_of(rec)) and sminos.socket_path_of(rec))
        self.assertTrue(sock, "its inbox answers")
        sminos.send_frame(sock, text)

    def replied(self, sid, mid, n=1):
        return wait_for(lambda: len([r for r in self.turns(sid) if r.get("type") == "assistant"
                                     and "reply to %s" % mid in json.dumps(r)]) >= n)

    def wake_flags(self, sid, *flags):
        return self.claude("--bg", "--resume", sid, *flags)


class TwinCases:
    """The behaviours both forms share (§8: one fixture in two forms that behave alike)."""

    def test_a_first_wake_with_no_message_starts_an_idle_process_with_its_inbox(self):
        sid = self.opened()
        before = self.turns(sid)
        code, out, err = self.wake_flags(sid, "--permission-mode", "auto", "--model", "haiku")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "backgrounded · %s (idle — send a prompt to start)" % sid[:8])
        self.assertNotIn("copy", err)
        rec = self.record(sid)
        self.assertIsNotNone(rec, "the engine's record exists by the time the launch returns (E18)")
        self.assertEqual((rec["kind"], rec["cwd"], rec["name"], rec["nameSource"], rec["status"]),
                         ("bg", self.root, "term-a", "user", "idle"))
        self.assertTrue(sminos.socket_ok(sminos.socket_path_of(rec)))
        self.assertEqual(self.turns(sid), before, "no turn runs (E17)")
        row = wake.row_of(sid)
        self.assertEqual((row["cwd"], wake.row_options(row)), (self.root, ["--permission-mode", "auto", "--model",
                                                                            "haiku"]))
        job = self.job(sid[:8])
        self.assertEqual((job["sessionId"], job["pid"], job["status"], job["state"]),
                         (sid, rec["pid"], "idle", "blocked"))
        self.assertTrue(sminos.peer_live(rec))

    def test_a_frame_pushed_runs_a_turn_its_marker_in_the_transcript_then_idle(self):
        sid = self.opened()
        self.wake_flags(sid, "--permission-mode", "auto", "--model", "haiku")
        frame = sminos.compose_frame("bee", "abc12345", "hello")
        self.push(sid, frame)
        self.assertTrue(self.replied(sid, "abc12345"))
        [got] = self.inputs(sid)
        self.assertEqual(got["message"]["content"], sminos.peer_envelope(frame), "the frame, whole")
        prompt_row, reply = [r for r in self.turns(sid) if r.get("type") in ("user", "assistant")][-2:]
        self.assertIn("id=abc12345", prompt_row["message"]["content"])
        self.assertEqual(prompt_row["permissionMode"], "auto")
        self.assertEqual((reply["message"]["model"], bool(reply["requestId"])), ("haiku", True))
        self.assertTrue(wait_for(lambda: self.record(sid)["status"] == "idle"))
        self.assertEqual(wake.last_turn(sid, whole=True), {"mode": "auto", "model": "haiku"})
        self.assertTrue(wait_for(lambda: self.job(sid[:8])["state"] == "done"))

    def test_a_message_after_the_id_is_refused(self):
        sid = self.opened()
        for argv in (["do this"], ["--model", "haiku", "--", "x"]):
            with self.subTest(argv=argv):
                code, out, err = self.wake_flags(sid, *argv)
                self.assertEqual((code, out), (2, ""))
        self.assertEqual(len(wake_engine.violations(self.state)), 2)
        os.unlink(os.path.join(self.state, "violations"))   # this test's own, which the teardown would fail on
        self.assertIsNone(self.record(sid), "nothing started")
        code, out, err = self.wake_flags(sid)
        self.assertEqual(code, 0, err)
        self.assertIsNotNone(self.record(sid), "a wake with no message is not refused")

    def test_stop_ends_the_process_and_a_later_wake_runs_under_the_row(self):
        sid = self.opened()
        self.wake_flags(sid, "--permission-mode", "auto", "--model", "haiku")
        pid = self.record(sid)["pid"]
        code, out, err = self.claude("stop", sid[:8])
        self.assertEqual((code, out.strip()), (0, "stopped " + sid[:8]), err)
        self.assertFalse(sminos.pid_alive(pid))
        self.assertIsNone(self.record(sid))
        self.assertEqual(self.job(sid[:8])["state"], "stopped")
        self.assertIsInstance(wake.row_of(sid), dict, "stop leaves the row")
        code, out, err = self.wake_flags(sid)
        self.assertEqual(code, 0, err)
        self.assertIn("note: woke session %s with its saved options (--permission-mode, --model)." % sid[:8], err)
        self.assertEqual(out.strip(), "backgrounded · %s · term-a (idle — send a prompt to start)" % sid[:8])
        self.push(sid, sminos.compose_frame("bee", "later001", "again"))
        self.assertTrue(self.replied(sid, "later001"))
        self.assertEqual(wake.last_turn(sid, whole=True), {"mode": "auto", "model": "haiku"})

    def test_flags_with_a_row_start_a_copy_and_rm_removes_it(self):
        sid = self.opened()
        self.wake_flags(sid, "--permission-mode", "auto")
        self.claude("stop", sid[:8])
        code, out, err = self.wake_flags(sid, "--model", "haiku")
        self.assertEqual(code, 0, err)
        copy = re.search(r"backgrounded · ([0-9a-f]{8})", out).group(1)
        self.assertNotEqual(copy, sid[:8])
        self.assertIn("note: background session %s keeps its own saved options, so the flags you passed started a "
                      "copy as %s. Without flags, the same command continues %s itself." % (sid[:8], copy, sid[:8]),
                      err)
        job = self.job(copy)
        self.assertNotEqual(job["sessionId"], sid)
        self.assertIsNotNone(self.record(job["sessionId"]))
        code, out, err = self.claude("rm", copy)
        self.assertEqual((code, out.strip()), (0, "removed " + copy), err)
        self.assertIsNone(self.job(copy))
        self.assertIsNone(self.record(job["sessionId"]))
        self.assertIsNone(wake.row_of(job["sessionId"]))
        self.assertIsInstance(wake.row_of(sid), dict, "the original's row is not the copy's")


class Twin(TwinCases, Engine):
    def test_a_session_open_in_a_terminal_or_running_in_the_background_answers_a_copy(self):
        sid = self.opened()
        _, proc = self.session(sid=sid, kind="interactive")
        code, out, err = self.wake_flags(sid)
        copy = re.search(r"backgrounded · ([0-9a-f]{8})", out).group(1)
        self.assertIn("note: session %s is open in another Claude Code process, so this started a copy as %s. The "
                      "original conversation is unchanged." % (sid[:8], copy), err)
        self.end(proc)
        self.claude("rm", copy)
        self.wake_flags(sid)
        code, out, err = self.wake_flags(sid)
        copy = re.search(r"backgrounded · ([0-9a-f]{8})", out).group(1)
        self.assertIn("note: session %s is already running in the background, so this started a copy as %s. "
                      "`claude attach %s` opens the original." % (sid[:8], copy, sid[:8]), err)
        copy_sid = self.job(copy)["sessionId"]
        self.assertEqual(self.record(copy_sid)["cwd"], self.root)
        self.push(copy_sid, sminos.compose_frame("bee", "copy0001", "x"))
        self.assertTrue(self.replied(copy_sid, "copy0001"))
        self.assertEqual(wake.last_turn(copy_sid, whole=True)["mode"], "default",
                         "a copy of a running session runs under the settings' defaults")

    def test_the_held_switch_answers_either_note(self):
        sid = self.opened()
        for value, phrase in (("open", "is open in another Claude Code process"),
                              ("running", "is already running in the background")):
            self.switch("held", value)
            code, out, err = self.wake_flags(sid)
            self.assertIn(phrase, err)
            self.assertNotIn(sid[:8], out)
        self.assertIsNone(self.record(sid))

    def test_a_silent_copy(self):
        sid = self.opened()
        self.switch("silent-copy")
        code, out, err = self.wake_flags(sid)
        self.assertEqual((code, err), (0, ""))
        short = re.search(r"backgrounded · ([0-9a-f]{8})", out).group(1)
        self.assertNotEqual(short, sid[:8])
        self.assertNotEqual(self.job(short)["sessionId"], sid)

    def test_a_worker_that_fails_before_it_starts_with_the_vector_the_spike_used(self):
        sid = self.opened()
        before = self.turns(sid)
        code, out, err = self.wake_flags(sid, "--output-style", "Explanatory", "--model", "haiku")
        self.assertEqual((code, out.strip(), err), (0, "backgrounded · %s (idle — send a prompt to start)"
                                                    % sid[:8], ""))
        self.assertEqual(self.job(sid[:8])["state"], "failed")
        self.assertNotIn("pid", self.job(sid[:8]))
        row = wake.row_of(sid)
        self.assertTrue(wake.row_failed(row))
        self.assertTrue(row["detail"].startswith("exit 1 before init"))
        self.assertEqual(wake.row_options(row), ["--model", "haiku"])
        self.assertIsNone(self.record(sid))
        self.assertEqual(self.turns(sid), before)
        code, out, err = self.wake_flags(sid, "--model", "haiku")
        self.assertIn("keeps its own saved options", err, "the next flagged wake is a copy (E20)")
        self.claude("rm", re.search(r"backgrounded · ([0-9a-f]{8})", out).group(1))
        code, out, err = self.claude("rm", sid[:8])
        self.assertEqual(code, 0, err)
        self.assertIsNone(wake.row_of(sid))
        code, out, err = self.wake_flags(sid, "--permission-mode", "auto", "--model", "haiku")
        self.assertEqual((code, err), (0, ""), "after rm a flagged wake continues the same id")
        self.assertIsNotNone(self.record(sid))

    def test_the_switch_for_a_worker_that_fails_before_it_starts(self):
        sid = self.opened()
        self.switch("fail-before-start")
        code, out, err = self.wake_flags(sid, "--permission-mode", "auto")
        self.assertEqual(code, 0, err)
        row = wake.row_of(sid)
        self.assertEqual((row["state"], wake.row_options(row)), ("failed", ["--permission-mode", "auto"]))
        self.assertTrue(row["detail"].startswith("exit 1 before init"))
        self.assertIsNone(self.record(sid))

    def test_a_job_that_fails_otherwise_with_a_row_in_place(self):
        sid = self.opened()
        self.wake_flags(sid, "--permission-mode", "auto")
        self.claude("stop", sid[:8])
        self.switch("fail-job")
        code, out, err = self.wake_flags(sid)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.job(sid[:8])["state"], "failed")
        row = wake.row_of(sid)
        self.assertTrue(wake.row_failed(row))
        self.assertFalse(row["detail"].startswith("exit 1 before init"))
        self.assertEqual(wake.row_options(row), ["--permission-mode", "auto"])
        self.assertIsNone(self.record(sid))

    def test_bypass_is_refused_without_the_disclaimer(self):
        sid = self.opened()
        for flags in (["--permission-mode", "bypassPermissions"], ["--dangerously-skip-permissions"]):
            code, out, err = self.wake_flags(sid, *flags)
            self.assertEqual((code, out), (1, ""))
            self.assertIn("requires accepting the disclaimer first", err)
            self.assertIs(wake.row_of(sid), wake.UNREADABLE, "no row, and no jobs directory")
        with open(os.path.join(self.config(), "settings.json"), "w") as f:
            json.dump({"skipDangerousModePermissionPrompt": True}, f)
        code, out, err = self.wake_flags(sid, "--permission-mode", "bypassPermissions")
        self.assertEqual(code, 0, err)
        self.push(sid, sminos.compose_frame("bee", "bypass01", "x"))
        self.assertTrue(self.replied(sid, "bypass01"))
        self.assertEqual(wake.last_turn(sid, whole=True)["mode"], "bypassPermissions")

    def test_manual_is_written_default(self):
        sid = self.opened()
        self.wake_flags(sid, "--permission-mode", "manual")
        self.push(sid, sminos.compose_frame("bee", "manual01", "x"))
        self.assertTrue(self.replied(sid, "manual01"))
        self.assertEqual(wake.last_turn(sid, whole=True)["mode"], "default")

    def test_a_session_with_no_conversation_is_refused(self):
        code, out, err = self.wake_flags(str(uuidlib.uuid4()))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("No conversation found", err)

    def test_a_row_the_engine_keeps_where_sminos_cannot_read_it(self):
        sid = self.opened()
        self.switch("row-elsewhere")
        self.wake_flags(sid, "--permission-mode", "auto")
        self.assertIs(wake.row_of(sid), wake.UNREADABLE)
        self.claude("stop", sid[:8])
        code, out, err = self.wake_flags(sid, "--model", "haiku")
        self.assertIn("keeps its own saved options", err, "the engine reads its own row")

    def test_a_copy_rm_refuses(self):
        sid = self.opened()
        self.wake_flags(sid)
        code, out, err = self.wake_flags(sid)
        copy = re.search(r"backgrounded · ([0-9a-f]{8})", out).group(1)
        self.switch("rm-refuses", copy)
        code, out, err = self.claude("rm", copy)
        self.assertEqual(code, 1)
        self.assertIsNotNone(self.job(copy))
        code, out, err = self.claude("rm", sid[:8])
        self.assertEqual(code, 0, "only the shorts it names")

    def test_a_late_inbox(self):
        sid = self.opened()
        self.switch("late-inbox", 1.0)
        start = time.monotonic()
        code, out, err = self.wake_flags(sid)
        rec = self.record(sid)
        self.assertIsNotNone(rec, "its record is written at once")
        self.assertFalse(sminos.socket_ok(sminos.socket_path_of(rec)), "its inbox answers later")
        self.assertTrue(wait_for(lambda: sminos.socket_ok(sminos.socket_path_of(rec))))
        self.assertGreaterEqual(time.monotonic() - start, 0.9)

    def test_a_pid_the_engine_does_not_own_is_neither_held_nor_signalled(self):
        other = subprocess.Popen(["sleep", "60"])
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)
        os.makedirs(os.path.join(self.state, "owned"), exist_ok=True)
        gone = os.path.join(self.state, "spec-gone.json")
        for i, stale in enumerate((str(other.pid), "%d %s" % (other.pid, gone))):
            with self.subTest(stale=stale):
                sid = self.opened(name="t%d" % i)
                with open(os.path.join(self.state, "owned", sid), "w") as f:
                    f.write(stale)
                self.assertEqual(wake_engine.held_by(sid), "", "a pid alone, or one whose command is not the spec's")
                wake_engine.write_json(os.path.join(self.state, "jobs", sid[:8] + ".json"),
                                       {"id": sid[:8], "sessionId": sid, "kind": "background", "name": "t",
                                        "cwd": self.root, "state": "working", "pid": other.pid})
                for verb in ("stop", "rm"):
                    code, out, err = self.claude(verb, sid[:8])
                    self.assertEqual(code, 0, err)
                self.assertIsNone(other.poll(), "the job's public pid is evidence, never a target")

    def test_teardown_escalates_only_to_a_process_still_its_own(self):
        # A process that outlives SIGTERM, whose pid stops being this engine's helper during the wait (the
        # helper exited and the pid went to another process): teardown must not SIGKILL it.
        other = subprocess.Popen([sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, "
                                  "signal.SIG_IGN); print(1, flush=True); time.sleep(60)"], stdout=subprocess.PIPE)
        self.addCleanup(other.stdout.close)
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)
        other.stdout.readline()
        helpers = os.path.join(self.state, "helpers")
        os.makedirs(helpers, exist_ok=True)
        with open(os.path.join(helpers, str(other.pid)), "w") as f:
            f.write(os.path.join(self.state, "spec-x.json"))
        with mock.patch.object(wake_engine, "helper_pid", side_effect=[other.pid, 0]):
            wake_engine.stop_all(self.state)
        with self.assertRaises(subprocess.TimeoutExpired, msg="no longer the engine's: never escalated to"):
            other.wait(timeout=1)

    def test_a_helper_that_exits_takes_its_ownership_with_it(self):
        sid = self.opened()
        self.wake_flags(sid)
        owned = os.path.join(self.state, "owned", sid)
        self.assertTrue(os.path.exists(owned))
        pid = self.record(sid)["pid"]
        os.kill(pid, signal.SIGTERM)
        self.assertTrue(wait_for(lambda: not sminos.pid_alive(pid)))
        self.assertFalse(os.path.exists(owned))
        self.assertEqual(wake_engine.held_by(sid), "")

    def test_a_process_that_never_gets_ready_fails_the_launch(self):
        sid = self.opened()
        sessions = os.path.join(self.config(), "sessions")
        os.makedirs(sessions, exist_ok=True)
        os.chmod(sessions, 0o500)
        self.addCleanup(os.chmod, sessions, 0o700)
        code, out, err = self.wake_flags(sid)
        self.assertEqual((code, out), (1, ""), err)
        self.assertIn("did not start", err)

    def test_a_late_process(self):
        sid = self.opened()
        self.switch("late-process", 1.0)
        code, out, err = self.wake_flags(sid)
        self.assertEqual(code, 0, err)
        self.assertIsNone(self.record(sid), "no record of it yet")
        self.assertNotIn("pid", self.job(sid[:8]))
        self.assertIsNotNone(wait_for(lambda: self.record(sid)))
        self.assertTrue(wait_for(lambda: "pid" in self.job(sid[:8])))

    def test_a_late_process_removed_before_it_publishes_never_appears(self):
        sid = self.opened()
        self.switch("late-process", 1.0)
        self.wake_flags(sid)
        code, out, err = self.claude("rm", sid[:8])
        self.assertEqual((code, out.strip()), (0, "removed " + sid[:8]), err)
        time.sleep(1.5)
        self.assertIsNone(self.record(sid), "its process ended with the removal")
        self.assertIsNone(self.job(sid[:8]))
        self.assertIsNone(wake.row_of(sid))

    def test_a_second_launch_before_the_first_process_publishes_is_a_copy(self):
        sid = self.opened()
        self.switch("late-process", 1.0)
        self.wake_flags(sid)
        os.unlink(os.path.join(self.state, "late-process"))
        code, out, err = self.wake_flags(sid)
        self.assertIn("is already running in the background", err)
        self.assertNotIn(" %s " % sid[:8], out)
        self.assertIsNotNone(wait_for(lambda: self.record(sid)))
        sminos.forget_caches()
        self.assertEqual(len([r for r in sminos.peer_records() if r.get("sessionId") == sid]), 1)

    def test_a_stop_before_the_process_publishes(self):
        sid = self.opened()
        self.switch("late-process", 1.0)
        self.wake_flags(sid)
        code, out, err = self.claude("stop", sid[:8])
        self.assertEqual(code, 0, err)
        time.sleep(1.5)
        self.assertIsNone(self.record(sid))
        self.assertEqual(self.job(sid[:8])["state"], "stopped")

    def test_the_job_list_failing(self):
        self.switch("agents-fail")
        code, out, err = self.claude("agents", "--json", "--all")
        self.assertEqual(code, 1)

    def test_a_launch_that_never_returns_its_banner_while_its_process_starts(self):
        sid = self.opened()
        self.switch("no-banner", 30)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.wake_flags_timeout(sid, 1.5)
        self.assertIsNotNone(wait_for(lambda: self.record(sid)), "the process started")

    def wake_flags_timeout(self, sid, timeout):
        return subprocess.run(["claude", "--bg", "--resume", sid], cwd=self.root, capture_output=True, text=True,
                              timeout=timeout)

    def test_a_barrier_holds_two_launches_and_counts_them(self):
        sid = self.opened()
        self.switch("barrier")
        procs = [subprocess.Popen(["claude", "--bg", "--resume", sid], cwd=self.root, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) for _ in range(2)]
        self.assertTrue(wait_for(lambda: wake_engine.launches(self.state) == 2))
        self.assertIsNone(self.record(sid), "held at the barrier")
        os.unlink(os.path.join(self.state, "barrier"))
        outs = [p.communicate(timeout=30) for p in procs]
        notes = [err for _, err in outs if "already running in the background" in err]
        self.assertEqual(len(notes), 1, "one wakes the session, the other is a copy (E13 at 0.1 s)")
        self.assertEqual(wake_engine.launches(self.state), 2)

    def test_a_launch_with_a_message_runs_it_as_the_first_turn(self):
        sid = self.opened()
        self.switch("accept-message")
        code, out, err = self.wake_flags(sid, "do this")
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(os.path.join(self.state, "violations")))
        self.assertTrue(wait_for(lambda: any(r.get("type") == "assistant" and "do this" in json.dumps(r)
                                             for r in self.turns(sid))), "it runs as the first turn")
        self.assertEqual(self.record(sid)["nameSource"], "auto", "a launch with a message renames (E17)")

    def test_what_is_a_message_after_the_id(self):
        sid = str(uuidlib.uuid4())
        # A word after a variadic option is one more of its values, as the engine reads it (E22): no message.
        self.assertFalse(wake_engine.has_positional(["--bg", "--resume", sid, "--add-dir", "/a", "msg-as-dir"]))
        self.assertTrue(wake_engine.has_positional(["--bg", "--resume", sid, "x"]))
        self.assertFalse(wake_engine.has_positional(["--bg", "--resume", sid, "--permission-mode", "auto",
                                                      "--model", "m", "--add-dir", "/a", "/b",
                                                      "--dangerously-skip-permissions"]))

    def test_no_reply_a_late_reply_and_a_second_frame_answered_first(self):
        sid = self.opened()
        self.wake_flags(sid)
        self.switch("no-reply")
        self.push(sid, sminos.compose_frame("bee", "none0001", "x"))
        self.assertTrue(wait_for(lambda: any("id=none0001" in json.dumps(r) for r in self.turns(sid))))
        self.assertTrue(wait_for(lambda: self.record(sid)["status"] == "idle"))
        self.assertFalse(any(r.get("type") == "assistant" and "none0001" in json.dumps(r) for r in self.turns(sid)))
        os.unlink(os.path.join(self.state, "no-reply"))
        self.switch("reply-delay", 0.5)
        self.push(sid, sminos.compose_frame("bee", "late0001", "x"))
        self.assertTrue(wait_for(lambda: self.record(sid)["status"] == "busy"))
        self.assertTrue(self.replied(sid, "late0001"))
        os.unlink(os.path.join(self.state, "reply-delay"))
        self.switch("reply-reversed")
        self.push(sid, sminos.compose_frame("bee", "first001", "x"))
        self.push(sid, sminos.compose_frame("cee", "second01", "y"))
        self.assertTrue(self.replied(sid, "first001"))
        tail = [r for r in self.turns(sid) if r.get("type") in ("user", "assistant")][-4:]
        said = [(r["type"], m) for r in tail for m in ("first001", "second01") if m in json.dumps(r)]
        self.assertEqual(said, [("user", "second01"), ("assistant", "second01"), ("user", "first001"),
                                ("assistant", "first001")], "each reply right after its own prompt")
        arrived = [m for f in self.inputs(sid)[-2:] for m in ("first001", "second01") if m in json.dumps(f)]
        self.assertEqual(arrived, ["first001", "second01"], "inputs/ keeps the order they came in")

    def test_a_frame_for_another_session_is_refused(self):
        sid = self.opened()
        self.wake_flags(sid)
        rec = self.record(sid)
        sock = sminos.socket_path_of(rec)
        self.assertTrue(wait_for(lambda: sminos.socket_ok(sock)))
        import socket as socketlib
        s = socketlib.socket(socketlib.AF_UNIX, socketlib.SOCK_STREAM)
        s.connect(sock)
        s.sendall((json.dumps({"type": "user", "session_id": str(uuidlib.uuid4()),
                               "message": {"role": "user", "content": "id=wrong001]"}}) + "\n").encode())
        s.shutdown(socketlib.SHUT_WR)
        s.recv(10)
        s.close()
        time.sleep(0.3)
        self.assertFalse(any("wrong001" in json.dumps(r) for r in self.turns(sid)))

    def test_the_three_signals_are_files_of_their_own(self):
        sid = self.opened()
        self.switch("bridge")
        self.wake_flags(sid)
        rec = self.record(sid)
        bridge = os.path.join(os.environ["SMINOS_HOME"], "bridge", sid + ".sock")
        self.assertTrue(wait_for(lambda: os.path.exists(bridge)))
        self.assertTrue(stat.S_ISSOCK(os.stat(bridge).st_mode))
        jobfile = os.path.join(self.state, "jobs", sid[:8] + ".json")
        recfile = os.path.join(self.config(), "sessions", "%d.json" % rec["pid"])
        for path in (bridge, jobfile, recfile):
            self.assertTrue(os.path.exists(path))
        os.unlink(jobfile)
        self.assertIsNone(self.job(sid[:8]))
        self.assertIsNotNone(self.record(sid), "the record stands without the job's entry")
        os.unlink(recfile)
        self.assertIsNone(self.record(sid))
        self.assertTrue(os.path.exists(bridge))
        os.kill(rec["pid"], 15)
        self.assertTrue(wait_for(lambda: not os.path.exists(bridge)), "the bridge goes with its process")

    def test_every_launch_is_logged_with_its_directory(self):
        sid = self.opened()
        other = self.repo("elsewhere")
        self.claude("--bg", "--resume", sid, cwd=other)
        with open(os.path.join(self.state, "calls.log")) as f:
            calls = [json.loads(line) for line in f]
        self.assertEqual(calls[-1], {"argv": ["--bg", "--resume", sid], "cwd": other})
        self.assertEqual(self.record(sid)["cwd"], other, "a first wake runs where it was issued (E11)")


class Stub(TwinCases, Engine):
    """The shell stub of run-sminos-tests.sh, which hands a wake with no
    message, and the stop or removal of one of its jobs, to the twin."""
    FORM = "stub"

    def install(self, exe):
        with open(exe, "w") as f:
            f.write(stub_text())
        os.chmod(exe, 0o755)
        stub = os.path.join(self.home, "stub")
        os.makedirs(os.path.join(stub, "agents"))
        os.makedirs(os.path.join(stub, "log"))
        patcher = mock.patch.dict(os.environ, {"STUB_STATE": stub, "WAKE_ENGINE": ENGINE})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.stub = stub

    def test_a_resume_with_a_message_is_the_engine_s_and_refused(self):
        sid = self.opened()
        code, out, err = self.claude("--bg", "--resume", sid, "hello there")
        self.assertEqual((code, out), (2, ""), err)
        self.assertIsNone(self.record(sid), "nothing started")
        self.assertEqual(len(wake_engine.violations(self.state)), 1, "the engine wrote it down")
        os.unlink(os.path.join(self.state, "violations"))   # this test's own, which the teardown would fail on

    def test_the_job_list_holds_the_stub_s_jobs_and_the_twin_s(self):
        code, out, err = self.claude("--bg", "-n", "fresh", "a task")
        self.assertEqual(code, 0, err)
        short = re.search(r"backgrounded · \S*?([0-9a-f]{8})", out).group(1)
        other = self.opened()
        self.wake_flags(other)
        ids = {j["sessionId"] for j in self.jobs()}
        self.assertEqual(ids, {short + "-e808-4cad-a7e0-c1e6447bad28", other})
        row = wake.row_of(short + "-e808-4cad-a7e0-c1e6447bad28")
        self.assertEqual(wake.row_options(row), ["-n", "fresh"], "a fresh launch writes its row (E8)")
        self.switch("agents-fail")
        code, out, err = self.claude("agents", "--json", "--all")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
