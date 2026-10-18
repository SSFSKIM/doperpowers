import base64
import pathlib
import sys
import tempfile
import unittest
import urllib.parse

import _path  # noqa: F401
from devcloudlib import proc, redact
from devcloudlib.proc import StepError, User

SECRET = "made-up-value-Zq81/Lp+x"


class KnownTest(unittest.TestCase):
    def test_scrubs_every_spelling_a_command_prints_by_accident(self):
        known = redact.Known()
        known.add(SECRET + "\n")
        raw = SECRET.encode()
        spellings = [raw, base64.b64encode(raw), base64.b64encode(raw).rstrip(b"="), base64.urlsafe_b64encode(raw),
                     raw.hex().encode(), raw.hex().upper().encode(), urllib.parse.quote(SECRET, safe="").encode()]
        for spelling in spellings:
            with self.subTest(spelling=spelling):
                out = known.scrub(b"before " + spelling + b" after")
                self.assertEqual(out, b"before [secret] after")

    def test_leaves_short_values_and_other_text_alone(self):
        known = redact.Known()
        known.add("abc")
        self.assertEqual(known.scrub(b"abc abcdef"), b"abc abcdef")
        self.assertEqual(redact.Known().scrub(b"nothing known"), b"nothing known")

    def test_host_values_reads_the_store_env_targets_and_file_targets(self):
        home = pathlib.Path(tempfile.mkdtemp())
        store = home / ".config/claude-secrets"
        (store / "projects/p").mkdir(parents=True)
        (store / "TOP").write_text("made-up-store-top\n")
        (store / "projects/p/PROJ").write_text("made-up-store-project")
        profile = home / ".claude/devcloud"
        profile.mkdir(parents=True)
        (profile / "secrets.toml").write_text(
            '[[secret]]\nname = "a"\nenv = "API_KEY"\n'
            '[[secret]]\nname = "b"\nfile = "~/hosts.yml"\ntemplate = "token: {value}\\nuser: x\\n"\n'
            '[[secret]]\nname = "c"\nfile = "~/.pgpass"\n')
        (home / "hosts.yml").write_text("token: made-up-templated\nuser: x\n")
        (home / ".pgpass").write_text("h:1:d:u:made-up-whole-file\n")
        env = home / "env"
        env.write_text('TZ="Europe/Berlin"\nAPI_KEY="made-up-env-value"\n')
        user = User(name="dev", uid=0, gid=0, home=home)
        known = redact.Known(redact.host_values(user, env_path=env))
        for value in ("made-up-store-top", "made-up-store-project", "made-up-env-value", "made-up-templated",
                      "h:1:d:u:made-up-whole-file"):
            self.assertEqual(known.scrub(f"<{value}>"), "<[secret]>", value)
        self.assertEqual(known.scrub("Europe/Berlin user: x"), "Europe/Berlin user: x")


class SignatureTest(unittest.TestCase):
    def test_changes_when_a_value_source_is_rewritten(self):
        home = pathlib.Path(tempfile.mkdtemp())
        user = User(name="dev", uid=0, gid=0, home=home)
        (home / ".claude/devcloud").mkdir(parents=True)
        (home / ".claude/devcloud/secrets.toml").write_text('[[secret]]\nname = "c"\nfile = "~/cred"\n')
        (home / "cred").write_text("made-up-one")
        env = home / "env"
        before = redact.host_signature(user, env_path=env)
        self.assertEqual(redact.host_signature(user, env_path=env), before)
        tmp = home / ".cred.tmp"
        tmp.write_text("made-up-two")
        tmp.replace(home / "cred")
        self.assertNotEqual(redact.host_signature(user, env_path=env), before)


class RunLogTest(unittest.TestCase):
    def setUp(self):
        self.saved = (proc.LOG_DIR, proc.KNOWN)
        proc.LOG_DIR = pathlib.Path(tempfile.mkdtemp())
        proc.KNOWN = redact.Known()
        proc.KNOWN.add(SECRET)

    def tearDown(self):
        proc.LOG_DIR, proc.KNOWN = self.saved

    def test_a_failing_child_that_prints_a_secret_leaves_no_value_in_its_log(self):
        script = f"import sys; print('stdout: {SECRET}'); print('stderr: {SECRET}', file=sys.stderr); sys.exit(3)"
        with self.assertRaises(StepError) as caught:
            proc.run([sys.executable, "-c", script], log="leak")
        self.assertNotIn(SECRET, str(caught.exception))
        log = (proc.LOG_DIR / "leak.log").read_text()
        self.assertNotIn(SECRET, log)
        self.assertIn("stdout: [secret]", log)
        self.assertIn("stderr: [secret]", log)

    def test_a_log_keeps_only_the_last_lines(self):
        script = "for i in range(5000): print('line', i)"
        proc.run([sys.executable, "-c", script], log="long")
        lines = (proc.LOG_DIR / "long.log").read_text().splitlines()
        self.assertLess(len(lines), 300)
        self.assertEqual(lines[-1], "line 4999")

    def test_captured_stdout_is_returned_whole_and_never_logged(self):
        out = proc.run([sys.executable, "-c", f"print('{SECRET}')"], log="capture", capture=True)
        self.assertEqual(out.strip(), SECRET)
        self.assertNotIn(SECRET, (proc.LOG_DIR / "capture.log").read_text())


if __name__ == "__main__":
    unittest.main()
