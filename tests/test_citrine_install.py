"""Finite stock admission and named endpoint regressions; no hardware access."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_package as pkg
import fm1_flash_transport as transport
import build_fm1_candidate as build
from tests.test_fm1_flash_transport import qualified_package, RecordJournal


class CitrineInstallTests(unittest.TestCase):
    def test_unique_stock_origin_and_required_backup(self):
        stock=bytes.fromhex(pkg.CITRINE_APP_SHA256)
        other=bytes.fromhex(pkg.INSTALLED_729_RELEASE2_APP_SHA256)
        with patch.object(pkg,'citrine_flash_reference',return_value=b'checked') as backup:
            profile=pkg.transition_profile(pkg.SONG_PRODUCT,pkg.CITRINE_TEMPLATE,stock)
            self.assertEqual(profile['origin_identity'],'FM-1_015')
            self.assertIsNone(profile['origin_package_sha256']);backup.assert_called_once()
            for loader in (None,b'',stock*2,stock+other,other,bytearray(stock)):
                with self.subTest(loader=loader),self.assertRaises(ValueError):
                    pkg.transition_profile(pkg.SONG_PRODUCT,pkg.CITRINE_TEMPLATE,loader)
            with self.assertRaises(ValueError):pkg.transition_profile(pkg.DEFAULTS_PRODUCT,pkg.CITRINE_TEMPLATE,stock)
        with patch.object(pkg,'citrine_flash_reference',side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):pkg.transition_profile(pkg.SONG_PRODUCT,pkg.CITRINE_TEMPLATE,stock)

    def test_stock_transport_refuses_wrong_evidence_before_opening_device(self):
        old=qualified_package()
        report=dict(old.report,product='FM-1_730',origin_identity='FM-1_015',loader_identity='ota-FM-1_730',
                    origin_app_sha256=pkg.CITRINE_APP_SHA256,origin_package_sha256=None,template=pkg.CITRINE_TEMPLATE,
                    reference_backup_sha256=pkg.CITRINE_DUMP_SHA256,reference_backup_report_sha256=pkg.CITRINE_REPORT_SHA256)
        make=lambda r:transport.QualifiedPackage(old.image,r,old.app_begin,old.app_end)
        self.assertEqual(transport.update_identities(make(report)),('FM-1_015','ota-FM-1_730','FM-1_730'))
        for key,value in [('origin_identity','FM-1_729'),('origin_app_sha256','0'*64),
                          ('reference_backup_sha256',pkg.TEST01_DUMP_SHA256),('reference_backup_report_sha256',pkg.TEST01_REPORT_SHA256),
                          ('template',pkg.TEST01_TEMPLATE),('origin_package_sha256',pkg.INSTALLED_729_RELEASE2_PACKAGE_SHA256)]:
            with self.subTest(key=key),patch.object(transport,'find_session') as find,self.assertRaises(transport.UpdateError):
                transport.perform_update(Mock(),make(dict(report,**{key:value})),RecordJournal())
            find.assert_not_called()

    def test_two_named_units_never_auto_select(self):
        endpoints={d:[dict(id=0,name='FMER Test01'),dict(id=1,name='FMER Citrine')] for d in ('inputs','outputs')}
        with self.assertRaises(transport.UpdateError):transport.select_pair(endpoints)
        for d in endpoints:endpoints[d]=endpoints[d][1:]
        a,b=transport.select_pair(endpoints)
        self.assertEqual(a['name'],b['name']);self.assertEqual(a['name'],'FMER Citrine')
        self.assertFalse(transport.PORT_NAME.fullmatch('Unrelated Citrine Synth'))

    def test_branding_changes_only_product_descriptor(self):
        source=(build.FELUCCA/'firmware/src/usb.c').read_bytes()
        original=build.brand_usb(source)
        named=build.brand_usb(source,'FMER Citrine')
        self.assertEqual(named,original.replace(build.usb_descriptor('FMER Test01').encode(),build.usb_descriptor('FMER Citrine').encode()))
        with self.assertRaises(ValueError):build.brand_usb(source,'Unreviewed')

if __name__=='__main__':unittest.main()
