"""`devcloud vm info` (EN.G2's plan, Interfaces §2): what each named host is,
for a program that words it itself (sminos's `channel show`). The reply's
shape, pinned for its reader; a VM, an adopted machine, a host with no price,
a handed-on host; names compared without regard to case, two hosts of one
name both reported; a read that asks no host, runs no reaper and writes
nothing; and the providers' budget, each account's fate recorded as it is
walked: listed, failed at once, stalled, never started."""
import json
import shutil
import time

import _path  # noqa: F401
from driver import adopt, cli, ops

from driver_fixtures import NOW, DriverBase, vm_labels

ACCOUNT = """
[[account]]
name = "{name}"
provider = "fake"
location = "here"
type = "medium"
env = {{ FAKE_TOKEN = "fake-token-secret" }}
vars = {{ FAKE_PROVIDER_STATE = "{state}" }}
registered = "{registered}"
"""

# The reply as sminos reads it (sminos_threads.info_reply, Interfaces §3): these keys, and no host without them.
REPLY_KEYS = {"hosts", "unknown", "listed", "unused"}
PROVIDER_HOST_KEYS = {"name", "account", "provider", "creator", "created", "spent", "currency"}
ADOPTED_HOST_KEYS = PROVIDER_HOST_KEYS | {"adopted"}
UNKNOWN_KEYS = {"account", "provider", "failed", "reason"}


class InfoTest(DriverBase):
    def add_account(self, name):
        """Another account on the stand-in provider, with its own state file and passing copy: the state file."""
        state = self.tmp / f"{name}-state.json"
        state.write_text(json.dumps({"servers": [], "images": [], "deleted": [], "calls": [], "behavior": {}}))
        toml = self.profile_dir / "driver.toml"
        toml.write_text(toml.read_text() + ACCOUNT.format(name=name, state=state, registered=self.sha))
        providers = self.profile_dir / "providers"
        shutil.copy(providers / ".pass" / "main", providers / ".pass" / name)
        (providers / f"{name}.pass.json").write_text((providers / "main.pass.json").read_text())
        self.ctx.reload_profile()
        return state

    def add_to(self, state, name, labels, created=NOW - 60):
        data = json.loads(state.read_text())
        data["servers"].append({"id": str(900 + len(data["servers"])), "name": name, "location": "here",
                                "type": "medium", "labels": labels, "public_ipv4": None, "state": "running",
                                "created": created})
        state.write_text(json.dumps(data))

    def behave_in(self, state, **behavior):
        data = json.loads(state.read_text())
        data["behavior"].update(behavior)
        state.write_text(json.dumps(data))

    def ask(self, *argv):
        self.out.truncate(0)
        self.out.seek(0)
        code = cli.main(["info", *argv], ctx=self.ctx, host_marker=self.tmp / "no-boot.env")
        return code, (json.loads(self.out.getvalue()) if code == 0 else None)

    def test_the_reply_sminos_reads_a_vm_s_owner_age_and_cost(self):
        self.add_server("dc-x-0001", vm_labels(**{"devcloud-creator": "1a2b3c4d"}), created=NOW - 7200)
        self.add_server("dc-x-0002", vm_labels(**{"devcloud-creator": "0000ffff"}))
        code, answer = self.ask("dc-x-0001")
        self.assertEqual(code, 0)
        self.assertEqual(set(answer), REPLY_KEYS)
        [host] = answer["hosts"]
        self.assertEqual(set(host), PROVIDER_HOST_KEYS, "a provider's host carries no `adopted`")
        self.assertEqual({k: host[k] for k in ("name", "account", "provider", "creator", "created", "currency")},
                         {"name": "dc-x-0001", "account": "main", "provider": "fake", "creator": "@1a2b3c4d",
                          "created": NOW - 7200, "currency": "EUR"})
        self.assertAlmostEqual(host["spent"], 0.1178 * 2, places=9, msg="the type's list price times its age")
        self.assertEqual(host["spent"], ops.spent({"hourly_price": 0.1178}, NOW - 7200, NOW), "vm ls's own rule")
        self.assertEqual((answer["unknown"], answer["listed"], answer["unused"]), ([], ["main"], []))

    def test_it_asks_no_host_runs_no_reaper_and_writes_nothing(self):
        self.add_server("dc-old-0001", vm_labels(expires=NOW - 3600, **{"devcloud-creator": "1a2b3c4d"}),
                        state="off")
        code, answer = self.ask("dc-old-0001")
        self.assertEqual((code, [h["name"] for h in answer["hosts"]]), (0, ["dc-old-0001"]))
        self.assertEqual(self.ops(), ["list", "types"], "one listing and one type list; no reaper's delete")
        self.assertEqual(self.remote.calls, [], "no host asked")
        self.assertFalse(self.state_dir.exists(), "nothing written under the driver's state")
        self.assertIn("dc-old-0001", self.servers(), "what outlived its lease is still there")

    def test_a_handed_on_host_names_the_label_s_thread(self):
        self.add_server("dc-x-0001", vm_labels(**{"devcloud-creator": "5e6f7a8b"}))   # after `vm owner`
        self.add_server("dc-x-0002", vm_labels())                                       # a host that names no one
        _, answer = self.ask("dc-x-0001", "dc-x-0002")
        self.assertEqual({h["name"]: h["creator"] for h in answer["hosts"]},
                         {"dc-x-0001": "@5e6f7a8b", "dc-x-0002": None})

    def test_an_adopted_machine_has_no_age_and_no_cost(self):
        adopt.save(self.ctx, adopt.Record(name="box-1", address="192.0.2.7", user="dev", lifetime="keep",
                                          expires=None, projects=[], phase="booted", created=NOW,
                                          creator="5e6f7a8b"))
        adopt.save(self.ctx, adopt.Record(name="box-2", address="192.0.2.8", user="dev", lifetime="keep",
                                          expires=None, projects=[], phase="booted", created=NOW))
        _, answer = self.ask("box-1", "box-2", "box-3")
        self.assertEqual(answer["hosts"], [
            {"name": "box-1", "account": "adopted", "provider": None, "adopted": True, "creator": "@5e6f7a8b",
             "created": None, "spent": None, "currency": None},
            {"name": "box-2", "account": "adopted", "provider": None, "adopted": True, "creator": None,
             "created": None, "spent": None, "currency": None}])
        self.assertEqual(set(answer["hosts"][0]), ADOPTED_HOST_KEYS)

    def test_a_type_with_no_price_or_none_listed_has_no_cost(self):
        self.add_server("dc-x-0001", vm_labels())
        data = self.state()
        data["servers"][0]["type"] = "custom"           # a type the list does not hold
        data["types"] = {"here": [{"type": "medium", "vcpus": 4, "memory_gb": 8, "disk_gb": 160, "available": True}]}
        self.state_file.write_text(json.dumps(data))
        self.add_server("dc-x-0002", vm_labels())       # medium, listed with no price
        self.add_server("dc-x-0003", vm_labels())
        data = self.state()
        data["types"]["here"].append({"type": "odd", "hourly_price": float("nan"), "currency": "EUR"})
        data["servers"][2]["type"] = "odd"              # a price that is no finite number
        self.state_file.write_text(json.dumps(data))
        _, answer = self.ask("dc-x-0001", "dc-x-0002", "dc-x-0003")
        self.assertEqual([(h["name"], h["created"], h["spent"], h["currency"]) for h in answer["hosts"]],
                         [("dc-x-0001", NOW - 3600, None, None), ("dc-x-0002", NOW - 3600, None, None),
                          ("dc-x-0003", NOW - 3600, None, None)])
        self.assertNotIn("NaN", self.out.getvalue())

    def test_a_cost_that_cannot_be_represented_is_none_and_the_other_hosts_keep_theirs(self):
        data = self.state()
        data["types"] = {"here": [
            {"type": "medium", "hourly_price": 0.1178, "currency": "EUR"},
            {"type": "huge", "hourly_price": 10 ** 400, "currency": "EUR"},     # past a float's range
            {"type": "dear", "hourly_price": 1e308, "currency": "EUR"},         # finite, its amount is not
        ]}
        self.state_file.write_text(json.dumps(data))
        for name, type_ in (("dc-x-0001", "medium"), ("dc-x-0002", "huge"), ("dc-x-0003", "dear")):
            self.add_server(name, vm_labels(), created=NOW - 7200)
            data = self.state()
            data["servers"][-1]["type"] = type_
            self.state_file.write_text(json.dumps(data))
        code, answer = self.ask("dc-x-0001", "dc-x-0002", "dc-x-0003")
        self.assertEqual(code, 0)
        self.assertEqual([(h["name"], h["spent"] is not None, h["currency"]) for h in answer["hosts"]],
                         [("dc-x-0001", True, "EUR"), ("dc-x-0002", False, None), ("dc-x-0003", False, None)])
        self.assertAlmostEqual(answer["hosts"][0]["spent"], 0.1178 * 2, places=9)
        self.assertNotIn("Infinity", self.out.getvalue())
        json.loads(self.out.getvalue(), parse_constant=lambda name: self.fail(name))

    def test_a_type_list_that_fails_leaves_the_host_with_no_cost(self):
        self.add_server("dc-x-0001", vm_labels(**{"devcloud-creator": "1a2b3c4d"}))
        self.behave(fail={"types": 1})
        code, answer = self.ask("dc-x-0001")
        self.assertEqual(code, 0)
        [host] = answer["hosts"]
        self.assertEqual((host["created"], host["spent"], host["currency"]), (NOW - 3600, None, None))
        self.assertEqual(answer["unknown"], [], "the host was listed: its cost alone is missing")

    def test_a_type_list_that_stalls_leaves_the_host_with_no_cost_within_the_budget(self):
        self.add_server("dc-x-0001", vm_labels(**{"devcloud-creator": "1a2b3c4d"}))
        self.behave(gate={"types": str(self.tmp / "never")})
        began = time.monotonic()
        code, answer = self.ask("--within", "1.5", "dc-x-0001")
        took = time.monotonic() - began
        self.assertEqual(code, 0)
        [host] = answer["hosts"]
        self.assertEqual((host["name"], host["spent"], host["currency"]), ("dc-x-0001", None, None))
        self.assertLess(took, 1.5 + 5, "within the budget and the caller's margin")

    def test_a_name_of_another_case_finds_its_host_and_two_hosts_of_one_name_are_both_reported(self):
        spare = self.add_account("spare")
        self.add_server("dc-x-0001", vm_labels(**{"devcloud-creator": "1a2b3c4d"}))
        self.add_to(spare, "DC-X-0001", vm_labels(**{"devcloud-creator": "5e6f7a8b"}))
        adopt.save(self.ctx, adopt.Record(name="Box-1", address="192.0.2.7", user="dev", lifetime="keep",
                                          expires=None, projects=[], phase="booted", created=NOW))
        _, answer = self.ask("Dc-X-0001", "BOX-1")
        self.assertEqual(sorted((h["name"], h["account"]) for h in answer["hosts"]),
                         [("Box-1", "adopted"), ("DC-X-0001", "spare"), ("dc-x-0001", "main")])

    def test_a_name_no_host_has_is_absent(self):
        self.add_server("dc-x-0001", vm_labels())
        code, answer = self.ask("dc-x-9999")
        self.assertEqual((code, answer), (0, {"hosts": [], "unknown": [], "listed": ["main"], "unused": []}))

    def test_an_account_that_could_not_be_listed_holds_no_host_with_invented_facts(self):
        spare = self.add_account("spare")
        self.add_to(spare, "dc-x-0001", vm_labels(**{"devcloud-creator": "1a2b3c4d"}))
        self.behave_in(spare, fail={"list": 1})
        code, answer = self.ask("dc-x-0001")
        self.assertEqual((code, answer["hosts"], answer["listed"]), (0, [], ["main"]))
        [missing] = answer["unknown"]
        self.assertEqual(set(missing), UNKNOWN_KEYS)
        self.assertEqual((missing["account"], missing["provider"], missing["failed"]), ("spare", "fake", "listing"))

    def test_an_unusable_account_is_unknown_and_one_never_used_here_is_unused(self):
        self.add_account("spare")
        # An account another profile used: its provider passed there (that profile made dc-x-0001 in it), and
        # never under this one, which holds no pass artifact of it.
        never = self.add_account("never")
        self.add_to(never, "dc-x-0001", vm_labels(**{"devcloud-creator": "1a2b3c4d"}))
        providers = self.profile_dir / "providers"
        (providers / "spare.pass.json").unlink()                 # a copy without its record: a sign of a pass
        (providers / ".pass" / "never").unlink()                  # no sign of any pass under this profile
        (providers / "never.pass.json").unlink()
        code, answer = self.ask("dc-x-0001")
        self.assertEqual(code, 0)
        self.assertEqual(answer["hosts"], [], "the other profile's VM is not seen from here")
        self.assertEqual([(m["account"], m["failed"]) for m in answer["unknown"]], [("spare", "account")])
        self.assertEqual((answer["listed"], answer["unused"]), (["main"], ["never"]))
        self.assertEqual(json.loads(never.read_text())["calls"], [], "nothing asked of it")
        self.assertIn("never", self.err.getvalue())

    def test_an_adoption_record_that_does_not_read_is_unknown(self):
        self.paths.adopted.mkdir(parents=True)
        (self.paths.adopted / "box-bad.json").write_text("{not json")
        code, answer = self.ask("box-bad")
        self.assertEqual((code, answer["hosts"]), (0, []))
        self.assertEqual([(m["account"], m["provider"], m["failed"]) for m in answer["unknown"]],
                         [("adopted", None, "listing")])

    def test_four_accounts_listed_failed_stalled_and_never_started_within_the_budget(self):
        failing, stalled, last = self.add_account("b-fails"), self.add_account("c-stalls"), self.add_account("d-last")
        self.add_server("dc-x-0001", vm_labels(**{"devcloud-creator": "1a2b3c4d"}))
        self.add_to(failing, "dc-x-0002", vm_labels())
        self.add_to(stalled, "dc-x-0003", vm_labels())
        self.add_to(last, "dc-x-0004", vm_labels())
        self.behave_in(failing, fail={"list": 1})
        self.behave_in(stalled, gate={"list": str(self.tmp / "never")})
        began = time.monotonic()
        code, answer = self.ask("--within", "2", "dc-x-0001", "dc-x-0002", "dc-x-0003", "dc-x-0004")
        took = time.monotonic() - began
        self.assertEqual(code, 0)
        self.assertEqual([h["name"] for h in answer["hosts"]], ["dc-x-0001"], "the first's hosts, read before")
        self.assertEqual([(m["account"], m["failed"]) for m in answer["unknown"]],
                         [("b-fails", "listing"), ("c-stalls", "time"), ("d-last", "time")])
        self.assertEqual(answer["listed"], ["main"])
        self.assertGreaterEqual(took, 2 - 0.1, "the stalled account took what was left")
        self.assertLess(took, 2 + 5, "and the reply came within the budget and the margin")
        self.assertEqual([c["op"] for c in json.loads(last.read_text())["calls"]], [], "the fourth never started")

    def test_usage(self):
        for argv in ([], ["--within", "0", "x"], ["--within", "-1", "x"], ["--within", "soon", "x"],
                     ["--within", "nan", "x"], ["--within", "inf", "x"], ["--within", "5"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.ask(*argv)[0], 2)
        self.assertEqual(self.state()["calls"], [])

    def test_names_after_a_double_dash_are_names(self):
        self.add_server("-odd", vm_labels())
        code, answer = self.ask("--within", "3", "--", "-odd")
        self.assertEqual((code, [h["name"] for h in answer["hosts"]]), (0, ["-odd"]))

    def test_on_a_host_it_is_6_and_asks_nothing(self):
        marker = self.tmp / "boot.env"
        marker.write_text("DEVCLOUD_NAME=x\n")
        self.assertEqual(cli.main(["info", "x"], ctx=self.ctx, host_marker=marker), 6)
        self.assertEqual(self.out.getvalue(), "")
        self.assertEqual(self.state()["calls"], [])
