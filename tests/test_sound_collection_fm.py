"""Original FM collection contracts; no device or persistent library access."""
import copy
from collections import Counter
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import sound_collection_fm as sounds
import companion_bank
import library


class SoundCollectionFmTests(unittest.TestCase):
    def test_catalog_has_distinct_musical_programs_and_printable_device_names(self):
        voices = sounds.recipes()
        self.assertEqual(len(voices), 128)
        self.assertEqual(len({tuple(p['vced'][:145]) for p in voices}), 128)
        self.assertEqual(len({p['id'] for p in voices}), 128)
        self.assertEqual(Counter(p['group'] for p in voices),
                         dict(percussion=32,bass=16,keys=16,winds=16,leads=16,pads=16,textures=16))
        for p in voices:
            with self.subTest(patch=p['name']):
                self.assertEqual(len(p['vced']), 155)
                self.assertEqual(bytes(p['vced'][145:]).decode('ascii').rstrip(), p['name'])
                self.assertTrue(1 <= len(p['name']) <= 10)
                self.assertIn(p['category'], companion_bank.CATEGORIES)
                self.assertTrue(all(32 <= ord(c) <= 126 for c in p['name']))
                self.assertTrue(0 <= p['audition_note'] <= 127)

    def test_callers_can_edit_a_recipe_without_mutating_next_collection(self):
        first = sounds.recipes()
        before = copy.deepcopy(first)
        first[0]['vced'][16] = 0
        first[0]['controls'][162] = 20
        first[0]['tags'].append('edited')
        self.assertEqual(sounds.recipes(), before)

    def test_carriers_match_actual_pinned_renderer_routing(self):
        source = (ROOT/'third_party/msfa/src/fm_core.cc').read_text()
        rows = re.findall(r'\{ \{ ((?:0x[0-9a-f]+,? ?){6}) \} \}',source)
        self.assertEqual(len(rows),32)
        actual = tuple(sum(1 << i for i,v in enumerate(re.findall(r'0x[0-9a-f]+',row))
                           if int(v,16) & 7 == 4) for row in rows)
        self.assertEqual(sounds.CARRIERS,actual)

    def test_sound_overrides_never_switch_playing_modes_or_patterns(self):
        allowed = {145,146,147,148,149,159,162,168,169,170,171,172,173,174,194}
        for p in sounds.recipes():
            self.assertLessEqual(set(p['controls']),allowed)
            self.assertEqual(len(p['modulation_profiles']),2)
            self.assertTrue(all(0 <= x <= 3 for x in p['modulation_profiles']))

    def test_feedback_avoids_unimplemented_multi_operator_loops(self):
        for p in sounds.recipes():
            if p['vced'][135]:
                self.assertNotIn(p['vced'][134],(3,5))

    def test_every_patch_releases_and_has_an_audible_carrier(self):
        for p in sounds.recipes():
            carriers=[i for i in range(6) if sounds.CARRIERS[p['vced'][134]] & (1 << i)]
            self.assertTrue(any(p['vced'][21*i+16] > 0 for i in carriers))
            self.assertTrue(all(p['vced'][21*i+7] == 0 for i in range(6)))

    def test_compiled_codec_and_native_sound_roundtrip(self):
        exe=ROOT/'artifacts/build/host/host/Release/fmer_host.exe'
        if not exe.is_file():
            self.skipTest('Build the Release host to run canonical codec integration')
        codec=library.PatchCodec(exe,lambda *args,**kwargs:None)
        voices=sounds.recipes()
        codec.validate([p['vced'] for p in voices])
        for start in range(0,128,32):
            vced=[p['vced'] for p in voices[start:start+32]]
            self.assertEqual([p['vced'] for p in codec.decode(codec.encode(vced))],vced)
        template=companion_bank.decode_record(companion_bank.profile(exe)[0]['native'])
        for p in voices:
            state=copy.deepcopy(template)
            state['vced']=p['vced'][:]
            state['controls'][:145]=p['vced'][:145]
            for k,v in p['controls'].items():state['controls'][k]=v
            state['modulation_profiles']=p['modulation_profiles'][:]
            entry=dict(name=p['name'],category=p['category'],favorite=False,
                       audition_note=p['audition_note'],native=companion_bank.pack(state))
            companion_bank.BankLibrary.validate_entry(entry)
            self.assertEqual(companion_bank.decode_record(entry['native'])['vced'],p['vced'])


if __name__=='__main__':unittest.main()
