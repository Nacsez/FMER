"""Six-voice wire/storage and the reviewed Spectrum catalog agree across C/Python."""
import base64
import copy
import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from tests.test_companion import fixture
import companion_bank as bank
import fm1_native_state_v12 as native
import build_spectrum_defaults

ROOT=Path(__file__).resolve().parents[1]

class Native12Tests(unittest.TestCase):
    def test_six_voices_roundtrip_and_legacy_limits(self):
        state=bank.decode_record(fixture()['native'])
        for budget in range(1,7):
            state['controls'][191]=budget
            raw=native.encode(state)
            self.assertEqual(native.decode(raw),state)
            self.assertEqual(native.v11.decode(native.legacy_wire(raw))['controls'][191],min(budget,4))
            with tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'in';source.write_bytes(raw)
                for tool,command in [('fm1_native_state_tests','--roundtrip'),('fm1_bank_store_tests','--migrate')]:
                    exe=ROOT/'artifacts/build/host/Release'/(tool+'.exe')
                    self.assertTrue(exe.exists(),'Build native probes first')
                    out=Path(tmp)/'out'
                    result=subprocess.run([str(exe),command,str(source),str(out)],capture_output=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertEqual(out.read_bytes(),raw)
        invalid=bytearray(raw);struct.pack_into('<H',invalid,414,7)
        struct.pack_into('<I',invalid,28,native.record_crc(invalid))
        with self.assertRaises(ValueError):native.decode(invalid)
        # Merely changing a legacy header must never admit six voices there.
        invalid=bytearray(raw);invalid[:8]=native.v11.MAGIC;struct.pack_into('<H',invalid,8,11)
        struct.pack_into('<I',invalid,28,native.record_crc(invalid))
        with self.assertRaises(ValueError):native.v11.decode(invalid)

    def test_sound_recall_preserves_all_modes(self):
        sound=bank.decode_record(fixture()['native'])
        for budget in range(1,7):
            state=copy.deepcopy(sound);state['controls'][191]=budget
            self.assertEqual(native.merge_sound(sound,state)['controls'][191],budget)
        state['controls'][153]=1
        self.assertEqual(native.runtime_state(state)['controls'][191],4)
        state['controls'][153]=0;state['controls'][150]=1
        self.assertEqual(native.runtime_state(state)['controls'][191],1)

    def test_spectrum_contains_every_favorite_and_matches_compiled_defaults(self):
        selection=json.loads((ROOT/'tools/sound_collection_selection.json').read_text())
        loadouts=json.loads((ROOT/'host/loadout_profiles.json').read_text())
        spectrum=next(p for p in loadouts['profiles'] if p['id']=='A')['sound_ids']
        self.assertEqual(len(set(spectrum)),64)
        self.assertTrue(set(selection['favorite_ids']).issubset(spectrum))
        self.assertEqual((ROOT/'firmware/fm1/spectrum_defaults.hpp').read_text(),build_spectrum_defaults.build())
        entries=bank.profile(None)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'defaults.bin'
            exe=ROOT/'artifacts/build/host/Release/fm1_bank_store_tests.exe'
            result=subprocess.run([str(exe),str(out)],capture_output=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            raw=out.read_bytes();self.assertEqual(len(raw),64*4000)
            for i,entry in enumerate(entries):
                actual=native.canonical_sound(native.decode(raw[i*4000:(i+1)*4000]))
                expected=native.canonical_sound(bank.decode_record(entry['native']))
                self.assertEqual(actual,expected,f'Spectrum slot {i}: {entry["name"]}')

if __name__=='__main__':unittest.main()
