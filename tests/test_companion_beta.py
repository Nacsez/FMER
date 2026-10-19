import sys,tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import companion_stock as stock,companion_support as support,fm1_package as package,release_firmware
class BetaTests(unittest.TestCase):
 def test_unknown_stock_rejected_before_hardware(self):
  for raw in (b'',b'x'*0x100000,b'x'*0x8f000):
   with self.assertRaises(ValueError):stock.prepare(raw)
 def test_supported_stock_excludes_boot_and_keeps_loader(self):
  if not package.CITRINE_BACKUP.exists():self.skipTest('Private stock fixture not installed')
  raw=package.citrine_flash_reference();out=stock.prepare(raw[0x4000:])
  self.assertEqual(out.report['product'],'FM-1_015');self.assertFalse(out.report['settings_restored'])
  self.assertEqual(out.image[out.app_begin-0x4000:out.app_begin],release_firmware.distribution_head())
  self.assertEqual(out.image[out.app_begin:out.app_end],raw[0x4000:])
  varied=bytearray(raw[0x4000:]);varied[-3]^=0x55;self.assertEqual(stock.prepare(bytes(varied)).report['product'],'FM-1_015')
  varied[0x200]^=1
  with self.assertRaises(ValueError):stock.prepare(bytes(varied))
 def test_feedback_excludes_payload_paths_and_optional_private_fields(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'123';p.mkdir();(p/'job.json').write_text(json.dumps(dict(id='123',state='failed',error='open C:\\Users\\Owner\\private.json',result={'backup':'SECRET'},diagnostics={'hex':'SECRET'},traceback='SECRET')))
   out=json.dumps(support.summary(d));self.assertNotIn('SECRET',out);self.assertNotIn('Owner',out);self.assertIn('local path removed',out)
 def test_support_never_requires_feedback_in_all_categories(self):
  with tempfile.TemporaryDirectory() as d:self.assertEqual(support.summary(d)['operations'],[])
 def test_feedback_identifies_the_shipped_companion_and_target(self):
  with tempfile.TemporaryDirectory() as d:
   report=support.summary(d)
   self.assertEqual('FM-1_'+report['firmware'],release_firmware.TARGET)
   page=(Path(__file__).resolve().parents[1]/'host/companion_app.html').read_text(encoding='utf8')
   self.assertIn('FMER Companion '+report['companion']+' ',page)
if __name__=='__main__':unittest.main()
