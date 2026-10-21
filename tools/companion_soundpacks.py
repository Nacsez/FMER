# SPDX-License-Identifier: GPL-3.0-only
"""Included sound packs: reviewable, additive catalog imports; no device access."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid

import companion_bank as bank
import companion_dx7 as dx7
import companion_shelf as shelf
import fm1_stock_catalog as stock

ROOT=Path(__file__).resolve().parents[1]
PACKS=[dict(id='fmer-defaults',title='FMER Defaults',count=64,license='GPL-3.0-only'),
       dict(id='oem-v15',title='OEM Patches — V15',count=128,license='Apache-2.0')]


def catalog(entries, title, source, tags, details=None):
    items=[]
    for index,entry in enumerate(entries):
        item=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,source+':'+str(index))),
                  kind='instrument',title=f'{index+1:03d} {entry["name"]}',
                  collection=title,tags=tags,notes=(details[index] if details else source),
                  favorite=False,entry=deepcopy(entry),dependencies={},
                  created='2026-10-20T00:00:00+00:00',updated='2026-10-20T00:00:00+00:00',trashed=False)
        shelf.Catalog.validate_item(item);items.append(item)
    return shelf.envelope(dict(format=shelf.FORMAT,version=1,capacity=shelf.CAPACITY,
                               revision=0,slots=items,undo_slots=None))


def prepare(identifier, defaults, codec):
    if identifier=='fmer-defaults':
        return dict(catalog=catalog(defaults,'FMER Defaults','FMER Default 726.1',['FMER']),
                    count=64,losses=['Original FMER instruments; importing creates editable local copies.'])
    if identifier!='oem-v15':raise ValueError('Unknown included sound pack')
    data=json.loads((ROOT/'third_party/oem_v15/voices.json').read_text(encoding='utf8'))
    if data.get('format')!='FMER-OEM-V15-VOICES' or len(data.get('voices',[]))!=128:
        raise ValueError('Invalid OEM sound pack')
    raw=b''.join(bytes(v) for v in data['voices'])
    if len(raw)!=16384 or hashlib.sha256(raw).hexdigest()!=data['bank_sha256'] or data['bank_sha256']!='ecad0b8620f9d784d46c8da1e3c5de02c40214649ed8dec218026431046aad25':
        raise ValueError('OEM sound pack checksum mismatch')
    normalized=[stock.normalize(stock.unpack_voice(bytes(v))) for v in data['voices']]
    entries=[];template=bank.decode_record(defaults[0]['native'])
    for first in range(0,128,32):
        entries.extend(dx7.decode(codec.encode([v for v,c in normalized[first:first+32]]),template,codec)['entries'])
    details=[]
    for index,(_,changes) in enumerate(normalized):
        details.append(f'OEM Patches / Original V15 / slot {index+1:03d}. Apache-2.0; M-VAVE public recovery resource. '
                       f'Source SHA-256: {data["source_sha256"]}. FM voice only; no stock effects or project. '
                       + ('Range normalization: '+', '.join(f'{c["parameter"]}: {c["original"]} → {c["imported"]}' for c in changes) if changes else 'No range normalization.'))
    changed=[i+1 for i,(_,c) in enumerate(normalized) if c]
    return dict(catalog=catalog(entries,PACKS[1]['title'],data['source_sha256'],['OEM','V15','FM'],details),count=128,
                normalized_slots=changed,losses=[*dx7.LOSSES,
                    'OEM slot numbers are 1–128. Eleven voices contain values outside standard DX7 ranges; their imported values and original values are recorded in Notes. Original packed data remains included.'])
