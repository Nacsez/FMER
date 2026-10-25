"""Stage the exact qualified 735/r11 assets; never uploads or publishes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import stage_github_release as base

R = Path(__file__).resolve().parents[1]


def stage(out, source):
    app = R / 'FMER Companion 735r11 Windows.zip'
    proof = R / 'artifacts/companion-startup-735r11/portable-qualified-test/report.json'
    record = base.verify_companion(app, proof, 'fm1-compatible-to-735-r9')
    if base.companion_revision(app) != 11:
        raise ValueError('Expected the qualified Companion r11')
    with zipfile.ZipFile(source) as z:
        manifest = json.loads(z.read('SOURCE_MANIFEST.json'))
        if manifest['firmware'] != 735 or set(z.namelist()) != set(manifest['files']) | {'SOURCE_MANIFEST.json'}:
            raise ValueError('Source manifest closure/build differs')
        for name, digest in manifest['files'].items():
            if hashlib.sha256(z.read(name)).hexdigest() != digest:
                raise ValueError('Source hash differs: ' + name)
        with zipfile.ZipFile(app) as a:
            root = a.namelist()[0].split('/')[0] + '/'
            files = json.loads(a.read(root + 'manifest.json'))['files']
            for name in files:
                if name.startswith(('tools/', 'host/', 'third_party/oem_v15/')) and z.read(name) != a.read(root + name):
                    raise ValueError('Release source/runtime mismatch: ' + name)
            sounds = a.read(root + 'Libraries/FMER Default Library.json')
    out.mkdir(parents=True, exist_ok=False)
    copies = {
        app: 'FMER-Companion-735-Windows-x64.zip',
        source: 'FMER-735-Source.zip',
        R / 'firmware/releases' / record['filename']: record['filename'],
        R / 'FMER Screen Sheets 735.zip': 'FMER-735-Screen-Atlas.zip',
        R / 'docs/release/media/fmer735-screen-sheet.png': 'FMER-735-Screen-Sheet.png',
        R / 'docs/release/media/fmer735-screen-sheet.pdf': 'FMER-735-Screen-Sheet.pdf',
        R / 'docs/release/INSTALLATION_735.md': 'INSTALLATION.md',
    }
    for origin, name in copies.items():
        shutil.copy2(origin, out / name)
    (out / 'FMER-735-Default-Sounds.fmer-catalog.json').write_bytes(sounds)
    files = {p.name: {'sha256': base.sha(p), 'bytes': p.stat().st_size}
             for p in sorted(out.iterdir()) if p.is_file()}
    base.dump(out / 'release-manifest.json', {
        'firmware': 735, 'firmware_revision': 9, 'companion_revision': 11,
        'tag': 'build-735-r11', 'draft': True, 'publication_authorized': False,
        'firmware_package_sha256': record['package_sha256'],
        'deployment_rehearsal_sha256': base.sha(proof), 'files': files,
        'limitations': 'See INSTALLATION.md and docs/release/RELEASE_NOTES_735.md'})
    (out / 'SHA256SUMS.txt').write_text(''.join(
        base.sha(p) + '  ' + p.name + '\n' for p in sorted(out.iterdir()) if p.is_file()), encoding='ascii')
    print(json.dumps({'output': str(out), 'assets': len(files) + 2, 'draft_only': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    stage(args.out, args.source)
