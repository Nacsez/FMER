# SPDX-License-Identifier: GPL-3.0-only
"""Read-only, hash-pinned official firmware package/layout research.

This is not a flash transport or admission bypass. It accepts only the two
publisher assets captured in the dated research record and emits JSON metadata.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import companion_stock
import fm1_package as package


def inspect(raw):
    known=companion_stock.known_file_info(raw)
    if known is None:raise ValueError('File does not match a reviewed official research asset')
    product=''.join(chr((raw[i*48+47]-i-1)&255) for i in range(20) if raw[i*48+47]!=0x7d)
    if product!=known['product']:raise ValueError('Publisher identity differs')
    logical=b''.join(raw[i*48:i*48+47] for i in range(20))+raw[960:]
    header=bytearray(logical[:64]);package.enc(header,0,64)
    total,count=struct.unpack_from('<IH',header,4)
    if total!=len(logical) or count not in (2,8):raise ValueError('Publisher package extent/count differs')
    if package.crc16(header[2:])!=int.from_bytes(header[:2],'little') or package.crc16(logical[64:64+80*count])!=int.from_bytes(header[2:4],'little'):
        raise ValueError('Publisher package directory CRC mismatch')
    records=[];flash=None;intervals=[]
    for i in range(count):
        entry=bytearray(logical[64+i*80:144+i*80]);package.enc(entry,0,80)
        typ,idx,checksum,reserved,offset,size,padded=struct.unpack_from('<HHHHIII',entry)
        name=bytes(entry[64:]).split(b'\0',1)[0].decode('ascii')
        if offset<1024 or offset+size>len(logical):raise ValueError('Publisher entry extent differs')
        if size and any(offset<end and start<offset+size for start,end in intervals):raise ValueError('Publisher entries overlap')
        if size:intervals.append((offset,offset+size))
        payload=logical[offset:offset+size]
        # Stock contains additional typed/encrypted resource formats. Their
        # directory checksums are not necessarily over stored bytes. The exact
        # publisher SHA pins them; only the reviewed flash/OTA codecs are checked.
        checked=name in ('flash.bin','ota.bin')
        if checked and package.crc16(payload)!=checksum:raise ValueError('Publisher entry CRC mismatch: '+name)
        records.append(dict(name=name,type=typ,index=idx,offset=offset,bytes=size,padded_bytes=padded,stored_crc_verified=checked,sha256=hashlib.sha256(payload).hexdigest()))
        if name=='flash.bin':flash=payload
    if flash is None:raise ValueError('No application flash entry')
    region=bytearray(flash[0x4000:]);package.sfc(region,0,len(region),0,package.KEY)
    headers=[]
    # Stock has seven inline directory entries; Open has six and a separate
    # EXT_RESERVED directory after its cfg_tool payload.
    n=7 if product=='FM-1_015' else 6
    for i in range(n):
        h=package.jlfs_header(region[i*32:i*32+32]);name=h[7].split(b'\0',1)[0].decode('ascii')
        headers.append(dict(name=name,address=h[2],bytes=h[3],flags=h[4:7]))
    app=headers[1]
    if app['name']!='app.bin':raise ValueError('Application record missing')
    code=region[app['address']:app['address']+app['bytes']]
    result=dict(known,product=product,package_entries=records,application_headers=headers,
                application_sha256=hashlib.sha256(code).hexdigest(),flash_extent=len(flash),
                supplied_boot_region_bytes=0x4000,device_access=False,installable=False)
    if product=='FM-1_8000013':
        offset=headers[0]['bytes']
        for relative in (0,32):
            h=package.jlfs_header(region[offset+relative:offset+relative+32])
            headers.append(dict(name=h[7].split(b'\0',1)[0].decode('ascii'),address=h[2],bytes=h[3],flags=h[4:7]))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();result=inspect(a.source.read_bytes());text=json.dumps(result,indent=2)+'\n'
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text,encoding='utf8')
    else:print(text,end='')


if __name__=='__main__':main()
