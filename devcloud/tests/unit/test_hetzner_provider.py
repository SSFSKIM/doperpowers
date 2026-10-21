"""The shipped Hetzner provider (the driver's Design §6.3, I13): the real script run as a
subprocess against the stand-in `hcloud` in tests/fixtures, whose state is a JSON file."""

import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve()
PROVIDER = HERE.parents[2] / "driver" / "providers" / "hetzner"
FAKE_HCLOUD = HERE.parents[1] / "fixtures" / "hcloud"
TOKEN = "hc-tok-7d1e9a5b3c2f4e6a8b0c1d2e3f4a5b6c"


def epoch(text):
    return int(datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())


def server(sid, name, labels, *, location="hil", stype="cpx31", ipv4="203.0.113.9",
           status="running", created="2026-10-21T04:20:02Z"):
    return {"id": sid, "name": name, "status": status, "created": created, "labels": labels,
            "server_type": {"id": 24, "name": stype},
            "location": {"id": 5, "name": location, "network_zone": "us-west"},
            "public_net": {"ipv4": {"ip": ipv4} if ipv4 else None, "ipv6": None}}


SERVER_TYPES = [
    {"id": 24, "name": "cpx31", "cores": 4, "memory": 8.0, "disk": 160, "deprecated": False,
     "locations": [{"name": "hil", "available": True, "deprecation": None},
                   {"name": "nbg1", "available": False, "deprecation": {"announced": "2026-01-01"}}],
     "prices": [{"location": "hil", "price_hourly": {"net": "0.1178000000", "gross": "0.1178000000000000"}},
                {"location": "nbg1", "price_hourly": {"net": "0.0201", "gross": "0.0239190000000000"}}]},
    {"id": 104, "name": "cx22", "cores": 2, "memory": 4.0, "disk": 40, "deprecated": False,
     "locations": [{"name": "nbg1", "available": True, "deprecation": None},
                   {"name": "fsn1", "available": True, "deprecation": None}],
     "prices": [{"location": "nbg1", "price_hourly": {"net": "0.006", "gross": "0.0071400000000000"}}]},
    {"id": 22, "name": "cpx11", "cores": 2, "memory": 2.0, "disk": 40, "deprecated": True,
     "locations": [{"name": "hil", "available": True, "deprecation": None}],
     "prices": []},
]
KNOWN_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKnownKnownKnownKnownKnownKnownKnownKnow"
NEW_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINewNewNewNewNewNewNewNewNewNewNewNewNewN"


class HetznerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-hetzner-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "hcloud").symlink_to(FAKE_HCLOUD)
        self.state_path = self.tmp / "hcloud-state.json"
        self.write_state({
            "servers": [server(42, "dc-a", {"devcloud": "vm", "devcloud-lifetime": "ttl"}),
                        server(43, "personal", {"owner": "me"}),
                        server(44, "dc-b", {"devcloud": "builder"}, ipv4=None, status="off",
                               location="nbg1", stype="cx22", created="2026-10-20T10:00:00+00:00")],
            "images": [{"id": 900, "type": "snapshot", "status": "available", "name": None,
                        "description": "personal-snap", "created": "2026-10-01T00:00:00Z", "labels": {}},
                       {"id": 901, "type": "system", "status": "available", "name": "ubuntu-24.04",
                        "description": "Ubuntu 24.04", "created": "2024-04-25T00:00:00Z",
                        "labels": {"devcloud": "image"}}],
            "ssh_keys": [{"id": 501, "name": "laptop", "public_key": KNOWN_KEY + " me@laptop", "labels": {}}],
            "server_types": SERVER_TYPES,
            "next_id": 1000,
            "calls": [],
            "fail": {},
        })

    def write_state(self, state):
        self.state_path.write_text(json.dumps(state))

    def state(self):
        return json.loads(self.state_path.read_text())

    def fail(self, command, stderr, code=1):
        state = self.state()
        state["fail"][command] = {"code": code, "stderr": stderr}
        self.write_state(state)

    def run_op(self, op, payload=None, *, stdin=None, token=TOKEN, argv=None):
        env = dict(os.environ)
        env.update(PATH=f"{self.bin}{os.pathsep}{env.get('PATH', '')}",
                   FAKE_HCLOUD_STATE=str(self.state_path), HCLOUD_CONTEXT="personal")
        env.pop("HCLOUD_TOKEN", None)
        if token is not None:
            env["HCLOUD_TOKEN"] = token
        r = subprocess.run([str(PROVIDER), *([op] if argv is None else argv)],
                           input=stdin if stdin is not None else json.dumps(payload or {}),
                           env=env, capture_output=True, text=True, timeout=60)
        self.assertNotIn(TOKEN, r.stdout + r.stderr, "the token was printed")
        return r

    def ok(self, op, payload=None):
        r = self.run_op(op, payload)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def refused(self, op, payload, kind):
        r = self.run_op(op, payload)
        self.assertEqual(r.returncode, 3, r.stderr)
        answer = json.loads(r.stdout)
        self.assertEqual(answer["kind"], kind)
        self.assertIsInstance(answer["error"], str)
        self.assertNotIn("\n", answer["error"])
        return answer

    def calls(self):
        return [c[2:] for c in self.state()["calls"]]

    def calls_of(self, *words):
        return [c for c in self.calls() if c[:len(words)] == list(words)]


def create_payload(**over):
    payload = {"name": "dc-new", "type": "cpx31", "location": "hil", "image": None,
               "labels": {"devcloud": "vm", "devcloud-lifetime": "ttl", "devcloud-expires": "1792000000",
                          "devcloud-by": "macbook"},
               "ssh_public_keys": [KNOWN_KEY + " driver@macbook"], "user_data": "#cloud-config\nruncmd: [true]\n",
               "disk_gb": None, "spot": False}
    payload.update(over)
    return payload


class InfoAndTypesTest(HetznerBase):
    def test_info_names_the_protocol_and_capabilities(self):
        self.assertEqual(self.ok("info"), {"protocol": 1, "capabilities": ["user_data", "images"]})

    def test_types_for_a_location(self):
        self.assertEqual(self.ok("types", {"location": "hil"}), [
            {"type": "cpx31", "vcpus": 4, "memory_gb": 8.0, "disk_gb": 160, "available": True,
             "hourly_price": 0.1178, "currency": "EUR"},
            {"type": "cpx11", "vcpus": 2, "memory_gb": 2.0, "disk_gb": 40, "available": False,
             "hourly_price": None, "currency": "EUR"},
        ])

    def test_types_unavailable_at_the_location_and_omitted_where_absent(self):
        types = {t["type"]: t for t in self.ok("types", {"location": "nbg1"})}
        self.assertEqual(sorted(types), ["cpx31", "cx22"])
        self.assertFalse(types["cpx31"]["available"])
        self.assertTrue(types["cx22"]["available"])
        self.assertEqual(types["cx22"]["hourly_price"], 0.00714)

    def test_every_call_uses_a_private_config_and_never_the_token_on_argv(self):
        self.ok("types", {"location": "hil"})
        self.ok("create", create_payload(ssh_public_keys=[NEW_KEY]))
        self.ok("list")
        raw = self.state()["calls"]
        self.assertGreater(len(raw), 3)
        for call in raw:
            self.assertEqual(call[0], "--config", call)
            self.assertFalse(pathlib.Path(call[1]).parent.exists(), "the private config dir was left behind")
            self.assertFalse(any(TOKEN in arg for arg in call), call)


class CreateTest(HetznerBase):
    def test_create_puts_every_label_in_the_one_create_call(self):
        vm = self.ok("create", create_payload())
        creates = self.calls_of("server", "create")
        self.assertEqual(len(creates), 1)
        argv = creates[0]
        labels = [argv[i + 1] for i, a in enumerate(argv) if a == "--label"]
        self.assertEqual(sorted(labels), sorted(f"{k}={v}" for k, v in create_payload()["labels"].items()))
        self.assertEqual(self.calls_of("server", "add-label"), [])
        self.assertEqual(vm["labels"], create_payload()["labels"])
        self.assertEqual(vm["id"], "1000")
        self.assertEqual((vm["name"], vm["location"], vm["type"], vm["state"]), ("dc-new", "hil", "cpx31", "running"))
        self.assertEqual(vm["public_ipv4"], "203.0.113.232")
        self.assertEqual(vm["created"], epoch("2026-10-21T05:00:00+00:00"))

    def test_user_data_reaches_the_server_and_the_default_image_is_ubuntu(self):
        self.ok("create", create_payload())
        made = [s for s in self.state()["servers"] if s["name"] == "dc-new"][0]
        self.assertEqual(made["_user_data"], create_payload()["user_data"])
        self.assertEqual(made["image"]["name"], "ubuntu-24.04")

    def test_a_given_image_is_used_and_no_user_data_means_no_file(self):
        self.ok("create", create_payload(image="901", user_data=None))
        argv = self.calls_of("server", "create")[0]
        self.assertEqual(argv[argv.index("--image") + 1], "901")
        self.assertNotIn("--user-data-from-file", argv)

    def test_a_known_key_is_reused_by_its_body(self):
        self.ok("create", create_payload())
        self.assertEqual(self.calls_of("ssh-key", "create"), [])
        made = [s for s in self.state()["servers"] if s["name"] == "dc-new"][0]
        self.assertEqual(made["_ssh_keys"], [501])

    def test_an_unknown_key_is_registered_with_the_devcloud_label(self):
        self.ok("create", create_payload(ssh_public_keys=[NEW_KEY + " driver@macbook", KNOWN_KEY]))
        [argv] = self.calls_of("ssh-key", "create")
        body = " ".join(NEW_KEY.split()[:2])
        self.assertEqual(argv[argv.index("--name") + 1], "devcloud-" + hashlib.sha256(body.encode()).hexdigest()[:12])
        self.assertEqual(argv[argv.index("--label") + 1], "devcloud=sshkey")
        new_id = [k["id"] for k in self.state()["ssh_keys"] if k["name"].startswith("devcloud-")][0]
        made = [s for s in self.state()["servers"] if s["name"] == "dc-new"][0]
        self.assertEqual(made["_ssh_keys"], [new_id, 501])

    def test_the_root_password_is_never_printed(self):
        r = self.run_op("create", create_payload())
        self.assertNotIn("fake-root-password", r.stdout + r.stderr)

    def test_spot_is_refused(self):
        self.refused("create", create_payload(spot=True), "unavailable")
        self.assertEqual(self.calls_of("server", "create"), [])

    def test_a_disk_beyond_the_types_own_is_refused(self):
        answer = self.refused("create", create_payload(disk_gb=200), "unavailable")
        self.assertIn("160", answer["error"])
        self.assertEqual(self.calls_of("server", "create"), [])

    def test_a_disk_within_the_types_own_is_created(self):
        self.ok("create", create_payload(disk_gb=160))

    def test_the_projects_limit_is_refused_with_kind_limit(self):
        self.fail("server create", "hcloud: Server limit exceeded (resource_limit_exceeded, 0f3a)")
        self.assertIn("limit exceeded", self.refused("create", create_payload(), "limit")["error"])

    def test_an_unavailable_type_or_location_is_refused_with_kind_unavailable(self):
        for code in ("resource_unavailable", "server_type_unavailable", "location_unavailable",
                     "unsupported_location_for_server_type", "placement_error"):
            with self.subTest(code=code):
                self.fail("server create", f"hcloud: cannot create server ({code}, 77aa)")
                self.refused("create", create_payload(), "unavailable")

    def test_another_hcloud_failure_is_exit_1_with_its_last_line(self):
        self.fail("server create", "progress\nhcloud: something broke (service_error, 1b2c)")
        r = self.run_op("create", create_payload())
        self.assertEqual(r.returncode, 1)
        self.assertIn("something broke (service_error, 1b2c)", r.stderr)
        self.assertNotIn("progress", r.stderr)


class ServersTest(HetznerBase):
    def test_list_returns_only_labeled_servers(self):
        vms = self.ok("list")
        self.assertEqual(vms, [
            {"id": "42", "name": "dc-a", "location": "hil", "type": "cpx31",
             "labels": {"devcloud": "vm", "devcloud-lifetime": "ttl"}, "public_ipv4": "203.0.113.9",
             "state": "running", "created": epoch("2026-10-21T04:20:02+00:00")},
            {"id": "44", "name": "dc-b", "location": "nbg1", "type": "cx22", "labels": {"devcloud": "builder"},
             "public_ipv4": None, "state": "off", "created": epoch("2026-10-20T10:00:00+00:00")},
        ])
        argv = self.calls_of("server", "list")[0]
        self.assertEqual(argv[argv.index("-l") + 1], "devcloud")

    def test_get_returns_the_vm_or_null(self):
        self.assertEqual(self.ok("get", {"id": "42"})["name"], "dc-a")
        self.assertIsNone(self.ok("get", {"id": "999999"}))

    def test_get_fails_on_another_error(self):
        self.fail("server describe", "hcloud: Unauthorized (unauthorized, 11)")
        r = self.run_op("get", {"id": "42"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("unauthorized", r.stderr)

    def test_set_labels_removes_absent_keys_and_overwrites_the_rest(self):
        vm = self.ok("set-labels", {"id": "42", "labels": {"devcloud": "vm", "devcloud-held": "1"}})
        self.assertEqual(vm["labels"], {"devcloud": "vm", "devcloud-held": "1"})
        self.assertEqual(self.calls_of("server", "remove-label"), [["server", "remove-label", "42", "devcloud-lifetime"]])
        [add] = self.calls_of("server", "add-label")
        self.assertIn("--overwrite", add)
        self.assertEqual(sorted(a for a in add if "=" in a), ["devcloud-held=1", "devcloud=vm"])

    def test_set_labels_without_removals_makes_no_remove_call(self):
        self.ok("set-labels", {"id": "42", "labels": {"devcloud": "vm", "devcloud-lifetime": "keep"}})
        self.assertEqual(self.calls_of("server", "remove-label"), [])
        self.assertEqual(self.ok("get", {"id": "42"})["labels"], {"devcloud": "vm", "devcloud-lifetime": "keep"})

    def test_delete_is_idempotent(self):
        self.assertEqual(self.ok("delete", {"id": "42"}), {})
        self.assertIsNone(self.ok("get", {"id": "42"}))
        self.assertEqual(self.ok("delete", {"id": "42"}), {})

    def test_delete_fails_on_another_error(self):
        self.fail("server delete", "hcloud: server is locked (locked, 3)")
        self.assertEqual(self.run_op("delete", {"id": "42"}).returncode, 1)


class ImagesTest(HetznerBase):
    def test_image_round_trip(self):
        labels = {"devcloud": "image", "devcloud-recipe": "0123456789ab"}
        image = self.ok("image-create", {"id": "42", "name": "devcloud-0123456789ab", "labels": labels})
        self.assertEqual(image, {"id": "1000", "name": "devcloud-0123456789ab", "labels": labels,
                                 "created": epoch("2026-10-21T05:00:00+00:00")})
        [argv] = self.calls_of("server", "create-image")
        self.assertEqual(argv[argv.index("--type") + 1], "snapshot")
        self.assertEqual(self.ok("images"), [image])
        self.assertEqual(self.ok("image-delete", {"id": "1000"}), {})
        self.assertEqual(self.ok("images"), [])
        self.assertEqual(self.ok("image-delete", {"id": "1000"}), {})


    def test_a_snapshot_still_being_made_is_not_listed(self):
        image = self.ok("image-create", {"id": "42", "name": "devcloud-0123456789ab", "labels": {"devcloud": "image"}})
        state = self.state()
        state["images"][-1]["status"] = "creating"
        self.state_path.write_text(json.dumps(state))
        self.assertEqual(self.ok("images"), [])
        state["images"][-1]["status"] = "available"
        self.state_path.write_text(json.dumps(state))
        self.assertEqual(self.ok("images"), [image])


class UsageTest(HetznerBase):
    def test_unknown_or_missing_op_and_bad_stdin_are_usage(self):
        for argv, stdin in ((["frobnicate"], "{}"), ([], "{}"), (["list"], "[1]"), (["list"], "not json")):
            with self.subTest(argv=argv, stdin=stdin):
                r = self.run_op(None, argv=argv, stdin=stdin)
                self.assertEqual(r.returncode, 2)
                self.assertTrue(r.stderr.strip())
        self.assertEqual(self.calls(), [])

    def test_a_missing_token_fails(self):
        r = self.run_op("list", token=None)
        self.assertEqual(r.returncode, 1)
        self.assertIn("HCLOUD_TOKEN", r.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
