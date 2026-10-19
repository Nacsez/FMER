import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fm1_stock_rom_entry as entry


class Fake:
    def __init__(self, identity="FM-1_015", fail_log=False):
        self.identity, self.fail_log, self.sent = identity, fail_log, []
    def identify(self):
        return self.identity
    def record(self, *args, **kwargs):
        if self.fail_log:
            raise OSError("disk full")
    def _send(self, packet, purpose):
        self.sent.append(packet)


class StockEntryTests(unittest.TestCase):
    def test_exact_stock_sends_only_documented_key(self):
        fake = Fake()
        entry.enter(fake, fake)
        self.assertEqual(fake.sent, [bytes.fromhex("f0 22 24 35 7d f7")])
    def test_other_identity_never_enters_rom(self):
        for identity in ("FM-1_730", "ota-FM-1_015", "FM-1_016", ""):
            with self.subTest(identity=identity):
                fake = Fake(identity)
                with self.assertRaises(entry.transport.UpdateError):
                    entry.enter(fake, fake)
                self.assertEqual(fake.sent, [])
    def test_failed_durable_intent_prevents_mode_switch(self):
        fake = Fake(fail_log=True)
        with self.assertRaises(OSError):
            entry.enter(fake, fake)
        self.assertEqual(fake.sent, [])
