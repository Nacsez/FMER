"""Offline exact-device selection, Windows SCSI lifetime, and private dump tests."""
import ctypes as ct
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fm1_rom_backup as backup
import fm1_rom_protocol as protocol

BOOTSTRAP = Path(__file__).resolve().parents[1] / "third_party/acquired/fm1-rom-bootstrap/wl82loader.bin"
IDENTITY = b"\0" * 8 + b"WL82".ljust(8, b" ") + b"UBOOT1.00".ljust(16, b" ") + b"1.00"


def candidate(**changes):
    values = {"path": "opaque disk interface with private serial", "instance": "USBSTOR\\DISK&VEN_WL82\\private",
              "usb_instance": "USB\\VID_4C4A&PID_8057\\private-serial", "location_paths": ("PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(4)",),
              "disk_service": "disk", "usb_service": "USBSTOR"}
    return backup.Candidate(**dict(values, **changes))


class MemoryJournal:
    def __init__(self, directory=None, fail=None):
        self.events, self.fail = [], fail
        self.directory = Path(directory) if directory else None

    def record(self, event, **values):
        if event == self.fail:
            raise OSError("journal unavailable")
        self.events.append({"event": event, **values})


class FakeStorage:
    def __init__(self, *, identity=IDENTITY, fault=None, mismatch=False):
        self.candidate, self.identity, self.fault = candidate(), identity, fault
        self.calls, self.blocks, self.reads = [], {}, 0
        self.mismatch = mismatch

    def enumerate(self):
        self.calls.append(("enumerate",))
        return [self.candidate]

    def open(self, path):
        self.calls.append(("open", path))
        return 0x123456789ABC

    def close(self, handle):
        self.calls.append(("close", handle))
        if self.fault == "close":
            raise backup.BackupError("close failed")

    def alignment(self, handle):
        return 4095

    def ioctl(self, handle, code, source, source_bytes, target, target_bytes):
        assert code == backup.IOCTL_SCSI_PASS_THROUGH_DIRECT
        packet = ct.cast(target, ct.POINTER(backup.ScsiPacket)).contents
        spt = packet.spt
        cdb = bytes(spt.Cdb[:spt.CdbLength])
        self.calls.append(("cdb", cdb))
        assert spt.DataBuffer % 4096 == 0
        assert spt.TimeOutValue == 2
        assert spt.PathId == spt.TargetId == spt.Lun == 0
        size = spt.DataTransferLength
        result = None
        if cdb == backup.INQUIRY:
            result = self.identity
        elif cdb[:2] == b"\xfb\x06":
            self.blocks[int.from_bytes(cdb[2:6], "big")] = ct.string_at(spt.DataBuffer, size)
        elif cdb[:2] == b"\xfd\x07":
            result = self.blocks[int.from_bytes(cdb[2:6], "big")]
        elif cdb[:2] == b"\xfb\x08":
            result = cdb[:2] + b"\0" * 14
        elif cdb[:2] == b"\xfc\x09":
            result = cdb[:2] + b"\0" * 4 + protocol.crc_cipher(bytes.fromhex("0f98"))[::-1] + b"\0" * 8
        elif cdb[:2] == b"\xfc\x0a":
            result = cdb[:2] + b"\3\0" + (0x856014).to_bytes(4, "little") + b"\0" * 8
        elif cdb[:2] == b"\xfd\x05":
            offset = int.from_bytes(cdb[2:6], "big")
            result = bytes((offset // 512 + index) & 255 for index in range(512))
            if self.mismatch and self.reads >= 2048 and offset == 0x4000:
                result = bytes([result[0] ^ 1]) + result[1:]
            self.reads += 1
        else:
            raise AssertionError("Unexpected command " + cdb.hex())
        if result is not None:
            ct.memmove(spt.DataBuffer, result, len(result))
        spt.SenseInfoLength = 0
        if self.fault == "status":
            spt.ScsiStatus = 2
        elif self.fault == "sense":
            spt.SenseInfoLength = 1
            packet.sense[0] = 0x70
        elif self.fault == "long_sense":
            spt.SenseInfoLength = 33
        elif self.fault == "length":
            spt.DataTransferLength -= 1
        elif self.fault == "cdb":
            spt.Cdb[0] ^= 1
        elif self.fault == "pointer":
            spt.DataBuffer += 1
        elif self.fault == "sense_metadata":
            spt.SenseInfoLength = 32
            return ct.sizeof(backup.ScsiPassThroughDirect)
        elif self.fault == "metadata":
            return ct.sizeof(backup.ScsiPassThroughDirect) - 1
        elif self.fault == "driver":
            raise backup.BackupError("driver failed")
        return ct.sizeof(backup.ScsiPacket)


class SelectionTests(unittest.TestCase):
    def test_exact_vid_pid_existing_driver_location_and_uniqueness_required(self):
        good = candidate()
        self.assertEqual(backup.select_candidate([good]), good)
        bad = [candidate(usb_instance="USB\\VID_4C4A&PID_80570\\x"),
               candidate(usb_instance="USB\\VID_4C4A&PID_C755\\x"),
               candidate(usb_service="WinUSB"), candidate(disk_service="Other"),
               candidate(location_paths=())]
        for candidates in ([], bad, [good, good]):
            with self.subTest(candidates=candidates), self.assertRaises(backup.BackupError):
                backup.select_candidate(candidates)
        self.assertEqual(backup.select_candidate(bad + [good]), good)

    def test_public_metadata_contains_no_device_path_or_serial(self):
        item = candidate()
        public = item.public()
        text = json.dumps(public)
        for private in (item.path, item.instance, item.usb_instance, "private-serial"):
            self.assertNotIn(private, text)
        self.assertEqual(public["path_sha256"], backup.text_hash(item.path))
        self.assertEqual(public["location_paths"], list(item.location_paths))

    def test_parent_walk_identifies_rom_ancestor_without_opening_any_device(self):
        api = object.__new__(backup.WindowsDiskAPI)
        api.cfg = Mock()
        identities = {1: "USBSTOR\\DISK&VEN_WL82\\serial", 2: "USB\\VID_4C4A&PID_8057\\serial"}
        api.instance_id = lambda node: identities[node]
        api.property_strings = lambda node, prop: (("disk",) if node == 1 else ("USBSTOR",)) if prop == 5 else ("USBROOT(0)#USB(4)",)
        def parent(output, node, flags):
            ct.cast(output, ct.POINTER(backup.DWORD))[0] = 2
            return 0
        api.cfg.CM_Get_Parent.side_effect = parent
        item = api.candidate_for("opaque", 1)
        self.assertEqual(item.usb_instance, identities[2])
        self.assertEqual(item.disk_service, "disk")

    def test_native_createfile_uses_correct_access_and_sharing_without_path_guessing(self):
        api = object.__new__(backup.WindowsDiskAPI)
        api.kernel = Mock()
        api.kernel.CreateFileW.return_value = 0x123456789ABC
        self.assertEqual(api.open("opaque setupapi path"), 0x123456789ABC)
        api.kernel.CreateFileW.assert_called_once_with("opaque setupapi path", 0xC0000000, 3, None, 3, 0, None)

    def test_adapter_alignment_query_validates_masks_bounds_and_transfer_capacity(self):
        for maximum, mask, returned, expected in ((512, 4095, 20, True), (512, 0, 20, True),
                                                   (256, 0, 20, False), (512, 5, 20, False),
                                                   (512, 65536, 20, False), (512, 0, 19, False)):
            api = object.__new__(backup.WindowsDiskAPI)
            def ioctl(handle, code, query, length, target, capacity):
                self.assertEqual(code, backup.IOCTL_STORAGE_QUERY_PROPERTY)
                self.assertEqual(ct.string_at(query, length), b"\1" + b"\0" * 11)
                data = b"".join(value.to_bytes(4, "little") for value in (20, 20, maximum, 1, mask))
                ct.memmove(target, data, len(data))
                return returned
            api.ioctl = ioctl
            with self.subTest(mask=mask, maximum=maximum, returned=returned):
                if expected:
                    self.assertEqual(api.alignment(1), mask)
                else:
                    with self.assertRaises(backup.BackupError):
                        api.alignment(1)


class SessionTests(unittest.TestCase):
    def test_same_handle_inquiry_and_aligned_buffers_before_vendor_access(self):
        api, journal = FakeStorage(), MemoryJournal()
        with backup.RomSession(api, candidate(), journal) as session:
            self.assertTrue(session.admitted)
            self.assertEqual(session.execute(backup.INQUIRY, data_in=36), IDENTITY)
        self.assertEqual([call[1] for call in api.calls if call[0] == "cdb"], [backup.INQUIRY] * 2)
        self.assertEqual([call for call in api.calls if call[0] == "close"], [("close", 0x123456789ABC)])

    def test_wrong_inquiry_closes_with_no_vendor_command(self):
        for identity in (IDENTITY.replace(b"WL82", b"WL80"), IDENTITY.replace(b"1.00", b"2.00"),
                         IDENTITY.replace(b"WL82    ", b"WL82\0\0\0\0"), b"\5" + IDENTITY[1:], b"\x20" + IDENTITY[1:]):
            api = FakeStorage(identity=identity)
            with self.subTest(identity=identity), self.assertRaises(backup.BackupError):
                with backup.RomSession(api, candidate(), MemoryJournal()):
                    pass
            self.assertEqual([call[1] for call in api.calls if call[0] == "cdb"], [backup.INQUIRY])
            self.assertEqual(sum(call[0] == "close" for call in api.calls), 1)

    def test_enumeration_change_after_open_closes_without_any_cdb(self):
        api = FakeStorage()
        api.candidate = candidate(location_paths=("USBROOT(0)#USB(5)",))
        with self.assertRaises(backup.BackupError):
            with backup.RomSession(api, candidate(), MemoryJournal()):
                pass
        self.assertFalse(any(call[0] == "cdb" for call in api.calls))
        self.assertEqual(sum(call[0] == "close" for call in api.calls), 1)

    def test_driver_status_sense_exact_lengths_and_metadata_fail_closed(self):
        for fault in ("status", "sense", "long_sense", "length", "cdb", "pointer", "metadata", "sense_metadata", "driver"):
            api = FakeStorage(fault=fault)
            session = backup.RomSession(api, candidate(), MemoryJournal())
            with self.subTest(fault=fault), self.assertRaises(backup.BackupError):
                session.__enter__()
            before = len(api.calls)
            with self.assertRaises(backup.BackupError):
                session.execute(backup.INQUIRY, data_in=36)
            self.assertEqual(len(api.calls), before)
            self.assertIsNone(session.handle)

    def test_journal_failure_prevents_open_or_native_transfer(self):
        api = FakeStorage()
        with self.assertRaises(OSError):
            backup.RomSession(api, candidate(), MemoryJournal(fail="open_intent")).__enter__()
        self.assertEqual(api.calls, [])
        with self.assertRaises(OSError):
            backup.RomSession(api, candidate(), MemoryJournal(fail="scsi_intent")).__enter__()
        self.assertFalse(any(call[0] == "cdb" for call in api.calls))

    def test_native_timeout_does_not_publish_a_successful_transfer(self):
        api = FakeStorage()
        with patch.object(backup.time, "monotonic", side_effect=[0, 3.1]):
            with self.assertRaises(backup.BackupError):
                backup.RomSession(api, candidate(), MemoryJournal()).__enter__()
        self.assertEqual(sum(call[0] == "close" for call in api.calls), 1)

    def test_forbidden_flash_commands_never_reach_driver(self):
        for command in (0xFB00, 0xFB01, 0xFB04):
            api = FakeStorage()
            with backup.RomSession(api, candidate(), MemoryJournal()) as session:
                with self.assertRaises(protocol.RomProtocolError):
                    session.execute(command.to_bytes(2, "big") + b"\xff" * 14, data_in=16)
            self.assertEqual([call[1] for call in api.calls if call[0] == "cdb"], [backup.INQUIRY])

    def test_close_error_is_not_hidden(self):
        api = FakeStorage(fault="close")
        session = backup.RomSession(api, candidate(), MemoryJournal())
        with self.assertRaises(backup.BackupError):
            with session:
                pass
        self.assertIsNotNone(session.handle)


class PersistenceTests(unittest.TestCase):
    @unittest.skipUnless(BOOTSTRAP.is_file(), "Pinned bootstrap acquisition not available; no device access")
    def test_real_protocol_mock_device_retains_two_identical_full_private_dumps(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = backup.Journal(Path(temp) / "run")
            api = FakeStorage()
            result = backup.perform_backup(api, BOOTSTRAP.read_bytes(), journal)
            outcome = backup.write_report(journal, result)
            journal.close()
            first = (journal.directory / "flash-pass-1.bin").read_bytes()
            second = (journal.directory / "flash-pass-2.bin").read_bytes()
            self.assertEqual(len(first), 0x100000)
            self.assertEqual(first, second)
            self.assertEqual(api.reads, 4096)
            self.assertEqual(len(api.blocks), 47)
            self.assertEqual(result["dumps"][0]["sha256"], hashlib.sha256(first).hexdigest())
            report_raw = (journal.directory / "report.json").read_bytes()
            self.assertEqual(outcome["report_sha256"], hashlib.sha256(report_raw).hexdigest())
            events = [json.loads(line) for line in (journal.directory / "events.jsonl").read_text().splitlines()]
            self.assertEqual([event["sequence"] for event in events], list(range(len(events))))
            self.assertNotIn("private-serial", (journal.directory / "events.jsonl").read_text())
            self.assertFalse(any(call[0] == "cdb" and call[1][:2] in (b"\xfb\0", b"\xfb\1", b"\xfb\4") for call in api.calls))
            with self.assertRaises(FileExistsError):
                backup.write_report(journal, result)

    @unittest.skipUnless(BOOTSTRAP.is_file(), "Pinned bootstrap acquisition not available; no device access")
    def test_mismatched_second_dump_preserves_both_files_and_no_verified_event(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = MemoryJournal(temp)
            api = FakeStorage(mismatch=True)
            with self.assertRaises(protocol.RomProtocolError):
                backup.perform_backup(api, BOOTSTRAP.read_bytes(), journal)
            self.assertEqual((Path(temp) / "flash-pass-1.bin").stat().st_size, 0x100000)
            self.assertEqual((Path(temp) / "flash-pass-2.bin").stat().st_size, 0x100000)
            self.assertFalse(any(event["event"] == "backup_verified" for event in journal.events))
            self.assertEqual(sum(call[0] == "close" for call in api.calls), 1)

    def test_invalid_blob_is_refused_before_enumeration_or_private_output(self):
        api = Mock()
        with self.assertRaises(protocol.RomProtocolError):
            backup.perform_backup(api, b"invalid", MemoryJournal())
        api.enumerate.assert_not_called()
        with patch.object(backup, "WindowsDiskAPI") as factory, patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(backup.main(["backup", "--expected-bootstrap-sha256", "0" * 64]), 1)
        factory.assert_not_called()

    def test_private_output_refuses_workspace_escape_and_journal_is_exclusive(self):
        with self.assertRaises(backup.BackupError):
            backup.private_root(backup.ROOT / "artifacts")
        self.assertEqual(backup.private_root(backup.ROOT / "private/rom-backups"), backup.ROOT / "private/rom-backups")
        with tempfile.TemporaryDirectory() as temp:
            journal = backup.Journal(Path(temp) / "run")
            journal.close()
            with self.assertRaises(FileExistsError):
                backup.Journal(journal.directory)


if __name__ == "__main__":
    unittest.main()
