import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import build_fm1_candidate as build


class Fm1BuildTests(unittest.TestCase):
    def test_709_build_includes_factory_presets_and_native_state_provenance(self):
        self.assertEqual(build.WIRE_IDENTITY, "FM-1_734")
        sources = build.local_source_files()
        headers = build.local_header_files()
        self.assertIn(build.ROOT / "core/factory_presets.cpp", sources)
        self.assertIn(build.ROOT / "core/factory_presets.hpp", headers)
        self.assertIn(build.ROOT / "firmware/fm1/native_state.h", headers)
        self.assertIn(build.ROOT / "firmware/fm1/preset_store.h", headers)
        self.assertIn(build.ROOT / "firmware/fm1/onboard_store.h", headers)
        self.assertIn(build.ROOT / "firmware/fm1/memory_layout.h", headers)
        self.assertIn(build.ROOT / "third_party/msfa/src/sin.h", headers)
        self.assertIn(build.ROOT / "third_party/msfa/src/fm_op_kernel.h", headers)
        self.assertEqual(len(sources), len(set(sources)))
        self.assertEqual(len(headers), len(set(headers)))
        self.assertTrue(all(path.is_file() for path in sources + headers))

    def test_hot_dsp_uses_speed_optimization_without_fast_math(self):
        for name in ("core/synth.cpp", "core/effects.cpp", "core/performance.cpp", "firmware/fm1/dsp_adapter.cpp", "third_party/msfa/src/fm_core.cc"):
            self.assertEqual(build.optimization_for_source(name), "-O2")
        for name in ("firmware/fm1/board.c", "core/patch.cpp", "firmware/crt0.S"):
            self.assertEqual(build.optimization_for_source(name), "-Oz")

    def test_regions_accept_expected_xip_ram_and_pool(self):
        build.validate_regions([
            {"name": ".text", "address": build.XIP[0], "size": 1024, "load_address": build.XIP[0]},
            {"name": ".data", "address": 0x1C08000, "size": 32, "load_address": build.XIP[0] + 1024},
            {"name": ".pool", "address": 0x1C20000, "size": 288 * 1024}], build.XIP[0])

    def test_pool_cannot_cross_stack_guard(self):
        with self.assertRaises(ValueError):
            build.validate_regions([{"name": ".pool", "address": 0x1C20000, "size": 0x54001}], build.XIP[0])

    def test_workspace_fits_between_fixed_arena_and_stack_guard(self):
        build.validate_regions([
            {"name": ".pool", "address": 0x1C20000, "size": 288 * 1024},
            {"name": ".workspace", "address": 0x1C68000, "size": 48 * 1024}], build.XIP[0])

    def test_arena_and_workspace_cannot_borrow_each_others_or_stack_memory(self):
        for section in [
            {"name": ".pool", "address": 0x1C20000, "size": 288 * 1024 + 16},
            {"name": ".workspace", "address": 0x1C67FF0, "size": 32},
            {"name": ".workspace", "address": 0x1C68000, "size": 48 * 1024 + 16}]:
            with self.subTest(section=section), self.assertRaises(ValueError):
                build.validate_regions([section], build.XIP[0])

    def test_noinit_cannot_reach_boot_identity_and_vector_area(self):
        with self.assertRaises(ValueError):
            build.validate_regions([{"name": ".noinit", "address": 0x1C7C000, "size": 0x3D51}], build.XIP[0])

    def test_overlap_unexpected_section_and_wrong_entry_refused(self):
        for sections, entry in [
            ([{"name": ".bss", "address": 0x1C08000, "size": 64},
              {"name": ".data", "address": 0x1C08020, "size": 64}], build.XIP[0]),
            ([{"name": ".init_array", "address": build.XIP[0], "size": 4}], build.XIP[0]),
            ([], build.XIP[0] + 4)]:
            with self.assertRaises(ValueError):
                build.validate_regions(sections, entry)

    def test_ram_payload_requires_xip_load_address(self):
        with self.assertRaises(ValueError):
            build.validate_regions([{"name": ".data", "address": 0x1C08000, "size": 32,
                                     "load_address": 0x1C08000}], build.XIP[0])

    def test_load_overlap_and_misalignment_refused(self):
        for load in [build.XIP[0] + 16, build.XIP[0] + 33]:
            with self.assertRaises(ValueError):
                build.validate_regions([
                    {"name": ".text", "address": build.XIP[0], "size": 32, "load_address": build.XIP[0]},
                    {"name": ".data", "address": 0x1C08000, "size": 16, "load_address": load}], build.XIP[0])

    def test_usb_descriptor_length_is_byte_count_and_round_trips(self):
        values = [int(value) for value in build.usb_descriptor("FMER Test01").strip("{}").split(", ")]
        self.assertEqual(values[:2], [24, 3])
        self.assertEqual(bytes(values[2:]).decode("utf-16-le"), "FMER Test01")
        with self.assertRaises(ValueError):
            build.usb_descriptor("A" * 127)

    def test_usb_patch_preserves_unrelated_code_and_loader_descriptor(self):
        source = (b"/* retained license */\nstatic const uint8_t STR1[] = {4, 3, 'X', 0};\n"
                  b"#ifdef FELUCCA_LOADER\nstatic const uint8_t STR2[] = {4, 3, 'L', 0};\n#else\n"
                  b"static const uint8_t STR2[] = {16, 3, 'F', 0, 'e', 0, 'l', 0, 'u', 0, 'c', 0, 'c', 0, 'a', 0};\n#endif\n"
                  b"    if (cin == 0xFu && (st == 0xF8u || st == 0xFAu || st == 0xFBu || st == 0xFCu)) {\n    }\n")
        with mock.patch.object(build, "USB_SHA256", hashlib.sha256(source).hexdigest()):
            changed = build.brand_usb(source).decode()
        self.assertIn("/* retained license */", changed)
        self.assertIn("static const uint8_t STR2[] = {4, 3, 'L', 0};", changed)
        self.assertIn(build.usb_descriptor("FMER"), changed)
        self.assertIn(build.usb_descriptor("FMER Test01"), changed)
        self.assertIn('cin == 3u && st == 0xF2u',changed)
        self.assertIn('st == 0xFEu || st == 0xFFu',changed)

    def test_unpinned_usb_and_upstream_metadata_refused(self):
        with self.assertRaises(ValueError):
            build.brand_usb(b"altered")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "tree.json").write_text("{}")
            with self.assertRaises(ValueError):
                build.verify_upstream(root / "source")

    def test_existing_output_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "report.json").write_text("previous evidence")
            with self.assertRaises(FileExistsError):
                build.build_candidate(root, root, root, root)
            self.assertEqual((root / "report.json").read_text(), "previous evidence")

    def test_non_target_and_truncated_elf_refused(self):
        for data in [b"", b"MZ" + bytes(100), b"\x7fELF\x01\x01\x01" + bytes(45)]:
            with self.assertRaises(ValueError):
                build.inspect_elf(data)


if __name__ == "__main__":
    unittest.main()
