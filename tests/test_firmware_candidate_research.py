# SPDX-License-Identifier: GPL-3.0-only
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_package as package
import inspect_firmware_candidate as research
import probe_community_dx7 as probe
import release_firmware as release


class CandidateResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=release.bundled(release.PROFILE)
        cls.sha=hashlib.sha256(cls.raw).hexdigest()

    def test_inspection_is_never_installation_admission(self):
        result=research.inspect(self.raw,self.sha)
        self.assertEqual(result['product'],'FM-1_734')
        self.assertEqual(result['application_slot_bytes'],580892)
        self.assertEqual(result['flash_extent'],0x93000)
        self.assertFalse(result['installable'])
        self.assertFalse(result['hardware_access'])
        self.assertFalse(result['updater_executed'])

    def test_pin_and_size_refusals(self):
        for raw,sha in [(self.raw,'0'*64),(self.raw,self.sha.upper()),(b'bad',self.sha),(bytes(2*1024*1024+1),self.sha)]:
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):research.inspect(raw,sha)

    def test_corrupt_payload_refused_even_with_its_new_hash(self):
        raw=bytearray(self.raw);raw[-1]^=1;raw=bytes(raw)
        with self.assertRaisesRegex(ValueError,'checksum'):research.inspect(raw,hashlib.sha256(raw).hexdigest())

    def test_corrupt_directory_refused(self):
        raw=bytearray(self.raw);raw[90]^=1;raw=bytes(raw)
        with self.assertRaises(ValueError):research.inspect(raw,hashlib.sha256(raw).hexdigest())

    def test_repacked_corrupt_application_refused(self):
        _,_,files=package.decode_package(self.raw)
        flash=bytearray(files['flash.bin']['payload']);flash[0x4300]^=1
        raw=package.ufw(bytes(flash),files['ota.bin']['payload'],'FM-1_734')
        with self.assertRaisesRegex(ValueError,'checksum'):research.inspect(raw,hashlib.sha256(raw).hexdigest())

    def test_unreviewed_upstream_javascript_is_never_executed(self):
        for raw in (b'process.exit(0)',b'const FM6 = (() => {});',b''):
            with self.assertRaisesRegex(ValueError,'Unreviewed'):probe.excerpt(raw)


if __name__=='__main__':unittest.main()
