from pathlib import Path
import sys,unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_flash_transport as t
import companion_errors
from unittest.mock import patch
class CompatibilityTests(unittest.TestCase):
 def test_diagnostic_probe_never_starts_application_even_when_compatible(self):
  for dirty in (False,True):
   stages=[]
   session=SimpleNamespace(verified_identity='ota-FM-1_935',close=lambda:[],loader_control=lambda op:dict(state=0,error=0,match_count=1,app_dirty=dirty))
   journal=SimpleNamespace(record=lambda *a,**k:None)
   with patch.object(t,'require_write_qualification'),patch.object(t,'update_identities',return_value=('compatible-FM-1','ota-FM-1_935','FM-1_733')),patch.object(t,'find_session',return_value=session),patch.object(t,'serve',side_effect=lambda s,p,stage,j:stages.append(stage)),patch.object(t,'collect_metadata') as read:
    t.perform_loader_probe(None,None,journal,metadata_only=True)
    self.assertEqual(stages,[1]);read.assert_called_once()
 def frame(self,page=0):
  data=bytes([page,0])+bytes(range(256));data+=bytes([(~sum(data))&255])
  return t.CONTROL_PREFIX+b'\x43'+t.protocol.pack_seven_bit(data)+b'\xf7'
 def test_metadata_checksum_page_and_length(self):
  f=self.frame();self.assertEqual(len(f),305);self.assertEqual(t.parse_metadata_page(f,0),bytes(range(256)))
  for bad in (f[:-1],f[:20]+bytes([f[20]^1])+f[21:],self.frame(1)):
   with self.assertRaises(t.UpdateError):t.parse_metadata_page(bad,0)
 def test_fixed_read_windows_and_export(self):
  calls=[];events=[]
  session=SimpleNamespace(metadata_page=lambda page:(calls.append(page) or bytes(range(256))))
  package=SimpleNamespace(app_begin=0x4400,image=b'\0'*0x94000)
  journal=SimpleNamespace(record=lambda event,**data:events.append((event,data)))
  result=t.collect_metadata(session,package,journal)
  self.assertEqual(calls,list(range(20)));self.assertFalse(result['application_write_started'])
  self.assertEqual(result['pages'][0]['offset'],0x4000);self.assertEqual(result['pages'][-1]['offset'],0x92f00)
  self.assertEqual(events[-1][0],'compatibility_metadata')
 def test_no_diagnostic_command_to_old_or_stock_firmware(self):
  for identity in ('FM-1_015','ota-FM-1_933'):
   with self.assertRaises(t.UpdateError):t.MidiSession.metadata_page(SimpleNamespace(verified_identity=identity),0)
 def test_human_outcome_does_not_assert_hardware_revision(self):
  x=companion_errors.explain('This unit has a different memory layout or calibration',True)
  self.assertIn('does not prove',x['explanation']);self.assertIn('not written',x['explanation']);self.assertIn('Export',x['next_step'])
if __name__=='__main__':unittest.main()
