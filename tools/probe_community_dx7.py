# SPDX-License-Identifier: GPL-3.0-only
"""Offline interoperability probe of reviewed community codecs and FMER.

Only the three hash-pinned, inspected pure FM6 codec excerpts may run. No web
page, installer, factory bank, MIDI API or acquired build script is executed.
Node is a research prerequisite, not a new Companion runtime dependency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

import companion_bank as bank
import companion_dx7 as dx7
import library

REVIEWED = {
    '9746fa24ebc0db8e90951d230403a2c34f3ee55480d892150b58fa3cbac2927b': 'Felucca 1.6.1',
    '442e608255e039e31957b8beea0c36d151c04aac0de61c778f5e06c40c2c47fe': 'SLOOP 2.7.1',
    'a571e989d9c3fc203ef33bfecc1523f155aa9c6e2ffdd2458b4d944379026216': 'JIANT source e9692d7',
}
JS = r"""
const fs = require('node:fs'), vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = vm.createContext({input});
const script = input.code + `
JSON.stringify({
 singles: input.voices.map((v,i) => Array.from(FM6.singleSysex(v, i % 16))),
 banks: [0,32].map(i => Array.from(FM6.bankSysex(input.voices.slice(i,i+32)))),
 decoded: input.fmer.map(raw => {
   const r=FM6.parseSysex(raw);
   return {voices:r.voices.map(x=>Array.from(x.v)),badSum:r.badSum,short:r.short,skipped:r.skipped};
 })
});`;
process.stdout.write(new vm.Script(script).runInContext(context,{timeout:5000}));
"""


def excerpt(raw):
    sha = hashlib.sha256(raw).hexdigest()
    if sha not in REVIEWED: raise ValueError('Unreviewed community codec; no code executed')
    source = raw.decode('utf8')
    start = source.index('const FM6 = (() => {')
    end = source.index('  const ALG =', start)
    code = source[start:end]
    if re.search(r'\b(require|process|fetch|eval|Function|constructor|import|document|window)\b', code):
        raise ValueError('Unexpected operation in reviewed excerpt')
    return code + '\n return {singleSysex,bankSysex,parseSysex}; })();', sha


def template():
    c = [bank.native.control_bounds(i)[0] for i in range(198)]
    c[178] = 120; c[186:191] = [16, 0, 128, 100, 75]; c[191] = 4
    state = dict(schema=bank.native.SCHEMA, version=bank.native.VERSION,
                 source_generation=0, preset_id=65535, controls=c,
                 vced=c[:145] + list(b'RESEARCH  '),
                 patterns=[dict(length=16, steps=[[128,100,75] for _ in range(64)]) for _ in range(16)])
    bank.native.initialize_tracks(state)
    return state


def probe(editor, host, node='node'):
    code, sha = excerpt(editor.read_bytes())
    rng = random.Random(734)
    voices=[]
    for n in range(64):
        v=[]
        for i in range(145):
            lo,hi=bank.native.control_bounds(i)
            v.append(lo if n == 0 else hi if n == 1 else rng.randint(lo,hi))
        v[134]=n%32
        v += list(f'PROBE {n:04d}'.encode('ascii'))
        voices.append(v)
    codec=library.PatchCodec(host,lambda *a,**k:None)
    fmer=[list(codec.encode([v])) for v in voices]
    fmer += [list(codec.encode(voices[i:i+32])) for i in (0,32)]
    request=dict(code=code,voices=voices,fmer=fmer)
    result=subprocess.run([node,'-e',JS],input=json.dumps(request),capture_output=True,text=True,timeout=30)
    if result.returncode:raise RuntimeError(result.stderr)
    other=json.loads(result.stdout)
    expected=[[v] for v in voices]+[voices[:32],voices[32:]]
    for actual,want in zip(other['decoded'],expected,strict=True):
        if actual['voices']!=want or any(actual[k] for k in ('badSum','short','skipped')):
            raise ValueError('Community decoder differs from original FMER voice data')
    for raw,want in zip(other['singles']+other['banks'],expected,strict=True):
        decoded=dx7.decode(bytes(raw),template(),codec)
        actual=[bank.decode_record(e['native'])['vced'] for e in decoded['entries']]
        if actual!=want:raise ValueError('Companion import differs from community voice data')
    corrupted=bytearray(other['singles'][2]);corrupted[-2]^=1
    try:dx7.decode(bytes(corrupted),template(),codec)
    except ValueError:pass
    else:raise ValueError('Companion accepted a corrupt checksum')
    return dict(passed=True,community=REVIEWED[sha],source_sha256=sha,
                excerpt_sha256=hashlib.sha256(code.encode()).hexdigest(),
                host_sha256=hashlib.sha256(host.read_bytes()).hexdigest(),
                synthetic_voices=64,algorithms=32,single_voice_channels=16,
                files_each_direction=66,companion_native_import=True,
                corrupt_checksum_rejected=True,hardware_access=False,
                audio_equivalence_tested=False,factory_patches_copied=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editor',type=Path,required=True)
    parser.add_argument('--host',type=Path,required=True)
    parser.add_argument('--node',default='node')
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();result=probe(a.editor,a.host,a.node)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result))


if __name__=='__main__':main()
