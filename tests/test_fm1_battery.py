"""Cached battery observations: honest unknowns, bounded capture and no writes."""
from pathlib import Path
import copy,sys,tempfile,unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_native_bridge_v13 as bridge
import fm1_session as capture
import companion_device as companion
from tests.test_fm1_session import frame,FakeSession,MemoryJournal,Clock
from tests.test_fm1_native_bridge_v13 import Session,Journal


class BatteryTests(unittest.TestCase):
    def test_unknown_stale_and_valid_readings_keep_exact_adc(self):
        self.assertEqual(bridge.battery_status_request(),capture.PREFIX+bytes([28,247]))
        for values in ([1,0,0,0xffffffff,0,0],[1,612,603,5000,0,1],[1,611,606,4999,1,1]):
            value=bridge.parse_battery_status(frame(28,values))
            self.assertEqual(list(value.values()),values)
            self.assertEqual(set(value),set(bridge.BATTERY_FIELDS))
            self.assertFalse({'percent','voltage','charging'}&set(value))

    def test_malformed_and_impossible_validity_never_become_samples(self):
        good=[1,611,606,20,1,1]
        bad=[frame(27,good),frame(28,good[:-1]),frame(28,good+[0]),frame(28,good)[:-1]]
        for idx,val in ((0,2),(1,1024),(2,1024),(3,5000),(3,1<<32),(4,2),(5,2),(1,-1)):
            values=good.copy();values[idx]=val;bad.append(frame(28,values))
        bad.extend([frame(28,good).replace(b'611',b'0611'),frame(28,good).replace(b'611',b'+611')])
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):bridge.parse_battery_status(value)

    def test_bridge_read_keeps_sound_bank_and_working_state_unchanged(self):
        session,journal=Session(),Journal();before=copy.deepcopy(session.__dict__)
        normal=session._send
        def send(packet,purpose):
            if packet==bridge.battery_status_request():session.sent.append(packet);session.frame=frame(28,[1,611,606,20,1,1])
            else:normal(packet,purpose)
        session._send=send
        value=bridge.NativeBridge(session,journal).battery_status()
        self.assertEqual(value['raw_adc'],611)
        self.assertEqual(session.sent,[bridge.battery_status_request()])
        for key in ('state','slots','generation','native_writes','flash_writes'):
            self.assertEqual(session.__dict__[key],before[key])
        self.assertEqual(journal.events[-1]['event'],'battery_status')

    def test_read_allowlist_requires_verified719_and_exact_request(self):
        session=object.__new__(capture.ReadOnlySession)
        with patch.object(capture.transport.MidiSession,'_send') as send:
            for expected,verified in [('FM-1_718','FM-1_718'),('FM-1_719',None),('FM-1_719','FM-1_719')]:
                session.expected_identity=expected;session.verified_identity=verified
                if expected==verified=='FM-1_719':session._send(bridge.battery_status_request(),'test')
                else:
                    with self.assertRaises(capture.CaptureError):session._send(bridge.battery_status_request(),'test')
            with self.assertRaises(capture.CaptureError):session._send(capture.PREFIX+bytes([28,0,247]),'test')
            self.assertEqual(send.call_count,1)

    def test_sampler_cadence_unknown_and_disconnect_are_distinct(self):
        journal=MemoryJournal();sampler=capture.BatteryTelemetry(journal)
        session=Mock();session.read.return_value=frame(28,[1,600,602,12,1,1])
        for now in (0.,1.,4.99,5.,6.,10.):sampler.poll(session,now)
        self.assertEqual(session._send.call_count,3)
        self.assertEqual(len(journal.events),3)
        session.read.return_value=None
        with self.assertRaises(capture.Disconnected):sampler.poll(session,15.)
        old=Mock();old.read.return_value=None;journal=MemoryJournal();sampler=capture.BatteryTelemetry(journal)
        for now in (0.,5.,20.):self.assertIsNone(sampler.poll(old,now))
        self.assertEqual(old._send.call_count,1)
        self.assertEqual(journal.events[0]['event'],'battery_telemetry_unavailable')

    def test_recorder_is_opt_in_and_records_on_five_second_cadence(self):
        for enabled in (False,True):
            session=FakeSession(identity='FM-1_719');journal=MemoryJournal();clock=Clock();original=session.read
            session.read=lambda timeout:frame(28,[1,611,606,20,1,1]) if session.sent[-1][6]==28 else original(timeout)
            with patch.object(capture,'connect',return_value=(session,None)):
                capture.capture(Mock(),journal,duration=10.3,identity='FM-1_719',clock=clock,sleep=clock.sleep,battery_telemetry=enabled)
            self.assertEqual(sum(p[6]==28 for p in session.sent),3 if enabled else 0)
            self.assertEqual(sum(e['event']=='battery_status' for e in journal.events),3 if enabled else 0)
        with self.assertRaises(ValueError):capture.capture(Mock(),MemoryJournal(),identity='FM-1_718',battery_telemetry=True)

    def test_companion_explicit_flag_reaches_hidden_recorder_without_hardware(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);service=companion.Device(Path('unused'),root/'library')
            for enabled in (False,True):
                service.recorder=None;service.capture_battery=enabled
                proc=Mock();proc.poll.return_value=None;proc.pid=123
                with patch.object(companion,'ROOT',root),patch.object(companion.subprocess,'Popen',return_value=proc) as popen,patch.object(Path,'read_text',return_value='{"phase":"capturing"}'):
                    service.start_recording()
                command=popen.call_args.args[0]
                self.assertEqual('--battery-telemetry' in command,enabled)
            for request in ({'action':'record','battery_telemetry':1},{'action':'pull','slot':0,'battery_telemetry':True}):
                with self.assertRaises(ValueError):service.dispatch(request)

    def test_companion_record_request_and_resume_retain_explicit_choice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);service=companion.Device(Path('unused'),root/'library')
            session=Mock();session.verified_identity=companion.bridge.IDENTITY;session.close.return_value=[];client=Mock();client.list_slots.return_value={}
            observed=[]
            def start():observed.append(service.capture_battery);return {'recording':True}
            with patch.object(companion,'ROOT',root),patch.object(companion.hardware_bridge,'WinMM'),patch.object(companion.bridge.transport,'find_session',return_value=session),patch.object(companion.bridge,'NativeBridge',return_value=client),patch.object(service,'start_recording',side_effect=start),patch.object(service,'stop_recording'):
                service.dispatch({'action':'record','battery_telemetry':True})
                service.recorder=Mock();service.recorder.poll.return_value=None
                service.dispatch({'action':'catalog'})
                service.dispatch({'action':'record'})
            self.assertEqual(observed,[True,True,False])

if __name__=='__main__':unittest.main()
