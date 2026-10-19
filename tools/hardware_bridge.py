#!/usr/bin/env python3
"""Windows USB-MIDI bridge: enumerate or issue only FM-1's documented identity read.

No upload, reboot, bank-write or arbitrary-message command is exposed. Hardware
operations are explicit CLI actions; importing this module opens no DLL or port.
"""
from __future__ import annotations

import argparse
from collections import deque
import ctypes as ct
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_REQUEST = bytes.fromhex("F0 00 32 45 00 00 00 40 7F F7")
FM1_NAME = re.compile(r"(?<![A-Za-z0-9])FM[- ]?1(?:\s+Midi)?(?![A-Za-z0-9])", re.I)
DWORD, WORD, UINT, UINTPTR = ct.c_uint32, ct.c_uint16, ct.c_uint32, ct.c_size_t
HANDLE = ct.c_void_p
MIM_LONGDATA, MIM_LONGERROR, MHDR_DONE, MHDR_INQUEUE = 0x3C4, 0x3C6, 1, 4


class MidiHeader(ct.Structure):
    _fields_ = [("lpData", ct.c_void_p), ("dwBufferLength", DWORD),
                ("dwBytesRecorded", DWORD), ("dwUser", UINTPTR), ("dwFlags", DWORD),
                ("lpNext", ct.c_void_p), ("reserved", UINTPTR), ("dwOffset", DWORD),
                ("dwReserved", UINTPTR * 8)]


class MidiInCaps(ct.Structure):
    _fields_ = [("wMid", WORD), ("wPid", WORD), ("vDriverVersion", DWORD),
                ("szPname", ct.c_wchar * 32), ("dwSupport", DWORD)]


class MidiOutCaps(ct.Structure):
    _fields_ = [("wMid", WORD), ("wPid", WORD), ("vDriverVersion", DWORD),
                ("szPname", ct.c_wchar * 32), ("wTechnology", WORD),
                ("wVoices", WORD), ("wNotes", WORD), ("wChannelMask", WORD),
                ("dwSupport", DWORD)]


class BridgeError(RuntimeError):
    pass


class WinMMError(BridgeError):
    """Preserve API/result identity for narrowly scoped lifecycle decisions."""
    def __init__(self, operation: str, result: int):
        self.operation, self.result = operation, result
        super().__init__(f"{operation} returned MMRESULT {result}")


def select_pair(devices: dict, input_id: int | None = None,
                output_id: int | None = None) -> tuple[dict, dict]:
    """Never guess among multiple devices or silently open a non-FM-1 endpoint."""
    chosen = []
    for direction, requested in (("inputs", input_id), ("outputs", output_id)):
        candidates = [row for row in devices[direction] if FM1_NAME.search(row["name"])]
        if requested is not None:
            candidates = [row for row in candidates if row["id"] == requested]
        if len(candidates) != 1:
            raise BridgeError(f"Need one matching FM-1 {direction}; found {len(candidates)}. "
                              "Use explicit IDs from enumeration when ambiguous.")
        chosen.append(candidates[0])
    return chosen[0], chosen[1]


class SysexAssembler:
    """Bounded stream assembly: tolerate real-time bytes; reject broken framing."""
    def __init__(self, maximum: int = 1024):
        self.maximum = maximum
        self.pending = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        frames = []
        for byte in chunk:
            if byte >= 0xF8:
                continue
            if byte == 0xF0:
                if self.pending:
                    raise BridgeError("Nested SysEx start before previous message ended")
                self.pending.append(byte)
            elif not self.pending:
                raise BridgeError("Unframed bytes in long MIDI input")
            elif byte == 0xF7:
                if len(self.pending) >= self.maximum:
                    raise BridgeError("Identity response exceeds bounded input size")
                self.pending.append(byte)
                frames.append(bytes(self.pending)); self.pending.clear()
            elif byte & 0x80:
                raise BridgeError("Unexpected status inside SysEx")
            else:
                self.pending.append(byte)
            if len(self.pending) > self.maximum:
                raise BridgeError("Identity response exceeds bounded input size")
        return frames


class WinMM:
    """Thin standard-library binding; no callbacks invoke multimedia APIs."""
    def __init__(self):
        if os.name != "nt":
            raise BridgeError("Physical bridge requires Windows")
        if ct.sizeof(MidiHeader) != (120 if ct.sizeof(HANDLE) == 8 else 64):
            raise BridgeError("Unexpected MIDIHDR ABI")
        self.dll = ct.WinDLL("winmm.dll")
        self.callback_type = ct.WINFUNCTYPE(None, HANDLE, UINT, UINTPTR, UINTPTR, UINTPTR)
        signatures = {
            "midiInGetNumDevs": [], "midiOutGetNumDevs": [],
            "midiInGetDevCapsW": [UINTPTR, ct.POINTER(MidiInCaps), UINT],
            "midiOutGetDevCapsW": [UINTPTR, ct.POINTER(MidiOutCaps), UINT],
            "midiInOpen": [ct.POINTER(HANDLE), UINT, UINTPTR, UINTPTR, DWORD],
            "midiOutOpen": [ct.POINTER(HANDLE), UINT, UINTPTR, UINTPTR, DWORD],
        }
        for direction in ("In", "Out"):
            for suffix in ("PrepareHeader", "UnprepareHeader"):
                signatures[f"midi{direction}{suffix}"] = [HANDLE, ct.POINTER(MidiHeader), UINT]
            for suffix in ("Reset", "Close"):
                signatures[f"midi{direction}{suffix}"] = [HANDLE]
        signatures.update(midiInAddBuffer=[HANDLE, ct.POINTER(MidiHeader), UINT],
                          midiOutLongMsg=[HANDLE, ct.POINTER(MidiHeader), UINT],
                          midiInStart=[HANDLE], midiInStop=[HANDLE])
        for name, arguments in signatures.items():
            function = getattr(self.dll, name)
            function.argtypes, function.restype = arguments, UINT

    def checked(self, name, *args):
        result = getattr(self.dll, name)(*args)
        if result:
            raise WinMMError(name, result)

    def enumerate(self) -> dict:
        result = {"inputs": [], "outputs": []}
        for direction, caps_type, key in (("In", MidiInCaps, "inputs"),
                                           ("Out", MidiOutCaps, "outputs")):
            count = getattr(self.dll, f"midi{direction}GetNumDevs")()
            if count > 1024:
                raise BridgeError("Unreasonable Windows MIDI endpoint count")
            for index in range(count):
                caps = caps_type()
                self.checked(f"midi{direction}GetDevCapsW", index, ct.byref(caps), ct.sizeof(caps))
                # These are WinMM driver IDs, NOT USB VID/PID identifiers.
                result[key].append({"id": index, "name": caps.szPname,
                                    "driver_manufacturer_id": caps.wMid,
                                    "driver_product_id": caps.wPid,
                                    "driver_version": caps.vDriverVersion})
        return result


class IdentitySession:
    def __init__(self, backend: WinMM, input_id: int, output_id: int, events: list):
        self.api, self.input_id, self.output_id = backend, input_id, output_id
        self.events = events
        self.input, self.output = HANDLE(), HANDLE()
        self.buffers = []
        self.out_buffer = None
        self.received = deque()
        self.short_received = deque()
        self.short_overflow = 0
        self.capture_short = False
        self.callback_overflow = False
        self.callback = self.api.callback_type(self._callback)

    def _callback(self, handle, message, instance, parameter, timestamp):
        if message in (0x3C3,0x3C5) and self.capture_short:
            if len(self.short_received)>=4096:self.short_overflow+=1
            else:self.short_received.append((int(parameter),int(timestamp),message==0x3C5))
            return
        if message not in (MIM_LONGDATA, MIM_LONGERROR):
            return
        if len(self.received) >= 64:
            self.callback_overflow = True
            return
        self.received.append((message, parameter, timestamp))

    def __enter__(self):
        try:
            self.api.checked("midiInOpen", ct.byref(self.input), self.input_id,
                             ct.cast(self.callback, ct.c_void_p).value, 0, 0x30000)
            self.events.append({"event": "input_opened", "id": self.input_id})
            for _ in range(4):
                storage = ct.create_string_buffer(1024)
                header = MidiHeader(lpData=ct.addressof(storage), dwBufferLength=1024)
                self.api.checked("midiInPrepareHeader", self.input, ct.byref(header), ct.sizeof(header))
                self.buffers.append((header, storage))
                self.api.checked("midiInAddBuffer", self.input, ct.byref(header), ct.sizeof(header))
            self.api.checked("midiInStart", self.input)
            self.api.checked("midiOutOpen", ct.byref(self.output), self.output_id, 0, 0, 0)
            self.events.append({"event": "output_opened", "id": self.output_id})
            return self
        except BaseException:
            self.close()
            raise

    def query(self, timeout: float) -> list[bytes]:
        # No arbitrary-byte sender: this transport can emit only the audited read.
        storage = ct.create_string_buffer(IDENTITY_REQUEST)
        header = MidiHeader(lpData=ct.addressof(storage), dwBufferLength=len(IDENTITY_REQUEST))
        self.api.checked("midiOutPrepareHeader", self.output, ct.byref(header), ct.sizeof(header))
        self.out_buffer = (header, storage)
        self.api.checked("midiOutLongMsg", self.output, ct.byref(header), ct.sizeof(header))
        self.events.append({"event": "identity_query_sent", "hex": IDENTITY_REQUEST.hex(" ")})
        assembler, frames = SysexAssembler(), []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.callback_overflow:
                raise BridgeError("MIDI callback queue overflowed")
            while self.received:
                message, address, timestamp = self.received.popleft()
                pair = next((p for p in self.buffers if ct.addressof(p[0]) == address), None)
                if pair is None:
                    raise BridgeError("Driver returned an unknown input buffer")
                incoming, data = pair
                if message == MIM_LONGERROR:
                    raise BridgeError("Driver reported malformed long MIDI input")
                size = incoming.dwBytesRecorded
                if size > incoming.dwBufferLength:
                    raise BridgeError("Driver reported an out-of-bounds input length")
                chunk = bytes(data.raw[:size])
                if chunk:
                    self.events.append({"event": "received", "timestamp_ms": timestamp,
                                        "hex": chunk.hex(" ")})
                    frames.extend(assembler.feed(chunk))
                incoming.dwBytesRecorded = 0
                self.api.checked("midiInAddBuffer", self.input, ct.byref(incoming), ct.sizeof(incoming))
                if len(frames) > 8:
                    raise BridgeError("Unexpected number of identity responses")
            # Await send completion as well as input, before releasing headers.
            if frames and header.dwFlags & MHDR_DONE:
                if assembler.pending:
                    raise BridgeError("Trailing incomplete identity response")
                return frames
            time.sleep(.01)
        raise BridgeError("Timed out waiting for a complete FM-1 identity reply")

    def close(self):
        failures = []
        self.cleanup_results = []
        def cleanup(name, *args):
            try:
                self.api.checked(name, *args)
                self.cleanup_results.append({"operation": name, "ok": True})
                return True
            except Exception as error:
                self.cleanup_results.append({"operation": name, "ok": False,
                                             "result": error.result if isinstance(error, WinMMError) else None,
                                             "error": str(error)})
                failures.append(str(error)); return False
        if self.input:
            cleanup("midiInStop", self.input)
            cleanup("midiInReset", self.input)
            for header, data in self.buffers:
                cleanup("midiInUnprepareHeader", self.input, ct.byref(header), ct.sizeof(header))
            if cleanup("midiInClose", self.input):
                self.input = HANDLE()
        if self.output:
            if self.out_buffer:
                header, data = self.out_buffer
                if header.dwFlags & MHDR_INQUEUE:
                    # Emergency driver-buffer cancellation; may silence notes.
                    self.events.append({"event": "output_reset_required", "may_silence_notes": True})
                    cleanup("midiOutReset", self.output)
                cleanup("midiOutUnprepareHeader", self.output, ct.byref(header), ct.sizeof(header))
            if cleanup("midiOutClose", self.output):
                self.output = HANDLE()
        self.events.append({"event": "ports_closed", "errors": failures})
        if failures:
            # Keep ctypes buffers/callback alive until process exit if the driver
            # failed to release them; never free driver-owned memory prematurely.
            _unreleased_sessions.append(self)
        return failures

    def __exit__(self, kind, error, traceback):
        failures = self.close()
        if failures and error is None:
            raise BridgeError("MIDI cleanup failed: " + "; ".join(failures))


_unreleased_sessions = []


def write_report(report: dict, directory: Path | None = None) -> Path:
    if directory is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        directory = ROOT / "artifacts" / "hardware-bridge" / f"{stamp}-{uuid.uuid4().hex[:8]}"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "report.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2); stream.write("\n")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enumerate", "identify"))
    parser.add_argument("--unit-label", default="FMER Test01")
    parser.add_argument("--input-id", type=int)
    parser.add_argument("--output-id", type=int)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 30:
        parser.error("timeout must be between 1 and 30 seconds")
    report = {"schema_version": 1, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "action": args.action, "unit_label": args.unit_label, "status": "error",
              "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "events": [], "flash_writes": False, "preset_writes": False,
              "device_commands": "identity_read_only" if args.action == "identify" else "none"}
    try:
        api = WinMM()
        report["endpoints"] = api.enumerate()
        if args.action == "identify":
            input_device, output_device = select_pair(report["endpoints"], args.input_id, args.output_id)
            report["selected"] = {"input": input_device, "output": output_device}
            # Import the independently reviewed codec before opening any port.
            import device_protocol
            parse_identity_reply = device_protocol.parse_identity_reply
            if device_protocol.IDENTITY_QUERY != IDENTITY_REQUEST:
                raise BridgeError("Transport and protocol identity-request constants disagree")
            report["protocol_sha256"] = hashlib.sha256(Path(device_protocol.__file__).read_bytes()).hexdigest()
            with IdentitySession(api, input_device["id"], output_device["id"], report["events"]) as session:
                frames = session.query(args.timeout)
            report["responses_hex"] = [frame.hex(" ") for frame in frames]
            identities = [parse_identity_reply(frame) for frame in frames]
            if len(identities) != 1:
                raise BridgeError("Expected exactly one validated identity reply")
            report["identity"] = identities[0]
        report["status"] = "success"
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    target = write_report(report)
    print(json.dumps({"status": report["status"], "report": str(target),
                      "identity": report.get("identity"), "error": report.get("error")}))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
