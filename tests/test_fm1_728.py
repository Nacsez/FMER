"""Exact origin selection for the corrected728 build, no hardware or private I/O."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_package as package
class RoutingOriginTests(unittest.TestCase):
 def test_each_origin_is_unique_and_mixed_or_unknown_origins_refused(self):
  old=bytes.fromhex(package.INSTALLED_727_APP_SHA256)
  initial=bytes.fromhex(package.INSTALLED_728_RELEASE1_APP_SHA256)
  with patch.object(package,'_installed_reference',return_value=b'checked'):
   for digest,identity in ((old,'FM-1_727'),(initial,'FM-1_728')):
    result=package.transition_profile(package.ROUTING_PRODUCT,package.TEST01_TEMPLATE,b'prefix'+digest+b'suffix')
    self.assertEqual(result['origin_identity'],identity)
    self.assertEqual(result['origin_app_sha256'],digest.hex())
   for bad in (b'',old*2,initial*2,old+initial,initial+bytes.fromhex(package.INSTALLED_726_APP_SHA256)):
    with self.assertRaises(ValueError):package.transition_profile(package.ROUTING_PRODUCT,package.TEST01_TEMPLATE,bad)
