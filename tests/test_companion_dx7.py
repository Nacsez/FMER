# SPDX-License-Identifier: GPL-3.0-only
"""DX7 import/export and catalog atomicity; no device I/O or user files."""
import base64
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import companion_dx7 as dx7
import companion_bank as bank
import companion_shelf as shelf
import library


def state():
    c = [bank.native.control_bounds(i)[0] for i in range(198)]
    c[178] = 120
    c[186:191] = [16, 0, 128, 100, 75]
    c[191] = 4
    s = dict(schema=bank.native.SCHEMA, version=bank.native.VERSION,
             source_generation=17, preset_id=65535, controls=c,
             vced=c[:145] + list(b'TEST SOUND'),
             patterns=[dict(length=16, steps=[[128, 100, 75] for _ in range(64)]) for _ in range(16)])
    bank.native.initialize_tracks(s)
    return s


class FixtureCodec:
    def decode(self, raw):
        return [dict(vced=state()['vced']) for _ in range(1 if len(raw) == 163 else 32)]


class CompanionDx7Tests(unittest.TestCase):
    def test_import_is_dry_complete_sound_without_mutating_template_or_device(self):
        template = state()
        template['patterns'][1]['steps'][2] = [63, 101, 88]
        before = deepcopy(template)
        result = dx7.decode(bytes(163), template, FixtureCodec())
        self.assertEqual(template, before)
        self.assertFalse(result['hardware_access'])
        imported = bank.decode_record(result['entries'][0]['native'])
        self.assertEqual(imported['vced'], template['vced'])
        self.assertEqual(imported['controls'][160], 0)
        self.assertEqual(imported['controls'][147], 1)
        self.assertEqual(imported['patterns'][1]['steps'][2][0], 128)
        self.assertTrue(all(imported['controls'][i] == 0 for i in (168,169,170,173,174)))

    def test_bank_catalog_import_is_one_undo_transaction(self):
        decoded = dx7.decode(bytes(4104), state(), FixtureCodec())
        with tempfile.TemporaryDirectory() as directory:
            catalog = shelf.Catalog(Path(directory), Path('unused'))
            result = catalog.dispatch(dict(action='import', revision=0, backup=dx7.make_catalog(decoded, 'Community FM')))
            self.assertEqual(len(result['slots']), 32)
            self.assertTrue(all(i['collection'] == 'Community FM' for i in result['slots']))
            self.assertEqual(catalog.dispatch(dict(action='undo', revision=result['revision']))['slots'], [])

    def test_editor_merge_retains_pattern_song_mixer_and_mode(self):
        project = state()
        project['patterns'][1]['steps'][2] = [63, 101, 88]
        project['controls'][153] = 1
        project['song'][0].update(enabled=True, length=1)
        imported = dx7.decode(bytes(163), state(), FixtureCodec())['entries'][0]
        result = dx7.merge_sound(imported, project)
        self.assertEqual(result['patterns'], project['patterns'])
        self.assertEqual(result['song'], project['song'])
        self.assertEqual(result['tracks'], project['tracks'])
        self.assertEqual(result['controls'][153], 1)

    def test_native_felucca_json_and_multiple_banks_are_explicitly_rejected(self):
        for raw in (b'{}', bytes(128), bytes(8208), 'text'):
            with self.subTest(size=len(raw)), self.assertRaisesRegex(ValueError, 'DX7 voice'):
                dx7.decode(raw, state(), FixtureCodec())

    def test_va_export_does_not_silently_export_hidden_fm_voice(self):
        s = state();s['controls'][160] = 1
        with self.assertRaisesRegex(ValueError, 'FM instruments only'):
            dx7.export([s], FixtureCodec())


@unittest.skipUnless(os.environ.get('FMER_HOST_EXE'), 'Set FMER_HOST_EXE for shared C++ DX7 codec checks')
class ActualCodecTests(unittest.TestCase):
    def setUp(self):
        self.codec = library.PatchCodec(Path(os.environ['FMER_HOST_EXE']), lambda *a, **kw: None)
        self.template = state()

    def test_single_and_bank_roundtrip_actual_codec(self):
        for count in (1, 32):
            voices = []
            for i in range(count):
                s = state();s['vced'][134] = s['controls'][134] = i
                voices.append(s)
            exported = dx7.export(voices, self.codec)
            decoded = dx7.decode(base64.b64decode(exported['raw']), self.template, self.codec)
            actual = [bank.decode_record(e['native'])['vced'] for e in decoded['entries']]
            self.assertEqual(actual, [s['vced'] for s in voices])

    def test_bad_checksum_and_out_of_range_parameter_refused(self):
        raw = bytearray(base64.b64decode(dx7.export([state()], self.codec)['raw']))
        raw[-2] ^= 1
        with self.assertRaises(ValueError):dx7.decode(bytes(raw), self.template, self.codec)
        raw[-2] ^= 1;raw[6] = 127;raw[-2] = (-sum(raw[6:-2])) & 127
        with self.assertRaises(ValueError):dx7.decode(bytes(raw), self.template, self.codec)


if __name__ == '__main__':unittest.main()
