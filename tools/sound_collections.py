# SPDX-License-Identifier: GPL-3.0-only
"""Build original, reviewable FMER sound collections without device access.

The recipe modules are authored source. Native/catalog/SysEx exports and audio
are reproducible derivatives. No OEM library or live user state is an input.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid
import wave

import companion_bank as bank
import companion_shelf as shelf
import companion_transfer as transfer
import library
import sandbox

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'FMER Expressions 2'
DATE = '2026-10-24T00:00:00+00:00'
GROUPS = ('percussion', 'bass', 'keys', 'winds', 'leads', 'pads', 'textures')
SOUND_CONTROLS = set(range(145)) | set(range(145, 153)) | {159} | set(range(160, 178)) | {194}


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True) + '\n', encoding='utf8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def recipes():
    import sound_collection_fm
    import sound_collection_va
    from sound_collection_revision2 import revise
    rows = revise(sound_collection_fm.recipes() + sound_collection_va.recipes())
    if len(rows) != 192 or len({r['id'] for r in rows}) != 192 or len({r['name'] for r in rows}) != 192:
        raise ValueError('Expected 192 distinct instrument identities and device names')
    for row in rows:
        if not re.fullmatch(r'(fm|va)_[a-z0-9_]+', row['id']):
            raise ValueError('Unsafe instrument identifier')
        if row['group'] not in GROUPS:
            raise ValueError('Unknown musical group')
    return rows


def make_entry(recipe, template):
    state = bank.native.canonical_sound(deepcopy(template))
    state['preset_id'] = bank.native.CUSTOM_PRESET
    state['source_generation'] = 0
    c = state['controls']
    c[145:154] = [0, 0, 0, 0, 0, 0, 150, 0, 0]
    c[159:178] = [0, 0, 0, 20000, 0, 0, 300, 100, 150, 0, 0, 0, 250, 30, 0, 0, 500, 0, 18000]
    c[178:186] = [120, 0, 0, 16, 1, 75, 0, 50]
    c[191:195] = [4, 0, 0, 50]
    state['fx_order'] = 0
    state['modulation_profiles'] = list(recipe.get('modulation_profiles', [0, 0]))
    if 'vced' in recipe:
        state['vced'] = list(recipe['vced'])
    else:
        # VA shares transpose and name with the patch record. Other FM values
        # have no VA effect, but remain a valid neutral FM INIT rather than a
        # hidden copy of a factory instrument.
        state['vced'] = [0] * 155
        for op in range(6):
            state['vced'][21*op:21*(op+1)] = [99,99,99,80,99,99,99,0,48,0,0,0,0,0,0,0,80 if op == 5 else 0,0,1,0,7]
        state['vced'][126:145] = [99,99,99,99,50,50,50,50,31,0,1,30,0,0,0,1,4,0,24]
    c[:145] = state['vced'][:145]
    for control, value in recipe.get('controls', {}).items():
        control = int(control)
        if control not in SOUND_CONTROLS:
            raise ValueError(f'Recipe cannot alter arrangement or voice mode: {control}')
        c[control] = value
        if control < 145:
            state['vced'][control] = value
    name = recipe['name']
    state['vced'][145:] = list(name.ljust(10).encode('ascii'))
    state = bank.native.canonical_sound(state)
    entry = dict(name=name, category=recipe['category'], favorite=False,
                 audition_note=recipe['audition_note'], native=bank.pack(state))
    bank.BankLibrary.validate_entry(entry)
    return entry


def collections(rows):
    selection=ROOT/'tools/sound_collection_selection.json'
    if selection.is_file():
        selected=json.loads(selection.read_text(encoding='utf8'))
        if selected['library_version']!=VERSION:raise ValueError('Stale curated selection')
        return deepcopy(selected['profiles'])
    grouped = {(engine, group): [r['id'] for r in rows if r['id'].startswith(engine+'_') and r['group'] == group]
               for engine in ('fm', 'va') for group in GROUPS}
    b_bass = grouped['fm', 'bass'][:8] + grouped['va', 'bass'][:8]
    b = grouped['fm', 'percussion'] + grouped['va', 'percussion'] + b_bass
    c = grouped['fm', 'bass'][8:] + grouped['va', 'bass'][8:] + grouped['fm', 'leads'] + grouped['va', 'leads'] + grouped['fm', 'keys'] + grouped['va', 'keys']
    d = grouped['fm', 'pads'] + grouped['va', 'pads'] + grouped['fm', 'textures'] + grouped['fm', 'winds']
    a = []
    for engine, counts in [('fm', (8,4,6,6,3,3,2)), ('va', (6,5,5,0,8,8,0))]:
        for group, count in zip(GROUPS, counts):
            choices = grouped[engine, group]
            # Spread the balanced bank across each role, not just its first
            # neighboring variations. Owner curation can replace any slot.
            a.extend(choices[(i*len(choices))//count] for i in range(count))
    result = [dict(id=letter, title=title, description=desc, patch_ids=ids) for letter,title,desc,ids in [
        ('A','A / Spectrum','Balanced proposed default: 32 FM and 32 VA instruments, from rhythm to atmosphere.',a),
        ('B','B / Rhythm','48 percussion voices and 16 basses. Electronic, tuned, noisy and metallic rhythm colors.',b),
        ('C','C / Voltage','Leads, arpeggio voices, keys, mallets and the remaining bass characters.',c),
        ('D','D / Atmosphere','Pads, evolving textures, experimental voices and expressive winds for ambient arrangements.',d)]]
    if any(len(x['patch_ids']) != 64 or len(set(x['patch_ids'])) != 64 for x in result):
        raise ValueError('Each initial collection must contain64 distinct sounds')
    if set.union(*(set(x['patch_ids']) for x in result)) != {r['id'] for r in rows}:
        raise ValueError('At least one instrument is absent from every collection')
    return result


def apply_curation(profiles, rows, curation):
    if not isinstance(curation, dict) or curation.get('format') != 'FMER-SOUND-CURATION' or curation.get('schema') != 1 or curation.get('library_version') != VERSION:
        raise ValueError('Curation belongs to a different library/version')
    source = curation.get('collections')
    if not isinstance(source, dict) or set(source) != {'A','B','C','D'}:
        raise ValueError('Curation requires exactly four collections')
    known = {r['id'] for r in rows}
    for values in source.values():
        if not isinstance(values, list) or len(values) != 64 or any(not isinstance(x,str) or x not in known for x in values):
            raise ValueError('Each curated collection needs64 known instrument IDs')
    result = deepcopy(profiles)
    engines={r['id']:r['id'][:2] for r in rows}
    for profile in result:
        profile['patch_ids'] = list(source[profile['id']])
        fm=sum(engines[i]=='fm' for i in profile['patch_ids'])
        profile['description']=f'Owner-curated 64-slot loadout: {fm} FM and {64-fm} VA placements. See the ordered slots for your selections.'
    return result


def catalog(rows, entries, title):
    items = []
    for index, row in enumerate(rows):
        item = dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, VERSION+':'+title+':'+str(index)+':'+row['id'])),
                    kind='instrument', title=f'{index+1:03d} {row["title"]}'[:80], collection=title,
                    tags=list(dict.fromkeys([row['id'][:2].upper(), row['group'], *row['tags']]))[:12],
                    notes=(row['description']+' '+row['technique']+' Original FMER recipe; GPL-3.0-only.')[:1000],
                    favorite=False, entry=entries[row['id']], dependencies={}, created=DATE, updated=DATE, trashed=False)
        shelf.Catalog.validate_item(item)
        items.append(item)
    return shelf.envelope(dict(format=shelf.FORMAT, version=1, capacity=shelf.CAPACITY, revision=0, slots=items, undo_slots=None))


def audio_metrics(path):
    import numpy as np
    with wave.open(str(path), 'rb') as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise ValueError('Expected mono signed16 WAV from shared renderer')
        sr = wav.getframerate()
        signal = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.float64)/32768
    power = signal*signal
    peak = float(np.max(np.abs(signal)))
    # Aggregate spectral measurements across time; do not confuse this proxy
    # with perceptual quality or a claim of listening acceptance.
    blocks = [signal[i:i+4096] for i in range(0,min(len(signal),sr*4)-4095,4096)]
    spectrum = np.mean([np.abs(np.fft.rfft(b*np.hanning(4096)))**2 for b in blocks],axis=0)
    freq = np.fft.rfftfreq(4096,1/sr)
    centroid = float(np.sum(freq*spectrum)/(np.sum(spectrum)+1e-20))
    return dict(peak=peak, rms=float(np.sqrt(np.mean(power))), dc=float(np.mean(signal)),
                centroid_hz=round(centroid,2), high_band_fraction=float(np.sum(spectrum[freq>4000])/(np.sum(spectrum)+1e-20)),
                final_half_second_rms=float(np.sqrt(np.mean(power[-sr//2:]))),
                sample_rate=sr, seconds=len(signal)/sr, sha256=digest(path))


def dry(settings):
    value = deepcopy(settings)
    for key in ('drive','chorus','delay','reverb','phaser'):
        value['effects'][key] = 0
    # Preserve intentional shared HP/BP/LP tone shaping: this is the designed
    # instrument with time/modulation FX removed, not unfiltered oscillator.
    return value


def phrase(row, settings):
    value = deepcopy(settings)
    value.update(duration=6, tail=5, budget=4)
    if row['group'] in ('pads','textures','winds'):
        value.update(scenario='chord' if row['group']=='pads' else 'note',duration=8,tail=6)
        return value
    root = row['audition_note']
    drums = row['group'] == 'percussion'
    pitches = [0,0,128,0,0,128,0,0,0,128,0,0,128,0,0,128] if drums else [0,128,7,12,128,3,7,128,0,10,7,128,3,128,7,12]
    steps=[]
    for i, offset in enumerate(pitches):
        steps.append(dict(notes=[] if offset ==128 else [dict(pitch=min(127,root+offset),velocity=[64,100,80,120][i%4])],gate=45 if drums else 65))
    value.update(scenario='sequence',bpm=110,pattern=dict(length=16,channel=0,steps=steps))
    return value


def render_one(row, entry, executable, work, destination):
    base = bank.render_settings(entry)
    base.update(duration=2,tail=4,budget=4)
    requests = [('performance','Phrase / stored FX','performance',phrase(row,base)),
                ('soft','Dry soft touch / velocity48','velocity',dry({**base,'velocity':48})),
                ('dry','Dry / velocity120','dry',dry({**base,'velocity':120}))]
    # Three registers x three velocities plus an explicit long release check.
    for note in sorted({max(12,row['audition_note']-12),row['audition_note'],min(108,row['audition_note']+12)}):
        for velocity in (48,88,120):
            requests.append((f'n{note}-v{velocity}','Matrix','matrix',{**dry(base),'note':note,'velocity':velocity,'duration':2,'tail':2}))
    requests.append(('release','Release','matrix',{**dry(base),'duration':4,'tail':10,'velocity':120}))
    root=row['audition_note']
    chord_steps=[dict(notes=[dict(pitch=min(127,root+d),velocity=120) for d in (0,3,7,10)],gate=100)]
    chord_steps.extend(dict(notes=[],tie=True,gate=100) for _ in range(7))
    requests.append(('chord4','Four-voice headroom','matrix',{**base,'scenario':'sequence','duration':2,'tail':6,'velocity':120,
                     'pattern':dict(length=8,channel=0,steps=chord_steps)}))
    clips=[];measurements=[]
    for slug,label,kind,request in requests:
        request_key=hashlib.sha256(library.canonical(dict(request=request,executable_sha256=digest(executable)))).hexdigest()
        cached=work/row['id']/('cache-'+request_key+'.json')
        measured=json.loads(cached.read_text(encoding='utf8')) if cached.is_file() else None
        if measured is not None:
            source=work/row['id']/measured['request_id']/'render.wav'
            if not source.is_file() or digest(source)!=measured['wav_sha256']:
                measured=None
        if measured is None:
            measured = sandbox.render_request(request,executable,output=work/row['id'])
            dump(cached,measured)
        source = work/row['id']/measured['request_id']/'render.wav'
        stats=audio_metrics(source)
        stats.update(kind=kind,test=slug,note=request['note'],velocity=request['velocity'],
                     clipped_samples=measured['clipped_samples'],fx_clipped_samples=measured['fx_clipped_samples'],
                     rejected_events=measured['rejected_events'],sanitized_samples=measured['fx_sanitized_samples'],
                     active_voices_end=measured['active_voices_end'],source=str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source))
        measurements.append(stats)
        if kind != 'matrix':
            filename=f'{row["id"]}-{slug}.wav'
            shutil.copyfile(source,destination/'audio'/filename)
            clips.append(dict(label=label,kind=kind,path='audio/'+filename,peak=stats['peak'],rms=stats['rms']))
    dump(work/row['id']/'analysis.json',measurements)
    failures=[m['test'] for m in measurements if m['clipped_samples'] or m['fx_clipped_samples'] or m['rejected_events'] or m['sanitized_samples'] or m['peak']<0.0001]
    warnings=[]
    release=next(m for m in measurements if m['test']=='release')
    if release['final_half_second_rms']>0.001: warnings.append('Audible tail remains after10s dry release')
    if max(m['peak'] for m in measurements)>.75: warnings.append('High output; review chord/mix headroom')
    if min(m['peak'] for m in measurements if m['kind']=='matrix')<.008: warnings.append('Quiet at a tested register/velocity')
    return dict(id=row['id'],clips=clips,metrics=dict(peak=max(m['peak'] for m in measurements),
        failures=failures,warnings=warnings,render_count=len(measurements),
        dry_centroid_hz=measurements[2]['centroid_hz'],dry_rms=measurements[2]['rms'],
        release_end_rms=release['final_half_second_rms']),measurements=measurements)


def build(output, executable, *, render=False, workers=4, curation=None):
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    rows=recipes();profiles=collections(rows)
    if curation is not None: profiles=apply_curation(profiles,rows,curation)
    template=bank.decode_record(bank.classic_profile(executable)[0]['native'])
    entries={row['id']:make_entry(row,template) for row in rows}
    lookup={row['id']:row for row in rows}
    downloads=[]
    all_path='libraries/All 192 Instruments.fmer-catalog.json'
    dump(output/all_path,catalog(rows,entries,VERSION))
    downloads.append(dict(label='All192 instruments / Companion catalog',path=all_path))
    # Exact encoded parameter equality, ignoring labels, is the minimum
    # uniqueness gate. Perceptual similarity still requires human curation.
    fingerprints=[]
    for entry in entries.values():
        s=bank.decode_record(entry['native']);s['vced'][145:]=[32]*10
        fingerprints.append(hashlib.sha256(bank.native.encode(s)).hexdigest())
    if len(set(fingerprints)) != len(rows): raise ValueError('Duplicate parameter recipes')
    for profile in profiles:
        selected=[lookup[i] for i in profile['patch_ids']]
        stem=f'Collection {profile["id"]}'
        filename='libraries/'+stem+'.fmer-catalog.json'
        dump(output/filename,catalog(selected,entries,VERSION+' / '+profile['title']))
        downloads.append(dict(label=stem+' /64-instrument catalog',path=filename))
        slots=[deepcopy(entries[i]) for i in profile['patch_ids']]
        payload=dict(format='FMER-SOUNDBANK',version=1,profile=bank.PROFILE,capacity=128,revision=0,
                     slots=slots+deepcopy(slots),undo_slots=None)
        validation=bank.BankLibrary(output/'validation-only',executable,defaults=slots)
        validation._validate_state(payload)
        filename='libraries/'+stem+'.fmer-banks.json'
        dump(output/filename,bank.BankLibrary._envelope(payload))
        downloads.append(dict(label=stem+' /PC banks (replaces DEFAULT and USER on PC)',path=filename))
        # These reviewed rows are developer artifacts; never presented as a
        # file the existing Companion can directly import.
        transfer_rows=[dict(kind='instrument',slot=64+i,entry=entry) for i,entry in enumerate(slots)]
        dump(output/('plans/'+stem+'.json'),dict(rows=transfer_rows,review=transfer.plan(transfer_rows)))
    codec=library.PatchCodec(executable,lambda *_a,**_k:None)
    fm=[r for r in rows if r['id'].startswith('fm_')]
    for start in range(0,len(fm),32):
        voices=[bank.decode_record(entries[r['id']]['native'])['vced'] for r in fm[start:start+32]]
        raw=codec.encode(voices)
        decoded=codec.decode(raw)
        if [v['vced'] for v in decoded]!=voices:raise ValueError('DX7 round-trip changed a recipe')
        filename=f'libraries/FM voices {start+1:03d}-{start+32:03d}.syx'
        (output/filename).write_bytes(raw)
        downloads.append(dict(label=f'FM {start+1}-{start+32} /DX7 voice data only',path=filename))
    manifest=dict(title='FMER Expressions',version=VERSION,collections=profiles,patches=[],downloads=downloads,
        qualification=dict(scope='Shared-core host auditions; owner listening and physical target qualification remain separate.',
            release='Development sound collection; published734-r5 downloads unchanged.',
            license='Original FMER recipes, GPL-3.0-only. No V16 patch data.',
            review='Stored-gain mono renders; no audio loudness normalization. Dry retains tonal filtering.',
            mode='Preset recall preserves playing mode and arrangements through the existing Companion sound-only transfer path.'))
    results={}
    if render:
        (output/'audio').mkdir(exist_ok=True)
        work=ROOT/'artifacts/sound-collections-20261022/renders'
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(render_one,row,entries[row['id']],executable,work,output):row['id'] for row in rows}
            for index,future in enumerate(as_completed(futures),1):
                result=future.result();results[result['id']]=result
                if index%8==0:print(f'Rendered {index}/{len(rows)} instruments',flush=True)
        dump(output/'analysis.json',dict(version=VERSION,executable_sha256=digest(executable),results=list(results.values())))
    for row in rows:
        public={k:v for k,v in row.items() if k not in ('vced','controls','modulation_profiles')}
        public.update(engine=row['id'][:2].upper(),clips=results.get(row['id'],{}).get('clips',[]),metrics=results.get(row['id'],{}).get('metrics',{}))
        manifest['patches'].append(public)
    dump(output/'manifest.json',manifest)
    dump(output/'recipes.json',rows)
    dump(output/'native-instruments.json',entries)
    from sound_collection_review import write_review
    write_review(output,manifest)
    shutil.copyfile(ROOT/'LICENSE',output/'LICENSE.txt')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/sound-collections-20261022/review')
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--workers',type=int,choices=range(1,9),default=4)
    parser.add_argument('--curation',type=Path)
    args=parser.parse_args()
    manifest=build(args.output,sandbox.find_executable('Release'),render=args.render,workers=args.workers,
                   curation=json.loads(args.curation.read_text(encoding='utf8')) if args.curation else None)
    print(json.dumps(dict(instruments=len(manifest['patches']),collections=len(manifest['collections']),review=str(args.output/'index.html'))))


if __name__=='__main__':
    main()
