"""Offline input/refusal regressions; these checks require no compiled executable."""
import base64
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("fmer_sandbox_tests", Path(__file__).resolve().parents[1] / "tools/sandbox.py")
sandbox = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sandbox)


class SandboxValidationTests(unittest.TestCase):
    def test_invalid_requests_cannot_launch_process_or_create_artifacts(self):
        invalid = [
            [], {"scenario": []}, {"scenario": "unknown"}, {"note": True},
            {"note": 128}, {"velocity": 0}, {"bpm": 19}, {"duration": 1.5},
            {"duration": 21}, {"engine": "external"}, {"wave": "unsupported-wave"},
            {"cutoff": 19}, {"edits": []}, {"edits": {"145": 0}},
            {"edits": {"0": True}}, {"edits": {"../0": 0}},
            {"sysex": "%%%"}, {"sysex": base64.b64encode(b"bad length").decode()},
            {"voice": 0}, {"voice": 33},
            {"effects": {"feedback": .9}}, {"effects": {"reverb": float("nan")}},
            {"effects": {"cutoff_hz": 1}}, {"arp": {"rate": 3}}, {"arp": {"swing": 80}},
            {"pattern": {"length": 2, "steps": []}}, {"vced": [0] * 154},
            {"tail": 11}, {"unimplemented": True},
            {"mono": 1}, {"glide": []}, {"glide": {"mode": 3}},
            {"glide": {"time_ms": 2001}}, {"glide": {"curve": True}},
            {"glide": {"time_ms": 1.5}}, {"glide": {"unknown": 0}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "absent-output"
            for data in invalid:
                with self.subTest(data=data), patch.object(sandbox.subprocess, "run") as process:
                    with self.assertRaises(ValueError):
                        sandbox.render_request(data, Path("not-invoked.exe"), output=output)
                    process.assert_not_called()
                    self.assertFalse(output.exists())

    def test_control_and_patch_arguments_survive_renderer_refusal_with_evidence(self):
        payload = bytes(range(128)) + bytes(35)
        data = {"scenario": "arp", "note": 69, "velocity": 88, "bpm": 137,
                "duration": 2, "engine": "va", "wave": "square", "cutoff": 1234,
                "edits": {"134": 7, "121": 88}, "voice": 7,
                "mono": True, "glide": {"mode": 2, "time_ms": 430, "curve": 1},
                "sysex": base64.b64encode(payload).decode("ascii")}
        failed = subprocess.CompletedProcess([], 2, "diagnostic stdout", "fixture decode rejected")
        with tempfile.TemporaryDirectory() as directory, patch.object(sandbox.subprocess, "run", return_value=failed) as process:
            output = Path(directory)
            with self.assertRaisesRegex(ValueError, "fixture decode rejected"):
                sandbox.render_request(data, Path("test-renderer.exe"), output=output)
            args = process.call_args.args[0]
            for flag, value in (("--render", "arp"), ("--note", "69"), ("--velocity", "88"),
                                ("--bpm", "137"), ("--duration", "2"), ("--engine", "va"),
                                ("--wave", "square"), ("--cutoff", "1234"), ("--voice", "7"),
                                ("--mono", "1"), ("--glide-mode", "2"), ("--glide-ms", "430"), ("--glide-curve", "1")):
                self.assertEqual(args[args.index(flag) + 1], value)
            self.assertIn("134=7", args)
            self.assertIn("121=88", args)
            self.assertEqual(Path(args[args.index("--patch") + 1]).read_bytes(), payload)
            reports = list(output.glob("*/process.json"))
            self.assertEqual(len(reports), 1)
            evidence = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(evidence["argv"], args)
            self.assertEqual(evidence["input"], data)
            self.assertEqual(evidence["returncode"], 2)
            self.assertEqual(evidence["stderr"], "fixture decode rejected")
            self.assertFalse(evidence["hardware_access"])
            self.assertFalse(list(output.glob("*/result.json")))

    def test_integer_bounds_accept_edges_but_not_boolean_or_numeric_text(self):
        self.assertEqual(sandbox.bounded_int(0, 0, 127, "note"), 0)
        self.assertEqual(sandbox.bounded_int(127, 0, 127, "note"), 127)
        for value in (True, False, "60", 60.0, -1, 128, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sandbox.bounded_int(value, 0, 127, "note")

    def test_timeout_retains_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sandbox.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixture", 60)):
            with self.assertRaises(subprocess.TimeoutExpired):
                sandbox.render_request({}, Path("fixture.exe"), Path(directory))
            files = list(Path(directory).glob("*/process.json"))
            self.assertEqual(len(files), 1)
            record = json.loads(files[0].read_text())
            self.assertIsNone(record["returncode"])
            self.assertIn("timed out", record["stderr"])

    def test_diagnostic_failure_cannot_misreport_a_successful_mutation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "open", side_effect=OSError("full disk")), contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertFalse(sandbox.journal("request_complete", output=Path(directory), revision=4))
            self.assertIn("full disk", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
