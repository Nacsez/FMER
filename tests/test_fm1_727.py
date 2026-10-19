import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import unittest
from unittest.mock import patch
import fm1_package as pkg
import fm1_native_bridge_v21 as bridge
import fm1_session as session
import fm1_bench
class Workflow727(unittest.TestCase):
 def test_exact_installed726_origin(self):
  digest=bytes.fromhex(pkg.INSTALLED_726_APP_SHA256)
  with patch.object(pkg,'_installed_reference',return_value=b'checked'):
   p=pkg.transition_profile(pkg.WORKFLOW_PRODUCT,pkg.TEST01_TEMPLATE,b'loader'+digest)
   self.assertEqual(p['origin_identity'],'FM-1_726')
   self.assertEqual(p['loader_identity'],'ota-FM-1_727')
   for wrong in (b'',digest*2,digest+bytes.fromhex(pkg.INSTALLED_724_RELEASE3_APP_SHA256)):
    with self.assertRaises(ValueError):pkg.transition_profile(pkg.WORKFLOW_PRODUCT,pkg.TEST01_TEMPLATE,wrong)
 def test_native_format_unchanged_and_explicit_identity(self):
  self.assertEqual(bridge.IDENTITY,'FM-1_727')
  self.assertIn(bridge.IDENTITY,session.SUPPORTED_IDENTITIES)
  self.assertIn('ota-FM-1_727',bridge.transport.SUPPORTED_LOADER_IDS)
  self.assertEqual(bridge.native.__name__,'fm1_native_state_v8')
