# SPDX-License-Identifier: GPL-3.0-only
"""Offline V16 import boundaries; never open a MIDI device."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import companion_jobs as jobs
import stock_v16_research as research


class V16ResearchTests(unittest.TestCase):
    def voice(self, name=b'JAZZFLUTE\0'):
        data = bytearray(128)
        data[118:] = name
        return bytes(data)

    def test_name_padding_preserves_parameters_and_source(self):
        raw = self.voice()
        vced, changes = research.normalize_voice(raw)
        self.assertEqual(bytes(vced[145:]), b'JAZZFLUTE ')
        self.assertEqual(raw[127], 0)
        self.assertEqual(changes, dict(name_padding=[dict(packed_offset=127, original=0, imported=32)], ranges=[]))

    def test_embedded_control_name_and_reserved_bits_are_not_sanitized(self):
        for data in (self.voice(b'JA\0ZFLUTE '), bytes([128])+self.voice()[1:]):
            with self.assertRaises(ValueError): research.normalize_voice(data)

    def test_wrong_package_never_gets_extracted(self):
        for raw in (b'', b'\0'*research.SIZE):
            with self.assertRaises(ValueError): research.inspect(raw)

    def test_actual_publisher_resource_and_companion_refusal(self):
        source=ROOT/'third_party/acquired/stock-v16-20261022/FM-1.fwsc'
        if not source.exists(): self.skipTest('Optional private V16 research acquisition absent')
        raw=source.read_bytes()
        result, voices, bank=research.inspect(raw)
        self.assertEqual(len(bank), 16384)
        self.assertEqual(len(voices), 128)
        self.assertEqual(result['normalized_slots'], [101])
        self.assertFalse(result['installable'])
        with tempfile.TemporaryDirectory() as directory:
            service=jobs.Jobs(Mock(), Path(directory))
            with patch.object(jobs.hardware_bridge, 'WinMM', side_effect=AssertionError('No hardware')):
                for action in ('inspect', 'inspect_stock'):
                    report=service.inspect(dict(action=action, raw=base64.b64encode(raw).decode()))
                    self.assertTrue(report['recognized'])
                    self.assertFalse(report['installable'])
                    self.assertNotIn('inspection', report)
                    with self.assertRaisesRegex(ValueError, 'qualified firmware'):
                        service.start(dict(action='install',inspection=report['sha256'],confirmation='Install FM-1_016'))
            self.assertEqual(service.packages, {})


if __name__ == '__main__': unittest.main()
