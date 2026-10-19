"""Runtime provenance and public installer-data regressions; no hardware."""
from pathlib import Path
import hashlib,json,shutil,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import source_runtime as runtime
import build_public_image as image
import fm1_package as package
import audit_source_runtime as audit

class RuntimeSourceTests(unittest.TestCase):
    def test_complete_unmodified_source_and_notices(self):
        m=runtime.verify()
        self.assertEqual(len(m['units']),49)
        self.assertTrue(all(x['modified'] is False for x in m['files']))
        for name in ('newlib/COPYING.NEWLIB','compiler-rt/LICENSE.TXT','compiler-rt/CREDITS.TXT'):
            self.assertIn(name,{x['path'] for x in m['files']})

    def test_tampered_source_or_notice_refused_before_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'runtime';shutil.copytree(runtime.SOURCE,root)
            p=root/'compiler-rt/LICENSE.TXT';p.write_bytes(p.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'Runtime source changed'):runtime.verify(root)

    def test_manifest_cannot_escape_source_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'runtime';shutil.copytree(runtime.SOURCE,root)
            p=root/'PROVENANCE.json';m=json.loads(p.read_text());m['files'][0]['path']='../outside.c';p.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'unsafe runtime source'):runtime.verify(root)

    def test_non_elf_and_truncated_object_refused(self):
        for raw in (b'',bytes(52),b'\x7fELF\x01\x01\x01'+bytes(45)):
            with self.assertRaises(ValueError):audit.object_contract(raw)

    def test_public_data_has_no_private_dump_dependency(self):
        with patch.object(package,'citrine_flash_reference',side_effect=AssertionError('private dump accessed')), \
             patch.object(package,'sdk_file',side_effect=AssertionError('vendor SDK accessed')):
            raw=image.application_region(bytes.fromhex('04818000')+bytes(32))
        decoded,layout=package.app_layout(raw,package.TEST01_APP_SLOT)
        self.assertEqual(decoded[0x120:0x124],bytes.fromhex('04818000'))
        self.assertEqual(raw[-32:],b'\xff'*32)
        self.assertEqual(layout['eq_sha256'],'697b4fd0a82dae4a80f83180101a61de7d9e1fc951188e671350b18403c97007')
        checked=b''.join(raw[a:b] for a,b in ((4,32),(36,0x120),(0x8de3c,0x8efe0)))
        self.assertEqual(hashlib.sha256(checked).hexdigest(),image.LAYOUT_SHA)

    def test_public_resource_tampering_refused(self):
        with patch.object(image,'PARAMETERS_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'resource changed'):image.resources()

    def test_unsafe_application_refused(self):
        for value in (b'',b'wrong entry',bytes(package.TEST01_APP_SLOT+1)):
            with self.assertRaisesRegex(ValueError,'Application size or entry'):image.application_region(value)

if __name__=='__main__':unittest.main()
