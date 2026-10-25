"""Next-release package/Companion contracts; never open physical MIDI ports."""
from pathlib import Path
import base64
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import release_firmware as release
import fm1_package as package
import compatible_firmware as compatible
import fm1_flash_transport as transport
import stage_release_package as stage
from companion_jobs import Jobs


class HeadContract(unittest.TestCase):
    def test_only_generated_public_key_record_changes_and_decodes_independently(self):
        old = release.distribution_head()
        new = release.distribution_head(release.METADATA_FORMAT)
        self.assertEqual(len(new), 16384)
        self.assertEqual(old[:14544], new[:14544])
        self.assertEqual(old[14578:], new[14578:])
        blob = new[14544:14576]
        total = sum(blob[:16]) & 255
        threshold = 0xaa if total >= 0xe0 else 0x55 if total <= 0x10 else total
        decoded = sum(1 << i for i in range(16) if (blob[16+i] ^ blob[15-i]) < threshold)
        self.assertEqual(decoded, 0x980f)
        self.assertEqual(int.from_bytes(new[14576:14578], 'little'), package.crc16(blob))

    def test_corrupt_metadata_or_boot_bytes_cannot_be_a_recognized_head(self):
        for name in (release.LEGACY_FORMAT, release.METADATA_FORMAT):
            self.assertEqual(release.head_format(release.distribution_head(name)), name)
            for offset in (0, 32, 160, 14544, 14576, 16383):
                head = bytearray(release.distribution_head(name)); head[offset] ^= 1
                with self.subTest(format=name, offset=offset), self.assertRaises(ValueError):
                    release.head_format(head)
        with self.assertRaises(ValueError): release.distribution_head('unknown')


class CompanionPackageContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = release.ROOT/'firmware/releases/fmer734-compatible-r2.fwsc'
        if not path.is_file(): raise unittest.SkipTest('Source-only checkout: release binary absent')
        cls.old = path.read_bytes()
        cls.new = stage.convert(cls.old)

    def test_conversion_preserves_application_updater_size_and_valid_checksums(self):
        _, _, before = package.decode_package(self.old)
        _, _, after = package.decode_package(self.new)
        self.assertEqual(len(self.old), len(self.new))
        self.assertEqual(before['flash.bin']['payload'][0x4000:], after['flash.bin']['payload'][0x4000:])
        self.assertEqual(before['ota.bin']['payload'], after['ota.bin']['payload'])
        self.assertEqual(self.new, package.ufw(after['flash.bin']['payload'], after['ota.bin']['payload'], 'FM-1_734'))
        with self.assertRaises(ValueError): stage.convert(self.new)

    def test_companion_inspects_both_packages_without_device_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = Mock()
            jobs = Jobs(device, Path(tmp))
            for raw, expected in ((self.old, release.LEGACY_FORMAT), (self.new, release.METADATA_FORMAT)):
                report = jobs.inspect(dict(action='inspect', raw=base64.b64encode(raw).decode()))
                self.assertIn('inspection', report)
                self.assertEqual(report['package_format'], expected)
                self.assertEqual(report['app_write_range'], [0x4000, 0x93000])
                self.assertFalse(report['head_written'])
                path = Path(tmp)/'candidate.fwsc'; path.write_bytes(raw)
                q = transport.qualify_package(path, release.digest(raw), stage.LOADER_SHA)
                self.assertEqual(transport.update_identities(q), ('compatible-FM-1', release.LOADER, 'FM-1_734'))
            self.assertEqual(device.mock_calls, [])

    def test_new_package_is_preferred_and_old_one_remains_available(self):
        records = release.available()
        self.assertEqual(records[0]['id'], release.NEXT_PROFILE)
        self.assertTrue(all(r['available'] for r in records))
        self.assertIn(release.PROFILE, {r['id'] for r in records})

    def test_every_catalog_tool_requirement_is_in_portable_runtime(self):
        import build_companion_portable as portable
        shipped = {p.relative_to(release.ROOT).as_posix() for p in portable.runtime_modules()}
        for record in release.catalog():
            for item in record['source_files']:
                if item['path'].startswith('tools/'):
                    self.assertIn(item['path'], shipped, 'Build-only pin would disable firmware in extracted Companion')

    def test_valid_outer_checksums_do_not_allow_modified_metadata_or_code_extent(self):
        identity, _, files = package.decode_package(self.new)
        for offset in (160, 14544, 14576, 16383, 0x4010):
            flash = bytearray(files['flash.bin']['payload']); flash[offset] ^= 1
            raw = package.ufw(flash, files['ota.bin']['payload'], identity)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                compatible.inspect_bytes(raw)

    def test_release_profile_cannot_mislabel_package_format(self):
        records = release.catalog()
        changed = [dict(r, package_format=release.LEGACY_FORMAT) if r['id']==release.METADATA_PROFILE else r for r in records]
        with patch.object(release, 'catalog', return_value=changed), self.assertRaises(ValueError):
            release.inspect_bytes(self.new)

    def test_compatible_application_path_recognizes_both_exact_headers(self):
        for raw in (self.old, self.new):
            report = compatible.inspect_bytes(raw)
            self.assertEqual(report['app_write_range'], [0x4000, 0x93000])
            self.assertFalse(report['head_written'])
            self.assertEqual(report['loader_sha256'], stage.LOADER_SHA)


if __name__ == '__main__': unittest.main()
