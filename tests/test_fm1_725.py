import unittest
from unittest.mock import patch
import fm1_package as pkg
import fm1_native_bridge_v19 as bridge
import companion_jobs
class Release725(unittest.TestCase):
 def test_exact_predecessor_only(self):
  digest=bytes.fromhex(pkg.INSTALLED_724_RELEASE3_APP_SHA256)
  with patch.object(pkg,'_installed_reference',return_value=b'checked'):
   result=pkg.transition_profile(pkg.RELEASE_PRODUCT,pkg.TEST01_TEMPLATE,b'loader'+digest)
   self.assertEqual(result['origin_identity'],'FM-1_724')
   self.assertEqual(result['loader_identity'],'ota-FM-1_725')
   for value in (b'',digest*2,digest+bytes.fromhex(pkg.INSTALLED_723_RELEASE4_APP_SHA256)):
    with self.assertRaises(ValueError):pkg.transition_profile(pkg.RELEASE_PRODUCT,pkg.TEST01_TEMPLATE,value)
 def test_companion_advertises_exact_bridge_and_mode_limits(self):
  caps=companion_jobs.Jobs(None,"unused").capabilities()
  self.assertEqual(caps['firmware_identity'],'FM-1_734')
  self.assertEqual(caps['native_version'],11)
  self.assertIn('mono',caps['voice_modes']['tracks'])
