import unittest
from unittest import mock

from scripts.automation import probe_yoda_resolver_telemetry as probe


class ResolverTelemetryProbeTests(unittest.TestCase):
    def test_test_probe_payload_has_complete_explicit_provenance(self):
        payload = probe.build_request_payload(
            question="SG-0128 test classification",
            depth=4,
            mode="test",
            pair_id="sg-0128-live-test-1",
        )

        self.assertEqual(payload["environment"], "test")
        self.assertTrue(payload["synthetic"])
        self.assertTrue(payload["test_run"])
        self.assertEqual(payload["pair_id"], "sg-0128-live-test-1")

    def test_production_control_payload_is_explicitly_production_shaped(self):
        payload = probe.build_request_payload(
            question="SG-0128 production classification control",
            depth=4,
            mode="production",
            pair_id="sg-0128-live-production-1",
        )

        self.assertEqual(payload["environment"], "production")
        self.assertFalse(payload["synthetic"])
        self.assertFalse(payload["test_run"])
        self.assertEqual(payload["pair_id"], "sg-0128-live-production-1")

    def test_probe_requires_a_stable_pair_id(self):
        with self.assertRaisesRegex(ValueError, "pair_id"):
            probe.build_request_payload(
                question="missing pair",
                depth=4,
                mode="test",
                pair_id="",
            )

    def test_authoritative_gbrain_readback_parses_tool_output(self):
        completed = mock.Mock()
        completed.stdout = 'notice\n{"events":[{"event_id":"evt-1","metadata":"{\\"environment\\":\\"test\\"}"}]}'
        with mock.patch("subprocess.run", return_value=completed) as run:
            events = probe.read_authoritative_events(limit=7)

        self.assertEqual(events[0]["event_id"], "evt-1")
        run.assert_called_once_with(
            ["gbrain", "call", "resolver_events_list", '{"limit": 7, "producer": "stargraph"}'],
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
