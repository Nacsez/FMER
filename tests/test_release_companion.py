"""Release-boundary regressions: no device access, no private review prerequisites."""
from pathlib import Path
import base64,hashlib,json,sys,tempfile,unittest,zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import release_firmware as release
import fm1_flash_transport as transport
import build_companion_portable as portable
R=release.ROOT

class HelpPictures(unittest.TestCase):
    def test_source_package_includes_original_licensed_splash(self):
        with tempfile.TemporaryDirectory() as tmp:
            portable.source_archive(Path(tmp))
            with zipfile.ZipFile(Path(tmp)/'Corresponding Source.zip') as archive:
                png=archive.read('FMER SPLASH.png')
                self.assertEqual(png,(R/'FMER SPLASH.png').read_bytes())
                notice=archive.read('docs/release/ARTWORK.md').decode('utf8')
                self.assertIn(hashlib.sha256(png).hexdigest(),notice)
                self.assertIn('GPL-3.0-only',notice)
                for name in ('LICENSE','tools/generate_fm1_visuals.py','firmware/fm1/splash.h'):
                    self.assertTrue(archive.read(name),name)

    def test_every_topic_and_menu_has_a_local_accessible_figure(self):
        topics=json.loads((R/'docs/help/topics.json').read_text())
        figures=json.loads((R/'docs/help/figures.json').read_text())
        self.assertEqual(set(figures),{x['slug'] for x in topics}|{'panel','reference'})
        self.assertEqual(len(figures['panel']),len(json.loads((R/'docs/help/panel.json').read_text())))
        for slug,items in figures.items():
            self.assertTrue(items,slug)
            for item in items:
                self.assertRegex(item['file'],r'^[a-z0-9_-]+\.(png|svg)$')
                self.assertTrue((R/'host/help'/item['file']).is_file(),item['file'])
                self.assertTrue(item['alt']);self.assertTrue(item['caption'])
    def test_runtime_closure_has_dynamic_entrypoints(self):
        files={p.stem for p in portable.runtime_modules()}
        self.assertTrue({'companion','portable_companion','fm1_session','release_firmware','fm1_native_bridge_v26','fm1_native_state_v11','unit_endpoints'}.issubset(files))

class ReleaseAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (R/release.CATALOG).is_file():raise unittest.SkipTest('Private preview package not built')
        cls.record=release.catalog()[0]
        path=R/'firmware/releases'/cls.record['filename']
        if not path.is_file():raise unittest.SkipTest('Private preview package not built')
        cls.raw=path.read_bytes()
    def test_exact_release_has_no_development_reference_lookup(self):
        with patch.object(release.package,'citrine_flash_reference',side_effect=AssertionError('Private dump lookup')),patch.object(release.package,'validate_package',side_effect=AssertionError('Legacy review lookup')):
            report=release.inspect_bytes(self.raw)
            self.assertTrue(report['runtime_preflight_qualified'])
            self.assertFalse(report['hardware_qualified'])
            with tempfile.TemporaryDirectory() as tmp:
                file=Path(tmp)/'preview.fwsc';file.write_bytes(self.raw)
                qualified=transport.qualify_package(file,self.record['package_sha256'],self.record['loader_sha256'])
                self.assertEqual(transport.update_identities(qualified),('compatible-FM-1',release.LOADER,'FM-1_734'))
    def test_changed_bytes_are_never_release_admitted(self):
        raw=bytearray(self.raw);raw[5000]^=1
        self.assertIsNone(release.inspect_bytes(raw))
    def test_current_target_requires_pinned_profile_and_exact_loader_hash(self):
        report=release.inspect_bytes(self.raw)
        unpinned={k:v for k,v in report.items() if k!='release_profile'}
        with self.assertRaisesRegex(transport.UpdateError,'catalog-pinned release'):
            transport.update_identities(type('Q',(),{'report':unpinned})())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'current.fwsc';path.write_bytes(self.raw)
            with self.assertRaisesRegex(transport.UpdateError,'product or loader'):
                transport.qualify_package(path,self.record['package_sha256'],'0'*64)
    def test_wrong_origin_and_missing_source_pin_refused(self):
        for change in ({'origin_identity':'FM-1_731'},{'source_files':[]},{'record_address':0xE4F00}):
            with patch.object(release,'catalog',return_value=[{**self.record,**change}]):
                with self.assertRaises(ValueError):release.inspect_bytes(self.raw)
    def test_unknown_stock_and_wrong_record_cannot_enter_stage_two(self):
        report=release.inspect_bytes(self.raw)
        qualified=type('Q',(),{'report':report})()
        good=dict(record_address=0xE7F00,match_count=1,loader_length=report['loader_image_bytes'],state=0,error=0,app_dirty=0)
        transport.require_loader_ready(good,qualified,resume=False)
        for changes in ({'app_dirty':1},{'record_address':0xE8F00},{'match_count':2},{'loader_length':1},{'error':-14}):
            with self.assertRaises(transport.UpdateError):transport.require_loader_ready({**good,**changes},qualified,resume=False)
        transport.require_loader_ready(good,qualified,resume=True)
        transport.require_loader_ready({**good,'record_address':0xE4F00},qualified,resume=False)
    def test_first_16k_never_contains_a_private_device_head(self):
        _,_,files=release.package.decode_package(self.raw)
        self.assertEqual(files['flash.bin']['payload'][:0x4000],release.distribution_head())
        self.assertEqual(files['flash.bin']['payload'][160:0x4000],b'\xff'*(0x4000-160))
        head=bytearray(files['flash.bin']['payload'][:32]);release.package.enc(head,0,32)
        self.assertEqual(release.package.crc16(head[2:]),int.from_bytes(head[:2],'little'))
        self.assertEqual(bytes(head[2:]),release.package.FLASH_HDR)
        # A valid flash descriptor alone is insufficient: stage1 follows the
        # directory before it ever asks for the updater. Validate every entry.
        entries=[]
        for offset in range(32,160,32):
            raw=bytearray(files['flash.bin']['payload'][offset:offset+32])
            release.package.enc(raw,0,32);entries.append(release.package.jlfs_header(raw))
        app=next(x for x in entries if x[-1].split(b'\0')[0]==b'app_dir_head')
        self.assertEqual((app[2],app[4]),(0x4000,0x81))
        self.assertEqual(files['flash.bin']['offset']+app[2],17408)


if __name__=='__main__':unittest.main()
