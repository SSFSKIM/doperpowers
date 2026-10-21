"""`devcloud vm up` (§3) against the stand-in provider and stand-in hosts:
resolution, the caps, names, what the create carries, the recount, the
slow path's order, the seed, the wait and its output."""
import argparse
import base64
import json
import re

import _path  # noqa: F401
from devcloudlib import descriptor, redact
from driver import compose, names, up
from driver.errors import DriverError

from driver_fixtures import KEY, NOW, TOKEN, DriverBase, status_json, vm_labels

HOUR = 3600


def opts(**kw):
    base = dict(label=None, project=[], account=None, type=None, location=None, disk=None, ttl=None, keep=False,
                spot=False, enroll_code=None, confirmed=False, dry_run=False)
    base.update(kw)
    return argparse.Namespace(**base)


class UpBase(DriverBase):
    def setUp(self):
        super().setUp()
        self.hexes = iter(["7f3a", "7f3b", "7f3c", "7f3d"])
        self.ctx = self.make_ctx(token_hex=lambda: next(self.hexes))
        self.booted()

    def booted(self, failed=None):
        self.remote.rules = [r for r in self.remote.rules if "status.json" not in r["needle"]]
        out = status_json(failed=failed) + "\n" + ("failed" if failed else "active")
        self.remote.on("status.json", out=out)
        self.remote.on("cloud-init status", out="status: done\n")

    def up(self, **kw):
        return up.run(self.ctx, opts(**kw))

    def refused(self, **kw):
        with self.assertRaises(DriverError) as caught:
            self.up(**kw)
        return caught.exception.code, str(caught.exception)


class ResolveTest(UpBase):
    def test_dry_run_prints_the_request_the_caps_and_the_price_and_creates_nothing(self):
        self.assertEqual(self.up(dry_run=True), 0)
        out = self.out.getvalue()
        self.assertIn("account   main (fake)", out)
        self.assertIn("type medium (4 vCPU, 8 GB, 160 GB disk)", out)
        self.assertIn("lifetime ttl 12h", out)
        self.assertIn("0.1178 EUR/h", out)
        self.assertIn("caps      throwaway 0/3 ok, lease 12h/72h ok, size 4/8 vCPU ok, disk 160/200 GB ok", out)
        self.assertNotIn("create", self.ops())
        self.assertEqual(self.remote.calls, [])

    def test_each_cap_exits_4_before_any_create(self):
        for i in range(3):
            self.add_server(f"dc-x-000{i}", vm_labels(expires=NOW + HOUR))
        cases = ({}, {"ttl": "100h"}, {"type": "big"}, {"type": "small", "disk": 500}, {"keep": True})
        for kw in cases:
            for dry in (True, False):
                with self.subTest(kw=kw, dry=dry):
                    code, message = self.refused(dry_run=dry, **kw)
                    self.assertEqual(code, 4)
                    self.assertIn("--confirmed", message)
        self.assertNotIn("create", self.ops())

    def test_the_messages_name_their_cap(self):
        self.assertIn("lifetime cap", self.refused(ttl="100h", dry_run=True)[1])
        self.assertIn("size cap", self.refused(type="big", dry_run=True)[1])
        self.assertEqual(self.refused(type="small", disk=500, dry_run=True)[1],
                         "500 GB is over the disk cap (200 GB): ask the person, then pass --confirmed")

    def test_a_types_own_large_disk_needs_no_confirmation(self):
        self.assertEqual(self.up(type="bigdisk", dry_run=True), 0)

    def test_confirmed_passes_the_caps(self):
        for i in range(3):
            self.add_server(f"dc-x-000{i}", vm_labels(expires=NOW + HOUR))
        self.assertEqual(self.up(confirmed=True, type="big", ttl="100h", dry_run=True), 0)
        self.assertIn("confirmed", self.out.getvalue())

    def test_spot_without_the_capability_is_exit_3(self):
        code, message = self.refused(spot=True, dry_run=True)
        self.assertEqual(code, 3)
        self.assertIn("spot", message)

    def test_a_type_not_offered_is_exit_3(self):
        self.assertEqual(self.refused(type="nonesuch", dry_run=True)[0], 3)
        self.assertEqual(self.refused(type="gone", dry_run=True)[0], 3)

    def test_an_unknown_account_is_usage_and_a_bad_label_too(self):
        self.assertEqual(self.refused(account="nowhere", dry_run=True)[0], 2)
        self.assertEqual(self.refused(label="Not_OK", dry_run=True)[0], 2)
        self.assertEqual(self.refused(label="a" * 21, dry_run=True)[0], 2)
        self.assertEqual(self.refused(ttl="soon", dry_run=True)[0], 2)

    def test_an_unregistered_account_is_exit_7(self):
        (self.profile_dir / "providers" / ".pass" / "main").unlink()
        self.assertEqual(self.refused(dry_run=True)[0], 7)


class NamesTest(UpBase):
    def test_names_never_collide(self):
        taken = {"dc-vm-0001", "dc-vm-0002", "dc-vm-0003"}
        hexes = iter(["0001", "0002", "0003", "0004"])
        self.assertEqual(names.draw("vm", taken, lambda: next(hexes)), "dc-vm-0004")

    def test_up_avoids_servers_tailnet_nodes_and_desk_machines(self):
        self.add_server("dc-vm-7f3a", vm_labels(lifetime="keep", confirmed=True))
        self.tailnet_nodes.append({"name": "dc-vm-7f3b", "online": False, "tags": ["tag:devcloud"]})
        self.desk_machines.append("dc-vm-7f3c")
        self.assertEqual(self.up(), 0)
        self.assertIn("dc-vm-7f3d", self.servers())


class CreateTest(UpBase):
    def test_the_create_carries_the_labels_keys_user_data_and_no_secret(self):
        import os
        os.environ["DEVCLOUD_TEST_RUN"] = "m3-unit"
        self.addCleanup(os.environ.pop, "DEVCLOUD_TEST_RUN")
        self.ctx = self.make_ctx(token_hex=lambda: "7f3a", env={"PATH": os.environ["PATH"],
                                                                 "DEVCLOUD_TEST_RUN": "m3-unit"})
        self.assertEqual(self.up(label="build", project=["example/repo"], confirmed=True), 0)
        create = [c for c in self.state()["calls"] if c["op"] == "create"][0]["input"]
        self.assertEqual(create["name"], "dc-build-7f3a")
        self.assertEqual(create["labels"], {
            "devcloud": "vm", "devcloud-lifetime": "ttl", "devcloud-expires": str(NOW + 12 * HOUR),
            "devcloud-by": "testmac", "devcloud-creator": "abcd1234",
            "devcloud-recipe": compose.recipe_hash(_path.DEVCLOUD), "devcloud-confirmed": "1",
            "devcloud-test": "m3-unit"})
        self.assertNotIn("set-labels", self.ops(), "labels go in the create, never a later call")
        self.assertEqual(create["ssh_public_keys"], [KEY])
        self.assertIsNone(create["image"])
        staged = [base64.b64decode(b).decode() for b in re.findall(r"content: (\S+)", create["user_data"])]
        desc = descriptor.parse(staged[1])
        self.assertEqual((desc.name, desc.expires, desc.creator, desc.projects),
                         ("dc-build-7f3a", NOW + 12 * HOUR, "@abcd1234", ("example/repo",)))
        known = redact.Known([TOKEN, self.seed.read_text()])
        self.assertEqual(known.scrub(create["user_data"]), create["user_data"], "a secret value in user-data")

    def test_the_slow_path_order_and_the_seed(self):
        self.assertEqual(self.up(), 0)
        commands = self.remote.commands()
        def at(needle):
            return next(i for i, c in enumerate(commands) if needle in c)
        order = [at("true"), at("cloud-init status --wait"), at("tar -x"), at("image/setup.sh"),
                 at("devcloud ledger add /etc/devcloud/seed/seed.json"), at("cat > /etc/devcloud/seed/seed.json.tmp"),
                 at(f"install -m 0600 -o root -g root {compose.STAGE} /etc/devcloud/boot.env"),
                 at("systemctl start --no-block devcloud-boot.service"), at("status.json")]
        self.assertEqual(order, sorted(order), commands)
        seed_call = next(c for c in self.remote.calls if "seed.json.tmp" in c["command"])
        self.assertEqual(seed_call["input"], self.seed.read_bytes(), "the seed goes on stdin")
        self.assertNotIn(self.seed.read_text(), " ".join(commands))
        setup = next(c for c in self.remote.calls if "setup.sh" in c["command"])
        self.assertIn("DEVCLOUD_USER=dev DEVCLOUD_UID=1001 DEVCLOUD_HOME=/Users/dev", setup["command"])
        first = self.remote.calls[0]
        self.assertEqual(first["target"], "203.0.113.101", "first contact is the public address")
        self.assertEqual(first["alias"], "devcloud-main-101", "keyed by the server, not its address")

    def test_a_failed_setup_stops_before_the_seed(self):
        self.remote.on("image/setup.sh", code=1, out="E: broke\n")
        code, message = self.refused()
        self.assertEqual(code, 1)
        self.assertIn("setup.sh", message)
        self.assertEqual(self.remote.commands("seed"), [])
        self.assertIn("dc-vm-7f3a", self.servers(), "a failure after the create leaves the VM with its lease")

    def test_the_wait_moves_to_the_tailnet_once_attached_and_prints_the_summary(self):
        self.remote.rules = [r for r in self.remote.rules if "status.json" not in r["needle"]]
        attached = json.dumps({"steps": [{"name": n, "state": "ok", "at": "t", "detail": ""}
                                         for n in ("identity", "seed", "bootstrap-secrets", "tailnet-attach")]})
        self.remote.on("status.json", out=attached + "\nactivating", target="203.0.113.101", times=1)
        self.remote.on("status.json", code=255, target="203.0.113.101")
        self.remote.on("status.json", out=status_json() + "\nactive", target="dc-vm-7f3a")
        self.assertEqual(self.up(), 0)
        out = self.out.getvalue()
        self.assertIn("dc-vm-7f3a", out)
        self.assertIn("fake/main", out)
        self.assertIn("tailnet   dc-vm-7f3a", out)
        self.assertIn("0.1178 EUR/h", out)
        self.assertIn("built from base, slow path", out)

    def test_a_failed_step_prints_the_status_and_exits_1_keeping_the_vm(self):
        self.booted(failed="secrets")
        code, message = self.refused()
        self.assertEqual(code, 1)
        self.assertIn("secrets", message)
        self.assertIn("secrets", self.err.getvalue() + self.out.getvalue())
        self.assertIn("dc-vm-7f3a", self.servers())

    def test_a_boot_that_never_finishes_times_out_at_15_minutes(self):
        self.remote.rules = [r for r in self.remote.rules if "status.json" not in r["needle"]]
        self.remote.on("status.json", out='{"steps": []}\nactivating')
        start = self.clock.now
        code, message = self.refused()
        self.assertEqual(code, 1)
        self.assertIn("15 minutes", message)
        self.assertLessEqual(self.clock.now - start, 16 * 60)

    def test_a_driver_key_not_yet_pushed_stops_before_anything_is_created(self):
        self.ctx = self.make_ctx(token_hex=lambda: "7f3a", key_pushed=lambda: False)
        code, message = self.refused()
        self.assertEqual(code, 1)
        self.assertIn("sync", message)
        self.assertNotIn("create", self.ops())

    def test_a_refused_create_is_exit_3_and_leaves_nothing(self):
        self.behave(refuse={"create": "limit"})
        code, message = self.refused()
        self.assertEqual(code, 3)
        self.assertIn("(limit)", message)
        self.assertEqual(self.servers(), {})

    def test_the_enrollment_code_after_the_boot(self):
        self.assertEqual(self.up(enroll_code=b"smns-enroll-v1.madeup\n"), 0)
        create = [c for c in self.state()["calls"] if c["op"] == "create"][0]["input"]
        self.assertEqual(create["labels"]["devcloud-enroll"], "code")
        commands = self.remote.commands()
        ledger = next(i for i, c in enumerate(commands) if "ledger add /etc/devcloud/enroll-code" in c)
        write = next(i for i, c in enumerate(commands) if "cat > /etc/devcloud/enroll-code.tmp" in c)
        reconcile = next(i for i, c in enumerate(commands) if c == "devcloud reconcile")
        self.assertLess(ledger, write)
        self.assertLess(write, reconcile)
        code_call = next(c for c in self.remote.calls if "enroll-code.tmp" in c["command"])
        self.assertEqual(code_call["input"], b"smns-enroll-v1.madeup\n")
        self.assertEqual(code_call["target"], "dc-vm-7f3a", "over the tailnet")


class RecountTest(UpBase):
    def test_racing_past_the_cap_deletes_its_own_vm_and_exits_4(self):
        for i in range(2):
            self.add_server(f"dc-x-000{i}", vm_labels(expires=NOW + HOUR), created=NOW - 60)

        def racing(state):
            # Another driver created one between this driver's count and its create.
            pass

        self.behave(now=NOW)
        # The other driver's VM appears right after this driver's count: insert it through the stand-in's state
        # before create runs, by making the count see two and the recount four.
        original_fleet = self.ctx.fleet
        calls = {"n": 0}

        def fleet(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 2:  # the count of step 1 has run; the other driver's VM lands now
                self.add_server("dc-other-0001", vm_labels(expires=NOW + HOUR), created=NOW - 1)
            return original_fleet(*a, **kw)

        self.ctx.fleet = fleet
        code, message = self.refused()
        self.assertEqual(code, 4)
        self.assertNotIn("dc-vm-7f3a", self.servers(), "its own VM, the newest, deleted")
        self.assertIn("dc-other-0001", self.servers())
        self.assertNotIn("seed", " ".join(self.remote.commands()))

    def test_a_confirmed_vm_is_not_counted_and_the_recount_spares_it(self):
        for i in range(3):
            self.add_server(f"dc-x-000{i}", vm_labels(expires=NOW + HOUR))
        self.assertEqual(self.up(confirmed=True), 0)
        self.assertIn("dc-vm-7f3a", self.servers())
        self.assertEqual(self.servers()["dc-vm-7f3a"]["labels"]["devcloud-confirmed"], "1")


if __name__ == "__main__":
    import unittest
    unittest.main()
