"""Passive inventory parsing and privacy regressions: fixtures only, no OS query."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "hardware_inventory_tests", Path(__file__).resolve().parents[1] / "tools/hardware_inventory.py")
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def node(name="FM-1 Midi", instance=r"USB\VID_4C4A&PID_C755&MI_04\PRIVATE123&0000"):
    return {"FriendlyName": name, "InstanceId": instance, "Class": "MEDIA", "Status": "OK"}


class HardwareInventoryTests(unittest.TestCase):
    def test_reported_normal_update_and_ambiguous_names(self):
        rows = [node(), node("ota-FM-1", r"USB\VID_4D4A&PID_4155\SECRET456"),
                node("FM_1 clone", r"USB\VID_1234&PID_5678\SECRET789"),
                node("M-VAVE", r"SWD\MMDEVAPI\PRIVATEOTHER"),
                node("Unrelated keyboard", r"USB\VID_1111&PID_2222\OTHER"),
                node("FM-10 device", r"USB\VID_1111&PID_2222\OTHER")]
        candidates = inventory.parse_envelope({"status": "ok", "devices": rows})
        self.assertEqual(len(candidates), 4)
        self.assertEqual([c["identity_hint"] for c in candidates],
                         ["reported_normal", "reported_update", "name_only_ambiguous", "name_only_ambiguous"])
        self.assertEqual(candidates[0]["interface"], "04")
        self.assertEqual(candidates[0]["vid"], "4C4A")
        self.assertEqual(candidates[1]["pid"], "4155")
        self.assertFalse(any(c["identity_confirmed"] for c in candidates))
        serialized = json.dumps(candidates)
        for private in ("PRIVATE", "SECRET", "InstanceId", "instance_id"):
            self.assertNotIn(private, serialized)

    def test_serial_component_cannot_spoof_reported_ids(self):
        self.assertEqual(inventory.parse_envelope({"status": "ok", "devices": [
            node("unrelated", r"USB\VID_1111&PID_2222\VID_4C4A&PID_C755")]}), [])

    def test_error_identifiers_redacted_and_query_failure_is_not_empty_success(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "input.json"
            fixture.write_text(json.dumps({"status": "error", "devices": [],
                "error": "Access denied: USB\\VID_4C4A&PID_C755\\SECRET123&0000"}), encoding="utf-8")
            with patch.object(inventory, "query_windows") as query:
                result = inventory.collect(fixture=fixture)
            query.assert_not_called()
            self.assertEqual(result["status"], "error")
            self.assertIn("Access denied", result["error"]["message"])
            self.assertIn("[redacted]", result["error"]["message"])
            self.assertNotIn("SECRET123", json.dumps(result))
            self.assertIn("unknown", result["observation"])

    def test_error_redaction_handles_doubled_slashes_and_complete_suffix(self):
        for raw in (r"USB\VID_4C4A&PID_C755\SERIAL&01\SUFFIX",
                    r"HID\\VID_1234&PID_5678\\SERIAL&01",
                    "USB\\VID_4C4A&PID_C755\\SERIAL WITH SPACES"):
            redacted = inventory.redact("Failure: " + raw)
            self.assertIn("Failure:", redacted)
            self.assertIn("[redacted]", redacted)
            self.assertNotIn("SERIAL", redacted)
            self.assertNotIn("SUFFIX", redacted)

    def test_serials_in_retained_text_are_also_redacted(self):
        row = node(r"FM-1 USB\VID_4C4A&PID_C755\PRIVATEVALUE")
        result = inventory.parse_envelope({"status": "ok", "devices": [row]})
        self.assertNotIn("PRIVATEVALUE", json.dumps(result))

    def test_malformed_envelopes_and_rows_are_refused(self):
        malformed = [None, [], {}, {"status": "ok", "devices": {}},
                     {"status": "ok", "devices": [], "error": "inconsistent"},
                     {"status": "ok", "devices": [42]},
                     {"status": "ok", "devices": [{"FriendlyName": "FM-1"}]},
                     {"status": "ok", "devices": [dict(node(), InstanceId=1)]},
                     {"status": "ok", "devices": [dict(node(), FriendlyName="bad\nname")]},
                     {"status": "error", "devices": [], "error": None},
                     {"status": "unknown", "devices": []}]
        for payload in malformed:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                inventory.parse_envelope(payload)

    def test_fixture_observations_are_unverified_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "input.json"
            fixture.write_text(json.dumps({"status": "ok", "devices": []}), encoding="utf-8")
            with patch.object(inventory, "query_windows") as query:
                result = inventory.collect(fixture=fixture, unit_label="Spare B",
                                           firmware_noted=" V15 / screen observation ")
            query.assert_not_called()
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["owner_observations"]["firmware_noted"], " V15 / screen observation ")
            self.assertEqual(result["owner_observations"]["classification"], "owner_noted_unverified")
            self.assertEqual(result["hardware_access"], "none_fixture")
            self.assertFalse(result["device_opened"])
            self.assertFalse(result["device_writes"])
            self.assertIn("absence is not established", result["observation"])

    def test_os_query_error_and_timeout_are_retained_without_device_open(self):
        for error in (OSError("Access is denied"), subprocess.TimeoutExpired("sensitive command", 30)):
            with patch.object(inventory, "query_windows", side_effect=error):
                report = inventory.collect()
            self.assertEqual(report["status"], "error")
            self.assertEqual(report["hardware_access"], "passive_os_enumeration")
            self.assertFalse(report["device_opened"])
            self.assertNotIn("sensitive command", json.dumps(report))

    def test_cli_failure_writes_evidence_nonzero_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture, out = Path(directory) / "input.json", Path(directory) / "report.json"
            fixture.write_text("private malformed content", encoding="utf-8")
            args = ["--input", str(fixture), "--out", str(out)]
            with patch.object(inventory, "query_windows") as query, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(inventory.main(args), 1)
            query.assert_not_called()
            prior = out.read_bytes()
            self.assertNotIn(b"private malformed content", prior)
            self.assertEqual(json.loads(prior)["status"], "error")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(inventory.main(args), 2)
            self.assertEqual(out.read_bytes(), prior)

    def test_success_cli_and_unique_default_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "input.json"
            fixture.write_text(json.dumps({"status": "ok", "devices": [node()]}), encoding="utf-8")
            with patch.object(inventory, "ROOT", Path(directory)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(inventory.main(["--input", str(fixture)]), 0)
                self.assertEqual(inventory.main(["--input", str(fixture)]), 0)
            outputs = list((Path(directory) / "artifacts/hardware-inventory").glob("*/report.json"))
            self.assertEqual(len(outputs), 2)
            for out in outputs:
                self.assertEqual(json.loads(out.read_text())["candidate_count"], 1)


if __name__ == "__main__":
    unittest.main()
