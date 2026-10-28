"""The idle notice's descriptor inputs and the driver's read of the host."""
import json
import subprocess
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import descriptor
from driver import context, hostctl, up
from driver_fixtures import DriverBase, NOW
import test_driver_compose
from test_driver_up import UpBase
from test_lease import BASE


class NoticeDescriptorTest(unittest.TestCase):
    def test_new_keys_are_optional_and_validate_at_the_boundary(self):
        d = descriptor.parse(BASE)
        self.assertEqual((d.created, d.hourly_price, d.currency, d.creator_project), (None, None, None, None))
        for key, values in {
            "CREATED": ["-1", "1.5", "soon"],
            "HOURLY_PRICE": ["-0.1", "NaN", "Infinity", "1e1000"],
            "CURRENCY": ["usd", "$", "USDD"],
            "CREATOR_PROJECT": ["--org", "one,two", "one two"],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(descriptor.DescriptorError):
                    descriptor.parse(BASE + f'DEVCLOUD_{key}="{value}"\n')

    def test_composed_descriptor_carries_cost_and_creator_project(self):
        d = descriptor.parse(test_driver_compose.DescriptorTest().compose(created=NOW, hourly_price=0.1178, currency="EUR",
                                                     creator_project="example"))
        self.assertEqual((d.created, d.hourly_price, d.currency, d.creator_project),
                         (NOW, 0.1178, "EUR", "example"))

    def test_small_decimal_price_is_not_written_as_an_exponent(self):
        d = descriptor.parse(test_driver_compose.DescriptorTest().compose(created=NOW, hourly_price=0.000001))
        self.assertEqual(d.hourly_price, 0.000001)


class CreatorTest(DriverBase):
    def test_one_who_call_provides_tag_short_and_project(self):
        ctx = self.make_ctx()
        # Use the real Context's identity path rather than the fixture's injected creator.
        ctx = context.Context(ctx.paths, env={"CLAUDE_CODE_SESSION_ID": "abcd1234-session", "PATH": "/bin"})
        result = subprocess.CompletedProcess([], 0, "Sminos-Session: build task#abcd1234 (example on testhost)\n", "")
        with mock.patch.object(context, "_sminos", return_value="/opt/sminos"), \
                mock.patch.object(context.subprocess, "run", return_value=result) as run:
            self.assertEqual(ctx.creator(), ("@abcd1234", "abcd1234"))
            self.assertEqual(ctx.creator_project(), "example")
            self.assertEqual(run.call_count, 1)

    def test_unnamed_session_address_and_outside_a_session(self):
        result = subprocess.CompletedProcess([], 0, "Sminos-Session: abcd1234 (example on testhost)\n", "")
        with mock.patch.object(context, "_sminos", return_value="/opt/sminos"), \
                mock.patch.object(context.subprocess, "run", return_value=result):
            self.assertEqual(context.session_creator({"CLAUDE_CODE_SESSION_ID": "s"}),
                             ("@abcd1234", "abcd1234", "example"))
            self.assertEqual(context.session_creator({}), (None, None, None))


class UpIdleTest(UpBase):
    def test_up_writes_creation_price_and_project_to_the_host(self):
        self.ctx.creator_project = lambda: "example"
        self.up(ttl="3h")
        create = next(c for c in self.state()["calls"] if c["op"] == "create")
        import base64
        import re
        data = create["input"]["user_data"]
        texts = [base64.b64decode(v).decode() for v in re.findall(r"content: (\S+)", data)]
        d = descriptor.parse(next(t for t in texts if "DEVCLOUD_NAME=" in t))
        self.assertEqual((d.created, d.hourly_price, d.currency, d.creator_project),
                         (NOW, 0.1178, "EUR", "example"))


class HostIdleTest(DriverBase):
    def test_reads_only_over_tailnet_with_a_bounded_noninteractive_probe(self):
        ctx = self.make_ctx()
        host = hostctl.Host("dc-idle-abcd", "devcloud-main-123", "192.0.2.1")
        record = {"active_at": NOW - 3600, "checked_at": NOW, "noticed_at": None}
        self.remote.on("idle.json", out=json.dumps(record))
        with mock.patch.object(self.remote, "run", wraps=self.remote.run) as run:
            self.assertEqual(hostctl.idle(ctx, host, timeout=7), record)
        self.assertEqual(run.call_args.kwargs["timeout"], 7)
        self.assertLessEqual(run.call_args.kwargs["connect_timeout"], 7)
        call = self.remote.calls[-1]
        self.assertEqual(call["target"], host.name)

    def test_missing_malformed_or_unreachable_state_is_unknown(self):
        ctx = self.make_ctx()
        host = hostctl.Host("dc-idle-abcd", "alias", None)
        for code, text in ((1, ""), (255, ""), (0, "broken"), (0, "[]"),
                           (0, '{}'), (0, '{"active_at": "yesterday"}'),
                           (0, '{"active_at": NaN}'), (0, '{"active_at": true}')):
            with self.subTest(code=code, text=text):
                self.remote.rules.clear()
                self.remote.on("idle.json", code=code, out=text)
                self.assertIsNone(hostctl.idle(ctx, host))
