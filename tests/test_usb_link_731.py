"""Exact-unit admission and interface isolation, without opening hardware."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_package as p
import fm1_flash_transport as t
import unit_endpoints as u
import fm1_native_bridge_v25 as b

class LinkTests(unittest.TestCase):
    def test_exact_unit_origin_and_template(self):
        for template,prefix in [(p.TEST01_TEMPLATE,'INSTALLED_730'),(p.CITRINE_TEMPLATE,'INSTALLED_CITRINE_730')]:
            digest=getattr(p,prefix+'_APP_SHA256')
            with patch.object(p,'_installed_reference') as verify:
                r=p.transition_profile(p.LINK_PRODUCT,template,bytes.fromhex(digest))
                self.assertEqual(r['origin_identity'],'FM-1_730')
                self.assertEqual(verify.call_args.args[-1],template)
                r.update(product=p.LINK_PRODUCT,template=template)
                self.assertEqual(t.update_identities(type('Package',(),{'report':r})()),('FM-1_730','ota-FM-1_731','FM-1_731'))
            other=p.INSTALLED_730_APP_SHA256 if template==p.CITRINE_TEMPLATE else p.INSTALLED_CITRINE_730_APP_SHA256
            for loader in (b'',bytes.fromhex(other),bytes.fromhex(digest)*2,bytes.fromhex(digest+other)):
                with self.assertRaises(ValueError):p.transition_profile(p.LINK_PRODUCT,template,loader)

    def test_same_names_select_only_exact_physical_port(self):
        a='PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(4)#USB(3)';z=a[:-2]+'4)'
        rows={'inputs':[dict(id=7,name='FMER Test01',location_paths=[a],interface_sha256='a'),dict(id=9,name='FMER Test01',location_paths=[z],interface_sha256='z')],
              'outputs':[dict(id=11,name='FMER Test01',location_paths=[z],interface_sha256='z'),dict(id=12,name='FMER Test01',location_paths=[a],interface_sha256='a')]}
        chosen=u.filter_location(rows,a);self.assertEqual(chosen['inputs'][0]['id'],7);self.assertEqual(chosen['outputs'][0]['id'],12)
        with self.assertRaises(t.UpdateError):t.select_pair(rows)
        rows['outputs'][1]['interface_sha256']='z'
        with self.assertRaises(ValueError):u.filter_location(rows,a)

    def test_no_match_never_falls_back(self):
        a='PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(4)#USB(3)'
        self.assertEqual(u.filter_location({'inputs':[],'outputs':[]},a),{'inputs':[],'outputs':[]})
        for bad in ('','FMER Test01','PCIROOT(0)*',a+';anything'):
            with self.assertRaises(ValueError):u.filter_location({'inputs':[],'outputs':[]},bad)

    def test_status_extent(self):
        data=b.native.PREFIX+bytes([33])+b'1 1 6 0 68 0 1 0 0 0 24 8 4 2 0 5 3'+bytes([247])
        self.assertEqual(b.parse_usb_link(data)['rx_events'],24)
        with self.assertRaises(ValueError):b.parse_usb_link(data.replace(b'1 1 6',b'1 1 8'))

if __name__=='__main__':unittest.main()
