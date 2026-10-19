"""722 sync/FX persistence, strict historical migration and sound projection."""
import copy
import unittest
from tests.test_fm1_native_v6 import fixture as previous_fixture
import fm1_native_state_v6 as previous
import fm1_native_state_v7 as native

def fixture():return native.decode_compatible(previous.encode(previous_fixture()))

class NativeV7Tests(unittest.TestCase):
    def test_old_song_migrates_without_changing_any_musical_value(self):
        old=previous_fixture();raw=previous.encode(old);new=native.decode_compatible(raw)
        for key in ('controls','patterns','tracks','vced','preset_id','source_generation'):
            self.assertEqual(new[key],old[key])
        self.assertEqual(len(native.encode(new)),len(raw))
        self.assertEqual(previous.encode(old),raw)

    def test_sync_and_all_models_roundtrip_and_belong_to_sound(self):
        for model in range(4):
            for division in range(8):
                s=fixture();s['controls'][148]=model;s['controls'][159]=division
                s['controls'][171]=327
                self.assertEqual(native.decode(native.encode(s)),s)
                sound=native.canonical_sound(s)
                self.assertEqual(sound['controls'][159],division)
                merged=native.merge_sound(sound,fixture())
                self.assertEqual(merged['controls'][159],division)
                self.assertEqual(merged['controls'][171],327)

    def test_old_reader_refuses_new_format_and_bounds_stay_strict(self):
        s=fixture();s['controls'][159]=7;s['controls'][148]=3
        with self.assertRaises(previous.NativeStateError):previous.decode(native.encode(s))
        for identifier,value in ((148,4),(159,8),(159,-1)):
            bad=copy.deepcopy(s);bad['controls'][identifier]=value
            with self.assertRaises(native.NativeStateError):native.encode(bad)

class BatteryHistoryTests(unittest.TestCase):
    def test_download_and_reject_inconsistent_or_invalid_history(self):
        import fm1_native_bridge_v16 as bridge
        class Journal:
            def record(self,*args,**kwargs):pass
        def run(rows):
            b=object.__new__(bridge.NativeBridge);b.journal=Journal();packets=iter(rows)
            b.request=lambda *args:native.PREFIX+bytes([32])+' '.join(map(str,next(packets))).encode()+bytes([247])
            return b.battery_history()
        result=run([[1,5,5,0,4]+[60,633,632,1]*4,[1,5,5,4,1,300,610,611,0]])
        self.assertEqual(len(result['retained_samples']),5)
        self.assertEqual(result['retained_samples'][-1]['raw_adc'],610)
        with self.assertRaises(RuntimeError):run([[1,5,5,0,4]+[60,633,632,1]*4,[1,6,6,4,2]+[300,610,611,0]*2])
        with self.assertRaises(ValueError):run([[1,1,1,0,1,60,1024,600,1]])
        self.assertEqual(run([[1,0,0,0,0]])['retained_samples'],[])

class Exact722TransitionTests(unittest.TestCase):
    def test_only_unique_pinned_origins_are_admitted(self):
        import fm1_package as pkg
        from unittest.mock import patch
        old=pkg.INSTALLED_721_APP_SHA256;current=pkg.INSTALLED_722_RELEASE1_APP_SHA256
        with patch.object(pkg,'_installed_reference',return_value=b'checked'):
            for digest,identity in ((old,'FM-1_721'),(current,'FM-1_722')):
                r=pkg.transition_profile(pkg.SYNC_PRODUCT,pkg.TEST01_TEMPLATE,b'loader'+bytes.fromhex(digest))
                self.assertEqual(r['origin_identity'],identity)
                self.assertEqual(r['origin_app_sha256'],digest)
            for raw in (b'unknown',bytes.fromhex(old)*2,bytes.fromhex(old+current)):
                with self.assertRaises(ValueError):pkg.transition_profile(pkg.SYNC_PRODUCT,pkg.TEST01_TEMPLATE,raw)

class SoundUploadContextTests(unittest.TestCase):
    def test_upload_preserves_stored_sound_and_live_project_tempos_independently(self):
        import fm1_native_bridge_v16 as bridge
        from unittest.mock import Mock
        class Fake(bridge.NativeBridge):
            def __init__(self):
                self.live=fixture();self.live['controls'][178]=111;self.live['controls'][191]=4
                self.live['source_generation']=1;self.journal=Mock();self.imports=0;self.conflict=False
            def _backup_slot(self,*args):return {'backup':{'path':'isolated'}}
            def _guard_slot(self,*args):return {}
            def snapshot(self):return native.encode(self.live),{}
            def status(self):return {'live_generation':self.live['source_generation']}
            def restore(self,raw,*args,expected_generation=None,**kwargs):
                assert self.live['source_generation']==expected_generation
                generation=self.live['source_generation']+1;self.live=native.decode(raw);self.live['source_generation']=generation;self.imports+=1
                return {'verified_generation':generation,'pre_restore_backup':{'path':'isolated'}}
            def _storage_action(self,*args):
                self.stored=native.encode(native.canonical_sound(self.live));self.live['source_generation']+=1;return {}
            def read_slot(self,*args):
                if self.conflict:self.live['controls'][162]=1234
                return self.stored,{}
        sound=native.canonical_sound(fixture());sound['controls'][178]=120;sound['controls'][191]=2
        sound['controls'][159]=3;sound['controls'][148]=3;raw=native.encode(sound)
        b=Fake();before=copy.deepcopy(b.live);result=b.push_slot(raw,63,None)
        self.assertTrue(result['complete_instrument_verified']);self.assertEqual(b.imports,2)
        stored=native.decode(b.stored)
        self.assertEqual((stored['controls'][178],stored['controls'][191]),(120,2))
        self.assertEqual((b.live['controls'][178],b.live['controls'][191]),(111,4))
        self.assertEqual(b.live['patterns'],before['patterns'])
        self.assertEqual(b.live['controls'][159],3)
        b=Fake();b.conflict=True
        with self.assertRaises(RuntimeError):b.push_slot(raw,63,None)
        self.assertEqual(b.imports,1);self.assertEqual(b.live['controls'][162],1234)
