"""Release guide provenance and source-export privacy contracts; no hardware."""
import base64, hashlib, json, sys, unittest
from pathlib import Path
import xml.etree.ElementTree as ET

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tools'))
import prepare_public_source


class ReleaseGuideTests(unittest.TestCase):
    def test_plates_embed_exact_source_frames_and_have_no_external_assets(self):
        manifest=json.loads((R/'docs/help/feature-plates.json').read_text())
        for name,expected in manifest['source_images'].items():
            self.assertEqual(hashlib.sha256((R/'host/help'/name).read_bytes()).hexdigest(),expected,name)
        for entry in manifest['features']:
            tree=ET.fromstring((R/'host/help'/entry['file']).read_bytes())
            images=tree.findall('.//{http://www.w3.org/2000/svg}image')
            self.assertEqual(len(images),len(entry['frames']),entry['slug'])
            for node,name in zip(images,entry['frames']):
                href=node.attrib['href'];self.assertTrue(href.startswith('data:image/png;base64,'))
                self.assertEqual(base64.b64decode(href.split(',',1)[1]),(R/'host/help'/name).read_bytes())
            self.assertNotIn('<script',(R/'host/help'/entry['file']).read_text())

    def test_production_renderer_and_annotation_inputs_are_current(self):
        manifest=json.loads((R/'docs/help/feature-plates.json').read_text())
        for name,expected in manifest['inputs'].items():
            self.assertEqual(hashlib.sha256((R/name).read_bytes()).hexdigest(),expected,name+' needs guide regeneration')

    def test_every_sheet_is_reachable_from_help(self):
        manifest=json.loads((R/'docs/help/feature-plates.json').read_text())
        figures=json.loads((R/'docs/help/figures.json').read_text())
        gallery=(R/'host/help/visual-guide.htm').read_text(encoding='utf8')
        for entry in manifest['features']:
            self.assertIn(entry['file'],gallery)
            self.assertIn(entry['file'],[x['file'] for x in figures[entry['topic']]])
        self.assertIn('visual-guide.htm',(R/'host/help/index.htm').read_text())

    def test_source_export_excludes_private_history_and_binary_payloads(self):
        for name in ('.git/config','private/unit.bin','local/library/saved.json',
                     'artifacts/a.json','evidence/Companion Appdata 3/log.json',
                     'third_party/acquired/vendor/tool.py','firmware/releases/a.fwsc',
                     'recording.mp3','evidence/unit-backup.json',
                     'FM1_Research_Corpus_2026-09-29/a.md','../secret'):
            self.assertFalse(prepare_public_source.allowed(name),name)
        for name in ('core/synth.cpp','host/help/guide-home.png','docs/help/topics.json',
                     'third_party/acquired/fm1-target-review/community/felucca/source/LICENSE'):
            self.assertTrue(prepare_public_source.allowed(name),name)


if __name__=='__main__':unittest.main()
