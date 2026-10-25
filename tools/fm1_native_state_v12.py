"""Native12: six-voice budget, unchanged 4000-byte storage; strict legacy migration."""
from copy import deepcopy
import struct,zlib
import fm1_native_state_v11 as v11
from fm1_native_state_v11 import *
from fm1_native_state_v11 import _integer,_decimal_fields,_u7,_write_new,_json_record
MAGIC=b'FMERNATC'
SCHEMA='fmer-native-target-state-v12'
VERSION=12
SIZE=4000
FIELDS=v11.FIELDS
SCOPE=v11.SCOPE+'; native12 admits 1..6 single-instrument voices'

def _legacy(state):
    if not isinstance(state,dict) or set(state)!=FIELDS or state.get('schema')!=SCHEMA or state.get('version')!=VERSION:raise NativeStateError('Expected native12')
    result=deepcopy(state);c=result['controls']
    if not isinstance(c,list) or len(c)!=198:raise NativeStateError('198 controls required')
    _integer(c[191],1,6,'Voice budget');c[191]=min(c[191],4)
    result.update(schema=v11.SCHEMA,version=v11.VERSION);return result

def _current(value,budget):
    value.update(schema=SCHEMA,version=VERSION);value['controls'][191]=budget;return value

def validate_state(state):v11.validate_state(_legacy(state))

def runtime_state(state):
    value=v11.runtime_state(_legacy(state));c=state['controls']
    return _current(value,4 if c[153] else 1 if c[150] else c[191])

def encode(state):
    out=bytearray(v11.encode(_legacy(state)));out[:8]=MAGIC;struct.pack_into('<H',out,8,VERSION)
    struct.pack_into('<H',out,414,state['controls'][191]);struct.pack_into('<I',out,28,record_crc(out));return bytes(out)

def decode(raw):
    if len(raw)!=SIZE or raw[:8]!=MAGIC or struct.unpack_from('<H',raw,8)[0]!=VERSION:raise NativeStateError('Expected native12 record')
    if record_crc(raw)!=struct.unpack_from('<I',raw,28)[0]:raise NativeStateError('Native12 CRC mismatch')
    budget=struct.unpack_from('<H',raw,414)[0];_integer(budget,1,6,'Voice budget')
    previous=bytearray(raw);previous[:8]=v11.MAGIC;struct.pack_into('<H',previous,8,11);struct.pack_into('<H',previous,414,min(budget,4))
    struct.pack_into('<I',previous,28,record_crc(previous))
    result=_current(v11.decode(previous),budget);validate_state(result);return result

def decode_compatible(raw):
    if raw[:8]==MAGIC:return decode(raw)
    value=v11.decode_compatible(raw);return _current(value,value['controls'][191])

def initialize_tracks(state):
    v11.initialize_tracks(state);return state

def canonical_sound(state):
    value=v11.canonical_sound(_legacy(state));return _current(value,6)

def merge_sound(sound,project,*,slot=None):
    value=v11.merge_sound(_legacy(sound),_legacy(project),slot=slot)
    c=project['controls'];return _current(value,4 if c[153] else 1 if value['controls'][150] else c[191])

def chunk_request(token: int, offset: int) -> bytes:
    _integer(token, 1, 0xffffffff, "Snapshot token")
    _integer(offset, 0, SIZE - 1, "Snapshot offset")
    return PREFIX + bytes([15]) + _u7(token) + _u7(offset, 2) + bytes([247])


def write_chunk_request(transaction: int, offset: int, raw: bytes) -> bytes:
    _integer(transaction, 1, 0xffffffff, "Transaction ID")
    _integer(offset, 0, SIZE - 1, "Write offset")
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 64 or offset + len(raw) > SIZE:
        raise NativeStateError("Write chunk must contain 1..64 bytes within the exact 4000-byte record")
    nibbles = bytes(value for byte in raw for value in (byte >> 4, byte & 15))
    return PREFIX + bytes([17]) + _u7(transaction) + _u7(offset, 2) + bytes([len(raw)]) + nibbles + bytes([247])


def parse_chunk(frame: bytes, *, token: int, offset: int) -> bytes:
    chunk_request(token, offset)
    fields = _decimal_fields(frame, 15)
    count = min(64, SIZE - offset)
    if len(fields) != 3 + count or fields[:3] != [token, offset, count] or any(value > 255 for value in fields[3:]):
        raise NativeStateError("Native chunk token/offset/count/data mismatch")
    return bytes(fields[3:])


def record_crc(raw: bytes) -> int:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != SIZE:
        raise NativeStateError(f"Native12 record must contain exactly {SIZE} bytes")
    return zlib.crc32(raw[:28] + bytes(4) + raw[32:]) & 0xffffffff


import json
from fm1_native_state_v8 import _write_new, _json_record
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

def control_bounds(identifier):
    return (1,6) if identifier==191 else v11.control_bounds(identifier)

def legacy_wire(raw):
    state=decode_compatible(raw)
    return v11.encode(_legacy(state))
