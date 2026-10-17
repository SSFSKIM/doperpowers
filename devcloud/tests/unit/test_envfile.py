import os
import shutil
import subprocess
import tempfile
import unittest

import _path  # noqa: F401
from devcloudlib import envfile


class ParseTest(unittest.TestCase):
    def test_bare_quoted_and_exported_assignments(self):
        text = (
            "# a comment\n"
            "\n"
            "TZ=Europe/Berlin\n"
            "export LANG=C.UTF-8\n"
            "A='single $quoted'\n"
            'B="double \\"quoted\\" \\$x"\n'
            "C=value # trailing comment\n"
        )
        self.assertEqual(
            envfile.parse(text),
            {"TZ": "Europe/Berlin", "LANG": "C.UTF-8", "A": "single $quoted",
             "B": 'double "quoted" $x', "C": "value"},
        )

    def test_expands_from_earlier_lines_then_the_base(self):
        text = 'EXTRA=/opt/x\nPATH="$EXTRA:${HOME}/bin:$PATH"\nNONE=$UNSET\n'
        got = envfile.parse(text, base={"HOME": "/Users/u", "PATH": "/usr/bin"})
        self.assertEqual(got["PATH"], "/opt/x:/Users/u/bin:/usr/bin")
        self.assertEqual(got["NONE"], "")

    def test_single_quotes_never_expand(self):
        self.assertEqual(envfile.parse("A='$HOME'\n", base={"HOME": "/h"}), {"A": "$HOME"})

    def test_rejects_what_a_shell_would_not_read_as_one_assignment(self):
        for bad in ("A=b c\n", "not an assignment\n", "1A=x\n", 'A="unterminated\n', "A=x'y\n"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                envfile.parse(bad)

    def test_an_error_names_the_line_never_its_value(self):
        with self.assertRaises(ValueError) as caught:
            envfile.parse("OK=1\nSECRET=has spaces-in-the-value\n")
        self.assertIn("line 2", str(caught.exception))
        self.assertNotIn("spaces-in-the-value", str(caught.exception))


class FormatTest(unittest.TestCase):
    TRICKY = {
        "PLAIN": "abc",
        "SPACES": "a b  c",
        "DOLLAR": "pa$$word$HOME${X}",
        "QUOTES": "it's \"quoted\"",
        "BACKSLASH": "back\\slash\\",
        "BACKTICK": "`id`",
        "EMPTY": "",
        "HASH": "a #b",
    }

    def test_round_trips_through_parse(self):
        self.assertEqual(envfile.parse(envfile.format(self.TRICKY.items())), self.TRICKY)

    def test_every_shell_reads_the_same_values(self):
        text = envfile.format(self.TRICKY.items())
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write(text)
        try:
            script = ('set -a; . "$1"; set +a; for k in ' + " ".join(self.TRICKY) +
                      '; do eval "v=\\${$k}"; printf \'%s\\000\' "$v"; done')
            for shell in [s for s in ("sh", "bash", "zsh") if shutil.which(s)]:
                with self.subTest(shell=shell):
                    out = subprocess.run([shell, "-c", script, shell, f.name], capture_output=True, check=True,
                                         env={"PATH": os.environ["PATH"], "HOME": "/nowhere"}).stdout
                    self.assertEqual(out.decode().split("\0")[:-1], list(self.TRICKY.values()))
        finally:
            os.unlink(f.name)

    def test_refuses_a_value_no_env_file_reader_can_hold(self):
        for bad in ("two\nlines", "nul\0byte"):
            with self.subTest(bad=repr(bad)), self.assertRaises(ValueError) as caught:
                envfile.format([("K", bad)])
            self.assertIn("K", str(caught.exception))
            self.assertNotIn(bad, str(caught.exception))

    def test_refuses_a_bad_name(self):
        with self.assertRaises(ValueError):
            envfile.format([("A-B", "x")])


if __name__ == "__main__":
    unittest.main()
