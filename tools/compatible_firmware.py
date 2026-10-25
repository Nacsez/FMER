"""Bounded application compatibility, using the unchanged reviewed 935 updater.

This admits transport/layout compatibility, not a third party's musical quality
or saved-data semantics. Never execute an unknown updater or move a partition.
The complete candidate is validated again immediately before any MIDI access.
"""
import re
import fm1_package as package
import release_firmware as release

PROFILE = 'fm1-935-application-v1'


def inspect_bytes(raw):
    product, logical, files = package.decode_package(raw, compatible_identity=True)
    if raw != package.ufw(files['flash.bin']['payload'], files['ota.bin']['payload'], product):
        raise ValueError('Custom firmware requires the canonical FWSC envelope')
    if not re.fullmatch(r'FM-1_[0-9]{3,8}', product):
        raise ValueError('Firmware must report an FM-1 numeric application identity')
    record = release._record(release.PROFILE)
    loader = package.validate_loader(files['ota.bin']['payload'])
    if release.digest(loader) != record['loader_sha256']:
        raise ValueError('This package uses a different updater. Companion supports the reviewed FMER 935 updater only; use the firmware publisher’s installer for this file.')
    flash = files['flash.bin']['payload']
    if len(flash) != 0x93000:
        raise ValueError('Firmware changes the protected boot descriptor or application extent')
    package_format = release.head_format(flash[:0x4000])
    region, layout = package.app_layout(flash[0x4000:], package.TEST01_APP_SLOT)
    _, _, baseline = package.decode_package(release.bundled(release.PROFILE))
    original, _ = package.app_layout(baseline['flash.bin']['payload'][0x4000:], package.TEST01_APP_SLOT)
    end = 0x120 + package.TEST01_APP_SLOT
    # Only app bytes and the two directory CRC pairs may differ.
    for start, stop in ((4, 32), (36, 0x120), (end, len(region))):
        if region[start:stop] != original[start:stop]:
            raise ValueError('Firmware changes protected layout, configuration or calibration')
    app = bytes(region[0x120:end])
    if app[:4] != bytes.fromhex('04818000') or (product+'\0').encode('ascii') not in app:
        raise ValueError('Firmware entry instruction or application identity does not match')
    return dict(product=product, compatible_profile=PROFILE, package_format=package_format, origin_identity='compatible-FM-1',
                loader_identity=release.LOADER, package_sha256=release.digest(raw),
                loader_sha256=record['loader_sha256'], loader_image_bytes=len(loader),
                raw_app_sha256=release.digest(flash[0x4000:]), app_sha256_padded=release.digest(app),
                app_write_range=[0x4000, 0x93000], record_address=0xE7F00,
                compatible_layout=True, runtime_preflight_qualified=True,
                hardware_qualified=False, target_executed=False, head_written=False,
                qualification='935 transport/layout compatible; application not release-qualified',
                compatibility='Reviewed updater and memory layout; custom application',
                logical_bytes=len(logical), template_layout=layout,
                files={n:{k:v for k,v in f.items() if k!='payload'} for n,f in files.items()})


def update_identities(qualified):
    """Recheck the executable loader, layout and report against the logical bytes."""
    r = qualified.report
    if r.get('compatible_profile') != PROFILE:
        raise ValueError('Unknown application compatibility profile')
    pieces = {}
    for name in ('flash.bin', 'ota.bin'):
        entry = r['files'][name]
        offset, size = entry['offset'], entry['bytes']
        if type(offset) is not int or type(size) is not int or offset < 1024 or size <= 0 or offset+size > len(qualified.image):
            raise ValueError('Invalid compatibility payload extent')
        pieces[name] = qualified.image[offset:offset+size]
    # Canonical reconstruction also binds offsets, checksums and header identity;
    # transport accepts only this canonical envelope for a custom application.
    raw = package.ufw(pieces['flash.bin'], pieces['ota.bin'], r['product'])
    actual = inspect_bytes(raw)
    if actual != r:
        raise ValueError('Compatible firmware report or application changed')
    offset = r['files']['flash.bin']['offset']
    if (qualified.app_begin, qualified.app_end) != (offset+0x4000, offset+0x93000):
        raise ValueError('Compatible firmware write boundary changed')
    return 'compatible-FM-1', release.LOADER, r['product']
