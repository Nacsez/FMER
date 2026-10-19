# SPDX-License-Identifier: GPL-3.0-only
"""File-only DX7 interchange for the production companion.

The existing compiled PatchCodec owns Yamaha framing, checksum, packing and
parameter validation. This adapter creates complete, dry FMER instruments; it
does not open MIDI or save a library. The caller reviews the result before one
normal catalog transaction or explicit device transfer.
"""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import uuid

import companion_bank as bank
import companion_shelf as shelf
import library

LOSSES = [
    'DX7 interchange contains only the six-operator FM voice and its ten-character name.',
    'VA, effects, patterns, songs, mixer assignments and native performance settings are not exchanged.',
    'Felucca FM6 and other DX7 tools can exchange this format; native multi-engine projects are different formats.',
    'Matching parameter data does not guarantee identical sound across different synthesis engines.',
]


def decode(raw, template_state, codec):
    """Return one or 32 new instrument entries; never mutate template_state."""
    if not isinstance(raw, bytes) or len(raw) not in (163, 4104):
        raise ValueError('Choose one DX7 voice (163 bytes) or one 32-voice DX7 bank (4104 bytes). Export FM6 as .syx from Felucca; native project JSON is not supported.')
    bank.native.validate_state(template_state)
    voices = codec.decode(raw)
    expected = 1 if len(raw) == 163 else 32
    if len(voices) != expected:
        raise ValueError('Shared DX7 decoder returned an unexpected voice count')
    entries, renamed = [], []
    for index, voice in enumerate(voices):
        state = deepcopy(template_state)
        state['preset_id'] = bank.native.CUSTOM_PRESET
        state['source_generation'] = 0
        state = bank.native.canonical_sound(state)
        vced = list(voice['vced'])
        if len(vced) != 155:
            raise ValueError('Shared DX7 decoder returned an invalid voice')
        name = ''.join(chr(v) if 32 <= v <= 126 else ' ' for v in vced[145:]).rstrip()
        if not name.strip():
            name = f'IMPORTED{index + 1:02d}'
        if list(name.ljust(10).encode('ascii')) != vced[145:]:
            renamed.append(index + 1)
        vced[145:] = list(name.ljust(10).encode('ascii'))
        state['vced'] = vced
        c = state['controls']
        c[:145] = vced[:145]
        # Neutral extras preserve the imported operators/envelopes/LFO itself.
        c[145:154] = [0, 0, 1, 0, 0, 0, 150, 0, 0]
        c[159] = 0
        c[160] = 0
        c[162] = 20000
        c[168:175] = [0, 0, 0, 250, 35, 0, 0]
        c[178:186] = [120, 0, 0, 16, 1, 75, 0, 50]
        c[191:195] = [4, 0, 0, 50]
        state['fx_order'] = 0
        state['modulation_profiles'] = [0, 0]
        entry = dict(name=name, category='Custom', favorite=False,
                     audition_note=60, native=bank.pack(state))
        bank.BankLibrary.validate_entry(entry)
        entries.append(entry)
    notices = list(LOSSES)
    if renamed:
        notices.append('Nonprinting or empty names were normalized for the instrument display in voice(s): ' + ', '.join(map(str, renamed)))
    return dict(entries=entries, count=len(entries), losses=notices,
                source_sha256=hashlib.sha256(raw).hexdigest(), hardware_access=False)


def export(states, codec):
    """Export a single FM instrument or exactly 32 FM instruments."""
    if not isinstance(states, list) or len(states) not in (1, 32):
        raise ValueError('Select one FM sound or exactly 32 FM sounds for DX7 export')
    for state in states:
        bank.native.validate_state(state)
        if state['controls'][160] != 0:
            raise ValueError('DX7 export supports FM instruments only; use native export for VA')
    raw = codec.encode([state['vced'] for state in states])
    expected = 163 if len(states) == 1 else 4104
    if not isinstance(raw, bytes) or len(raw) != expected:
        raise ValueError('Shared DX7 encoder returned an invalid file')
    return dict(raw=base64.b64encode(raw).decode('ascii'),
                filename='fmer-voice.syx' if len(states) == 1 else 'fmer-bank.syx',
                losses=list(LOSSES), hardware_access=False)


def make_catalog(decoded, collection='DX7 imports'):
    """Build a validated import envelope for one atomic shelf transaction."""
    shelf.text(collection, 80, 'Collection', True)
    entries = decoded.get('entries')
    if not isinstance(entries, list) or len(entries) not in (1, 32):
        raise ValueError('Expected a decoded DX7 voice or bank')
    now = datetime.now(timezone.utc).isoformat()
    items = []
    for entry in entries:
        item = dict(id=str(uuid.uuid4()), kind='instrument', title=entry['name'],
                    collection=collection, tags=['DX7'], notes='Imported DX7 FM voice; no source effects or project. Source SHA-256: ' + decoded['source_sha256'],
                    favorite=False, entry=deepcopy(entry), dependencies={},
                    created=now, updated=now, trashed=False)
        shelf.Catalog.validate_item(item)
        items.append(item)
    return shelf.envelope(dict(format=shelf.FORMAT, version=1, capacity=shelf.CAPACITY,
                               revision=0, slots=items, undo_slots=None))


def merge_sound(entry, project):
    """Adopt an imported sound while retaining the editor's musical project."""
    bank.BankLibrary.validate_entry(entry)
    result = bank.native.merge_sound(bank.decode_record(entry['native']), project)
    bank.native.validate_state(result)
    return result
