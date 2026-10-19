"""FMERNATB/native11: native10 plus two modulation recipes; still4000 bytes."""
from copy import deepcopy
import struct,zlib
import fm1_native_state_v10 as v10
from fm1_native_state_v10 import *
from fm1_native_state_v10 import _integer,_decimal_fields,_u7,_write_new,_json_record
MAGIC=b'FMERNATB'
SCHEMA='fmer-native-target-state-v11'
VERSION=11
SIZE=4000
FIELDS=v10.FIELDS|{'modulation_profiles'}
SCOPE=v10.SCOPE+'; native11 adds chorus/phaser recipes0..3 without increasing storage'
OFFSET=3705

def _legacy(state):
    if not isinstance(state,dict) or set(state)!=FIELDS:raise NativeStateError('Native11 fields')
    result=dict(state)
    if result.pop('schema',None)!=SCHEMA or result.pop('version',None)!=VERSION:raise NativeStateError('Expected native11')
    profiles=result.pop('modulation_profiles',None)
    if not isinstance(profiles,list) or len(profiles)!=2:raise NativeStateError('Two modulation profiles required')
    for p in profiles:_integer(p,0,3,'Modulation recipe')
    result.update(schema=v10.SCHEMA,version=v10.VERSION);return result

def validate_state(state):v10.validate_state(_legacy(state))

def runtime_state(state):
    result=v10.runtime_state(_legacy(state));result.update(schema=SCHEMA,version=VERSION,modulation_profiles=list(state['modulation_profiles']));return result

def encode(state):
    out=bytearray(v10.encode(_legacy(state)))
    out[:8]=MAGIC;struct.pack_into('<H',out,8,VERSION)
    out[OFFSET:OFFSET+6]=b'MOD1'+bytes(state['modulation_profiles'])
    struct.pack_into('<I',out,28,record_crc(out));return bytes(out)

def decode(raw):
    if len(raw)!=SIZE or raw[:8]!=MAGIC or struct.unpack_from('<H',raw,8)[0]!=VERSION:raise NativeStateError('Expected native11 record')
    if record_crc(raw)!=struct.unpack_from('<I',raw,28)[0]:raise NativeStateError('Native11 CRC mismatch')
    if raw[OFFSET:OFFSET+4]!=b'MOD1':raise NativeStateError('Modulation metadata missing')
    profiles=list(raw[OFFSET+4:OFFSET+6])
    previous=bytearray(raw);previous[:8]=v10.MAGIC;struct.pack_into('<H',previous,8,10);previous[OFFSET:OFFSET+6]=bytes(6)
    struct.pack_into('<I',previous,28,v10.record_crc(previous))
    result=v10.decode(previous);result.update(schema=SCHEMA,version=VERSION,modulation_profiles=profiles);validate_state(result);return result

def decode_compatible(raw):
    if raw[:8]==MAGIC:return decode(raw)
    result=v10.decode_compatible(raw);result.update(schema=SCHEMA,version=VERSION,modulation_profiles=[0,0]);return result

def initialize_tracks(state):
    v10.initialize_tracks(state);state['modulation_profiles']=[0,0];return state

def canonical_sound(state):
    result=v10.canonical_sound(_legacy(state));result.update(schema=SCHEMA,version=VERSION,modulation_profiles=list(state['modulation_profiles']));return result

def merge_sound(sound,project,*,slot=None):
    result=v10.merge_sound(_legacy(sound),_legacy(project),slot=slot)
    result.update(schema=SCHEMA,version=VERSION,modulation_profiles=list(sound['modulation_profiles']))
    if not project['controls'][153]:result['controls'][150:153]=project['controls'][150:153]
    return result

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
        raise NativeStateError(f"Native11 record must contain exactly {SIZE} bytes")
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
