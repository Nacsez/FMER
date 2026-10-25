# SPDX-License-Identifier: GPL-3.0-only
"""Behavioral checks for original sound exports; never open hardware."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import companion_bank as bank
import companion_shelf as shelf
import library
import sandbox
import sound_collections as sounds


class SoundCollections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=sounds.recipes()
        try:
            cls.exe=sandbox.find_executable('Release')
        except ValueError as error:
            raise unittest.SkipTest('Build Release host for complete sound-export checks') from error
        cls.template=bank.decode_record(bank.profile(cls.exe)[0]['native'])
        cls.entries={r['id']:sounds.make_entry(r,cls.template) for r in cls.rows}

    def test_catalog_coverage_and_balanced_default(self):
        profiles=sounds.collections(self.rows)
        self.assertEqual([len(p['patch_ids']) for p in profiles],[64]*4)
        self.assertEqual(len(set.union(*(set(p['patch_ids']) for p in profiles))),192)
        self.assertEqual(sum(x.startswith('fm_') for x in profiles[0]['patch_ids']),36)
        lookup={r['id']:r for r in self.rows}
        self.assertEqual(sum(lookup[x]['group']=='percussion' for x in profiles[1]['patch_ids']),48)

    def test_included_profiles_group_like_sounds_without_losing_favorites(self):
        profiles=sounds.collections(self.rows);lookup={r['id']:r for r in self.rows}
        for profile in profiles:
            categories=[lookup[k]['category'] for k in profile['patch_ids']]
            blocks=[c for i,c in enumerate(categories) if i==0 or c!=categories[i-1]]
            self.assertEqual(len(blocks),len(set(blocks)),profile['id'])
        selection=json.loads((sounds.ROOT/'tools/sound_collection_selection.json').read_text())
        self.assertTrue(set(selection['favorite_ids']).issubset(profiles[0]['patch_ids']))
        included=json.loads((sounds.ROOT/'host/loadout_profiles.json').read_text())
        self.assertEqual([p['sound_ids'] for p in included['profiles']],[p['patch_ids'] for p in profiles])

    def test_every_native_voice_roundtrips_without_patterns_or_mode_changes(self):
        original=copy.deepcopy(self.template)
        fingerprints=set()
        for row in self.rows:
            state=bank.decode_record(self.entries[row['id']]['native'])
            self.assertEqual(bank.native.decode(bank.native.encode(state)),state)
            self.assertEqual(state['controls'][:145],state['vced'][:145])
            self.assertEqual(state['controls'][191],6)
            self.assertEqual(state['controls'][153],0)
            self.assertTrue(all(step[0]==128 for p in state['patterns'] for step in p['steps']))
            self.assertEqual(state['vced'][145:],list(row['name'].ljust(10).encode('ascii')))
            state['vced'][145:]=[32]*10
            fingerprints.add(bank.native.encode(state))
        self.assertEqual(len(fingerprints),192)
        self.assertEqual(self.template,original)

    def test_original_fm_uses_broad_valid_routings(self):
        voices=[bank.decode_record(v['native'])['vced'] for key,v in self.entries.items() if key.startswith('fm_')]
        self.assertGreaterEqual(len({v[134] for v in voices}),20)
        library.PatchCodec(self.exe,lambda *_a,**_k:None).validate(voices)

    def test_catalog_import_is_one_undo_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=shelf.Catalog(Path(root),self.exe)
            seed=sounds.catalog(self.rows[:1],self.entries,'Existing test instrument')
            state=catalog.dispatch(dict(action='import',revision=0,backup=seed))
            before=copy.deepcopy(state['slots'])
            imported=catalog.dispatch(dict(action='import',revision=state['revision'],backup=sounds.catalog(self.rows,self.entries,sounds.VERSION)))
            self.assertEqual(len(imported['slots']),193)
            self.assertEqual(imported['slots'][:1],before)
            restored=catalog.dispatch(dict(action='undo',revision=imported['revision']))
            self.assertEqual(restored['slots'],before)

    def test_bad_curation_is_atomic_and_valid_slot_replacement_works(self):
        profiles=sounds.collections(self.rows)
        original=copy.deepcopy(profiles)
        c=dict(format='FMER-SOUND-CURATION',schema=1,library_version=sounds.VERSION,
               collections={p['id']:list(p['patch_ids']) for p in profiles})
        c['collections']['A'][0]='unknown'
        with self.assertRaises(ValueError):sounds.apply_curation(profiles,self.rows,c)
        self.assertEqual(profiles,original)
        c['collections']['A'][0]=self.rows[-1]['id']
        changed=sounds.apply_curation(profiles,self.rows,c)
        self.assertEqual(changed[0]['patch_ids'][0],self.rows[-1]['id'])
        self.assertEqual(profiles,original)

    def test_recipe_cannot_smuggle_transport_or_project_state(self):
        for forbidden in (153,154,155,178,179,186,191,195,197):
            row=copy.deepcopy(self.rows[0]);row.setdefault('controls',{})[forbidden]=1
            with self.assertRaises(ValueError):sounds.make_entry(row,self.template)


if __name__=='__main__':unittest.main()
