"""Images (§7): the structural check on a builder, choosing the builder's type
and the current image, `image build` against the stand-in provider and
stand-in hosts (its order, a failure labeled and deleted at each step),
`image ls`, and the reaper's daily build."""
import base64
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from driver import bake_check, compose, images, reaper
from driver.errors import DriverError
from driver.ssh import Result

from driver_fixtures import KEY, NOW, DriverBase, vm_labels

HOUR = 3600
RECIPE = compose.recipe_hash(_path.DEVCLOUD)


def image(iid, recipe, created, kind="image"):
    return {"id": iid, "name": f"img-{iid}", "labels": {"devcloud": kind, "devcloud-recipe": recipe},
            "created": created}


class CurrentTest(unittest.TestCase):
    def test_the_newest_image_whose_recipe_is_current(self):
        found = images.current([image("a", "aaaaaaaaaaaa", NOW - 3 * HOUR), image("b", RECIPE, NOW - 2 * HOUR),
                                image("c", RECIPE, NOW - HOUR), image("d", "dddddddddddd", NOW)], RECIPE)
        self.assertEqual(found["id"], "c")

    def test_none_when_no_image_is_current_and_test_images_never_count(self):
        self.assertIsNone(images.current([image("a", "aaaaaaaaaaaa", NOW)], RECIPE))
        self.assertIsNone(images.current([image("t", RECIPE, NOW, kind="test")], RECIPE))
        self.assertIsNone(images.current([], RECIPE))


class BuilderTypeTest(unittest.TestCase):
    def test_the_smallest_available_type_with_the_providers_least_disk(self):
        types = [{"type": "big", "vcpus": 8, "memory_gb": 16, "disk_gb": 40, "available": True, "hourly_price": 0.4},
                 {"type": "tiny", "vcpus": 2, "memory_gb": 2, "disk_gb": 40, "available": True, "hourly_price": 0.01},
                 {"type": "roomy", "vcpus": 1, "memory_gb": 1, "disk_gb": 80, "available": True, "hourly_price": 0.005},
                 {"type": "gone", "vcpus": 1, "memory_gb": 1, "disk_gb": 20, "available": False, "hourly_price": 0.1}]
        self.assertEqual(images.builder_type(types)["type"], "tiny")

    def test_nothing_available_is_a_refusal(self):
        with self.assertRaises(DriverError) as caught:
            images.builder_type([{"type": "gone", "vcpus": 1, "disk_gb": 20, "available": False}])
        self.assertEqual(caught.exception.code, 3)


class BakeCheckTest(unittest.TestCase):
    """The structural check (§7): what a builder must not hold before it is
    snapshotted, run against a filesystem root."""

    def setUp(self):
        self.fresh()

    def fresh(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-bake-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "etc").mkdir()
        (self.root / "etc/passwd").write_text(
            "root:x:0:0:root:/root:/bin/bash\n"
            "nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n"
            "dev:x:1001:1001::/Users/dev:/bin/zsh\n")
        for home in ("root", "Users/dev"):
            (self.root / home).mkdir(parents=True)
        (self.root / "etc/devcloud/seed").mkdir(parents=True)

    def put(self, rel, text="x"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_a_clean_builder_has_no_finding(self):
        self.assertEqual(bake_check.findings(self.root), [])

    def test_each_forbidden_file_is_found(self):
        forbidden = ["etc/devcloud/boot.env", "etc/devcloud/seed/seed.json", "etc/devcloud/enroll-code",
                     "var/lib/devcloud/status.json", "var/lib/devcloud-stage/boot.env",
                     "Users/dev/.claude/sminos/daemon/hub.json", "root/.claude/sminos/daemon/machine.json",
                     "Users/dev/.config/claude-secrets/GITHUB_TOKEN", "Users/dev/.config/gcloud/legacy/adc.json",
                     "Users/dev/.config/gcloud/application_default_credentials.json"]
        forbidden += [f"Users/dev/{rel}" for rel in bake_check.CREDENTIAL_FILES]
        forbidden += [f"root/{rel}" for rel in bake_check.CREDENTIAL_FILES]
        for rel in forbidden:
            with self.subTest(rel=rel):
                self.fresh()
                self.put(rel)
                found = bake_check.findings(self.root)
                self.assertEqual(len(found), 1, found)
                self.assertTrue(found[0] == "/" + rel or ("/" + rel).startswith(found[0] + "/"), found)

    def test_gclouds_folders_without_keys_are_not_findings(self):
        self.put("Users/dev/.config/gcloud/logs/2026.10.21/x.json")
        self.put("Users/dev/.config/gcloud/configurations/config_default")
        self.assertEqual(bake_check.findings(self.root), [])

    def test_the_streamed_form_reports_and_exits_as_the_driver_reads_it(self):
        """The driver sends the module's source to `python3 - /` on the builder."""
        source = pathlib.Path(bake_check.__file__).read_bytes()
        done = subprocess.run([sys.executable, "-", str(self.root)], input=source, capture_output=True)
        self.assertEqual((done.returncode, done.stdout), (0, b""))
        self.put("Users/dev/.config/gh/hosts.yml")
        done = subprocess.run([sys.executable, "-", str(self.root)], input=source, capture_output=True)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout.decode().splitlines(), ["forbidden /Users/dev/.config/gh/hosts.yml"])

    def test_the_credential_files_are_the_guards(self):
        """parent check 6(b): the guard's own list, `secrets-sources.tsx`."""
        source = (_path.DEVCLOUD / "hooks/mods/secrets-sources.tsx").read_text()
        block = re.search(r"CREDENTIAL_FILES[^=]*=\s*\[(.*?)\n\]", source, re.S).group(1)
        self.assertEqual(sorted(re.findall(r"path: '([^']+)'", block)), sorted(bake_check.CREDENTIAL_FILES))
        self.assertIn(f"STORE_DIR = '{bake_check.STORE_DIR}'", source)
        self.assertIn(f"GCLOUD_DIR = '{bake_check.GCLOUD_DIR}'", source)
        skip = re.search(r"GCLOUD_SKIP = new Set\(\[(.*?)\]\)", source).group(1)
        self.assertEqual(set(re.findall(r"'([^']+)'", skip)), set(bake_check.GCLOUD_SKIP))


class BuildBase(DriverBase):
    """A builder that answers like a fresh Ubuntu server: SSH, cloud-init,
    setup.sh, the check, then the clean that powers it off."""

    def setUp(self):
        super().setUp()
        self.hexes = iter(["b001", "b002", "b003", "b004", "b005"])
        self.ctx = self.make_ctx(token_hex=lambda: next(self.hexes))
        self.remote.on("cloud-init status", out="status: done\n")
        self.remote.on("cloud-init clean", fn=self.power_off)

    def power_off(self, target, command):
        state = self.state()
        for server in state["servers"]:
            if server["labels"].get("devcloud") == "builder":
                server["state"] = "off"
        self.state_file.write_text(json.dumps(state))
        return Result(255, "", "", False)

    def build(self, account=None):
        return images.build_command(self.ctx, account)

    def failed(self, account=None):
        with self.assertRaises(DriverError) as caught:
            self.build(account)
        return caught.exception.code, str(caught.exception)

    def calls(self, op):
        return [c["input"] for c in self.state()["calls"] if c["op"] == op]


class BuildTest(BuildBase):
    def test_a_build_records_a_current_image_and_deletes_its_builder(self):
        self.assertEqual(self.build(), 0)
        create = self.calls("create")[0]
        self.assertEqual(create["type"], "small", "the smallest available type with the least disk")
        self.assertEqual(create["location"], "here")
        self.assertIsNone(create["image"])
        self.assertEqual(create["labels"], {"devcloud": "builder", "devcloud-by": "testmac",
                                            "devcloud-recipe": RECIPE})
        written = [base64.b64decode(b).decode() for b in re.findall(r"content: (\S+)", create["user_data"])]
        self.assertEqual(written, [KEY + "\n"], "root's keys, and nothing else")
        self.assertNotIn("devcloud-stage", create["user_data"], "a builder gets no descriptor")
        (made,) = self.state()["images"]
        self.assertEqual(made["labels"], {"devcloud": "image", "devcloud-recipe": RECIPE, "devcloud-by": "testmac"})
        self.assertEqual(made["_from"], self.state()["deleted"][0]["id"])
        self.assertEqual(self.servers(), {}, "the builder is deleted")
        self.assertIn(made["name"], self.out.getvalue())
        self.assertEqual(images.current(self.ctx.client(self.ctx.profile.account("main")).images(), RECIPE)["id"],
                         made["id"])

    def test_the_bakes_order(self):
        self.build()
        commands = self.remote.commands()

        def at(needle):
            return next(i for i, c in enumerate(commands) if needle in c)
        order = [at("true"), at("cloud-init status --wait"), at("tar -x"), at("image/setup.sh"), at("python3 - /"),
                 at("cloud-init clean")]
        self.assertEqual(order, sorted(order), commands)
        check = next(c for c in self.remote.calls if "python3 - /" in c["command"])
        self.assertEqual(check["input"], pathlib.Path(bake_check.__file__).read_bytes())
        clean = commands[order[-1]]
        for part in ("--machine-id", "/etc/ssh/ssh_host_", "/root/.ssh/authorized_keys", "tailscaled.state",
                     "poweroff"):
            self.assertIn(part, clean)
        ops = self.ops()
        self.assertLess(ops.index("image-create"), len(ops) - 1 - ops[::-1].index("delete"))
        self.assertFalse(any("seed" in c and "ledger" in c for c in commands), "a builder never gets a seed")
        self.assertFalse(any("boot.env" in c for c in commands), "nor a descriptor")

    def test_the_test_run_label_reaches_the_builder_and_the_image(self):
        self.ctx = self.make_ctx(token_hex=lambda: "b001", env={"PATH": os.environ["PATH"],
                                                                 "DEVCLOUD_TEST_RUN": "m4-unit"})
        self.build()
        self.assertEqual(self.calls("create")[0]["labels"]["devcloud-test"], "m4-unit")
        self.assertEqual(self.state()["images"][0]["labels"]["devcloud-test"], "m4-unit")

    def test_a_failure_at_each_step_labels_the_builder_and_deletes_it(self):
        cases = {"cloud-init": "cloud-init status", "setup": "image/setup.sh", "check": "python3 - /",
                 "clean": "cloud-init clean"}
        for step, needle in cases.items():
            with self.subTest(step=step):
                self.setUp()
                self.remote.rules.insert(0, {"needle": needle, "code": 1, "out": "forbidden /etc/devcloud/boot.env",
                                             "err": "", "marker": False, "target": None, "times": None, "fn": None})
                code, message = self.failed()
                self.assertEqual(code, 1)
                self.assertIn(step, message)
                self.assertEqual(self.servers(), {})
                (gone,) = self.state()["deleted"]
                self.assertEqual(gone["labels"]["devcloud-bake"], f"failed-{step}")
                self.assertEqual(self.state()["images"], [])

    def test_a_check_finding_names_the_path(self):
        self.remote.rules.insert(0, {"needle": "python3 - /", "code": 1, "out": "forbidden /etc/devcloud/boot.env\n",
                                     "err": "", "marker": False, "target": None, "times": None, "fn": None})
        code, message = self.failed()
        self.assertIn("/etc/devcloud/boot.env", message)
        self.assertNotIn("cloud-init clean", " ".join(self.remote.commands()))

    def test_a_builder_that_never_powers_off_fails_at_poweroff(self):
        self.remote.rules = [r for r in self.remote.rules if r["needle"] != "cloud-init clean"]
        code, message = self.failed()
        self.assertIn("poweroff", message)
        self.assertEqual(self.state()["deleted"][0]["labels"]["devcloud-bake"], "failed-poweroff")

    def test_a_failed_bake_whose_builder_survives_says_so(self):
        self.remote.rules.insert(0, {"needle": "image/setup.sh", "code": 1, "out": "E: broke", "err": "",
                                     "marker": False, "target": None, "times": None, "fn": None})
        self.behave(fail={"delete": 1})
        code, message = self.failed()
        self.assertEqual(code, 1)
        self.assertNotIn("is deleted", message)
        self.assertIn("is left", message)
        self.assertIn("dc-bake-b001", self.servers())

    def test_a_failed_bake_says_its_builder_is_deleted_when_it_is(self):
        self.remote.rules.insert(0, {"needle": "image/setup.sh", "code": 1, "out": "E: broke", "err": "",
                                     "marker": False, "target": None, "times": None, "fn": None})
        self.assertIn("is deleted", self.failed()[1])

    def test_a_refused_image_create_fails_at_image(self):
        self.behave(refuse={"image-create": "quota"})
        code, message = self.failed()
        self.assertEqual(code, 3)
        self.assertEqual(self.state()["deleted"][0]["labels"]["devcloud-bake"], "failed-image")

    def test_an_interrupt_still_deletes_the_builder(self):
        def interrupted(target, command):
            raise KeyboardInterrupt
        self.remote.on("image/setup.sh", fn=interrupted)
        self.remote.rules.insert(0, self.remote.rules.pop())
        with self.assertRaises(KeyboardInterrupt):
            self.build()
        self.assertEqual(self.servers(), {})
        self.assertEqual(self.state()["deleted"][0]["labels"]["devcloud-bake"], "failed-setup")

    def test_a_refused_builder_create_leaves_nothing(self):
        self.behave(refuse={"create": "limit"})
        code, message = self.failed()
        self.assertEqual(code, 3)
        self.assertEqual(self.servers(), {})

    def test_a_provider_without_images_is_exit_3(self):
        self.behave(capabilities=["user_data"])
        code, message = self.failed("main")
        self.assertEqual(code, 3)
        self.assertIn("images", message)
        self.assertNotIn("create", self.ops())

    def test_without_an_account_every_account_with_images_is_built(self):
        self.assertEqual(self.build(), 0)
        self.assertEqual(len(self.state()["images"]), 1)


class ImageLsTest(BuildBase):
    def test_lists_each_image_and_which_is_current(self):
        state = self.state()
        state["images"] = [image("i1", RECIPE, NOW - HOUR), image("i0", "aaaaaaaaaaaa", NOW - 2 * HOUR)]
        self.state_file.write_text(json.dumps(state))
        self.assertEqual(images.ls(self.ctx), 0)
        lines = self.out.getvalue().splitlines()
        self.assertTrue(lines[0].startswith("ACCOUNT"))
        current = next(line for line in lines if "img-i1" in line)
        stale = next(line for line in lines if "img-i0" in line)
        self.assertIn("current", current)
        self.assertNotIn("current", stale)


class DailyBuildTest(BuildBase):
    """§7: the reaper's unbounded run builds an image for each account that
    lacks a current one, at most once a day, never while a builder of the
    account exists, never in a bounded run."""

    def test_the_decision(self):
        stale = [image("i0", "aaaaaaaaaaaa", NOW - HOUR)]
        self.assertTrue(images.needs_build(stale, builders=[], recipe=RECIPE, last=None, now=NOW))
        self.assertFalse(images.needs_build([image("i1", RECIPE, NOW)], [], RECIPE, None, NOW))
        self.assertFalse(images.needs_build(stale, [{"name": "dc-bake-0001"}], RECIPE, None, NOW))
        self.assertFalse(images.needs_build(stale, [], RECIPE, last=NOW - 23 * HOUR, now=NOW))
        self.assertTrue(images.needs_build(stale, [], RECIPE, last=NOW - 25 * HOUR, now=NOW))

    def test_a_scheduled_run_builds_and_logs_it(self):
        self.assertEqual(reaper.run(self.ctx), 0)
        (made,) = self.state()["images"]
        self.assertEqual(made["labels"]["devcloud-recipe"], RECIPE)
        log = self.paths.reap_log.read_text()
        self.assertIn(f"built image {made['name']}", log)
        self.assertIn("main", log)
        self.assertEqual(reaper.run(self.ctx), 0)
        self.assertEqual(len(self.state()["images"]), 1, "a current image needs no build")

    def test_a_failed_build_is_not_tried_again_the_same_day(self):
        self.behave(refuse={"create": "limit"})
        self.assertEqual(reaper.run(self.ctx), 1)
        self.assertIn("image build for account main failed", self.paths.reap_log.read_text())
        self.clock.now += 23 * HOUR
        creates = len(self.calls("create"))
        reaper.run(self.ctx)
        self.assertEqual(len(self.calls("create")), creates)
        self.clock.now += 2 * HOUR
        reaper.run(self.ctx)
        self.assertEqual(len(self.calls("create")), creates + 1)

    def test_an_old_builder_whose_delete_fails_still_holds_off_the_build(self):
        """A leftover builder the reaper could not delete is still a builder:
        no second one starts beside it (its delete raising, or refused)."""
        for behavior in ({"fail": {"delete": 1}}, {"drop_on_get": "devcloud"}):
            with self.subTest(behavior=behavior):
                self.setUp()
                self.add_server("dc-bake-0001", {"devcloud": "builder", "devcloud-by": "othermac"},
                                created=self.clock.now - 3 * HOUR)
                self.behave(**behavior)
                with mock.patch.object(images, "build") as build:
                    reaper.run(self.ctx)
                build.assert_not_called()
                self.assertIn("dc-bake-0001", self.servers())

    def test_no_build_while_a_builder_exists_nor_in_a_bounded_run_nor_without_images(self):
        with mock.patch.object(images, "build") as build:
            self.add_server("dc-bake-0001", {"devcloud": "builder", "devcloud-by": "othermac"},
                            created=self.clock.now - 60)
            reaper.run(self.ctx)
            self.state_file.write_text(json.dumps(dict(self.state(), servers=[])))
            reaper.run(self.ctx, bounded=True)
            self.behave(capabilities=["user_data"])
            self.ctx = self.make_ctx()     # a new command: the provider's capabilities read again
            reaper.run(self.ctx)
        build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
