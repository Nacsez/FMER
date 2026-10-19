#!/usr/bin/env python3
"""Real C++ render and loopback HTTP integration. Run with the built host path.

This is host evidence only. Test durations and renderer timings do not qualify a
physical device, an audio driver, USB/BLE transport, or real-time deadlines.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import http.client
from http.server import HTTPServer
import importlib.util
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fmer_integration_sandbox", ROOT / "tools/sandbox.py")
sandbox = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sandbox)


def read_pcm(payload: bytes) -> tuple[int, array.array]:
    with wave.open(io.BytesIO(payload), "rb") as stream:
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2 or stream.getcomptype() != "NONE":
            raise AssertionError("Expected mono PCM16 WAV")
        rate = stream.getframerate()
        samples = array.array("h", stream.readframes(stream.getnframes()))
        if sys.byteorder != "little":
            samples.byteswap()
    return rate, samples


class HostIntegrationTests(unittest.TestCase):
    executable: Path

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fmer-integration-")
        self.directory = Path(self.temporary.name)
        self.counter = 0

    def tearDown(self):
        self.temporary.cleanup()

    def command(self, *args):
        return subprocess.run([str(self.executable), *map(str, args)], capture_output=True,
                              text=True, timeout=90, check=False)

    def render(self, scenario="note", extra=()):
        self.counter += 1
        wav_path = self.directory / f"render-{self.counter}.wav"
        report_path = self.directory / f"render-{self.counter}.json"
        result = self.command("--render", scenario, "--duration", "1", "--out", wav_path,
                              "--report", report_path, *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        payload = wav_path.read_bytes()
        rate, samples = read_pcm(payload)
        self.assertEqual(rate, 44100)
        self.assertEqual(len(samples), 88200)
        self.assertEqual(report["frames"], len(samples))
        self.assertEqual(report["sample_rate"], rate)
        self.assertFalse(report["hardware_access"])
        self.assertEqual(report["device_fidelity"], "unmeasured")
        self.assertTrue(any(samples), "Renderer returned silent audio")
        for metric in ("peak", "rms", "render_seconds"):
            self.assertTrue(math.isfinite(report[metric]), f"Non-finite metric: {metric}")
        self.assertGreater(report["rms"], 0)
        self.assertLessEqual(report["peak"], 1)
        self.assertEqual(report["rejected_events"], 0)
        self.assertEqual([event["frame"] for event in report["events"]],
                         sorted(event["frame"] for event in report["events"]))
        return payload, report, samples

    def test_parameter_registry_exposes_all_145_stable_numeric_fields(self):
        result = self.command("--parameters")
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(document["schema_version"], 1)
        parameters = document["parameters"]
        self.assertEqual(len(parameters), 145)
        self.assertEqual({entry["id"] for entry in parameters}, set(range(145)))
        for entry in parameters:
            self.assertTrue(entry["name"].strip())
            self.assertIn(entry["operator_number"], range(7))
            self.assertLessEqual(0, entry["minimum"])
            self.assertLessEqual(entry["minimum"], entry["default_value"])
            self.assertLessEqual(entry["default_value"], entry["maximum"])
            self.assertLessEqual(entry["maximum"], 127)
        self.assertEqual(parameters[134]["maximum"], 31, "DX7 algorithm has 32 choices")

    def test_all_scenarios_render_and_release_with_bounded_voice_stress(self):
        for scenario in ("note", "chord", "sequence", "arp", "midi", "stress"):
            with self.subTest(scenario=scenario):
                payload, report, samples = self.render(scenario)
                self.assertEqual(report["scenario"], scenario)
                self.assertEqual(report["engine"], "MSFA")
                self.assertLessEqual(report["peak_voices"], 12)
                self.assertEqual(report["active_voices_end"], 0)
                self.assertLessEqual(max(abs(value) for value in samples[-4410:]), 1,
                                     "INIT release must settle to PCM silence in final 100ms")
                if scenario == "stress":
                    self.assertEqual(report["peak_voices"], 12)
                    self.assertGreaterEqual(report["stolen_voices"], 12)
                print(f"MEASURE scenario={scenario} sha256={hashlib.sha256(payload).hexdigest()} "
                      f"peak_voices={report['peak_voices']} stolen={report['stolen_voices']} rms={report['rms']}")

    def test_known_init_a4_frequency_is_440_hz(self):
        _, _, samples = self.render(extra=("--note", "69"))
        # Ignore attack and release; count positive-going zero crossings in a
        # separately specified middle window, rather than trusting reported pitch.
        window = samples[6615:19845]  # 0.15..0.45 seconds.
        crossings = [index for index in range(1, len(window)) if window[index - 1] <= 0 < window[index]]
        self.assertGreater(len(crossings), 50)
        frequency = (len(crossings) - 1) * 44100 / (crossings[-1] - crossings[0])
        self.assertAlmostEqual(frequency, 440, delta=5)
        print(f"MEASURE INIT A4 zero-crossing frequency={frequency:.6f} Hz")

    def test_identical_arguments_produce_identical_pcm_and_event_trace(self):
        first, a, _ = self.render("sequence", ("--bpm", "137"))
        second, b, _ = self.render("sequence", ("--bpm", "137"))
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())
        self.assertEqual(a["events"], b["events"])
        self.assertEqual(a["patch_vced"], b["patch_vced"])

    def test_va_waveforms_use_actual_engine_and_differ(self):
        hashes = set()
        for waveform in ("sine", "saw", "square", "triangle"):
            with self.subTest(waveform=waveform):
                payload, report, samples = self.render(extra=("--engine", "va", "--wave", waveform, "--note", "69"))
                self.assertEqual(report["engine"], "FMER-VA")
                self.assertEqual(report["active_voices_end"], 0)
                self.assertLessEqual(max(abs(value) for value in samples[-4410:]), 1)
                hashes.add(hashlib.sha256(payload).hexdigest())
        self.assertEqual(len(hashes), 4, "Different VA oscillator controls must change rendered PCM")

    def test_sysex_import_roundtrip_and_parameter_override_reach_audio_core(self):
        original, original_report, _ = self.render(extra=("--note", "69"))
        voice = bytes(original_report["patch_vced"])
        self.assertEqual(len(voice), 155)
        sysex = bytes((0xf0, 0x43, 0, 0, 1, 0x1b)) + voice + bytes(((-sum(voice)) & 127, 0xf7))
        patch_path = self.directory / "synthetic-init.syx"
        patch_path.write_bytes(sysex)
        restored, report, _ = self.render(extra=("--note", "69", "--patch", patch_path, "--voice", "1"))
        self.assertEqual(original, restored)
        self.assertEqual(report["patch_vced"], original_report["patch_vced"])
        _, edited, _ = self.render(extra=("--set", "134=31", "--set", "144=25"))
        self.assertEqual(edited["patch_vced"][134], 31)
        self.assertEqual(edited["patch_vced"][144], 25)

    def test_invalid_cli_and_corrupt_sysex_refuse_without_outputs(self):
        malformed = self.directory / "malformed.syx"
        malformed.write_bytes(bytes(163))
        invalid_options = [
            ("--note", "128"), ("--duration", "0"), ("--duration", "1.5"),
            ("--set", "145=0"), ("--set", "134=32"), ("--set", "0=100"),
            ("--set", "bad"), ("--patch", malformed), ("--engine", "external"),
        ]
        for index, extra in enumerate(invalid_options):
            with self.subTest(extra=extra):
                wav_path = self.directory / f"invalid-{index}.wav"
                report_path = self.directory / f"invalid-{index}.json"
                result = self.command("--render", "note", "--out", wav_path, "--report", report_path, *extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stderr.strip())
                self.assertFalse(wav_path.exists())
                self.assertFalse(report_path.exists())

    def test_output_overwrite_and_alias_refused(self):
        existing = self.directory / "existing.wav"
        existing.write_bytes(b"preserve user data")
        report = self.directory / "new.json"
        result = self.command("--render", "note", "--out", existing, "--report", report)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(existing.read_bytes(), b"preserve user data")
        self.assertFalse(report.exists())
        absent = self.directory / "same-path"
        result = self.command("--render", "note", "--out", absent, "--report", absent)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(absent.exists())

    def test_loopback_http_serves_ui_real_render_audio_and_request_guards(self):
        with patch.object(sandbox, "OUTPUT", self.directory / "http"):
            server = HTTPServer(("127.0.0.1", 0), sandbox.handler_for(self.executable, self.directory / "library"))
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            thread.start()
            try:
                def request(method, path, body=None, headers=None):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=90)
                    try:
                        connection.request(method, path, body=body, headers=headers or {})
                        response = connection.getresponse()
                        return response.status, dict(response.getheaders()), response.read()
                    finally:
                        connection.close()
                status, headers, body = request("GET", "/")
                self.assertEqual(status, 200)
                self.assertIn("text/html", headers["Content-Type"])
                self.assertIn(b"FMER", body)
                status, _, body = request("GET", "/api/parameters")
                self.assertEqual(status, 200)
                self.assertEqual(len(json.loads(body)["parameters"]), 145)
                command = {"scenario": "note", "duration": 1, "note": 69, "edits": {"134": 31}}
                status, _, body = request("POST", "/api/render", json.dumps(command), {"Content-Type": "application/json"})
                self.assertEqual(status, 200, body)
                report = json.loads(body)
                self.assertFalse(report["hardware_access"])
                self.assertEqual(report["patch_vced"][134], 31)
                status, headers, audio = request("GET", report["audio_url"])
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], "audio/wav")
                self.assertEqual(hashlib.sha256(audio).hexdigest(), report["wav_sha256"])
                rate, samples = read_pcm(audio)
                self.assertEqual(rate, 44100)
                self.assertTrue(any(samples))
                status, _, body = request("GET", "/api/library")
                self.assertEqual(status, 200, body)
                self.assertEqual(json.loads(body)["revision"], 0)
                preset = {"name": "HTTP retained sound", "vced": report["patch_vced"],
                          "settings": {"effects": {"delay": 0.25}, "engine": "fm"}}
                status, _, body = request("POST", "/api/library", json.dumps({"action": "save", "revision": 0, "slot": 127, "preset": preset}))
                self.assertEqual(status, 200, body)
                self.assertEqual(json.loads(body)["slots"][127], preset)
                # Restart from disk; this is not just a browser memory assertion.
                reopened = sandbox.library.PatchLibrary(self.directory / "library", self.executable)
                self.assertEqual(reopened.load(127)["preset"], preset)
                status, _, body = request("POST", "/api/library", json.dumps({"action": "save", "revision": 0, "slot": 127, "preset": preset}))
                self.assertEqual(status, 409, body)
                status, _, body = request("POST", "/api/library", json.dumps({"action": "export", "slot": 127}))
                self.assertEqual(status, 200, body)
                exported = json.loads(body)
                self.assertTrue(exported["losses"])
                status, _, body = request("POST", "/api/patch", json.dumps({"sysex": exported["sysex"]}))
                self.assertEqual(status, 200, body)
                self.assertEqual(json.loads(body)["voices"][0]["vced"], report["patch_vced"])
                status, _, body = request("POST", "/api/telemetry", json.dumps({"event": "test_action", "details": {"control": "delay"}, "session_id": "integration"}))
                self.assertEqual(status, 200, body)
                self.assertIn('test_action', (self.directory / "http/events.jsonl").read_text())
                status, _, body = request("POST", "/api/library", '{"action":"undo","revision":1}')
                self.assertEqual(status, 200, body)
                self.assertIsNone(json.loads(body)["slots"][127])
                for invalid in (b"{", b"[]", b'{"scenario":[]}'):
                    with self.subTest(invalid=invalid):
                        status, _, body = request("POST", "/api/render", invalid)
                        self.assertEqual(status, 400, body)
                        self.assertIn("error", json.loads(body))
                status, _, _ = request("POST", "/api/render", b"{}", {"Origin": "https://other.example"})
                self.assertEqual(status, 403)
                status, _, _ = request("GET", "/", headers={"Host": "other.example"})
                self.assertEqual(status, 403)
                status, _, _ = request("POST", "/api/render", b"{}", {"Content-Length": "65537"})
                self.assertEqual(status, 400)
                status, _, _ = request("GET", "/audio/../CMakeLists.txt")
                self.assertEqual(status, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())

    def test_editable_pattern_preserves_chords_ties_rests_and_hidden_steps(self):
        pattern = {"length": 4, "channel": 3, "steps": [
            {"notes": [{"pitch": 60, "velocity": 88}, {"pitch": 67, "velocity": 77}], "gate": 50},
            {"notes": [], "tie": True, "gate": 100},
            {"notes": [], "gate": 75},
            {"notes": [{"pitch": 72, "velocity": 66}], "gate": 50},
            {"notes": [{"pitch": 90, "velocity": 99}], "gate": 75}]}
        result = sandbox.render_request({"scenario": "sequence", "duration": 1, "pattern": pattern}, self.executable, self.directory)
        notes = [e for e in result["events"] if e["type"] == "NoteOn"]
        self.assertEqual([e["data1"] for e in notes], [60, 67, 72, 60, 67, 72])
        self.assertEqual([e["data2"] for e in notes[:3]], [88, 77, 66])
        self.assertTrue(all(e["channel"] == 3 for e in notes))
        offs = [e for e in result["events"] if e["type"] == "NoteOff"]
        self.assertEqual(offs[0]["frame"], 11025)  # Tie holds chord through two steps.
        self.assertEqual(result["active_voices_end"], 0)
        path = self.directory / result["request_id"] / "pattern.txt"
        self.assertIn("90 99", path.read_text())

    def test_all_effects_reach_audio_and_report_clipping_and_tails(self):
        dry, _, _ = self.render()
        for settings in ({"drive": .5}, {"chorus": .5}, {"phaser": .5}, {"delay": .5}, {"reverb": .5}, {"cutoff_hz": 100}):
            result = sandbox.render_request({"duration": 1, "effects": settings}, self.executable, self.directory)
            wav = self.directory / result["request_id"] / "render.wav"
            self.assertNotEqual(wav.read_bytes(), dry, settings)
            self.assertEqual(result["fx_sanitized_samples"], 0)
            self.assertLessEqual(result["peak"], 1)
        long_tail = sandbox.render_request({"duration": 1, "tail": 3, "effects": {"delay": .5, "feedback": .85}}, self.executable, self.directory)
        self.assertEqual(long_tail["tail_frames"], 132300)
        self.assertTrue(long_tail["tail_truncated"])

    def test_arp_rate_swing_seed_and_latch_reach_real_renderer(self):
        def run(settings):
            return sandbox.render_request({"scenario": "arp", "duration": 1, "arp": settings}, self.executable, self.directory)
        a = run({"order": "random", "seed": 123, "swing": 65})
        b = run({"order": "random", "seed": 123, "swing": 65})
        self.assertEqual(a["wav_sha256"], b["wav_sha256"])
        self.assertEqual(a["events"], b["events"])
        short = run({"held_release": True, "latch": False})
        held = run({"held_release": True, "latch": True})
        note_frames = lambda r: [e["frame"] for e in r["events"] if e["type"] == "NoteOn"]
        self.assertTrue(all(frame < 22050 for frame in note_frames(short)))
        self.assertTrue(any(frame > 22050 for frame in note_frames(held)))
        repeat = run({"order": "repeat", "octaves": 1, "rate": 8, "triplet": True, "swing": 75})
        self.assertEqual(len([f for f in note_frames(repeat) if f == 0]), 3)

    def test_raw_working_voice_renders_same_as_codec_export(self):
        dry, report, _ = self.render(extra=("--set", "100=75"))
        result = sandbox.render_request({"duration": 1, "vced": report["patch_vced"]}, self.executable, self.directory)
        self.assertEqual(result["wav_sha256"], hashlib.sha256(dry).hexdigest())

    def test_largest_exposed_arp_score_has_trace_capacity_and_releases(self):
        result = sandbox.render_request({"scenario": "arp", "duration": 20, "bpm": 300,
            "arp": {"order": "repeat", "octaves": 4, "rate": 32, "triplet": True}},
            self.executable, self.directory)
        self.assertGreater(len(result["events"]), 16384)
        self.assertLessEqual(len(result["events"]), 32768)
        self.assertEqual(result["active_voices_end"], 0)
        self.assertEqual(result["rejected_events"], 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    HostIntegrationTests.executable = args.executable.resolve()
    if not HostIntegrationTests.executable.is_file():
        parser.error("Compiled host executable does not exist")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HostIntegrationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
