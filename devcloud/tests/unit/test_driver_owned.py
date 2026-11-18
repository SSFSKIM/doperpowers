"""`devcloud vm owned-by` (contract X9): which VMs name a creator, as an
answer whose "none" can be trusted: every configured account listed in full,
else unknown, naming what could not be asked."""
import json
import shutil

import _path  # noqa: F401
from driver import adopt, cli

from driver_fixtures import NOW, DriverBase, vm_labels

SPARE = """
[[account]]
name = "spare"
provider = "fake"
location = "here"
type = "medium"
env = { FAKE_TOKEN = "fake-token-secret" }
vars = { FAKE_PROVIDER_STATE = "{state}" }
registered = "{registered}"
"""


class OwnedByTest(DriverBase):
    def setUp(self):
        super().setUp()
        # A second account with servers of its own: its own state file, its own passing copy.
        self.spare_state = self.tmp / "spare-state.json"
        self.spare_state.write_text(json.dumps({"servers": [], "images": [], "deleted": [], "calls": [],
                                                "behavior": {}}))
        toml = self.profile_dir / "driver.toml"
        toml.write_text(toml.read_text() + SPARE.replace("{state}", str(self.spare_state))
                        .replace("{registered}", self.sha))
        providers = self.profile_dir / "providers"
        shutil.copy(providers / ".pass" / "main", providers / ".pass" / "spare")
        (providers / "spare.pass.json").write_text((providers / "main.pass.json").read_text())
        self.ctx.reload_profile()

    def add_spare(self, name, labels):
        data = json.loads(self.spare_state.read_text())
        data["servers"].append({"id": str(900 + len(data["servers"])), "name": name, "location": "here",
                                "type": "medium", "labels": labels, "public_ipv4": None, "state": "running",
                                "created": NOW - 60})
        self.spare_state.write_text(json.dumps(data))

    def spare_unusable(self):
        (self.profile_dir / "providers" / "spare.pass.json").unlink()

    def ask(self, *names):
        self.out.truncate(0)
        self.out.seek(0)
        code = cli.main(["owned-by", *names], ctx=self.ctx, host_marker=self.tmp / "no-boot.env")
        return code, (json.loads(self.out.getvalue()) if code == 0 else None)

    def names(self, answer):
        return sorted(vm["name"] for vm in answer["vms"])

    def test_a_match_by_tag_and_by_short_id(self):
        self.add_server("dc-a-0001", vm_labels(**{"devcloud-creator": "abcd1234"}))
        self.add_server("dc-b-0002", vm_labels(**{"devcloud-creator": "0000ffff"}))
        self.add_server("dc-c-0003", vm_labels())
        self.add_spare("dc-d-0004", vm_labels(**{"devcloud-creator": "abcd1234"}))
        for names in (["@abcd1234"], ["abcd1234"], ["@builder#abcd1234"], ["@nobody", "@x#abcd1234"]):
            with self.subTest(names=names):
                code, answer = self.ask(*names)
                self.assertEqual(code, 0)
                self.assertEqual(answer["answer"], "owned")
                self.assertEqual(answer["unknown"], [])
                self.assertEqual(sorted(answer["listed"]), ["main", "spare"])
                self.assertEqual(sorted((vm["name"], vm["account"], vm["provider"], vm["creator"])
                                        for vm in answer["vms"]),
                                 [("dc-a-0001", "main", "fake", "@abcd1234"),
                                  ("dc-d-0004", "spare", "fake", "@abcd1234")])

    def test_a_short_id_matches_whole_never_as_a_prefix(self):
        self.add_server("dc-a-0001", vm_labels(**{"devcloud-creator": "abcd1234"}))
        for names in (["@abcd"], ["abcd12345"], ["@x#abcd"], ["@abcd1234x"]):
            with self.subTest(names=names):
                self.assertEqual(self.ask(*names)[1]["answer"], "none")

    def test_a_complete_none_lists_every_account(self):
        self.add_server("dc-a-0001", vm_labels(**{"devcloud-creator": "0000ffff"}))
        code, answer = self.ask("@abcd1234")
        self.assertEqual(code, 0)
        self.assertEqual(answer, {"answer": "none", "vms": [], "unknown": [], "listed": ["main", "spare"]})

    def test_asking_runs_no_reaper_and_touches_no_host(self):
        self.add_server("dc-old-0001", vm_labels(expires=NOW - 3600, **{"devcloud-creator": "abcd1234"}),
                        state="off")
        code, answer = self.ask("@abcd1234")
        self.assertEqual((code, self.names(answer)), (0, ["dc-old-0001"]))
        self.assertEqual(self.ops(), ["list"])
        self.assertEqual(self.remote.calls, [])

    def test_an_unusable_account_with_no_match_elsewhere_is_unknown(self):
        self.spare_unusable()
        self.add_server("dc-a-0001", vm_labels(**{"devcloud-creator": "0000ffff"}))
        code, answer = self.ask("@abcd1234")
        self.assertEqual(code, 0)
        self.assertEqual(answer["answer"], "unknown")
        self.assertEqual(answer["vms"], [])
        self.assertEqual(answer["listed"], ["main"])
        [missing] = answer["unknown"]
        self.assertEqual((missing["account"], missing["provider"], missing["failed"]), ("spare", "fake", "account"))
        self.assertIn("passing copy", missing["reason"])

    def test_a_provider_whose_listing_fails_is_unknown(self):
        self.behave(fail={"list": 1})
        code, answer = self.ask("@abcd1234")
        self.assertEqual(code, 0)
        self.assertEqual(answer["answer"], "unknown")
        self.assertEqual(answer["listed"], ["spare"])
        [missing] = answer["unknown"]
        self.assertEqual((missing["account"], missing["provider"], missing["failed"]), ("main", "fake", "listing"))
        self.assertIn("list failed", missing["reason"])

    def test_a_secret_that_cannot_be_read_is_unknown_too(self):
        del self.secrets.values["fake-token-secret"]
        code, answer = self.ask("@abcd1234")
        self.assertEqual((code, answer["answer"]), (0, "unknown"))
        self.assertEqual(sorted(m["account"] for m in answer["unknown"]), ["main", "spare"])

    def test_a_match_plus_an_unusable_account_carries_both(self):
        self.spare_unusable()
        self.add_server("dc-a-0001", vm_labels(**{"devcloud-creator": "abcd1234"}))
        code, answer = self.ask("@abcd1234")
        self.assertEqual(code, 0)
        self.assertEqual(answer["answer"], "owned")
        self.assertEqual(self.names(answer), ["dc-a-0001"])
        self.assertEqual([m["account"] for m in answer["unknown"]], ["spare"])

    def test_an_adopted_host_is_owned_by_its_creator(self):
        adopt.save(self.ctx, adopt.Record(name="dc-own-0001", address="192.0.2.7", user="dev", lifetime="keep",
                                          expires=None, projects=[], phase="booted", created=NOW,
                                          creator="abcd1234"))
        code, answer = self.ask("@abcd1234")
        self.assertEqual(answer["answer"], "owned")
        self.assertEqual(answer["vms"], [{"name": "dc-own-0001", "account": "adopted", "provider": None,
                                          "creator": "@abcd1234", "adopted": True}])
        self.assertEqual(self.ask("@0000ffff")[1]["answer"], "none")

    def test_an_adoption_record_that_does_not_read_is_unknown(self):
        self.paths.adopted.mkdir(parents=True)
        (self.paths.adopted / "dc-bad-0001.json").write_text("{not json")
        code, answer = self.ask("@abcd1234")
        self.assertEqual((code, answer["answer"]), (0, "unknown"))
        [missing] = answer["unknown"]
        self.assertEqual((missing["account"], missing["provider"], missing["failed"]), ("adopted", None, "listing"))

    def test_names_that_are_not_tags_or_short_ids_are_usage(self):
        for names in ([], ["abcd 1234"], ["@"], ["ABCD1234"], ["@x#notahex"], ["--json"]):
            with self.subTest(names=names):
                self.assertEqual(self.ask(*names)[0], 2)
        self.assertEqual(self.state()["calls"], [])

    def test_on_a_host_it_is_6_and_asks_nothing(self):
        marker = self.tmp / "boot.env"
        marker.write_text("DEVCLOUD_NAME=x\n")
        self.assertEqual(cli.main(["owned-by", "@abcd1234"], ctx=self.ctx, host_marker=marker), 6)
        self.assertEqual(self.out.getvalue(), "")
        self.assertEqual(self.state()["calls"], [])
