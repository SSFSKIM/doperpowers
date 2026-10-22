"""Boot steps 2-4: the seed and the bootstrap secrets come before the tailnet
attach, which joins with the Tailscale OAuth client handed over in a
root-only file (never in an argument list), or with the fallback key file.
A fake `tailscale` on PATH records every call. Every value is made up."""

import hashlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import descriptor, lease, nodekind, proc, services, status, steps, tsapi
from devcloudlib.proc import StepError

CLIENT = "tskey-client-madeupid-MadeUpClientSecret7Qx2"
CONFIG_TOKEN = "made-up-config-token-Lk9Pz3Rw"
FAKE_TAILSCALE = pathlib.Path(__file__).resolve().parents[1] / "fixtures/tailscale"


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


class TailnetBase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-tailnet-"))
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "tailscale").symlink_to(FAKE_TAILSCALE)
        self.log = self.tmp / "calls.jsonl"
        self.run_dir = self.tmp / "run"
        self.kind = self.tmp / "tailnet.json"
        for patch in (mock.patch.object(nodekind, "PATH", self.kind),mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}",
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


class TailnetTest(TailnetBase):
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
        status, up = self.calls()[:2]
        self.assertEqual(status["argv"][:2], ["status", "--json"])
        self.assertEqual(up["argv"][0], "up")
        self.assertIn("--advertise-tags=tag:devcloud", up["argv"])
        self.assertIn("--hostname=devbox-a", up["argv"])
        self.assertEqual(up["key_sha256"], hashlib.sha256(CLIENT.encode()).hexdigest())
        self.assertEqual(up["key_attributes"], "ephemeral=false&preauthorized=true")
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
        self.assertIn("--auth-key=file:<path>", up["argv"])
        self.assertNotIn("--advertise-tags=tag:devcloud", up["argv"])
        self.assertFalse(key.exists(), "the fallback key file was not deleted")

    def test_the_fallback_without_its_file_and_not_joined_fails(self):
        r = self.boot_run(desc(DEVCLOUD_TS_SECRET=None, DEVCLOUD_TS_AUTHKEY_FILE=str(self.tmp / "gone.key")))
        with self.assertRaisesRegex(StepError, "not joined"):
            steps.tailnet_attach(r)

    def test_an_already_joined_node_skips_the_join_and_drops_a_leftover_key_file(self):
        key = self.tmp / "ts.key"
        key.write_text("tskey-auth-madeup-OneTimeKey5Hy6\n")
        nodekind.record(False, False, nodekind.JOINED, path=self.kind)       # kept, and joined as such
        for d in (desc(), desc(DEVCLOUD_TS_SECRET=None, DEVCLOUD_TS_AUTHKEY_FILE=str(key))):
            with self.subTest(oauth=bool(d.ts_secret)), mock.patch.dict(os.environ, {"FAKE_TS_STATE": "Running"}):
                self.log.unlink(missing_ok=True)
                r = self.boot_run(d)
                steps.bootstrap_secrets(r)
                self.assertEqual(steps.tailnet_attach(r), "already joined")
                self.assertEqual([c["argv"][0] for c in self.calls()], ["status"])
        self.assertFalse(key.exists(), "a key file left beside a joined node")

    def test_a_leased_host_joins_as_an_ephemeral_node_and_an_unleased_one_does_not(self):
        for expires, ephemeral in (("1792000000", "true"), (None, "false")):
            with self.subTest(leased=bool(expires)):
                self.log.unlink(missing_ok=True)
                r = self.boot_run(desc(DEVCLOUD_EXPIRES=expires))
                steps.bootstrap_secrets(r)
                detail = steps.tailnet_attach(r)
                up = [c for c in self.calls() if c["argv"][0] == "up"][-1]
                self.assertEqual(up["key_attributes"], f"ephemeral={ephemeral}&preauthorized=true")
                self.assertTrue(detail.endswith("ephemeral (leased)" if expires else "non-ephemeral (kept)"), detail)

    def test_a_join_records_the_kind_and_the_name_the_tailnet_gave(self):
        node = self.tmp / "node.json"
        with mock.patch.dict(os.environ, {"FAKE_TS_NODE": str(node)}):
            r = self.boot_run(desc(DEVCLOUD_EXPIRES="1792000000"))
            steps.bootstrap_secrets(r)
            steps.tailnet_attach(r)
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["state"], kind["name"]), (True, nodekind.JOINED, "devbox-a"))

    def test_a_tailnet_only_inbound_closes_the_public_port_after_the_join(self):
        nodekind.record(False, False, nodekind.JOINED, path=self.kind)
        order = []
        with mock.patch.object(steps.inbound, "apply", lambda: order.append("inbound") or "inbound closed"):
            for state in ("NeedsLogin", "Running"):
                with self.subTest(state=state), mock.patch.dict(os.environ, {"FAKE_TS_STATE": state}):
                    order.clear()
                    self.log.unlink(missing_ok=True)
                    r = self.boot_run(desc(DEVCLOUD_INBOUND="tailnet"))
                    steps.bootstrap_secrets(r)
                    detail = steps.tailnet_attach(r)
                    order[:0] = [c["argv"][0] for c in self.calls()]
                    self.assertEqual(order[-1], "inbound", "the policy before the join")
                    self.assertIn("inbound closed", detail)

    def test_a_failed_join_leaves_the_public_port_open(self):
        applied = []
        with mock.patch.object(steps.inbound, "apply", lambda: applied.append(1)), \
                mock.patch.dict(os.environ, {"FAKE_TS_EXIT": "1"}):
            r = self.boot_run(desc(DEVCLOUD_INBOUND="tailnet"))
            steps.bootstrap_secrets(r)
            with self.assertRaises(StepError):
                steps.tailnet_attach(r)
        self.assertEqual(applied, [])

    def test_open_inbound_or_a_container_writes_no_policy(self):
        applied = []
        with mock.patch.object(steps.inbound, "apply", lambda: applied.append(1)):
            for d in (desc(), desc(DEVCLOUD_INBOUND="open"), desc(DEVCLOUD_KIND="container", DEVCLOUD_INBOUND="tailnet")):
                self.log.unlink(missing_ok=True)
                r = self.boot_run(d)
                steps.bootstrap_secrets(r)
                steps.tailnet_attach(r)
        self.assertEqual(applied, [])

    def test_host_and_none_do_nothing(self):
        for mode in ("host", "none"):
            r = self.boot_run(desc(DEVCLOUD_TAILSCALE=mode, DEVCLOUD_TS_SECRET=None, DEVCLOUD_KIND="container",
                                   DEVCLOUD_ROLE="sandbox"))
            steps.tailnet_attach(r)
        self.assertEqual(self.calls(), [])


class FakeApi:
    """The Tailscale API's token and node removal, as tsapi's callers see them."""

    def __init__(self, scopes=("auth_keys", "devices:core"), delete_fails=0, node=None):
        self.scopes = list(scopes)
        self.delete_fails = delete_fails
        self.calls = []
        self.node = node
        self.joins_at_delete = []       # how many joins the stand-in tailscale had made at each removal

    def token(self, secret):
        self.calls.append(("token", secret == CLIENT))
        return tsapi.Token("made-up-access-token", self.scopes)

    def delete_node(self, tok, node_id):
        self.calls.append(("delete", node_id))
        if self.node:
            self.joins_at_delete.append(json.loads(self.node.read_text()).get("joins"))
        if self.delete_fails:
            self.delete_fails -= 1
            raise StepError("HTTP 500")
        return "removed"


class NodeKindBase(TailnetBase):
    """A joined node whose kind does not follow its lease rejoins as the kind
    it wants, under the same name: an ephemeral node leaves at its logout; a
    non-ephemeral one, which a logout leaves listed, is removed through the
    API after it (§4.1, measured 2026-10-22)."""

    def setUp(self):
        super().setUp()
        self.node = self.tmp / "node.json"
        self.api = FakeApi(node=self.node)
        for patch in (mock.patch.dict(os.environ, {"FAKE_TS_NODE": str(self.node)}),
                      mock.patch.object(steps.tsapi, "token", self.api.token),
                      mock.patch.object(steps.tsapi, "delete_node", self.api.delete_node)):
            patch.start()
            self.addCleanup(patch.stop)

    def joined_as(self, ephemeral):
        r = self.boot_run(desc(DEVCLOUD_EXPIRES="1792000000" if ephemeral else None))
        steps.bootstrap_secrets(r)
        steps.tailnet_attach(r)
        self.log.unlink(missing_ok=True)
        return json.loads(self.node.read_text())["id"]

    def attach(self, expires):
        r = self.boot_run(desc(DEVCLOUD_EXPIRES=expires))
        steps.bootstrap_secrets(r)
        return steps.tailnet_attach(r)

    def verbs(self):
        return [c["argv"][0] for c in self.calls()]

    def node_state(self, state):
        """The node tailscaled holds, in backend state `state`."""
        node = json.loads(self.node.read_text())
        node["state"] = state
        self.node.write_text(json.dumps(node))
        return node


class NodeKindTest(NodeKindBase):
    def test_a_kept_node_given_a_lease_is_removed_after_its_logout_and_joins_ephemeral(self):
        old = self.joined_as(False)
        detail = self.attach("1792000000")
        self.assertEqual(self.api.calls, [("token", True), ("delete", old)])
        self.assertEqual(self.verbs(), ["status", "status", "logout", "status", "up", "status"])
        self.assertEqual(self.calls()[4]["key_attributes"], "ephemeral=true&preauthorized=true")
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["state"], kind["name"]), (True, nodekind.JOINED, "devbox-a"))
        self.assertIn("rejoined", detail)
        self.assertIn(f"the old node {old} removed", detail)

    def test_a_leased_node_kept_leaves_at_its_logout_without_the_api(self):
        self.joined_as(True)
        detail = self.attach(None)
        self.assertEqual(self.api.calls, [])
        self.assertEqual(self.verbs(), ["status", "logout", "up", "status"])
        self.assertEqual(self.calls()[2]["key_attributes"], "ephemeral=false&preauthorized=true")
        self.assertEqual(nodekind.recorded()["ephemeral"], False)
        self.assertIn("left at its logout", detail)

    def test_a_node_of_no_recorded_kind_is_removed_too(self):
        self.joined_as(True)
        self.kind.unlink()
        self.attach("1792000000")
        self.assertEqual([c[0] for c in self.api.calls], ["token", "delete"])
        self.assertTrue(nodekind.recorded()["ephemeral"])

    def test_a_client_that_may_not_remove_nodes_changes_nothing_and_does_not_fail_the_boot(self):
        self.api.scopes = ["auth_keys", "devices:core:read"]
        self.joined_as(False)
        detail = self.attach("1792000000")
        self.assertEqual(set(self.verbs()), {"status"}, "a logout or a join ran")
        self.assertTrue(detail.startswith("already joined; not rejoined as ephemeral: "), detail)
        self.assertIn("devices:core", detail)
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["wanted"], kind["state"]), (False, True, nodekind.FAILED))
        self.assertTrue(nodekind.behind(desc(DEVCLOUD_EXPIRES="1792000000")), "the lease service would not retry")

    def test_a_removal_that_keeps_failing_still_joins_and_names_the_name_it_got(self):
        self.api.delete_fails = 3
        old = self.joined_as(False)
        with mock.patch.object(steps, "DELETE_PAUSE", 0), mock.patch.dict(os.environ, {"FAKE_TS_NAME_TAKEN": "1"}):
            detail = self.attach("1792000000")
        self.assertEqual(self.api.calls[1:], [("delete", old)] * 3)
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["state"], kind["name"]), (True, nodekind.JOINED, "devbox-a-1"))
        self.assertIn("not removed", kind["detail"])
        self.assertIn("named devbox-a-1, not devbox-a", detail)
        self.assertEqual(kind["remove"], [old], "the old node's id forgotten")
        self.assertTrue(nodekind.behind(desc(DEVCLOUD_EXPIRES="1792000000")), "the lease service would not retry")

    def test_a_pending_removal_is_retried_without_leaving_a_node_of_the_right_kind(self):
        self.api.delete_fails = 3
        old = self.joined_as(False)
        with mock.patch.object(steps, "DELETE_PAUSE", 0), mock.patch.dict(os.environ, {"FAKE_TS_NAME_TAKEN": "1"}):
            self.attach("1792000000")
        current = json.loads(self.node.read_text())["id"]
        self.log.unlink()
        self.api.calls.clear()
        detail = self.attach("1792000000")
        self.assertEqual(self.api.calls, [("token", True), ("delete", old)])
        self.assertNotIn("logout", self.verbs())
        self.assertNotIn("up", self.verbs())
        self.assertEqual(json.loads(self.node.read_text())["id"], current)
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["state"], kind["remove"]), (True, nodekind.JOINED, []))
        self.assertFalse(nodekind.behind(desc(DEVCLOUD_EXPIRES="1792000000")))
        self.assertIn(f"the old node {old} removed", detail)

    def assert_the_next_join_removes(self, old):
        """The old node, logged out and not yet removed, is remembered, and the
        next join removes it through the API before its `up`."""
        self.assertEqual(nodekind.recorded()["remove"], [old])
        self.assertTrue(nodekind.behind(desc(DEVCLOUD_EXPIRES="1792000000")), "the lease service would not retry")
        joins = json.loads(self.node.read_text())["joins"]
        self.log.unlink(missing_ok=True)
        self.api.calls.clear()
        self.api.joins_at_delete.clear()
        detail = self.attach("1792000000")
        self.assertEqual(self.api.calls, [("token", True), ("delete", old)])
        self.assertEqual(self.api.joins_at_delete, [joins], "removed after the up, which got <name>-1")
        self.assertNotIn("logout", self.verbs())
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["state"], kind["remove"]), (True, nodekind.JOINED, []))
        self.assertFalse(nodekind.behind(desc(DEVCLOUD_EXPIRES="1792000000")))
        self.assertIn(f"the old node {old} removed", detail)

    def test_a_host_stopping_between_the_logout_and_the_removal_leaves_the_removal_to_the_next_join(self):
        class HostStopped(Exception):
            pass
        old = self.joined_as(False)
        with mock.patch.object(steps.tsapi, "delete_node", side_effect=HostStopped), \
                self.assertRaises(HostStopped):
            self.attach("1792000000")
        self.assert_the_next_join_removes(old)

    def test_a_logout_that_fails_after_taking_effect_leaves_the_removal_to_the_next_join(self):
        old = self.joined_as(False)
        with mock.patch.dict(os.environ, {"FAKE_TS_LOGOUT_EXIT": "1", "FAKE_TS_LOGOUT_EFFECT": "1"}), \
                self.assertRaises(StepError):
            self.attach("1792000000")
        self.assert_the_next_join_removes(old)

    def test_a_pending_removal_that_still_fails_joins_anyway_and_keeps_the_id(self):
        old = self.joined_as(False)
        with mock.patch.dict(os.environ, {"FAKE_TS_LOGOUT_EXIT": "1", "FAKE_TS_LOGOUT_EFFECT": "1"}), \
                self.assertRaises(StepError):
            self.attach("1792000000")
        self.api.scopes = ["auth_keys"]
        with mock.patch.dict(os.environ, {"FAKE_TS_NAME_TAKEN": "1"}):
            self.attach("1792000000")
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["state"], kind["name"], kind["remove"]),
                         (True, nodekind.JOINED, "devbox-a-1", [old]))
        self.assertIn("not removed", kind["detail"])

    def test_a_stopped_or_starting_node_of_the_right_kind_resumes_with_a_plain_up(self):
        for state in ("Stopped", "Starting"):
            with self.subTest(state=state):
                self.node.unlink(missing_ok=True)
                held = self.joined_as(True)
                self.node_state(state)
                detail = self.attach("1792000000")
                self.assertEqual(self.verbs(), ["status", "up", "status"])
                self.assertEqual(self.api.calls, [])
                node = json.loads(self.node.read_text())
                self.assertEqual((node["id"], node["state"]), (held, "Running"))
                kind = nodekind.recorded()
                self.assertEqual((kind["state"], kind["detail"]), (nodekind.JOINED, "resumed as ephemeral"))
                self.assertTrue(detail.startswith("resumed"), detail)

    def test_a_stopped_node_of_the_other_kind_leaves_first(self):
        # `up` would resume it as it was joined: non-ephemeral, whatever its key now says.
        old = self.joined_as(False)
        self.node_state("Stopped")
        self.attach("1792000000")
        self.assertEqual(self.verbs(), ["status", "status", "logout", "status", "up", "status"])
        self.assertEqual(self.api.calls, [("token", True), ("delete", old)])
        node = json.loads(self.node.read_text())
        self.assertNotEqual(node["id"], old)
        self.assertTrue(node["ephemeral"], "the old node resumed and was recorded as the kind wanted")
        self.assertTrue(nodekind.recorded()["ephemeral"])

    def test_a_stopped_node_whose_rejoin_is_refused_stays_as_it_was(self):
        self.api.scopes = ["auth_keys"]
        old = self.joined_as(False)
        self.node_state("Stopped")
        detail = self.attach("1792000000")
        self.assertEqual(set(self.verbs()), {"status"}, "a logout or a join ran")
        self.assertTrue(detail.startswith("already joined; not rejoined as ephemeral: "), detail)
        self.assertEqual(json.loads(self.node.read_text())["id"], old)
        self.assertEqual(nodekind.recorded()["state"], nodekind.FAILED)

    def test_a_boot_whose_status_cannot_be_read_still_joins_as_a_kind_it_does_not_claim(self):
        with mock.patch.dict(os.environ, {"FAKE_TS_STATUS_EXIT": "1"}):
            self.attach(None)
        self.assertIn("up", self.verbs())
        kind = nodekind.recorded()
        self.assertEqual((kind["state"], kind["ephemeral"]), (nodekind.JOINED, None))
        self.assertTrue(nodekind.behind(desc()), "the lease service would not settle the kind")

    def test_a_held_node_of_the_other_kind_resumed_through_an_unreadable_status_is_not_recorded_as_wanted(self):
        old = self.joined_as(False)
        once = self.tmp / "status-fails-once"
        once.touch()
        with mock.patch.dict(os.environ, {"FAKE_TS_STATUS_FAIL_ONCE": str(once)}):
            detail = self.attach("1792000000")     # the boot step does not fail
        self.assertEqual(json.loads(self.node.read_text())["id"], old, "up resumed the node held")
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["state"], kind["name"]), (None, nodekind.JOINED, "devbox-a"))
        self.assertTrue(nodekind.behind(desc(DEVCLOUD_EXPIRES="1792000000")))
        self.assertIn("unknown", detail)
        # Once the status reads, the rejoin settles it.
        self.attach("1792000000")
        self.assertEqual(self.api.calls[-1], ("delete", old))
        self.assertTrue(json.loads(self.node.read_text())["ephemeral"])
        self.assertTrue(nodekind.recorded()["ephemeral"])

    def test_a_logout_that_fails_without_effect_and_a_reversed_lease_keep_the_node(self):
        old = self.joined_as(False)
        with mock.patch.dict(os.environ, {"FAKE_TS_LOGOUT_EXIT": "1"}):
            self.attach("1792000000")          # refused: the node stays as it was
        self.assertEqual(nodekind.recorded()["remove"], [], "the node held is down for removal")
        self.attach(None)                      # the lease change reversed
        self.assertEqual([c for c in self.api.calls if c[0] == "delete"], [])
        node = json.loads(self.node.read_text())
        self.assertEqual((node["id"], node["state"]), (old, "Running"))
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["state"], kind["remove"]), (False, nodekind.JOINED, []))

    def test_a_pending_id_of_the_node_held_is_dropped_without_a_removal(self):
        old = self.joined_as(False)
        nodekind.record(False, False, nodekind.FAILED, "the logout failed", name="devbox-a", remove=[old])
        detail = self.attach(None)
        self.assertEqual(self.api.calls, [])
        self.assertEqual(json.loads(self.node.read_text())["id"], old)
        kind = nodekind.recorded()
        self.assertEqual((kind["state"], kind["remove"]), (nodekind.JOINED, []))
        self.assertIn("cancelled", detail)

    def test_a_pending_removal_waits_while_the_node_held_cannot_be_read(self):
        old = self.joined_as(False)
        nodekind.record(None, True, nodekind.REJOINING, "logged out", remove=[old])
        with mock.patch.dict(os.environ, {"FAKE_TS_STATUS_EXIT": "1"}):
            self.attach("1792000000")
        self.assertEqual([c for c in self.api.calls if c[0] == "delete"], [])
        self.assertEqual(nodekind.recorded()["remove"], [old])

    def test_a_join_that_fails_after_the_logout_records_the_node_gone(self):
        self.joined_as(True)
        with mock.patch.dict(os.environ, {"FAKE_TS_EXIT": "1"}), self.assertRaises(StepError):
            self.attach(None)
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["state"]), (None, nodekind.FAILED))
        self.assertEqual(list(self.run_dir.glob("tailscale-auth-*")), [])


class RejoinRunTest(NodeKindBase):
    """`devcloud rejoin`, the devcloud-rejoin unit's run."""

    def setUp(self):
        super().setUp()
        self.status = self.tmp / "status.json"
        self.said = []
        for patch in (mock.patch.object(status, "PATH", self.status),
                      mock.patch.object(lease, "LOCK", self.tmp / "lifecycle.lock"),
                      mock.patch.object(steps, "_say", self.said.append),
                      mock.patch.object(steps, "_fetch_text", lambda r, name: CLIENT)):
            patch.start()
            self.addCleanup(patch.stop)
        self.expires = "1792000000"

    def rejoin(self):
        def load(r):
            r.desc = desc(DEVCLOUD_EXPIRES=self.expires)
            r.tokens = FakeTokens({})
        with mock.patch.object(steps.Run, "load", load):
            return steps.rejoin(sleep=lambda seconds: None)

    def test_rejoins_a_kept_node_given_a_lease(self):
        self.joined_as(False)
        self.assertEqual(self.rejoin(), 0)
        self.assertTrue(nodekind.recorded()["ephemeral"])
        self.assertIn("rejoin: rejoined", self.said[-1])

    def test_nothing_to_do_for_a_node_that_follows_its_lease(self):
        self.joined_as(True)
        self.assertEqual(self.rejoin(), 0)
        self.assertEqual(self.calls(), [])
        self.assertIn("already ephemeral", self.said[-1])

    def test_refused_once_the_departure_has_started(self):
        self.joined_as(False)
        status.set_lifecycle("depart", "departing", "departing")
        self.assertEqual(self.rejoin(), 3)
        self.assertEqual(self.calls(), [])

    def test_a_boot_under_way_sets_the_kind_itself(self):
        self.joined_as(False)
        with steps._locked():
            self.assertEqual(self.rejoin(), 0)
        self.assertEqual(self.calls(), [])
        self.assertIn("boot is under way", self.said[-1])

    def test_a_join_failing_after_the_logout_is_tried_three_times(self):
        self.joined_as(True)
        self.expires = None
        with mock.patch.dict(os.environ, {"FAKE_TS_EXIT": "1"}):
            self.assertEqual(self.rejoin(), 1)
        self.assertEqual(self.verbs().count("up"), 3)
        self.assertEqual(self.verbs().count("logout"), 1, "a node that had left logged out again")
        self.assertEqual(nodekind.recorded()["state"], nodekind.FAILED)

    def test_an_oauth_client_that_cannot_be_fetched_is_recorded_for_the_driver(self):
        self.joined_as(False)

        def unreachable(r, name):
            raise StepError("Secret Manager: HTTP 503")
        with mock.patch.object(steps, "_fetch_text", unreachable):
            self.assertEqual(self.rejoin(), 1)
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["wanted"], kind["state"], kind["name"]),
                         (False, True, nodekind.FAILED, "devbox-a"))
        self.assertNotIn("logout", self.verbs())

    def test_a_status_that_cannot_be_read_refuses_the_rejoin_and_changes_nothing(self):
        old = self.joined_as(False)
        with mock.patch.dict(os.environ, {"FAKE_TS_STATUS_EXIT": "1"}):
            self.assertEqual(self.rejoin(), 1)
        self.assertEqual(set(self.verbs()), {"status"}, "a logout or a join ran")
        self.assertEqual(self.api.calls, [])
        self.assertEqual(json.loads(self.node.read_text())["id"], old)
        kind = nodekind.recorded()
        self.assertEqual((kind["ephemeral"], kind["wanted"], kind["state"]), (False, True, nodekind.FAILED))
        self.assertIn("status", kind["detail"])

    def test_a_pending_removal_is_retried_by_the_rejoin(self):
        self.api.delete_fails = 3
        old = self.joined_as(False)
        with mock.patch.object(steps, "DELETE_PAUSE", 0):
            self.assertEqual(self.rejoin(), 0)
        self.assertEqual(nodekind.recorded()["remove"], [old])
        self.log.unlink()
        self.assertEqual(self.rejoin(), 0)
        self.assertEqual(self.api.calls[-1], ("delete", old))
        self.assertNotIn("logout", self.verbs())
        self.assertEqual(nodekind.recorded()["remove"], [])

    def test_a_refusal_before_any_change_fails_without_trying_again(self):
        self.api.scopes = ["auth_keys"]
        self.joined_as(False)
        self.assertEqual(self.rejoin(), 1)
        self.assertEqual(self.api.calls, [("token", True)])
        self.assertNotIn("logout", self.verbs())


class TsApiTest(unittest.TestCase):
    """The Tailscale API's token and node removal, against a stand-in urlopen."""

    SECRET = "tskey-client-kExample123-" + "madeup" * 4

    def respond(self, status_code=200, body=b"{}"):
        seen = []

        def urlopen(request, timeout):
            seen.append(request)
            if status_code >= 400:
                raise tsapi.urllib.error.HTTPError(request.full_url, status_code, "x", {}, None)
            response = mock.MagicMock()
            response.__enter__.return_value = io.BytesIO(body)
            return response
        return urlopen, seen

    def test_the_token_names_the_client_and_its_scopes(self):
        urlopen, seen = self.respond(body=b'{"access_token": "t", "scope": "auth_keys devices:core"}')
        tok = tsapi.token(self.SECRET, urlopen=urlopen)
        self.assertTrue(tok.can_delete)
        self.assertIn("client_id=kExample123", seen[0].data.decode())
        self.assertTrue(seen[0].full_url.endswith("/api/v2/oauth/token"))

    def test_read_only_device_scopes_may_not_remove(self):
        urlopen, _ = self.respond(body=b'{"access_token": "t", "scope": "auth_keys devices:core:read"}')
        self.assertFalse(tsapi.token(self.SECRET, urlopen=urlopen).can_delete)

    def test_a_refused_token_names_the_status_and_never_the_secret(self):
        urlopen, _ = self.respond(401)
        with self.assertRaises(StepError) as caught:
            tsapi.token(self.SECRET, urlopen=urlopen)
        self.assertIn("401", str(caught.exception))
        self.assertNotIn("madeup", str(caught.exception))

    def test_a_secret_that_is_not_a_client_secret_is_refused(self):
        with self.assertRaises(StepError):
            tsapi.client_id("tskey-auth-abc-def")

    def test_removes_by_node_id_and_a_gone_node_counts(self):
        tok = tsapi.Token("t", ["devices:core"])
        urlopen, seen = self.respond()
        self.assertEqual(tsapi.delete_node(tok, "nAbc123CNTRL", urlopen=urlopen), "removed")
        self.assertEqual(seen[0].get_method(), "DELETE")
        self.assertTrue(seen[0].full_url.endswith("/api/v2/device/nAbc123CNTRL"))
        self.assertEqual(seen[0].get_header("Authorization"), "Bearer t")
        urlopen, _ = self.respond(404)
        self.assertEqual(tsapi.delete_node(tok, "nAbc123CNTRL", urlopen=urlopen), "already gone")
        urlopen, _ = self.respond(403)
        with self.assertRaisesRegex(StepError, "403"):
            tsapi.delete_node(tok, "nAbc123CNTRL", urlopen=urlopen)

    def test_a_response_that_closes_before_its_length_is_a_step_error_not_a_raw_http_exception(self):
        import http.client
        tok = tsapi.Token("t", ["devices:core"])

        def truncated(request, timeout):
            response = mock.MagicMock()
            response.__enter__.return_value.read.side_effect = http.client.IncompleteRead(b"{", 100)
            return response

        def dropped(request, timeout):
            raise http.client.RemoteDisconnected("closed")

        with self.assertRaisesRegex(StepError, "IncompleteRead"):
            tsapi.token(self.SECRET, urlopen=truncated)
        with self.assertRaisesRegex(StepError, "IncompleteRead"):
            tsapi.devices(tok, urlopen=truncated)
        with self.assertRaisesRegex(StepError, "RemoteDisconnected"):
            tsapi.delete_node(tok, "nAbc123CNTRL", urlopen=dropped)


    def test_lists_the_tailnets_devices(self):
        tok = tsapi.Token("t", ["devices:core"])
        body = json.dumps({"devices": [{"nodeId": "nA1CNTRL", "hostname": "dc-kpt-e642", "tags": ["tag:devcloud"]},
                                       "not a device"]}).encode()
        urlopen, seen = self.respond(body=body)
        self.assertEqual(tsapi.devices(tok, urlopen=urlopen),
                         [{"nodeId": "nA1CNTRL", "hostname": "dc-kpt-e642", "tags": ["tag:devcloud"]}])
        self.assertTrue(seen[0].full_url.endswith("/api/v2/tailnet/-/devices"))
        self.assertEqual(seen[0].get_method(), "GET")
        self.assertEqual(seen[0].get_header("Authorization"), "Bearer t")
        urlopen, _ = self.respond(403)
        with self.assertRaisesRegex(StepError, "403"):
            tsapi.devices(tok, urlopen=urlopen)
        urlopen, _ = self.respond(body=b'{"error": "x"}')
        with self.assertRaisesRegex(StepError, "no devices"):
            tsapi.devices(tok, urlopen=urlopen)

if __name__ == "__main__":
    unittest.main()
