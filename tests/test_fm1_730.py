import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unittest.mock import patch
import fm1_package as package
import fm1_native_bridge_v24 as bridge
import tempfile
from tests import test_fm1_native_bridge_v14 as mock_device
from tests.test_fm1_native_v10 import Native10Tests

class Song730Tests(unittest.TestCase):
    def test_musical_probe_is_audible_after_owner_highpass_and_glide(self):
        import fm1_730_bench as bench
        state=Native10Tests().state()
        state['controls'][145]=1
        state['controls'][146]=42
        state['controls'][150]=1
        # MIDI/sequence fixtures must define their own filter and voice state,
        # independently of the owner's legitimate sound-design choices.
        probe=bridge.native.decode(bench.pattern_probe(bridge.native.encode(state)))
        self.assertEqual(probe['controls'][145:147],[0,0])
        self.assertEqual(probe['controls'][162],20000)
        self.assertEqual(probe['controls'][150],0)
        self.assertEqual(probe['controls'][191],4)
        self.assertEqual(state['controls'][145:147],[1,42])

    def test_transport_exact_route_and_no_access_on_wrong_origin(self):
        import fm1_flash_transport as updater
        from unittest.mock import Mock
        from tests.test_fm1_flash_transport import qualified_package,RecordJournal,ready_status
        old=qualified_package()
        report=dict(old.report,product='FM-1_730',origin_identity='FM-1_729',loader_identity='ota-FM-1_730',
            origin_app_sha256=package.INSTALLED_729_RELEASE2_APP_SHA256,
            origin_package_sha256=package.INSTALLED_729_RELEASE2_PACKAGE_SHA256,template=package.TEST01_TEMPLATE)
        good=updater.QualifiedPackage(old.image,report,old.app_begin,old.app_end)
        self.assertIn('FM-1_730',updater.SUPPORTED_TARGET_IDS)
        self.assertIn('ota-FM-1_730',updater.SUPPORTED_LOADER_IDS)
        self.assertEqual(updater.update_identities(good),('FM-1_729','ota-FM-1_730','FM-1_730'))
        for resume,expected in ((False,['FM-1_729','ota-FM-1_730','FM-1_730']),(True,['ota-FM-1_730','FM-1_730'])):
            sessions=[Mock() for _ in expected]
            for s in sessions:s.close.return_value=[];s.loader_control.return_value=ready_status(dirty=resume)
            with patch.object(updater,'find_session',side_effect=sessions) as find,patch.object(updater,'serve'):
                updater.perform_update(Mock(),good,RecordJournal(),resume=resume)
            self.assertEqual([call.args[1] for call in find.call_args_list],expected)
        for change in (dict(origin_app_sha256=package.INSTALLED_729_RELEASE1_APP_SHA256),dict(origin_package_sha256=package.INSTALLED_729_RELEASE1_PACKAGE_SHA256),dict(origin_identity='FM-1_728'),dict(loader_identity='ota-FM-1_729')):
            bad=updater.QualifiedPackage(old.image,dict(report,**change),old.app_begin,old.app_end)
            with patch.object(updater,'find_session') as find,self.assertRaises(updater.UpdateError):
                updater.perform_update(Mock(),bad,RecordJournal())
            find.assert_not_called()

    def test_installer_requires_exact_installed729_release2(self):
        digest=bytes.fromhex(package.INSTALLED_729_RELEASE2_APP_SHA256)
        other=bytes.fromhex(package.INSTALLED_729_RELEASE1_APP_SHA256)
        with patch.object(package,'_installed_reference',return_value=b'checked'):
            profile=package.transition_profile(package.SONG_PRODUCT,package.TEST01_TEMPLATE,digest)
            self.assertEqual(profile['origin_identity'],'FM-1_729')
            self.assertEqual(profile['loader_identity'],'ota-FM-1_730')
            self.assertEqual(profile['origin_app_sha256'],digest.hex())
            for bad in (b'',other,digest*2,digest+other):
                with self.assertRaises(ValueError):package.transition_profile(package.SONG_PRODUCT,package.TEST01_TEMPLATE,bad)

    def test_storage_status_declares_whole_song_record(self):
        values=[4,1,0,11,0,0,1,1,128,5,30,0,0,6,0,0,6,4000,3,12,1,16,719]
        frame=lambda: bridge.native.PREFIX+bytes([21])+' '.join(map(str,values)).encode()+bytes([247])
        self.assertEqual(bridge.parse_store_status(frame())['native_bytes'],4000)
        values[17]=3728
        with self.assertRaises(ValueError):bridge.parse_store_status(frame())

    def test_complete_song_crosses_chunked_bridge_and_readback(self):
        n=bridge.native
        with patch.object(mock_device,'native',n),patch.object(mock_device,'fixture',side_effect=Native10Tests().state):
            session=mock_device.Session();session.verified_identity=bridge.IDENTITY
            client=bridge.NativeBridge(session,mock_device.Journal(),sleep=lambda _:None)
            raw,_=client.snapshot();self.assertEqual(n.decode(raw),session.state)
            wanted=n.decode(raw);wanted['song'][3]['entries'][31]['transpose']=24
            with tempfile.TemporaryDirectory() as tmp:
                result=client.restore(n.encode(wanted),Path(tmp),transaction=730)
            self.assertTrue(result['complete_state_verified'])
            self.assertEqual(session.state['song'],wanted['song'])
            self.assertEqual(len(session.received),4000)
            self.assertEqual(session.flash_writes,0)

if __name__=='__main__':unittest.main()
