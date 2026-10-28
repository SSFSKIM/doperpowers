"""Slow activity probes, checkout scans and message delivery cannot hold departure's lock."""
import json
import threading
from unittest import mock

import _path  # noqa: F401
from devcloudlib import idle, lease, notices
from test_idle import IdleBase, DAY, NOW
from test_lease import BASE


class NoticeLockingTest(IdleBase):
    def setUp(self):
        super().setUp()
        self.desc = self.root / "boot.env"
        self.desc.write_text(BASE + f"DEVCLOUD_EXPIRES={NOW + 60}\n")
        self.state.write_text(json.dumps({"active_at": NOW - 3 * DAY, "checked_at": NOW - 300,
                                         "noticed_at": None}))
        patch = mock.patch.object(idle, "STATE", self.state)
        patch.start()
        self.addCleanup(patch.stop)
        self.clock = NOW
        self.started = []
        self.paths = dict(desc_path=self.desc, lock_path=self.root / "lock", state_path=self.root / "lease.json",
                          status_path=self.root / "status.json")

    def run_tick(self, **kw):
        options = dict(now=lambda: self.clock, active=lambda unit: False,
                       start=lambda unit, argv: self.started.append(unit), say=lambda text: None)
        options.update(kw)
        return lease.tick(self.user, **self.paths, **options)

    def assert_unlocked(self):
        with lease.locked(path=self.paths["lock_path"], timeout=0.01):
            pass

    def test_expired_lease_starts_departure_before_any_activity_or_notice_work(self):
        self.clock = NOW + 60
        with mock.patch.object(idle, "active", side_effect=AssertionError("probed after expiry")), \
                mock.patch.object(lease, "unpushed", side_effect=AssertionError("scanned after expiry")):
            self.assertEqual(self.run_tick(), 0)
        self.assertEqual(self.started, [lease.DEPART_UNIT])

    def test_expiry_during_activity_probe_is_rechecked_before_reserving_or_sending(self):
        def probe(user, since):
            self.assert_unlocked()
            self.clock += 240
            return False
        with mock.patch.object(idle, "active", side_effect=probe), \
                mock.patch.object(lease, "unpushed", side_effect=AssertionError("scanned after expiry")):
            self.assertEqual(self.run_tick(), 0)
        self.assertEqual(self.started, [lease.DEPART_UNIT])
        self.assertIsNone(self.read()["noticed_at"])

    def test_scan_and_both_deliveries_run_unlocked_after_their_reservations(self):
        delivered = []
        def scan(user):
            self.assert_unlocked()
            self.assertEqual(json.loads(self.paths["state_path"].read_text())["warned_for"], NOW + 60)
            self.assertEqual(self.read()["noticed_at"], NOW)
            return []
        def send(user, d, text, **kw):
            self.assert_unlocked()
            delivered.append(text)
        with mock.patch.object(idle, "active", return_value=False), \
                mock.patch.object(lease, "unpushed", side_effect=scan), \
                mock.patch.object(notices, "deliver", side_effect=send):
            self.assertEqual(self.run_tick(), 0)
        self.assertEqual(len(delivered), 2)
        self.assertTrue(any("lease ends" in text and "idle" not in text for text in delivered))
        self.assertTrue(any("idle" in text for text in delivered))

    def test_a_concurrent_expiry_tick_can_depart_while_delivery_is_blocked(self):
        entered, release, departed = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def send(*args, **kw):
            entered.set()
            if not release.wait(3):
                raise AssertionError("delivery was not released")
        def run(**kw):
            try:
                self.run_tick(**kw)
            except BaseException as error:
                errors.append(error)
        with mock.patch.object(idle, "active", return_value=False), \
                mock.patch.object(lease, "unpushed", return_value=[]), \
                mock.patch.object(notices, "deliver", side_effect=send):
            first = threading.Thread(target=run)
            first.start()
            second = None
            try:
                self.assertTrue(entered.wait(1), "the notice did not reach delivery")
                self.clock += 240
                second = threading.Thread(target=lambda: run(start=lambda *args: departed.set()))
                second.start()
                self.assertTrue(departed.wait(1), "slow delivery blocked the departure decision")
            finally:
                release.set()
                first.join(4)
                if second:
                    second.join(4)
        self.assertFalse(first.is_alive())
        self.assertEqual(errors, [])

    def test_a_slow_send_does_not_leave_the_tick_with_a_stale_lease_decision(self):
        def send(*args, **kw):
            self.clock = NOW + 240
        with mock.patch.object(idle, "active", return_value=False), \
                mock.patch.object(lease, "unpushed", return_value=[]), \
                mock.patch.object(notices, "deliver", side_effect=send):
            self.assertEqual(self.run_tick(), 0)
        self.assertEqual(self.started, [lease.DEPART_UNIT])

    def test_a_lease_renewed_during_activity_probe_is_reread(self):
        def probe(user, since):
            with lease.locked(path=self.paths["lock_path"], timeout=0.01):
                self.desc.write_text(BASE + f"DEVCLOUD_EXPIRES={NOW + 600}\n")
            self.clock += 240
            return False
        with mock.patch.object(idle, "active", side_effect=probe), \
                mock.patch.object(lease, "unpushed", return_value=[]), \
                mock.patch.object(notices, "deliver") as delivery:
            self.assertEqual(self.run_tick(), 0)
        self.assertEqual(self.started, [])
        self.assertEqual(json.loads(self.paths["state_path"].read_text())["warned_for"], NOW + 600)
        self.assertTrue(all(call.args[1].expires == NOW + 600 for call in delivery.call_args_list))

    def test_overlapping_observations_reserve_only_one_notice(self):
        first = idle.observe(self.user, self.d, path=self.state, now=lambda: NOW,
                             activity=lambda *args: False)
        second = idle.observe(self.user, self.d, path=self.state, now=lambda: NOW,
                              activity=lambda *args: False)
        with lease.locked(path=self.paths["lock_path"]):
            self.assertIsNotNone(idle.reserve(self.d, first, path=self.state, now=lambda: NOW))
            self.assertIsNone(idle.reserve(self.d, second, path=self.state, now=lambda: NOW))
        self.assertEqual(self.read()["noticed_at"], NOW)

    def test_a_slow_activity_scan_does_not_hide_writes_after_its_start(self):
        def probe(user, since):
            self.clock += 30
            return False
        observed = idle.observe(self.user, self.d, path=self.state, now=lambda: self.clock, activity=probe)
        idle.reserve(self.d, observed, path=self.state, now=lambda: self.clock)
        self.assertEqual(self.read()["checked_at"], NOW)
