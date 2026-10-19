"""FMERNAT9: native8 plus a six-stage FX permutation; record stays3728B."""
from copy import deepcopy
import struct
import fm1_native_state_v8 as v8
from fm1_native_state_v8 import *
from fm1_native_state_v8 import _integer, _decimal_fields, _u7

MAGIC=b'FMERNAT9'
SCHEMA='fmer-native-target-state-v9'
VERSION=9
FIELDS=v8.FIELDS|{'fx_order'}
FX_OFFSET=v8.TRACKS_END
SCOPE=v8.SCOPE+'; v9 also retains the shared FX order'

def effect_order(rank):
    v1._integer(rank,0,719,'FX order permutation')
    available=list(range(6));result=[]
    for factor in (120,24,6,2,1,1):
        index,rank=divmod(rank,factor);result.append(available.pop(index))
    return result

def effect_rank(order):
    if not isinstance(order,list) or len(order)!=6 or any(type(x)is not int for x in order) or sorted(order)!=list(range(6)):
        raise NativeStateError('FX order must contain each stage exactly once')
    available=list(range(6));rank=0
    for item,factor in zip(order,(120,24,6,2,1,1)):
        rank+=available.index(item)*factor;available.remove(item)
    return rank

def _legacy(state):
    result=deepcopy(state)
    if result.pop('schema',None)!=SCHEMA or result.pop('version',None)!=VERSION:
        raise NativeStateError('Expected native9 state')
    v1._integer(result.pop('fx_order',None),0,719,'FX order permutation')
    result.update(schema=v8.SCHEMA,version=v8.VERSION)
    return result

def validate_state(state):v8.validate_state(_legacy(state))

def runtime_state(state):
    """Copy for adoption by728; archival decode/encode remain lossless.

    Four tracks reserve four voices. Single-instrument glide reserves one.
    This is an explicit allocation conversion, not a relaxed readback check.
    """
    validate_state(state)
    result=deepcopy(state);c=result['controls']
    if c[153]:c[191]=4
    elif c[150]:c[191]=1
    return result

def encode(state):
    out=bytearray(v8.encode(_legacy(state)))
    out[:8]=MAGIC;struct.pack_into('<H',out,8,VERSION)
    out[FX_OFFSET:FX_OFFSET+4]=b'FX09'
    struct.pack_into('<H',out,FX_OFFSET+4,state['fx_order'])
    struct.pack_into('<I',out,28,record_crc(out))
    return bytes(out)

def decode(raw):
    if len(raw)!=SIZE or raw[:8]!=MAGIC or struct.unpack_from('<H',raw,8)[0]!=VERSION:
        raise NativeStateError('Expected native9 record')
    if raw[FX_OFFSET:FX_OFFSET+4]!=b'FX09' or any(raw[FX_OFFSET+6:]):
        raise NativeStateError('Invalid native9 FX extension')
    if record_crc(raw)!=struct.unpack_from('<I',raw,28)[0]:raise NativeStateError('Native9 CRC mismatch')
    rank=struct.unpack_from('<H',raw,FX_OFFSET+4)[0];v1._integer(rank,0,719,'FX order permutation')
    old=bytearray(raw);old[:8]=v8.MAGIC;struct.pack_into('<H',old,8,8);old[FX_OFFSET:]=bytes(SIZE-FX_OFFSET)
    struct.pack_into('<I',old,28,record_crc(old))
    state=v8.decode(old);state.update(schema=SCHEMA,version=VERSION,fx_order=rank)
    return state

def decode_compatible(raw):
    if raw[:8]==MAGIC:return decode(raw)
    state=v8.decode_compatible(raw);state.update(schema=SCHEMA,version=VERSION,fx_order=0)
    return state

def initialize_tracks(state):
    v8.initialize_tracks(state);state['fx_order']=0
    return state

def canonical_sound(state):
    result=v8.canonical_sound(_legacy(state));result.update(schema=SCHEMA,version=VERSION,fx_order=state['fx_order'])
    return result

def merge_sound(sound,project,*,slot=None):
    result=v8.merge_sound(_legacy(sound),_legacy(project),slot=slot)
    result.update(schema=SCHEMA,version=VERSION,fx_order=sound['fx_order'])
    return result


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


