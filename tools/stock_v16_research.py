# SPDX-License-Identifier: GPL-3.0-only
"""Pinned, offline V16 inspection and private factory-voice extraction.

No MIDI, flashing, downloaded code execution or redistribution grant. Preserve
the publisher package and unmodified packed voices; report import normalization.
"""
import argparse
import hashlib
import json
from pathlib import Path

import fm1_package as package
import fm1_stock_catalog as stock
import inspect_firmware_candidate as candidate

SHA256 = 'd017fb65e70aca97ee29d944470c3515a74581df5c0576bf70de917c7b2b61d5'
SIZE = 718196
URL = 'https://yms-file-store.oss-cn-hongkong.aliyuncs.com/software/firmware/FM-1.fwsc'
ROOT = Path(__file__).resolve().parents[1]


def normalize_voice(raw):
    """V16 slot101 ends in NUL; make only trailing NUL name padding printable."""
    if len(raw) != 128:
        raise ValueError('Expected one packed 128-byte voice')
    cooked = bytearray(raw)
    name = bytes(cooked[118:])
    padded = name.rstrip(b'\0').ljust(10, b' ')
    changes = [dict(packed_offset=118+i, original=a, imported=b)
               for i, (a, b) in enumerate(zip(name, padded)) if a != b]
    cooked[118:] = padded
    voice, ranges = stock.normalize(stock.unpack_voice(bytes(cooked)))
    return voice, dict(name_padding=changes, ranges=ranges)


def inspect(raw):
    if len(raw) != SIZE:
        raise ValueError('Unexpected V16 package size')
    result = candidate.inspect(raw, SHA256)
    if result['product'] != 'FM-1_016' or result['flash_extent'] != 0xa9000:
        raise ValueError('Unexpected V16 identity/layout')
    logical = b''.join(raw[i*48:i*48+47] for i in range(20)) + raw[960:]
    entry = next(e for e in result['entries'] if e['name'] == 'flash.bin')
    flash = logical[entry['offset']:entry['offset']+entry['bytes']]
    area = bytearray(flash[0x4000:]); package.sfc(area, 0, len(area), 0, package.KEY)
    descriptors = result['application_headers']
    index = next(i for i, e in enumerate(descriptors) if e['name'] == 'DX7.bin')
    descriptor = descriptors[index]
    if (index, descriptor['address'], descriptor['bytes']) != (3, 598631, 73226):
        raise ValueError('Unreviewed V16 factory resource placement')
    resource = bytes(area[descriptor['address']:descriptor['address']+descriptor['bytes']])
    header = package.jlfs_header(area[index*32:(index+1)*32])
    if package.crc16(resource) != header[1]:
        raise ValueError('Factory resource CRC mismatch')
    bank = resource[:16384]
    if bank != resource[16384:32768]:
        raise ValueError('V16 factory bank copies differ')
    records = []
    for slot in range(128):
        packed = bank[slot*128:(slot+1)*128]
        voice, changes = normalize_voice(packed)
        records.append(dict(slot=slot+1, name=bytes(voice[145:]).decode('ascii').rstrip(),
                            packed=list(packed), normalized_vced=voice, normalization=changes))
    prior = json.loads((ROOT/'third_party/oem_v15/voices.json').read_text(encoding='utf8'))
    same = [i+1 for i in range(128) if list(bank[i*128:(i+1)*128]) == prior['voices'][i]]
    result.update(source_url=URL, source_date='2026-10-21', factory_bank_sha256=hashlib.sha256(bank).hexdigest(),
                  factory_resource_crc16=header[1], duplicate_factory_banks=True,
                  same_slot_bytes_as_v15=same, changed_slots_from_v15=[i for i in range(1,129) if i not in same],
                  normalized_slots=[r['slot'] for r in records if any(r['normalization'].values())],
                  redistribution='Unverified for V16; private extraction only. Do not inherit the V15 resource grant.',
                  device_access=False, installable=False)
    return result, records, bank


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT/'private'):
        parser.error('Extracted voices must stay in ignored private/')
    result, records, bank = inspect(args.source.read_bytes())
    out.mkdir(parents=True, exist_ok=False)
    (out/'factory-original.vmem').write_bytes(bank)
    (out/'voice-records.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(report=str(out/'report.json'), voices=len(records),
                          changed_slots=result['changed_slots_from_v15'], normalized_slots=result['normalized_slots'])))


if __name__ == '__main__':
    main()
