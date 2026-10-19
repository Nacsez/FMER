#!/usr/bin/env python3
"""Strict offline FMERNAT6 codec for721; no MIDI/device I/O.

3728 bytes retain 198 controls, exact155-byte VCED, sixteen64-step patterns and
four track references. Strict v1..v3 migration initializes disabled glide and
single-track mode while preserving the old sounds, effects and pattern data.
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

MAGIC = b"FMERNAT6"
SCHEMA = "fmer-native-target-state-v6"
VERSION = 6
SIZE = 3728
CONTROL_COUNT = 198
CONTROLS_OFFSET = 32
VCED_OFFSET = 428
PATTERNS_OFFSET = 583
PATTERN_COUNT = 16
PATTERN_BYTES = 193
PADDING_OFFSET = 3671
CUSTOM_PRESET = 65535
PREFIX = v1.PREFIX
STATUS_FIELDS = v1.STATUS_FIELDS
RESULT_NAMES = v1.RESULT_NAMES
FIELDS = {"schema", "version", "source_generation", "preset_id", "controls", "vced", "patterns", "tracks"}
PATTERN_FIELDS = {"length", "steps"}
TRACK_FIELDS = {"pattern", "chain_mask", "sound_ref", "level", "mute", "solo", "fx_bypass"}
TRACK_MAGIC = b"TRK3"
TRACKS_END = 3699
SCOPE = ("721 editable FM/VA/effects/arp/MIDI/glide state, sixteen complete patterns and four track references; "
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
        raise NativeStateError("Write chunk must contain 1..64 bytes within the exact 3728-byte record")
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
    if 145 <= identifier <= 149:
        return (0, (2,100,1,1,1)[identifier-145])
    if 150 <= identifier <= 159:
        return 0, (2,2000,2,1,3,127,100,1,2,0)[identifier-150]
    if identifier == 180:
        return 0, 9
    if identifier == 188:
        return 0, 129
    if identifier < 195:
        return v1.control_bounds(identifier)
    return ((0, 15), (0, 1), (1, 65535))[identifier - 195]


def validate_state(state: dict) -> None:
    if not isinstance(state, dict) or set(state) != FIELDS:
        raise NativeStateError("Native v6 state has missing or unknown fields")
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
            _integer(step[0], 0, 129, f"Pattern {bank} step {index} pitch")
            _integer(step[1], 1, 127, f"Pattern {bank} step {index} velocity")
            _integer(step[2], 1, 100, f"Pattern {bank} step {index} gate")
    selected = patterns[controls[195]]
    if controls[186] != selected["length"] or controls[187] >= selected["length"]:
        raise NativeStateError("Selected pattern length/step disagree with controls")
    if selected["steps"][controls[187]] != controls[188:191]:
        raise NativeStateError("Selected pattern step fields disagree with canonical controls")
    tracks=state['tracks']
    _list(tracks,4,'Tracks')
    for index,track in enumerate(tracks):
        if not isinstance(track,dict) or set(track)!=TRACK_FIELDS:
            raise NativeStateError(f'Track {index} has missing or unknown fields')
        for key,maximum in zip(('pattern','chain_mask','sound_ref','level','mute','solo','fx_bypass'),(15,65535,127,100,1,1,1)):
            _integer(track[key],0,maximum,f'Track {index} {key}')
    track=tracks[controls[154]]
    if controls[155:158]!=[track['sound_ref'],track['level'],track['mute']]:
        raise NativeStateError('Selected track sound/level/mute disagree with canonical controls')


def record_crc(raw: bytes) -> int:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != SIZE:
        raise NativeStateError(f"Native v6 record must contain exactly {SIZE} bytes")
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
    out[PADDING_OFFSET:PADDING_OFFSET+4]=TRACK_MAGIC
    for index,track in enumerate(state['tracks']):
        start=PADDING_OFFSET+4+index*6
        struct.pack_into("<BHBBB",out,start,track['pattern'],track['chain_mask'],track['sound_ref'],track['level'],track['mute'] | track['solo']<<1 | track['fx_bypass']<<2)
    struct.pack_into("<I", out, 28, record_crc(out))
    return bytes(out)


def decode(raw: bytes) -> dict:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != SIZE:
        raise NativeStateError(f"Native v6 record must contain exactly {SIZE} bytes")
    magic, version, header, size, flags, generation, preset, controls, vced, patterns, steps, crc = struct.unpack_from("<8sHHHHIHHHBBI", raw)
    if (magic, version, header, size, flags, controls, vced, patterns, steps) != (MAGIC, VERSION, 32, SIZE, 0, CONTROL_COUNT, 155, PATTERN_COUNT, 64):
        raise NativeStateError("Unsupported native v6 header/schema/counts/flags")
    if raw[PADDING_OFFSET:PADDING_OFFSET+4]!=TRACK_MAGIC:
        raise NativeStateError('Native v6 track extension magic mismatch')
    if any(raw[TRACKS_END:]):
        raise NativeStateError("Native v6 reserved padding must be zero")
    if record_crc(raw) != crc:
        raise NativeStateError("Native v6 CRC32 mismatch")
    banks = []
    for bank in range(PATTERN_COUNT):
        start = PATTERNS_OFFSET + bank * PATTERN_BYTES
        banks.append(dict(length=raw[start], steps=[list(raw[start + 1 + step * 3:start + 4 + step * 3]) for step in range(64)]))
    state = dict(schema=SCHEMA, version=VERSION, source_generation=generation, preset_id=preset,
                 controls=list(struct.unpack_from("<198H", raw, CONTROLS_OFFSET)),
                 vced=list(raw[VCED_OFFSET:PATTERNS_OFFSET]), patterns=banks,
                 tracks=[dict(zip(('pattern','chain_mask','sound_ref','level','mute'),
                                  struct.unpack_from("<BHBBB",raw,PADDING_OFFSET+4+i*6))) for i in range(4)])
    for track in state['tracks']:
        flags=track['mute']
        if flags>7:raise NativeStateError('Unknown track flags')
        track.update(mute=flags&1,solo=(flags>>1)&1,fx_bypass=(flags>>2)&1)
    validate_state(state)
    return state


def initialize_tracks(state: dict) -> dict:
    import fm1_native_state_v4 as v4
    v4.initialize_tracks(state)
    for track in state['tracks']:track.update(solo=0,fx_bypass=0)
    state["controls"][158]=1
    return state


def _upgrade_legacy(raw: bytes) -> bytes:
    """Strictly validate historical state; only append empty patterns9..16."""
    import fm1_native_state_v5 as v5
    state=v5.decode_compatible(raw)
    state.update(schema=SCHEMA,version=VERSION)
    for track in state['tracks']:track.update(solo=0,fx_bypass=0)
    return encode(state)


def _upgrade_version(raw: bytes, version: int) -> bytes:
    if not isinstance(raw,(bytes,bytearray)) or raw[:8]!=f'FMERNAT{version}'.encode('ascii'):
        raise NativeStateError(f'Expected a native v{version} source record')
    return _upgrade_legacy(raw)


def upgrade_v1(raw: bytes) -> bytes:return _upgrade_version(raw,1)
def upgrade_v2(raw: bytes) -> bytes:return _upgrade_version(raw,2)
def upgrade_v3(raw: bytes) -> bytes:return _upgrade_version(raw,3)
def upgrade_v4(raw: bytes) -> bytes:return _upgrade_version(raw,4)
def upgrade_v5(raw: bytes) -> bytes:return _upgrade_version(raw,5)


def decode_compatible(raw: bytes) -> dict:
    if raw[:8] in (b'FMERNAT1',b'FMERNAT2',b'FMERNAT3',b'FMERNAT4',b'FMERNAT5'):
        return decode(_upgrade_legacy(raw))
    return decode(raw)


def canonical_sound(state: dict) -> dict:
    """Instrument save projection; every musical sound/FX/arp value is retained.

    Projects own patterns, tracks and sequence editor state. The native envelope
    uses a specified empty project when exchanging a saved instrument alone.
    """
    from copy import deepcopy
    validate_state(state)
    result=deepcopy(state);c=result['controls']
    reference=64+(result['preset_id'] if result['preset_id']<64 else 0)
    c[153:160]=[0,0,reference,100,0,0,0]
    c[186:191]=[16,0,128,100,75];c[195:198]=[0,0,1]
    result['patterns']=[dict(length=16,steps=[[128,100,75] for _ in range(64)]) for _ in range(16)]
    result['tracks']=[dict(pattern=i,chain_mask=0,sound_ref=reference,level=100,mute=0,solo=0,fx_bypass=0) for i in range(4)]
    validate_state(result)
    return result


def merge_sound(sound: dict, project: dict, *, slot: int | None = None) -> dict:
    """Explicit sound recall retains the live arrangement and restores sound FX.

    This differs from immediate audition, whose established behavior retains FX.
    Supplying slot also assigns that instrument to the currently selected track.
    """
    from copy import deepcopy
    validate_state(sound);validate_state(project)
    result=deepcopy(sound)
    result['patterns']=deepcopy(project['patterns']);result['tracks']=deepcopy(project['tracks'])
    for i in (*range(153,160),*range(186,192),*range(195,198),178):
        result['controls'][i]=project['controls'][i]
    if slot is not None:
        _integer(slot,0,127,'Sound slot')
        result['controls'][155]=slot;result['tracks'][result['controls'][154]]['sound_ref']=slot
    validate_state(result)
    return result


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


def save_backup(raw: bytes, directory: Path, *, device_identity: str, source: str = "explicit native v6 record") -> dict:
    decode(raw)
    if not isinstance(device_identity, str) or not device_identity or len(device_identity) > 128:
        raise NativeStateError("Explicit device identity must be a nonempty string up to 128 characters")
    if not isinstance(source, str) or not source or len(source) > 1024:
        raise NativeStateError("Explicit backup source must be a nonempty string up to 1024 characters")
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(raw).hexdigest()
    name = now.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + digest[:12] + "-" + uuid.uuid4().hex[:8]
    result = write_record(Path(directory) / (name + ".fmer-native"), raw)
    result.update(schema="fmer-native-host-backup-v6", utc=now.isoformat(), device_identity=device_identity,
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
    for name in ("verify", "decode", "encode", "backup", "upgrade-v1", "upgrade-v2", "upgrade-v3", "upgrade-v4"):
        sub = subs.add_parser(name)
        sub.add_argument("input", type=Path)
        if name in ("decode", "encode", "upgrade-v1", "upgrade-v2", "upgrade-v3", "upgrade-v4"):
            sub.add_argument("output", type=Path, help="New file; existing files are never overwritten")
        if name == "backup":
            sub.add_argument("--directory", type=Path, required=True)
            sub.add_argument("--device-identity", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "encode":
            report = write_record(args.output, encode(_json_record(args.input)))
        elif args.command.startswith('upgrade-'):
            with args.input.open('rb') as handle:original=handle.read(SIZE+1)
            upgrader={'upgrade-v1':upgrade_v1,'upgrade-v2':upgrade_v2,'upgrade-v3':upgrade_v3,'upgrade-v4':upgrade_v4}[args.command]
            report = write_record(args.output, upgrader(original))
            report.update(migration=args.command+' to FMERNAT6', original_path=str(args.input),
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
