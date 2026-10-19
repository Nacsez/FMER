import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fm1_native_state as native


def state_fixture():
    controls = [native.control_bounds(identifier)[0] for identifier in range(195)]
    controls[134] = 31
    controls[186] = 64
    controls[187] = 63
    controls[193:195] = [16, 100]
    steps = [[index * 2, index + 1, index % 100 + 1] for index in range(64)]
    steps[62][0] = 128
    controls[188:191] = steps[63]
    return dict(schema=native.SCHEMA, version=1, source_generation=0xffffffff, preset_id=15,
                controls=controls, vced=controls[:145] + [0, 127, 32, 65, 66, 67, 68, 69, 70, 71],
                length=64, steps=steps)


def crc_fixed(raw):
    raw = bytearray(raw)
    struct.pack_into("<I", raw, 28, native.record_crc(raw))
    return bytes(raw)


class NativeRecordTests(unittest.TestCase):
    def setUp(self):
        self.state = state_fixture()
        self.raw = native.encode(self.state)

    def test_exact_complete_roundtrip_and_known_layout(self):
        self.assertEqual(native.decode(self.raw), self.state)
        self.assertEqual(len(self.raw), 784)
        self.assertEqual(self.raw[:8], b"FMERNAT1")
        self.assertEqual(struct.unpack_from("<H", self.raw, 22)[0], 195)
        self.assertEqual(self.raw[422:577], bytes(self.state["vced"]))
        self.assertEqual(self.raw[577:580], bytes(self.state["steps"][0]))
        self.assertEqual(self.raw[766:769], bytes(self.state["steps"][63]))
        self.assertEqual(self.raw[769:], bytes(15))
        self.assertEqual(native.encode(native.decode(self.raw)), self.raw)

    def test_every_single_bit_corruption_is_refused(self):
        for offset in range(len(self.raw)):
            for bit in range(8):
                raw = bytearray(self.raw)
                raw[offset] ^= 1 << bit
                with self.subTest(offset=offset, bit=bit), self.assertRaises(native.NativeStateError):
                    native.decode(raw)

    def test_size_unknown_version_flags_and_counts(self):
        for raw in (self.raw[:-1], self.raw + b"\0", b"", self.raw[:32]):
            with self.assertRaises(native.NativeStateError):
                native.decode(raw)
        for offset in (8, 10, 12, 14, 22, 24, 26):
            raw = bytearray(self.raw)
            raw[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(native.NativeStateError):
                native.decode(crc_fixed(raw))

    def test_reserved_zero_fields_even_when_crc_valid(self):
        for identifier in range(145, 160):
            raw = bytearray(self.raw)
            raw[32 + identifier * 2] = 1
            with self.subTest(identifier=identifier), self.assertRaises(native.NativeStateError):
                native.decode(crc_fixed(raw))
        raw = bytearray(self.raw)
        raw[783] = 1
        with self.assertRaises(native.NativeStateError):
            native.decode(crc_fixed(raw))

    def test_control_and_voice_disagreement(self):
        raw = bytearray(self.raw)
        raw[422] = 1
        with self.assertRaisesRegex(native.NativeStateError, "disagree"):
            native.decode(crc_fixed(raw))
        self.state["controls"][134] = 32
        self.state["vced"][134] = 32
        with self.assertRaises(native.NativeStateError):
            native.encode(self.state)

    def test_names_preserve_all_seven_bit_values_and_refuse_eight_bit(self):
        for value in range(128):
            self.state["vced"][145:] = [value] * 10
            self.assertEqual(native.decode(native.encode(self.state))["vced"][145:], [value] * 10)
        self.state["vced"][145] = 128
        with self.assertRaises(native.NativeStateError):
            native.encode(self.state)

    def test_unknown_extra_and_missing_json_fields(self):
        for missing in self.state:
            state = copy.deepcopy(self.state)
            del state[missing]
            with self.subTest(missing=missing), self.assertRaises(native.NativeStateError):
                native.encode(state)
        self.state["master"] = 123
        with self.assertRaises(native.NativeStateError):
            native.encode(self.state)

    def test_bool_float_and_wrong_container_are_not_values(self):
        for value in (True, 1.0, "1", None):
            state = copy.deepcopy(self.state)
            state["controls"][0] = value
            with self.assertRaises(native.NativeStateError):
                native.encode(state)
        self.state["steps"][0] = (0, 1, 1)
        with self.assertRaises(native.NativeStateError):
            native.encode(self.state)

    def test_pattern_length_selection_and_selected_field_consistency(self):
        for mutate in (lambda s: s.update(length=0), lambda s: s.update(length=65),
                       lambda s: s.update(length=63), lambda s: s["controls"].__setitem__(187, 64),
                       lambda s: s["controls"].__setitem__(188, 24),
                       lambda s: s["controls"].__setitem__(189, 24),
                       lambda s: s["controls"].__setitem__(190, 24)):
            state = copy.deepcopy(self.state)
            mutate(state)
            with self.assertRaises(native.NativeStateError):
                native.encode(state)

    def test_all_inactive_steps_preserved_and_validated(self):
        self.state["length"] = self.state["controls"][186] = 1
        self.state["controls"][187] = 0
        self.state["controls"][188:191] = self.state["steps"][0]
        self.assertEqual(native.decode(native.encode(self.state))["steps"], self.state["steps"])
        for index, value in ((0, 129), (1, 0), (1, 128), (2, 0), (2, 101)):
            state = copy.deepcopy(self.state)
            state["steps"][63][index] = value
            with self.subTest(index=index, value=value), self.assertRaises(native.NativeStateError):
                native.encode(state)

    def test_all_control_upper_bounds_and_invalid_successors(self):
        for identifier in range(195):
            state = copy.deepcopy(self.state)
            upper = native.control_bounds(identifier)[1]
            state["controls"][identifier] = upper + 1
            if identifier < 145:
                state["vced"][identifier] = upper + 1
            with self.subTest(identifier=identifier), self.assertRaises(native.NativeStateError):
                native.encode(state)

    def test_arp_rate_is_power_of_two(self):
        for value in (1, 2, 4, 8, 16, 32):
            self.state["controls"][181] = value
            native.encode(self.state)
        for value in (0, 3, 5, 31, 33):
            self.state["controls"][181] = value
            with self.assertRaises(native.NativeStateError):
                native.encode(self.state)

    def test_source_generation_custom_and_factory_metadata(self):
        for value in (0, 0xffffffff):
            self.state["source_generation"] = value
            for preset in (*range(16), 65535):
                self.state["preset_id"] = preset
                self.assertEqual(native.decode(native.encode(self.state)), self.state)
        for invalid in (-1, 16, 128, 65534, 65536, True):
            self.state["preset_id"] = invalid
            with self.assertRaises(native.NativeStateError):
                native.encode(self.state)

    def test_invalid_record_never_creates_file_and_existing_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.fmer-native"
            with self.assertRaises(native.NativeStateError):
                native.write_record(path, self.raw[:-1])
            self.assertFalse(path.exists())
            native.write_record(path, self.raw)
            with self.assertRaises(FileExistsError):
                native.write_record(path, self.raw)
            self.assertEqual(path.read_bytes(), self.raw)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_backup_has_identity_hash_and_complete_record(self):
        with tempfile.TemporaryDirectory() as directory:
            result = native.save_backup(self.raw, Path(directory), device_identity="FMER Test01 / FM-1_707", source="mock frozen native snapshot")
            self.assertEqual(Path(result["path"]).read_bytes(), self.raw)
            self.assertEqual(result["sha256"], hashlib.sha256(self.raw).hexdigest())
            self.assertEqual(json.loads(Path(result["metadata_path"]).read_text())["persistent_location"], "host filesystem")
            self.assertFalse(result["hardware_write"])

    def test_sidecar_failure_does_not_misreport_committed_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            original = native._write_new
            def sidecar_failure(path, raw):
                if path.suffix == ".json":
                    raise OSError("simulated metadata disk error")
                return original(path, raw)
            with patch.object(native, "_write_new", side_effect=sidecar_failure):
                result = native.save_backup(self.raw, Path(directory), device_identity="test")
            self.assertIn("Record committed", result["warning"])
            self.assertEqual(Path(result["path"]).read_bytes(), self.raw)

    def test_staging_failure_preserves_destination_and_removes_partial_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "safe.fmer-native"
            with patch.object(native.os, "fsync", side_effect=OSError("simulated flush failure")):
                with self.assertRaises(OSError):
                    native.write_record(path, self.raw)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_duplicate_json_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text('{"schema":"one","schema":"two"}')
            with self.assertRaisesRegex(native.NativeStateError, "Duplicate"):
                native._json_record(path)


def reply(opcode, fields):
    return native.PREFIX + bytes([opcode]) + " ".join(str(field) for field in fields).encode("ascii") + bytes([247])


class NativeProtocolTests(unittest.TestCase):
    def test_exact_request_bytes_and_nibble_order(self):
        self.assertEqual(native.status_request(), native.PREFIX + bytes([13, 247]))
        self.assertEqual(native.snapshot_request(), native.PREFIX + bytes([14, 247]))
        self.assertEqual(native.chunk_request(0xffffffff, 783), native.PREFIX + bytes([15, 127,127,127,127,15,15,6,247]))
        self.assertEqual(native.begin_request(1, 0xffffffff), native.PREFIX + bytes([16,1,0,0,0,0,127,127,127,127,15,247]))
        self.assertEqual(native.write_chunk_request(1, 782, b"\xab\xcd"), native.PREFIX + bytes([17,1,0,0,0,0,14,6,2,10,11,12,13,247]))
        self.assertEqual(native.commit_request(2), native.PREFIX + bytes([18,2,0,0,0,0,247]))
        self.assertEqual(native.backup_ack_request(3, 128), native.PREFIX + bytes([19,3,0,0,0,0,0,1,0,0,0,247]))
        self.assertEqual(native.abort_request(), native.PREFIX + bytes([20,0,0,0,0,0,247]))

    def test_request_ranges_exclude_wrap_bool_empty_and_overflow(self):
        invalid = (lambda: native.chunk_request(0, 0), lambda: native.chunk_request(1, 784),
                   lambda: native.chunk_request(1, -1), lambda: native.begin_request(True, 1),
                   lambda: native.begin_request(1, 0x100000000), lambda: native.commit_request(0),
                   lambda: native.backup_ack_request(1, -1), lambda: native.write_chunk_request(1, 0, bytes(65)),
                   lambda: native.write_chunk_request(1, 783, bytes(2)), lambda: native.write_chunk_request(1, 0, b""),
                   lambda: native.write_chunk_request(1, 0, bytearray(1)))
        for operation in invalid:
            with self.assertRaises(native.NativeStateError):
                operation()

    def test_status_fields_and_strict_ranges(self):
        fields = [1, 0xffffffff, 65535, 1, 2, 1, 3, 7, 14]
        self.assertEqual(native.parse_status(reply(13, fields)), dict(zip(native.STATUS_FIELDS, fields)))
        for offset, value in ((0, 2), (1, 0x100000000), (2, 16), (3, 2), (8, 15)):
            changed = list(fields)
            changed[offset] = value
            with self.subTest(offset=offset), self.assertRaises(native.NativeStateError):
                native.parse_status(reply(13, changed))
        with self.assertRaises(native.NativeStateError):
            native.parse_status(reply(13, fields + [0]))

    def test_reply_decimal_and_opcode_are_canonical(self):
        for text in (b"01 0 0 0 0 0 0 0 0", b"1 -1 0 0 0 0 0 0 0", b"1 +1 0 0 0 0 0 0 0",
                     b"1  0 0 0 0 0 0 0 0", b"1\t0 0 0 0 0 0 0 0", b"1 0 0 0 0 0 0 0 0 ",
                     b"1 0 0 0 0 0 0 0 \xff"):
            with self.assertRaises(native.NativeStateError):
                native.parse_status(native.PREFIX + bytes([13]) + text + bytes([247]))
        with self.assertRaises(native.NativeStateError):
            native.parse_status(reply(14, [1,0,0,0,0,0,0,0,0]))

    def test_chunk_exact_owner_extent_and_all_eight_bit_values(self):
        for offset in (0, 64, 768, 783):
            data = bytes(range(256))[128:128 + min(64, native.SIZE - offset)]
            frame = reply(15, [9, offset, len(data), *data])
            self.assertEqual(native.parse_chunk(frame, token=9, offset=offset), data)
            with self.assertRaises(native.NativeStateError):
                native.parse_chunk(frame, token=10, offset=offset)
        for fields in ([9,783,1,256], [9,783,2,0,0], [9,783,0], [9,782,1,0]):
            with self.assertRaises(native.NativeStateError):
                native.parse_chunk(reply(15, fields), token=9, offset=783)

    def test_transaction_results_exact_owner_and_supported_codes(self):
        for opcode in (16,17,18,19,20):
            for result in range(15):
                self.assertEqual(native.parse_result(reply(opcode,[7,result]), opcode=opcode, transaction=7)["result"], result)
        for fields in ([8,0], [7,15], [7], [7,0,0]):
            with self.assertRaises(native.NativeStateError):
                native.parse_result(reply(18,fields), opcode=18, transaction=7)


if __name__ == "__main__":
    unittest.main()
