# SPDX-License-Identifier: GPL-3.0-only
"""Extract only the OEM voice resource from the pinned, licensed public V15 file.

No private dump, firmware execution or device access. This is a build tool;
Companion reads the resulting attributed voice data offline.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import acquire_stock_reference as reference
import fm1_package as package
import fm1_stock_catalog as stock


def extract(raw):
    reference.decode_reference(raw)  # Exact publisher hash plus nested app checks.
    logical = b''.join(raw[i*48:i*48+47] for i in range(20)) + raw[960:]
    entry = bytearray(logical[224:304]); package.enc(entry, 0, 80)
    typ, index, crc, reserved, offset, size, padded = struct.unpack_from('<HHHHIII', entry)
    if (typ, index, offset, size, padded, bytes(entry[64:]).rstrip(b'\0')) != (50, 2, 603136, 73226, 73248, b'USR'):
        raise ValueError('Unexpected OEM resource descriptor')
    data = bytearray(logical[offset:offset+size])
    # SFC mixes the absolute UFW payload address, not the destination flash address.
    package.sfc(data, 0, len(data), -offset, package.KEY)
    if package.crc16(data) != crc:
        raise ValueError('OEM resource checksum mismatch')
    bank = bytes(data[:16384])
    if bank != data[16384:32768]:
        raise ValueError('Published OEM bank copies differ')
    voices = [list(bank[i*128:(i+1)*128]) for i in range(128)]
    for voice in voices: stock.unpack_voice(bytes(voice))
    return dict(format='FMER-OEM-V15-VOICES', version=1,
                source_url='https://github.com/m-vave/fm1_open/blob/b178ac43c25f010c60a878056fb5331fe693fd62/sdk/firmware/FM-1_015.fwsc',
                source_sha256=reference.PACKAGE_SHA, resource_crc16=crc,
                bank_sha256=hashlib.sha256(bank).hexdigest(), license='Apache-2.0',
                modification='Extracted 128 original packed FM voices; firmware, settings and other resources omitted. Normalization is reported at import.',
                voices=voices)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();result=extract(args.package.read_bytes())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='voices'}))
