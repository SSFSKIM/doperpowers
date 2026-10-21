"""The shipped GCE provider (the driver's Design §6.4, I13): the real script run as a subprocess
against the stand-in `gcloud` in tests/fixtures, whose state is a JSON file."""

import datetime
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve()
PROVIDER = HERE.parents[2] / "driver" / "providers" / "gce"
FAKE_GCLOUD = HERE.parents[1] / "fixtures" / "gcloud"
SA = "host@example-project.iam.gserviceaccount.com"
SEED_EMAIL = "driver@example-project.iam.gserviceaccount.com"
ZONE = "us-west1-b"
URL = f"https://www.googleapis.com/compute/v1/projects/example-project/zones/{ZONE}"


def epoch(text):
    return int(datetime.datetime.fromisoformat(text).timestamp())


def mtype(name, cpus, mb, shared=False, accelerators=None, deprecated=None):
    t = {"name": name, "guestCpus": cpus, "memoryMb": mb, "isSharedCpu": shared, "zone": ZONE}
    if accelerators:
        t["accelerators"] = accelerators
    if deprecated:
        t["deprecated"] = {"state": "DEPRECATED"}
    return t


MACHINE_TYPES = {ZONE: [
    mtype("e2-standard-4", 4, 16384), mtype("e2-highcpu-2", 2, 2048), mtype("e2-micro", 2, 1024, shared=True),
    mtype("f1-micro", 1, 614, shared=True), mtype("g2-standard-4", 4, 16384, accelerators=[{"guestAcceleratorCount": 1}]),
    mtype("n1-standard-2", 2, 7680, deprecated=True), mtype("n4a-highcpu-2", 2, 4096), mtype("n1-standard-1", 1, 3840),
    mtype("n1-highcpu-2", 2, 1843)]}


def instance(iid, name, labels, status="RUNNING", zone=ZONE, mt="e2-standard-4", ip="198.51.100.7"):
    url = URL.replace(ZONE, zone)
    return {"id": str(iid), "name": name, "zone": url, "machineType": f"{url}/machineTypes/{mt}",
            "status": status, "creationTimestamp": "2026-10-21T04:20:02.123-07:00", "labels": labels,
            "networkInterfaces": [{"accessConfigs": [{"natIP": ip}] if ip else []}],
            "disks": [{"boot": True, "source": f"{url}/disks/{name}"}], "metadata": {"items": []}}


def load_module():
    loader = importlib.machinery.SourceFileLoader("gce_provider", str(PROVIDER))
    spec = importlib.util.spec_from_loader("gce_provider", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class GceBase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-gce-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "gcloud").symlink_to(FAKE_GCLOUD)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.seed = self.tmp / "seed.json"
        self.seed.write_text(json.dumps({"type": "service_account", "client_email": SEED_EMAIL,
                                         "private_key": "-----BEGIN PRIVATE KEY-----\nnot-a-key\n"}))
        self.state_path = self.tmp / "gcloud-state.json"
        self.write_state({
            "instances": [instance(101, "dc-a", {"devcloud": "vm", "devcloud-lifetime": "ttl"}),
                          instance(102, "personal", {"purpose": "other"}, zone="us-west2-a"),
                          instance(103, "dc-b", {"devcloud": "builder"}, status="TERMINATED", ip=None)],
            "images": [{"id": "900", "name": "personal-image", "creationTimestamp": "2026-10-01T00:00:00.000-07:00",
                        "labels": {}},
                       {"id": "901", "name": "dc-img-0123456789ab-202610210500",
                        "creationTimestamp": "2026-10-21T05:00:00.000-07:00",
                        "labels": {"devcloud": "image", "devcloud-recipe": "0123456789ab"}}],
            "machine_types": MACHINE_TYPES,
            "custom_types": {"e2-custom-4-8192": {"guestCpus": 4, "memoryMb": 8192, "isSharedCpu": False}},
            "next_id": 1000, "calls": [], "fail": {},
        })
        self.vars = {"GCE_PROJECT": "example-project", "GCE_SERVICE_ACCOUNT": SA, "GCE_IMAGE_FAMILY": "devcloud",
                     "GCE_CUSTOM_TYPES": "e2-custom-4-8192 e2-custom-9-9999"}

    def write_state(self, state):
        self.state_path.write_text(json.dumps(state))

    def state(self):
        return json.loads(self.state_path.read_text())

    def fail(self, command, stderr, code=1):
        state = self.state()
        state["fail"][command] = {"code": code, "stderr": stderr}
        self.write_state(state)

    def run_op(self, op, payload=None, *, argv=None, seed=True, extra=None):
        env = {"PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}", "HOME": str(self.home),
               "FAKE_GCLOUD_STATE": str(self.state_path), "CLOUDSDK_CONFIG": str(self.tmp / "persons-gcloud"),
               "CLOUDSDK_CORE_ACCOUNT": "person@example.com", **self.vars}
        if seed:
            env["DEVCLOUD_SEED_FILE"] = str(self.seed)
        env.update(extra or {})
        r = subprocess.run([str(PROVIDER), *([op] if argv is None else argv)], input=json.dumps(payload or {}),
                           env=env, capture_output=True, text=True, timeout=60)
        self.assertNotIn("not-a-key", r.stdout + r.stderr, "the seed's key was printed")
        return r

    def ok(self, op, payload=None, **kw):
        r = self.run_op(op, payload, **kw)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def refused(self, op, payload, kind):
        r = self.run_op(op, payload)
        self.assertEqual(r.returncode, 3, r.stderr)
        answer = json.loads(r.stdout)
        self.assertEqual(answer["kind"], kind)
        self.assertNotIn("\n", answer["error"])
        return answer

    def calls(self):
        return [c["argv"] for c in self.state()["calls"]]

    def calls_of(self, *words):
        return [c for c in self.calls() if c[:len(words)] == list(words)]

    def flag(self, argv, name):
        values = [a.split("=", 1)[1] for a in argv if a.startswith(name + "=")]
        return values[-1] if values else None


def create_payload(**over):
    payload = {"name": "dc-new-7f3a", "type": "e2-custom-4-8192", "location": ZONE, "image": None,
               "labels": {"devcloud": "vm", "devcloud-lifetime": "ttl", "devcloud-expires": "1792000000",
                          "devcloud-by": "macbook"},
               "ssh_public_keys": ["ssh-ed25519 AAAAkey driver@macbook"],
               "user_data": "#cloud-config\nruncmd: [true]\n", "disk_gb": None, "spot": False}
    payload.update(over)
    return payload


class IdentityTest(GceBase):
    def test_gcloud_runs_under_a_private_config_with_the_seed_activated_once(self):
        self.ok("list")
        self.ok("list")
        state = self.state()
        private = str(self.home / ".local/state/devcloud/gce/gcloud")
        self.assertEqual(state["activated"], [str(self.seed)], "activated once, from the seed's path")
        for call in state["calls"]:
            self.assertEqual(call["env"]["CLOUDSDK_CONFIG"], private)
            self.assertEqual(call["env"].get("CLOUDSDK_CORE_ACCOUNT"), SEED_EMAIL)
            self.assertEqual(call["env"].get("CLOUDSDK_CORE_PROJECT"), "example-project")

    def test_a_changed_seed_is_activated_again(self):
        self.ok("list")
        self.seed.write_text(self.seed.read_text().replace("not-a-key", "not-a-key-either"))
        self.ok("list")
        self.assertEqual(len(self.state()["activated"]), 2)

    def test_no_seed_or_no_project_fails_before_gcloud_runs(self):
        r = self.run_op("list", seed=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DEVCLOUD_SEED_FILE", r.stderr)
        del self.vars["GCE_PROJECT"]
        r = self.run_op("list")
        self.assertEqual(r.returncode, 1)
        self.assertIn("GCE_PROJECT", r.stderr)
        self.assertEqual(self.calls(), [])


class InfoAndTypesTest(GceBase):
    def test_info(self):
        self.assertEqual(self.ok("info"), {"protocol": 1,
                                           "capabilities": ["user_data", "images", "spot", "metadata_seed"]})
        self.assertEqual(self.calls(), [], "info needs no gcloud")

    def test_types_are_the_zones_dedicated_types_and_the_named_custom_ones(self):
        types = {t["type"]: t for t in self.ok("types", {"location": ZONE})}
        self.assertEqual(sorted(types), ["e2-custom-4-8192", "e2-highcpu-2", "e2-standard-4", "n1-standard-2"])
        self.assertEqual(types["e2-custom-4-8192"], {"type": "e2-custom-4-8192", "vcpus": 4, "memory_gb": 8.0,
                                                     "disk_gb": 50, "available": True, "hourly_price": None,
                                                     "currency": "USD"})
        self.assertFalse(types["n1-standard-2"]["available"], "a deprecated type is not available")

    def test_the_disk_default_comes_from_the_account(self):
        self.vars["GCE_DISK_GB"] = "80"
        self.assertEqual({t["disk_gb"] for t in self.ok("types", {"location": ZONE})}, {80})

    def test_prices_come_from_a_fresh_cache(self):
        cache = self.home / ".local/state/devcloud/gce/prices-us-west1.json"
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps({"fetched": 4102444800, "rates": {"e2": {"core": 0.02, "ram": 0.003}}}))
        types = {t["type"]: t for t in self.ok("types", {"location": ZONE})}
        self.assertAlmostEqual(types["e2-custom-4-8192"]["hourly_price"], 4 * 0.02 + 8 * 0.003)
        self.assertIsNone(types["n1-standard-2"]["hourly_price"], "no rate for its family")


class PriceParseTest(unittest.TestCase):
    def test_on_demand_core_and_ram_rates_of_the_region(self):
        gce = load_module()

        def sku(description, group, usage, regions, price, unit="h"):
            units, nanos = divmod(round(price * 1e9), 10 ** 9)
            return {"description": description, "serviceRegions": regions,
                    "category": {"resourceFamily": "Compute", "resourceGroup": group, "usageType": usage},
                    "pricingInfo": [{"pricingExpression": {"usageUnit": unit, "tieredRates": [
                        {"unitPrice": {"units": str(units), "nanos": nanos}}]}}]}
        skus = [sku("E2 Instance Core running in Americas", "CPU", "OnDemand", ["us-west1", "us-east1"], 0.0218),
                sku("E2 Instance Ram running in Americas", "RAM", "OnDemand", ["us-west1"], 0.0029, "GiBy.h"),
                sku("Spot Preemptible E2 Instance Core running in Americas", "CPU", "Preemptible", ["us-west1"], 0.01),
                sku("N2D AMD Instance Core running in Americas", "CPU", "OnDemand", ["us-west1"], 0.03),
                sku("N2D AMD Instance Ram running in Americas", "RAM", "OnDemand", ["us-west1"], 0.004, "GiBy.h"),
                sku("N1 Predefined Instance Core running in Americas", "CPU", "OnDemand", ["us-west1"], 0.031),
                sku("E2 Instance Core running in Paris", "CPU", "OnDemand", ["europe-west9"], 0.5),
                sku("Commitment v1: E2 Cpu in Americas for 1 Year", "CPU", "Commit1Yr", ["us-west1"], 0.01)]
        rates = gce.rates_from(skus, "us-west1")
        self.assertEqual(rates["e2"], {"core": 0.0218, "ram": 0.0029})
        self.assertEqual(rates["n2d"], {"core": 0.03, "ram": 0.004})
        self.assertEqual(rates["n1"], {"core": 0.031})
        self.assertAlmostEqual(gce.price("e2-standard-4", 4, 16.0, rates), 4 * 0.0218 + 16 * 0.0029)
        self.assertIsNone(gce.price("n1-standard-1", 1, 3.75, rates), "a family without both rates")
        self.assertIsNone(gce.price("n2d-custom-4-8192", 4, 8.0, rates), "custom outside E2 is priced apart")


class CreateTest(GceBase):
    def create(self, **over):
        vm = self.ok("create", create_payload(**over))
        [argv] = self.calls_of("compute", "instances", "create")
        return vm, argv

    def test_the_command_line_of_a_create(self):
        vm, argv = self.create()
        self.assertEqual(argv[3], "dc-new-7f3a")
        self.assertEqual(self.flag(argv, "--zone"), ZONE)
        self.assertEqual(self.flag(argv, "--machine-type"), "e2-custom-4-8192")
        self.assertEqual(self.flag(argv, "--service-account"), SA)
        self.assertEqual(self.flag(argv, "--scopes"), "cloud-platform")
        self.assertEqual(self.flag(argv, "--labels"),
                         "devcloud=vm,devcloud-lifetime=ttl,devcloud-expires=1792000000,devcloud-by=macbook")
        self.assertEqual(self.flag(argv, "--metadata"), "block-project-ssh-keys=TRUE")
        self.assertEqual(self.flag(argv, "--image-family"), "ubuntu-2404-lts-amd64")
        self.assertEqual(self.flag(argv, "--image-project"), "ubuntu-os-cloud")
        self.assertEqual(self.flag(argv, "--boot-disk-size"), "50GB")
        self.assertEqual(self.flag(argv, "--boot-disk-type"), "pd-balanced")
        self.assertIsNone(self.flag(argv, "--provisioning-model"))
        self.assertEqual(vm, {"id": "1000", "name": "dc-new-7f3a", "location": ZONE, "type": "e2-custom-4-8192",
                              "labels": create_payload()["labels"], "public_ipv4": "198.51.100.232",
                              "state": "running", "created": epoch("2026-10-21T05:00:00.000-07:00")})

    def test_user_data_reaches_the_instance_from_a_file_and_never_argv(self):
        _, argv = self.create()
        path = self.flag(argv, "--metadata-from-file")
        self.assertTrue(path.startswith("user-data="))
        made = [i for i in self.state()["instances"] if i["name"] == "dc-new-7f3a"][0]
        items = {m["key"]: m["value"] for m in made["metadata"]["items"]}
        self.assertEqual(items["user-data"], create_payload()["user_data"])
        self.assertEqual(items["block-project-ssh-keys"], "TRUE")
        self.assertFalse(any("runcmd" in a for a in argv))

    def test_spot_flags(self):
        _, argv = self.create(spot=True)
        self.assertEqual(self.flag(argv, "--provisioning-model"), "SPOT")
        self.assertEqual(self.flag(argv, "--instance-termination-action"), "DELETE")

    def test_an_image_of_the_project_and_a_disk_larger_than_the_default(self):
        _, argv = self.create(image="dc-img-0123456789ab-202610210500", disk_gb=120)
        self.assertEqual(self.flag(argv, "--image"), "dc-img-0123456789ab-202610210500")
        self.assertEqual(self.flag(argv, "--image-project"), "example-project")
        self.assertIsNone(self.flag(argv, "--image-family"))
        self.assertEqual(self.flag(argv, "--boot-disk-size"), "120GB")

    def test_a_disk_below_the_default_keeps_the_default(self):
        _, argv = self.create(disk_gb=20)
        self.assertEqual(self.flag(argv, "--boot-disk-size"), "50GB")

    def test_hyperdisk_families(self):
        _, argv = self.create(type="c4-standard-4")
        self.assertEqual(self.flag(argv, "--boot-disk-type"), "hyperdisk-balanced")

    def test_no_seed_is_delivered_and_no_key_reaches_the_instance_metadata(self):
        self.create()
        made = [i for i in self.state()["instances"] if i["name"] == "dc-new-7f3a"][0]
        keys = {m["key"] for m in made["metadata"]["items"]}
        self.assertEqual(keys, {"user-data", "block-project-ssh-keys"})

    def test_refusals(self):
        self.fail("instances create", "ERROR: (gcloud.compute.instances.create) Could not fetch resource:\n"
                                      " - Quota 'E2_CPUS' exceeded.  Limit: 24.0 in region us-west1.")
        self.refused("create", create_payload(), "quota")
        self.fail("instances create", "ERROR: (gcloud.compute.instances.create) Could not fetch resource:\n"
                                      " - The zone 'projects/p/zones/us-west1-b' does not have enough resources "
                                      "available to fulfill the request.  '(resource type:compute)'.")
        self.refused("create", create_payload(), "unavailable")

    def test_user_data_over_the_metadata_limit_is_refused(self):
        self.refused("create", create_payload(user_data="x" * (256 * 1024 + 1)), "other")
        self.assertEqual(self.calls_of("compute", "instances", "create"), [])

    def test_another_failure_is_exit_1_with_its_last_line(self):
        self.fail("instances create", "ERROR: something odd\n - and its detail")
        r = self.run_op("create", create_payload())
        self.assertEqual(r.returncode, 1)
        self.assertIn("something odd - and its detail", r.stderr)


class ServersTest(GceBase):
    def test_list_returns_only_labeled_instances_of_every_zone(self):
        vms = self.ok("list")
        self.assertEqual([v["name"] for v in vms], ["dc-a", "dc-b"])
        self.assertEqual(vms[1]["state"], "terminated")
        self.assertIsNone(vms[1]["public_ipv4"])
        [argv] = self.calls_of("compute", "instances", "list")
        self.assertEqual(self.flag(argv, "--filter"), "labels.devcloud:*")

    def test_get_by_id_or_null(self):
        self.assertEqual(self.ok("get", {"id": "101"})["name"], "dc-a")
        self.assertIsNone(self.ok("get", {"id": "999"}))
        r = self.run_op("get", {"id": "101 OR name:x"})
        self.assertEqual(r.returncode, 2, "an id that is not a number is usage")

    def test_set_labels_is_the_full_set_in_one_update(self):
        vm = self.ok("set-labels", {"id": "101", "labels": {"devcloud": "vm", "devcloud-held": "1"}})
        self.assertEqual(vm["labels"], {"devcloud": "vm", "devcloud-held": "1"})
        [argv] = self.calls_of("compute", "instances", "update")
        self.assertEqual(self.flag(argv, "--remove-labels"), "devcloud-lifetime")
        self.assertEqual(self.flag(argv, "--update-labels"), "devcloud=vm,devcloud-held=1")

    def test_delete_is_idempotent(self):
        self.assertEqual(self.ok("delete", {"id": "101"}), {})
        self.assertEqual([i["name"] for i in self.state()["instances"]], ["personal", "dc-b"])
        self.assertEqual(self.ok("delete", {"id": "101"}), {})
        [argv] = self.calls_of("compute", "instances", "delete")
        self.assertIn("--quiet", argv)
        self.assertEqual(self.flag(argv, "--zone"), ZONE)


class ImagesTest(GceBase):
    def test_round_trip_from_the_instances_boot_disk(self):
        labels = {"devcloud": "image", "devcloud-recipe": "aaaaaaaaaaaa"}
        image = self.ok("image-create", {"id": "103", "name": "dc-img-aaaaaaaaaaaa-202610211200", "labels": labels})
        self.assertEqual(image, {"id": "dc-img-aaaaaaaaaaaa-202610211200", "name": "dc-img-aaaaaaaaaaaa-202610211200",
                                 "labels": labels, "created": epoch("2026-10-21T05:00:00.000-07:00"),
                                 "state": "ready"})
        [argv] = self.calls_of("compute", "images", "create")
        self.assertEqual(self.flag(argv, "--source-disk"), "dc-b")
        self.assertEqual(self.flag(argv, "--source-disk-zone"), ZONE)
        self.assertEqual(self.flag(argv, "--family"), "devcloud")
        self.assertIn("--force", argv)
        names = [i["name"] for i in self.ok("images")]
        self.assertEqual(names, ["dc-img-0123456789ab-202610210500", "dc-img-aaaaaaaaaaaa-202610211200"])
        self.assertEqual(self.ok("image-delete", {"id": image["id"]}), {})
        self.assertEqual(self.ok("image-delete", {"id": image["id"]}), {})
        self.assertEqual(len(self.ok("images")), 1)

    def test_every_owned_image_is_listed_with_its_state(self):
        # The listing is the ownership fence for deletes, so a pending or failed image stays in it;
        # `state` says whether a create can use it now.
        state = json.loads(self.state_path.read_text())
        for iid, status in (("902", "PENDING"), ("903", "FAILED")):
            state["images"].append({"id": iid, "name": f"dc-img-0123456789ab-20261021100{iid[-1]}", "status": status,
                                    "creationTimestamp": "2026-10-21T10:00:00.000-07:00",
                                    "labels": {"devcloud": "image", "devcloud-recipe": "0123456789ab"}})
        state["images"][1]["status"] = "READY"
        self.write_state(state)
        self.assertEqual([(i["name"][-4:], i["state"]) for i in self.ok("images")],
                         [("0500", "ready"), ("1002", "pending"), ("1003", "failed")])

    def test_a_test_image_joins_no_family(self):
        self.ok("image-create", {"id": "103", "name": "dc-ptest-img-1", "labels": {"devcloud": "test"}})
        [argv] = self.calls_of("compute", "images", "create")
        self.assertIsNone(self.flag(argv, "--family"))


class UsageTest(GceBase):
    def test_unknown_or_missing_op_and_bad_stdin(self):
        for argv in (["frobnicate"], []):
            r = self.run_op(None, argv=argv)
            self.assertEqual(r.returncode, 2)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
