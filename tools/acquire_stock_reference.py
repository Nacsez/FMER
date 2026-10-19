#!/usr/bin/env python3
"""Verify/extract the exact published V15 comparison reference; never access a unit.

Default: verify the existing ignored acquisition. --download explicitly fetches
the one pinned publisher URL. Vendor bytes remain outside source control and are
not a backup of FMER Test01. No downloaded program is executed.
"""
from __future__ import annotations
import argparse
import binascii
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
from urllib.request import Request, urlopen
import uuid

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/"third_party/acquired/stock-v15-reference"
URL="https://yms-file-store.oss-cn-hongkong.aliyuncs.com/software/firmware/FM-1.fwsc"
SIZE=699956
PACKAGE_SHA="db1642b2b6fa5c2cccb11ffd13878068bb28601678d3644049f99dc40e7edb8a"
APP_SHA="6edf3c37fb5bbbc33607c89375ee024d5477c17914d72221c8c68e58a8255686"
EQ_SHA="697b4fd0a82dae4a80f83180101a61de7d9e1fc951188e671350b18403c97007"


def decode_reference(raw: bytes) -> dict[str,bytes]:
    if len(raw)!=SIZE or hashlib.sha256(raw).hexdigest()!=PACKAGE_SHA:
        raise ValueError("Published V15 package does not match the pinned hash/size")
    logical=b"".join(raw[i*48:i*48+47] for i in range(20))+raw[960:]
    product="".join(chr((raw[i*48+47]-i-1)&255) for i in range(20) if raw[i*48+47]!=0x7D)
    def xor(data,key=0xFFFF):
        result=bytearray(data)
        for i in range(len(result)):
            result[i]^=key&255
            key=((key<<1)^(0x1021 if key&0x8000 else 0))&0xFFFF
        return bytes(result)
    def crc(data): return binascii.crc_hqx(data,0)
    h=xor(logical[:64]);total,count=struct.unpack_from("<IH",h,4)
    if product!="FM-1_015" or total!=len(logical) or count!=8 or crc(h[2:])!=int.from_bytes(h[:2],"little") or crc(logical[64:704])!=int.from_bytes(h[2:4],"little"):
        raise ValueError("V15 header/entry-list integrity failed")
    e=xor(logical[64:144]);typ,idx,checksum,res,off,n,pad=struct.unpack_from("<HHHHIII",e)
    if e[64:].rstrip(b"\0")!=b"flash.bin" or (typ,idx,off,n,pad)!=(0,0,1024,0x93000,0x93000):
        raise ValueError("Unexpected stock flash entry")
    flash=logical[off:off+n]
    if crc(flash)!=checksum: raise ValueError("Stock flash payload CRC failed")
    app=flash[0x4000:0x93000]
    if hashlib.sha256(app).hexdigest()!=APP_SHA: raise ValueError("Stock raw app hash failed")
    plain=b"".join(xor(app[i:i+32],0x980F^(i>>2)) for i in range(0,len(app),32))
    base=int.from_bytes(plain[8:12],"little")
    eq_header=plain[base+32:base+64]
    if len(eq_header)!=32 or crc(eq_header[2:])!=int.from_bytes(eq_header[:2],"little") or eq_header[16:].split(b"\0")[0]!=b"eq_cfg_hw.bin":
        raise ValueError("Stock EQ directory failed")
    eq_off,eq_len=struct.unpack_from("<II",eq_header,4)
    eq=plain[base+eq_off:base+eq_off+eq_len]
    if len(eq)!=2873 or crc(eq)!=int.from_bytes(eq_header[2:4],"little") or hashlib.sha256(eq).hexdigest()!=EQ_SHA:
        raise ValueError("Stock EQ/calibration integrity failed")
    return {"FM-1.fwsc":raw,"stock-v15-flash.bin":flash,"stock-v15-app-encrypted.bin":app,"eq_cfg_hw.bin":eq}


def preserve(path: Path,data: bytes):
    if path.exists():
        if path.read_bytes()!=data: raise ValueError(f"Refusing to overwrite differing acquisition: {path}")
    else:
        with path.open("xb") as stream: stream.write(data)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download",action="store_true")
    args=parser.parse_args(argv)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")+"-"+uuid.uuid4().hex[:8]
    out=ROOT/"artifacts/stock-reference"/stamp;out.mkdir(parents=True)
    report={"success":False,"source_url":URL,"download_requested":args.download,
            "device_access":False,"tool_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope":"Published comparison reference; not a Test01 backup. No redistribution grant."}
    try:
        if args.download:
            with urlopen(Request(URL,headers={"User-Agent":"FMER-source-audit/1"}),timeout=30) as response:
                if response.url!=URL: raise ValueError("Unexpected publisher download redirect")
                raw=response.read(SIZE+1)
        else:
            with (CACHE/"FM-1.fwsc").open("rb") as stream: raw=stream.read(SIZE+1)
        files=decode_reference(raw)
        CACHE.mkdir(parents=True,exist_ok=True)
        for name,data in files.items(): preserve(CACHE/name,data)
        report.update(success=True,files=[{"path":(CACHE/name).relative_to(ROOT).as_posix(),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()} for name,data in files.items()])
    except Exception as error: report["error"]=str(error)
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"success":report["success"],"report":str(out/"report.json"),"error":report.get("error")}))
    return 0 if report["success"] else 1


if __name__=="__main__": raise SystemExit(main())
