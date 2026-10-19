#!/usr/bin/env python3
"""Strict offline FMERNAT2 codec for 708; no MIDI/device I/O.

2176 bytes retain 198 controls, exact 155-byte VCED and eight complete 64-step
mono patterns. v1 migration is explicit and uses the unchanged strict707 codec.
This record is not DX7, FMERPST, firmware, calibration or a whole-device image.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys
import uuid
import zlib

import fm1_native_state as v1

MAGIC = b"FMERNAT2"
SCHEMA = "fmer-native-target-state-v2"
VERSION = 2
SIZE = 2176
CONTROL_COUNT = 198
CONTROLS_OFFSET = 32
VCED_OFFSET = 428
PATTERNS_OFFSET = 583
PATTERN_COUNT = 8
PATTERN_BYTES = 193
PADDING_OFFSET = 2127
CUSTOM_PRESET = 65535
PREFIX = v1.PREFIX
STATUS_FIELDS = v1.STATUS_FIELDS
RESULT_NAMES = v1.RESULT_NAMES
FIELDS = {"schema", "version", "source_generation", "preset_id", "controls", "vced", "patterns"}
PATTERN_FIELDS = {"length", "steps"}
SCOPE = ("708 editable FM/VA/effects/arp/MIDI state and eight complete mono patterns; "
         "includes all inactive steps and exact VCED name; excludes physical master, "
         "octave/page, held notes, pedal, running/recording position, effect tails, "
         "diagnostic counters and device calibration; this tool writes host files only")
NativeStateError = v1.NativeStateError
_integer, _list, _u7 = v1._integer, v1._list, v1._u7
_decimal_fields = v1._decimal_fields
_write_new, _json_record = v1._write_new, v1._json_record
status_request, snapshot_request = v1.status_request, v1.snapshot_request
begin_request, commit_request = v1.begin_request, v1.commit_request
backup_ack_request, abort_request = v1.backup_ack_request, v1.abort_request
parse_result = v1.parse_result


def chunk_request(token: int, offset: int) -> bytes:
    _integer(token, 1, 0xffffffff, "Snapshot token")
    _integer(offset, 0, SIZE - 1, "Snapshot offset")
    return PREFIX + bytes([15]) + _u7(token) + _u7(offset, 2) + bytes([247])


def write_chunk_request(transaction: int, offset: int, raw: bytes) -> bytes:
    _integer(transaction, 1, 0xffffffff, "Transaction ID")
    _integer(offset, 0, SIZE - 1, "Write offset")
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 64 or offset + len(raw) > SIZE:
        raise NativeStateError("Write chunk must contain 1..64 bytes within the exact 2176-byte record")
    nibbles = bytes(value for byte in raw for value in (byte >> 4, byte & 15))
    return PREFIX + bytes([17]) + _u7(transaction) + _u7(offset, 2) + bytes([len(raw)]) + nibbles + bytes([247])


def parse_status(frame: bytes) -> dict:
    fields = _decimal_fields(frame, 13)
    if len(fields) != len(STATUS_FIELDS):
        raise NativeStateError("Unexpected native status field count")
    result = dict(zip(STATUS_FIELDS, fields))
    if (result["schema"] != 2 or result["preset_id"] not in (*range(64), CUSTOM_PRESET) or
            result["sound_dirty"] > 1 or result["last_import_result"] >= len(RESULT_NAMES)):
        raise NativeStateError("Native status exceeds schema2 ranges")
    return result


def parse_chunk(frame: bytes, *, token: int, offset: int) -> bytes:
    chunk_request(token, offset)
    fields = _decimal_fields(frame, 15)
    count = min(64, SIZE - offset)
    if len(fields) != 3 + count or fields[:3] != [token, offset, count] or any(value > 255 for value in fields[3:]):
        raise NativeStateError("Native chunk token/offset/count/data mismatch")
    return bytes(fields[3:])


def control_bounds(identifier: int) -> tuple[int, int]:
    _integer(identifier, 0, CONTROL_COUNT - 1, "Control ID")
    if identifier == 180:
        return 0, 9
    if identifier < 195:
        return v1.control_bounds(identifier)
    return ((0, 7), (0, 1), (1, 255))[identifier - 195]


def validate_state(state: dict) -> None:
    if not isinstance(state, dict) or set(state) != FIELDS:
        raise NativeStateError("Native v2 state has missing or unknown fields")
    if state["schema"] != SCHEMA or type(state["version"]) is not int or state["version"] != VERSION:
        raise NativeStateError("Unsupported native schema/version")
    _integer(state["source_generation"], 0, 0xffffffff, "Source generation")
    _integer(state["preset_id"], 0, CUSTOM_PRESET, "Preset ID")
    if state["preset_id"] not in (*range(64), CUSTOM_PRESET):
        raise NativeStateError("Preset ID must be 0..63 or 65535 (custom)")
    controls, vced, patterns = state["controls"], state["vced"], state["patterns"]
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
    _list(patterns, PATTERN_COUNT, "Patterns")
    for bank, pattern in enumerate(patterns):
        if not isinstance(pattern, dict) or set(pattern) != PATTERN_FIELDS:
            raise NativeStateError(f"Pattern {bank} has missing or unknown fields")
        _integer(pattern["length"], 1, 64, f"Pattern {bank} length")
        _list(pattern["steps"], 64, f"Pattern {bank} steps")
        for index, step in enumerate(pattern["steps"]):
            _list(step, 3, f"Pattern {bank} step {index}")
            _integer(step[0], 0, 128, f"Pattern {bank} step {index} pitch")
            _integer(step[1], 1, 127, f"Pattern {bank} step {index} velocity")
            _integer(step[2], 1, 100, f"Pattern {bank} step {index} gate")
    selected = patterns[controls[195]]
    if controls[186] != selected["length"] or controls[187] >= selected["length"]:
        raise NativeStateError("Selected pattern length/step disagree with controls")
    if selected["steps"][controls[187]] != controls[188:191]:
        raise NativeStateError("Selected pattern step fields disagree with canonical controls")


def record_crc(raw: bytes) -> int:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != SIZE:
        raise NativeStateError(f"Native v2 record must contain exactly {SIZE} bytes")
    return zlib.crc32(raw[:28] + bytes(4) + raw[32:]) & 0xffffffff


def encode(state: dict) -> bytes:
    validate_state(state)
    out = bytearray(SIZE)
    struct.pack_into("<8sHHHHIHHHBBI", out, 0, MAGIC, VERSION, 32, SIZE, 0,
                     state["source_generation"], state["preset_id"], CONTROL_COUNT, 155,
                     PATTERN_COUNT, 64, 0)
    struct.pack_into("<198H", out, CONTROLS_OFFSET, *state["controls"])
    out[VCED_OFFSET:PATTERNS_OFFSET] = bytes(state["vced"])
    for bank, pattern in enumerate(state["patterns"]):
        start = PATTERNS_OFFSET + bank * PATTERN_BYTES
        out[start] = pattern["length"]
        out[start + 1:start + PATTERN_BYTES] = bytes(value for step in pattern["steps"] for value in step)
    struct.pack_into("<I", out, 28, record_crc(out))
    return bytes(out)


def decode(raw: bytes) -> dict:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != SIZE:
        raise NativeStateError(f"Native v2 record must contain exactly {SIZE} bytes")
    magic, version, header, size, flags, generation, preset, controls, vced, patterns, steps, crc = struct.unpack_from("<8sHHHHIHHHBBI", raw)
    if (magic, version, header, size, flags, controls, vced, patterns, steps) != (MAGIC, VERSION, 32, SIZE, 0, CONTROL_COUNT, 155, PATTERN_COUNT, 64):
        raise NativeStateError("Unsupported native v2 header/schema/counts/flags")
    if any(raw[PADDING_OFFSET:]):
        raise NativeStateError("Native v2 reserved padding must be zero")
    if record_crc(raw) != crc:
        raise NativeStateError("Native v2 CRC32 mismatch")
    banks = []
    for bank in range(PATTERN_COUNT):
        start = PATTERNS_OFFSET + bank * PATTERN_BYTES
        banks.append(dict(length=raw[start], steps=[list(raw[start + 1 + step * 3:start + 4 + step * 3]) for step in range(64)]))
    state = dict(schema=SCHEMA, version=VERSION, source_generation=generation, preset_id=preset,
                 controls=list(struct.unpack_from("<198H", raw, CONTROLS_OFFSET)),
                 vced=list(raw[VCED_OFFSET:PATTERNS_OFFSET]), patterns=banks)
    validate_state(state)
    return state


def upgrade_v1(raw: bytes) -> bytes:
    """Explicit lossless 707->708 migration, leaving input and its file intact.

    Existing 0..15 factory recipe IDs are retained by 708; no ID remapping occurs.
    Seven empty 16-step banks are added, including defined inactive step bytes.
    """
    old = v1.decode(raw)
    state = dict(schema=SCHEMA, version=VERSION, source_generation=old["source_generation"],
                 preset_id=old["preset_id"], controls=old["controls"] + [0, 0, 1], vced=old["vced"],
                 patterns=[dict(length=old["length"], steps=old["steps"])] +
                          [dict(length=16, steps=[[128, 100, 75] for _ in range(64)]) for _ in range(7)])
    return encode(state)


def read_record(path: Path) -> bytes:
    with Path(path).open("rb") as handle:
        raw = handle.read(SIZE + 1)
    decode(raw)
    return raw


def write_record(path: Path, raw: bytes) -> dict:
    state = decode(raw)
    _write_new(Path(path), bytes(raw))
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                source_generation=state["source_generation"], preset_id=state["preset_id"],
                native_schema=SCHEMA, scope=SCOPE)


def save_backup(raw: bytes, directory: Path, *, device_identity: str, source: str = "explicit native v2 record") -> dict:
    decode(raw)
    if not isinstance(device_identity, str) or not device_identity or len(device_identity) > 128:
        raise NativeStateError("Explicit device identity must be a nonempty string up to 128 characters")
    if not isinstance(source, str) or not source or len(source) > 1024:
        raise NativeStateError("Explicit backup source must be a nonempty string up to 1024 characters")
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(raw).hexdigest()
    name = now.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + digest[:12] + "-" + uuid.uuid4().hex[:8]
    result = write_record(Path(directory) / (name + ".fmer-native"), raw)
    result.update(schema="fmer-native-host-backup-v2", utc=now.isoformat(), device_identity=device_identity,
                  source=source, persistent_location="host filesystem", hardware_write=False)
    sidecar = Path(directory) / (name + ".json")
    try:
        _write_new(sidecar, (json.dumps(result, indent=2) + "\n").encode("utf-8"))
        result["metadata_path"] = str(sidecar)
    except OSError as exc:
        result["warning"] = "Record committed; metadata sidecar failed: " + str(exc)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "decode", "encode", "backup", "upgrade-v1"):
        sub = subs.add_parser(name)
        sub.add_argument("input", type=Path)
        if name in ("decode", "encode", "upgrade-v1"):
            sub.add_argument("output", type=Path, help="New file; existing files are never overwritten")
        if name == "backup":
            sub.add_argument("--directory", type=Path, required=True)
            sub.add_argument("--device-identity", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "encode":
            report = write_record(args.output, encode(_json_record(args.input)))
        elif args.command == "upgrade-v1":
            original = v1.read_record(args.input)
            report = write_record(args.output, upgrade_v1(original))
            report.update(migration="FMERNAT1 to FMERNAT2", original_path=str(args.input),
                          original_sha256=hashlib.sha256(original).hexdigest())
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
                              engine=state["controls"][160], pattern_lengths=[x["length"] for x in state["patterns"]],
                              selected_pattern=state["controls"][195], patch_name_bytes=state["vced"][145:], scope=SCOPE)
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, TypeError, struct.error) as exc:
        print(json.dumps(dict(success=False, error=str(exc))), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
