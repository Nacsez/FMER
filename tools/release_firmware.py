"""Self-contained, hash-pinned FMER distribution admission.
The portable updater admits changed application code on the compatible layout;
configuration/calibration must match the replacement outside code/CRC spans.
The exact stock digest is retained only for guarded abort, not install admission.
No private dump, SDK or build-tree lookup occurs in the shipped runtime.
"""
from pathlib import Path
import hashlib
import json
import re
import fm1_package as package

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'fm1-compatible-to-734-r1'
METADATA_PROFILE = 'fm1-compatible-to-734-r3'
FIRST_SIX_PROFILE = 'fm1-compatible-to-735-r1'
BANKS_PROFILE = 'fm1-compatible-to-735-r2'
GROUPED_PROFILE = 'fm1-compatible-to-735-r3'
CLICK_PROFILE = 'fm1-compatible-to-735-r4'
RAM_PROFILE = 'fm1-compatible-to-735-r5'
VALIDATION_PROFILE = 'fm1-compatible-to-735-r6'
UNROLLED_PROFILE = 'fm1-compatible-to-735-r7'
HANDOFF_PROFILE = 'fm1-compatible-to-735-r8'
NEXT_PROFILE = 'fm1-compatible-to-735-r9'
LEGACY_FORMAT = 'application-only-v1'
METADATA_FORMAT = 'self-describing-v1'
PROFILE_FORMATS = {PROFILE: LEGACY_FORMAT, METADATA_PROFILE: METADATA_FORMAT, NEXT_PROFILE: METADATA_FORMAT,FIRST_SIX_PROFILE: METADATA_FORMAT,BANKS_PROFILE: METADATA_FORMAT,GROUPED_PROFILE: METADATA_FORMAT,CLICK_PROFILE: METADATA_FORMAT,RAM_PROFILE: METADATA_FORMAT,VALIDATION_PROFILE: METADATA_FORMAT,UNROLLED_PROFILE: METADATA_FORMAT,HANDOFF_PROFILE: METADATA_FORMAT}
PROFILE_TARGETS = {PROFILE:'FM-1_734',METADATA_PROFILE:'FM-1_734',NEXT_PROFILE:'FM-1_735',FIRST_SIX_PROFILE:'FM-1_735',BANKS_PROFILE:'FM-1_735',GROUPED_PROFILE:'FM-1_735',CLICK_PROFILE:'FM-1_735',RAM_PROFILE:'FM-1_735',VALIDATION_PROFILE:'FM-1_735',UNROLLED_PROFILE:'FM-1_735',HANDOFF_PROFILE:'FM-1_735'}
ORIGIN_SHA = '8c1d13a5934eb3c70a5fec644577618a31b2a96c8748a7b692c506a86505dbb1'
TARGET = 'FM-1_735'
LOADER = 'ota-FM-1_935'
CATALOG = 'firmware/releases/catalog.json'

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def catalog():
    path = ROOT / CATALOG
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 1 or not isinstance(data.get('releases'), list):
        raise ValueError('Unsupported bundled firmware catalog')
    return data['releases']

def _record(identifier):
    matches = [r for r in catalog() if r.get('id') == identifier]
    if len(matches) != 1:
        raise ValueError('Unknown bundled firmware release')
    r = matches[0]
    if (r.get('id') not in PROFILE_FORMATS or
            r.get('package_format', LEGACY_FORMAT) != PROFILE_FORMATS[r['id']] or
            r.get('product') != PROFILE_TARGETS.get(r['id']) or
            r.get('origin_identity') != 'compatible-FM-1' or r.get('origin_app_sha256') != ORIGIN_SHA or
            r.get('loader_identity') != LOADER or r.get('record_address') != 0xE7F00 or
            r.get('qualification') != 'offline-qualified-first-install-preview'):
        raise ValueError('Bundled firmware admission profile differs')
    for field in ('package_sha256','loader_sha256','app_region_sha256','app_padded_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', r.get(field,'')):
            raise ValueError('Incomplete release hash pins')
    # Review includes the executed transport/format modules; tampering or stale
    # packaging cannot silently inherit an older qualification.
    sources = r.get('source_files')
    mandatory = {'tools/release_firmware.py','tools/fm1_flash_transport.py',
                 'tools/fm1_package.py','tools/hardware_bridge.py','tools/unit_endpoints.py',
                 'tools/compatible_firmware.py','tools/companion_loadouts.py','tools/companion_install_loadout.py'}
    if not isinstance(sources,list) or not mandatory.issubset({s.get('path') for s in sources}):
        raise ValueError('Missing release transport source pins')
    for s in sources:
        p=(ROOT/s['path']).resolve()
        if not p.is_relative_to(ROOT.resolve()) or not p.is_file() or digest(p.read_bytes())!=s['sha256']:
            raise ValueError('Release file changed or missing: '+s['path'])
    return r

def available():
    result=[]
    for item in catalog():
        try:
            r=_record(item['id']); p=_path(r)
            if digest(p.read_bytes())!=r['package_sha256']:
                raise ValueError('Bundled firmware file changed')
            result.append(dict(id=r['id'],title=r['title'],product=r['product'],
                origin_identity=r['origin_identity'],qualification=r['qualification'],available=True))
        except (ValueError,OSError,KeyError) as error:
            result.append(dict(id=item.get('id'),title=item.get('title','Bundled firmware'),available=False,error=str(error)))
    # The local next-release package is preferred without removing the stable
    # package needed for backward compatibility and original-firmware recovery.
    return sorted(result, key=lambda r: r['id'] != NEXT_PROFILE)

def _path(r):
    # Flat allowlist: a catalog cannot turn this into an arbitrary file reader.
    name=r.get('filename','')
    if not re.fullmatch(r'[a-z0-9_-]+\.fwsc',name):
        raise ValueError('Invalid release filename')
    return (ROOT/CATALOG).parent/name

def bundled(identifier):
    r=_record(identifier)
    raw=_path(r).read_bytes()
    if digest(raw)!=r['package_sha256']:
        raise ValueError('Bundled firmware checksum mismatch')
    return raw

def inspect_bytes(raw):
    """None means legacy inspection may try; never admit an unknown release."""
    sha=digest(raw)
    matches=[r for r in catalog() if r.get('package_sha256')==sha]
    if not matches:
        return None
    if len(matches)!=1:
        raise ValueError('Ambiguous bundled firmware hash')
    r=_record(matches[0]['id'])
    product,logical,files=package.decode_package(raw)
    flash=files['flash.bin']['payload']
    package_format=PROFILE_FORMATS[r['id']]
    if product!=r['product'] or len(flash)!=0x93000 or flash[:0x4000]!=distribution_head(package_format):
        raise ValueError('Release image target or protected-head sentinel differs')
    if digest(flash[0x4000:])!=r['app_region_sha256']:
        raise ValueError('Release application/calibration fingerprint differs')
    region,layout=package.app_layout(flash[0x4000:],package.TEST01_APP_SLOT)
    app=bytes(region[0x120:0x120+package.TEST01_APP_SLOT])
    loader=package.validate_loader(files['ota.bin']['payload'])
    if digest(loader)!=r['loader_sha256'] or digest(app)!=r['app_padded_sha256']:
        raise ValueError('Release loader/application checksum mismatch')
    if (loader.count(bytes.fromhex(ORIGIN_SHA))!=1 or
            (LOADER+'\0').encode() not in loader or (product+'\0').encode() not in app):
        raise ValueError('Release identities or exact stock admission are missing')
    return dict(product=product,release_profile=r['id'],package_format=package_format,origin_identity='compatible-FM-1',
        loader_identity=LOADER,origin_app_sha256=ORIGIN_SHA,origin_package_sha256=None,
        package_sha256=sha,loader_sha256=r['loader_sha256'],loader_image_bytes=len(loader),
        app_sha256_padded=r['app_padded_sha256'],raw_app_sha256=r['app_region_sha256'],
        template='reviewed-stock-v15',template_layout=layout,logical_bytes=len(logical),
        runtime_preflight_qualified=True,qualification=r['qualification'],hardware_qualified=False,
        target_executed=False,stock_calibration_preserved=True,head_written=False,
        app_write_range=[0x4000,0x93000],record_address=0xE7F00,compatible_layout=True,
        files={name:{k:v for k,v in f.items() if k!='payload'} for name,f in files.items()})

def update_identities(qualified):
    r=_record(qualified.report.get('release_profile'))
    expected={'product':r['product'],'origin_identity':'compatible-FM-1','loader_identity':LOADER,
        'package_format':PROFILE_FORMATS[r['id']],
        'origin_app_sha256':ORIGIN_SHA,'origin_package_sha256':None,'package_sha256':r['package_sha256'],
        'loader_sha256':r['loader_sha256'],'raw_app_sha256':r['app_region_sha256'],
        'app_write_range':[0x4000,0x93000],'record_address':0xE7F00}
    if any(qualified.report.get(k)!=v for k,v in expected.items()):
        raise ValueError('Release origin or write extent changed')
    extent=qualified.report['files']['flash.bin']['offset']
    if (qualified.app_begin,qualified.app_end)!=(extent+0x4000,extent+0x93000):
        raise ValueError('Release logical write boundary changed')
    return ('compatible-FM-1',LOADER,r['product'])


def distribution_head(package_format=LEGACY_FORMAT):
    # Stage1 traverses the top-level JLFS directory to locate app_dir_head.
    # These are format descriptors only, reconstructed from reviewed V15
    # metadata. No SPL or private configuration/identity payload is shipped.
    if package_format not in (LEGACY_FORMAT, METADATA_FORMAT):
        raise ValueError('Unknown firmware package format')
    import struct
    head=bytearray(struct.pack('<H',package.crc16(package.FLASH_HDR))+package.FLASH_HDR)
    for args in ((29128,160,14384,0,0,0,'uboot.boot'),
                 (28885,14544,699,2,128,0,'isd_config.ini'),
                 (65535,0x4000,0xffffffff,0x81,255,0,'app_dir_head'),
                 (65535,0xff000,0x1000,0x12,1,65535,'key_mac')):
        head.extend(package.entry(*args))
    for offset in range(0,len(head),32):package.enc(head,offset,32)
    head.extend(b'\xff'*(0x4000-len(head)))
    if package_format == METADATA_FORMAT:
        # Generated public SFC decoding metadata for tools that unpack the app
        # without a physical device. Updater935 never writes this region and
        # still obtains the real unit's key from the unit itself.
        head[14544:14578]=package.key_blob(package.KEY)
    return bytes(head)


def head_format(head):
    """Admit only our two exact generated heads, never arbitrary boot content."""
    for name in (LEGACY_FORMAT, METADATA_FORMAT):
        if head == distribution_head(name):
            return name
    raise ValueError('Firmware changes the protected boot descriptor or metadata')
