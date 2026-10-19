import unittest,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import fm1_native_bridge_v23 as b
import companion_archive as archive
from tests.test_companion_product import unit_backup
from unittest.mock import Mock
class Defaults729Tests(unittest.TestCase):
 def test_settings_status_and_actions(self):
  values=[4,1,0,11,0,0,1,1,128,5,30,0,0,6,0,0,6,3728,3,12,1,16,719]
  frame=b.native.PREFIX+bytes([21])+(' '.join(map(str,values))).encode()+bytes([247])
  self.assertEqual(b.parse_store_status(frame)['fx_default'],719)
  for a in (11,12):self.assertIn(a,b.store_action_request(a,0,1,30))
  with self.assertRaises(ValueError):b.store_action_request(13,0,1,30)
  values[-1]=720
  with self.assertRaises(ValueError):b.parse_store_status(b.native.PREFIX+bytes([21])+(' '.join(map(str,values))).encode()+bytes([247]))
 def test_archives_preserve_global_default_and_old_scope(self):
  value=unit_backup();client=Mock();archive.restore(client,value,Path('unused'));client.save_fx_default.assert_not_called()
  value['payload']['identity']='FM-1_729';value['payload']['fx_default']=719;value=archive.seal(value['payload']);client=Mock()
  archive.restore(client,value,Path('unused'));client.save_fx_default.assert_called_once_with(719,Path('unused'))
  value['payload']['fx_default']=720
  with self.assertRaises(ValueError):archive.validate(archive.seal(value['payload']))

 def test_only_exact_installed_origins_can_transition_to729(self):
  import fm1_package as package
  from unittest.mock import patch
  digest=bytes.fromhex(package.INSTALLED_728_RELEASE3_APP_SHA256)
  other=bytes.fromhex(package.INSTALLED_728_RELEASE1_APP_SHA256)
  repair=bytes.fromhex(package.INSTALLED_729_RELEASE1_APP_SHA256)
  with patch.object(package,'_installed_reference',return_value=b'checked'):
   good=package.transition_profile(package.DEFAULTS_PRODUCT,package.TEST01_TEMPLATE,b'prefix'+digest+b'suffix')
   self.assertEqual(good['origin_identity'],'FM-1_728');self.assertEqual(good['loader_identity'],'ota-FM-1_729')
   self.assertEqual(good['origin_app_sha256'],digest.hex())
   repaired=package.transition_profile(package.DEFAULTS_PRODUCT,package.TEST01_TEMPLATE,repair)
   self.assertEqual(repaired['origin_identity'],'FM-1_729')
   self.assertEqual(repaired['origin_app_sha256'],repair.hex())
   for bad in (b'',other,digest*2,digest+other,repair*2,digest+repair,repair+other):
    with self.assertRaises(ValueError):package.transition_profile(package.DEFAULTS_PRODUCT,package.TEST01_TEMPLATE,bad)
