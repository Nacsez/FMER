"""Companion persistence fault/refusal tests, plus opt-in actual host codec tests.

Set FMER_HOST_EXE to the newly built executable to exercise its CLI as well.
Unit persistence tests run without a compiler or a pre-existing user library.
"""
import base64
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("fmer_library_tests", Path(__file__).resolve().parents[1] / "tools/library.py")
library = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(library)


def voice(seed=0):
    result = [0] * 155
    result[0] = seed
    result[145:] = list(b"TEST VOICE")
    return result


def preset(name="My voice", seed=0):
    return {"name": name, "vced": voice(seed), "settings": {
        "scenario": "sequence", "engine": "va", "wave": "triangle", "cutoff": 2311,
        "note": 61, "velocity": 90, "bpm": 137, "duration": 4, "tail": 3,
        "effects": {"drive": .15, "delay": .3, "delay_ms": 267, "feedback": .4,
                    "order": ["drive", "filter", "chorus", "phaser", "delay", "reverb"]},
        "arp": {"order": "random", "seed": 82, "octaves": 3, "latch": True,
                "rate": 16, "triplet": False, "swing": 62, "held_release": True},
        "pattern": {"length": 2, "channel": 1, "steps": [
            {"notes": [{"pitch": 61, "velocity": 94}], "gate": 100, "tie": False},
            {"notes": [], "gate": 75, "tie": True},
            {"notes": [{"pitch": 73, "velocity": 70}], "gate": 52, "tie": False}]}}}


class FakeCodec:
    """Persistence isolation; real field/framing tests use the actual executable."""
    def __init__(self):
        self.validated = []
        self.imported = [{"name": "BANK VOICE", "vced": voice(i)} for i in range(32)]

    def validate(self, voices):
        self.validated.extend(deepcopy(voices))
        if any(v[0] > 99 for v in voices):
            raise ValueError("shared codec: VCED byte 0 exceeds 99")

    def decode(self, payload):
        return deepcopy(self.imported if len(payload) == 4104 else self.imported[:1])

    def encode(self, voices):
        self.validate(voices)
        if len(voices) == 1:
            body = bytes(voices[0])
            return bytes([0xf0, 0x43, 0, 0, 1, 27]) + body + bytes([(-sum(body)) & 127, 0xf7])
        return bytes(4104)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "library"
        self.codec = FakeCodec()
        self.lib = library.PatchLibrary(self.root, Path("unused.exe"), codec=self.codec)

    def tearDown(self):
        self.temporary.cleanup()

    def test_empty_read_does_not_create_persistent_state(self):
        state = self.lib.snapshot()
        self.assertEqual(state["revision"], 0)
        self.assertEqual(state["slots"], [None] * 128)
        self.assertFalse(state["can_undo"])
        self.assertFalse(self.root.exists())

    def test_save_load_restart_and_audition_preserve_native_fields(self):
        original = preset()
        self.assertEqual(self.lib.save(127, original, 0)["revision"], 1)
        original["vced"][0] = 99
        restarted = library.PatchLibrary(self.root, Path("unused.exe"), codec=self.codec)
        before = self.lib.path.read_bytes()
        loaded = restarted.load(127)
        self.assertEqual(loaded["preset"], preset())
        self.assertEqual(self.lib.path.read_bytes(), before)
        self.assertTrue(self.codec.validated)

    def test_stale_revision_refuses_without_changing_files(self):
        self.lib.save(0, preset(), 0)
        before = self.lib.path.read_bytes()
        with self.assertRaises(library.LibraryConflict):
            self.lib.save(0, preset("Wrong overwrite"), 0)
        self.assertEqual(self.lib.path.read_bytes(), before)
        self.assertFalse(self.lib.previous_path.exists())

    def test_all_128_slots_round_trip_without_clipping_or_fill(self):
        state = self.lib._empty()
        state["slots"] = [preset(f"Slot {i + 1}", i % 100) for i in range(128)]
        restored = self.lib.restore(self.lib._envelope(state), 0)
        self.assertEqual(restored["slots"], state["slots"])
        self.assertEqual(self.lib.backup()["backup"]["payload"]["slots"], state["slots"])

    def test_undo_is_one_level_and_revision_keeps_increasing(self):
        self.lib.save(0, preset("First"), 0)
        self.lib.save(0, preset("Second"), 1)
        undone = self.lib.undo(2)
        self.assertEqual(undone["revision"], 3)
        self.assertEqual(undone["slots"][0]["name"], "First")
        self.assertFalse(undone["can_undo"])
        with self.assertRaisesRegex(ValueError, "No library change"):
            self.lib.undo(3)

    def test_delete_and_undo_restore_exact_preset(self):
        self.lib.save(4, preset(), 0)
        self.assertIsNone(self.lib.delete(4, 1)["slots"][4])
        self.assertEqual(self.lib.undo(2)["slots"][4], preset())
        with self.assertRaises(ValueError):
            self.lib.delete(5, 3)

    def test_previous_backup_is_byte_identical_last_good_file(self):
        self.lib.save(0, preset(), 0)
        before = self.lib.path.read_bytes()
        self.lib.save(1, preset("Next"), 1)
        self.assertEqual(self.lib.previous_path.read_bytes(), before)
        self.assertFalse(list(self.root.glob("*.tmp")))
        self.assertFalse((self.root / "library.lock").exists())

    def test_restore_is_atomic_undoable_and_does_not_rewind_revision(self):
        self.lib.save(0, preset(), 0)
        backup = self.lib.backup()["backup"]
        self.lib.save(1, preset("Next"), 1)
        self.assertEqual(self.lib.restore(backup, 2)["revision"], 3)
        self.assertIsNone(self.lib.snapshot()["slots"][1])
        self.assertEqual(self.lib.undo(3)["slots"][1]["name"], "Next")

    def test_corrupt_backup_and_unknown_version_are_refused_without_mutation(self):
        self.lib.save(0, preset(), 0)
        original = self.lib.path.read_bytes()
        backup = self.lib.backup()["backup"]
        backup["payload"]["slots"][0]["vced"][0] = 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.lib.restore(backup, 1)
        state = self.lib._empty()
        state["version"] = 99
        with self.assertRaisesRegex(ValueError, "format/version"):
            self.lib.restore(self.lib._envelope(state), 1)
        self.assertEqual(self.lib.path.read_bytes(), original)

    def test_truncated_primary_never_reinitializes_or_overwrites(self):
        self.lib.save(0, preset(), 0)
        broken = self.lib.path.read_bytes()[:80]
        self.lib.path.write_bytes(broken)
        for operation in (self.lib.snapshot, lambda: self.lib.save(1, preset(), 1),
                          lambda: self.lib.restore(self.lib._envelope(self.lib._empty()), 1)):
            with self.assertRaises(ValueError):
                operation()
            self.assertEqual(self.lib.path.read_bytes(), broken)

    def test_interrupted_replace_preserves_primary_and_backup(self):
        self.lib.save(0, preset(), 0)
        before = self.lib.path.read_bytes()
        real_replace = library.os.replace
        def fail_primary(source, target):
            if Path(target) == self.lib.path:
                raise OSError("simulated interrupted primary replace")
            real_replace(source, target)
        with patch.object(library.os, "replace", side_effect=fail_primary):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.lib.save(1, preset(), 1)
        self.assertEqual(self.lib.path.read_bytes(), before)
        self.assertEqual(self.lib.previous_path.read_bytes(), before)
        self.assertFalse(list(self.root.glob("*.tmp")))
        self.assertEqual(self.lib.snapshot()["revision"], 1)

    def test_fsync_failure_preserves_primary_and_cleans_lock(self):
        self.lib.save(0, preset(), 0)
        before = self.lib.path.read_bytes()
        with patch.object(library.os, "fsync", side_effect=OSError("disk refused sync")):
            with self.assertRaises(OSError):
                self.lib.save(1, preset(), 1)
        self.assertEqual(self.lib.path.read_bytes(), before)
        self.assertFalse((self.root / "library.lock").exists())

    def test_cross_process_lock_refuses_and_preserves_owner_lock(self):
        self.root.mkdir()
        lock = self.root / "library.lock"
        lock.write_text('{"pid":9999}', encoding="utf-8")
        with self.assertRaises(library.LibraryConflict):
            self.lib.save(0, preset(), 0)
        self.assertEqual(lock.read_text(), '{"pid":9999}')
        self.assertFalse(self.lib.path.exists())

    def test_missing_primary_with_retained_backup_requires_explicit_recovery(self):
        self.lib.save(0, preset(), 0)
        self.lib.save(1, preset(), 1)
        self.lib.path.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.lib.snapshot()

    def test_bank_import_bounds_conflicts_and_whole_bank_undo(self):
        payload = base64.b64encode(bytes(4104)).decode()
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.lib.import_bank(payload, 97, 0)
        self.assertFalse(self.lib.path.exists())
        state = self.lib.import_bank(payload, 96, 0)
        self.assertEqual(sum(x is not None for x in state["slots"]), 32)
        before = self.lib.path.read_bytes()
        with self.assertRaises(library.LibraryConflict):
            self.lib.import_bank(payload, 96, 1)
        self.assertEqual(self.lib.path.read_bytes(), before)
        self.lib.import_bank(payload, 96, 1, overwrite=True)
        self.assertEqual(self.lib.undo(2)["slots"], state["slots"])

    def test_export_warns_about_native_loss_and_refuses_empty_bank(self):
        self.lib.save(0, preset(), 0)
        before = self.lib.path.read_bytes()
        result = self.lib.export(slot=0)
        self.assertEqual(len(base64.b64decode(result["sysex"])), 163)
        self.assertIn("VA", " ".join(result["losses"]))
        with self.assertRaisesRegex(ValueError, "occupied"):
            self.lib.export(start_slot=0, count=32)
        self.assertEqual(self.lib.path.read_bytes(), before)
        self.assertFalse(result["hardware_access"])

    def test_working_voice_export_does_not_save_library(self):
        exported = self.lib.dispatch({"action": "export_voice", "vced": voice()})
        self.assertEqual(len(base64.b64decode(exported["sysex"])), 163)
        self.assertFalse(self.root.exists())

    def test_malformed_state_request_or_settings_fail_closed(self):
        invalid = [[], {}, {"action": []}, {"action": "save"}, {"action": "backup", "mystery": 1}]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.lib.dispatch(item)
        for invalid_settings in ({"mystery": 1}, {"effects": {"delay": float("nan")}},
                                 {"arp": {"rate": True}}, {"effects": {"order": ["filter"] * 6}},
                                 {"pattern": {"length": 1, "steps": [{"tie": True, "notes": [{"pitch": 60, "velocity": 99}]}]}}):
            candidate = preset()
            candidate["settings"] = invalid_settings
            with self.subTest(settings=invalid_settings), self.assertRaises(ValueError):
                self.lib.save(0, candidate, 0)
        self.assertFalse(self.lib.path.exists())

    def test_invalid_voice_is_rejected_by_core_before_persistence(self):
        candidate = preset()
        candidate["vced"][0] = 100
        with self.assertRaisesRegex(ValueError, "shared codec"):
            self.lib.save(0, candidate, 0)
        self.assertFalse(self.lib.path.exists())

    def test_logs_identify_operations_revisions_and_no_hardware(self):
        self.lib.dispatch({"action": "save", "slot": 0, "revision": 0, "preset": preset()})
        with self.assertRaises(library.LibraryConflict):
            self.lib.dispatch({"action": "delete", "slot": 0, "revision": 0})
        lines = [json.loads(line) for line in (self.root / "library.log.jsonl").read_text().splitlines()]
        self.assertTrue(all(record["hardware_access"] is False for record in lines))
        self.assertTrue(any(record["event"] == "transaction_committed" and record["revision"] == 1 for record in lines))
        self.assertTrue(any(record["event"] == "request_refused" for record in lines))

    def test_final_log_failure_reports_committed_revision_with_warning(self):
        real_log = self.lib._log
        def fail_commit_log(event, **details):
            if event == "transaction_committed":
                raise OSError("diagnostic volume became full")
            real_log(event, **details)
        with patch.object(self.lib, "_log", side_effect=fail_commit_log):
            result = self.lib.save(0, preset(), 0)
        self.assertEqual(result["revision"], 1)
        self.assertIn("Library saved", result["warnings"][0])
        self.assertEqual(self.lib.load(0)["preset"], preset())

    def test_lock_cleanup_failure_preserves_commit_error_and_foreign_owner(self):
        real_unlink = Path.unlink
        for mode in ("committed", "refused", "foreign"):
            with self.subTest(mode=mode):
                lib = library.PatchLibrary(self.root / mode, Path("unused.exe"), codec=FakeCodec())
                lib.save(0, preset(), 0)
                before = lib.path.read_bytes()
                lock = lib.root / "library.lock"
                def refuse_lock_unlink(path, *args, **kwargs):
                    if path == lock:
                        raise OSError("simulated lock unlink failure")
                    return real_unlink(path, *args, **kwargs)
                if mode == "refused":
                    invalid = preset()
                    invalid["vced"][0] = 100
                    with patch.object(Path, "unlink", refuse_lock_unlink):
                        with self.assertRaisesRegex(ValueError, "shared codec"):
                            lib.save(1, invalid, 1)
                    self.assertEqual(lib.path.read_bytes(), before)
                    self.assertTrue(lock.exists())
                elif mode == "foreign":
                    real_log = lib._log
                    foreign = b'{"pid":987654,"token":"another-owner"}'
                    def replace_owner(event, **details):
                        real_log(event, **details)
                        if event == "transaction_committed":
                            lock.write_bytes(foreign)
                    with patch.object(lib, "_log", side_effect=replace_owner):
                        result = lib.save(1, preset("New"), 1)
                    self.assertEqual(lock.read_bytes(), foreign)
                    self.assertEqual(result["revision"], 2)
                    self.assertIn("foreign lock was preserved", result["warnings"][0])
                else:
                    with patch.object(Path, "unlink", refuse_lock_unlink):
                        result = lib.save(1, preset("New"), 1)
                    self.assertEqual(result["revision"], 2)
                    self.assertIn("Library saved at revision 2", result["warnings"][0])
                    self.assertIn("lock cleanup failed", result["warnings"][0])
                    self.assertEqual(lib.load(1)["preset"]["name"], "New")
                    self.assertTrue(lock.exists())
                with self.assertRaises(library.LibraryConflict):
                    lib.save(2, preset(), 2)

    def test_unbounded_numeric_input_is_refused_without_overflow(self):
        for value in (10**1000, -10**1000, float("nan"), float("inf"), True, "0.5"):
            with self.subTest(value=repr(value)[:24]), self.assertRaises(ValueError):
                library.validate_settings({"effects": {"drive": value}})

    def test_strict_json_refuses_duplicate_keys_and_nonfinite_values(self):
        for raw in ('{"revision":0,"revision":1}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):
                library.strict_loads(raw)

    def test_maximum_chord_grid_preserves_inactive_steps(self):
        candidate = preset()
        candidate["settings"]["pattern"] = {"length": 1, "channel": 15, "steps": [
            {"notes": [{"pitch": n + 20, "velocity": 127} for n in range(9)], "gate": 100, "tie": False}
            for unused in range(64)]}
        state = self.lib.save(0, candidate, 0)
        self.assertEqual(state["slots"][0], candidate)
        self.assertLess(len(library.canonical(candidate["settings"])), library.MAX_SETTINGS_BYTES)


@unittest.skipUnless(os.environ.get("FMER_HOST_EXE"), "Set FMER_HOST_EXE for actual C++ codec CLI integration")
class CodecIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.executable = Path(os.environ["FMER_HOST_EXE"]).resolve()
        self.lib = library.PatchLibrary(self.root / "library", self.executable)

    def tearDown(self):
        self.temporary.cleanup()

    def test_single_and_bank_round_trip_core_validation(self):
        raw = voice(37)
        single = self.lib.codec.encode([raw])
        self.assertEqual(len(single), 163)
        self.assertEqual(self.lib.codec.decode(single)[0]["vced"], raw)
        bank_voices = [voice(i) for i in range(32)]
        bank = self.lib.codec.encode(bank_voices)
        self.assertEqual(len(bank), 4104)
        self.assertEqual([p["vced"] for p in self.lib.codec.decode(bank)], bank_voices)

    def test_invalid_field_or_sysex_checksum_does_not_create_library(self):
        invalid = preset()
        invalid["vced"][134] = 32
        with self.assertRaisesRegex(ValueError, "VCED byte 134"):
            self.lib.save(0, invalid, 0)
        message = bytearray(self.lib.codec.encode([voice()]))
        message[-2] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.lib.decode(base64.b64encode(message).decode())
        self.assertFalse(self.lib.path.exists())

    def test_library_native_backup_and_bank_import_through_actual_codec(self):
        self.lib.save(0, preset(), 0)
        saved = self.lib.backup()["backup"]
        imported = self.lib.codec.encode([voice(i) for i in range(32)])
        state = self.lib.import_bank(base64.b64encode(imported).decode(), 96, 1)
        self.assertEqual(state["slots"][127]["vced"], voice(31))
        exported = self.lib.export(start_slot=96, count=32)
        self.assertEqual(base64.b64decode(exported["sysex"]), imported)
        self.lib.restore(saved, 2)
        self.assertEqual(self.lib.load(0)["preset"], preset())
        self.assertIsNone(self.lib.snapshot()["slots"][127])

    def test_cli_refuses_existing_output_input_alias_and_unknown_options(self):
        source = self.root / "raw.bin"
        target = self.root / "existing.syx"
        source.write_bytes(bytes(voice()))
        target.write_bytes(b"keep me")
        args = [str(self.executable), "--patch-tool", "encode-single", "--in", str(source)]
        for output in (target, source):
            result = subprocess.run(args + ["--out", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(target.read_bytes(), b"keep me")
        self.assertEqual(source.read_bytes(), bytes(voice()))
        result = subprocess.run(args + ["--out", str(self.root / "new.syx"), "--unknown", "0"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / "new.syx").exists())


if __name__ == "__main__":
    unittest.main()
