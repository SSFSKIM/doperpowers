"""The shipped AWS provider (the driver's Design §6.6, I13): the real script run as a subprocess
against the stand-in `aws` CLI in tests/fixtures, whose state is a JSON file."""

import base64
import gzip
import json
import os
import pathlib
import random
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve()
PROVIDER = HERE.parents[2] / "driver" / "providers" / "aws"
FAKE_AWS = HERE.parents[1] / "fixtures" / "aws"
REGION = "us-west-2"
UBUNTU_PARAM = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
UBUNTU_AMI = "ami-0ubuntu2404west2"
KEY_ID = "AKIAEXAMPLEEXAMPLE00"
SECRET = "made-up-secret-access-key-0123456789abcdef"
NOW = "2026-11-04T10:00:00+00:00"
EPOCH = 1793786400          # NOW as Unix seconds


def itype(name, vcpus, mib, arch=("x86_64",)):
    return {"InstanceType": name, "VCpuInfo": {"DefaultVCpus": vcpus}, "MemoryInfo": {"SizeInMiB": mib},
            "ProcessorInfo": {"SupportedArchitectures": list(arch)}}


INSTANCE_TYPES = [itype("t3.nano", 2, 512), itype("t3.micro", 2, 1024), itype("m7i.xlarge", 4, 16384),
                  itype("m7i.2xlarge", 8, 32768), itype("c7i.large", 2, 4096), itype("g6.xlarge", 4, 16384),
                  itype("m7g.large", 2, 8192, arch=("arm64",)), itype("t3a.small", 2, 2048),
                  itype("m5.large", 2, 8192), itype("m7i-flex.large", 2, 8192)]
OFFERED = ["t3.nano", "t3.micro", "m7i.xlarge", "m7i.2xlarge", "g6.xlarge", "m7g.large", "t3a.small", "m5.large",
           "m7i-flex.large"]


def product(instance_type, usd, region=REGION, **attrs):
    attributes = {"instanceType": instance_type, "regionCode": region, "operatingSystem": "Linux",
                  "tenancy": "Shared", "preInstalledSw": "NA", "capacitystatus": "Used",
                  "licenseModel": "No License required", **attrs}
    return {"product": {"attributes": attributes}, "serviceCode": "AmazonEC2",
            "terms": {"OnDemand": {"SKU.TERM": {"priceDimensions": {"SKU.TERM.RATE": {
                "unit": "Hrs", "pricePerUnit": {"USD": f"{usd:.10f}"}}}}}}}


def region_state(region, subnets=("a", "b", "c")):
    return {
        "instance_types": INSTANCE_TYPES, "offerings": OFFERED,
        "vpcs": [{"VpcId": f"vpc-{region}", "IsDefault": True}, {"VpcId": "vpc-other", "IsDefault": False}],
        "subnets": [{"SubnetId": f"subnet-{region}-{z}", "VpcId": f"vpc-{region}", "AvailabilityZone": f"{region}{z}",
                     "DefaultForAz": True} for z in subnets]
                   + [{"SubnetId": "subnet-private", "VpcId": f"vpc-{region}", "AvailabilityZone": f"{region}a",
                       "DefaultForAz": False}],
        "security_groups": [{"GroupId": "sg-default", "GroupName": "default", "VpcId": f"vpc-{region}", "Tags": [],
                             "IpPermissions": []}],
        "instances": [], "images": [], "snapshots": [],
        "public_images": [{"ImageId": UBUNTU_AMI if region == REGION else f"ami-0ubuntu-{region}", "Name": "ubuntu",
                           "State": "available", "OwnerId": "099720109477", "RootDeviceName": "/dev/sda1",
                           "BlockDeviceMappings": [{"DeviceName": "/dev/sda1",
                                                    "Ebs": {"SnapshotId": "snap-canonical", "VolumeSize": 8}}]}],
        "ssm": {UBUNTU_PARAM: UBUNTU_AMI if region == REGION else f"ami-0ubuntu-{region}"},
    }


def instance(iid, name, labels, state="running", region=REGION, itype_="m7i.xlarge", launch=NOW, attach=None,
             ip="192.0.2.7"):
    tags = [{"Key": "Name", "Value": name}] + [{"Key": k, "Value": v} for k, v in labels.items()]
    made = {"InstanceId": iid, "InstanceType": itype_, "State": {"Name": state}, "LaunchTime": launch,
            "Placement": {"AvailabilityZone": f"{region}a"}, "RootDeviceName": "/dev/sda1", "Tags": tags,
            "BlockDeviceMappings": [{"DeviceName": "/dev/sda1", "Ebs": {"AttachTime": attach or launch,
                                                                        "VolumeId": f"vol-{iid}"}}]}
    if ip:
        made["PublicIpAddress"] = ip
    return made


def create_payload(**over):
    payload = {"name": "dc-new-7f3a", "type": "m7i.xlarge", "location": REGION, "image": None,
               "labels": {"devcloud": "vm", "devcloud-lifetime": "keep", "devcloud-by": "macbook",
                          "devcloud-recipe": "0123456789ab"},
               "ssh_public_keys": ["ssh-ed25519 AAAAkey driver@macbook"],
               "user_data": "#cloud-config\ndisable_root: false\n", "disk_gb": None, "spot": False}
    payload.update(over)
    return payload


class AwsBase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-aws-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "aws").symlink_to(FAKE_AWS)
        self.home = self.tmp / "home"
        (self.home / ".aws").mkdir(parents=True)
        (self.home / ".aws/config").write_text("[default]\nregion = eu-north-1\n")
        self.state_path = self.tmp / "aws-state.json"
        self.write_state({"regions": {REGION: region_state(REGION), "us-east-1": region_state("us-east-1")},
                          "products": [product("m7i.xlarge", 0.2016), product("t3.micro", 0.0104),
                                       product("m7i.xlarge", 0.5, operatingSystem="Windows"),
                                       product("m7i.xlarge", 0.9, region="us-east-1")],
                          "calls": [], "fail": {}, "next_id": 4096, "now": NOW})
        self.vars = {"AWS_REGION": REGION}

    def write_state(self, state):
        self.state_path.write_text(json.dumps(state))

    def state(self):
        return json.loads(self.state_path.read_text())

    def region(self, name=REGION):
        return self.state()["regions"][name]

    def edit(self, fn):
        state = self.state()
        fn(state)
        self.write_state(state)

    def fail(self, command, *failures):
        self.edit(lambda s: s["fail"].setdefault(command, []).extend(failures))

    def run_op(self, op, payload=None, *, argv=None, extra=None, keys=True):
        env = {"PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}", "HOME": str(self.home),
               "FAKE_AWS_STATE": str(self.state_path), "AWS_PROFILE": "persons-profile",
               "AWS_SESSION_TOKEN": "persons-session", "AWS_CONFIG_FILE": str(self.home / ".aws/config"),
               "AWS_DEFAULT_REGION": "eu-north-1", **self.vars}
        if keys:
            env.update(AWS_ACCESS_KEY_ID=KEY_ID, AWS_SECRET_ACCESS_KEY=SECRET)
        env.update(extra or {})
        r = subprocess.run([str(PROVIDER), *([op] if argv is None else argv)], input=json.dumps(payload or {}),
                           env=env, capture_output=True, text=True, timeout=60)
        self.assertNotIn(SECRET, r.stdout + r.stderr, "the secret access key was printed")
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
        if name not in argv:
            return None
        value = argv[argv.index(name) + 1]
        return json.loads(value) if value[:1] in "[{" else value


class IdentityTest(AwsBase):
    def test_the_cli_runs_with_the_key_alone_and_private_empty_configuration(self):
        self.ok("list")
        private = self.home / ".local/state/devcloud/aws"
        calls = self.state()["calls"]
        self.assertTrue(calls)
        for call in calls:
            env = call["env"]
            self.assertEqual(env["AWS_CONFIG_FILE"], str(private / "config"))
            self.assertEqual(env["AWS_SHARED_CREDENTIALS_FILE"], str(private / "credentials"))
            self.assertEqual(env["AWS_ACCESS_KEY_ID"], KEY_ID)
            self.assertEqual(env["AWS_SECRET_ACCESS_KEY"], f"<{len(SECRET)} chars>")
            for gone in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_DEFAULT_REGION", "AWS_REGION"):
                self.assertNotIn(gone, env, f"{gone} reached the CLI")
            self.assertEqual(call["argv"][call["argv"].index("--region") + 1], REGION)
            self.assertFalse(any(SECRET in a for a in call["argv"]), "the secret reached argv")
        self.assertEqual((private / "config").read_text(), "")
        self.assertEqual((self.home / ".aws/config").read_text(), "[default]\nregion = eu-north-1\n")

    def test_a_missing_or_malformed_region_is_usage_before_the_cli_runs(self):
        del self.vars["AWS_REGION"]
        r = self.run_op("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("AWS_REGION", r.stderr)
        self.vars["AWS_REGION"] = "us-west-2; rm -rf /"
        self.assertEqual(self.run_op("list").returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_a_missing_key_fails_before_the_cli_runs(self):
        r = self.run_op("list", keys=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("AWS_ACCESS_KEY_ID", r.stderr)
        self.assertEqual(self.calls(), [])


class InfoAndTypesTest(AwsBase):
    def test_info(self):
        self.assertEqual(self.ok("info"), {"protocol": 1, "capabilities": ["user_data", "images", "spot"]})
        self.assertEqual(self.calls(), [], "info needs no CLI")

    def test_types_are_the_regions_x86_types_of_the_families(self):
        types = {t["type"]: t for t in self.ok("types", {"location": REGION})}
        self.assertEqual(sorted(types), ["c7i.large", "g6.xlarge", "m7i.2xlarge", "m7i.xlarge", "t3.micro", "t3.nano"])
        self.assertEqual(types["m7i.xlarge"], {"type": "m7i.xlarge", "vcpus": 4, "memory_gb": 16.0, "disk_gb": 50,
                                               "available": True, "hourly_price": 0.2016, "currency": "USD",
                                               "architecture": "x86"})
        self.assertEqual(types["t3.nano"]["memory_gb"], 0.5)
        self.assertFalse(types["c7i.large"]["available"], "not offered in the region")
        self.assertIsNone(types["g6.xlarge"]["hourly_price"], "a type the catalog does not price shows none")

    def test_the_families_and_the_disk_come_from_the_account(self):
        self.vars.update(AWS_FAMILIES="m7i, g6", AWS_DISK_GB="80")
        types = self.ok("types", {"location": REGION})
        self.assertEqual(sorted(t["type"] for t in types), ["g6.xlarge", "m7i.2xlarge", "m7i.xlarge"])
        self.assertEqual({t["disk_gb"] for t in types}, {80})

    def test_a_location_other_than_the_region_is_usage(self):
        r = self.run_op("types", {"location": "us-east-1"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("AWS_REGION", r.stderr)
        r = self.run_op("create", create_payload(location="us-west-2a"))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.calls_of("ec2", "run-instances"), [])

    def test_prices_are_cached_a_week_and_their_failure_never_fails_types(self):
        self.ok("types", {"location": REGION})
        reads = len(self.calls_of("pricing", "get-products"))
        self.assertGreaterEqual(reads, 1)
        [argv] = self.calls_of("pricing", "get-products")[:1]
        self.assertEqual(argv[argv.index("--region") + 1], "us-east-1", "the Pricing API's endpoint")
        self.ok("types", {"location": REGION})
        self.assertEqual(len(self.calls_of("pricing", "get-products")), reads, "the cache was not used")
        cache = self.home / ".local/state/devcloud/aws/prices-us-west-2.json"
        data = json.loads(cache.read_text())
        data["fetched"] -= 8 * 86400
        cache.write_text(json.dumps(data))
        self.fail("pricing get-products", {"error": "AccessDeniedException", "message": "no"})
        types = {t["type"]: t for t in self.ok("types", {"location": REGION})}
        self.assertEqual(types["m7i.xlarge"]["hourly_price"], 0.2016, "a stale cache beats none")
        cache.unlink()
        self.fail("pricing get-products", {"error": "AccessDeniedException", "message": "no"})
        types = {t["type"]: t for t in self.ok("types", {"location": REGION})}
        self.assertIsNone(types["m7i.xlarge"]["hourly_price"])


class CreateTest(AwsBase):
    def create(self, **over):
        vm = self.ok("create", create_payload(**over))
        [argv] = self.calls_of("ec2", "run-instances")
        return vm, argv

    def made(self):
        [made] = [i for i in self.region()["instances"] if i["State"]["Name"] != "terminated"]
        return made

    def test_the_command_line_of_a_create(self):
        vm, argv = self.create()
        self.assertEqual(self.flag(argv, "--image-id"), UBUNTU_AMI, "Canonical's AMI from the SSM parameter")
        [ssm] = self.calls_of("ssm", "get-parameter")
        self.assertEqual(self.flag(ssm, "--name"), UBUNTU_PARAM)
        self.assertEqual(self.flag(argv, "--instance-type"), "m7i.xlarge")
        tags = [{"Key": k, "Value": v} for k, v in create_payload()["labels"].items()] + [
            {"Key": "Name", "Value": "dc-new-7f3a"}]
        self.assertEqual(self.flag(argv, "--tag-specifications"), [{"ResourceType": "instance", "Tags": tags},
                                                                   {"ResourceType": "volume", "Tags": tags}])
        self.assertEqual(self.flag(argv, "--metadata-options"),
                         {"HttpTokens": "required", "HttpPutResponseHopLimit": 2, "HttpEndpoint": "enabled"})
        self.assertEqual(self.flag(argv, "--block-device-mappings"),
                         [{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 50, "VolumeType": "gp3",
                                                              "DeleteOnTermination": True}}])
        [nic] = self.flag(argv, "--network-interfaces")
        group = [g for g in self.region()["security_groups"] if g["GroupName"] == "devcloud"][0]
        self.assertEqual(nic, {"DeviceIndex": 0, "SubnetId": "subnet-us-west-2-a", "Groups": [group["GroupId"]],
                               "AssociatePublicIpAddress": True, "DeleteOnTermination": True})
        self.assertIsNone(self.flag(argv, "--instance-market-options"))
        self.assertNotIn("--key-name", argv, "the keys travel in user-data")
        self.assertEqual(vm, {"id": self.made()["InstanceId"], "name": "dc-new-7f3a", "location": REGION,
                              "type": "m7i.xlarge", "labels": create_payload()["labels"],
                              "public_ipv4": self.made()["PublicIpAddress"], "state": "running", "created": EPOCH})

    def test_the_security_group_is_created_once_with_its_tag_and_rules(self):
        self.create()
        groups = [g for g in self.region()["security_groups"] if g["GroupName"] == "devcloud"]
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group["VpcId"], f"vpc-{REGION}")
        self.assertEqual(group["Tags"], [{"Key": "devcloud", "Value": "network"}])
        ports = sorted((p["IpProtocol"], p["FromPort"], p["ToPort"]) for p in group["IpPermissions"])
        self.assertEqual(ports, [("tcp", 22, 22), ("udp", 41641, 41641)])
        for p in group["IpPermissions"]:
            self.assertEqual(p["IpRanges"], [{"CidrIp": "0.0.0.0/0"}])
            self.assertEqual(p["Ipv6Ranges"], [{"CidrIpv6": "::/0"}])
        self.ok("create", create_payload(name="dc-two-0001"))
        self.assertEqual(len(self.calls_of("ec2", "create-security-group")), 1, "found the second time")
        self.assertEqual(len(self.calls_of("ec2", "authorize-security-group-ingress")), 1)

    def test_a_group_left_without_its_rules_gets_them(self):
        def half_made(s):
            s["regions"][REGION]["security_groups"].append({
                "GroupId": "sg-half", "GroupName": "devcloud", "VpcId": f"vpc-{REGION}",
                "Tags": [{"Key": "devcloud", "Value": "network"}],
                "IpPermissions": [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                                   "IpRanges": [{"CidrIp": "0.0.0.0/0"}], "Ipv6Ranges": [{"CidrIpv6": "::/0"}]}]})
        self.edit(half_made)
        _, argv = self.create()
        self.assertEqual(self.calls_of("ec2", "create-security-group"), [])
        [auth] = self.calls_of("ec2", "authorize-security-group-ingress")
        self.assertEqual([p["FromPort"] for p in self.flag(auth, "--ip-permissions")], [41641])
        self.assertEqual(self.flag(argv, "--network-interfaces")[0]["Groups"], ["sg-half"])

    def test_a_group_named_devcloud_without_the_tag_is_not_used(self):
        self.edit(lambda s: s["regions"][REGION]["security_groups"].append(
            {"GroupId": "sg-theirs", "GroupName": "devcloud", "VpcId": f"vpc-{REGION}", "Tags": [],
             "IpPermissions": []}))
        r = self.run_op("create", create_payload())
        self.assertEqual(r.returncode, 1)
        self.assertIn("devcloud=network", r.stderr)
        self.assertEqual(self.calls_of("ec2", "run-instances"), [])

    def test_spot_options(self):
        _, argv = self.create(spot=True)
        self.assertEqual(self.flag(argv, "--instance-market-options"),
                         {"MarketType": "spot", "SpotOptions": {"SpotInstanceType": "one-time",
                                                                "InstanceInterruptionBehavior": "terminate"}})

    def test_an_image_and_a_disk_larger_than_the_default(self):
        self.edit(lambda s: s["regions"][REGION]["images"].append({
            "ImageId": "ami-0devcloud", "Name": "dc-img-x", "State": "available", "RootDeviceName": "/dev/sda1",
            "Tags": [{"Key": "devcloud", "Value": "image"}],
            "BlockDeviceMappings": [{"DeviceName": "/dev/sda1", "Ebs": {"SnapshotId": "snap-1", "VolumeSize": 50}}]}))
        _, argv = self.create(image="ami-0devcloud", disk_gb=120)
        self.assertEqual(self.flag(argv, "--image-id"), "ami-0devcloud")
        self.assertEqual(self.calls_of("ssm", "get-parameter"), [])
        self.assertEqual(self.flag(argv, "--block-device-mappings")[0]["Ebs"]["VolumeSize"], 120)

    def test_a_disk_below_the_default_keeps_the_default(self):
        _, argv = self.create(disk_gb=20)
        self.assertEqual(self.flag(argv, "--block-device-mappings")[0]["Ebs"]["VolumeSize"], 50)

    def test_user_data_from_a_file_and_gzip_past_16_kb(self):
        _, argv = self.create()
        self.assertTrue(self.flag(argv, "--user-data").startswith("fileb://"))
        self.assertEqual(base64.b64decode(self.made()["_request"]["--user-data"]["fileb"]).decode(),
                         create_payload()["user_data"])
        big = "#cloud-config\n" + "# padding that compresses well\n" * 1000
        self.assertGreater(len(big.encode()), 16 * 1024)
        self.ok("create", create_payload(name="dc-big-0001", user_data=big))
        sent = [i for i in self.region()["instances"] if i["Tags"][-1]["Value"] == "dc-big-0001"][0]
        data = base64.b64decode(sent["_request"]["--user-data"]["fileb"])
        self.assertLessEqual(len(data), 16 * 1024)
        self.assertEqual(gzip.decompress(data).decode(), big)

    def test_user_data_over_16_kb_compressed_is_refused(self):
        noise = random.Random(7).randbytes(20 * 1024)
        answer = self.refused("create", create_payload(user_data=base64.b64encode(noise).decode()), "other")
        self.assertIn("16", answer["error"])
        self.assertEqual(self.calls_of("ec2", "run-instances"), [])

    def test_quota_refusals(self):
        for code in ("VcpuLimitExceeded", "InstanceLimitExceeded", "MaxSpotInstanceCountExceeded"):
            with self.subTest(code=code):
                self.edit(lambda s: s["calls"].clear())
                self.fail("ec2 run-instances", {"error": code, "message": "You have requested more vCPU capacity"})
                self.refused("create", create_payload(), "quota")
                self.assertEqual(len(self.calls_of("ec2", "run-instances")), 1, "a quota is not retried elsewhere")

    def test_a_capacity_refusal_tries_the_other_default_subnets_in_turn(self):
        self.fail("ec2 run-instances",
                  {"error": "InsufficientInstanceCapacity", "message": "We currently do not have sufficient capacity"},
                  {"error": "Unsupported", "message": "Your requested instance type is not supported in your "
                                                      "requested Availability Zone (us-west-2b)."})
        vm = self.ok("create", create_payload())
        subnets = [self.flag(a, "--network-interfaces")[0]["SubnetId"] for a in self.calls_of("ec2", "run-instances")]
        self.assertEqual(subnets, ["subnet-us-west-2-a", "subnet-us-west-2-b", "subnet-us-west-2-c"])
        self.assertEqual(vm["name"], "dc-new-7f3a")

    def test_no_subnet_with_capacity_is_unavailable(self):
        self.fail("ec2 run-instances", *[{"error": "InsufficientInstanceCapacity", "message": "none here"}] * 2,
                  {"error": "InvalidInstanceType", "message": "not offered in this zone"})
        answer = self.refused("create", create_payload(), "unavailable")
        self.assertIn("m7i.xlarge", answer["error"])
        self.assertEqual(len(self.calls_of("ec2", "run-instances")), 3)
        self.assertEqual(self.region()["instances"], [])

    def test_a_missing_spot_role_names_it(self):
        self.fail("ec2 run-instances", {"error": "AuthFailure.ServiceLinkedRoleCreationNotPermitted",
                                        "message": "The provided credentials do not have permission to create the "
                                                   "service-linked role for EC2 Spot Instances."})
        answer = self.refused("create", create_payload(spot=True), "other")
        self.assertIn("AWSServiceRoleForEC2Spot", answer["error"])

    def test_another_failure_is_exit_1_with_its_line(self):
        self.fail("ec2 run-instances", {"error": "UnauthorizedOperation",
                                        "message": "You are not authorized to perform this operation."})
        r = self.run_op("create", create_payload())
        self.assertEqual(r.returncode, 1)
        self.assertIn("UnauthorizedOperation", r.stderr)


class ServersTest(AwsBase):
    def setUp(self):
        super().setUp()

        def servers(s):
            west, east = s["regions"][REGION], s["regions"]["us-east-1"]
            west["instances"] += [
                instance("i-0000000000000a01", "dc-a", {"devcloud": "vm", "devcloud-lifetime": "keep"}),
                instance("i-0000000000000a02", "personal", {"purpose": "other"}),
                instance("i-0000000000000a03", "dc-b", {"devcloud": "builder"}, state="stopped", ip=None,
                         launch="2026-11-04T12:00:00+00:00", attach="2026-11-04T09:00:00+00:00"),
                instance("i-0000000000000a04", "dc-gone", {"devcloud": "vm"}, state="terminated", ip=None),
                instance("i-0000000000000a05", "dc-going", {"devcloud": "vm"}, state="shutting-down", ip=None)]
            east["instances"] += [instance("i-0000000000000e01", "dc-east", {"devcloud": "vm"}, region="us-east-1")]
        self.edit(servers)

    def test_list_returns_the_regions_labeled_live_instances_without_their_name_tag(self):
        vms = self.ok("list")
        self.assertEqual([v["name"] for v in vms], ["dc-a", "dc-b"])
        self.assertEqual(vms[0]["labels"], {"devcloud": "vm", "devcloud-lifetime": "keep"})
        self.assertEqual(vms[1]["state"], "stopped")
        self.assertIsNone(vms[1]["public_ipv4"])
        self.assertEqual(vms[1]["created"], EPOCH - 3600, "created is the root volume's attach, not the restart")
        self.assertEqual({v["location"] for v in vms}, {REGION})

    def test_list_in_two_regions_from_independent_invocations_with_empty_state(self):
        west = self.ok("list")
        shutil.rmtree(self.home / ".local/state/devcloud/aws")
        self.vars["AWS_REGION"] = "us-east-1"
        east = self.ok("list")
        self.assertEqual([v["name"] for v in west], ["dc-a", "dc-b"])
        self.assertEqual([(v["name"], v["location"]) for v in east], [("dc-east", "us-east-1")])

    def test_get_by_id_or_null_for_a_missing_or_terminated_instance(self):
        self.assertEqual(self.ok("get", {"id": "i-0000000000000a01"})["name"], "dc-a")
        self.assertIsNone(self.ok("get", {"id": "i-00000000000009ff"}))
        self.assertIsNone(self.ok("get", {"id": "i-0000000000000a04"}), "terminated is gone")
        self.assertIsNone(self.ok("get", {"id": "i-0000000000000a05"}), "shutting-down is gone")
        self.assertEqual(self.run_op("get", {"id": "i-1 --filters x"}).returncode, 2, "an id that is not one")

    def test_set_labels_is_the_full_set(self):
        vm = self.ok("set-labels", {"id": "i-0000000000000a01", "labels": {"devcloud": "vm", "devcloud-held": "1"}})
        self.assertEqual(vm["labels"], {"devcloud": "vm", "devcloud-held": "1"})
        [deleted] = self.calls_of("ec2", "delete-tags")
        self.assertEqual(self.flag(deleted, "--tags"), [{"Key": "devcloud-lifetime"}])
        made = [i for i in self.region()["instances"] if i["InstanceId"] == "i-0000000000000a01"][0]
        self.assertIn({"Key": "Name", "Value": "dc-a"}, made["Tags"], "the Name tag stays")

    def test_delete_is_idempotent(self):
        self.assertEqual(self.ok("delete", {"id": "i-0000000000000a01"}), {})
        self.assertIsNone(self.ok("get", {"id": "i-0000000000000a01"}))
        self.assertEqual(self.ok("delete", {"id": "i-00000000000009ff"}), {})


class ImagesTest(AwsBase):
    def setUp(self):
        super().setUp()
        self.edit(lambda s: s["regions"][REGION]["instances"].append(
            instance("i-0000000000000b01", "dc-bake-0001", {"devcloud": "builder"}, state="stopping")))

    def test_round_trip_from_a_stopped_builder(self):
        labels = {"devcloud": "image", "devcloud-recipe": "aaaaaaaaaaaa"}
        image = self.ok("image-create", {"id": "i-0000000000000b01", "name": "dc-img-aaaaaaaaaaaa-202611041000",
                                         "labels": labels})
        self.assertTrue(image["id"].startswith("ami-"))
        self.assertEqual(image, {"id": image["id"], "name": "dc-img-aaaaaaaaaaaa-202611041000", "labels": labels,
                                 "created": EPOCH, "state": "ready"})
        [argv] = self.calls_of("ec2", "create-image")
        tags = [{"Key": k, "Value": v} for k, v in labels.items()]
        self.assertEqual(self.flag(argv, "--tag-specifications"),
                         [{"ResourceType": "image", "Tags": tags}, {"ResourceType": "snapshot", "Tags": tags}])
        self.assertIn("--no-reboot", argv)
        self.assertEqual([i["id"] for i in self.ok("images")], [image["id"]])
        self.assertEqual(self.ok("image-delete", {"id": image["id"]}), {})
        [dereg] = self.calls_of("ec2", "deregister-image")
        self.assertIn("--delete-associated-snapshots", dereg)
        self.assertEqual(self.region()["snapshots"], [], "the AMI's snapshot went with it")
        self.assertEqual(self.ok("image-delete", {"id": image["id"]}), {}, "idempotent")
        self.assertEqual(self.ok("images"), [])

    def test_images_lists_only_the_accounts_devcloud_amis_whatever_their_state(self):
        def amis(s):
            s["regions"][REGION]["images"] += [
                {"ImageId": "ami-0mine", "Name": "personal", "State": "available", "CreationDate": NOW, "Tags": [],
                 "BlockDeviceMappings": []},
                {"ImageId": "ami-0pending", "Name": "dc-img-p", "State": "pending", "CreationDate": NOW,
                 "Tags": [{"Key": "devcloud", "Value": "image"}], "BlockDeviceMappings": []},
                {"ImageId": "ami-0failed", "Name": "dc-img-f", "State": "failed", "CreationDate": NOW,
                 "Tags": [{"Key": "devcloud", "Value": "image"}, {"Key": "Name", "Value": "x"}],
                 "BlockDeviceMappings": []}]
        self.edit(amis)
        listed = self.ok("images")
        self.assertEqual([(i["id"], i["state"], i["labels"]) for i in listed],
                         [("ami-0pending", "pending", {"devcloud": "image"}),
                          ("ami-0failed", "failed", {"devcloud": "image"})])
        [argv] = self.calls_of("ec2", "describe-images")
        self.assertEqual(self.flag(argv, "--owners"), "self")

    def test_the_orphan_snapshot_sweep(self):
        day_old = "2026-11-03T09:00:00+00:00"

        def snapshots(s):
            west = s["regions"][REGION]
            west["images"].append({"ImageId": "ami-0kept", "Name": "dc-img-k", "State": "available",
                                   "CreationDate": NOW, "Tags": [{"Key": "devcloud", "Value": "image"}],
                                   "BlockDeviceMappings": [{"DeviceName": "/dev/sda1",
                                                            "Ebs": {"SnapshotId": "snap-kept", "VolumeSize": 50}}]})
            image_tag = [{"Key": "devcloud", "Value": "image"}]
            west["snapshots"] += [
                {"SnapshotId": "snap-kept", "StartTime": day_old, "Tags": image_tag},     # its AMI names it
                {"SnapshotId": "snap-orphan", "StartTime": day_old, "Tags": image_tag},   # an interrupted delete
                {"SnapshotId": "snap-test", "StartTime": day_old, "Tags": [{"Key": "devcloud", "Value": "test"}]},
                {"SnapshotId": "snap-fresh", "StartTime": NOW, "Tags": image_tag},        # a create in flight
                {"SnapshotId": "snap-theirs", "StartTime": day_old, "Tags": []}]
        self.edit(snapshots)
        self.assertEqual([i["id"] for i in self.ok("images")], ["ami-0kept"])
        left = sorted(s["SnapshotId"] for s in self.region()["snapshots"])
        self.assertEqual(left, ["snap-fresh", "snap-kept", "snap-theirs"])

    def test_a_failing_sweep_never_fails_images(self):
        self.fail("ec2 describe-snapshots", {"error": "UnauthorizedOperation", "message": "no"})
        r = self.run_op("images")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("snapshot", r.stderr)


class UsageTest(AwsBase):
    def test_unknown_or_missing_op_and_bad_stdin(self):
        for argv in (["frobnicate"], []):
            self.assertEqual(self.run_op(None, argv=argv).returncode, 2)
        r = subprocess.run([str(PROVIDER), "list"], input="not json", capture_output=True, text=True,
                           env={"PATH": os.environ["PATH"], "AWS_REGION": REGION})
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
