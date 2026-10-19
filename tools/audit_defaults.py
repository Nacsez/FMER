"""Build a frozen/current bank comparison and publish dry auditions. No device I/O."""
import argparse
from datetime import datetime,timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
import companion_bank as bank
import sandbox

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'artifacts/defaults-709');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    baseline=out/'baseline708/factory_presets.cpp'
    if not baseline.exists():raise ValueError('Frozen708 recipe source is required; never substitute current recipes')
    cmake=shutil.which('cmake') or 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
    source=out/'harness';source.mkdir(exist_ok=True)
    (source/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(FMERDefaultsAudit LANGUAGES CXX)
set(PROJECT_SOURCE_DIR "{ROOT.as_posix()}")
add_subdirectory("{ROOT.as_posix()}/core" core)
add_executable(current "{ROOT.as_posix()}/tests/defaults_audition.cpp")
target_link_libraries(current PRIVATE fmer_core)
add_executable(baseline "{ROOT.as_posix()}/tests/defaults_audition.cpp" "{baseline.as_posix()}")
target_link_libraries(baseline PRIVATE fmer_core)
add_executable(recipe_tests "{ROOT.as_posix()}/tests/factory_presets_tests.cpp")
target_link_libraries(recipe_tests PRIVATE fmer_core)
option(FMER_AUDIT_DEVICE "Run device arithmetic on the host" OFF)
if(FMER_AUDIT_DEVICE)
    foreach(target fmer_core fmer_msfa recipe_tests)
        target_compile_definitions(${{target}} PRIVATE FMER_DEVICE=1)
    endforeach()
endif()
''',encoding='utf-8')
    manifest=dict(started_utc=datetime.now(timezone.utc).isoformat(),profile=bank.PROFILE,hardware_access=False,source_sha256={str(x.relative_to(ROOT)):sha(x) for x in [baseline,ROOT/'core/factory_presets.cpp',ROOT/'tests/defaults_audition.cpp',ROOT/'core/synth.cpp']},steps=[])
    def run(name,argv):
        r=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=120)
        (out/(name+'.log')).write_text(r.stdout+'\n'+r.stderr,encoding='utf-8');manifest['steps'].append(dict(name=name,argv=list(map(str,argv)),returncode=r.returncode))
        (out/'audit.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        if r.returncode:raise RuntimeError(name+' failed; see retained log')
        return r.stdout
    build=out/'build'
    run('configure',[cmake,'-S',source,'-B',build]);run('build',[cmake,'--build',build,'--config','Release','--parallel','2'])
    def executable(name):
        for x in (build/'Release'/(name+'.exe'),build/name):
            if x.exists():return x
        raise ValueError('Build output missing')
    rows={}
    for label in ('baseline','current'):
        dest=out/label;dest.mkdir(exist_ok=True)
        rows[label]=json.loads(run(label,[executable(label),dest]))
    run('recipe-tests',[executable('recipe_tests')])
    device=out/'device-build'
    run('device-configure',[cmake,'-S',source,'-B',device,'-DFMER_AUDIT_DEVICE=ON'])
    run('device-build',[cmake,'--build',device,'--config','Release','--target','recipe_tests','--parallel','2'])
    device_exe=device/'Release/recipe_tests.exe' if (device/'Release/recipe_tests.exe').exists() else device/'recipe_tests'
    run('device-recipe-tests',[device_exe])
    profile=bank.profile(sandbox.find_executable('Release'))
    manifest.update(sounds=64,single_note_cases_per_bank=576,release_checks_per_bank=576,four_voice_chord_cases_current=192,
                    clips=128,peak_current=max(r['peak'] for r in rows['current']),peak_baseline=max(r['peak'] for r in rows['baseline']),results=rows)
    for label in rows:
        for r in rows[label]:r['wav_sha256']=sha(out/label/f'preset-{r["id"]}.wav')
    manifest['finished_utc']=datetime.now(timezone.utc).isoformat();(out/'audit.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    parts=['''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FMER Default listening comparison</title><style>
body{font:15px/1.5 system-ui;background:#070709;color:#f5f7fa;margin:24px;max-width:1300px}h1,a{color:#76ff53}button,input,select{font:inherit;padding:8px;background:#101014;color:#f5f7fa;border:1px solid #727684;border-radius:3px}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #4b4e5a}th,small{color:#c9a0ff}audio{max-width:100%;width:255px}.bar{height:10px;background:#ff78d4;max-width:100%}.old{background:#727684}button.active{background:#76ff53;color:#070709}*:focus-visible{outline:2px solid #ff78d4}@media(max-width:800px){body{margin:10px}td,th{padding:5px}audio{width:150px}td:last-child,th:last-child{display:none}}</style>
<h1>FMER Default 709.1 — listening comparison</h1><p>64 revised instruments, with the frozen708 sound beside each. Every clip uses the same dry score and gain: C4 at velocity100, release, then a four-note chord at velocity110 and release. No normalization or effects. Click one player at a time; the others pause.</p><p>Software renders establish bounded audio and a repeatable comparison. They do not establish analog-output quality or owner preference. Short percussion and slow pads intentionally have different average levels. Bass recipes should also be auditioned below C4 in the companion.</p><p><a href="http://127.0.0.1:8787/">Open companion editor</a> · <a href="audit.json">Detailed measurements / provenance</a></p><label>Engine <select id="engine"><option value="all">FM + VA</option><option value="0">FM</option><option value="1">VA</option></select></label> <input id="search" placeholder="Search name or category" aria-label="Search name or category"><p id="count"></p><table><thead><tr><th>Instrument / role</th><th>708 baseline</th><th>709.1 revision</th><th>RMS comparison<br><small>Gray708 / pink709.1; same linear scale</small></th></tr></thead><tbody>''']
    for new,old,e in zip(rows['current'],rows['baseline'],profile):
        label=html.escape(new['name']+' '+e['category'])
        parts.append(f'<tr data-engine="{new["engine"]}" data-search="{label.lower()}"><td><b>{html.escape(new["name"])}</b><br><small>{e["category"]} · program{new["id"]}</small></td><td><audio controls preload="none" src="baseline/preset-{new["id"]}.wav"></audio></td><td><audio controls preload="none" src="current/preset-{new["id"]}.wav"></audio></td><td><div class="bar old" style="width:{old["rms"]*1000:.1f}%"></div><div class="bar" style="width:{new["rms"]*1000:.1f}%"></div><small>{old["rms"]:.4f} → {new["rms"]:.4f}<br>Peak {new["peak"]:.3f} / 1.000</small></td></tr>')
    parts.append('''</tbody></table><script>function update(){let n=0;const e=document.querySelector('#engine').value,q=document.querySelector('#search').value.toLowerCase();document.querySelectorAll('tr[data-engine]').forEach(r=>{r.hidden=(e!=='all'&&r.dataset.engine!==e)||!r.dataset.search.includes(q);if(!r.hidden)n++;});document.querySelector('#count').textContent=n+' instruments';}document.querySelector('#engine').onchange=update;document.querySelector('#search').oninput=update;document.querySelectorAll('audio').forEach(a=>a.onplay=()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause();}));update();</script></html>''')
    (out/'index.html').write_text('\n'.join(parts),encoding='utf-8');print(json.dumps({k:manifest[k] for k in ('sounds','clips','peak_current','peak_baseline','hardware_access')}))
if __name__=='__main__':main()
