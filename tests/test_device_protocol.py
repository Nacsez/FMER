"""Offline protocol fixtures and chunk guards; never open a device."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "device_protocol_under_test", Path(__file__).resolve().parents[1] / "tools/device_protocol.py")
protocol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(protocol)

# Published captures, not measured on our unit. Source pin and scope in docs.
STOCK_V15 = (bytes.fromhex("F0 00 32 45 58 01 00 00 23 4D 5A 44 79 05 26 4C 1A")
             + bytes(21) + bytes.fromhex("20 06 F7"))
BAUD_V089_STALE_CHECKSUM = (
    bytes.fromhex("F0 00 32 45 58 01 00 00 23 4D 5A 44 79 05 06 4E 1C")
    + bytes(21) + bytes.fromhex("20 06 F7"))


def reference_pack(raw):
    """Independent whole-integer representation for fixture construction."""
    bits = int.from_bytes(raw, "little")
    return bytes((bits >> offset) & 127 for offset in range(0, len(raw) * 8, 7))


def frame(raw):
    return b"\xf0" + reference_pack(raw) + b"\xf7"


def identity_block(name=b"FM-1_015"):
    payload = name.ljust(27, b"\0")
    return b"\x00\x59\x11\x1b\x00\x00" + payload + bytes([255 - sum(payload) % 256])


def preset_frame(slot=0, status=0, data=None):
    if data is None:
        data = bytes((index * 37) % 256 for index in range(187)) if status == 0 else b""
    body = bytes([0x7D, 0x50, status]) + slot.to_bytes(4, "little") + len(data).to_bytes(2, "little") + data
    return frame(body + bytes([255 - sum(body) % 256]))


class IdentityTests(unittest.TestCase):
    def test_only_request_constant_matches_published_read_only_probe(self):
        self.assertEqual(protocol.IDENTITY_QUERY, bytes.fromhex("F0 00 32 45 00 00 00 40 7F F7"))

    def test_published_stock_v15_capture_and_independent_construction(self):
        self.assertEqual(frame(identity_block()), STOCK_V15)
        result = protocol.parse_identity_reply(STOCK_V15)
        self.assertEqual((result["identity"], result["model"], result["version"], result["mode"]),
                         ("FM-1_015", "FM-1", 15, "normal"))
        self.assertTrue(result["checksum_valid"])
        self.assertEqual(result["checksum_received"], 0x19)
        self.assertFalse(result["image_compatibility_verified"])

    def test_published_custom_checksum_mismatch_is_explicit_diagnostic_only(self):
        with self.assertRaisesRegex(protocol.ProtocolError, "checksum"):
            protocol.parse_identity_reply(BAUD_V089_STALE_CHECKSUM)
        result = protocol.parse_identity_reply(BAUD_V089_STALE_CHECKSUM, allow_bad_checksum=True)
        self.assertEqual(result["identity"], "FM-1_089")
        self.assertFalse(result["checksum_valid"])
        self.assertFalse(result["image_compatibility_verified"])

    def test_checksum_tolerance_does_not_relax_structure(self):
        damaged = bytearray(STOCK_V15); damaged[0] = 0xF1
        for candidate in (b"", STOCK_V15[:-1], STOCK_V15 + b"\0", bytes(damaged), protocol.IDENTITY_QUERY):
            with self.subTest(frame=candidate.hex()), self.assertRaises(protocol.ProtocolError):
                protocol.parse_identity_reply(candidate, allow_bad_checksum=True)
        damaged = bytearray(STOCK_V15); damaged[20] = 0x80
        with self.assertRaises(protocol.ProtocolError):
            protocol.parse_identity_reply(damaged)
        damaged = bytearray(STOCK_V15); damaged[-2] |= 0x40
        with self.assertRaisesRegex(protocol.ProtocolError, "padding"):
            protocol.parse_identity_reply(damaged)

    def test_declared_length_header_name_and_padding_refused(self):
        original = identity_block()
        for offset, value in ((2, 0x12), (3, 26), (4, 1), (6, 0), (7, 0x1F), (6, 0x80), (30, 1)):
            candidate = bytearray(original); candidate[offset] = value
            candidate[-1] = 255 - sum(candidate[6:-1]) % 256
            with self.subTest(offset=offset, value=value), self.assertRaises(protocol.ProtocolError):
                protocol.parse_identity_reply(frame(candidate))

    def test_update_and_unknown_names_never_become_a_stock_compatibility_claim(self):
        update = protocol.parse_identity_reply(frame(identity_block(b"ota-FM-1_015")))
        self.assertEqual(update["mode"], "update")
        unknown = protocol.parse_identity_reply(frame(identity_block(b"OTHER_123")))
        self.assertEqual(unknown["mode"], "unknown")
        self.assertIsNone(unknown["version"])
        modified = protocol.parse_identity_reply(frame(identity_block(b"FM-1_999")))
        self.assertEqual(modified["version"], 999)
        self.assertFalse(modified["image_compatibility_verified"])


class PackingTests(unittest.TestCase):
    def test_independent_vectors_all_length_residues(self):
        for length in range(256):
            original = bytes((i * 173 + length) % 256 for i in range(length))
            expected = reference_pack(original)
            self.assertEqual(protocol.pack_seven_bit(original), expected)
            self.assertEqual(protocol.unpack_seven_bit(expected, length), original)

    def test_bounds_types_and_extra_padding(self):
        for bad in ([1, 2], 4, "frame"):
            with self.assertRaises(TypeError):
                protocol.pack_seven_bit(bad)
        for bad in (b"\x80", b"\x01"):
            with self.assertRaises(protocol.ProtocolError):
                protocol.unpack_seven_bit(bad)
        with self.assertRaises(protocol.ProtocolError):
            protocol.unpack_seven_bit(reference_pack(b"A") + b"\0", 1)
        with self.assertRaises(protocol.ProtocolError):
            protocol.pack_seven_bit(bytes(4096))
        with self.assertRaises(protocol.ProtocolError):
            protocol.unpack_seven_bit(bytes(4097))
        with self.assertRaises(protocol.ProtocolError):
            protocol.unpack_seven_bit(b"", True)


class FramingTests(unittest.TestCase):
    def test_every_identity_callback_split(self):
        for split in range(1, len(STOCK_V15)):
            assembler = protocol.SysExAssembler()
            self.assertEqual(assembler.feed(STOCK_V15[:split]), [])
            self.assertEqual(assembler.feed(STOCK_V15[split:]), [STOCK_V15])
            self.assertFalse(assembler.buffer)

    def test_realtime_single_byte_chunks_and_multiple_frames(self):
        assembler = protocol.SysExAssembler()
        results = []
        for byte in STOCK_V15:
            results += assembler.feed(bytes([0xF8, byte, 0xFE]))
        self.assertEqual(results, [STOCK_V15])
        self.assertEqual(assembler.realtime_bytes, 82)
        self.assertEqual(assembler.feed(STOCK_V15 * 2), [STOCK_V15, STOCK_V15])

    def test_interrupt_oversize_finish_and_recovery(self):
        assembler = protocol.SysExAssembler(41)
        self.assertEqual(assembler.feed(b"\xf0\x01\x90\x40\x40\xf7"), [])
        self.assertEqual(assembler.aborted_messages, 1)
        self.assertEqual(assembler.feed(b"\xf0" + bytes(41) + b"\xf7"), [])
        self.assertEqual(assembler.oversized_messages, 1)
        self.assertEqual(assembler.feed(b"\xf0\0" + STOCK_V15), [STOCK_V15])
        assembler.feed(STOCK_V15[:20]); assembler.finish()
        self.assertFalse(assembler.buffer)
        self.assertEqual(assembler.aborted_messages, 3)
        self.assertEqual(assembler.feed(STOCK_V15), [STOCK_V15])


class PresetReplyTests(unittest.TestCase):
    def test_opaque_preset_bytes_roundtrip_and_slot_match(self):
        result = protocol.parse_baud_preset_reply(preset_frame(127), expected_slot=127)
        self.assertTrue(result["complete"])
        self.assertEqual(result["voice"] + result["record"],
                         bytes((i * 37) % 256 for i in range(187)))
        self.assertEqual(len(result["voice"]), 128)
        self.assertEqual(len(result["record"]), 59)
        with self.assertRaisesRegex(protocol.ProtocolError, "slot"):
            protocol.parse_baud_preset_reply(preset_frame(1), expected_slot=0)

    def test_rejected_reads_do_not_return_complete_backups(self):
        for status in (1, 2, 3):
            result = protocol.parse_baud_preset_reply(preset_frame(status=status), expected_slot=0)
            self.assertEqual(result, {"slot": 0, "status": status, "complete": False})
        with self.assertRaises(protocol.ProtocolError):
            protocol.parse_baud_preset_reply(preset_frame(status=4, data=b""), expected_slot=0)

    def test_malformed_backup_replies_never_become_complete_records(self):
        valid = preset_frame()
        corrupted = bytearray(valid); corrupted[12] ^= 1
        for candidate in (valid[:-1], valid[:-1] + b"\0\xf7", bytes(corrupted),
                          preset_frame(data=bytes(186)), preset_frame(data=bytes(188)),
                          preset_frame(status=2, data=b"X"), STOCK_V15):
            with self.subTest(length=len(candidate)), self.assertRaises(protocol.ProtocolError):
                protocol.parse_baud_preset_reply(candidate, expected_slot=0)
        for slot in (-1, 128, True, "0"):
            with self.assertRaises(protocol.ProtocolError):
                protocol.parse_baud_preset_reply(valid, expected_slot=slot)


if __name__ == "__main__":
    unittest.main()
