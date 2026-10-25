# SPDX-License-Identifier: GPL-3.0-only
"""Package a reviewed sound-library folder; no firmware or device operations."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_rendered(source, manifest, analysis):
    """Require the measured set and actual media, not just an empty failure list."""
    patches=manifest.get('patches',[]);results=analysis.get('results',[])
    ids=[p['id'] for p in patches];result_ids=[r['id'] for r in results]
    if len(ids)!=192 or len(set(ids))!=192 or len(result_ids)!=192 or set(result_ids)!=set(ids):
        raise ValueError('Complete192-instrument render coverage required')
    lookup={r['id']:r for r in results};media=set()
    for patch in patches:
        result=lookup[patch['id']]
        if result['metrics'].get('failures') or result['metrics'].get('render_count')!=14 or len(result.get('measurements',[]))!=14:
            raise ValueError('Every instrument needs14 successful measured render cases')
        if patch.get('clips')!=result.get('clips') or patch.get('metrics')!=result.get('metrics') or len(patch.get('clips',[]))!=3:
            raise ValueError('Manifest and measured audio disagree; rebuild with --render')
        measured={m['test']:m for m in result['measurements']}
        for clip,slug in zip(patch['clips'],('performance','soft','dry')):
            path=(source/clip['path']).resolve()
            if not path.is_relative_to(source) or path.suffix!='.wav' or path in media or not path.is_file():
                raise ValueError('Expected576 distinct local WAV auditions')
            if sha(path)!=measured[slug]['sha256']:
                raise ValueError('Audition WAV differs from its measured SHA256')
            media.add(path)
    if len(media)!=576:raise ValueError('Incomplete audition media')


def package(source, destination):
    source=source.resolve();destination=destination.resolve()
    if not destination.is_relative_to(ROOT) or destination==ROOT or destination.exists():
        raise ValueError('Choose a new output folder inside the workspace; existing reviews are never removed')
    archive=destination.with_suffix('.zip')
    if archive.exists():
        raise ValueError('Archive already exists; choose a new output name')
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf8'))
    analysis=json.loads((source/'analysis.json').read_text(encoding='utf8'))
    validate_rendered(source,manifest,analysis)
    shutil.copytree(source,destination)
    (destination/'source').mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'NOTICE',destination/'NOTICE.txt')
    shutil.copyfile(ROOT/'third_party/msfa/COPYING',destination/'MSFA-LICENSE.txt')
    for name in ('sound_collections.py','sound_collection_fm.py','sound_collection_va.py','sound_collection_review.py','package_sound_collections.py'):
        shutil.copyfile(ROOT/'tools'/name,destination/'source'/name)
    guide=(ROOT/'docs/SOUND_COLLECTIONS_2026-10-22.md').read_text(encoding='utf8')
    guide=guide.replace('research/V16_PATCH_LICENSE_REVIEW.md','V16-PATCH-LICENSE.md').replace('../evidence/sound-collections-20261022.json','analysis.json')
    (destination/'DESIGN-AND-WORKFLOW.md').write_text(guide,encoding='utf8')
    shutil.copyfile(ROOT/'docs/research/V16_PATCH_LICENSE_REVIEW.md',destination/'V16-PATCH-LICENSE.md')
    for filename in ('EXPRESSIONS_FM_DESIGN.md','EXPRESSIONS_VA_DESIGN.md'):
        text=(ROOT/'docs/research'/filename).read_text(encoding='utf8')
        for prefix in ('../../tools/','../../tests/','../../core/'):
            text=text.replace(prefix,'source/')
        (destination/filename).write_text(text,encoding='utf8')
    for relative in ('tests/test_sound_collection_fm.py','core/synth.cpp','core/synth.hpp'):
        shutil.copyfile(ROOT/relative,destination/'source'/Path(relative).name)
    membership={p['id']:[] for p in manifest['patches']}
    for collection in manifest['collections']:
        for slot,identifier in enumerate(collection['patch_ids'],1):membership[identifier].append(collection['id']+str(slot).zfill(2))
    with (destination/'Instrument Catalog.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['ID','Device name','Title','Engine','Group','Category','Family','Loadout slots (1-based)','Audition MIDI note','Description','Technique'])
        for p in manifest['patches']:
            writer.writerow([p['id'],p['name'],p['title'],p['engine'],p['group'],p['category'],p['family'],', '.join(membership[p['id']]),p['audition_note'],p['description'],p['technique']])
    (destination/'READ ME FIRST.txt').write_text('''FMER EXPRESSIONS 1 - INSTRUMENT REVIEW

Open index.html. No installation, internet, Python or device needed.
Keep this entire folder together. The audio folder contains all576 auditions.

192 original sounds:128 FM +64 VA. Four64-slot collections:
A Spectrum (balanced proposed default), B Rhythm (drums/bass),
C Voltage (leads/arp/keys), D Atmosphere (pads/textures/expressive winds).

Mark Keep/Rework/Pass, favorite sounds, and write notes. Open Review loadout
slots to change any collection. Export review saves those choices to JSON.
Browser storage is convenient; exported JSON is the portable copy to keep.
Editing the review does not change existing bank downloads until rebuilt.

IMPORT INTO COMPANION
Library > Import file: choose All192 catalog or a Collection catalog under
libraries. Existing catalog items remain. Import is one Undo action. The limit
is512 items including Trash. Do not import all overlapping files needlessly.
Use Send selected to unit and review the slot destinations before confirming.
Projects refer to instrument slots: replacing a slot changes their sound.

The .fmer-banks.json files are optional PC-bank backups. Restoring one REPLACES
BOTH PC DEFAULT and PC USER banks with copies of that64-sound collection.
Back up PC banks first. No unit is written automatically. Use existing reviewed
Companion bank deployment separately. Do not treat these as unit backups.

The four .syx files contain128 FM voices only. They omit VA, effects, FMER LFO
enable state and project/performance settings. Native catalogs retain the full
sound. All4T tracks still share one FX chain; there is no independent per-track
reverb. The existing four-voice and64+64 onboard bank limits are unchanged.

A is a proposed next-release default, not a replacement of the published
firmware's Reset to FMER Default bank. Current published release is untouched.
This library has host/format/browser validation. Owner musical listening and
physical-device acceptance remain separate. No subjective quality guarantee
is inferred from numerical tests. The reviewer exposes conservative level
flags from4-note tests; they are not clipping failures.

COPYING AND SOURCE
Original FMER recipes and review software: GPL-3.0-only; see LICENSE.txt.
No OEM/V16 patch data included. Recipe source is under source; recipes.json
contains editable expanded data. Reproduction uses the FMER source repository
and its current host renderer: https://github.com/Nacsez/FMER
Audio analysis additionally uses NumPy2.4.3. Playback needs only a browser.
Read DESIGN-AND-WORKFLOW.md and the two engine-design notes for full scope.

checksums.json covers every included file except itself. Review JSON that you
export later is your own working document and is not part of those checksums.
''',encoding='utf8')
    checks={p.relative_to(destination).as_posix():sha(p) for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination/'checksums.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf8')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(destination.rglob('*')):
            if path.is_file():
                info=zipfile.ZipInfo(destination.name+'/'+path.relative_to(destination).as_posix(),(2026,10,22,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                bundle.writestr(info,path.read_bytes())
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:raise ValueError('Archive CRC validation failed')
        for relative,expected in checks.items():
            if hashlib.sha256(bundle.read(destination.name+'/'+relative)).hexdigest()!=expected:
                raise ValueError('Archive content verification failed: '+relative)
    result=dict(folder=str(destination),archive=str(archive),bytes=archive.stat().st_size,sha256=sha(archive),files=len(checks)+1,archive_verified=True)
    archive.with_suffix('.sha256.txt').write_text(result['sha256']+'  '+archive.name+'\n',encoding='ascii')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'artifacts/sound-collections-20261022/review')
    parser.add_argument('--output',type=Path,default=ROOT/'FMER Expressions 1')
    args=parser.parse_args();print(json.dumps(package(args.source,args.output),indent=2))
