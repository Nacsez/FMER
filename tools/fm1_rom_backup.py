#!/usr/bin/env python3
"""FM-1 ROM backup through the existing Windows USB storage driver.

No MIDI entry, driver installation, flash erase/write or arbitrary CDB CLI.
Importing does not load a Windows DLL or access a device. Native Windows ROM
compatibility remains a bench question until an exact-device run succeeds.
Windows ABI/constants checked against Windows SDK 10.0.26100.0 headers.
Protocol: pinned FM-1 Transporter and jl-uboot-tool; see fm1_rom_protocol.py.
"""
from __future__ import annotations

import argparse
import ctypes as ct
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
DWORD, WORD, BYTE, BOOL = ct.c_uint32, ct.c_uint16, ct.c_uint8, ct.c_int32
HANDLE = ct.c_void_p
INVALID_HANDLE = ct.c_void_p(-1).value
IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014
IOCTL_STORAGE_QUERY_PROPERTY = 0x2D1400
ROM_INSTANCE = re.compile(r"USB\\VID_4C4A&PID_8057(?:&[A-Z0-9_]+)*\\[^\\]+", re.I)
INQUIRY = bytes.fromhex("12 00 00 00 24 00")
FLASH_BYTES, BLOCK_BYTES = 0x100000, 512


class BackupError(RuntimeError):
    pass


class GUID(ct.Structure):
    _fields_ = [("Data1", DWORD), ("Data2", WORD), ("Data3", WORD), ("Data4", BYTE * 8)]


DISK_GUID = GUID.from_buffer_copy(uuid.UUID("53f56307-b6bf-11d0-94f2-00a0c91efb8b").bytes_le)


class DeviceInfo(ct.Structure):
    _fields_ = [("cbSize", DWORD), ("ClassGuid", GUID), ("DevInst", DWORD), ("Reserved", ct.c_size_t)]


class DeviceInterface(ct.Structure):
    _fields_ = [("cbSize", DWORD), ("InterfaceClassGuid", GUID), ("Flags", DWORD), ("Reserved", ct.c_size_t)]


class ScsiPassThroughDirect(ct.Structure):
    _fields_ = [("Length", WORD), ("ScsiStatus", BYTE), ("PathId", BYTE), ("TargetId", BYTE),
                ("Lun", BYTE), ("CdbLength", BYTE), ("SenseInfoLength", BYTE), ("DataIn", BYTE),
                ("DataTransferLength", DWORD), ("TimeOutValue", DWORD), ("DataBuffer", HANDLE),
                ("SenseInfoOffset", DWORD), ("Cdb", BYTE * 16)]


class ScsiPacket(ct.Structure):
    _fields_ = [("spt", ScsiPassThroughDirect), ("sense", BYTE * 32)]


def text_hash(value: str) -> str:
    return hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Candidate:
    path: str
    instance: str
    usb_instance: str
    location_paths: tuple[str, ...]
    disk_service: str
    usb_service: str

    def public(self):
        return {"path_sha256": text_hash(self.path), "instance_sha256": text_hash(self.instance),
                "usb_instance_sha256": text_hash(self.usb_instance), "location_paths": list(self.location_paths),
                "location_sha256": text_hash("\n".join(self.location_paths)),
                "disk_service": self.disk_service, "usb_service": self.usb_service,
                "usb_vid": "4C4A", "usb_pid": "8057"}


def select_candidate(candidates: list[Candidate]) -> Candidate:
    matching = [item for item in candidates if ROM_INSTANCE.fullmatch(item.usb_instance) and
                item.disk_service.casefold() == "disk" and item.usb_service.casefold() == "usbstor" and
                item.location_paths and item.path and item.instance]
    if len(matching) != 1:
        raise BackupError(f"Need exactly one ROM disk with existing USBSTOR binding; found {len(matching)}")
    return matching[0]


class Journal:
    """Private exclusive directory and durable metadata; never log flash bytes."""
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.stream = (self.directory / "events.jsonl").open("x", encoding="utf-8")
        self.sequence = 0

    def record(self, event: str, **values):
        self.stream.write(json.dumps({"sequence": self.sequence, "utc": datetime.now(timezone.utc).isoformat(),
                                      "event": event, **values}, allow_nan=False) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.sequence += 1

    def close(self):
        self.stream.close()


class WindowsDiskAPI:
    """Typed native interfaces. Enumeration reads PnP metadata, never all disks."""
    def __init__(self):
        if os.name != "nt":
            raise BackupError("ROM storage transport requires Windows")
        wide, ptr = ct.sizeof(ct.c_wchar), ct.sizeof(HANDLE)
        if wide != 2 or ct.sizeof(ScsiPassThroughDirect) != (56 if ptr == 8 else 44):
            raise BackupError("Unexpected Windows SCSI ABI")
        self.setup = ct.WinDLL("setupapi.dll", use_last_error=True)
        self.cfg = ct.WinDLL("cfgmgr32.dll", use_last_error=True)
        self.kernel = ct.WinDLL("kernel32.dll", use_last_error=True)
        signatures = [
            (self.setup, "SetupDiGetClassDevsW", [ct.POINTER(GUID), ct.c_wchar_p, HANDLE, DWORD], HANDLE),
            (self.setup, "SetupDiEnumDeviceInterfaces", [HANDLE, HANDLE, ct.POINTER(GUID), DWORD, ct.POINTER(DeviceInterface)], BOOL),
            (self.setup, "SetupDiGetDeviceInterfaceDetailW", [HANDLE, ct.POINTER(DeviceInterface), HANDLE, DWORD,
                                                             ct.POINTER(DWORD), ct.POINTER(DeviceInfo)], BOOL),
            (self.setup, "SetupDiDestroyDeviceInfoList", [HANDLE], BOOL),
            (self.cfg, "CM_Get_Device_IDW", [DWORD, ct.c_wchar_p, DWORD, DWORD], DWORD),
            (self.cfg, "CM_Get_Parent", [ct.POINTER(DWORD), DWORD, DWORD], DWORD),
            (self.cfg, "CM_Get_DevNode_Registry_PropertyW", [DWORD, DWORD, ct.POINTER(DWORD), HANDLE, ct.POINTER(DWORD), DWORD], DWORD),
            (self.kernel, "CreateFileW", [ct.c_wchar_p, DWORD, DWORD, HANDLE, DWORD, DWORD, HANDLE], HANDLE),
            (self.kernel, "CloseHandle", [HANDLE], BOOL),
            (self.kernel, "DeviceIoControl", [HANDLE, DWORD, HANDLE, DWORD, HANDLE, DWORD, ct.POINTER(DWORD), HANDLE], BOOL),
        ]
        for dll, name, arguments, result in signatures:
            function = getattr(dll, name)
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def last_error(operation):
        # Do not include device path strings or serial numbers in errors.
        return BackupError(f"{operation} failed with Win32 error {ct.get_last_error()}")

    def instance_id(self, devinst: int) -> str:
        result = ct.create_unicode_buffer(4096)
        code = self.cfg.CM_Get_Device_IDW(devinst, result, len(result), 0)
        if code:
            raise BackupError(f"CM_Get_Device_IDW failed with CONFIGRET {code}")
        return result.value

    def property_strings(self, devinst: int, prop: int) -> tuple[str, ...]:
        kind, length = DWORD(), DWORD()
        code = self.cfg.CM_Get_DevNode_Registry_PropertyW(devinst, prop, ct.byref(kind), None, ct.byref(length), 0)
        if code == 0x25:  # CR_NO_SUCH_VALUE
            return ()
        if code != 0x1A or not 2 <= length.value <= 65536 or length.value % 2:
            raise BackupError(f"Invalid PnP property size/result: {code}")
        buffer = ct.create_string_buffer(length.value)
        capacity = length.value
        code = self.cfg.CM_Get_DevNode_Registry_PropertyW(devinst, prop, ct.byref(kind), buffer, ct.byref(length), 0)
        if code or kind.value not in (1, 7) or not 2 <= length.value <= capacity or length.value % 2:
            raise BackupError(f"Invalid PnP property data/result: {code}")
        value = bytes(buffer.raw[:length.value]).decode("utf-16-le", errors="strict")
        if not value.endswith("\0"):
            raise BackupError("PnP string property is not terminated")
        return tuple(part for part in value.rstrip("\0").split("\0") if part)

    def candidate_for(self, path: str, devinst: int) -> Candidate | None:
        instance = self.instance_id(devinst)
        service = self.property_strings(devinst, 0x05)  # CM_DRP_SERVICE
        disk_service = service[0] if len(service) == 1 else ""
        node, seen = devinst, set()
        for _ in range(32):
            if node in seen:
                raise BackupError("PnP parent cycle")
            seen.add(node)
            identity = self.instance_id(node)
            if ROM_INSTANCE.fullmatch(identity):
                driver = self.property_strings(node, 0x05)
                if len(driver) == 1 and driver[0].casefold() == "usbstor":
                    locations = self.property_strings(node, 0x24)  # CM_DRP_LOCATION_PATHS
                    return Candidate(path, instance, identity, locations, disk_service, driver[0])
            parent = DWORD()
            code = self.cfg.CM_Get_Parent(ct.byref(parent), node, 0)
            if code == 0x0D:  # CR_NO_SUCH_DEVNODE: root has no parent
                return None
            if code:
                raise BackupError(f"CM_Get_Parent failed with CONFIGRET {code}")
            node = parent.value
        raise BackupError("PnP parent chain exceeds bound")

    def enumerate(self) -> list[Candidate]:
        group = self.setup.SetupDiGetClassDevsW(ct.byref(DISK_GUID), None, None, 0x12)
        if group == INVALID_HANDLE or not group:
            raise self.last_error("SetupDiGetClassDevsW")
        result = []
        try:
            for index in range(1024):
                interface = DeviceInterface(cbSize=ct.sizeof(DeviceInterface))
                if not self.setup.SetupDiEnumDeviceInterfaces(group, None, ct.byref(DISK_GUID), index, ct.byref(interface)):
                    if ct.get_last_error() == 259:  # ERROR_NO_MORE_ITEMS
                        return result
                    raise self.last_error("SetupDiEnumDeviceInterfaces")
                if not interface.Flags & 1 or interface.Flags & 4:
                    continue
                required, info = DWORD(), DeviceInfo(cbSize=ct.sizeof(DeviceInfo))
                ok = self.setup.SetupDiGetDeviceInterfaceDetailW(group, ct.byref(interface), None, 0,
                                                                 ct.byref(required), ct.byref(info))
                if ok or ct.get_last_error() != 122 or not 8 <= required.value <= 65536:
                    raise BackupError("Invalid device interface detail size/result")
                detail = ct.create_string_buffer(required.value)
                # WCHAR path starts at offset4; cbSize is8 on Win64,6 on Win32.
                ct.cast(detail, ct.POINTER(DWORD))[0] = 8 if ct.sizeof(HANDLE) == 8 else 6
                capacity = required.value
                if not self.setup.SetupDiGetDeviceInterfaceDetailW(group, ct.byref(interface), detail, capacity,
                                                                    ct.byref(required), ct.byref(info)):
                    raise self.last_error("SetupDiGetDeviceInterfaceDetailW")
                if not 8 <= required.value <= capacity or (required.value - 4) % 2:
                    raise BackupError("Invalid device interface detail length")
                path = bytes(detail.raw[4:required.value]).decode("utf-16-le", errors="strict")
                if not path.endswith("\0") or "\0" in path.rstrip("\0"):
                    raise BackupError("Malformed device interface path")
                candidate = self.candidate_for(path.rstrip("\0"), info.DevInst)
                if candidate is not None:
                    result.append(candidate)
            raise BackupError("Disk interface enumeration exceeds bound")
        finally:
            if not self.setup.SetupDiDestroyDeviceInfoList(group):
                raise self.last_error("SetupDiDestroyDeviceInfoList")

    def open(self, path: str):
        handle = self.kernel.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
        if handle == INVALID_HANDLE or not handle:
            raise self.last_error("CreateFileW exact ROM disk")
        return handle

    def close(self, handle):
        if not self.kernel.CloseHandle(handle):
            raise self.last_error("CloseHandle ROM disk")

    def ioctl(self, handle, code, input_buffer, input_bytes, output_buffer, output_bytes) -> int:
        returned = DWORD()
        if not self.kernel.DeviceIoControl(handle, code, input_buffer, input_bytes, output_buffer,
                                            output_bytes, ct.byref(returned), None):
            raise self.last_error("DeviceIoControl")
        if returned.value > output_bytes:
            raise BackupError("Driver returned more metadata than the supplied buffer")
        return returned.value

    def alignment(self, handle) -> int:
        query = ct.create_string_buffer((1).to_bytes(4, "little") + b"\0" * 8)  # StorageAdapterProperty
        output = ct.create_string_buffer(1024)
        returned = self.ioctl(handle, IOCTL_STORAGE_QUERY_PROPERTY, query, 12, output, len(output))
        if returned < 20:
            raise BackupError("Storage adapter descriptor is truncated")
        raw = output.raw
        version, size, maximum, pages, mask = [int.from_bytes(raw[i:i + 4], "little") for i in range(0, 20, 4)]
        if not 20 <= version <= size <= returned or maximum < BLOCK_BYTES or mask > 65535 or mask & (mask + 1):
            raise BackupError("Storage adapter descriptor cannot support bounded aligned transfers")
        return mask


class RomSession:
    def __init__(self, api, candidate: Candidate, journal, *, bootstrap: bytes | None = None):
        self.api, self.candidate, self.journal = api, candidate, journal
        self.handle, self.admitted, self.alignment_mask = None, False, None
        self.failed = False
        self.bootstrap = bootstrap
        if bootstrap is not None:
            import fm1_rom_protocol as protocol
            protocol.validate_bootstrap(bootstrap)

    def __enter__(self):
        if select_candidate([self.candidate]) != self.candidate:
            raise BackupError("Invalid ROM candidate")
        self.journal.record("open_intent", candidate=self.candidate.public())
        self.handle = self.api.open(self.candidate.path)
        try:
            if select_candidate(self.api.enumerate()) != self.candidate:
                raise BackupError("ROM device changed between enumeration and open")
            self.alignment_mask = self.api.alignment(self.handle)
            identity = self.execute(INQUIRY, data_in=36)
            import fm1_rom_protocol as protocol
            try:
                protocol.parse_inquiry(identity)
            except protocol.RomProtocolError as error:
                raise BackupError("Opened ROM disk failed exact WL82/UBOOT1.00/1.00 inquiry") from error
            if identity[0] != 0:
                raise BackupError("Opened ROM disk failed exact WL82/UBOOT1.00/1.00 inquiry")
            if select_candidate(self.api.enumerate()) != self.candidate:
                raise BackupError("ROM device changed while validating opened handle")
            self.admitted = True
            self.journal.record("opened_rom_verified", vendor="WL82", product="UBOOT1.00", revision="1.00",
                                candidate=self.candidate.public(), alignment_mask=self.alignment_mask)
            return self
        except BaseException:
            self.close()
            raise

    def execute(self, cdb: bytes, data_out: bytes | None = None, data_in: int = 0) -> bytes:
        if self.failed:
            raise BackupError("ROM session failed previously; no further commands permitted")
        try:
            return self._execute(cdb, data_out, data_in)
        except BaseException:
            self.failed = True
            raise

    def _execute(self, cdb: bytes, data_out: bytes | None, data_in: int) -> bytes:
        if self.handle is None or type(cdb) is not bytes or not 1 <= len(cdb) <= 16:
            raise BackupError("Closed ROM session or invalid CDB")
        if type(data_in) is not int or not 0 <= data_in <= BLOCK_BYTES or (data_out is not None and type(data_out) is not bytes):
            raise BackupError("Invalid bounded SCSI transfer")
        if data_out is not None and (data_in or not 1 <= len(data_out) <= BLOCK_BYTES):
            raise BackupError("Bidirectional or oversized SCSI transfer refused")
        if cdb == INQUIRY:
            if data_out is not None or data_in != 36:
                raise BackupError("Invalid inquiry transfer")
        else:
            if not self.admitted:
                raise BackupError("Vendor command before exact opened-handle inquiry")
            # Protocol constrains opcodes, addresses, sizes and checksum; this
            # transport additionally binds the exact pinned RAM payload.
            import fm1_rom_protocol as protocol
            kind = protocol.validate_transfer(cdb, data_out=data_out, data_in=data_in)
            if kind == "write_ram":
                offset = int.from_bytes(cdb[2:6], "big") - protocol.RAM_BASE
                if self.bootstrap is None or data_out != self.bootstrap[offset:offset + len(data_out)]:
                    raise BackupError("RAM upload differs from the exact pinned bootstrap bytes")
        length = len(data_out) if data_out is not None else data_in
        if not length or self.alignment_mask is None:
            raise BackupError("Missing transfer data or verified adapter alignment")
        storage = ct.create_string_buffer(length + self.alignment_mask)
        address = (ct.addressof(storage) + self.alignment_mask) & ~self.alignment_mask
        if data_out is not None:
            ct.memmove(address, data_out, length)
        packet = ScsiPacket()
        spt = packet.spt
        spt.Length, spt.CdbLength, spt.SenseInfoLength = ct.sizeof(ScsiPassThroughDirect), len(cdb), 32
        spt.DataIn, spt.DataTransferLength, spt.TimeOutValue = (0 if data_out is not None else 1), length, 2
        spt.DataBuffer, spt.SenseInfoOffset = address, ScsiPacket.sense.offset
        for index, byte in enumerate(cdb):
            spt.Cdb[index] = byte
        self.journal.record("scsi_intent", cdb=cdb.hex(" "), direction="out" if data_out is not None else "in",
                            bytes=length, output_sha256=hashlib.sha256(data_out).hexdigest() if data_out is not None else None,
                            timeout_seconds=2)
        started = time.monotonic()
        returned = self.api.ioctl(self.handle, IOCTL_SCSI_PASS_THROUGH_DIRECT, ct.byref(packet), ct.sizeof(packet),
                                  ct.byref(packet), ct.sizeof(packet))
        elapsed = time.monotonic() - started
        sense = bytes(packet.sense[:min(spt.SenseInfoLength, 32)])
        self.journal.record("scsi_result", cdb=cdb.hex(" "), status=spt.ScsiStatus,
                            transferred=spt.DataTransferLength, metadata_bytes=returned,
                            sense_hex=sense.hex(), elapsed_seconds=elapsed)
        if (returned < ct.sizeof(ScsiPassThroughDirect) or spt.Length != ct.sizeof(ScsiPassThroughDirect) or
                spt.SenseInfoLength > 32 or spt.SenseInfoOffset != ScsiPacket.sense.offset or
                (spt.SenseInfoLength and returned < spt.SenseInfoOffset + spt.SenseInfoLength) or
                spt.DataBuffer != address or spt.CdbLength != len(cdb) or bytes(spt.Cdb[:len(cdb)]) != cdb or
                spt.DataIn != (0 if data_out is not None else 1) or spt.TimeOutValue != 2):
            raise BackupError("Malformed SCSI completion metadata")
        if spt.ScsiStatus or any(sense) or spt.DataTransferLength != length or elapsed > 3.0:
            raise BackupError("SCSI status, sense, exact transfer length or deadline failed")
        return bytes(ct.string_at(address, length)) if data_in else b""

    def close(self):
        if self.handle is not None:
            handle = self.handle
            self.api.close(handle)
            self.handle, self.admitted = None, False
            self.journal.record("rom_session_closed")

    def __exit__(self, *args):
        self.close()


def perform_backup(api, blob: bytes, journal, *, expected_location_sha256: str | None = None) -> dict:
    """Exactly two full reads, retaining even incomplete/mismatched private files."""
    import fm1_rom_protocol as protocol
    protocol.validate_bootstrap(blob)
    if expected_location_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_location_sha256):
        raise BackupError("Expected location must be a lowercase SHA-256")
    candidate = select_candidate(api.enumerate())
    public = candidate.public()
    if expected_location_sha256 is not None and public["location_sha256"] != expected_location_sha256:
        raise BackupError("Unique ROM disk is not at the pinned physical location")
    journal.record("backup_intent", candidate=public, flash_bytes=FLASH_BYTES, passes=2,
                   bootstrap_sha256=hashlib.sha256(blob).hexdigest(), flash_writes_allowed=False)

    def progress(event, **values):
        if isinstance(event, dict):
            details = dict(event)
            name = details.pop("event", "protocol_progress")
            if "sequence" in details:
                details["protocol_sequence"] = details.pop("sequence")
            journal.record("protocol_" + name, **details)
        else:
            journal.record("protocol_" + event, **values)

    dumps, dump_reports = [], []
    with RomSession(api, candidate, journal, bootstrap=blob) as session:
        reader = protocol.RomReader(session.execute, progress=progress)
        inquiry = reader.inquiry()
        info = reader.start_loader(blob)
        for pass_number in (1, 2):
            path = journal.directory / f"flash-pass-{pass_number}.bin"
            position, digest = 0, hashlib.sha256()
            journal.record("dump_file_intent", file=path.name, pass_number=pass_number)
            with path.open("xb") as stream:
                def chunk(number, offset, data):
                    nonlocal position
                    if (number != pass_number or offset != position or type(data) is not bytes or
                            len(data) != BLOCK_BYTES or position > FLASH_BYTES - len(data)):
                        raise BackupError("Dump callback exceeded the exact sequential flash extent")
                    if stream.write(data) != len(data):
                        raise BackupError("Private dump write was incomplete")
                    digest.update(data)
                    position += len(data)
                content = reader.read_full_flash(pass_number=pass_number, on_chunk=chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if (type(content) is not bytes or len(content) != FLASH_BYTES or position != FLASH_BYTES or
                    digest.hexdigest() != hashlib.sha256(content).hexdigest()):
                raise BackupError("Full dump and retained private bytes disagree")
            dump_report = {"file": path.name, "bytes": position, "sha256": digest.hexdigest(), "pass": pass_number}
            journal.record("dump_file_complete", **dump_report)
            dumps.append(content)
            dump_reports.append(dump_report)
            reader.keepalive()
        comparison = protocol.verify_matching_dumps(dumps[0], dumps[1])
    result = {"status": "verified_double_dump", "candidate": public, "inquiry": inquiry, "loader": info,
              "dumps": dump_reports, "comparison": comparison,
              "bootstrap_sha256": hashlib.sha256(blob).hexdigest(), "flash_write_commands_sent": False,
              "limits": "Backup readback only; physical restore remains separate. Opaque RAM helper initialization may configure NOR status/quad-mode registers; absence of all hardware side effects is not claimed"}
    journal.record("backup_verified", **result)
    return result


def write_report(journal: Journal, result: dict) -> dict:
    events = journal.directory / "events.jsonl"
    report = dict(result, utc=datetime.now(timezone.utc).isoformat(),
                  events_sha256=hashlib.sha256(events.read_bytes()).hexdigest(),
                  source_sha256={name: hashlib.sha256((ROOT / "tools" / name).read_bytes()).hexdigest()
                                 for name in ("fm1_rom_backup.py", "fm1_rom_protocol.py")})
    raw = (json.dumps(report, indent=2, allow_nan=False) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    for filename, data in (("report.json", raw), ("report.sha256", (digest + "  report.json\n").encode("ascii"))):
        with (journal.directory / filename).open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return {"report": str(journal.directory / "report.json"), "report_sha256": digest, "status": report["status"]}


def private_root(path: Path) -> Path:
    intended = ROOT.resolve() / "private"
    resolved = Path(path).resolve()
    if resolved != intended and intended not in resolved.parents:
        raise BackupError("Backup output must remain under this workspace's ignored private directory")
    return resolved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enumerate", "backup"))
    parser.add_argument("--bootstrap", type=Path)
    parser.add_argument("--expected-bootstrap-sha256")
    parser.add_argument("--expected-location-sha256")
    parser.add_argument("--output-root", type=Path, default=ROOT / "private/rom-backups")
    args = parser.parse_args(argv)
    journal = None
    try:
        import fm1_rom_protocol as protocol
        blob = None
        if args.action == "backup":
            if args.bootstrap is None or args.expected_bootstrap_sha256 != protocol.BOOTSTRAP_SHA256:
                raise BackupError("Backup requires the exact pinned bootstrap path and expected SHA-256")
            with args.bootstrap.open("rb") as stream:
                blob = stream.read(protocol.BOOTSTRAP_SIZE + 1)
            protocol.validate_bootstrap(blob)
        output = private_root(args.output_root)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        journal = Journal(output / f"{stamp}-{uuid.uuid4().hex[:8]}")
        journal.record("start", action=args.action, flash_write_commands_allowed=False,
                       windows_device_qualification="unmeasured until this run is verified")
        api = WindowsDiskAPI()
        if args.action == "enumerate":
            candidates = [candidate.public() for candidate in api.enumerate()]
            result = {"status": "enumerated", "candidates": candidates, "handles_opened": False}
            journal.record("enumerated", **result)
        else:
            result = perform_backup(api, blob, journal, expected_location_sha256=args.expected_location_sha256)
        print(json.dumps(write_report(journal, result), indent=2))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        if journal is not None:
            try:
                result = {"status": "failed", "error": f"{type(error).__name__}: {error}",
                          "flash_write_commands_sent": False, "automatic_recovery_attempted": False}
                journal.record("failed", **result)
                print(json.dumps(write_report(journal, result), indent=2), file=sys.stderr)
            except Exception:
                print(f"Backup failed; preserve partial private files at {journal.directory}", file=sys.stderr)
        print(f"ROM backup stopped: {error}", file=sys.stderr)
        return 1
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
