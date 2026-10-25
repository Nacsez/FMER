"""Build/qualify the metadata-only next release without rebuilding the synth.

No device or network access. --activate selects the qualified files in the local
development catalog; it never replaces an existing binary or publishes anything.
"""
from pathlib import Path
import argparse
import copy
import json
import subprocess
import build_public_image
import fm1_package as package
import release_firmware as release

BASELINE_SHA = 'a953cd928543a333b9065e911b8b452757fce71944d4344cc8cb7c0e1b4e5e41'
LOADER_SHA = 'c640eff6f75a2a4a5cceb9d3cbb8dc9b461ae908d3aff4ce1cd4b554ff575634'


def convert(raw):
    if release.digest(raw) != BASELINE_SHA:
        raise ValueError('Expected the unchanged published 734-r2 package')
    identity, _, files = package.decode_package(raw)
    flash = files['flash.bin']['payload']
    if identity != 'FM-1_734' or flash[:0x4000] != release.distribution_head():
        raise ValueError('Unexpected baseline layout')
    if release.digest(package.validate_loader(files['ota.bin']['payload'])) != LOADER_SHA:
        raise ValueError('Unexpected baseline updater')
    updated = release.distribution_head(release.METADATA_FORMAT) + flash[0x4000:]
    return package.ufw(updated, files['ota.bin']['payload'], identity)


def build(baseline, out, loader_test, *, activate=False):
    raw = baseline.read_bytes()
    modern = convert(raw)
    out.mkdir(parents=True, exist_ok=False)
    name = 'fmer734-compatible-r3.fwsc'
    (out/name).write_bytes(modern)
    (out/'fmer734-compatible-r2.fwsc').write_bytes(raw)
    _, _, files = package.decode_package(modern)
    (out/'loader.bin').write_bytes(package.validate_loader(files['ota.bin']['payload']))
    (out/'device-head-fixture.bin').write_bytes(build_public_image.device_head_fixture())
    command = [str(loader_test.resolve()), str((out/name).resolve()),
               str((out/'loader.bin').resolve()), str((out/'device-head-fixture.bin').resolve())]
    result = subprocess.run(command, capture_output=True, text=True)
    (out/'loader-tests.json').write_text(json.dumps(dict(command=command, returncode=result.returncode,
        stdout=result.stdout, stderr=result.stderr), indent=2), encoding='utf-8')
    if result.returncode or 'passed' not in result.stdout.lower():
        raise ValueError('Independent loader checks failed; inspect loader-tests.json')
    old = copy.deepcopy(next(r for r in release.catalog() if r['id'] == release.PROFILE))
    if old['package_sha256'] != BASELINE_SHA or old['loader_sha256'] != LOADER_SHA:
        raise ValueError('Catalog baseline pins changed')
    # These are development source pins, not changes to the published catalog.
    build_sources = ('tools/stage_release_package.py', 'tools/build_release_firmware.py')
    # Build-only tools do not belong to the portable runtime's admission closure.
    # Record their provenance in the build report, not a runtime file requirement.
    sources = ({s['path'] for s in old['source_files']} - set(build_sources)) | {'tools/companion_loadouts.py','tools/companion_install_loadout.py'}
    old['source_files'] = [dict(path=s, sha256=release.digest((release.ROOT/s).read_bytes())) for s in sorted(sources)]
    old['package_format'] = release.LEGACY_FORMAT
    new = copy.deepcopy(old)
    new.update(id=release.METADATA_PROFILE, title='FMER 734 · package r3', filename=name,
               package_format=release.METADATA_FORMAT, package_sha256=release.digest(modern))
    catalog = dict(schema=1, releases=[old, new])
    (out/'catalog.json').write_text(json.dumps(catalog, indent=2)+'\n', encoding='utf-8')
    previous = release.CATALOG
    try:
        release.CATALOG = str((out/'catalog.json').resolve())
        inspections = [release.inspect_bytes(b) for b in (raw, modern)]
        if not all(r['available'] for r in release.available()):
            raise ValueError('Staged Companion catalog unavailable')
    finally:
        release.CATALOG = previous
    if activate:
        destination = (release.ROOT/release.CATALOG).parent
        for record, data in ((old, raw), (new, modern)):
            target = destination/record['filename']
            if target.exists() and target.read_bytes() != data:
                raise ValueError('Refusing to replace existing firmware bytes: '+str(target))
        for record, data in ((old, raw), (new, modern)):
            (destination/record['filename']).write_bytes(data)
        (release.ROOT/release.CATALOG).write_text(json.dumps(catalog, indent=2)+'\n', encoding='utf-8')
    report = dict(success=True, activated_locally=activate, device_opened=False, hardware_qualified=False,
        baseline_sha256=BASELINE_SHA, package_sha256=release.digest(modern), bytes=len(modern),
        application_and_updater_unchanged=True, inspections=inspections,
        build_sources=[dict(path=s, sha256=release.digest((release.ROOT/s).read_bytes())) for s in build_sources],
        loader_tests_sha256=release.digest((out/'loader-tests.json').read_bytes()))
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, default=release.ROOT/'firmware/releases/fmer734-compatible-r2.fwsc')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--loader-test', type=Path, required=True)
    p.add_argument('--activate', action='store_true')
    a = p.parse_args()
    r = build(a.baseline, a.out, a.loader_test, activate=a.activate)
    print(json.dumps({k:r[k] for k in ('success','activated_locally','package_sha256','bytes','hardware_qualified')}, indent=2))
