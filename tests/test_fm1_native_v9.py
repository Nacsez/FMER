import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unittest,itertools,tempfile,json
import fm1_native_state_v9 as native
import companion_bank
import fm1_native_state_v10 as current

class Native9Tests(unittest.TestCase):
    def test_runtime_allocation_is_explicit_and_archives_stay_lossless(self):
        from tests.test_companion import fixture
        from fm1_native_bridge_v22 import NativeBridge
        from tests.test_fm1_native_bridge_v14 import Journal
        from copy import deepcopy
        source=current._legacy(companion_bank.native.v11._legacy(companion_bank.native._legacy(companion_bank.decode_record(fixture()['native']))))
        source['controls'][150]=2;source['controls'][191]=3
        raw=native.encode(source);effective=native.runtime_state(source)
        self.assertEqual(effective['controls'][191],1)
        self.assertEqual(native.decode(raw),source)
        bridge=object.__new__(NativeBridge);bridge.journal=Journal()
        actual=native.encode(effective)
        self.assertTrue(bridge._verify_state(raw,actual,'load',runtime=True)['complete_state_verified'])
        self.assertEqual(bridge.journal.events[0]['before'],3)
        with self.assertRaises(RuntimeError):bridge._verify_state(raw,actual,'archive')
        # Neither wrong allocation nor another damaged field may be hidden.
        for control,value in ((191,2),(162,1234)):
            damaged=deepcopy(effective);damaged['controls'][control]=value
            with self.assertRaises(RuntimeError):bridge._verify_state(raw,native.encode(damaged),'load',runtime=True)
        source['controls'][153]=1
        self.assertEqual(native.runtime_state(source)['controls'][191],4)
        source['controls'][153]=source['controls'][150]=0
        self.assertEqual(native.runtime_state(source)['controls'][191],3)

    def test_all_permutations(self):
        for rank,order in enumerate(itertools.permutations(range(6))):
            self.assertEqual(native.effect_order(rank),list(order))
            self.assertEqual(native.effect_rank(list(order)),rank)
        for bad in (-1,720,True):
            with self.assertRaises(ValueError):native.effect_order(bad)
        with self.assertRaises(ValueError):native.effect_rank([0]*6)

    def test_legacy_and_fx_profiles(self):
        # Use deterministic profile fixture through the current public factory
        # provider; no library file or device access.
        from tests import test_companion as fixtures
        state=current._legacy(companion_bank.native.v11._legacy(companion_bank.native._legacy(companion_bank.decode_record(fixtures.fixture()['native']))))
        state['fx_order']=719
        raw=native.encode(state)
        self.assertEqual(len(raw),3728)
        self.assertEqual(native.decode(raw),state)
        older=native.v8.encode(native._legacy(state))
        self.assertEqual(native.decode_compatible(older)['fx_order'],0)
        profile=companion_bank.export_fx(companion_bank.native.decode_compatible(native.encode(state)))
        state['fx_order']=0
        self.assertEqual(companion_bank.import_fx(companion_bank.native.decode_compatible(native.encode(state)),profile)['fx_order'],719)
        with tempfile.TemporaryDirectory() as folder:
            record=native.save_backup(raw,Path(folder),device_identity='FM-1_728')
            self.assertEqual(Path(record['path']).read_bytes(),raw)

if __name__=='__main__':unittest.main()

