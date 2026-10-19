import unittest
from unittest.mock import patch
import fm1_native_bridge_v17 as b
import fm1_package as pkg
class Cleanup723(unittest.TestCase):
 def test_exact_origin(self):
  digest=pkg.INSTALLED_722_RELEASE2_APP_SHA256
  with patch.object(pkg,'_installed_reference',return_value=b'checked'):
   r=pkg.transition_profile(pkg.CLEANUP_PRODUCT,pkg.TEST01_TEMPLATE,b'loader'+bytes.fromhex(digest))
   self.assertEqual(r['origin_identity'],'FM-1_722')
   for raw in (b'unknown',bytes.fromhex(digest)*2,bytes.fromhex(digest+pkg.INSTALLED_721_APP_SHA256)):
    with self.assertRaises(ValueError):pkg.transition_profile(pkg.CLEANUP_PRODUCT,pkg.TEST01_TEMPLATE,raw)
 def test_battery_history_v2(self):
  c=object.__new__(b.NativeBridge);c.journal=type('J',(),{'record':lambda *a,**k:None})()
  def frame(schema=2,adc=590):return b.native.PREFIX+bytes([32])+f'{schema} 1 1 0 1 300 {adc} {adc} 0'.encode()+bytes([247])
  c.request=lambda *a:frame();r=c.battery_history()
  self.assertEqual(r['nominal_interval_seconds'],300)
  self.assertEqual(r['retained_samples'][0]['usb_bus_active'],0)
  for schema,adc in ((1,590),(2,1024)):
   c.request=lambda *a:frame(schema,adc)
   with self.assertRaises(ValueError):c.battery_history()
