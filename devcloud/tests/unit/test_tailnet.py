"""Boot steps 2-4: the seed and the bootstrap secrets come before the tailnet
attach, which joins with the Tailscale OAuth client handed over in a
root-only file (never in an argument list), or with the fallback key file.
A fake `tailscale` on PATH records every call. Every value is made up."""

import json
import os
import pathlib
import stat
import tempfile
import textwrap
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import descriptor, proc, services, status, steps
from devcloudlib.proc import StepError

CLIENT = "tskey-client-madeupid-MadeUpClientSecret7Qx2"
CONFIG_TOKEN = "made-up-config-token-Lk9Pz3Rw"
FAKE_TAILSCALE = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, stat, sys
    log = os.environ["FAKE_TS_LOG"]
    call = {"argv": sys.argv[1:]}
    for arg in sys.argv[1:]:
        if arg.startswith("--auth-key=file:"):
            path = arg[len("--auth-key=file:"):]
            st = os.stat(path)
            call["key_mode"] = oct(stat.S_IMODE(st.st_mode))
            call["key_owner"] = st.st_uid
            call["key_dir_mode"] = oct(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode))
            call["key"] = open(path).read()
    with open(log, "a") as f:
        f.write(json.dumps(call) + "\\n")
    if sys.argv[1:2] == ["status"]:
        print(json.dumps({"BackendState": os.environ.get("FAKE_TS_STATE", "NeedsLogin")}))
    sys.exit(int(os.environ.get("FAKE_TS_EXIT", "0")) if sys.argv[1:2] == ["up"] else 0)
""")


def desc(**overrides):
    values = {
        "DEVCLOUD_NAME": "devbox-a", "DEVCLOUD_KIND": "vm", "DEVCLOUD_ROLE": "persistent",
        "DEVCLOUD_TAILSCALE": "join", "DEVCLOUD_TS_SECRET": "tailscale-client",
        "DEVCLOUD_SEED": "file:/etc/devcloud/seed.json", "DEVCLOUD_SM_PROJECT": "example-project",
        "DEVCLOUD_CONFIG_REPO": "https://github.com/example/config.git", "DEVCLOUD_CONFIG_TOKEN_SECRET": "config-token",
    }
    values.update(overrides)
    return descriptor.parse("".join(f"{k}={v}\n" for k, v in values.items() if v is not None))


class FakeTokens:
    def __init__(self, values):
        self.values = values
        self.asked = []

    def access(self, name):
        self.asked.append(name)
        value = self.values.get(name)
        return None if value is None else value.encode()


class BootOrderTest(unittest.TestCase):
    def test_the_seed_and_the_bootstrap_secrets_come_before_the_tailnet(self):
        self.assertEqual([name for name, _ in steps.BOOT], [
            "identity", "seed", "bootstrap-secrets", "tailnet-attach", "configuration", "tailnet-check",
            "secrets", "home", "apply", "settings-and-env", "services"])

    def test_the_status_file_keeps_the_boot_order(self):
        self.assertEqual(status.STEPS, tuple(name for name, _ in steps.BOOT) + ("projects",))


class TailnetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-tailnet-"))
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "tailscale"
        fake.write_text(FAKE_TAILSCALE)
        fake.chmod(0o755)
        self.log = self.tmp / "calls.jsonl"
        self.run_dir = self.tmp / "run"
        for patch in (mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}",
                                                   "FAKE_TS_LOG": str(self.log)}),
                      mock.patch.object(steps, "RUN_DIR", self.run_dir),
                      mock.patch.object(proc, "LOG_DIR", self.tmp / "log"),
                      mock.patch.object(services, "systemd_is_init", lambda: False),
                      mock.patch.object(proc, "KNOWN", proc.redact.Known())):
            patch.start()
            self.addCleanup(patch.stop)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def boot_run(self, d, values=None):
        r = steps.Run("boot")
        r.desc = d
        r.tokens = FakeTokens(values if values is not None else {"config-token": CONFIG_TOKEN,
                                                                   "tailscale-client": CLIENT + "\n"})
        return r

    def test_bootstrap_secrets_fetch_the_config_token_and_the_oauth_client(self):
        r = self.boot_run(desc())
        detail = steps.bootstrap_secrets(r)
        self.assertEqual((r.bootstrap, r.ts_secret), (CONFIG_TOKEN, CLIENT))
        self.assertEqual(r.tokens.asked, ["config-token", "tailscale-client"])
        self.assertNotIn(CLIENT, detail)
        self.assertEqual(proc.KNOWN.scrub(f"x {CLIENT}?ephemeral=false y"), "x [secret]?ephemeral=false y")

    def test_bootstrap_secrets_fetch_no_tailscale_client_unless_named(self):
        r = self.boot_run(desc(DEVCLOUD_TS_SECRET=None, DEVCLOUD_TS_AUTHKEY_FILE="/k"))
        steps.bootstrap_secrets(r)
        self.assertEqual(r.tokens.asked, ["config-token"])
        self.assertIsNone(r.ts_secret)

    def test_an_absent_oauth_client_fails_the_bootstrap_secrets(self):
        r = self.boot_run(desc(), values={"config-token": CONFIG_TOKEN})
        with self.assertRaisesRegex(StepError, "tailscale-client is absent"):
            steps.bootstrap_secrets(r)

    def test_joins_with_the_oauth_client_through_a_root_only_file(self):
        r = self.boot_run(desc())
        steps.bootstrap_secrets(r)
        detail = steps.tailnet_attach(r)
        status, up = self.calls()
        self.assertEqual(status["argv"][:2], ["status", "--json"])
        self.assertEqual(up["argv"][0], "up")
        self.assertIn("--advertise-tags=tag:devcloud", up["argv"])
        self.assertIn("--hostname=devbox-a", up["argv"])
        self.assertEqual(up["key"], CLIENT + "?ephemeral=false&preauthorized=true")
        self.assertEqual((up["key_mode"], up["key_owner"]), ("0o600", os.getuid()))
        for call in self.calls():
            self.assertFalse(any(CLIENT in arg for arg in call["argv"]), f"the client secret in argv: {call}")
        self.assertEqual(list(self.run_dir.iterdir()), [], "the key file outlived the join")
        self.assertIn("tag:devcloud", detail)
        self.assertNotIn(CLIENT, detail)

    def test_the_key_file_is_removed_when_the_join_fails(self):
        r = self.boot_run(desc())
        steps.bootstrap_secrets(r)
        with mock.patch.dict(os.environ, {"FAKE_TS_EXIT": "1"}), self.assertRaises(StepError):
            steps.tailnet_attach(r)
        self.assertEqual(list(self.run_dir.iterdir()), [])

    def test_the_fallback_joins_with_the_auth_key_file_and_deletes_it(self):
        key = self.tmp / "ts.key"
        key.write_text("tskey-auth-madeup-OneTimeKey5Hy6\n")
        r = self.boot_run(desc(DEVCLOUD_TS_SECRET=None, DEVCLOUD_TS_AUTHKEY_FILE=str(key)))
        steps.bootstrap_secrets(r)
        steps.tailnet_attach(r)
        up = self.calls()[-1]
        self.assertIn(f"--auth-key=file:{key}", up["argv"])
        self.assertNotIn("--advertise-tags=tag:devcloud", up["argv"])
        self.assertFalse(key.exists(), "the fallback key file was not deleted")

    def test_the_fallback_without_its_file_and_not_joined_fails(self):
        r = self.boot_run(desc(DEVCLOUD_TS_SECRET=None, DEVCLOUD_TS_AUTHKEY_FILE=str(self.tmp / "gone.key")))
        with self.assertRaisesRegex(StepError, "not joined"):
            steps.tailnet_attach(r)

    def test_an_already_joined_node_skips_the_join_and_drops_a_leftover_key_file(self):
        key = self.tmp / "ts.key"
        key.write_text("tskey-auth-madeup-OneTimeKey5Hy6\n")
        for d in (desc(), desc(DEVCLOUD_TS_SECRET=None, DEVCLOUD_TS_AUTHKEY_FILE=str(key))):
            with self.subTest(oauth=bool(d.ts_secret)), mock.patch.dict(os.environ, {"FAKE_TS_STATE": "Running"}):
                self.log.unlink(missing_ok=True)
                r = self.boot_run(d)
                steps.bootstrap_secrets(r)
                self.assertEqual(steps.tailnet_attach(r), "already joined")
                self.assertEqual([c["argv"][0] for c in self.calls()], ["status"])
        self.assertFalse(key.exists(), "a key file left beside a joined node")

    def test_host_and_none_do_nothing(self):
        for mode in ("host", "none"):
            r = self.boot_run(desc(DEVCLOUD_TAILSCALE=mode, DEVCLOUD_TS_SECRET=None, DEVCLOUD_KIND="container",
                                   DEVCLOUD_ROLE="sandbox"))
            steps.tailnet_attach(r)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
