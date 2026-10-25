"""Refuse stale or mismatched draft assets before any network operation."""
from pathlib import Path
import hashlib,io,json,sys,tempfile,unittest,zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import stage_github_release as stage

class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'firmware/releases').mkdir(parents=True)
        self.record={'id':'current','filename':'current.fwsc'};self.catalog={'schema':1,'releases':[self.record]}
        (self.root/'firmware/releases/catalog.json').write_text(json.dumps(self.catalog))
        (self.root/'FMER SPLASH.png').write_bytes(b'original artwork')
        self.zip=self.root/'companion.zip';self.proof=self.root/'rehearsal.json'
        self.files={'tools/companion.py':b'pass\n','host/index.htm':b'<p>FMER</p>',
                    'firmware/releases/catalog.json':json.dumps(self.catalog).encode(),
                    'firmware/releases/current.fwsc':b'qualified image'}
    def make(self,source_change=False,omit=False):
        source=io.BytesIO()
        with zipfile.ZipFile(source,'w') as z:
            z.writestr('tools/companion.py',b'different' if source_change else self.files['tools/companion.py'])
            z.writestr('host/index.htm',self.files['host/index.htm'])
            z.writestr('FMER SPLASH.png',b'original artwork')
        self.files['Corresponding Source.zip']=source.getvalue()
        manifest={'files':{n:hashlib.sha256(v).hexdigest() for n,v in self.files.items()}}
        with zipfile.ZipFile(self.zip,'w') as z:
            for n,v in self.files.items():
                if not (omit and n=='host/index.htm'):z.writestr('App/'+n,v)
            z.writestr('App/manifest.json',json.dumps(manifest))
        self.proof.write_text(json.dumps({'status':'passed','zip_sha256':stage.sha(self.zip)}))
    def check(self):
        with patch.object(stage,'R',self.root),patch.object(stage.release,'catalog',return_value=[self.record]),patch.object(stage.release,'bundled',return_value=b'qualified image'):
            return stage.verify_companion(self.zip,self.proof)
    def test_verified_set_accepted(self):
        self.make();self.assertEqual(self.check(),self.record)
    def test_explicit_profile_does_not_choose_first_catalog_entry(self):
        self.make()
        with patch.object(stage,'R',self.root),patch.object(stage.release,'catalog',return_value=[{'id':'historical'},self.record]),patch.object(stage.release,'bundled',return_value=b'qualified image') as bundled:
            self.assertEqual(stage.verify_companion(self.zip,self.proof,'current'),self.record)
            bundled.assert_called_once_with('current')
            with self.assertRaisesRegex(ValueError,'not in the catalog'):stage.verify_companion(self.zip,self.proof,'unknown')
    def test_stale_rehearsal_rejected(self):
        self.make();self.proof.write_text(json.dumps({'status':'passed','zip_sha256':'0'*64}))
        with self.assertRaisesRegex(ValueError,'exact Companion ZIP'):self.check()
    def test_missing_runtime_file_rejected(self):
        self.make(omit=True)
        with self.assertRaisesRegex(ValueError,'closure'):self.check()
    def test_corresponding_source_mismatch_rejected(self):
        self.make(source_change=True)
        with self.assertRaisesRegex(ValueError,'Runtime/source mismatch'):self.check()
    def test_different_standalone_firmware_rejected(self):
        self.files['firmware/releases/current.fwsc']=b'other firmware';self.make()
        with self.assertRaisesRegex(ValueError,'firmware differ'):self.check()
    def test_release_revision_comes_from_delivered_package(self):
        for revision in (5,6):
            with zipfile.ZipFile(self.zip,'w') as z:
                z.writestr('App/manifest.json',json.dumps({'companion_revision':revision}))
            self.assertEqual(stage.companion_revision(self.zip),revision)
    def test_missing_or_invalid_release_revision_rejected(self):
        for revision in (None,True,0,'5'):
            with zipfile.ZipFile(self.zip,'w') as z:
                z.writestr('App/manifest.json',json.dumps({'companion_revision':revision}))
            with self.assertRaisesRegex(ValueError,'revision required'):stage.companion_revision(self.zip)

if __name__=='__main__':unittest.main()
