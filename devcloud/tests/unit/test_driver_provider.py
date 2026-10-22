"""The provider protocol's client (I13, §6.1, §6.2), against the stand-in
provider executable: exits, timeouts, the environment, the scrub, and which
executable an account's calls run."""
import json
import os
import shutil
import signal
import threading
import time

import _path  # noqa: F401
from driver import provider
from driver.errors import DriverError, NotOwned, Spent

from driver_fixtures import TOKEN, DriverBase, vm_labels


class ProtocolTest(DriverBase):
    def client(self):
        return self.ctx.client(self.ctx.profile.account("main"))

    def code_of(self, fn):
        with self.assertRaises(DriverError) as caught:
            fn()
        return caught.exception.code, str(caught.exception)

    def test_a_refusal_of_each_kind_is_exit_3_with_its_kind(self):
        for kind in ("limit", "quota", "unavailable", "other"):
            with self.subTest(kind=kind):
                self.behave(refuse={"create": kind})
                code, message = self.code_of(lambda: self.client().call("create", {"labels": {"devcloud": "vm"}}))
                self.assertEqual(code, 3)
                self.assertIn(f"({kind})", message)

    def test_any_other_exit_or_unparsable_stdout_is_exit_1(self):
        self.behave(fail={"list": 1})
        self.assertEqual(self.code_of(lambda: self.client().list())[0], 1)
        self.behave(fail={"list": 7})
        self.assertEqual(self.code_of(lambda: self.client().list())[0], 1)
        self.behave(fail={}, garbage=["list"])
        self.assertEqual(self.code_of(lambda: self.client().list())[0], 1)
        # A refusal whose stdout is not a refusal is a failure, not a refusal.
        self.behave(garbage=[], refuse={}, fail={"get": 3})
        self.assertEqual(self.code_of(lambda: self.client().get("1"))[0], 1)

    def test_each_timeout(self):
        ctx = self.make_ctx(timeouts={"list": 1, "create": 1})
        client = ctx.client(ctx.profile.account("main"))
        self.behave(hang=["list", "create"])
        for fn in (client.list, lambda: client.call("create", {"labels": {"devcloud": "vm"}})):
            code, message = self.code_of(fn)
            self.assertEqual(code, 1)
            self.assertIn("timed out", message)
        self.assertEqual(provider.LONG, 900)
        self.assertEqual(provider.SHORT, 120)
        self.assertEqual(set(provider.LONG_OPS), {"create", "image-create", "images", "image-delete"})

    def test_credentials_reach_the_childs_environment_only(self):
        ctx = self.make_ctx(env={"PATH": self.ctx.env["PATH"], "HOME": str(self.tmp), "DRIVER_ONLY": "x"})
        self.behave(record_env=["FAKE_TOKEN", "FAKE_PROVIDER_STATE", "DRIVER_ONLY", "HOME"])
        ctx.client(ctx.profile.account("main")).list()
        call = self.state()["calls"][-1]
        self.assertEqual(call["argv"], ["list"])
        self.assertEqual(call["env"]["FAKE_TOKEN"], TOKEN)
        self.assertEqual(call["env"]["FAKE_PROVIDER_STATE"], str(self.state_file))
        self.assertIsNone(call["env"]["DRIVER_ONLY"], "the driver's own environment leaked into the provider's")
        self.assertEqual(call["env"]["HOME"], str(self.tmp))
        self.assertEqual(self.secrets.reads, ["fake-token-secret"], "read from Secret Manager per call")
        ctx.client(ctx.profile.account("main")).list()
        self.assertEqual(self.secrets.reads, ["fake-token-secret"] * 2)

    def test_stderr_is_shown_scrubbed_of_the_credential(self):
        self.behave(stderr="auth with {env:FAKE_TOKEN} failed", fail={"list": 1})
        self.code_of(lambda: self.client().list())
        shown = self.err.getvalue()
        self.assertIn("auth with [secret] failed", shown)
        self.assertNotIn(TOKEN, shown)
        self.behave(fail={}, refuse={"create": "limit"})
        self.code_of(lambda: self.client().call("create", {"labels": {"devcloud": "vm"}}))
        self.assertNotIn(TOKEN, self.err.getvalue())

    def test_a_label_outside_i14_is_refused_before_the_provider_runs(self):
        before = len(self.state()["calls"])
        for labels in ({"devcloud": "vm", "owner": "me"}, {"devcloud": "nope"}, {"name": "x"}):
            code, _ = self.code_of(lambda: self.client().call("create", {"labels": labels}))
            self.assertEqual(code, 1)
        self.assertEqual(len(self.state()["calls"]), before)

    def test_answers_that_are_not_the_shapes_are_failures(self):
        state = self.state()
        state["servers"].append({"id": 1, "name": "x", "labels": {"devcloud": "vm"}})
        self.state_file.write_text(json.dumps(state))
        self.assertEqual(self.code_of(lambda: self.client().list())[0], 1)


class UsabilityTest(DriverBase):
    def account(self):
        return self.ctx.profile.account("main")

    def code_of(self, fn):
        with self.assertRaises(DriverError) as caught:
            fn()
        return caught.exception.code, str(caught.exception)

    def test_an_unregistered_account_is_exit_7_naming_registration(self):
        toml = self.profile_dir / "driver.toml"
        toml.write_text("\n".join(l for l in toml.read_text().splitlines() if not l.startswith("registered")))
        self.ctx.reload_profile()
        code, message = self.code_of(lambda: self.ctx.client(self.account()))
        self.assertEqual(code, 7)
        self.assertIn("not registered (the person runs devcloud vm provider register main --confirmed, then "
                      "devcloud vm provider test main)", message)

    def test_no_passing_copy_is_exit_7(self):
        (self.profile_dir / "providers" / ".pass" / "main").unlink()
        code, message = self.code_of(lambda: self.ctx.client(self.account()))
        self.assertEqual(code, 7)
        self.assertIn("no passing copy", message)

    def test_a_copy_that_does_not_match_its_record_is_exit_7(self):
        copy = self.profile_dir / "providers" / ".pass" / "main"
        copy.write_text(copy.read_text() + "\n# changed\n")
        self.assertEqual(self.code_of(lambda: self.ctx.client(self.account()))[0], 7)

    def test_every_call_runs_the_passing_copy_not_the_working_file(self):
        working = self.profile_dir / "providers" / "fake"
        working.write_text("#!/bin/sh\necho broken >&2\nexit 1\n")
        self.add_server("dc-a-0001", vm_labels(expires=1))
        names = [vm["name"] for vm in self.ctx.client(self.account()).list()]
        self.assertEqual(names, ["dc-a-0001"])

    def test_a_profile_provider_under_a_shipped_name_is_refused(self):
        shutil.copy(self.profile_dir / "providers" / "fake", self.profile_dir / "providers" / "hetzner")
        toml = self.profile_dir / "driver.toml"
        toml.write_text(toml.read_text().replace('provider = "fake"', 'provider = "hetzner"'))
        self.ctx.reload_profile()
        code, message = self.code_of(lambda: self.ctx.client(self.account()))
        self.assertEqual(code, 2)
        self.assertIn("shadows", message)

    def test_a_shipped_provider_needs_neither(self):
        toml = self.profile_dir / "driver.toml"
        toml.write_text(toml.read_text().replace('provider = "fake"', 'provider = "hetzner"'))
        self.ctx.reload_profile()
        client = self.ctx.client(self.account())
        self.assertEqual(client.executable, provider.SHIPPED_DIR / "hetzner")

    def test_a_missing_working_file_leaves_the_copy_serving(self):
        (self.profile_dir / "providers" / "fake").unlink()
        self.add_server("dc-a-0001", vm_labels(expires=1))
        self.assertEqual([vm["name"] for vm in self.ctx.client(self.account()).list()], ["dc-a-0001"])

    def test_a_change_to_the_copy_after_the_client_was_built_is_exit_7_at_the_next_call(self):
        client = self.ctx.client(self.account())
        client.list()
        calls = len(self.state()["calls"])
        copy = self.profile_dir / "providers" / ".pass" / "main"
        copy.write_text(copy.read_text() + "\n# swapped after the check\n")
        code, message = self.code_of(client.list)
        self.assertEqual(code, 7)
        self.assertIn("no longer matches its pass record", message)
        self.assertEqual(len(self.state()["calls"]), calls, "the changed copy never ran")

    def test_usable_skips_and_names_an_unusable_account(self):
        (self.profile_dir / "providers" / ".pass" / "main").unlink()
        self.assertEqual(self.ctx.usable(), [])
        self.assertIn("skipping account main", self.err.getvalue())


class GateTest(DriverBase):
    """Every delete and relabel reads its target again first (the ownership
    gate): `get` for a server, `images` for an image (I13 has no image get)."""

    def client(self):
        return self.ctx.client(self.ctx.profile.account("main"))

    def unlabel(self, sid):
        state = self.state()
        server = next(s for s in state["servers"] if s["id"] == sid)
        server["labels"] = {k: v for k, v in server["labels"].items() if k != "devcloud"}
        self.state_file.write_text(json.dumps(state))

    def test_set_labels_refuses_a_target_that_lost_the_devcloud_label(self):
        sid = self.add_server("dc-a-0001", vm_labels(expires=1))
        self.unlabel(sid)
        with self.assertRaises(NotOwned):
            self.client().set_labels(sid, vm_labels(expires=2))
        self.assertNotIn("set-labels", self.ops())
        self.assertNotIn("devcloud", self.servers()["dc-a-0001"]["labels"])

    def test_set_labels_refuses_a_target_that_is_gone(self):
        with self.assertRaises(NotOwned):
            self.client().set_labels("777", vm_labels(expires=2))
        self.assertNotIn("set-labels", self.ops())

    def test_merge_lays_the_changes_over_the_labels_read_now(self):
        sid = self.add_server("dc-a-0001", vm_labels(expires=1))
        state = self.state()
        state["servers"][0]["labels"]["devcloud-held"] = "1"     # written after this driver's list
        self.state_file.write_text(json.dumps(state))
        self.client().set_labels(sid, {"devcloud-expires": "5"}, merge=True)
        labels = self.servers()["dc-a-0001"]["labels"]
        self.assertEqual((labels["devcloud-expires"], labels["devcloud-held"]), ("5", "1"))

    def test_merge_drops_the_keys_named(self):
        sid = self.add_server("dc-a-0001", vm_labels(expires=1))
        self.client().set_labels(sid, {"devcloud-lifetime": "keep"}, merge=True, drop=("devcloud-expires",))
        labels = self.servers()["dc-a-0001"]["labels"]
        self.assertEqual(labels["devcloud-lifetime"], "keep")
        self.assertNotIn("devcloud-expires", labels)
        self.assertEqual(labels["devcloud"], "vm")

    def test_delete_refuses_an_unlabeled_target_and_one_its_fence_rejects(self):
        sid = self.add_server("dc-a-0001", vm_labels(expires=1))
        with self.assertRaises(NotOwned):
            self.client().delete(sid, fence=lambda current: "its lease changed")
        self.unlabel(sid)
        with self.assertRaises(NotOwned):
            self.client().delete(sid)
        self.assertIn("dc-a-0001", self.servers())
        self.assertNotIn("delete", self.ops())
        self.assertFalse(self.client().delete("777"), "already gone: nothing to delete")

    def images(self, *images):
        state = self.state()
        state["images"] = list(images)
        self.state_file.write_text(json.dumps(state))

    def test_the_image_fence(self):
        decided = {"devcloud": "image", "devcloud-recipe": "aaaaaaaaaaaa"}
        self.images({"id": "i1", "name": "img1", "labels": dict(decided, **{"devcloud-recipe": "bbbbbbbbbbbb"}),
                     "created": 1})
        with self.assertRaises(NotOwned):
            self.client().image_delete("i1", decided)
        self.assertEqual([i["id"] for i in self.state()["images"]], ["i1"], "relabeled since: kept")
        self.assertFalse(self.client().image_delete("i9", decided), "no longer listed: nothing to delete")
        self.images({"id": "i1", "name": "img1", "labels": decided, "created": 1})
        self.assertTrue(self.client().image_delete("i1", decided))
        self.assertEqual(self.state()["images"], [])
        self.assertEqual(self.ops()[-2:], ["images", "image-delete"], "listed again right before the delete")


class BudgetTest(DriverBase):
    """A bounded run's deadline reaches each call's credential reads and
    timeout, and no call starts once it is spent."""

    def client(self):
        return self.ctx.client(self.ctx.profile.account("main"))

    def test_no_call_starts_once_the_budget_is_spent(self):
        with self.ctx.bounded(0):
            with self.assertRaises(Spent):
                self.client().list()
        self.assertEqual(self.state()["calls"], [])
        self.assertEqual(self.secrets.reads, [], "not even the credential read")

    def test_the_budget_caps_the_timeout_and_the_credential_reads(self):
        self.behave(hang=["list"])
        started = time.monotonic()
        with self.ctx.bounded(1):
            with self.assertRaises(DriverError) as caught:
                self.client().list()
        self.assertLess(time.monotonic() - started, 10, "the 2 min list timeout was not cut to the budget")
        self.assertIn("timed out", str(caught.exception))
        self.assertTrue(all(t is not None and t <= 1 for t in self.secrets.timeouts), self.secrets.timeouts)
        self.behave(hang=[])
        self.client().list()
        self.assertIsNone(self.secrets.timeouts[-1], "outside the bounded run nothing is cut")


class InterruptTest(DriverBase):
    def test_an_interrupt_during_a_call_stops_the_providers_group(self):
        self.behave(hang=["list"])
        client = self.ctx.client(self.ctx.profile.account("main"))
        cancelled = threading.Event()

        def interrupt_once_the_provider_runs():
            # A fixed delay raced a slow start of the fake under load: interrupt once its call is
            # recorded, and never once the test is over (cancelled) or the call never came.
            deadline = time.monotonic() + 30
            while not cancelled.is_set() and time.monotonic() < deadline:
                try:
                    if self.state()["calls"]:
                        os.kill(os.getpid(), signal.SIGINT)
                        return
                except ValueError:      # read while the fake rewrote it
                    pass
                cancelled.wait(0.05)

        monitor = threading.Thread(target=interrupt_once_the_provider_runs)
        self.addCleanup(monitor.join)
        self.addCleanup(cancelled.set)
        monitor.start()
        with self.assertRaises(KeyboardInterrupt):
            client.list()
        pid = self.state()["calls"][-1]["pid"]
        self.addCleanup(_stop_group, pid)       # the client should have; never leave it running
        with self.assertRaises(ProcessLookupError):
            os.killpg(pid, 0)


def _stop_group(pgid):
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
