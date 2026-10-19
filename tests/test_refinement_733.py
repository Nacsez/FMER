"""Finite unit origins for the native11 release; no hardware access."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_package as p
import fm1_flash_transport as t

class RefinementAdmission(unittest.TestCase):
    def test_exact_unit_only(self):
        for template,prefix,other_prefix in ((p.TEST01_TEMPLATE,'INSTALLED_731','INSTALLED_CITRINE_731'),(p.CITRINE_TEMPLATE,'INSTALLED_CITRINE_731','INSTALLED_731')):
            digest=bytes.fromhex(getattr(p,prefix+'_APP_SHA256'))
            other=bytes.fromhex(getattr(p,other_prefix+'_APP_SHA256'))
            with patch.object(p,'_installed_reference') as verify:
                result=p.transition_profile(p.REFINEMENT_PRODUCT,template,digest)
                self.assertEqual(verify.call_args.args[-1],template)
                result.update(product=p.REFINEMENT_PRODUCT,template=template)
                self.assertEqual(t.update_identities(type('Package',(),{'report':result})()),('FM-1_731','ota-FM-1_733','FM-1_733'))
                wrong=dict(result,origin_app_sha256=getattr(p,other_prefix+'_APP_SHA256'))
                with self.assertRaises(t.UpdateError):t.update_identities(type('Package',(),{'report':wrong})())
            for loader in (b'',other,digest*2,digest+other,bytes(32)):
                with self.assertRaises(ValueError):p.transition_profile(p.REFINEMENT_PRODUCT,template,loader)

if __name__=='__main__':unittest.main()
