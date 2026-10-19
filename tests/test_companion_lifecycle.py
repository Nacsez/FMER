from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from companion_lifecycle import BrowserLeases
class LifecycleTests(unittest.TestCase):
 def test_tabs_refresh_close_and_transfer_guard(self):
  now=[0];l=BrowserLeases(lambda:now[0]);self.assertFalse(l.expired())
  l.update('a');l.update('b');l.update('a',True)
  now[0]=40;l.update('b');self.assertFalse(l.expired())
  l.update('b',True);now[0]=86;self.assertTrue(l.expired())
  self.assertFalse(l.expired(active=True));now[0]=120;self.assertFalse(l.expired())
  now[0]=132;self.assertTrue(l.expired());l.update('reopened');self.assertFalse(l.expired())
 def test_crashed_browser_and_no_browser_start_timeout(self):
  now=[0];l=BrowserLeases(lambda:now[0]);now[0]=119;self.assertFalse(l.expired())
  now[0]=121;self.assertTrue(l.expired());l.update('tab');now[0]=167;self.assertFalse(l.expired());now[0]=302;self.assertTrue(l.expired())
 def test_invalid_lease_rejected(self):
  l=BrowserLeases()
  for x in (None,'','x'*81):
   with self.assertRaises(ValueError):l.update(x)
if __name__=='__main__':unittest.main()
