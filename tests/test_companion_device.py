"""Device boundary tests use fakes only; never open Windows MIDI."""
import base64
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import companion_device as device
from tests.test_fm1_native_v8 import fixture as old_fixture
import fm1_native_state_v8 as old_native
def fixture():return device.bridge.native.decode_compatible(old_native.encode(old_fixture()))

class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.service=device.Device(Path('unused'),self.root/'library')
        self.pin=patch.object(device,'ROOT',self.root);self.pin.start();self.addCleanup(self.pin.stop)

    def test_stock_probe_is_connected_without_native_commands(self):
        session=Mock();session.verified_identity='FM-1_015';session.close.return_value=[]
        with patch.object(device.hardware_bridge,'WinMM'),patch.object(device.bridge.transport,'find_session',return_value=session),patch.object(device.bridge,'NativeBridge') as native:
            result=self.service.dispatch({'action':'probe'})
            self.assertTrue(result['success']);self.assertFalse(result['can_manage'])
            self.assertEqual(result['identity'],'FM-1_015');native.assert_not_called()
            with self.assertRaisesRegex(ValueError,'Install FMER'):
                self.service.dispatch({'action':'backup_all'})
            native.assert_not_called()

    def test_previous_native11_device_still_backed_up_before_upgrade(self):
        session=Mock();session.verified_identity='FM-1_733';session.close.return_value=[]
        client=Mock();client.list_slots.return_value={'slots':[]}
        with patch.object(device.hardware_bridge,'WinMM'),patch.object(device.bridge.transport,'find_session',return_value=session),patch.dict(device.LEGACY_CLIENTS,{'FM-1_733':Mock(return_value=client)}) as old,patch.object(device.bridge,'NativeBridge') as latest:
            self.assertTrue(self.service.dispatch({'action':'probe'})['can_manage'])
            self.service.dispatch({'action':'catalog'})
            old['FM-1_733'].assert_called_once_with(session,unittest.mock.ANY)
            latest.assert_not_called();client.list_slots.assert_called_once()
            self.assertEqual(self.service.record_identity,'FM-1_733')

    def test_invalid_or_unconfirmed_input_cannot_open_device(self):
        raw=base64.b64encode(device.bridge.native.encode(fixture())).decode()
        with patch.object(device.hardware_bridge,'WinMM') as api:
            for request in ({'action':'erase'}, {'action':'pull','slot':128}, {'action':'push','slot':0,'raw':raw},
                {'action':'push','slot':0,'raw':raw,'confirmation':'Replace device slot 1'},
                {'action':'reset_user','confirmation':'Clear User Bank'}, {'action':'clear_user'},
                {'action':'catalog','unsafe':True}):
                with self.subTest(request=request),self.assertRaises(ValueError):self.service.dispatch(request)
            api.assert_not_called()

    def test_catalog_and_pull_never_mutate_ram_or_flash(self):
        wire=device.bridge.native.encode(fixture());path=self.root/'saved.fmer-native';path.write_bytes(wire)
        session=Mock();session.verified_identity=device.bridge.IDENTITY;session.close.return_value=[];client=Mock()
        client.list_slots.return_value=dict(slots=[],status=dict(generation=4))
        client.export_slot.return_value=dict(backup=dict(path=str(path)))
        with patch.object(device.hardware_bridge,'WinMM'),patch.object(device.bridge.transport,'find_session',return_value=session),patch.object(device.bridge,'NativeBridge',return_value=client):
            result=self.service.dispatch(dict(action='pull',slot=127))
            self.assertEqual(base64.b64decode(result['raw']),wire)
            client.push_slot.assert_not_called();client.restore.assert_not_called();client.reset_bank.assert_not_called()
            session.close.assert_called_once();self.assertTrue((Path(result['artifacts'])/'report.json').is_file())

    def test_failed_transfer_closes_session_and_retains_failure_report(self):
        wire=base64.b64encode(device.bridge.native.encode(fixture())).decode();session=Mock();session.verified_identity=device.bridge.IDENTITY;session.close.return_value=[]
        client=Mock();client.push_slot.side_effect=RuntimeError('ambiguous commit; no retry')
        with patch.object(device.hardware_bridge,'WinMM'),patch.object(device.bridge.transport,'find_session',return_value=session),patch.object(device.bridge,'NativeBridge',return_value=client):
            with self.assertRaisesRegex(RuntimeError,'ambiguous'):self.service.dispatch(dict(action='push',slot=127,raw=wire,confirmation='Replace device slot 127'))
        session.close.assert_called_once();client.push_slot.assert_called_once()
        reports=list((self.root/'library/device-logs').glob('*/report.json'));self.assertEqual(len(reports),1)
        self.assertIn('ambiguous commit',reports[0].read_text());self.assertFalse((self.root/'library/device-access/library.lock').exists())

    def test_stop_recording_does_not_open_midi(self):
        with patch.object(device.hardware_bridge,'WinMM') as api:
            self.assertFalse(self.service.dispatch(dict(action='stop_recording'))['recording']);api.assert_not_called()

    def test_legacy_slot_push_is_upgraded_without_modifying_original_record(self):
        import fm1_native_state_v2 as v2
        from tests.test_fm1_native_v2 import state_fixture
        wire=v2.encode(state_fixture());encoded=base64.b64encode(wire).decode()
        session=Mock();session.verified_identity=device.bridge.IDENTITY;session.close.return_value=[];client=Mock();client.push_slot.return_value={}
        with patch.object(device.hardware_bridge,'WinMM'),patch.object(device.bridge.transport,'find_session',return_value=session),patch.object(device.bridge,'NativeBridge',return_value=client):
            self.service.dispatch(dict(action='push',slot=64,raw=encoded,confirmation='Replace device slot 64'))
        converted=client.push_slot.call_args.args[0]
        self.assertEqual(converted[:8],b'FMERNATC')
        self.assertEqual(device.bridge.native.decode(converted),device.bridge.native.decode_compatible(wire))
        self.assertEqual(base64.b64decode(encoded),wire);session.close.assert_called_once()

    def test_project_destinations_and_confirmations_checked_before_open(self):
        raw=base64.b64encode(device.bridge.native.encode(fixture())).decode()
        with patch.object(device.hardware_bridge,'WinMM') as api:
            for req in ({'action':'project_pull','slot':16},{'action':'project_save','slot':0},
                        {'action':'project_push','slot':15,'raw':raw,'confirmation':'Replace device slot 15'}):
                with self.assertRaises(ValueError):self.service.dispatch(req)
            api.assert_not_called()

    def test_project_operations_dispatch_separate_from_instruments(self):
        wire=device.bridge.native.encode(fixture());path=self.root/'project.fmer-native';path.write_bytes(wire)
        session=Mock();session.verified_identity=device.bridge.IDENTITY;session.close.return_value=[];client=Mock()
        client.list_projects.return_value={'slots':[],'status':{'project_capacity':16}}
        client.export_project.return_value={'backup':{'path':str(path)}}
        client.save_project.return_value=client.load_project.return_value=client.push_project.return_value={}
        with patch.object(device.hardware_bridge,'WinMM'),patch.object(device.bridge.transport,'find_session',return_value=session),patch.object(device.bridge,'NativeBridge',return_value=client):
            self.service.dispatch({'action':'project_catalog'})
            pulled=self.service.dispatch({'action':'project_pull','slot':15})
            self.assertEqual(base64.b64decode(pulled['raw']),wire)
            self.service.dispatch({'action':'project_push','slot':15,'raw':pulled['raw'],'confirmation':'Replace device project 15'})
            self.service.dispatch({'action':'project_load','slot':15})
            self.service.dispatch({'action':'project_save','slot':15,'confirmation':'Save device project 15'})
        client.push_slot.assert_not_called();client.load_slot.assert_not_called()
        client.push_project.assert_called_once();client.save_project.assert_called_once();client.load_project.assert_called_once()
        self.assertEqual(session.close.call_count,5)


if __name__=='__main__':unittest.main()
