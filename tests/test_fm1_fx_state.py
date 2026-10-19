"""Strict migration and declarative FX profiles; no device I/O."""
import copy
import struct
import unittest
from tests.test_fm1_native_v2 import state_fixture
from tools import fm1_native_state_v2 as old
from tools import fm1_native_state_v3 as native
from tools import companion_bank as bank

class FxStateTests(unittest.TestCase):
    def test_legacy_upgrade_preserves_every_original_value(self):
        source=state_fixture();raw=old.encode(source)
        result=native.decode(native.upgrade_v2(raw))
        expected=copy.deepcopy(source);expected.update(schema=native.SCHEMA,version=3)
        expected['controls'][147]=1
        self.assertEqual(result,expected)
        self.assertEqual(raw,old.encode(source))
        self.assertEqual(native.decode_compatible(raw),expected)
        bad=bytearray(raw);struct.pack_into('<H',bad,32+145*2,1)
        struct.pack_into('<I',bad,28,old.record_crc(bad))
        with self.assertRaises(ValueError):native.upgrade_v2(bad)

    def test_new_fields_roundtrip_and_reserved_remain_rejected(self):
        state=native.decode(native.upgrade_v2(old.encode(state_fixture())))
        state['controls'][145:150]=[2,100,0,1,1]
        self.assertEqual(native.decode(native.encode(state)),state)
        with self.assertRaises(ValueError):old.decode(native.encode(state))
        for i in range(145,160):
            bad=copy.deepcopy(state);bad['controls'][i]=native.control_bounds(i)[1]+1
            with self.subTest(i=i),self.assertRaises(ValueError):native.encode(bad)

    def test_profile_changes_only_fx_and_is_atomic(self):
        # The app's working-state contract is v4; import validates/migrates old
        # wire records before exposing the FX editor. Historical v3 tests above
        # intentionally keep their frozen codec and reserved-field rules.
        state=bank.native.decode_compatible(old.encode(state_fixture()))
        profile=bank.export_fx(state);profile['controls'].update({'145':1,'146':83,'147':0,'148':1,'149':1,'173':60})
        changed=bank.import_fx(state,profile)
        self.assertEqual(changed['patterns'],state['patterns'])
        self.assertEqual(changed['vced'],state['vced'])
        for i in range(198):
            if i not in bank.FX_IDS:self.assertEqual(changed['controls'][i],state['controls'][i])
        self.assertEqual(changed['controls'][146],83)
        self.assertEqual(state['controls'][146],0)
        for bad in (dict(profile,dsp='untrusted'),dict(profile,code='run'),dict(profile,version=True)):
            with self.assertRaises(ValueError):bank.import_fx(state,bad)
        profile['controls']['146']=101
        with self.assertRaises(ValueError):bank.import_fx(state,profile)

if __name__=='__main__':unittest.main()
