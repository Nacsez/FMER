"""Restore supported user-supplied stock V15 application, never its boot/identity.
Proprietary images are not bundled. Format and fixed application digest are
checked offline; existing portable loader repeats layout/calibration admission.
"""
import hashlib
import json
from pathlib import Path
import fm1_package as p
import fm1_flash_transport as t
import release_firmware as release
STOCK_PREFIX_SHA='176297a40fee9e8cfbeaf50b2eecec41e40afac3f78b0602deb9c03491f0a12c'
STOCK_SHA='8c1d13a5934eb3c70a5fec644577618a31b2a96c8748a7b692c506a86505dbb1'

# Exact publisher assets inspected 2026-10-18. Recognition is deliberately
# separate from installation admission: both use layouts outside loader935's
# qualified preservation contract. Never send their vendor loader implicitly.
OFFICIAL_FILES={
    'db1642b2b6fa5c2cccb11ffd13878068bb28601678d3644049f99dc40e7edb8a':dict(
        bytes=699956,product='FM-1_015',title='M-VAVE published Original V15',
        source_url='https://github.com/m-vave/fm1_open/blob/b178ac43c25f010c60a878056fb5331fe693fd62/sdk/firmware/FM-1_015.fwsc',
        license='Apache-2.0 resource grant; original component notices retained',
        reason='This is the official published V15 image. Its application is 672 bytes larger than the original-device V15 layout supported by this companion. Installing it needs a separately tested layout migration; no device was written.'),
    'c35330f1cad641f38908a6269c7316fdaf4ffb8b1091a7b3282fa31b9be9fe74':dict(
        bytes=479796,product='FM-1_8000013',title='M-VAVE Open V13',
        source_url='https://open.m-vave.com/assets/fm1/c35330f1cad641f38908a6269c7316fdaf4ffb8b1091a7b3282fa31b9be9fe74.bin',
        license='GPL-3.0-only with vendor SDK exception and separate component terms',
        reason='M-VAVE Open V13 is a separate firmware with a different project/sample memory layout. The companion has not qualified migration and rollback for that layout. Use a complete backup and the official Workbench after reviewing its instructions; this companion has not written the device.'),
}


def known_file_info(raw):
    """Recognize exact public files for human-readable, read-only inspection."""
    if not isinstance(raw,bytes) or len(raw)>2*1024*1024:return None
    digest=hashlib.sha256(raw).hexdigest();record=OFFICIAL_FILES.get(digest)
    if record is None:
        profiles=json.loads((Path(__file__).resolve().parents[1]/'host/firmware_compatibility.json').read_text(encoding='utf8'))
        record=next((r for r in profiles if r['sha256']==digest),None)
    if record is None or len(raw)!=record['bytes']:return None
    return dict(record,sha256=digest,recognized=True,installable=False,
                hardware_access=False,compatibility='layout migration not qualified')

def prepare(raw):
    if not isinstance(raw,bytes) or len(raw)>2*1024*1024:raise ValueError('Choose a supported stock V15 firmware or ROM backup file')
    official=known_file_info(raw)
    if official is not None:raise ValueError(official['reason'])
    if len(raw)==0x100000:region=raw[0x4000:0x93000]
    elif len(raw)==0x8f000:region=raw
    else:
        try:
            candidate=raw
            if len(raw)>=960 and bytes(raw[i*48+47] for i in range(8))==bytes(ord(c)+i+1 for i,c in enumerate('FM-1_015')) and all(raw[i*48+47]==0x7d for i in range(8,20)):
                candidate=bytearray(raw)
                for i,c in enumerate('FM-1_733'):candidate[i*48+47]=ord(c)+i+1
                candidate=bytes(candidate)
            _,_,files=p.decode_package(candidate);region=files['flash.bin']['payload'][0x4000:0x93000]
        except ValueError as e:raise ValueError('Unsupported stock file. Use your verified V15 ROM backup or supported application image; no device was written.') from e
    if len(region)!=0x8f000 or hashlib.sha256(region[:-32]).hexdigest()!=STOCK_PREFIX_SHA:raise ValueError('This stock image is not yet supported. No device was written; export diagnostics for compatibility review.')
    _,layout=p.app_layout(region,p.TEST01_APP_SLOT)
    bundled=release.bundled(release.PROFILE);validated=release.inspect_bytes(bundled)
    _,_,files=p.decode_package(bundled);current=files['flash.bin']['payload'];flash=release.distribution_head()+region
    for a,b in ((0x4004,0x4020),(0x4024,0x4120),(0x91e3c,0x92fe0)):
        if flash[a:b]!=current[a:b]:raise ValueError('Stock image layout/calibration differs from this supported installer')
    # Envelope denotes the known update transport; actual reboot target is015.
    cooked=p.ufw(flash,files['ota.bin']['payload'],release.TARGET)
    _,logical,files=p.decode_package(cooked);start=files['flash.bin']['offset']
    report=dict(product='FM-1_015',stock_restore=True,compatible_layout=True,runtime_preflight_qualified=True,
        loader_identity=release.LOADER,loader_image_bytes=validated['loader_image_bytes'],
        package_sha256=hashlib.sha256(cooked).hexdigest(),loader_sha256=validated['loader_sha256'],
        source_sha256=hashlib.sha256(raw).hexdigest(),stock_application_sha256=hashlib.sha256(region).hexdigest(),stock_prefix_sha256=STOCK_PREFIX_SHA,
        protected_sector=[0x92000,0x93000],head_written=False,settings_restored=False,
        files={n:{k:v for k,v in f.items() if k!='payload'} for n,f in files.items()})
    return t.QualifiedPackage(logical,report,start+0x4000,start+0x93000)

def perform(api,raw,journal):
    package=prepare(raw) # Revalidate source and bundled loader immediately before I/O.
    session=None
    try:
        journal.record('stock_restore_qualified',package=package.report)
        session=t.find_session(api,'compatible-FM-1',journal,wait=3)
        origin=session.verified_identity
        if origin==release.LOADER:raise t.UpdateError('An updater is already running. Complete that operation before restoring stock firmware.')
        if origin=='FM-1_015':
            journal.record('stock_already_running',identity=origin);return dict(firmware=origin,already_stock=True)
        journal.record('update_phase',phase='Preparing original firmware restore',stage=1)
        t.serve(session,package,1,journal)
        if session.close():raise t.UpdateError('Stock restore MIDI cleanup failed')
        session=None
        session=t.find_session(api,release.LOADER,journal,wait=45,transitional=origin,retry_identity_timeout=True)
        status=session.loader_control(t.CONTROL_STATUS);journal.record('stock_restore_admission',status=status)
        if status['state']==0 and status['app_dirty']:t.collect_metadata(session,package,journal)
        t.require_loader_ready(status,package,resume=False)
        journal.record('update_phase',phase='Restoring original firmware',stage=2)
        t.serve(session,package,2,journal)
        if session.close():raise t.UpdateError('Stock restore MIDI cleanup failed')
        session=None
        journal.record('update_phase',phase='Restarting and verifying original firmware',stage=3)
        session=t.find_session(api,'FM-1_015',journal,wait=45,transitional=release.LOADER,retry_identity_timeout=True)
        journal.record('stock_restore_complete',identity='FM-1_015',settings_restored=False)
        return dict(firmware='FM-1_015',settings_restored=False)
    finally:
        if session is not None and session.close():raise t.UpdateError('Stock restore MIDI cleanup failed; export operation record')
