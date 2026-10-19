"""Build the supported FM-1 application region from licensed public data.

No device dump, vendor executable, download or hardware operation. Compatibility
is checked against the same fingerprint enforced by updater935 before writes.
"""
from pathlib import Path
import hashlib
import json
import fm1_package as p

ROOT=Path(__file__).resolve().parents[1]
PARAMETERS_SHA='309815c5307a4334cb6a8bed1febf999cdb911212c7254a37fe758a96abd668d'
LAYOUT_SHA='3c96f791076cb529d42be1225d42e4e5c820728e91c187e58682e3d7708acd88'

def resources():
    raw=(ROOT/'third_party/fm1_resources/parameters.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PARAMETERS_SHA:
        raise ValueError('Public configuration resource changed')
    data=json.loads(raw)
    blocks={}
    for item in data['blocks']:
        raw=bytes.fromhex(item['hex'])
        if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('Configuration resource block changed')
        blocks[item['name']]=raw
    if set(blocks)!={'cfg_tool.bin','eq_cfg_hw.bin'}:
        raise ValueError('Unexpected configuration resource')
    return blocks

def application_region(app):
    if not 4<=len(app)<=p.TEST01_APP_SLOT or app[:4]!=bytes.fromhex('04818000'):
        raise ValueError('Application size or entry differs from supported target')
    blocks=resources();cfg_tool=blocks['cfg_tool.bin'];eq=blocks['eq_cfg_hw.bin']
    app=app+b'\xff'*(p.TEST01_APP_SLOT-len(app))
    end=0x120+len(app)+len(cfg_tool)
    area=bytearray(b'\xff'*end)
    area[0x120:0x120+len(app)]=app;area[0x120+len(app):]=cfg_tool
    entries=[p.entry(p.crc16(app),0x120,len(app),0x82,255,0,'app.bin'),
        p.entry(p.crc16(cfg_tool),0x120+len(app),len(cfg_tool),0x82,255,0,'cfg_tool.bin'),
        p.entry(65535,0x93000,352256,0x12,0x80,0,bytes.fromhex('564d00ffffffffffffffffff00800000')),
        p.entry(65535,0,p.FLASH_SIZE,0x92,0x82,0,bytes.fromhex('5052435400ffffffffffffff434f4445')),
        p.entry(65535,0xe9000,4096,0x92,0x80,0,bytes.fromhex('4254494600ffffffffffffff4155544f')),
        p.entry(65535,0xea000,73728,0x92,0x80,1,'USR')]
    area[32:224]=b''.join(entries)
    area[:32]=p.entry(p.crc16(area[32:]),0x02000120,end,0x83,255,0,'app_area_head')
    cfg_body=p.entry(p.crc16(eq),64,len(eq),0x82,255,1,'eq_cfg_hw.bin')+eq
    region=area+p.entry(p.crc16(cfg_body),32,32+len(cfg_body),0x83,255,1,'cfg')+cfg_body
    p.sfc(region,0,len(region),0,p.KEY)
    region+=b'\xff'*(0x8f000-len(region))
    # Same exact non-application spans as loader/compatibility.h. Never widen
    # admission merely to make a newly constructed image pass.
    checked=b''.join(region[a:b] for a,b in ((4,32),(36,0x120),(0x8de3c,0x8efe0)))
    if len(region)!=0x8f000 or hashlib.sha256(checked).hexdigest()!=LAYOUT_SHA:
        raise ValueError('Generated layout/calibration differs from qualified hardware')
    p.app_layout(region,p.TEST01_APP_SLOT)
    return bytes(region)

def device_head_fixture():
    """Synthetic loader-test device; no real device's boot/calibration data."""
    import release_firmware
    head=bytearray(release_firmware.distribution_head())
    # Deterministic sentinel fills exercise preservation; this is not boot code.
    for i in range(160,len(head)):head[i]=(i*73+19)&255
    blob=p.key_blob(p.KEY)
    head[14544:14544+len(blob)]=blob
    return bytes(head)
