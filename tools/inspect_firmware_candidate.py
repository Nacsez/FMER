# SPDX-License-Identifier: GPL-3.0-only
"""Offline candidate research, NEVER firmware installation admission.

The caller must supply the expected publisher/acquisition SHA256. This reads
bounded UFW/JLFS metadata only. It neither imports a MIDI adapter nor executes
the package's updater. A valid envelope does not imply a safe write procedure.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

import fm1_package as p


def inspect(raw, expected_sha256):
    if not isinstance(raw, bytes) or not 1024 <= len(raw) <= 2 * 1024 * 1024:
        raise ValueError('Candidate must be a bounded FWSC package')
    digest = hashlib.sha256(raw).hexdigest()
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha256) or digest != expected_sha256:
        raise ValueError('Candidate differs from its expected SHA256')
    marker = bytes((raw[i * 48 + 47] - i - 1) & 255 for i in range(20) if raw[i * 48 + 47] != 0x7d)
    product = marker.decode('ascii')
    if not re.fullmatch(r'FM-1_[0-9]{3,8}', product):
        raise ValueError('Unrecognized FM-1 product marker')
    logical = b''.join(raw[i * 48:i * 48 + 47] for i in range(20)) + raw[960:]
    header = bytearray(logical[:64]); p.enc(header, 0, 64)
    total, count = struct.unpack_from('<IH', header, 4)
    if total != len(logical) or not 1 <= count <= 12 or 64 + 80 * count > 1024:
        raise ValueError('Invalid package extent or entry count')
    if p.crc16(header[2:]) != int.from_bytes(header[:2], 'little') or p.crc16(logical[64:64 + 80 * count]) != int.from_bytes(header[2:4], 'little'):
        raise ValueError('Package directory checksum mismatch')
    entries, payloads, intervals = [], {}, []
    for i in range(count):
        e = bytearray(logical[64 + i * 80:144 + i * 80]); p.enc(e, 0, 80)
        typ, index, crc, reserved, off, size, padded = struct.unpack_from('<HHHHIII', e)
        name = bytes(e[64:]).split(b'\0', 1)[0].decode('ascii')
        if not name or name in payloads or off < 1024 or off + size > len(logical):
            raise ValueError('Invalid or duplicate package entry')
        if size and any(off < hi and lo < off + size for lo, hi in intervals):
            raise ValueError('Overlapping package entries')
        if size: intervals.append((off, off + size))
        body = logical[off:off + size]; payloads[name] = body
        checked = name in ('flash.bin', 'ota.bin')
        if checked and p.crc16(body) != crc:
            raise ValueError('Payload checksum mismatch: ' + name)
        entries.append(dict(name=name, type=typ, index=index, bytes=size, offset=off,
                            sha256=hashlib.sha256(body).hexdigest(), stored_crc_verified=checked))
    if not {'flash.bin', 'ota.bin'} <= payloads.keys():
        raise ValueError('Missing flash or updater entry')
    flash, ota = payloads['flash.bin'], payloads['ota.bin']
    if len(flash) < 0x4200:
        raise ValueError('Truncated flash metadata')
    area = bytearray(flash[0x4000:]); p.sfc(area, 0, len(area), 0, p.KEY)
    headers = []
    for i in range(9):
        block = area[i * 32:(i + 1) * 32]
        if block == b'\xff' * 32: break
        h = p.jlfs_header(block)
        name = h[7].split(b'\0', 1)[0].decode('ascii')
        headers.append(dict(name=name, address=h[2], bytes=h[3], flags=list(h[4:7])))
    if len(headers) < 2 or headers[0]['name'] != 'app_area_head' or headers[1]['name'] != 'app.bin':
        raise ValueError('Unrecognized application directory')
    root = p.jlfs_header(area[:32]); root_length = root[3]
    if not 0x100 <= root_length <= len(area) or p.crc16(area[32:root_length]) != root[1]:
        raise ValueError('Application directory body checksum mismatch')
    app = headers[1]; start, length = app['address'], app['bytes']
    if start < 0x100 or length < 4 or start + length > len(area):
        raise ValueError('Invalid application extent')
    app_head = p.jlfs_header(area[32:64])
    if p.crc16(area[start:start + length]) != app_head[1]:
        raise ValueError('Application checksum mismatch')
    # Open firmware places the USR descriptor in an EXT_RESERVED container.
    # Read its two fixed headers only; this remains metadata, never a write plan.
    if root_length + 64 <= len(area):
        tail = area[root_length:root_length + 32]
        if tail[16:29] == b'EXT_RESERVED\0':
            for off in (root_length, root_length + 32):
                h = p.jlfs_header(area[off:off + 32])
                headers.append(dict(name=h[7].split(b'\0',1)[0].decode('ascii'),
                                    address=h[2], bytes=h[3], flags=list(h[4:7])))
    return dict(product=product, sha256=digest, bytes=len(raw), entries=entries,
                flash_extent=len(flash), application_headers=headers,
                application_slot_bytes=length,
                application_sha256=hashlib.sha256(area[start:start + length]).hexdigest(),
                updater_sha256=hashlib.sha256(ota).hexdigest(),
                felucca_loader_marker=b'FELUCCA-LOADER-1' in ota,
                hardware_access=False, updater_executed=False, installable=False,
                classification='offline envelope/layout inspection; no installation qualification',
                limitations=['Non-flash/OTA typed resource checksums are not decoded.',
                             'Application directory addresses describe data; they are not approved write ranges.',
                             'No application startup, persistence, audio or recovery behavior was exercised.'])


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('source', type=Path)
    a.add_argument('--sha256', required=True)
    a.add_argument('--output', type=Path)
    args = a.parse_args()
    if args.source.stat().st_size > 2 * 1024 * 1024:
        a.error('Candidate exceeds research size limit')
    result = inspect(args.source.read_bytes(), args.sha256)
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf8')
    else: print(text, end='')


if __name__ == '__main__': main()
