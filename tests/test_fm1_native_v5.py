"""Sixteen-pattern snapshots and instrument/project projections; no device I/O."""
import copy
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_native_state as v1
import fm1_native_state_v2 as v2
import fm1_native_state_v3 as v3
import fm1_native_state_v4 as v4
import fm1_native_state_v5 as native
from tests.test_fm1_native_v2 import state_fixture as legacy_fixture, v1_fixture
from tests.test_fm1_native_v4 import fixture as v4_fixture


def fixture():
    state=native.decode_compatible(v4.encode(v4_fixture()))
    state['controls'][195]=15;state['controls'][197]=65535
    state['patterns'][15]=dict(length=64,steps=[[129 if i%2 else 128,127-i,100-i] for i in range(64)])
    state['controls'][186:191]=[64,63,*state['patterns'][15]['steps'][63]]
    state['tracks'][0].update(pattern=15,chain_mask=0xa581)
    return state


class NativeV5Tests(unittest.TestCase):
    def test_exact_layout_with_highest_pattern_and_wide_track_masks(self):
        s=fixture();raw=native.encode(s)
        self.assertEqual(len(raw),3728);self.assertEqual(raw[:8],b'FMERNAT5')
        self.assertEqual(raw[3671:3675],b'TRK2');self.assertEqual(raw[3699:],bytes(29))
        self.assertEqual(struct.unpack_from('<BHBBB',raw,3675),(15,0xa581,120,100,0))
        self.assertEqual(native.decode(raw),s)

    def test_strict_ranges_and_track_mirrors(self):
        for key,value in [('pattern',16),('chain_mask',65536),('sound_ref',128),('mute',2)]:
            s=fixture();s['tracks'][0][key]=value
            with self.subTest(key=key),self.assertRaises(native.NativeStateError):native.encode(s)
        for i,value in [(195,16),(197,0),(197,65536),(158,3),(155,7)]:
            s=fixture();s['controls'][i]=value
            with self.subTest(control=i),self.assertRaises(native.NativeStateError):native.encode(s)

    def test_every_new_pattern_and_track_byte_is_checked(self):
        raw=native.encode(fixture())
        for i in range(2127,3728):
            b=bytearray(raw);b[i]^=1
            with self.subTest(byte=i),self.assertRaises(native.NativeStateError):native.decode(b)
        for i in range(3699,3728):
            b=bytearray(raw);b[i]=1;struct.pack_into('<I',b,28,native.record_crc(b))
            with self.assertRaises(native.NativeStateError):native.decode(b)

    def test_historical_files_add_only_empty_upper_patterns_and_preserve_replace_mode(self):
        inputs=[v1.encode(v1_fixture()),v2.encode(legacy_fixture()),v3.upgrade_v2(v2.encode(legacy_fixture())),v4.encode(v4_fixture())]
        for raw in inputs:
            old=v4.decode_compatible(raw);before=bytes(raw);state=native.decode_compatible(raw)
            self.assertEqual(raw,before);self.assertEqual(state['patterns'][:8],old['patterns'])
            self.assertEqual(state['vced'],old['vced']);self.assertEqual(state['tracks'],old['tracks'])
            expected=old['controls'][:];expected[158]=2 if expected[158]==1 else 0
            self.assertEqual(state['controls'],expected)
            self.assertEqual(state['patterns'][8:],[dict(length=16,steps=[[128,100,75] for _ in range(64)]) for _ in range(8)])
        self.assertEqual(native.decode_compatible(inputs[-1])['controls'][158],2)

    def test_new_default_recording_is_overdub_without_reinterpreting_legacy(self):
        s=fixture();native.initialize_tracks(s);self.assertEqual(s['controls'][158],1)
        self.assertEqual(native.decode_compatible(v4.encode(v4_fixture()))['controls'][158],2)

    def test_instrument_projection_preserves_algorithm_glide_envelopes_and_fx(self):
        original=fixture();before=copy.deepcopy(original);result=native.canonical_sound(original)
        self.assertEqual(original,before);self.assertEqual(result['vced'],original['vced'])
        excluded={*range(153,160),*range(186,191),*range(195,198)}
        for i in range(198):
            if i not in excluded:self.assertEqual(result['controls'][i],original['controls'][i])
        self.assertEqual(result['controls'][195:],[0,0,1]);self.assertEqual(len(result['patterns']),16)
        self.assertTrue(all(p['length']==16 and all(step==[128,100,75] for step in p['steps']) for p in result['patterns']))
        self.assertEqual(native.canonical_sound(result),result)

    def test_explicit_sound_load_keeps_project_and_assigns_selected_track(self):
        project=fixture();sound=native.canonical_sound(project);sound['controls'][134]=sound['vced'][134]=31
        sound['controls'][169]=73;sound['controls'][170]=54;sound['controls'][178]=33
        result=native.merge_sound(sound,project,slot=74)
        self.assertEqual(result['patterns'],project['patterns']);self.assertEqual(result['controls'][178],project['controls'][178])
        self.assertEqual(result['controls'][134],31);self.assertEqual(result['controls'][169:171],[73,54])
        self.assertEqual(result['controls'][155],74);self.assertEqual(result['tracks'][result['controls'][154]]['sound_ref'],74)
        for i in range(4):
            if i!=result['controls'][154]:self.assertEqual(result['tracks'][i],project['tracks'][i])

    def test_named_upgraders_refuse_the_wrong_source_version(self):
        raws=[v1.encode(v1_fixture()),v2.encode(legacy_fixture()),v3.upgrade_v2(v2.encode(legacy_fixture())),v4.encode(v4_fixture())]
        for i,upgrade in enumerate((native.upgrade_v1,native.upgrade_v2,native.upgrade_v3,native.upgrade_v4)):
            for j,raw in enumerate(raws):
                if i==j:self.assertEqual(native.decode(upgrade(raw)),native.decode_compatible(raw))
                else:
                    with self.subTest(source=j+1,requested=i+1),self.assertRaises(native.NativeStateError):upgrade(raw)

    def test_c_and_python_migrate_identically(self):
        root=Path(__file__).resolve().parents[1];probe=root/'artifacts/build/host/Release/fm1_native_state_tests.exe'
        if not probe.exists():self.skipTest('Build the current native host codec probe first')
        raws=[v1.encode(v1_fixture()),v2.encode(legacy_fixture()),v3.upgrade_v2(v2.encode(legacy_fixture())),v4.encode(v4_fixture()),native.encode(fixture())]
        with tempfile.TemporaryDirectory() as tmp:
            for i,raw in enumerate(raws):
                src=Path(tmp)/f'{i}.in';out=Path(tmp)/f'{i}.out';src.write_bytes(raw)
                run=subprocess.run([str(probe),'--roundtrip',str(src),str(out)],capture_output=True,text=True,timeout=10)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                import fm1_native_state_v12 as current
                self.assertEqual(out.read_bytes(),current.encode(current.decode_compatible(raw)))
