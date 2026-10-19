# SPDX-License-Identifier: GPL-3.0-only
"""Official recognition never implies destructive layout-conversion admission."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import companion_stock as stock
import inspect_official_firmware as inspection


class OfficialRecognitionTests(unittest.TestCase):
    def test_unknown_bytes_are_not_recognized(self):
        self.assertIsNone(stock.known_file_info(b''))
        self.assertIsNone(stock.known_file_info(b'x' * 699956))
        self.assertIsNone(stock.known_file_info('not bytes'))

    def test_recognition_does_not_skip_layout_gate_or_open_hardware(self):
        raw=b'fixture'
        info=dict(reason='A new layout needs migration qualification',installable=False)
        with patch.object(stock,'known_file_info',return_value=info),patch.object(stock.release,'bundled',side_effect=AssertionError('Must stop before installer construction')):
            with self.assertRaisesRegex(ValueError,'migration qualification'):stock.prepare(raw)

    def test_pinned_vendor_fixtures_when_available(self):
        root=Path(__file__).resolve().parents[1]/'third_party/acquired/community-20261018'
        filenames=('stock-v15-package.bin','open-v13-package.bin')
        if not all((root/name).exists() for name in filenames):self.skipTest('Optional official reference acquisition not installed')
        for filename in filenames:
            raw=(root/filename).read_bytes();info=stock.known_file_info(raw)
            self.assertIsNotNone(info);self.assertFalse(info['installable']);self.assertFalse(info['hardware_access'])
            with self.assertRaisesRegex(ValueError,'layout'):stock.prepare(raw)
            altered=bytearray(raw);altered[-1]^=1
            self.assertIsNone(stock.known_file_info(bytes(altered)))

    def test_research_inspector_exposes_incompatible_regions(self):
        root=Path(__file__).resolve().parents[1]/'third_party/acquired/community-20261018'
        if not all((root/name).exists() for name in ('stock-v15-package.bin','open-v13-package.bin')):
            self.skipTest('Optional official reference acquisition not installed')
        public=inspection.inspect((root/'stock-v15-package.bin').read_bytes())
        opened=inspection.inspect((root/'open-v13-package.bin').read_bytes())
        self.assertEqual(public['application_headers'][1]['bytes'],581564)
        user=next(h for h in opened['application_headers'] if h['name']=='USER')
        self.assertEqual((user['address'],user['bytes']),(0x7c000,536576))
        self.assertFalse(opened['device_access']);self.assertFalse(opened['installable'])
        with self.assertRaises(ValueError):inspection.inspect(b'unknown')


if __name__=='__main__':unittest.main()
