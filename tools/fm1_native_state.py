#!/usr/bin/env python3
"""Strict offline FMERNAT1 codec and durable host backups; no MIDI/device I/O.

This format retains the current 707 target's complete editable musical state:
195 controls, 155 VCED bytes including its exact name, and all 64 mono steps.
It is not a DX7 file, FMERPST bank, browser library or whole-device image.
Physical master/octave/page, held notes, transport, effect tails and calibration
are excluded. Saving a file does not imply on-device flash persistence.

All integer fields are little endian. Exactly 784 bytes: header[32], controls
[390], VCED[155], interleaved steps[192], zero padding[15]. IEEE CRC32 covers
the entire record with header bytes28..31 zero. A valid import must stop/panic
before an atomic audio-owner adoption; this offline tool cannot perform that.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import uuid
import zlib

MAGIC = b"FMERNAT1"
SCHEMA = "fmer-native-target-state-v1"
VERSION = 1
SIZE = 784
CONTROL_COUNT = 195
CONTROLS_OFFSET = 32
VCED_OFFSET = 422
STEPS_OFFSET = 577
PADDING_OFFSET = 769
CUSTOM_PRESET = 65535
PREFIX = bytes.fromhex("F0 7D 46 4D 45 52")
STATUS_FIELDS = ("schema", "live_generation", "preset_id", "sound_dirty", "save_token", "save_acked_token",
                 "export_token", "last_import_tx", "last_import_result")
RESULT_NAMES = ("ok", "argument", "size", "format", "crc", "control", "voice", "pattern", "metadata",
                "busy", "transaction", "order", "conflict", "incomplete", "stale")
SCOPE = ("707 editable FM/VA/effects/arp/mono-pattern state; includes inactive "
         "steps and exact VCED name; excludes physical master, octave/page, "
         "held notes, pedal, playback/recording position, effect tails, counters "
         "and device calibration; host file persistence only")
FIELDS = {"schema", "version", "source_generation", "preset_id", "controls", "vced", "length", "steps"}
OP_MAX = (99,99,99,99,99,99,99,99,99,99,99,3,3,7,3,7,99,1,31,99,14)
GLOBAL_MAX = (99,99,99,99,99,99,99,99,31,7,1,99,99,99,99,1,5,7,48)
# Keep this independent of C implementation so cross-language fixtures catch
# incorrect ranges/offsets. It deliberately names all 707 native fields.
NATIVE_RANGES = (
    (0,1), (0,3), (20,20000), (0,95), (0,10000), (0,10000), (0,100), (0,10000),
    (0,100), (0,100), (0,100), (20,1000), (0,85), (0,100), (0,100), (10,1000),
    (0,100), (20,18000), (20,300), (0,1), (0,6), (1,32), (1,4), (0,100),
    (0,1), (50,75), (1,64), (0,63), (0,128), (1,127), (1,100), (1,4),
    (0,1), (0,16), (0,100))


class NativeStateError(ValueError):
    """Invalid or unsupported native record; caller must retain prior state."""


def _u7(value: int, count: int = 5) -> bytes:
    _integer(value, 0, 0xffffffff if count == 5 else (1 << (count * 7)) - 1, "Wire integer")
    return bytes((value >> (index * 7)) & 127 for index in range(count))


def status_request() -> bytes:
    return PREFIX + bytes([13, 247])


def snapshot_request() -> bytes:
    """Freeze a complete audio-owner snapshot; no musical setting changes."""
    return PREFIX + bytes([14, 247])


def chunk_request(token: int, offset: int) -> bytes:
    _integer(token, 1, 0xffffffff, "Snapshot token")
    _integer(offset, 0, SIZE - 1, "Snapshot offset")
    return PREFIX + bytes([15]) + _u7(token) + _u7(offset, 2) + bytes([247])


def begin_request(transaction: int, expected_generation: int) -> bytes:
    _integer(transaction, 1, 0xffffffff, "Transaction ID")
    return PREFIX + bytes([16]) + _u7(transaction) + _u7(expected_generation) + bytes([247])


def write_chunk_request(transaction: int, offset: int, raw: bytes) -> bytes:
    _integer(transaction, 1, 0xffffffff, "Transaction ID")
    _integer(offset, 0, SIZE - 1, "Write offset")
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 64 or offset + len(raw) > SIZE:
        raise NativeStateError("Write chunk must contain 1..64 bytes within the exact record")
    nibbles = bytes(value for byte in raw for value in (byte >> 4, byte & 15))
    return PREFIX + bytes([17]) + _u7(transaction) + _u7(offset, 2) + bytes([len(raw)]) + nibbles + bytes([247])


def commit_request(transaction: int) -> bytes:
    _integer(transaction, 1, 0xffffffff, "Transaction ID")
    return PREFIX + bytes([18]) + _u7(transaction) + bytes([247])


def backup_ack_request(token: int, crc: int) -> bytes:
    _integer(token, 1, 0xffffffff, "SAVE token")
    return PREFIX + bytes([19]) + _u7(token) + _u7(crc) + bytes([247])


def abort_request(transaction: int = 0) -> bytes:
    """Discard incomplete staging only; zero addresses any abandoned staging."""
    _integer(transaction, 0, 0xffffffff, "Transaction ID")
    return PREFIX + bytes([20]) + _u7(transaction) + bytes([247])


def _decimal_fields(frame: bytes, opcode: int) -> list[int]:
    if not isinstance(frame, bytes) or not 9 <= len(frame) <= 1024 or frame[:7] != PREFIX + bytes([opcode]) or frame[-1] != 247:
        raise NativeStateError("Unexpected native reply framing/opcode")
    try:
        words = frame[7:-1].decode("ascii").split(" ")
    except UnicodeDecodeError as exc:
        raise NativeStateError("Native reply is not ASCII") from exc
    if any(re.fullmatch(r"(?:0|[1-9][0-9]{0,9})", word) is None for word in words):
        raise NativeStateError("Native reply requires canonical unsigned decimal fields")
    result = [int(word) for word in words]
    if any(value > 0xffffffff for value in result):
        raise NativeStateError("Native reply exceeds unsigned32")
    return result


def parse_status(frame: bytes) -> dict:
    fields = _decimal_fields(frame, 13)
    if len(fields) != len(STATUS_FIELDS):
        raise NativeStateError("Unexpected native status field count")
    result = dict(zip(STATUS_FIELDS, fields))
    if (result["schema"] != 1 or result["preset_id"] not in (*range(16), CUSTOM_PRESET) or
            result["sound_dirty"] > 1 or result["last_import_result"] >= len(RESULT_NAMES)):
        raise NativeStateError("Native status exceeds schema1 ranges")
    return result


def parse_chunk(frame: bytes, *, token: int, offset: int) -> bytes:
    chunk_request(token, offset)
    fields = _decimal_fields(frame, 15)
    count = min(64, SIZE - offset)
    if len(fields) != 3 + count or fields[:3] != [token, offset, count] or any(value > 255 for value in fields[3:]):
        raise NativeStateError("Native chunk token/offset/count/data mismatch")
    return bytes(fields[3:])


def parse_result(frame: bytes, *, opcode: int, transaction: int) -> dict:
    if opcode not in (16, 17, 18, 19, 20):
        raise NativeStateError("Unsupported native result opcode")
    _integer(transaction, 0 if opcode == 20 else 1, 0xffffffff, "Transaction/token")
    fields = _decimal_fields(frame, opcode)
    if len(fields) != 2 or fields[0] != transaction or fields[1] >= len(RESULT_NAMES):
        raise NativeStateError("Unexpected native transaction result")
    return dict(transaction=transaction, result=fields[1], result_name=RESULT_NAMES[fields[1]])


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise NativeStateError(f"{label} must be an integer {low}..{high}")


def _list(value, count, label):
    if not isinstance(value, list) or len(value) != count:
        raise NativeStateError(f"{label} must contain exactly {count} values")


def control_bounds(identifier: int) -> tuple[int, int]:
    _integer(identifier, 0, CONTROL_COUNT - 1, "Control ID")
    if identifier < 126:
        return 0, OP_MAX[identifier % 21]
    if identifier < 145:
        return 0, GLOBAL_MAX[identifier - 126]
    if identifier < 160:
        return 0, 0
    return NATIVE_RANGES[identifier - 160]


def validate_state(state: dict) -> None:
    """Validate every field, including duplicate representations, before use."""
    if not isinstance(state, dict) or set(state) != FIELDS:
        raise NativeStateError("Native state has missing or unknown fields")
    if state["schema"] != SCHEMA or type(state["version"]) is not int or state["version"] != VERSION:
        raise NativeStateError("Unsupported native schema/version")
    _integer(state["source_generation"], 0, 0xffffffff, "Source generation")
    _integer(state["preset_id"], 0, CUSTOM_PRESET, "Preset ID")
    if state["preset_id"] not in (*range(16), CUSTOM_PRESET):
        raise NativeStateError("Preset ID must be 0..15 or 65535 (custom)")
    controls, vced, steps = state["controls"], state["vced"], state["steps"]
    _list(controls, CONTROL_COUNT, "Controls")
    for identifier, value in enumerate(controls):
        _integer(value, *control_bounds(identifier), f"Control {identifier}")
    if controls[181] not in (1, 2, 4, 8, 16, 32):
        raise NativeStateError("Arp rate must be 1,2,4,8,16,32")
    _list(vced, 155, "VCED")
    for offset, value in enumerate(vced):
        _integer(value, 0, 127, f"VCED byte {offset}")
    if vced[:145] != controls[:145]:
        raise NativeStateError("VCED numeric fields disagree with canonical controls")
    _integer(state["length"], 1, 64, "Pattern length")
    if controls[186] != state["length"] or controls[187] >= state["length"]:
        raise NativeStateError("Pattern length/selection disagree with controls")
    _list(steps, 64, "Pattern steps")
    for index, step in enumerate(steps):
        _list(step, 3, f"Step {index}")
        _integer(step[0], 0, 128, f"Step {index} pitch")
        _integer(step[1], 1, 127, f"Step {index} velocity")
        _integer(step[2], 1, 100, f"Step {index} gate")
    if steps[controls[187]] != controls[188:191]:
        raise NativeStateError("Selected step fields disagree with canonical controls")


def record_crc(raw: bytes) -> int:
    if len(raw) != SIZE:
        raise NativeStateError(f"Native record must contain exactly {SIZE} bytes")
    return zlib.crc32(raw[:28] + bytes(4) + raw[32:]) & 0xffffffff


def encode(state: dict) -> bytes:
    validate_state(state)
    out = bytearray(SIZE)
    struct.pack_into("<8sHHHHIHHHBBI", out, 0, MAGIC, VERSION, CONTROLS_OFFSET, SIZE, 0,
                     state["source_generation"], state["preset_id"], CONTROL_COUNT, 155,
                     64, state["length"], 0)
    struct.pack_into("<195H", out, CONTROLS_OFFSET, *state["controls"])
    out[VCED_OFFSET:STEPS_OFFSET] = bytes(state["vced"])
    out[STEPS_OFFSET:PADDING_OFFSET] = bytes(value for step in state["steps"] for value in step)
    struct.pack_into("<I", out, 28, record_crc(out))
    return bytes(out)


def decode(raw: bytes) -> dict:
    if not isinstance(raw, (bytes, bytearray)):
        raise NativeStateError("Native record must be bytes")
    if len(raw) != SIZE:
        raise NativeStateError(f"Native record must contain exactly {SIZE} bytes")
    magic, version, header, size, flags, generation, preset, controls, vced, steps, length, crc = struct.unpack_from("<8sHHHHIHHHBBI", raw)
    if (magic, version, header, size, flags, controls, vced, steps) != (MAGIC, VERSION, 32, SIZE, 0, CONTROL_COUNT, 155, 64):
        raise NativeStateError("Unsupported native header/schema/counts/flags")
    if any(raw[PADDING_OFFSET:]):
        raise NativeStateError("Native reserved padding must be zero")
    if record_crc(raw) != crc:
        raise NativeStateError("Native CRC32 mismatch")
    result = dict(schema=SCHEMA, version=VERSION, source_generation=generation, preset_id=preset,
                  controls=list(struct.unpack_from("<195H", raw, CONTROLS_OFFSET)),
                  vced=list(raw[VCED_OFFSET:STEPS_OFFSET]), length=length,
                  steps=[list(raw[STEPS_OFFSET + index * 3:STEPS_OFFSET + index * 3 + 3]) for index in range(64)])
    validate_state(result)
    return result


def read_record(path: Path) -> bytes:
    with Path(path).open("rb") as handle:
        raw = handle.read(SIZE + 1)
    decode(raw)
    return raw


def _write_new(path: Path, content: bytes) -> None:
    """Flush a staged file, then link atomically without replacing any file.

    Windows and POSIX hard-link creation refuse an existing destination. The
    same-directory temporary name ensures the final name cannot expose partial
    content. Fsync establishes OS flush, not a power-loss claim for the disk.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with staged.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def write_record(path: Path, raw: bytes) -> dict:
    state = decode(raw)
    _write_new(Path(path), bytes(raw))
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                source_generation=state["source_generation"], preset_id=state["preset_id"], scope=SCOPE)


def save_backup(raw: bytes, directory: Path, *, device_identity: str, source: str = "explicit native record") -> dict:
    """Save a validated complete record and provenance sidecar, never overwrite.

    A sidecar failure does not undo or misreport a committed record. Returned
    warning identifies that failure so a recorder can log successful backup
    independently from optional metadata. Identity is reported by the caller;
    this function neither identifies a device nor establishes hardware success.
    """
    decode(raw)
    if not isinstance(device_identity, str) or not device_identity or len(device_identity) > 128:
        raise NativeStateError("Explicit device identity must be a nonempty string up to 128 characters")
    if not isinstance(source, str) or not source or len(source) > 1024:
        raise NativeStateError("Explicit backup source must be a nonempty string up to 1024 characters")
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(raw).hexdigest()
    name = now.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + digest[:12] + "-" + uuid.uuid4().hex[:8]
    result = write_record(Path(directory) / (name + ".fmer-native"), raw)
    result.update(schema="fmer-native-host-backup-v1", utc=now.isoformat(), device_identity=device_identity,
                  source=source, persistent_location="host filesystem", hardware_write=False)
    sidecar = Path(directory) / (name + ".json")
    try:
        _write_new(sidecar, (json.dumps(result, indent=2) + "\n").encode("utf-8"))
        result["metadata_path"] = str(sidecar)
    except OSError as exc:
        result["warning"] = "Record committed; metadata sidecar failed: " + str(exc)
    return result


def _json_record(path: Path) -> dict:
    with path.open("rb") as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise NativeStateError("Native JSON exceeds the 1 MiB input bound")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise NativeStateError("Duplicate native JSON key: " + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "decode", "encode", "backup"):
        sub = subs.add_parser(name)
        sub.add_argument("input", type=Path)
        if name in ("decode", "encode"):
            sub.add_argument("output", type=Path, help="New file; existing files are never overwritten")
        if name == "backup":
            sub.add_argument("--directory", type=Path, required=True)
            sub.add_argument("--device-identity", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "encode":
            report = write_record(args.output, encode(_json_record(args.input)))
        else:
            raw = read_record(args.input)
            if args.command == "decode":
                _write_new(args.output, (json.dumps(decode(raw), indent=2) + "\n").encode("utf-8"))
                report = dict(path=str(args.output), scope=SCOPE)
            elif args.command == "backup":
                report = save_backup(raw, args.directory, device_identity=args.device_identity, source=str(args.input))
            else:
                state = decode(raw)
                report = dict(valid=True, bytes=SIZE, sha256=hashlib.sha256(raw).hexdigest(),
                              source_generation=state["source_generation"], preset_id=state["preset_id"],
                              engine=state["controls"][160], pattern_length=state["length"],
                              patch_name_bytes=state["vced"][145:], scope=SCOPE)
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, TypeError, struct.error) as exc:
        print(json.dumps(dict(success=False, error=str(exc))), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
