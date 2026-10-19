"""FMERNATA/native10: legacy sound/patterns plus four 32-entry song lanes (4000B)."""
from copy import deepcopy
import struct,zlib
import fm1_native_state_v9 as v9
from fm1_native_state_v9 import *
from fm1_native_state_v9 import _integer,_decimal_fields,_u7,_write_new,_json_record
MAGIC=b'FMERNATA'
SCHEMA='fmer-native-target-state-v10'
VERSION=10
SIZE=4000
FIELDS=v9.FIELDS|{'song'}
SCOPE=v9.SCOPE+'; native10 adds four32-entry arrangement lanes, transpose and repeats'

def empty_song():
    return [dict(enabled=False,loop=False,length=0,entries=[dict(pattern=0,transpose=0,repeats=1) for _ in range(32)]) for _ in range(4)]

def validate_song(song):
    if not isinstance(song,list) or len(song)!=4:raise NativeStateError('Song requires four lanes')
    for lane in song:
        if not isinstance(lane,dict) or set(lane)!={'enabled','loop','length','entries'}:raise NativeStateError('Song lane fields')
        for key in ('enabled','loop'):
            if type(lane[key]) is not bool:raise NativeStateError('Song flags must be boolean')
        _integer(lane['length'],0,32,'Song length')
        if lane['enabled'] and not lane['length']:raise NativeStateError('Enabled song lane is empty')
        if not isinstance(lane['entries'],list) or len(lane['entries'])!=32:raise NativeStateError('Song requires32 retained entries')
        for row in lane['entries']:
            if not isinstance(row,dict) or set(row)!={'pattern','transpose','repeats'}:raise NativeStateError('Song entry fields')
            _integer(row['pattern'],0,16,'Song pattern (16=rest)');_integer(row['transpose'],-24,24,'Song transpose');_integer(row['repeats'],1,32,'Song repeats')

def _legacy(state):
    if not isinstance(state,dict) or set(state)!=FIELDS:raise NativeStateError('Native10 fields')
    # Only top-level format tags change here. Legacy codecs own their copies;
    # avoid cloning four song lanes just to discard them on every validation.
    result=dict(state)
    if result.pop('schema',None)!=SCHEMA or result.pop('version',None)!=VERSION:raise NativeStateError('Expected native10')
    validate_song(result.pop('song',None));result.update(schema=v9.SCHEMA,version=v9.VERSION);return result

def validate_state(state):v9.validate_state(_legacy(state))

def runtime_state(state):
    result=v9.runtime_state(_legacy(state));result.update(schema=SCHEMA,version=VERSION,song=deepcopy(state['song']));return result

def encode(state):
    out=bytearray(v9.encode(_legacy(state)))+bytearray(272)
    out[:8]=MAGIC;struct.pack_into('<H',out,8,VERSION);struct.pack_into('<H',out,12,SIZE)
    for t,lane in enumerate(state['song']):
        out[3728+t]=lane['length'];out[3732+t]=lane['enabled'];out[3736+t]=lane['loop']
        for r,row in enumerate(lane['entries']):
            n=row['pattern']|((row['transpose']&63)<<5)|((row['repeats']-1)<<11)
            struct.pack_into('<H',out,3744+2*(t*32+r),n)
    struct.pack_into('<I',out,28,record_crc(out));return bytes(out)

def decode(raw):
    if len(raw)!=SIZE or raw[:8]!=MAGIC or struct.unpack_from('<H',raw,8)[0]!=VERSION or struct.unpack_from('<H',raw,12)[0]!=SIZE:raise NativeStateError('Expected native10 record')
    if record_crc(raw)!=struct.unpack_from('<I',raw,28)[0]:raise NativeStateError('Native10 CRC mismatch')
    if any(raw[3740:3744]):raise NativeStateError('Song reserved bytes')
    old=bytearray(raw[:3728]);old[:8]=v9.MAGIC;struct.pack_into('<H',old,8,9);struct.pack_into('<H',old,12,3728);struct.pack_into('<I',old,28,v9.record_crc(old))
    result=v9.decode(old);song=empty_song()
    for t,lane in enumerate(song):
        if raw[3732+t]>1 or raw[3736+t]>1:raise NativeStateError('Song flags')
        lane.update(length=raw[3728+t],enabled=bool(raw[3732+t]),loop=bool(raw[3736+t]))
        for r,row in enumerate(lane['entries']):
            n=struct.unpack_from('<H',raw,3744+2*(t*32+r))[0];tr=(n>>5)&63
            row.update(pattern=n&31,transpose=tr-64 if tr>=32 else tr,repeats=(n>>11)+1)
    result.update(schema=SCHEMA,version=VERSION,song=song);validate_state(result);return result

def decode_compatible(raw):
    if raw[:8]==MAGIC:return decode(raw)
    state=v9.decode_compatible(raw);state.update(schema=SCHEMA,version=VERSION,song=empty_song());return state

def initialize_tracks(state):
    v9.initialize_tracks(state);state['song']=empty_song();return state

def canonical_sound(state):
    result=v9.canonical_sound(_legacy(state));result.update(schema=SCHEMA,version=VERSION,song=empty_song());return result

def merge_sound(sound,project,*,slot=None):
    result=v9.merge_sound(_legacy(sound),_legacy(project),slot=slot)
    result.update(schema=SCHEMA,version=VERSION,song=deepcopy(project['song']));return result

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
        raise NativeStateError(f"Native10 record must contain exactly {SIZE} bytes")
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
