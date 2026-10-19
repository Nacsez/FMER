"""Build the reviewed Newlib/LLVM subset. No downloads, installers or devices.

The compiler and its normal headers remain external prerequisites. No vendor
runtime archive is read or linked by this builder. Each source is hash-checked.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'third_party/runtime'
ARCHIVER = {'path': 'bin/llvm-ar.exe',
            'sha256': '0b436f8d2ab4f5750fe70ac0b9c6e0028b8188cd3ef0eb29413b967a002dd822'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root=SOURCE):
    root = root.resolve()
    data = json.loads((root / 'PROVENANCE.json').read_text(encoding='utf8'))
    if data.get('schema') != 1 or len(data.get('units', [])) != 49:
        raise ValueError('Unreviewed runtime manifest')
    seen = set()
    for entry in data['files']:
        name = entry['path']
        path = (root / name).resolve()
        if name in seen or not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Missing, duplicate or unsafe runtime source: ' + name)
        if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            raise ValueError('Runtime source changed: ' + name)
        seen.add(name)
    units = set()
    for unit in data['units']:
        key = (unit['archive'], unit['member'])
        if (unit['source'] not in seen or not unit['source'].endswith('.c') or
                unit['archive'] not in ('libc.a', 'libm.a', 'libcompiler-rt.a') or
                Path(unit['member']).name != unit['member'] or
                unit['optimization'] not in ('-Oz', '-Os', '-O2') or key in units):
            raise ValueError('Invalid runtime compilation unit')
        units.add(key)
    return data


def build(toolchain, out, checked):
    """Compile objects in the recorded library/member order, then archive them.

    Keep upstream sections together to minimize differences from the reference
    runtime. No fast-math, allocation, operating-system or radio code is added.
    checked(name, argv) must persist stdout/stderr and reject nonzero exit codes.
    """
    data = verify()
    if digest(toolchain / ARCHIVER['path']) != ARCHIVER['sha256']:
        raise ValueError('Pinned runtime archiver changed')
    out.mkdir(parents=True, exist_ok=False)
    common = [str(toolchain / 'bin/clang.exe'), '-target', 'pi32v2', '-mcpu=r3',
              '-fno-builtin', '-resource-dir', str(toolchain / 'lib/clang/4.0.1'),
              '-isystem', str(toolchain / 'pi32v2-include'),
              '-I', str(SOURCE / 'newlib/newlib/libm/common')]
    objects = {}
    for unit in data['units']:
        source = SOURCE / unit['source']
        folder = out / 'objects' / unit['archive']
        folder.mkdir(parents=True, exist_ok=True)
        obj = folder / unit['member']
        checked('runtime-' + unit['member'], common + [unit['optimization'],
                '-I', str(source.parent), '-c', str(source), '-o', str(obj)])
        objects.setdefault(unit['archive'], []).append(obj)
    archives = []
    for name, members in objects.items():
        archive = out / name
        checked('runtime-archive-' + name, [str(toolchain / 'bin/llvm-ar.exe'),
                'rcs', str(archive)] + [str(p) for p in members])
        archives.append({'name': name, 'sha256': digest(archive),
                         'objects': [{'name': p.name, 'sha256': digest(p)} for p in members]})
    report = {'kind': 'source-built-runtime', 'manifest_sha256': digest(SOURCE / 'PROVENANCE.json'),
              'vendor_binary_archives': False, 'archives': archives,
              'hardware_qualified': False, 'archiver': ARCHIVER}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    return report
