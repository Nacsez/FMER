"""Prepare a fresh source-only tree, without exporting private workspace history.

Uses the reviewed Corresponding Source allowlist, then public-facing metadata.
Does not run git init, contact a remote, publish, or clear distribution gates.
"""
from pathlib import Path
import argparse, hashlib, json, shutil, tempfile, zipfile
import build_companion_portable

R = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {'.git', 'private', 'local', 'artifacts', '__pycache__', 'Deploy',
                   'FM1_Research_Corpus_2026-09-29'}
FORBIDDEN_SUFFIXES = {'.rom', '.fwsc', '.exe', '.dll', '.wav', '.mp3', '.mp4', '.zip', '.pyc'}
BUILD_EVIDENCE = {'evidence/target-toolchain.json', 'evidence/msfa-source.json',
                  'evidence/python-portable-runtime.json', 'evidence/community-20261018.json',
                  'evidence/companion-community-20261020.json', 'evidence/companion-qa-20261021.json'}


def allowed(name):
    p=Path(name)
    return (not p.is_absolute() and '..' not in p.parts and
            not FORBIDDEN_PARTS.intersection(p.parts) and
            p.suffix.lower() not in FORBIDDEN_SUFFIXES and
            not any(part.startswith('Companion Appdata') for part in p.parts) and
            (not name.startswith('evidence/') or name in BUILD_EVIDENCE) and
            ('acquired' not in p.parts or name.startswith('third_party/acquired/fm1-target-review/community/felucca/')))


def prepare(out):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='fmer-source-') as tmp:
        build_companion_portable.source_archive(Path(tmp))
        with zipfile.ZipFile(Path(tmp)/'Corresponding Source.zip') as archive:
            for name in archive.namelist():
                if not allowed(name):raise ValueError('Source export rejects '+name)
                archive.extract(name,out)
    shutil.copy2(R/'CONTRIBUTING.md',out/'CONTRIBUTING.md')
    for name in ('.gitignore','.gitattributes'):
        shutil.copy2(R/'packaging'/('PUBLIC'+name),out/name)
    shutil.copytree(R/'.github',out/'.github')
    shutil.copy2(R/'packaging/PUBLIC_README.md',out/'README.md')
    shutil.copy2(R/'packaging/PUBLIC_AGENTS.md',out/'AGENTS.md')
    paths=sorted(p for p in out.rglob('*') if p.is_file())
    manifest=dict(format='FMER-PUBLIC-SOURCE',firmware=734,publication=False,
        gates='See docs/release/RELEASE_READINESS.md; preparation is not distribution clearance.',
        files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (out/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(out.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(out))
    print(json.dumps({'files':len(paths),'output':str(out),'published':False,'history_exported':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    prepare(p.parse_args().out)
