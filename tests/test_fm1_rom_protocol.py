"""Offline ROM simulation; no OS device access or vendor payload dependency."""
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "fm1_rom_protocol", Path(__file__).resolve().parents[1] / "tools/fm1_rom_protocol.py")
rom = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rom)


def reference_crc(data, crc=0):
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 65535
    return crc


def reference_cipher(data):
    magic = bytes.fromhex("c3cfc0e8ced2b0aec4e3a3acd3f1c1d6")
    state = reference_crc(b"\xff\xff", 65535)
    output = bytearray()
    for index, value in enumerate(data):
        state = reference_crc(bytes([magic[index % 16]]), state)
        output.append(value ^ (state & 255))
    return bytes(output)


def inquiry(vendor=b"WL82", product=b"UBOOT1.00", revision=b"1.00"):
    return bytes(8) + vendor.ljust(8, b" ") + product.ljust(16, b" ") + revision


def command(opcode, args=b""):
    return (opcode.to_bytes(2, "big") + args).ljust(16, b"\xff")


def block_args(address, length=512):
    return address.to_bytes(4, "big") + length.to_bytes(2, "big")


FIXTURE = b"".join(bytes((i * 7 + block * 19) % 256 for i in range(512))
                   for block in range(47))
FIXTURE_SHA = hashlib.sha256(FIXTURE).hexdigest()
FIXTURE_GIT = hashlib.sha1(b"blob 24064\0" + FIXTURE).hexdigest()
FLASH = bytes(range(256)) * 4096


class FakeRom:
    """Independent simulated RAM cipher and raw SPI map, with fault injection."""
    def __init__(self):
        self.calls = []
        self.ram = bytearray(24064)
        self.uploaded = set()
        self.read_back = set()
        self.jumped = False
        self.identity = inquiry()
        self.key = 0x980F
        self.flash_id = 0x856014
        self.device_type = 3
        self.corrupt_ram_at = None
        self.short_command = None
        self.bad_echo = None
        self.raise_command = None
        self.flash_reads = 0
        self.mutate_second_dump = False

    def execute(self, cdb, *, data_out=None, data_in=0):
        self.calls.append((cdb, data_out, data_in))
        if cdb == bytes.fromhex("120000002400"):
            return self.identity
        opcode = int.from_bytes(cdb[:2], "big")
        if opcode == self.raise_command:
            raise OSError("synthetic device disconnect")
        if opcode == 0xFB06:
            assert not self.jumped
            offset = int.from_bytes(cdb[2:6], "big") - 0x01C02000
            assert int.from_bytes(cdb[6:8], "big") == len(data_out) == 512
            assert int.from_bytes(cdb[9:11], "little") == reference_crc(data_out)
            self.ram[offset:offset + 512] = reference_cipher(data_out)
            self.uploaded.add(offset)
            result = b""
        elif opcode == 0xFD07:
            assert not self.jumped
            offset = int.from_bytes(cdb[2:6], "big") - 0x01C02000
            assert offset in self.uploaded
            self.read_back.add(offset)
            result = reference_cipher(self.ram[offset:offset + 512])
            if offset == self.corrupt_ram_at:
                result = bytes([result[0] ^ 1]) + result[1:]
        elif opcode == 0xFB08:
            assert len(self.uploaded) == len(self.read_back) == 47
            assert cdb[2:8] == bytes.fromhex("01c020000001")
            self.jumped = True
            result = b"\xfb\x08" + bytes(14)
        elif opcode == 0xFC09:
            assert self.jumped
            payload = bytearray(14)
            payload[4:6] = reference_cipher(self.key.to_bytes(2, "little"))[::-1]
            result = b"\xfc\x09" + payload
        elif opcode == 0xFC0A:
            assert self.jumped
            payload = bytearray(14)
            payload[0] = self.device_type
            payload[2:6] = self.flash_id.to_bytes(4, "little")
            result = b"\xfc\x0a" + payload
        elif opcode == 0xFD05:
            assert self.jumped
            offset = int.from_bytes(cdb[2:6], "big")
            result = FLASH[offset:offset + 512]
            if self.mutate_second_dump and self.flash_reads >= 2048 and offset == 512:
                result = b"\xee" + result[1:]
            self.flash_reads += 1
        else:
            raise AssertionError(f"Unexpected command {opcode:#x}")
        if opcode == self.bad_echo:
            result = b"\0\0" + result[2:]
        if opcode == self.short_command:
            result = result[:-1]
        return bytes(result)


class CipherTests(unittest.TestCase):
    def test_crc_known_vector(self):
        self.assertEqual(rom.crc16(b"123456789"), 0x31C3)
        for initial in (0, 0xFFFF, 0x1234):
            self.assertEqual(rom.crc16(bytes(range(256)), initial),
                             reference_crc(bytes(range(256)), initial))

    def test_cipher_independent_vector_and_per_block_reset(self):
        expected = bytes.fromhex(
            "2fa481cc4ec15deaeea2b6a6298ad4f70384ebe1cf8a8a14bde6dd1cd0f8463b"
            "9d01ed53942fe1a1c795118dd6ffaa3da0e8b29d81af44dcaf8a7e5c51b8e7ff")
        self.assertEqual(rom.crc_cipher(bytes(64)), expected)
        raw = bytes(range(256)) * 2
        self.assertEqual(rom.crc_cipher(raw), reference_cipher(raw))
        self.assertEqual(rom.crc_cipher(rom.crc_cipher(raw)), raw)
        self.assertNotEqual(rom.crc_cipher(raw + raw), rom.crc_cipher(raw) * 2)

    def test_exact_real_pin_constants_and_rejection(self):
        self.assertEqual(rom.BOOTSTRAP_SIZE, 24064)
        self.assertEqual(rom.BOOTSTRAP_SHA256,
                         "d41da6126760c9d66660bcc0cac8d27d221806c5e369a8036921efe68dca5376")
        self.assertEqual(rom.BOOTSTRAP_GIT_BLOB, "3b47cffaf7bd87f27163ca7bf0c7deb0c783ac87")
        for value in (b"", FIXTURE, bytearray(FIXTURE), FIXTURE + b"\0"):
            with self.subTest(kind=type(value), length=len(value)):
                with self.assertRaises(rom.RomProtocolError):
                    rom.validate_bootstrap(value)


class CommandTests(unittest.TestCase):
    def test_inquiry_is_exact_not_prefix(self):
        self.assertEqual(rom.parse_inquiry(inquiry())["vendor"], "WL82")
        for reply in (inquiry(vendor=b"BR23"), inquiry(product=b"UBOOT2.00"),
                      inquiry(revision=b"2.00"), inquiry()[:-1], inquiry() + b"\0",
                      inquiry(vendor=b"\xff")):
            with self.subTest(reply=reply):
                with self.assertRaises(rom.RomProtocolError):
                    rom.parse_inquiry(reply)

    def test_forbidden_commands_never_pass_allowlist(self):
        for opcode in (0xFB00, 0xFB01, 0xFB02, 0xFB04, 0xFC0C, 0xFC12, 0xFC14,
                       0xFCFF, 0xFD01, 0xFFFF):
            for length in (0, 16, 512):
                with self.subTest(opcode=opcode, length=length):
                    with self.assertRaises(rom.RomProtocolError):
                        rom.validate_transfer(command(opcode), data_in=length)

    def test_memory_bounds_jump_key_and_padding_are_fixed(self):
        self.assertEqual(rom.validate_transfer(command(0xFD07, block_args(rom.RAM_BASE)), data_in=512), "read_ram")
        self.assertEqual(rom.validate_transfer(command(0xFD07, block_args(rom.RAM_BASE + 24064 - 512)), data_in=512), "read_ram")
        for address in (rom.RAM_BASE - 512, rom.RAM_BASE + 1, rom.RAM_BASE + 24064):
            with self.assertRaises(rom.RomProtocolError):
                rom.validate_transfer(command(0xFD07, block_args(address)), data_in=512)
        for cdb in (command(0xFB08, block_args(rom.RAM_BASE, 0)),
                    command(0xFB08, block_args(rom.RAM_BASE + 512, 1)),
                    command(0xFC09, bytes.fromhex("00ac6901")),
                    command(0xFC0A)[:-1] + b"\0"):
            with self.assertRaises(rom.RomProtocolError):
                rom.validate_transfer(cdb, data_in=16)

    def test_ram_crc_direction_and_length(self):
        block = FIXTURE[:512]
        cdb = command(0xFB06, block_args(rom.RAM_BASE) + b"\0" + reference_crc(block).to_bytes(2, "little"))
        self.assertEqual(rom.validate_transfer(cdb, data_out=block), "write_ram")
        invalid = [(cdb, block[:-1], 0), (cdb, None, 512), (cdb, block, 16),
                   (cdb, bytearray(block), 0), (cdb[:9] + b"\0\0" + cdb[11:], block, 0),
                   (cdb[:-1] + b"\0", block, 0), (cdb[:8] + b"\x01" + cdb[9:], block, 0)]
        for frame, output, count in invalid:
            with self.assertRaises(rom.RomProtocolError):
                rom.validate_transfer(frame, output, count)

    def test_flash_bounds_and_transfer_types(self):
        for address in (0, rom.FLASH_SIZE - 512):
            self.assertEqual(rom.validate_transfer(command(0xFD05, block_args(address)), data_in=512), "read_flash")
        for address in (1, rom.FLASH_SIZE, 0xFFFFFFFF):
            with self.assertRaises(rom.RomProtocolError):
                rom.validate_transfer(command(0xFD05, block_args(address)), data_in=512)
        for length in (0, 1, 511, 513, 65535):
            with self.assertRaises(rom.RomProtocolError):
                rom.validate_transfer(command(0xFD05, block_args(0, length)), data_in=length)
        for frame, output, count in ((rom.INQUIRY_CDB, None, True),
                                     (rom.INQUIRY_CDB, b"", 36),
                                     (bytearray(rom.INQUIRY_CDB), None, 36),
                                     (rom.INQUIRY_CDB + b"\0", None, 36),
                                     (rom.INQUIRY_CDB, None, 35)):
            with self.assertRaises(rom.RomProtocolError):
                rom.validate_transfer(frame, output, count)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        # Synthetic bytes exercise the real validators; proprietary payloads
        # are never required by or incorporated into these offline tests.
        self.sha_patch = patch.object(rom, "BOOTSTRAP_SHA256", FIXTURE_SHA)
        self.git_patch = patch.object(rom, "BOOTSTRAP_GIT_BLOB", FIXTURE_GIT)
        self.sha_patch.start()
        self.git_patch.start()
        self.addCleanup(self.sha_patch.stop)
        self.addCleanup(self.git_patch.stop)
        self.fake = FakeRom()
        self.progress = []
        self.reader = rom.RomReader(self.fake.execute, self.progress.append)

    def start(self):
        self.reader.inquiry()
        return self.reader.start_loader(FIXTURE)

    def test_full_upload_readback_order_and_decoded_ram(self):
        info = self.start()
        operations = [int.from_bytes(cdb[:2], "big") for cdb, _, _ in self.fake.calls[1:]]
        self.assertEqual(operations, [0xFB06] * 47 + [0xFD07] * 47 + [0xFB08, 0xFC09, 0xFC0A])
        self.assertEqual(bytes(self.fake.ram), b"".join(reference_cipher(FIXTURE[i:i+512]) for i in range(0, 24064, 512)))
        self.assertEqual(info["bootstrap"]["decoded_ram_sha256"], hashlib.sha256(self.fake.ram).hexdigest())
        self.assertTrue(info["ram_readback_verified"])
        self.assertEqual(info["chip_key"], 0x980F)
        self.assertEqual(self.reader.state, "loader")
        self.assertEqual(self.reader.read_flash(0), FLASH[:512])
        self.assertEqual(self.reader.read_flash(rom.FLASH_SIZE-512), FLASH[-512:])
        self.assertEqual(self.reader.keepalive()["flash_id"], 0x856014)
        self.assertTrue(any(row["event"] == "bootstrap_ram_verified" for row in self.progress))
        self.assertTrue(all(not any(isinstance(v, bytes) for v in row.values()) for row in self.progress))

    def test_no_transfer_before_inquiry_and_no_duplicate_start(self):
        with self.assertRaises(rom.RomProtocolError):
            self.reader.start_loader(FIXTURE)
        with self.assertRaises(rom.RomProtocolError):
            self.reader.read_flash(0)
        self.assertEqual(self.fake.calls, [])
        self.start()
        before = len(self.fake.calls)
        for action in (self.reader.inquiry, lambda: self.reader.start_loader(FIXTURE)):
            with self.assertRaises(rom.RomProtocolError):
                action()
        self.assertEqual(len(self.fake.calls), before)

    def test_changed_blob_rejected_before_ram_io(self):
        self.reader.inquiry()
        with self.assertRaises(rom.RomProtocolError):
            self.reader.start_loader(FIXTURE[:-1] + bytes([FIXTURE[-1] ^ 1]))
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(self.reader.state, "failed")

    def test_bad_inquiry_permanently_refuses_vendor_commands(self):
        self.fake.identity = inquiry(vendor=b"BR23")
        with self.assertRaises(rom.RomProtocolError):
            self.reader.inquiry()
        with self.assertRaises(rom.RomProtocolError):
            self.reader.start_loader(FIXTURE)
        self.assertEqual(len(self.fake.calls), 1)

    def test_last_ram_block_corruption_never_jumps(self):
        self.fake.corrupt_ram_at = 24064 - 512
        with self.assertRaisesRegex(rom.RomProtocolError, "readback mismatch"):
            self.start()
        self.assertFalse(self.fake.jumped)
        self.assertEqual(self.reader.state, "failed")
        self.assertFalse(any(cdb[:2] == b"\xfb\x08" for cdb, _, _ in self.fake.calls))

    def test_short_readback_stops_before_jump(self):
        self.fake.short_command = 0xFD07
        with self.assertRaisesRegex(rom.RomProtocolError, "byte count"):
            self.start()
        self.assertFalse(self.fake.jumped)
        self.assertEqual(len(self.fake.read_back), 1)

    def test_bad_jump_echo_prevents_loader_commands(self):
        self.fake.bad_echo = 0xFB08
        with self.assertRaisesRegex(rom.RomProtocolError, "Reply command mismatch"):
            self.start()
        self.assertFalse(any(cdb[:2] == b"\xfc\x09" for cdb, _, _ in self.fake.calls))

    def test_wrong_key_or_flash_geometry_prevents_flash_reads(self):
        for field, value in (("key", 0xFFFF), ("device_type", 4), ("flash_id", 0x856015)):
            with self.subTest(field=field):
                self.fake = FakeRom()
                setattr(self.fake, field, value)
                self.reader = rom.RomReader(self.fake.execute)
                with self.assertRaises(rom.RomProtocolError):
                    self.start()
                with self.assertRaises(rom.RomProtocolError):
                    self.reader.read_flash(0)
                self.assertEqual(self.fake.flash_reads, 0)
                self.assertEqual(self.reader.state, "failed")

    def test_disconnect_and_wrong_keepalive_identity_latch_failure(self):
        self.start()
        self.fake.flash_id = 0xFFFFFF
        with self.assertRaises(rom.RomProtocolError):
            self.reader.keepalive()
        with self.assertRaises(rom.RomProtocolError):
            self.reader.read_flash(0)
        self.assertEqual(self.fake.flash_reads, 0)
        self.fake = FakeRom()
        self.reader = rom.RomReader(self.fake.execute)
        self.start()
        self.fake.raise_command = 0xFD05
        with self.assertRaises(OSError):
            self.reader.read_flash(0)
        self.assertEqual(self.reader.state, "failed")
        before = len(self.fake.calls)
        with self.assertRaises(rom.RomProtocolError):
            self.reader.read_flash(0)
        self.assertEqual(len(self.fake.calls), before)

    def test_read_flash_argument_checks_before_transport(self):
        self.start()
        before = len(self.fake.calls)
        for offset, length in ((True, 512), (-512, 512), (0.0, 512), (0, True),
                               (rom.FLASH_SIZE, 512), (0, 1024), (1, 512)):
            with self.assertRaises(rom.RomProtocolError):
                self.reader.read_flash(offset, length)
        self.assertEqual(len(self.fake.calls), before)

    def test_two_full_raw_reads_and_durable_chunk_callback(self):
        self.start()
        chunks = []
        first = self.reader.read_full_flash(pass_number=1, on_chunk=lambda p, o, b: chunks.append((p, o, len(b))))
        second = self.reader.read_full_flash(pass_number=2, on_chunk=lambda p, o, b: chunks.append((p, o, len(b))))
        self.assertEqual(first, FLASH)
        self.assertEqual(second, FLASH)
        self.assertEqual(self.fake.flash_reads, 4096)
        self.assertEqual(chunks, [(p, o, 512) for p in (1, 2) for o in range(0, rom.FLASH_SIZE, 512)])
        result = rom.verify_matching_dumps(first, second)
        self.assertTrue(result["byte_equal"])
        self.assertEqual(result["sha256"], hashlib.sha256(FLASH).hexdigest())

    def test_short_flash_read_and_sink_failure_do_not_report_complete_dump(self):
        self.start()
        self.fake.short_command = 0xFD05
        with self.assertRaises(rom.RomProtocolError):
            self.reader.read_full_flash()
        self.assertFalse(any(r["event"] == "dump_complete" for r in self.progress))
        self.fake = FakeRom()
        self.reader = rom.RomReader(self.fake.execute)
        self.start()
        def full_disk(*args):
            raise OSError("synthetic disk full")
        with self.assertRaises(OSError):
            self.reader.read_full_flash(on_chunk=full_disk)
        self.assertEqual(self.reader.state, "failed")
        self.assertEqual(self.fake.flash_reads, 1)

    def test_mismatch_and_incomplete_dumps_are_refused(self):
        self.start()
        self.fake.mutate_second_dump = True
        first = self.reader.read_full_flash(pass_number=1)
        second = self.reader.read_full_flash(pass_number=2)
        with self.assertRaisesRegex(rom.RomProtocolError, "0x200"):
            rom.verify_matching_dumps(first, second)
        for a, b in ((b"", b""), (FLASH[:-1], FLASH[:-1]), (FLASH, FLASH[:-1]),
                     (bytearray(FLASH), FLASH)):
            with self.assertRaises(rom.RomProtocolError):
                rom.verify_matching_dumps(a, b)


if __name__ == "__main__":
    unittest.main()
