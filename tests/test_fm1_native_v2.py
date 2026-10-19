import copy
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fm1_native_state as v1
import fm1_native_state_v2 as native


def state_fixture(seed=0):
    rng = random.Random(seed)
    controls = [native.control_bounds(identifier)[0] for identifier in range(198)]
    for identifier in range(145):
        controls[identifier] = rng.randint(*native.control_bounds(identifier))
    controls[180:184] = [9, 32, 4, 100]
    controls[193:198] = [16, 100, 7, 1, 255]
    patterns = [dict(length=bank + 1, steps=[[rng.randrange(129), rng.randrange(1,128), rng.randrange(1,101)] for _ in range(64)]) for bank in range(8)]
    patterns[7]["length"] = 64
    controls[186:191] = [64, 63] + patterns[7]["steps"][63]
    return dict(schema=native.SCHEMA, version=2, source_generation=0xffffffff, preset_id=63,
                controls=controls, vced=controls[:145] + [0, 127, 32, 65, 66, 67, 68, 69, 70, 71], patterns=patterns)


def v1_fixture():
    modern = state_fixture()
    controls = modern["controls"][:195]
    controls[180] = 6
    selected = modern["patterns"][7]
    return dict(schema=v1.SCHEMA, version=1, source_generation=modern["source_generation"], preset_id=15,
                controls=controls, vced=modern["vced"], length=selected["length"], steps=selected["steps"])


def crc_fixed(raw):
    raw = bytearray(raw)
    struct.pack_into("<I", raw, 28, native.record_crc(raw))
    return bytes(raw)


def reply(opcode, fields):
    return native.PREFIX + bytes([opcode]) + " ".join(map(str, fields)).encode("ascii") + bytes([247])


class NativeV2RecordTests(unittest.TestCase):
    def setUp(self):
        self.state = state_fixture()
        self.raw = native.encode(self.state)

    def test_exact_complete_layout_and_roundtrip(self):
        self.assertEqual(len(self.raw), 2176)
        self.assertEqual(self.raw[:8], b"FMERNAT2")
        self.assertEqual(self.raw[428:583], bytes(self.state["vced"]))
        self.assertEqual(self.raw[2127:], bytes(49))
        for bank, pattern in enumerate(self.state["patterns"]):
            offset = 583 + bank * 193
            self.assertEqual(self.raw[offset], pattern["length"])
            self.assertEqual(self.raw[offset + 1:offset + 193], bytes(x for step in pattern["steps"] for x in step))
        self.assertEqual(native.decode(self.raw), self.state)
        self.assertEqual(native.encode(native.decode(self.raw)), self.raw)

    def test_every_single_bit_corruption_is_refused(self):
        for offset in range(2176):
            for bit in range(8):
                raw = bytearray(self.raw)
                raw[offset] ^= 1 << bit
                with self.subTest(offset=offset, bit=bit), self.assertRaises(native.NativeStateError):
                    native.decode(raw)

    def test_every_header_count_flag_and_version_is_explicit(self):
        for offset in (0, 8, 10, 12, 14, 22, 24, 26, 27):
            raw = bytearray(self.raw)
            raw[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(native.NativeStateError):
                native.decode(crc_fixed(raw))

    def test_exact_size_and_bytes_input(self):
        for raw in (self.raw[:-1], self.raw + b"\0", b"", "x" * 2176, [0] * 2176, v1.encode(v1_fixture())):
            with self.assertRaises(native.NativeStateError):
                native.decode(raw)

    def test_reserved_controls_and_padding_even_with_valid_crc(self):
        for offset in list(range(32 + 145 * 2, 32 + 160 * 2, 2)) + [2127, 2175]:
            raw = bytearray(self.raw)
            raw[offset] = 1
            with self.subTest(offset=offset), self.assertRaises(native.NativeStateError):
                native.decode(crc_fixed(raw))

    def test_all_eight_patterns_and_hidden_steps_are_validated(self):
        for bank in range(8):
            for field, value in ((0, 129), (1, 0), (1, 128), (2, 0), (2, 101)):
                state = copy.deepcopy(self.state)
                state["patterns"][bank]["steps"][60][field] = value
                with self.subTest(bank=bank, field=field), self.assertRaises(native.NativeStateError):
                    native.encode(state)
            for length in (0, 65, True, 1.0):
                state = copy.deepcopy(self.state)
                state["patterns"][bank]["length"] = length
                with self.assertRaises(native.NativeStateError):
                    native.encode(state)

    def test_selection_matches_selected_bank_not_bank_zero(self):
        state = copy.deepcopy(self.state)
        state["controls"][195] = 0
        with self.assertRaises(native.NativeStateError):
            native.encode(state)
        state["controls"][186:191] = [state["patterns"][0]["length"], 0] + state["patterns"][0]["steps"][0]
        self.assertEqual(native.decode(native.encode(state)), state)
        state["controls"][188] ^= 1
        with self.assertRaises(native.NativeStateError):
            native.encode(state)

    def test_preset_bounds_and_name_bytes_preserved(self):
        for preset in (0, 15, 16, 31, 32, 39, 40, 63, 65535):
            state = copy.deepcopy(self.state)
            state["preset_id"] = preset
            self.assertEqual(native.decode(native.encode(state))["vced"][145:], state["vced"][145:])
        for preset in (-1, 64, 65534, 65536, True):
            state = copy.deepcopy(self.state)
            state["preset_id"] = preset
            with self.assertRaises(native.NativeStateError):
                native.encode(state)

    def test_new_controls_boundaries_and_existing_rate_contract(self):
        for identifier, bad in ((180,10), (181,3), (195,8), (196,2), (197,0), (197,256)):
            state = copy.deepcopy(self.state)
            state["controls"][identifier] = bad
            with self.subTest(identifier=identifier), self.assertRaises(native.NativeStateError):
                native.encode(state)
        for order in range(10):
            state = copy.deepcopy(self.state)
            state["controls"][180] = order
            self.assertEqual(native.decode(native.encode(state))["controls"][180], order)

    def test_missing_unknown_duplicate_and_wrong_type_json(self):
        for state in ({}, dict(self.state, extra=1), dict(self.state, version=True), dict(self.state, patterns=[])):
            with self.assertRaises(native.NativeStateError):
                native.encode(state)
        state = copy.deepcopy(self.state)
        state["patterns"][0]["extra"] = 1
        with self.assertRaises(native.NativeStateError):
            native.encode(state)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "duplicate.json"
            path.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(native.NativeStateError):
                native._json_record(path)

    def test_fixed_seed_complete_state_roundtrips(self):
        records = set()
        for seed in range(32):
            state = state_fixture(seed)
            encoded = native.encode(state)
            self.assertEqual(native.decode(encoded), state)
            records.add(hashlib.sha256(encoded).hexdigest())
        self.assertEqual(len(records), 32)


class MigrationTests(unittest.TestCase):
    def test_v1_upgrade_preserves_every_existing_field_and_all_64_steps(self):
        old = v1_fixture()
        raw = v1.encode(old)
        before = bytes(raw)
        upgraded = native.decode(native.upgrade_v1(raw))
        self.assertEqual(raw, before)
        for field in ("source_generation", "preset_id", "vced"):
            self.assertEqual(upgraded[field], old[field])
        self.assertEqual(upgraded["controls"][:195], old["controls"])
        self.assertEqual(upgraded["controls"][195:], [0,0,1])
        self.assertEqual(upgraded["patterns"][0], dict(length=old["length"], steps=old["steps"]))
        for pattern in upgraded["patterns"][1:]:
            self.assertEqual(pattern, dict(length=16, steps=[[128,100,75] for _ in range(64)]))

    def test_upgrade_uses_strict_legacy_ranges_and_preserves_ids(self):
        for preset in (0, 7, 8, 15, 65535):
            old = v1_fixture()
            old["preset_id"] = preset
            self.assertEqual(native.decode(native.upgrade_v1(v1.encode(old)))["preset_id"], preset)
        raw = bytearray(v1.encode(v1_fixture()))
        raw[32 + 180 * 2] = 9
        struct.pack_into("<I", raw, 28, v1.record_crc(raw))
        with self.assertRaises(native.NativeStateError):
            native.upgrade_v1(raw)

    def test_migration_cli_keeps_original_and_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            path, out = Path(directory) / "707.native", Path(directory) / "708.native"
            original = v1.encode(v1_fixture())
            path.write_bytes(original)
            with patch("builtins.print"):
                self.assertEqual(native.main(["upgrade-v1", str(path), str(out)]), 0)
                self.assertEqual(native.main(["upgrade-v1", str(path), str(out)]), 1)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(out.read_bytes(), native.upgrade_v1(original))


class HostFileTests(unittest.TestCase):
    def setUp(self):
        self.raw = native.encode(state_fixture())

    def test_durable_record_readback_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "state.fmer-native"
            report = native.write_record(path, self.raw)
            self.assertEqual(native.read_record(path), self.raw)
            self.assertEqual(report["sha256"], hashlib.sha256(self.raw).hexdigest())
            with self.assertRaises(FileExistsError):
                native.write_record(path, self.raw)
            self.assertEqual(path.read_bytes(), self.raw)
            self.assertEqual(list(Path(root).glob("*.tmp")), [])

    def test_backup_has_versioned_scope_and_exact_file(self):
        with tempfile.TemporaryDirectory() as root:
            report = native.save_backup(self.raw, Path(root), device_identity="FM-1_708")
            self.assertEqual(Path(report["path"]).read_bytes(), self.raw)
            metadata = json.loads(Path(report["metadata_path"]).read_text())
            self.assertEqual(metadata["schema"], "fmer-native-host-backup-v2")
            self.assertEqual(metadata["native_schema"], native.SCHEMA)
            self.assertFalse(metadata["hardware_write"])

    def test_sidecar_failure_retains_committed_file_and_warning(self):
        with tempfile.TemporaryDirectory() as root:
            actual = native._write_new
            def fail_sidecar(path, raw):
                if path.suffix == ".json":
                    raise OSError("simulated full disk")
                return actual(path, raw)
            with patch.object(native, "_write_new", side_effect=fail_sidecar):
                report = native.save_backup(self.raw, Path(root), device_identity="FM-1_708")
            self.assertIn("metadata sidecar failed", report["warning"])
            self.assertEqual(native.read_record(Path(report["path"])), self.raw)

    def test_failed_record_commit_never_reports_backup(self):
        with tempfile.TemporaryDirectory() as root, patch.object(native, "_write_new", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                native.save_backup(self.raw, Path(root), device_identity="FM-1_708")
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_invalid_data_and_provenance_create_no_file(self):
        with tempfile.TemporaryDirectory() as root:
            for raw, identity in ((self.raw[:-1], "FM-1_708"), (self.raw, ""), (self.raw, "x" * 129)):
                with self.assertRaises(native.NativeStateError):
                    native.save_backup(raw, Path(root), device_identity=identity)
            self.assertEqual(list(Path(root).iterdir()), [])


class WireTests(unittest.TestCase):
    def test_extended_chunk_offsets_nibble_payloads_and_bounds(self):
        for offset in (0, 768, 2112, 2175):
            count = min(64,2176-offset)
            raw = bytes(range(128,128+count))
            request = native.write_chunk_request(0xffffffff,offset,raw)
            self.assertEqual(request[7:12], bytes([127,127,127,127,15]))
            self.assertEqual(request[-1],247)
            self.assertEqual(native.parse_chunk(reply(15,[7,offset,count,*raw]),token=7,offset=offset),raw)
        for call in (lambda:native.chunk_request(1,2176), lambda:native.chunk_request(0,0),
                     lambda:native.write_chunk_request(1,2175,b"ab"), lambda:native.write_chunk_request(1,0,bytes(65))):
            with self.assertRaises(native.NativeStateError):
                call()

    def test_schema2_status_exact_preset_and_ranges(self):
        fields=[2,0xffffffff,63,1,6,5,7,9,14]
        self.assertEqual(native.parse_status(reply(13,fields)),dict(zip(native.STATUS_FIELDS,fields)))
        for index,value in ((0,1),(0,3),(2,64),(3,2),(8,15)):
            altered=list(fields);altered[index]=value
            with self.assertRaises(native.NativeStateError):
                native.parse_status(reply(13,altered))

    def test_chunk_reply_stale_partial_and_wrong_token_refused(self):
        for fields in ([7,2175,1,256],[8,2175,1,0],[7,2175,2,0,0],[7,14]):
            with self.assertRaises(native.NativeStateError):
                native.parse_chunk(reply(15,fields),token=7,offset=2175)

    def test_legacy_codec_and_wire_are_unchanged(self):
        old=v1.encode(v1_fixture())
        self.assertEqual(len(old),784)
        self.assertEqual(v1.decode(old)["preset_id"],15)
        with self.assertRaises(v1.NativeStateError):
            v1.parse_status(reply(13,[2,1,0,0,0,0,0,0,0]))
        with self.assertRaises(v1.NativeStateError):
            v1.chunk_request(1,784)


if __name__ == "__main__":
    unittest.main()
