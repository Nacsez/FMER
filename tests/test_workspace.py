"""Regression coverage for delivery integrity and acceptance traceability failures."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import verify_workspace as vw


class IntegrityTests(unittest.TestCase):
    def test_changed_file_and_rewritten_manifest_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "evidence.txt"
            payload.write_bytes(b"original")
            manifest = root / "MANIFEST.sha256"
            manifest.write_text(f"{vw.sha256(payload)}  evidence.txt\n", encoding="utf-8")
            identity = vw.sha256(manifest)
            self.assertEqual(vw.verify_manifest(root, identity, 1), 1)
            payload.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                vw.verify_manifest(root, identity, 1)
            manifest.write_text(f"{vw.sha256(payload)}  evidence.txt\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity changed"):
                vw.verify_manifest(root, identity, 1)

    def test_traversal_absolute_and_windows_paths_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in ("../outside", "/outside", "C:/outside", "C:outside", "sub\\outside"):
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Unsafe"):
                    vw.local_path(Path(directory), path)

    def test_duplicate_manifest_entries_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "item").write_bytes(b"fixture")
            line = f"{vw.sha256(root / 'item')}  item\n"
            (root / "MANIFEST.sha256").write_text(line * 2, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                vw.verify_manifest(root, vw.sha256(root / "MANIFEST.sha256"), 2)

    def test_unlisted_code_cannot_pass_the_execution_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "original.txt").write_bytes(b"original")
            manifest = root / "MANIFEST.sha256"
            manifest.write_text(f"{vw.sha256(root / 'original.txt')}  original.txt\n", encoding="utf-8")
            identity = vw.sha256(manifest)
            (root / "acquired").mkdir()
            (root / "acquired/report.json").write_text("[]", encoding="utf-8")
            self.assertEqual(vw.verify_manifest(root, identity, 1), 1)
            (root / "tests").mkdir()
            (root / "tests/test_extra.py").write_text("raise RuntimeError('unverified')\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unlisted corpus paths.*test_extra.py"):
                vw.verify_manifest(root, identity, 1)


class TraceabilityTests(unittest.TestCase):
    def test_dependency_bytes_are_pinned_before_build_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence").mkdir()
            (root / "vendor").mkdir()
            license_file = root / "vendor/COPYING"
            license_file.write_bytes(b"license fixture")
            lock = {"schema_version":1, "commit":"a"*40, "vendor_root":"vendor",
                    "files":[{"path":"COPYING","local_sha256":vw.sha256(license_file)}]}
            (root / "evidence/msfa-source.json").write_text(json.dumps(lock),encoding="utf-8")
            self.assertEqual(vw.verify_dependencies(root),1)
            license_file.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError,"dependency hash mismatch"):
                vw.verify_dependencies(root)

    def write_rows(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, vw.ACCEPTANCE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def test_missing_and_changed_acceptance_cannot_pass(self):
        rows = [dict(id=ident, area="test", requirement="Title | Pass: Original",
                     milestone="M1", mode="host", status="planned", evidence="Not implemented")
                for ident in ("P01", "UI01", "PL01")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acceptance.csv"
            original = {"P01": "Title | Pass: Original"}
            self.write_rows(path, rows)
            self.assertEqual(vw.verify_acceptance(path, original), 3)
            self.write_rows(path, rows[1:])
            with self.assertRaisesRegex(ValueError, "missing"):
                vw.verify_acceptance(path, original)
            rows[0]["requirement"] = "Weakened requirement"
            self.write_rows(path, rows)
            with self.assertRaisesRegex(ValueError, "requirement changed"):
                vw.verify_acceptance(path, original)

    def test_broken_local_link_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = root / "README.md"
            doc.write_text("[Missing](missing.md)\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Broken local link"):
                vw.verify_links(root, [doc])
            (root / "missing.md").write_text("# Present\n", encoding="utf-8")
            self.assertEqual(vw.verify_links(root, [doc]), 1)


if __name__ == "__main__":
    unittest.main()
