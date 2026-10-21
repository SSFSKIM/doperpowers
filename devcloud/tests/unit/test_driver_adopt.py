"""`devcloud vm adopt` and the life of an adopted machine (§6.5, M5): the
contract driven through the same core the live run uses, against a stand-in
SSH target — refusals, each phase recorded before the step it names, resume
from each phase, `ls`, `lease` on the host and the record alone, `down`
releasing over the tailnet or the recorded address, the record removed only
after a verified release, and a reaper that never touches it."""
import argparse
import base64
import json
import pathlib
import tempfile

import _path  # noqa: F401
from devcloudlib import descriptor
from driver import adopt, adopt_host, compose, ops, reaper
from driver.errors import DriverError
from driver.ssh import Result

from driver_fixtures import KEY, NOW, DriverBase, FakeRemote, status_json

ADDRESS = "203.0.113.50"
NAME = "dc-adp-7f3a"


class Target(FakeRemote):
    """A plain Ubuntu 24.04 server reached as `login`@ADDRESS with the
    person's key, and, once adopt authorized it, as root with the driver's;
    after its boot only over the tailnet (the public port closed), until a
    release opens it again."""

    def __init__(self, test, login="root"):
        super().__init__()
        self.test = test
        self.login = login
        self.m = {"os": ("ubuntu", "24.04"), "descriptor": None, "keys_saved": False, "authorized": False,
                  "setup": 0, "seeded": 0, "booted": 0, "tailnet": False, "public": True, "released": False,
                  "boot_ok": True, "release_code": None, "unpushed": False, "lease": None,
                  # A release that stopped after it gave the keys back and logged out: the driver's
                  # key no longer works, the person's login does again, the descriptor stays.
                  "restored": False, "fail_after_restore": False}
        self.phases = {}       # step → the record's phase when it ran

    def _phase(self, step):
        records = list((self.test.state_dir / "adopted").glob("*.json"))
        self.phases.setdefault(step, json.loads(records[0].read_text())["phase"] if records else None)

    def run(self, target, alias, command, *, user="root", input=None, timeout=60, connect_timeout=10, person=False):
        self.calls.append({"kind": "run", "target": target, "alias": alias, "command": command, "user": user,
                           "input": input, "person": person})
        m = self.m
        if target == ADDRESS:
            if not m["public"]:
                return Result(255, "", "connection timed out")
            if person:
                replaced = self.login == "root" and m["booted"] and not (m["released"] or m["restored"])
                if user != self.login or replaced:
                    return Result(255, "", "Permission denied (publickey)")
            elif not m["authorized"] or m["released"] or m["restored"]:
                return Result(255, "", "Permission denied (publickey)")
        elif target == NAME:
            if not m["tailnet"]:
                return Result(255, "", "no route")
        else:
            return Result(255, "", "unknown host")
        return self.answer(command, input)

    def answer(self, command, input):
        m = self.m
        if command.endswith("true") and len(command) < 40:
            return Result(0, "", "")
        if "python3 - inspect" in command:
            return Result(0, json.dumps({"id": m["os"][0], "version": m["os"][1], "descriptor": m["descriptor"]}), "")
        if "python3 - preflight" in command:
            self.test.assertIn("preflight dev 1001 /Users/dev", command, "the profile's build.env")
            m["preflights"] = m.get("preflights", 0) + 1
            return Result(0, json.dumps({"problems": m.get("account_problems", [])}), "")
        if "python3 - rollback" in command:
            self._phase("rollback")
            if m.get("rollback_fails"):
                return Result(1, "", "rollback: the ledger lists /home/x, which only `devcloud release` removes")
            m.update(released=True, keys_saved=False, seeded=0, staged=None)
            return Result(0, "rolled back", "")
        if "python3 - save-keys" in command:
            self._phase("save-keys")
            m["keys_saved"] = True
            return Result(0, "saved", "")
        if "python3 - authorize" in command:
            self._phase("authorize")
            keys = base64.b64decode(command.split()[-1]).decode()
            self.test.assertIn(KEY, keys)
            m["authorized"] = True
            return Result(0, "authorized 1 key(s)", "")
        if "image/setup.sh" in command:
            self._phase("setup")
            m["setup"] += 1
            return Result(0, "", "")
        if f"cat > {compose.STAGE}" in command:
            self._phase("stage")
            m["staged"] = input.decode()
            return Result(0, "", "")
        if "cat > /etc/devcloud/seed/seed.json.tmp" in command:
            self._phase("seed")
            m["seeded"] += 1
            return Result(0, "", "")
        if "systemctl start --no-block devcloud-boot.service" in command:
            self._phase("boot")
            m["booted"] += 1
            m["descriptor"] = {"name": NAME, "adopted": True}
            if m["boot_ok"]:
                m["tailnet"], m["public"] = True, False
            return Result(0, "", "")
        if "status.json" in command and "lifecycle" not in command:
            if not m["booted"]:
                return Result(0, "{}\ninactive", "")
            return Result(0, status_json(failed=None if m["boot_ok"] else "seed") + "\n" +
                          ("inactive" if m["boot_ok"] else "failed"), "")
        if "devcloud unpushed" in command:
            return Result(5, "repo\tahead 1\n", "") if m["unpushed"] else Result(0, "", "")
        if "devcloud lease set" in command:
            m["lease"] = int(command.split()[3])
            return Result(0, f"{m['lease']}\n", "")
        if "credentials.ledger" in command:
            return Result(0 if m["released"] else 1, "", "")
        return Result(0, "", "")

    def stream(self, target, alias, command, *, user="root", timeout=60, marker=None, person=False):
        self.calls.append({"kind": "stream", "target": target, "alias": alias, "command": command, "user": user,
                           "input": None, "person": person})
        reach = self.run(target, alias, "true", user=user, person=person)
        self.calls.pop()
        if reach.code != 0:
            return Result(255, "", "unreachable", False)
        self._phase("release")
        if self.m["fail_after_restore"]:
            # remove-units failed after restore-keys and logout: off the tailnet, the keys given back.
            self.m.update(fail_after_restore=False, restored=True, tailnet=False, public=True)
            return Result(1, hostctl_ready(), "", True)
        if self.m["release_code"] is not None:
            return Result(self.m["release_code"], "", "", False)
        if self.m["descriptor"] is None:
            # No boot ever installed it: `devcloud release` has nothing to load.
            return Result(1, "devcloud release: /etc/devcloud/boot.env: not found\n", "", False)
        self.m.update(released=True, tailnet=False, public=True, descriptor=None)
        return Result(255, self.m.get("release_out", "") + hostctl_ready(), "", True)

    def targets_of(self, needle):
        return [c["target"] for c in self.calls if needle in c["command"]]


def hostctl_ready():
    from driver import hostctl
    return hostctl.READY + "\n"


def opts(**kw):
    base = dict(target=f"root@{ADDRESS}", label="adp", project=[], ttl=None, confirmed=True, dry_run=False)
    base.update(kw)
    return argparse.Namespace(**base)


class AdoptBase(DriverBase):
    def setUp(self):
        super().setUp()
        self.remote = Target(self)
        self.hexes = iter(["7f3a", "7f3b"])
        self.ctx = self.make_ctx(token_hex=lambda: next(self.hexes))

    def adopt(self, **kw):
        return adopt.run(self.ctx, opts(**kw))

    def refused(self, **kw):
        with self.assertRaises(DriverError) as caught:
            self.adopt(**kw)
        return caught.exception.code, str(caught.exception)

    def record(self):
        path = self.state_dir / "adopted" / f"{NAME}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def write_record(self, phase, **over):
        record = {"name": NAME, "address": ADDRESS, "user": "root", "lifetime": "ttl", "expires": NOW + 7200,
                  "projects": [], "phase": phase, "created": NOW - 600, "ready": None, "creator": "abcd1234"}
        record.update(over)
        (self.state_dir / "adopted").mkdir(parents=True, exist_ok=True)
        (self.state_dir / "adopted" / f"{NAME}.json").write_text(json.dumps(record))


class RefusalTest(AdoptBase):
    def test_without_confirmed_is_exit_4_dry_run_too_and_nothing_is_contacted(self):
        for dry in (False, True):
            code, message = self.refused(confirmed=False, dry_run=dry)
            self.assertEqual(code, 4)
            self.assertIn("--confirmed", message)
        self.assertEqual(self.remote.calls, [])

    def test_a_dry_run_contacts_nothing_and_records_nothing(self):
        self.assertEqual(self.adopt(dry_run=True, ttl="2h"), 0)
        self.assertEqual(self.remote.calls, [])
        self.assertIsNone(self.record())
        self.assertIn(f"root@{ADDRESS}", self.out.getvalue())

    def test_a_driver_key_not_yet_in_the_configuration_repository_is_refused_before_any_contact(self):
        """The boot's home step makes root's keys the configuration
        repository's: without this Mac's key there, the driver would lose the
        machine once its public port closed."""
        self.ctx = self.make_ctx(token_hex=lambda: next(self.hexes), key_pushed=lambda: False)
        code, message = self.refused()
        self.assertEqual(code, 1)
        self.assertIn("configuration repository", message)
        self.assertEqual(self.remote.calls, [])
        self.assertIsNone(self.record())
        self.assertEqual(self.adopt(dry_run=True), 0, "a dry run changes nothing, so it is not refused")

    def test_a_target_that_is_not_user_at_address_is_usage(self):
        for target in (ADDRESS, "@" + ADDRESS, "root@", "Root;x@" + ADDRESS):
            self.assertEqual(self.refused(target=target)[0], 2)

    def test_not_ubuntu_24_04_is_refused_before_any_change(self):
        self.remote.m["os"] = ("ubuntu", "22.04")
        code, message = self.refused()
        self.assertEqual(code, 1)
        self.assertIn("Ubuntu 24.04", message)
        self.assertIsNone(self.record())
        self.assertFalse(self.remote.m["keys_saved"])

    def test_an_existing_host_with_no_matching_record_is_refused(self):
        self.remote.m["descriptor"] = {"name": "dc-other-0001", "adopted": False}
        code, message = self.refused()
        self.assertEqual(code, 1)
        self.assertIn("vm ls", message)
        self.assertIsNone(self.record())
        self.assertFalse(self.remote.m["keys_saved"])

    def test_a_record_that_does_not_match_the_descriptor_is_refused(self):
        self.write_record("booted")
        self.remote.m.update(descriptor={"name": "dc-other-0001", "adopted": True}, authorized=True)
        code, _ = self.refused()
        self.assertEqual(code, 1)
        self.assertEqual(self.remote.m["booted"], 0)


class AdoptionTest(AdoptBase):
    def test_each_phase_is_recorded_before_the_step_it_names(self):
        self.assertEqual(self.adopt(ttl="2h", project=["example/repo"]), 0)
        self.assertEqual(self.remote.phases, {"save-keys": "preparing", "authorize": "preparing",
                                              "setup": "preparing", "stage": "preparing", "seed": "seeded",
                                              "boot": "booted"})
        record = self.record()
        self.assertEqual(record["phase"], "booted")
        self.assertEqual(record["ready"], NOW)
        self.assertEqual((record["address"], record["user"], record["lifetime"]), (ADDRESS, "root", "ttl"))
        self.assertEqual(record["expires"], NOW + 7200)

    def test_the_order_the_keys_and_the_descriptor(self):
        self.assertEqual(self.adopt(), 0)
        commands = self.remote.commands()
        def at(needle):
            return next(i for i, c in enumerate(commands) if needle in c)
        order = [at("python3 - inspect"), at("python3 - save-keys root"), at("python3 - authorize"), at("tar -x"),
                 at("image/setup.sh"),
                 at("devcloud ledger add /etc/devcloud/seed/seed.json /etc/devcloud/seed/seed.json.tmp"),
                 at("seed.json.tmp"), at("systemctl start --no-block devcloud-boot.service")]
        self.assertEqual(order, sorted(order), commands)
        person = [c["command"] for c in self.remote.calls if c["person"]]
        self.assertTrue(person and all("inspect" in c or "preflight" in c or "save-keys" in c or "authorize" in c
                                       or c.endswith("true") for c in person), person)
        self.assertEqual({c["alias"] for c in self.remote.calls}, {NAME}, "keyed by the machine's name")
        desc = descriptor.parse(self.remote.m["staged"])
        self.assertEqual((desc.name, desc.adopted, desc.seed_kind, desc.inbound), (NAME, True, "file", "tailnet"))
        self.assertIsNone(desc.expires, "an adopted machine is kept unless --ttl")
        self.assertEqual(self.record()["lifetime"], "keep")
        self.assertIn("adopted", self.out.getvalue())
        self.assertNotIn("create", self.ops(), "no provider is asked to make anything")

    def test_a_login_user_other_than_root_works_through_sudo(self):
        self.remote.login = "ubuntu"
        self.assertEqual(self.adopt(target=f"ubuntu@{ADDRESS}"), 0)
        save = next(c for c in self.remote.calls if "save-keys" in c["command"])
        self.assertEqual((save["user"], save["person"]), ("ubuntu", True))
        self.assertTrue(save["command"].startswith("sudo -n "))
        self.assertIn("save-keys ubuntu", save["command"])

    def test_an_account_setup_sh_would_remove_or_take_over_is_refused_before_any_change(self):
        """Adopting ubuntu@addr, ubuntu at uid 1000, with a profile wanting uid
        1000 for another name: setup.sh would `userdel -r ubuntu`, and the
        release could never give the login back."""
        self.remote.login = "ubuntu"
        self.remote.m["account_problems"] = ["uid 1001 belongs to ubuntu"]
        code, message = self.refused(target=f"ubuntu@{ADDRESS}")
        self.assertEqual(code, 1)
        self.assertIn("uid 1001 belongs to ubuntu", message)
        self.assertIn("never deletes or replaces", message)
        self.assertFalse(self.remote.m["keys_saved"])
        self.assertFalse(self.remote.m["authorized"])
        self.assertEqual(self.remote.m["setup"], 0)
        self.assertIsNone(self.record())

    def test_setup_sh_runs_told_it_is_adopting(self):
        self.assertEqual(self.adopt(), 0)
        [setup] = self.remote.commands("image/setup.sh")
        self.assertIn("DEVCLOUD_ADOPTING=1", setup)

    def test_root_logins_refused_by_the_machine_stop_after_the_keys(self):
        self.remote.login = "ubuntu"
        original = self.remote.answer
        def no_root(command, input):
            if "python3 - authorize" in command:
                return Result(0, "", "")     # authorized, but sshd refuses root
            return original(command, input)
        self.remote.answer = no_root
        code, message = self.refused(target=f"ubuntu@{ADDRESS}")
        self.assertEqual(code, 1)
        self.assertIn("root", message)
        self.assertEqual(self.remote.m["setup"], 0)

    def test_a_boot_that_fails_keeps_the_record_at_booted(self):
        self.remote.m["boot_ok"] = False
        code, message = self.refused()
        self.assertEqual(code, 1)
        self.assertEqual(self.record()["phase"], "booted")
        self.assertIsNone(self.record()["ready"])


class ResumeTest(AdoptBase):
    def test_from_preparing(self):
        self.write_record("preparing")
        self.remote.m.update(keys_saved=True)
        self.assertEqual(self.adopt(), 0)
        self.assertIn("resuming", self.out.getvalue())
        self.assertEqual(self.remote.m["setup"], 1)
        self.assertEqual(self.record()["phase"], "booted")

    def test_a_resume_after_setup_sh_made_the_account_preflights_again_on_the_machine(self):
        """The machine keeps the preflight's verdict: the account setup.sh made
        on the first run is not a reason to refuse the second."""
        self.write_record("preparing")
        self.remote.m.update(keys_saved=True)
        self.assertEqual(self.adopt(), 0)
        self.assertEqual(self.remote.m["preflights"], 1)

    def test_from_seeded_skips_the_preparation(self):
        self.write_record("seeded")
        self.remote.m.update(keys_saved=True, authorized=True)
        self.assertEqual(self.adopt(), 0)
        self.assertEqual(self.remote.m["setup"], 0)
        self.assertEqual(self.remote.commands("save-keys"), [])
        self.assertEqual(self.remote.m["seeded"], 1)
        self.assertEqual(self.remote.m["booted"], 1)

    def test_from_booted_after_a_crash_with_the_descriptor_installed(self):
        """The descriptor is on the machine but the boot never finished: the
        matching record makes adopt resume, not refuse."""
        self.write_record("booted")
        self.remote.m.update(keys_saved=True, authorized=True, descriptor={"name": NAME, "adopted": True})
        self.assertEqual(self.adopt(), 0)
        self.assertEqual(self.remote.m["seeded"], 0)
        self.assertEqual(self.remote.m["booted"], 1)
        self.assertEqual(self.record()["ready"], NOW)

    def test_from_booted_once_the_boot_has_finished_starts_nothing(self):
        self.write_record("booted")
        self.remote.m.update(keys_saved=True, authorized=True, descriptor={"name": NAME, "adopted": True}, booted=1,
                             tailnet=True, public=False)
        self.assertEqual(self.adopt(), 0)
        self.assertEqual(self.remote.m["booted"], 1)
        self.assertEqual(self.record()["ready"], NOW)

    def test_a_release_under_way_is_downs_to_finish(self):
        self.write_record("released")
        code, message = self.refused()
        self.assertEqual(code, 1)
        self.assertIn("devcloud vm down", message)
        self.assertEqual(self.remote.calls, [])

    def test_the_record_is_found_by_its_target_whatever_the_flags(self):
        self.write_record("seeded")
        self.remote.m.update(keys_saved=True, authorized=True)
        self.assertEqual(self.adopt(label="other", ttl="5h"), 0)
        self.assertEqual(self.record()["expires"], NOW + 7200, "a resume keeps what was recorded")
        self.assertIn("ignored", self.out.getvalue())


class LsLeaseTest(AdoptBase):
    def test_ls_lists_adopted_machines_and_an_incomplete_adoption_with_its_phase(self):
        self.write_record("seeded")
        self.tailnet_nodes.append({"name": NAME, "online": True, "tags": ["tag:devcloud"]})
        ops.ls(self.ctx, as_json=True)
        data = json.loads(self.out.getvalue())
        [row] = [r for r in data["vms"] if r["name"] == NAME]
        self.assertTrue(row["adopted"])
        self.assertEqual(row["phase"], "seeded")
        self.assertEqual(data["throwaway"]["alive"], 0, "an adopted machine is not a throwaway VM")
        self.out.truncate(0)
        self.out.seek(0)
        ops.ls(self.ctx)
        line = next(l for l in self.out.getvalue().splitlines() if l.startswith(NAME))
        self.assertIn("adopted", line)
        self.assertIn("seeded", line)
        self.assertNotIn("tailnet only", self.out.getvalue())

    def test_lease_writes_the_host_and_the_record_and_no_label(self):
        self.write_record("booted", ready=NOW - 60, lifetime="keep", expires=None)
        self.remote.m.update(tailnet=True)
        self.assertEqual(ops.lease(self.ctx, NAME, "3h", confirmed=False), 0)
        self.assertEqual(self.remote.m["lease"], NOW + 3 * 3600)
        self.assertEqual(self.remote.targets_of("devcloud lease set"), [NAME])
        self.assertIn(f"--cap {NOW - 600 + 72 * 3600}", self.remote.commands("lease set")[0])
        record = self.record()
        self.assertEqual((record["expires"], record["lifetime"]), (NOW + 3 * 3600, "ttl"))
        self.assertEqual(self.ops(), [], "no provider call, no label")

    def test_ssh_reaches_an_adopted_machine_over_the_tailnet(self):
        self.write_record("booted", ready=NOW - 60)
        self.remote.m.update(tailnet=True)
        ops.ssh(self.ctx, NAME, root=True, command=["true"])
        self.assertEqual(self.remote.calls[-1]["target"], NAME)


class DownTest(AdoptBase):
    def adopted(self):
        self.write_record("booted", ready=NOW - 60)
        self.remote.m.update(keys_saved=True, authorized=True, booted=1, tailnet=True, public=False,
                             descriptor={"name": NAME, "adopted": True})

    def test_down_releases_over_the_tailnet_and_removes_the_record_once_verified(self):
        self.adopted()
        self.assertEqual(ops.down(self.ctx, NAME, force=False), 0)
        self.assertEqual(self.remote.phases["release"], "released")
        [release] = [c for c in self.remote.calls if c["kind"] == "stream"]
        self.assertEqual(release["target"], NAME)
        self.assertEqual(release["command"], "devcloud release --force")
        verify = [c for c in self.remote.calls if "credentials.ledger" in c["command"]]
        self.assertTrue(verify and all(c["person"] and c["user"] == "root" and c["target"] == ADDRESS for c in verify))
        self.assertIsNone(self.record())
        self.assertIn("keeps running", self.out.getvalue())
        self.assertEqual(self.ops(), [], "nothing is deleted at a provider")

    def test_with_the_tailnet_down_it_releases_over_the_recorded_address(self):
        self.adopted()
        self.remote.m.update(tailnet=False, public=True)
        self.assertEqual(ops.down(self.ctx, NAME, force=False), 0)
        [release] = [c for c in self.remote.calls if c["kind"] == "stream"]
        self.assertEqual(release["target"], ADDRESS)

    def test_force_passes_no_hold(self):
        self.adopted()
        self.assertEqual(ops.down(self.ctx, NAME, force=True), 0)
        [release] = [c for c in self.remote.calls if c["kind"] == "stream"]
        self.assertEqual(release["command"], "devcloud release --force --no-hold")

    def test_unpushed_work_is_exit_5(self):
        self.adopted()
        self.remote.m["unpushed"] = True
        with self.assertRaises(DriverError) as caught:
            ops.down(self.ctx, NAME, force=False)
        self.assertEqual(caught.exception.code, 5)
        self.assertEqual(self.record()["phase"], "booted")

    def test_a_held_or_failed_release_keeps_the_record(self):
        for code, needle in ((4, "held"), (1, "again")):
            with self.subTest(code=code):
                self.adopted()
                self.remote.m["release_code"] = code
                with self.assertRaises(DriverError) as caught:
                    ops.down(self.ctx, NAME, force=False)
                self.assertEqual(caught.exception.code, 1)
                self.assertIn(needle, str(caught.exception))
                self.assertEqual(self.record()["phase"], "released")

    def test_a_release_that_cannot_be_verified_keeps_the_record(self):
        self.adopted()
        original = self.remote.answer
        self.remote.answer = lambda command, input: (Result(1, "", "") if "credentials.ledger" in command
                                                     else original(command, input))
        with self.assertRaises(DriverError) as caught:
            ops.down(self.ctx, NAME, force=False)
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("record", str(caught.exception))
        self.assertIsNotNone(self.record())

    def test_a_machine_its_own_lease_released_is_verified_and_its_record_removed(self):
        self.adopted()
        self.remote.m.update(released=True, tailnet=False, public=True, descriptor=None)
        self.assertEqual(ops.down(self.ctx, NAME, force=False), 0)
        self.assertEqual([c for c in self.remote.calls if c["kind"] == "stream"], [])
        self.assertIsNone(self.record())

    def test_a_release_that_failed_after_giving_the_keys_back_resumes_through_the_login(self):
        """The host restored the keys and logged out, then a later step failed:
        the driver's key is gone and the tailnet too, and down again finishes
        the release as the original login user (sudo for one not root)."""
        for login in ("root", "ubuntu"):
            with self.subTest(login=login):
                self.remote = Target(self, login=login)
                self.ctx = self.make_ctx(token_hex=lambda: "7f3a")
                self.write_record("booted", ready=NOW - 60, user=login)
                self.remote.m.update(keys_saved=True, authorized=True, booted=1, tailnet=True, public=False,
                                     descriptor={"name": NAME, "adopted": True}, fail_after_restore=True)
                with self.assertRaises(DriverError) as caught:
                    ops.down(self.ctx, NAME, force=False)
                self.assertIn("again", str(caught.exception))
                self.assertEqual(self.record()["phase"], "released")
                self.remote.calls.clear()
                self.assertEqual(ops.down(self.ctx, NAME, force=False), 0)
                guard = [c for c in self.remote.calls if "devcloud unpushed" in c["command"]]
                [release] = [c for c in self.remote.calls if c["kind"] == "stream"]
                for call in guard + [release]:
                    self.assertEqual((call["target"], call["user"], call["person"]), (ADDRESS, login, True))
                    self.assertEqual(call["command"].startswith("sudo -n "), login != "root")
                self.assertTrue(guard, "the unpushed guard was skipped")
                self.assertIn("devcloud release --force", release["command"])
                self.assertIsNone(self.record())

    def test_an_adoption_interrupted_before_its_boot_is_rolled_back(self):
        """The seed and the ledger delivered, the boot never started: there is
        no descriptor for `devcloud release` to load, so down gives back what
        was delivered itself, and never records `released` before that is
        verified."""
        for phase in ("preparing", "seeded", "booted", "released"):
            with self.subTest(phase=phase):
                self.remote = Target(self)
                self.ctx = self.make_ctx(token_hex=lambda: "7f3a")
                self.write_record(phase)
                self.remote.m.update(keys_saved=True, authorized=True, seeded=1, descriptor=None)
                self.assertEqual(ops.down(self.ctx, NAME, force=True), 0)
                self.assertEqual(self.remote.phases["rollback"], phase, "the phase moved before the rollback")
                self.assertEqual([c for c in self.remote.calls if c["kind"] == "stream"], [], "no release ran")
                self.assertEqual(self.remote.commands("devcloud unpushed"), [], "no session ever ran there")
                self.assertTrue(self.remote.m["released"])
                self.assertIsNone(self.record())
                self.assertIn("rolled back", self.out.getvalue())

    def test_a_rollback_that_fails_keeps_the_record_at_its_phase(self):
        self.write_record("seeded")
        self.remote.m.update(keys_saved=True, authorized=True, seeded=1, descriptor=None, rollback_fails=True)
        with self.assertRaises(DriverError) as caught:
            ops.down(self.ctx, NAME, force=True)
        self.assertIn("only `devcloud release` removes", str(caught.exception))
        self.assertEqual(self.record()["phase"], "seeded")
        self.remote.m["rollback_fails"] = False
        self.assertEqual(ops.down(self.ctx, NAME, force=True), 0, "down again finishes it")
        self.assertIsNone(self.record())

    def test_a_leave_the_release_did_not_confirm_is_named_before_the_record_goes(self):
        self.adopted()
        self.write_record("booted", ready=NOW - 60, enroll="key")
        self.assertEqual(ops.down(self.ctx, NAME, force=False), 0)
        self.assertIsNone(self.record())
        line = next(l for l in self.out.getvalue().splitlines() if "released" in l)
        self.assertIn("may still be in the desk's Machines: remove it by hand if so", line)

    def test_a_confirmed_leave_or_an_unenrolled_machine_needs_no_note(self):
        for enroll, out in (("key", "devcloud release: leave: ok — left the desk\n"),
                            ("key", "devcloud release: leave: ok — left the desk (an earlier run)\n"),
                            (None, "")):
            with self.subTest(enroll=enroll, out=out):
                self.out.truncate(0)
                self.out.seek(0)
                self.adopted()
                self.write_record("booted", ready=NOW - 60, enroll=enroll)
                self.remote.m.update(released=False, release_out=out)
                self.assertEqual(ops.down(self.ctx, NAME, force=False), 0)
                self.assertNotIn("desk", self.out.getvalue())

    def test_unreachable_and_not_released_keeps_the_record(self):
        self.adopted()
        self.remote.m.update(tailnet=False, public=False)
        with self.assertRaises(DriverError):
            ops.down(self.ctx, NAME, force=True)
        self.assertIsNotNone(self.record())


class ReaperTest(AdoptBase):
    def test_the_reaper_never_departs_or_deletes_an_adopted_machine(self):
        self.write_record("booted", ready=NOW - 60, expires=NOW - 30 * 86400)
        self.tailnet_nodes.append({"name": NAME, "online": True, "tags": ["tag:devcloud"]})
        self.remote.m.update(tailnet=True)
        from driver import images
        images.record_build(self.ctx, "main", NOW)
        self.assertEqual(reaper.run(self.ctx), 0)
        self.assertEqual(self.remote.calls, [])
        self.assertEqual(self.record()["phase"], "booted")


class HostScriptTest(AdoptBase):
    """The script streamed to the machine, on a stand-in root."""

    def setUp(self):
        super().setUp()
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-adopt-root-", dir=self.tmp))
        (self.root / "root/.ssh").mkdir(parents=True)
        (self.root / "root/.ssh/authorized_keys").write_text("ssh-ed25519 AAAAperson person@laptop\n")
        (self.root / "home/ubuntu").mkdir(parents=True)

        class Pw:
            def __init__(self, home):
                self.pw_dir = home
        self.passwd = lambda user: Pw({"root": "/root", "ubuntu": "/home/ubuntu"}[user])

    def test_inspect(self):
        (self.root / "etc").mkdir()
        (self.root / "etc/os-release").write_text('NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="24.04"\n')
        self.assertEqual(adopt_host.inspect(self.root), {"id": "ubuntu", "version": "24.04", "descriptor": None})
        (self.root / "etc/devcloud").mkdir()
        (self.root / "etc/devcloud/boot.env").write_text("DEVCLOUD_NAME=dc-x-0001\nDEVCLOUD_ADOPTED=1\n")
        self.assertEqual(adopt_host.inspect(self.root)["descriptor"], {"name": "dc-x-0001", "adopted": True})

    def test_save_keys_once_then_authorize(self):
        adopt_host.save_keys("ubuntu", root=self.root, passwd=self.passwd)
        adopt = self.root / "var/lib/devcloud-adopt"
        manifest = json.loads((adopt / "keys.json").read_text())
        self.assertEqual(manifest, {"keys": [
            {"path": "/root/.ssh/authorized_keys", "owner": "root", "saved": "root.authorized_keys"},
            {"path": "/home/ubuntu/.ssh/authorized_keys", "owner": "ubuntu", "saved": None}]})
        self.assertEqual((adopt / "root.authorized_keys").read_text(), "ssh-ed25519 AAAAperson person@laptop\n")
        self.assertEqual(oct((adopt / "keys.json").stat().st_mode & 0o777), "0o600")
        adopt_host.authorize([KEY], root=self.root, passwd=self.passwd)
        adopt_host.authorize([KEY], root=self.root, passwd=self.passwd)
        self.assertEqual((self.root / "root/.ssh/authorized_keys").read_text(),
                         f"ssh-ed25519 AAAAperson person@laptop\n{KEY}\n")
        self.assertEqual(adopt_host.save_keys("ubuntu", root=self.root, passwd=self.passwd), "already saved")
        self.assertEqual((adopt / "root.authorized_keys").read_text(), "ssh-ed25519 AAAAperson person@laptop\n",
                         "a second run never saves the keys devcloud wrote")

    def preflight(self, user="dev", uid="1001", home="/Users/dev", accounts=()):
        """`accounts`: (name, uid, home) the stand-in machine has."""
        class Pw:
            def __init__(self, name, uid, home):
                self.pw_name, self.pw_uid, self.pw_dir = name, uid, home

        def by(field):
            def look(value):
                for a in accounts:
                    if (a[0] if field == "name" else a[1]) == value:
                        return Pw(*a)
                raise KeyError(value)
            return look
        return adopt_host.preflight(user, uid, home, root=self.root, by_name=by("name"), by_uid=by("uid"))

    def test_preflight_names_each_account_or_home_setup_sh_would_remove_or_take_over(self):
        ubuntu = ("ubuntu", 1001, "/home/ubuntu")
        self.assertEqual(self.preflight(accounts=[ubuntu]), ["uid 1001 belongs to ubuntu (home /home/ubuntu)"])
        self.assertIn("an account named dev already exists", self.preflight(accounts=[("dev", 1001, "/Users/dev")])[0])
        (self.root / "Users/dev").mkdir(parents=True)
        self.assertEqual(self.preflight(), ["/Users/dev already exists"])
        self.assertFalse((self.root / "var/lib/devcloud-adopt").exists(), "a refusal changes nothing")

    def test_preflight_passes_once_and_its_verdict_stays_for_a_resume(self):
        self.assertEqual(self.preflight(), [])
        self.assertTrue((self.root / "var/lib/devcloud-adopt/preflight.json").exists())
        # setup.sh then made the account: a resumed adoption is not refused for it.
        self.assertEqual(self.preflight(accounts=[("dev", 1001, "/Users/dev")]), [])
        self.assertIn("1002", self.preflight(uid="1002")[0], "a profile changed since asks again")
        adopt_host.save_keys("ubuntu", root=self.root, passwd=self.passwd)
        self.assertTrue((self.root / "var/lib/devcloud-adopt/keys.json").exists())

    def rollback_machine(self):
        """An adoption that delivered its seed and stopped before its boot."""
        import os

        class Pw:
            def __init__(self, home):
                self.pw_dir, self.pw_uid, self.pw_gid = home, os.getuid(), os.getgid()
        self.passwd = lambda user: Pw({"root": "/root", "ubuntu": "/home/ubuntu"}[user])
        adopt_host.save_keys("ubuntu", root=self.root, passwd=self.passwd)
        adopt_host.authorize([KEY], root=self.root, passwd=self.passwd)
        (self.root / "home/ubuntu/.ssh").mkdir(parents=True)
        (self.root / "home/ubuntu/.ssh/authorized_keys").write_text(f"{KEY}\n")   # none before adopt
        for path in ("etc/devcloud/seed/seed.json", "var/lib/devcloud-stage/boot.env", "etc/devcloud/image.env",
                     "usr/local/lib/devcloud/devcloud"):
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text("made-up")
        (self.root / "var/lib/devcloud").mkdir(parents=True)
        (self.root / "var/lib/devcloud/credentials.ledger").write_text(
            "/etc/devcloud/seed/seed.json\n/etc/devcloud/boot.env\n")
        units = self.root / "etc/systemd/system"
        units.mkdir(parents=True)
        for name in ("devcloud-boot.service", "devcloud-spot.service", "sshd.service"):
            (units / name).write_text("")
        self.systemctl = []
        return lambda: adopt_host.rollback(root=self.root, passwd=self.passwd,
                                           systemctl=lambda *a: self.systemctl.append(list(a)))

    def test_rollback_gives_back_what_the_adoption_delivered(self):
        rollback = self.rollback_machine()
        rollback()
        for gone in ("etc/devcloud/seed/seed.json", "var/lib/devcloud-stage", "var/lib/devcloud",
                     "var/lib/devcloud-adopt", "etc/systemd/system/devcloud-boot.service",
                     "etc/systemd/system/devcloud-spot.service", "home/ubuntu/.ssh/authorized_keys"):
            self.assertFalse((self.root / gone).exists(), f"{gone} survived the rollback")
        self.assertEqual((self.root / "root/.ssh/authorized_keys").read_text(), "ssh-ed25519 AAAAperson person@laptop\n")
        self.assertTrue((self.root / "etc/systemd/system/sshd.service").exists())
        self.assertTrue((self.root / "usr/local/lib/devcloud/devcloud").exists(), "the tools stay, as a release's do")
        self.assertEqual(self.systemctl, [["disable", "--now", "devcloud-boot.service", "devcloud-spot.service"],
                                          ["daemon-reload"]])
        self.assertIn("nothing saved", rollback(), "run again, it has nothing left to do")

    def test_rollback_removes_a_seed_its_delivery_left_staged(self):
        """deliver_seed writes seed.json.tmp, then renames it: a machine stopped
        in between holds the key there, ledgered or not (an older driver
        ledgered only seed.json)."""
        rollback = self.rollback_machine()
        (self.root / "etc/devcloud/seed/seed.json").rename(self.root / "etc/devcloud/seed/seed.json.tmp")
        rollback()
        self.assertFalse((self.root / "etc/devcloud/seed/seed.json.tmp").exists())

    def test_a_key_restore_that_fails_leaves_the_working_keys_whole(self):
        """Root's authorized_keys is the way in for a root-login adoption: a
        write that fails (ENOSPC) must not leave it empty, and a later run
        restores from the backup still there."""
        import errno
        rollback = self.rollback_machine()
        keys = self.root / "root/.ssh/authorized_keys"
        working = keys.read_text()
        real_write = adopt_host.os.write

        def full(fd, data):
            raise OSError(errno.ENOSPC, "No space left on device")
        adopt_host.os.write = full
        try:
            with self.assertRaises(OSError):
                rollback()
        finally:
            adopt_host.os.write = real_write
        self.assertEqual(keys.read_text(), working)
        self.assertEqual(sorted(p.name for p in keys.parent.iterdir()), ["authorized_keys"], "no staged copy left")
        self.assertTrue((self.root / "var/lib/devcloud-adopt/keys.json").exists(), "the backup stays for a retry")
        rollback()
        self.assertEqual(keys.read_text(), "ssh-ed25519 AAAAperson person@laptop\n")
        self.assertEqual(oct(keys.stat().st_mode & 0o777), "0o600")

    def test_the_release_check_covers_a_staged_seed(self):
        self.assertIn(f"test ! -e {compose.SEED_PATH}.tmp", adopt.RELEASED)

    def test_rollback_never_removes_as_root_what_only_a_release_removes(self):
        rollback = self.rollback_machine()
        (self.root / "home/ubuntu/.pgpass").write_text("made-up")
        with open(self.root / "var/lib/devcloud/credentials.ledger", "a") as f:
            f.write("/home/ubuntu/.pgpass\n")
        with self.assertRaises(adopt_host.Refused) as caught:
            rollback()
        self.assertIn("/home/ubuntu/.pgpass", str(caught.exception))
        self.assertTrue((self.root / "etc/devcloud/seed/seed.json").exists(), "a refusal removes nothing")
        self.assertIn(KEY, (self.root / "root/.ssh/authorized_keys").read_text())

    def test_the_streamed_form(self):
        import subprocess
        import sys
        source = pathlib.Path(adopt_host.__file__).read_bytes()
        done = subprocess.run([sys.executable, "-", "bogus"], input=source, capture_output=True)
        self.assertEqual(done.returncode, 2)
