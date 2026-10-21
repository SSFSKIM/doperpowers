"""`provider test` and `provider register` (§6.2): the conformance sequence
on the stand-in provider and on the shipped hetzner script, its failures,
the finally-delete, the passing copy and its record, registration."""
import json
import os
import shutil

import _path  # noqa: F401
from driver import conformance, reaper
from driver.errors import DriverError
from driver.provider import pass_paths, sha256_file

from driver_fixtures import FIXTURES, NOW, DriverBase, vm_labels

import test_hetzner_provider as hz


class ConformanceBase(DriverBase):
    def setUp(self):
        super().setUp()
        # A fresh profile provider: registered, no passing copy yet.
        copy, record = pass_paths(self.profile_dir, "main")
        copy.unlink()
        record.unlink()

    def provider_test(self, **kw):
        kw.setdefault("gone_window", 3)
        kw.setdefault("running_window", 3)
        kw.setdefault("poll", 1)
        return conformance.test(self.ctx, "main", **kw)

    def fails(self, **kw):
        with self.assertRaises(DriverError) as caught:
            self.provider_test(**kw)
        return caught.exception.code, str(caught.exception)


class PassTest(ConformanceBase):
    def test_passes_and_leaves_the_tested_copy_with_its_record(self):
        self.assertEqual(self.provider_test(), 0)
        out = self.out.getvalue()
        for step in ("info ok", "types ok", "create ok", "list ok", "get ok", "set-labels ok", "images ok",
                     "delete ok", "gone ok", "pass recorded"):
            self.assertIn(step, out)
        copy, record = pass_paths(self.profile_dir, "main")
        working = self.profile_dir / "providers" / "fake"
        self.assertEqual(copy.read_bytes(), working.read_bytes())
        self.assertTrue(os.access(copy, os.X_OK))
        self.assertEqual(json.loads(record.read_text())["sha256"], sha256_file(working))
        self.assertEqual(self.servers(), {}, "its server deleted")
        self.assertEqual(self.state()["images"], [], "its image deleted")
        create = next(c for c in self.state()["calls"] if c["op"] == "create")["input"]
        self.assertEqual(create["labels"]["devcloud"], "test")
        self.assertRegex(create["labels"]["devcloud-test"], r"\Apt-[0-9]{12}-[0-9a-f]{4}\Z")
        self.assertEqual(create["type"], "small", "the smallest available type")
        # The copy serves another driver (a fresh context over the same profile).
        other = self.make_ctx(paths=type(self.paths)(profile=self.profile_dir, state=self.tmp / "other",
                                                      seed=self.seed))
        self.assertEqual(other.client(other.profile.account("main")).executable, copy)

    def test_a_passing_edit_replaces_the_copy_with_no_new_registration(self):
        self.provider_test()
        registered = self.ctx.profile.account("main").registered
        working = self.profile_dir / "providers" / "fake"
        working.write_text(working.read_text() + "\n# a passing edit\n")
        self.provider_test()
        copy, record = pass_paths(self.profile_dir, "main")
        self.assertIn("# a passing edit", copy.read_text())
        self.ctx.reload_profile()
        self.assertEqual(self.ctx.profile.account("main").registered, registered)

    def test_a_failing_edit_leaves_the_previous_copy_serving_ls_and_the_reaper(self):
        self.provider_test()
        copy, _ = pass_paths(self.profile_dir, "main")
        before = copy.read_bytes()
        working = self.profile_dir / "providers" / "fake"
        working.write_text(working.read_text().replace('labels = dict(request["labels"])',
                                                       'labels = {k: v for k, v in request["labels"].items() '
                                                       'if k != "devcloud-test"}'))
        self.assertEqual(self.fails()[0], 1)
        self.assertEqual(copy.read_bytes(), before)
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 3600), state="off")
        reaper.run(self.ctx)
        self.assertNotIn("dc-a-0001", self.servers(), "the reaper's cleanup ran through the previous copy")


class FailTest(ConformanceBase):
    def assert_fails_at(self, step, **behavior):
        self.behave(**behavior)
        code, message = self.fails()
        self.assertEqual(code, 1)
        self.assertIn(step, message)
        copy, record = pass_paths(self.profile_dir, "main")
        self.assertFalse(copy.exists(), "a failed test leaves no passing copy")

    def test_an_altered_label(self):
        self.assert_fails_at("get", alter_label={"devcloud-test": "altered"})

    def test_listing_an_unlabeled_server(self):
        self.assert_fails_at("list", list_unlabeled=True)

    def test_still_listing_a_deleted_server(self):
        self.assert_fails_at("gone", keep_deleted=True)

    def test_not_reporting_running(self):
        self.assert_fails_at("running", state_word="starting")

    def test_set_labels_that_do_not_round_trip(self):
        self.assert_fails_at("set-labels", drop_on_set="devcloud-held")

    def test_the_server_is_deleted_in_a_finally_block(self):
        self.behave(fail={"set-labels": 1})
        self.fails()
        self.assertEqual(self.servers(), {})

    def test_a_leftover_is_named_and_exit_1(self):
        self.behave(fail={"set-labels": 1, "delete": 1})
        code, message = self.fails()
        self.assertEqual(code, 1)
        leftover = list(self.servers().values())[0]["id"]
        self.assertIn(f"leftover server {leftover}", self.err.getvalue() + message)

    def test_an_unregistered_account_is_refused_before_anything_runs(self):
        toml = self.profile_dir / "driver.toml"
        toml.write_text("\n".join(l for l in toml.read_text().splitlines() if not l.startswith("registered")))
        self.ctx.reload_profile()
        code, message = self.fails()
        self.assertEqual(code, 7)
        self.assertEqual(self.state()["calls"], [], "the test is itself a credentialed run")


class RegisterTest(ConformanceBase):
    def setUp(self):
        super().setUp()
        toml = self.profile_dir / "driver.toml"
        toml.write_text("\n".join(l for l in toml.read_text().splitlines() if not l.startswith("registered")) + "\n")
        self.ctx.reload_profile()

    def test_needs_confirmed_and_records_the_sha256(self):
        with self.assertRaises(DriverError) as caught:
            conformance.register(self.ctx, "main", confirmed=False)
        self.assertEqual(caught.exception.code, 4)
        self.assertEqual(conformance.register(self.ctx, "main", confirmed=True), 0)
        self.ctx.reload_profile()
        self.assertEqual(self.ctx.profile.account("main").registered,
                         sha256_file(self.profile_dir / "providers" / "fake"))
        self.assertEqual(self.provider_test(), 0)

    def test_registering_again_replaces_the_value(self):
        conformance.register(self.ctx, "main", confirmed=True)
        working = self.profile_dir / "providers" / "fake"
        working.write_text(working.read_text() + "\n# v2\n")
        conformance.register(self.ctx, "main", confirmed=True)
        self.ctx.reload_profile()
        self.assertEqual(self.ctx.profile.account("main").registered, sha256_file(working))
        self.assertEqual((self.profile_dir / "driver.toml").read_text().count("registered"), 1)

    def test_a_shipped_provider_needs_no_registration(self):
        toml = self.profile_dir / "driver.toml"
        toml.write_text(toml.read_text().replace('provider = "fake"', 'provider = "hetzner"'))
        self.ctx.reload_profile()
        with self.assertRaises(DriverError) as caught:
            conformance.register(self.ctx, "main", confirmed=True)
        self.assertEqual(caught.exception.code, 2)


class HetznerConformanceTest(DriverBase):
    """The shipped hetzner script through the whole sequence, its image
    operations included, against the stand-in hcloud."""

    def test_passes(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "hcloud").symlink_to(FIXTURES / "hcloud")
        state = self.tmp / "hcloud.json"
        state.write_text(json.dumps({"servers": [], "images": [], "ssh_keys": [], "server_types": hz.SERVER_TYPES,
                                     "next_id": 1000, "calls": [], "fail": {}}))
        toml = self.profile_dir / "driver.toml"
        text = toml.read_text().replace('provider = "fake"', 'provider = "hetzner"').replace(
            'location = "here"', 'location = "hil"').replace('type = "medium"', 'type = "cpx31"').replace(
            'env = { FAKE_TOKEN = "fake-token-secret" }', 'env = { HCLOUD_TOKEN = "fake-token-secret" }').replace(
            f'vars = {{ FAKE_PROVIDER_STATE = "{self.state_file}" }}', f'vars = {{ FAKE_HCLOUD_STATE = "{state}" }}')
        toml.write_text(text)
        ctx = self.make_ctx(env={"PATH": f"{bin_dir}:{os.environ['PATH']}"})
        self.assertEqual(conformance.test(ctx, "main", gone_window=3, running_window=3, poll=1), 0)
        out = self.out.getvalue()
        self.assertIn("images ok", out)
        self.assertIn("shipped provider", out)
        data = json.loads(state.read_text())
        self.assertEqual(data["servers"], [])
        self.assertEqual([i for i in data["images"] if i.get("labels", {}).get("devcloud")], [])
        words = [" ".join(c[:2]) for c in data["calls"]]
        self.assertIn("server create-image", " ".join(" ".join(c) for c in data["calls"]))
        self.assertTrue(any("image delete" in " ".join(c) for c in data["calls"]), words)
