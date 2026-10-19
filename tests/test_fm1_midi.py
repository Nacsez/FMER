"""No device I/O: strict710 MIDI protocol, staged parser and callback regressions."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_native_bridge_v4 as bridge
import fm1_session as recorder
import hardware_bridge as hw
import build_fm1_candidate as builder
from tests.test_fm1_native_state import reply
from collections import deque

class MidiTests(unittest.TestCase):
 def test_exact_midi_settings_and_status(self):
  settings=[3,15,1,2,0,1,1,0]
  packet=bridge.midi_settings_request(settings,0xffffffff)
  self.assertEqual(packet,bytes.fromhex('f0 7d 46 4d 45 52 1a 7f 7f 7f 7f 0f 03 0f 01 02 00 01 01 00 f7'))
  fields=[1,4,4,1]+settings+[120,1,1,40,0,0,1,919,0,3,0,0,1,0]
  status=bridge.parse_midi_status(reply(25,fields));self.assertEqual(status['settings'],settings)
  self.assertEqual(status['received_clock'],120)
  for i,value in ((0,2),(3,2),(4,4),(5,16),(7,3),(11,1),(22,65),(25,65536)):
   bad=fields.copy();bad[i]=value
   with self.subTest(i=i),self.assertRaises(ValueError):bridge.parse_midi_status(reply(25,bad))
  for bad in ([],[True]*8,[0,16,1,0,0,1,0,0],[0,0,1,3,0,1,0,0]):
   with self.assertRaises(ValueError):bridge.midi_settings_request(bad,1)
 def test_callback_separates_short_messages_from_sysex(self):
  s=object.__new__(hw.IdentitySession);s.capture_short=True;s.short_received=deque();s.short_overflow=0;s.received=deque();s.callback_overflow=False
  s._callback(None,0x3c3,None,0x643c90,123)
  self.assertEqual(list(s.short_received),[(0x643c90,123,False)]);self.assertFalse(s.received)
  for i in range(4100):s._callback(None,0x3c3,None,0xf8,i)
  self.assertEqual(len(s.short_received),4096);self.assertEqual(s.short_overflow,5)
  s._callback(None,hw.MIM_LONGDATA,None,1234,12);self.assertEqual(list(s.received),[(hw.MIM_LONGDATA,1234,12)])
 def test_explicit_recorder_identity_and_new_read(self):
  self.assertEqual(recorder.parameter_count('FM-1_710'),198)
  with self.assertRaises(ValueError):recorder.require_identity('FM-1_732')
 def test_staged_parser_patches_refuse_unknown_source(self):
  for patch in (builder.brand_usb,builder.patch_uart):
   with self.assertRaises(ValueError):patch(b'unreviewed')

if __name__=='__main__':unittest.main()
