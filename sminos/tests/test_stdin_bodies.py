#!/usr/bin/env python3
"""A verb's prose from standard input (`-` in its place), and the plugin's launcher on a session's PATH.

Each verb in STDIN_BODIES takes its text from stdin when it is given as `-`: the handler sees the text whole,
backticks, `$`, quotes and lines kept, less the one line ending a heredoc adds; a terminal or an empty stdin is
refused with a usage error. Through main() with each handler replaced, so the parse is the real one and nothing
runs. Then `bin/sminos`, the plugin's bin/ entry, runs the CLI: from another directory, and through a symlink."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "skills/sminos/scripts"
BASE = tempfile.mkdtemp(prefix="sminos-stdin-")
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"))
sys.path.insert(0, str(SCRIPTS))
import sminos  # noqa: E402

# A body no double-quoted argument survives: a backtick span, a `$`, both quotes, two lines.
BODY = "@peer the fix is in `parse()`; $HOME stays \"as is\", it's 'kept'\nsecond line"

# Each verb that reads its prose from stdin, with the argv that puts `-` in its place.
ARGV = {
    "say": ["say", "-"],
    "send": ["send", "peer", "-"],
    "spawn": ["spawn", "helper", "-", "--brief", "owns the parser"],
    "steer": ["steer", "peer", "-"],
    "resume": ["resume", "helper", "-"],
    "fill": ["fill", "helper", "-"],
    "compact": ["compact", "peer", "-"],
}


class Stdin:
    """Standard input as a pipe or a terminal gives it."""

    def __init__(self, data=b"", tty=False):
        self.buffer = io.BytesIO(data)
        self.tty = tty

    def isatty(self):
        return self.tty


class StdinBodies(unittest.TestCase):
    def setUp(self):
        self.seen = []
        self.migrate = sminos.migrate
        self.handlers = {}
        for verb in ARGV:
            name = "cmd_" + verb
            self.handlers[name] = getattr(sminos, name)
            setattr(sminos, name, lambda a: self.seen.append(a))
        sminos.migrate = lambda *_, **__: []
        self.stdin = sys.stdin

    def tearDown(self):
        for name, fn in self.handlers.items():
            setattr(sminos, name, fn)
        sminos.migrate = self.migrate
        sys.stdin = self.stdin

    def run_main(self, argv, data=b"", tty=False):
        sys.stdin = Stdin(data, tty)
        sminos.main(list(argv))
        return self.seen[-1]

    def test_every_verb_reads_its_text_from_stdin(self):
        self.assertEqual(set(ARGV), set(sminos.STDIN_BODIES), "each verb that reads stdin is tested here")
        for verb, argv in ARGV.items():
            with self.subTest(verb=verb):
                a = self.run_main(argv, (BODY + "\n").encode())
                self.assertEqual(getattr(a, sminos.STDIN_BODIES[verb]), BODY, "the text whole, less the heredoc's newline")

    def test_the_other_arguments_parse_as_before(self):
        a = self.run_main(ARGV["spawn"], b"the task\n")
        self.assertEqual((a.alias, a.task, a.brief), ("helper", "the task", "owns the parser"))
        a = self.run_main(["say", "--org", "-"], b"to everyone\n")
        self.assertEqual((a.text, a.org), ("to everyone", True))

    def test_only_one_line_ending_is_taken(self):
        self.assertEqual(self.run_main(["say", "-"], b"a\n\n").text, "a\n")
        self.assertEqual(self.run_main(["say", "-"], b"a\r\n").text, "a")
        self.assertEqual(self.run_main(["say", "-"], b"no newline").text, "no newline")
        self.assertEqual(self.run_main(["say", "-"], "café → ok\n".encode()).text, "café → ok")

    def test_a_text_given_in_argv_is_untouched(self):
        a = self.run_main(["say", "hello - there"], b"never read\n")
        self.assertEqual(a.text, "hello - there")
        a = self.run_main(["send", "-", "msg"], b"never read\n")
        self.assertEqual((a.target, a.msg), ("-", "msg"), "only the prose's place reads stdin")

    def test_a_terminal_or_no_text_is_a_usage_error(self):
        for data, tty, says in [(b"", True, "read from standard input"), (b"", False, "no text on standard input"),
                                (b" \n\n", False, "no text on standard input")]:
            with self.subTest(data=data, tty=tty):
                err = io.StringIO()
                stderr, sys.stderr = sys.stderr, err
                try:
                    with self.assertRaises(SystemExit) as cm:
                        self.run_main(["say", "-"], data, tty)
                finally:
                    sys.stderr = stderr
                self.assertEqual(cm.exception.code, sminos.EXIT_USAGE)
                self.assertIn(says, err.getvalue())


class Launcher(unittest.TestCase):
    """bin/sminos, which the engine puts on a session's PATH, runs the CLI beside the skill."""

    def run_cli(self, path, cwd):
        return subprocess.run([str(path), "help"], cwd=cwd, capture_output=True, text=True, timeout=60)

    def test_it_runs_the_cli_from_any_directory(self):
        p = self.run_cli(PLUGIN / "bin/sminos", BASE)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("sminos say", p.stdout)

    def test_it_runs_the_cli_through_a_symlink(self):
        link = Path(BASE) / "links/sminos"
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.exists():
            link.symlink_to(PLUGIN / "bin/sminos")
        p = self.run_cli(link, "/")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("sminos say", p.stdout)

    def test_stdin_reaches_the_cli_through_it(self):
        p = subprocess.run([str(PLUGIN / "bin/sminos"), "say", "-"], input="", cwd=BASE, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, sminos.EXIT_USAGE)
        self.assertIn("no text on standard input", p.stderr)


if __name__ == "__main__":
    unittest.main()
