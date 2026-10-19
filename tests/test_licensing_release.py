"""Release source/notices coverage; never accesses an instrument or network."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_companion_help as handbook
import build_companion_portable as portable
import build_fm1_candidate as target


class SourceDistributionTests(unittest.TestCase):
    def test_archive_preserves_license_and_rebuildable_platform_inputs(self):
        if not target.FELUCCA.exists():
            self.skipTest('Reviewed Felucca acquisition is not present')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            portable.source_archive(out)
            with zipfile.ZipFile(out / 'Corresponding Source.zip') as archive:
                names = set(archive.namelist())
                for name in ('LICENSE', 'LICENSING.md', 'NOTICE',
                             'docs/SOURCE_BUILD.md', 'core/factory_presets.cpp',
                             'tools/build_fm1_candidate.py',
                             'tools/build_companion_portable.py',
                             'third_party/msfa/COPYING',
                             'firmware/fm1/README.md',
                             'firmware/fm1/loader/LICENSE',
                             'firmware/fm1/loader/PROVENANCE.json',
                             'firmware/fm1/loader/tests/CMakeLists.txt',
                             'firmware/fm1/loader/compatibility.h',
                             'firmware/fm1/loader/write_policy.h'):
                    self.assertIn(name, names)
                    self.assertEqual(archive.read(name), (portable.ROOT / name).read_bytes())
                # Every source/header selected by the actual target builder must
                # be present, including pre-generated font and splash headers.
                for path in target.local_source_files()+target.local_header_files():
                    name=path.relative_to(portable.ROOT).as_posix()
                    self.assertEqual(archive.read(name),path.read_bytes())
                for folder in ('core','host','firmware/fm1'):
                    for path in (portable.ROOT/folder).rglob('CMakeLists.txt'):
                        name=path.relative_to(portable.ROOT).as_posix()
                        self.assertEqual(archive.read(name),path.read_bytes())
                figures=json.loads((portable.ROOT/'docs/help/figures.json').read_text(encoding='utf8'))
                for group in figures.values():
                    for figure in group:
                        name='host/help/'+figure['file']
                        self.assertEqual(archive.read(name),(portable.ROOT/name).read_bytes())
                for name in ('host/help/license.txt','host/help/notice.txt'):
                    self.assertEqual(archive.read(name),(portable.ROOT/name).read_bytes())
                # Neither a private dump nor a third-party musical bank is source.
                self.assertFalse(any(n.endswith(('.rom', '.fwsc', '.wav')) for n in names))
                base = target.FELUCCA.relative_to(portable.ROOT).as_posix()
                self.assertNotIn(base + '/firmware/src/voice.c', names)
                archive.extractall(out / 'extracted')
            extracted = out / 'extracted' / target.FELUCCA.relative_to(portable.ROOT)
            # The production verifier needs the exact parent tree.json as well
            # as each source blob. This was missing in the earlier package.
            self.assertEqual(target.verify_upstream(extracted),
                             target.verify_upstream(target.FELUCCA))

    def test_offline_help_provides_verbatim_license_and_attribution(self):
        files = handbook.build()
        self.assertEqual(files['license.txt'], (portable.ROOT / 'LICENSE').read_text())
        self.assertEqual(files['notice.txt'], (portable.ROOT / 'NOTICE').read_text(encoding='utf8'))
        page = files['licensing.htm']
        for name in ('license.txt', 'notice.txt', 'fmer-foundations.svg'):
            self.assertIn(name, page)
        coverage = json.loads(files['coverage.json'])
        self.assertIn('licensing', coverage['figures'])
        self.assertIn('LICENSING.md', coverage['sources'])


if __name__ == '__main__':
    unittest.main()
