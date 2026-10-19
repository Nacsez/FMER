"""Offline synthetic comparisons; optional public-package fixtures are not device dumps."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fm1_flash_compare as compare
import fm1_package as package


def extend(reference):
    return reference + b"\xff" * (0x100000 - len(reference))


def encrypt_app(plain, key=package.KEY):
    result = bytearray(plain)
    package.sfc(result, 0, len(result), 0, key)
    return bytes(result)


class SyntheticComparisons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sdk = {"uboot.boot": b"SPL" * 100, "cfg_tool.bin": bytes(383),
                   "cfg/eq_cfg_hw.bin": bytes(range(256)) * 2 + b"synthetic EQ"}
        cls.app = bytes.fromhex("04818000") + b"original synthetic app" * 32
        with patch.object(package, "sdk_file", side_effect=cls.sdk.__getitem__):
            cls.reference = package._format_flash_image(cls.app, package.KEY)
        cls.data = extend(cls.reference)
        cls.plain, cls.layout = compare.decode_app(cls.reference[0x4000:], package.KEY)

    def setUp(self):
        self.flash_pin = patch.object(compare, "PUBLISHED_FLASH_SHA256", compare.sha(self.reference))
        self.app_pin = patch.object(compare.stock, "APP_SHA", compare.sha(self.reference[0x4000:]))
        self.flash_pin.start()
        self.app_pin.start()
        self.addCleanup(self.flash_pin.stop)
        self.addCleanup(self.app_pin.stop)

    def run_compare(self, data):
        return compare.compare(bytes(data), compare.sha(data), self.reference)

    def test_equal_extended_reference_has_no_differences(self):
        report = self.run_compare(self.data)
        self.assertEqual(report["chip_key"], 0x980F)
        self.assertTrue(report["chip_keys_match"])
        self.assertTrue(report["layout_matches"])
        self.assertEqual(report["raw_app"]["changed_bytes"], 0)
        self.assertEqual(report["protected_head"]["changed_bytes"], 0)
        self.assertEqual(report["private_tail_sha256"], compare.sha(self.data[0x93000:]))
        self.assertTrue(all(r["changed_bytes"] == 0 for r in report["plaintext_regions"].values()))
        self.assertFalse(report["device_access"])
        self.assertFalse(report["writes"])

    def test_modified_padding_is_isolated_without_crc_failure(self):
        data = bytearray(self.data)
        data[0x92FFF] ^= 1
        report = self.run_compare(data)
        for name, region in report["plaintext_regions"].items():
            self.assertEqual(region["changed_bytes"], int(name == "tail_padding"))
        self.assertEqual(report["raw_tail_padding"]["first_difference"], 0x92FFF)
        self.assertEqual(report["raw_tail_padding"]["changed_sectors"], [0x92000])

    def test_private_tail_is_hashed_without_exposing_contents(self):
        data = bytearray(self.data)
        data[0xFF123] = 12
        report = self.run_compare(data)
        self.assertEqual(report["raw_app"]["changed_bytes"], 0)
        self.assertEqual(report["private_tail_sha256"], compare.sha(data[0x93000:]))
        self.assertNotIn("private_tail", report)

    def test_wrong_size_or_requested_hash_is_rejected(self):
        for data, digest in ((self.data[:-1], compare.sha(self.data[:-1])),
                             (self.data + b"x", compare.sha(self.data + b"x")),
                             (self.data, "0" * 64)):
            with self.subTest(size=len(data)), self.assertRaisesRegex(ValueError, "Dump size"):
                compare.compare(data, digest, self.reference)

    def test_reference_head_is_also_hash_pinned(self):
        reference = bytearray(self.reference)
        reference[0x3000] ^= 1
        with self.assertRaisesRegex(ValueError, "Published reference"):
            compare.compare(self.data, compare.sha(self.data), reference)

    def test_corrupt_executable_crc_is_rejected(self):
        data = bytearray(self.data)
        data[0x10000] ^= 1
        with self.assertRaisesRegex(ValueError, "data CRC"):
            self.run_compare(data)

    def test_corrupt_calibration_crc_is_rejected(self):
        data = bytearray(self.data)
        data[0x4000 + self.layout["eq_start"] + 4] ^= 1
        with self.assertRaisesRegex(ValueError, "Calibration data CRC"):
            self.run_compare(data)

    def test_corrupt_chip_key_record_is_rejected(self):
        header = bytearray(self.data[64:96])
        package.enc(header, 0, len(header))
        start = package.jlfs_header(header)[2]
        data = bytearray(self.data)
        data[start] ^= 1
        with self.assertRaisesRegex(ValueError, "Chip-key record CRC"):
            self.run_compare(data)

    def test_valid_changed_calibration_is_reported_separately(self):
        plain = bytearray(self.plain)
        cfg_at, cfg_end = self.layout["cfg_start"], self.layout["cfg_end"]
        eq_start, eq_end = self.layout["eq_start"], self.layout["eq_end"]
        plain[eq_start + 4] ^= 1
        struct.pack_into("<H", plain, cfg_at + 34, package.crc16(plain[eq_start:eq_end]))
        struct.pack_into("<H", plain, cfg_at + 32, package.crc16(plain[cfg_at+34:cfg_at+64]))
        struct.pack_into("<H", plain, cfg_at + 2, package.crc16(plain[cfg_at+32:cfg_end]))
        struct.pack_into("<H", plain, cfg_at, package.crc16(plain[cfg_at+2:cfg_at+32]))
        data = self.data[:0x4000] + encrypt_app(plain) + self.data[0x93000:]
        report = self.run_compare(data)
        self.assertGreater(report["plaintext_regions"]["calibration"]["changed_bytes"], 0)
        self.assertNotEqual(report["actual_layout"]["eq_sha256"], report["reference_layout"]["eq_sha256"])
        self.assertEqual(report["plaintext_regions"]["app_payload"]["changed_bytes"], 0)

    def test_different_keys_do_not_imply_raw_padding_changes(self):
        with patch.object(package, "sdk_file", side_effect=self.sdk.__getitem__):
            data = extend(package._format_flash_image(self.app, 0x1234))
        report = self.run_compare(data)
        self.assertFalse(report["chip_keys_match"])
        self.assertEqual(report["plaintext_regions"]["app_payload"]["changed_bytes"], 0)
        self.assertEqual(report["plaintext_regions"]["calibration"]["changed_bytes"], 0)
        self.assertEqual(report["raw_tail_padding"]["changed_bytes"], 0)
        self.assertGreater(report["plaintext_regions"]["tail_padding"]["changed_bytes"], 0)
        self.assertFalse(report["plaintext_regions"]["tail_padding"]["same_key_comparison"])

    def test_invalid_calibration_extent_is_rejected_even_with_header_crc(self):
        plain = bytearray(self.plain)
        cfg_at = self.layout["cfg_start"]
        struct.pack_into("<I", plain, cfg_at + 8, 0xFFFFFFFF)
        struct.pack_into("<H", plain, cfg_at, package.crc16(plain[cfg_at+2:cfg_at+32]))
        with self.assertRaisesRegex(ValueError, "Calibration extents"):
            compare.decode_app(encrypt_app(plain), package.KEY)

    def test_valid_shorter_stock_slot_compares_relocated_files(self):
        with patch.object(package, "sdk_file", side_effect=self.sdk.__getitem__), \
                patch.object(package, "APP_SLOT", package.APP_SLOT - 672):
            variant = extend(package._format_flash_image(self.app, package.KEY))
        report = self.run_compare(variant)
        self.assertEqual(report["version"], 2)
        self.assertFalse(report["layout_matches"])
        self.assertEqual(report["actual_layout"]["app_bytes"], self.layout["app_bytes"] - 672)
        for name in ("cfg_tool", "calibration", "eq_payload"):
            region = report["region_comparisons"][name]
            self.assertTrue(region["byte_equal"])
            self.assertEqual(region["reference_start"] - region["actual_start"], 672)
            self.assertNotIn(name, report["plaintext_regions"])
        payload = report["region_comparisons"]["app_payload"]
        self.assertEqual(payload["reference_unpaired_bytes"], 672)
        self.assertEqual(payload["common_changed_bytes"], 0)
        self.assertTrue(report["raw_tail_padding"]["actual_all_ff"])
        self.assertTrue(report["raw_tail_padding"]["reference_all_ff"])
        self.assertEqual(report["raw_tail_padding"]["actual_unpaired_bytes"], 672)

    def test_shifted_calibration_change_is_not_hidden_by_layout_difference(self):
        changed_sdk = dict(self.sdk, **{"cfg/eq_cfg_hw.bin": b"changed EQ" + self.sdk["cfg/eq_cfg_hw.bin"][10:]})
        with patch.object(package, "sdk_file", side_effect=changed_sdk.__getitem__), \
                patch.object(package, "APP_SLOT", package.APP_SLOT - 672):
            variant = extend(package._format_flash_image(self.app, package.KEY))
        report = self.run_compare(variant)
        self.assertFalse(report["layout_matches"])
        self.assertFalse(report["region_comparisons"]["eq_payload"]["byte_equal"])
        self.assertGreater(report["region_comparisons"]["eq_payload"]["common_changed_bytes"], 0)

    @staticmethod
    def refresh_header_and_area(plain, header):
        struct.pack_into("<H", plain, header, package.crc16(plain[header+2:header+32]))
        area_end = int.from_bytes(plain[8:12], "little")
        struct.pack_into("<H", plain, 2, package.crc16(plain[32:area_end]))
        struct.pack_into("<H", plain, 0, package.crc16(plain[2:32]))

    def test_app_extent_cannot_overlap_directory_or_leave_region(self):
        for address, size in ((0x100, self.layout["app_bytes"]), (0x120, 0xFFFFFFFF), (0x120, 3)):
            plain = bytearray(self.plain)
            struct.pack_into("<II", plain, 36, address, size)
            self.refresh_header_and_area(plain, 32)
            with self.assertRaisesRegex(ValueError, "payload extent"):
                compare.decode_app(encrypt_app(plain), package.KEY)

    def test_cfg_tool_overlap_and_crc_cannot_hide_in_valid_area_crc(self):
        plain = bytearray(self.plain)
        struct.pack_into("<I", plain, 68, self.layout["app_end"] - 1)
        self.refresh_header_and_area(plain, 64)
        with self.assertRaisesRegex(ValueError, "Configuration tool extent"):
            compare.decode_app(encrypt_app(plain), package.KEY)
        plain = bytearray(self.plain)
        plain[self.layout["cfg_tool_start"]] ^= 1
        self.refresh_header_and_area(plain, 64)
        with self.assertRaisesRegex(ValueError, "Configuration tool data CRC"):
            compare.decode_app(encrypt_app(plain), package.KEY)

    def test_flash_region_descriptor_requires_known_boundaries_and_valid_crc(self):
        plain = bytearray(self.plain)
        struct.pack_into("<I", plain, 100, 0x92000)
        self.refresh_header_and_area(plain, 96)
        with self.assertRaisesRegex(ValueError, "flash-region descriptor"):
            compare.decode_app(encrypt_app(plain), package.KEY)
        plain = bytearray(self.plain)
        plain[96] ^= 1
        self.refresh_header_and_area(plain, 0)
        with self.assertRaisesRegex(ValueError, "header CRC"):
            compare.decode_app(encrypt_app(plain), package.KEY)


class PublishedReferenceComparisons(unittest.TestCase):
    """Use only the optional pinned publisher download, padded synthetically to 1 MiB."""
    @classmethod
    def setUpClass(cls):
        path = compare.stock.CACHE / "FM-1.fwsc"
        if not path.is_file():
            raise unittest.SkipTest("Optional private publisher reference not acquired; synthetic coverage still runs")
        cls.reference = compare.stock.decode_reference(path.read_bytes())["stock-v15-flash.bin"]
        cls.data = extend(cls.reference)

    def test_public_reference_extended_with_ff_is_not_device_evidence(self):
        report = compare.compare(self.data, compare.sha(self.data), self.reference)
        self.assertTrue(report["layout_matches"])
        self.assertEqual(report["raw_app"]["actual_sha256"], compare.stock.APP_SHA)
        self.assertEqual(report["raw_app"]["changed_bytes"], 0)
        self.assertEqual(report["raw_tail_padding"]["bytes"], 556)
        self.assertEqual(report["actual_layout"]["eq_sha256"], compare.stock.EQ_SHA)
        self.assertFalse(report["device_access"])

    def test_public_padding_change_isolated(self):
        data = bytearray(self.data)
        data[0x92FFF] ^= 0x80
        report = compare.compare(data, compare.sha(data), self.reference)
        self.assertEqual(report["raw_tail_padding"]["changed_bytes"], 1)
        self.assertEqual(report["plaintext_regions"]["app_payload"]["changed_bytes"], 0)
        self.assertEqual(report["plaintext_regions"]["calibration"]["changed_bytes"], 0)

    def test_public_executable_corruption_fails_crc(self):
        data = bytearray(self.data)
        data[0x4120] ^= 1
        with self.assertRaisesRegex(ValueError, "data CRC"):
            compare.compare(data, compare.sha(data), self.reference)


if __name__ == "__main__":
    unittest.main()
