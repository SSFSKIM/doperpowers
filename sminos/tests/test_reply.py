#!/usr/bin/env python3
"""A seat's reply (`sminos reply`, what `send --wait` and `sync` record) and the turn's end as sminos reads it from
the transcript, for a turn that ends on a message the session sent its human through a message tool: the reply is
the last thing it said, the message's text where the turn ended on a final message, which to-human answers with a
response of its own (`answeredWithoutRequest`, no request made) that says nothing of the session's; and that response
ends the turn for the readers of its end. Through the real CLI in a temp home; the rows are shaped as the engine
writes them (2.1.312, read off a live to-human final message)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/sminos/scripts"
CLI = SCRIPTS / "sminos.py"
BASE = tempfile.mkdtemp(prefix="sminos-reply-")
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"))
sys.path.insert(0, str(SCRIPTS))
import sminos  # noqa: E402
import sminos_subagents as V  # noqa: E402

MESSAGE_TOOL = "mcp__to-human__message"
MAWS_MESSAGE_TOOL = "mcp__maws__message"
MADE_UP = "Message sent to the human."


class Rows:
    """Transcript rows as the engine writes them."""
    n = 0

    @classmethod
    def _row(cls, kind, message, **extra):
        cls.n += 1
        return {"type": kind, "uuid": "u-%d" % cls.n, "timestamp": "2026-10-28T00:18:%02d.000Z" % (cls.n % 60),
                "isSidechain": False, "message": message, **extra}

    @classmethod
    def prompt(cls, text="do the work"):
        return cls._row("user", {"role": "user", "content": text})

    @classmethod
    def text(cls, text, stop="end_turn"):
        cls.n += 1
        return cls._row("assistant", {"id": "msg_%d" % cls.n, "role": "assistant", "stop_reason": stop,
                                      "content": [{"type": "text", "text": text}]}, requestId="req_%d" % cls.n)

    @classmethod
    def call(cls, tid, name, inp):
        cls.n += 1
        return cls._row("assistant", {"id": "msg_%d" % cls.n, "role": "assistant", "stop_reason": "tool_use",
                                      "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]},
                        requestId="req_%d" % cls.n)

    @classmethod
    def result(cls, tid, text="sent", error=False):
        block = {"type": "tool_result", "tool_use_id": tid, "content": text, **({"is_error": True} if error else {})}
        return cls._row("user", {"role": "user", "content": [block]})

    @classmethod
    def made_up(cls):
        """to-human's response in place of the request after a final message, as the live row holds it."""
        cls.n += 1
        return cls._row("assistant", {"id": "msg_hook_%d" % cls.n, "role": "assistant", "model": "claude-haiku-5-5",
                                      "stop_reason": "end_turn", "stop_sequence": None, "type": "message",
                                      "usage": {"input_tokens": 0, "output_tokens": 0},
                                      "content": [{"type": "text", "text": MADE_UP, "citations": None}]},
                        isApiErrorMessage=False, isUnmetered=True, answeredWithoutRequest=True)

    @staticmethod
    def attachment(kind):
        return {"type": "attachment", "attachment": {"type": kind}}


class Reply(unittest.TestCase):
    """`sminos reply <seat>`: the reply read from the seat's transcript."""

    @classmethod
    def setUpClass(cls):
        cls.home = Path(os.environ["HOME"])
        cls.cwd = cls.home / "work"
        cls.cwd.mkdir(parents=True)
        cls.transcripts = cls.home / ".claude/projects/fake-project"
        cls.transcripts.mkdir(parents=True)
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith(("SMINOS_", "SMNS_", "CLAUDE_CODE_"))}
        cls.env.update(SMINOS_HOME=os.environ["SMINOS_HOME"], DAEMON_HOST="testhost")
        subprocess.run(["git", "init", "-q", str(cls.cwd)], env=cls.env, check=True)
        cls.cli("project", "init", "--name", "reply")
        cls.seats = 0

    @classmethod
    def cli(cls, *args):
        r = subprocess.run([sys.executable, str(CLI), *args], cwd=cls.cwd, env=cls.env, text=True, capture_output=True)
        if r.returncode:
            raise AssertionError(f"{args}: {r.returncode}\n{r.stdout}\n{r.stderr}")
        return r.stdout

    def reply(self, rows):
        """The reply `sminos reply` prints for a seat whose transcript holds `rows`."""
        type(self).seats += 1
        session = "abc0%04d-0000-4000-8000-000000000001" % self.seats
        (self.transcripts / (session + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in rows))
        seat = "seat-%d" % self.seats
        self.cli("seat", "add", "reply", seat, "--session", session)
        out = self.cli("reply", seat)
        return out.split("--- latest reply ---\n", 1)[1].strip()

    def test_a_turn_that_ended_on_a_final_message_replies_with_the_message(self):
        rows = [Rows.prompt(), Rows.text("Reading the logs.", stop="tool_use"),
                Rows.call("toolu_f1", MESSAGE_TOOL, {"text": "The build is green; PR #12 is ready.", "final": True}),
                Rows.result("toolu_f1"), Rows.attachment("total_tokens_reminder"), Rows.attachment("output_style"),
                Rows.made_up()]
        self.assertEqual(self.reply(rows), "The build is green; PR #12 is ready.")

    def test_maws_message_tool_counts_as_well(self):
        rows = [Rows.prompt(), Rows.call("toolu_m1", MAWS_MESSAGE_TOOL, {"text": "Sent through MAWS."}),
                Rows.result("toolu_m1"), Rows.made_up()]
        self.assertEqual(self.reply(rows), "Sent through MAWS.")

    def test_a_message_call_followed_by_the_models_text_replies_with_the_text(self):
        rows = [Rows.prompt(), Rows.call("toolu_m1", MESSAGE_TOOL, {"text": "Halfway there."}),
                Rows.result("toolu_m1"), Rows.text("Closing note: all done.")]
        self.assertEqual(self.reply(rows), "Closing note: all done.")

    def test_a_refused_message_is_no_reply(self):
        rows = [Rows.prompt(), Rows.text("Working on it.", stop="tool_use"),
                Rows.call("toolu_m1", MESSAGE_TOOL, {"text": "  "}),
                Rows.result("toolu_m1", "message needs its text", error=True)]
        self.assertEqual(self.reply(rows), "Working on it.")

    def test_the_model_saying_the_made_up_sentence_itself_is_its_reply(self):
        rows = [Rows.prompt(), Rows.text(MADE_UP)]
        self.assertEqual(self.reply(rows), MADE_UP)

    def test_a_pending_AskUserQuestion_is_still_rendered_after_a_final_message(self):
        rows = [Rows.prompt(), Rows.call("toolu_f1", MESSAGE_TOOL, {"text": "Earlier news.", "final": True}),
                Rows.result("toolu_f1"), Rows.made_up(), Rows.prompt("go on"),
                Rows.text("Before I pick, one question.", stop="tool_use"),
                Rows.call("toolu_q1", "AskUserQuestion",
                          {"questions": [{"question": "Which color?", "options": [{"label": "Red"}, {"label": "Blue"}]}]})]
        out = self.reply(rows)
        self.assertIn("Before I pick, one question.", out)
        self.assertIn("Q: Which color?", out)
        self.assertIn("Red / Blue", out)
        self.assertIn("[pending AskUserQuestion", out)


class TurnEnd(unittest.TestCase):
    """The made-up response ends its turn, as a finished response, for every reader of a turn's end."""

    def test_it_is_a_turn_record_and_closes_its_turn(self):
        made = Rows.made_up()
        self.assertTrue(sminos.is_turn_record(made))
        self.assertTrue(V._closes(made, made["message"]))

    def test_a_main_loop_tail_ending_on_it_reads_as_a_closed_turn_with_nothing_in_flight(self):
        rows = [Rows.prompt(), Rows.call("toolu_f1", MESSAGE_TOOL, {"text": "Done.", "final": True}),
                Rows.result("toolu_f1"), Rows.attachment("output_style"), Rows.made_up()]
        path = Path(BASE) / "tail.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        tail = V.read_tail(str(path))
        self.assertEqual((tail["last"], tail["closed"], tail["failed"], tail["inflight"]), (True, True, False, []))
        # Before it is written, the call's turn is still open, on the message's result.
        path.write_text("".join(json.dumps(r) + "\n" for r in rows[:3]))
        self.assertFalse(V.read_tail(str(path))["closed"])


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        import shutil
        shutil.rmtree(BASE, ignore_errors=True)
