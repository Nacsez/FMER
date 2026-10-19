import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import unittest
import fm1_native_state_v8 as native
import fm1_native_state_v7 as previous
from tests.test_fm1_native_v7 import fixture as old_fixture

def fixture():return native.decode_compatible(previous.encode(old_fixture()))

class Native8Tests(unittest.TestCase):
 def test_old_records_migrate_exactly(self):
  old=old_fixture(); new=fixture()
  for key in ('controls','vced','tracks','patterns','source_generation','preset_id'):self.assertEqual(new[key],old[key])
  self.assertEqual(native.decode(native.encode(new)),new)
 def test_strum_and_noise_roundtrip_and_old_decoder_refuses(self):
  s=fixture();s['controls'][161]=4;s['controls'][180]=10
  raw=native.encode(s);self.assertEqual(native.decode(raw),s)
  with self.assertRaises(previous.NativeStateError):previous.decode(raw)
  for key,value in ((161,5),(180,11)):
   s=fixture();s['controls'][key]=value
   with self.assertRaises(native.NativeStateError):native.encode(s)
