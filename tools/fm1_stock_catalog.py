#!/usr/bin/env python3
"""Offline extraction of the two stock V15 VMEM regions from a verified dump.

Original voice bytes always remain separate from normalized FMER imports.
No device access, bank writes, or public redistribution is performed here.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

import companion_bank as bank
import companion_shelf as shelf
import fm1_flash_compare as flash
import fm1_native_state as v1
import library

ROOT = Path(__file__).resolve().parents[1]
BANK_OFFSETS = (0xEA000, 0xEE000)


def unpack_voice(raw):
    """Preserve stock's out-of-DX7-range values in the returned original VCED."""
    if len(raw) != 128 or any(x > 127 for x in raw):
        raise ValueError('Expected 128 seven-bit stock voice bytes')
    voice = []
    for op in range(6):
        p = raw[op*17:op*17+17]
        if p[11] & 0x70 or p[13] & 0x60 or p[15] & 0x40:
            raise ValueError('Reserved operator bits are set')
        voice += list(p[:11]) + [p[11]&3, (p[11]>>2)&3, p[12]&7,
            p[13]&3, (p[13]>>2)&7, p[14], p[15]&1, (p[15]>>1)&31,
            p[16], (p[12]>>3)&15]
    if raw[110] > 31 or raw[111] & 0x70:
        raise ValueError('Reserved global bits are set')
    voice += list(raw[102:110])+[raw[110], raw[111]&7, (raw[111]>>3)&1]
    voice += list(raw[112:116])+[raw[116]&1, (raw[116]>>1)&7, raw[116]>>4, raw[117]]
    voice += list(raw[118:128])
    if any(not 32 <= x <= 126 for x in voice[145:]) or not bytes(voice[145:]).strip():
        raise ValueError('Stock voice name is not printable and nonempty')
    return voice


def normalize(voice):
    if len(voice) != 155:
        raise ValueError('Expected 155 VCED bytes')
    maximum = list(v1.OP_MAX)*6 + list(v1.GLOBAL_MAX) + [126]*10
    changes = [dict(parameter=i, original=x, imported=maximum[i])
               for i,x in enumerate(voice) if x > maximum[i]]
    return [min(x, maximum[i]) for i,x in enumerate(voice)], changes


def verified_dump(directory):
    report_bytes = (directory/'report.json').read_bytes()
    expected = (directory/'report.sha256').read_text().split()
    if expected != [hashlib.sha256(report_bytes).hexdigest(), 'report.json']:
        raise ValueError('Acquisition report hash differs from sidecar')
    report = json.loads(report_bytes)
    if report.get('status') != 'verified_double_dump':
        raise ValueError('Require successful double-read acquisition report')
    data = []
    for row in report['dumps']:
        if row['file'] not in ('flash-pass-1.bin','flash-pass-2.bin'):
            raise ValueError('Unexpected dump filename')
        raw = (directory/row['file']).read_bytes()
        if len(raw) != 0x100000 or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('Dump hash/size differs from acquisition')
        data.append(raw)
    if len(data) != 2 or data[0] != data[1]:
        raise ValueError('Two identical complete flash reads are required')
    return data[0]


def extract(directory, output, executable, label):
    output = output.resolve()
    if not output.is_relative_to(ROOT/'private'):
        raise ValueError('Stock payload output must stay under ignored private/')
    raw = verified_dump(directory)
    decoded, layout = flash.decode_app(raw[0x4000:0x93000], flash.decode_key(raw))
    voices = [[unpack_voice(raw[base+i*128:base+(i+1)*128]) for i in range(128)]
              for base in BANK_OFFSETS]
    # Validate all data before creating an export directory.
    output.mkdir(parents=True, exist_ok=False)
    codec_log = []
    codec = library.PatchCodec(executable, lambda event, **kw: codec_log.append(dict(event=event, **kw)))
    baseline = bank.decode_record(bank.profile(executable)[0]['native'])
    now = datetime.now(timezone.utc).isoformat()
    items, rows = [], []
    matching = voices[0] == voices[1]
    for b, voice_bank in enumerate(voices):
        base = BANK_OFFSETS[b]
        (output/f'region-{base:05x}.vmem').write_bytes(raw[base:base+16384])
        normalized = []
        for slot, original in enumerate(voice_bank):
            voice, changes = normalize(original)
            normalized.append(voice)
            name = bytes(voice[145:]).decode('ascii').rstrip()
            rows.append(dict(region=f'0x{base:05X}',slot=slot,display_slot=slot+1,name=name,
                flash_offset=base+slot*128,vmem_sha256=hashlib.sha256(raw[base+slot*128:base+(slot+1)*128]).hexdigest(),
                original_vced=original,normalization=changes))
            if b == 1 and matching:
                continue
            state = deepcopy(baseline)
            state.update(preset_id=65535, source_generation=0, vced=voice)
            state['controls'][:145] = voice[:145]
            # Imported voice alone: no inherited FMER-default effects, arp or glide.
            for control in (145,146,148,149,150,153,168,169,170,173,174,179):
                state['controls'][control] = 0
            state['controls'][147] = 1
            state['controls'][160] = 0
            state['controls'][162] = 20000
            state['controls'][163] = 0
            state['controls'][191] = 4
            state['controls'][197] = 1
            entry = dict(name=name,category='Custom',favorite=False,audition_note=60,native=bank.pack(state))
            bank.BankLibrary.validate_entry(entry)
            notes = (f'Private stock {label} V15 capture. Slot {slot+1:03d}; flash 0x{base+slot*128:05X}. '
                     'DX7 voice only; stock FX, routing, arp and sequence settings are not translated. '
                     f'{len(changes)} out-of-range fields normalized to FMER limits; original bytes retained in private extraction. '
                     'Playback equivalence to stock is not guaranteed. Redistribution rights unverified.')
            items.append(dict(id=str(uuid.uuid4()),kind='instrument',title=f'{slot+1:03d} {name}',
                collection=f'{label} stock V15'+('' if matching else f' {base:05X}'),tags=['Stock','FM','Private'],
                notes=notes,favorite=False,entry=entry,dependencies={},created=now,updated=now,trashed=False))
        for part in range(4):
            subset=normalized[part*32:(part+1)*32]
            sysex=codec.encode(subset)
            decoded_voices=codec.decode(sysex)
            if [p['vced'] for p in decoded_voices] != subset:
                raise ValueError('Compiled DX7 codec round trip differs')
            for local in range(32):
                slot=part*32+local
                if not normalize(voice_bank[slot])[1]:
                    if sysex[6+local*128:6+(local+1)*128] != raw[base+slot*128:base+(slot+1)*128]:
                        raise ValueError('Unmodified voice does not reproduce exact original VMEM')
            (output/f'region-{base:05x}-bank-{part+1}-normalized.syx').write_bytes(sysex)
    catalog=dict(format=shelf.FORMAT,version=1,capacity=shelf.CAPACITY,revision=0,slots=items,undo_slots=None)
    for item in items:shelf.Catalog.validate_item(item)
    (output/'companion-catalog.json').write_bytes(library.canonical(shelf.envelope(catalog)))
    (output/'voice-records.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8')
    (output/'codec-log.json').write_text(json.dumps(codec_log,indent=2)+'\n',encoding='utf8')
    (output/'application-decoded.bin').write_bytes(decoded)
    report=dict(unit=label,source=str(directory),source_sha256=hashlib.sha256(raw).hexdigest(),
        layout=layout,regions=[hex(x) for x in BANK_OFFSETS],voice_records=256,banks_byte_equivalent=matching,
        catalog_items=len(items),normalized_slots=[dict(region=r['region'],slot=r['slot'],changes=r['normalization']) for r in rows if r['normalization']],
        scope='Private voice extraction; exact raw regions retained. Bank roles are not inferred solely from offsets. Stock FX/global/pattern bytes retained only in full flash.',
        files=[dict(name=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(output.iterdir())])
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backup',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--executable',type=Path,required=True);p.add_argument('--unit-label',required=True)
    a=p.parse_args();r=extract(a.backup,a.output,a.executable.resolve(),a.unit_label)
    print(json.dumps({k:r[k] for k in ('unit','voice_records','banks_byte_equivalent','catalog_items')}))


if __name__=='__main__':main()
