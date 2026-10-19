# SPDX-License-Identifier: GPL-3.0-only
"""Independent 734 admission and interchange review; temporary files, no MIDI."""
import base64
from http.server import HTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import companion
import companion_bank as bank
import companion_device as device
import companion_jobs as jobs
import companion_stock as stock
import library
import release_firmware


class ReviewAdmissionTests(unittest.TestCase):
    def test_recognized_publisher_files_cannot_be_promoted_to_install_jobs(self):
        """Even an exact vendor pin supplies no install capability or token."""
        fixtures = Path(__file__).resolve().parents[1] / 'third_party/acquired/community-20261018'
        files = [fixtures / name for name in ('stock-v15-package.bin', 'open-v13-package.bin')]
        if not all(path.is_file() for path in files):
            self.skipTest('Optional official reference acquisition not installed')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'operations'
            service = jobs.Jobs(Mock(), root)
            with patch.object(jobs.hardware_bridge, 'WinMM', side_effect=AssertionError('No MIDI during inspection')):
                for path in files:
                    for action in ('inspect', 'inspect_stock'):
                        with self.subTest(file=path.name, action=action):
                            report = service.inspect(dict(action=action, raw=base64.b64encode(path.read_bytes()).decode()))
                            self.assertTrue(report['recognized'])
                            self.assertFalse(report['installable'])
                            self.assertNotIn('inspection', report)
                            with self.assertRaisesRegex(ValueError, 'qualified firmware'):
                                service.start(dict(action='install', inspection=report['sha256'],
                                                   confirmation='Install ' + report['product']))
                self.assertEqual(service.packages, {})
                self.assertEqual(service.jobs, {})
                self.assertFalse(root.exists())

    def test_installed_native_bridges_refuse_cross_version_sessions(self):
        """The current and previous identities are explicit admission paths."""
        for identity, module in device.BRIDGES.items():
            matching = Mock(verified_identity=identity)
            module.NativeBridge(matching, Mock())
            for other in ('FM-1_015', 'FM-1_8000013', 'FM-1_733', 'FM-1_734'):
                if other == identity:
                    continue
                with self.subTest(bridge=identity, other=other), self.assertRaisesRegex(RuntimeError, 'exact checksum-valid'):
                    module.NativeBridge(Mock(verified_identity=other), Mock())

    def test_current_bundled_package_is_exact_734_and_never_recognized_as_stock(self):
        raw = release_firmware.bundled('fm1-compatible-to-734-r1')
        report = release_firmware.inspect_bytes(raw)
        self.assertEqual(report['product'], 'FM-1_734')
        self.assertEqual(report['loader_identity'], 'ota-FM-1_935')
        self.assertTrue(report['runtime_preflight_qualified'])
        self.assertFalse(report['head_written'])
        self.assertEqual(report['app_write_range'][0], 16384)
        self.assertIsNone(stock.known_file_info(raw))


@unittest.skipUnless(os.environ.get('FMER_HOST_EXE'), 'Actual shared C++ codec requires FMER_HOST_EXE')
class ReviewDx7HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.executable = Path(os.environ['FMER_HOST_EXE'])
        cls.profile = bank.profile(cls.executable)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.hardware = patch.object(device.hardware_bridge, 'WinMM', side_effect=AssertionError('DX7 exchange must not access MIDI'))
        self.hardware.start()
        self.server = HTTPServer(('127.0.0.1', 0), companion.handler_for(self.executable, self.root / 'banks'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.hardware.stop()
        self.temp.cleanup()

    def request(self, path, data=None):
        body = None if data is None else library.canonical(data)
        with urlopen(Request(self.url + path, body, {'Content-Type': 'application/json'}), timeout=30) as response:
            return json.load(response)

    def test_bank_inspection_stale_commit_and_undo_preserve_existing_item(self):
        original = self.profile[0]
        initial = self.request('/api/catalog', dict(action='add', revision=0, kind='instrument',
                                                   title='Existing user sound', entry=original))
        entries = [entry for entry in self.profile if bank.decode_record(entry['native'])['controls'][160] == 0]
        self.assertEqual(len(entries), 32)
        exported = self.request('/api/dx7', dict(action='export', entries=entries))
        decoded = self.request('/api/dx7', dict(action='decode', raw=exported['raw']))
        self.assertEqual(decoded['count'], 32)
        self.assertEqual(self.request('/api/catalog'), initial)
        with self.assertRaises(HTTPError) as conflict:
            self.request('/api/catalog', dict(action='import', revision=0, backup=decoded['catalog']))
        self.assertEqual(conflict.exception.code, 409)
        self.assertEqual(self.request('/api/catalog'), initial)
        imported = self.request('/api/catalog', dict(action='import', revision=initial['revision'], backup=decoded['catalog']))
        self.assertEqual(len(imported['slots']), 33)
        self.assertEqual(imported['slots'][0], initial['slots'][0])
        undone = self.request('/api/catalog', dict(action='undo', revision=imported['revision']))
        self.assertEqual(undone['slots'], initial['slots'])
        self.assertEqual(self.request('/api/banks')['revision'], 0)

    def test_felucca_json_padded_to_valid_size_and_bad_base64_are_not_patch_imports(self):
        before = self.request('/api/catalog')
        raw = json.dumps({'patch': {'engine': 'FM6'}}).encode().ljust(163, b' ')
        for value in ('%%%invalid%%%', base64.b64encode(raw).decode()):
            with self.subTest(value=value[:24]), self.assertRaises(HTTPError) as rejected:
                self.request('/api/dx7', dict(action='decode', raw=value))
            self.assertEqual(rejected.exception.code, 400)
        self.assertEqual(self.request('/api/catalog'), before)
        self.assertFalse((self.root / 'banks' / 'library.json').exists())


if __name__ == '__main__':
    unittest.main()
