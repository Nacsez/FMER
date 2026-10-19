import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("target_probe", Path(__file__).resolve().parents[1] / "tools/target_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class TargetProbeTests(unittest.TestCase):
    def test_target_elf_identity_rejects_wrong_architecture_or_type(self):
        data = bytearray(52)
        data[:7] = b"\x7fELF\x01\x01\x01"
        struct.pack_into("<HHII", data, 16, 1, 0xF1, 1, 0)
        self.assertEqual(probe.elf_identity(data, 1)["machine"], 0xF1)
        with self.assertRaises(ValueError):
            probe.elf_identity(data, 2)
        struct.pack_into("<H", data, 18, 0x3E)
        with self.assertRaises(ValueError):
            probe.elf_identity(data, 1)

    def test_truncated_and_big_endian_elf_refused(self):
        for data in [b"\x7fELF", b"\x7fELF\x01\x02\x01" + bytes(45), bytes(52)]:
            with self.assertRaises(ValueError):
                probe.elf_identity(data, 1)

    def test_changed_missing_and_escaping_inputs_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "compiler").write_bytes(b"approved")
            files = [{"path": "compiler", "sha256": hashlib.sha256(b"approved").hexdigest()}]
            probe.verify_files(root, files)
            (root / "compiler").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                probe.verify_files(root, files)
            for bad in ["missing", "../outside"]:
                with self.assertRaises(ValueError):
                    probe.verify_files(root, [{"path": bad, "sha256": "0" * 64}])

    def test_process_failure_retains_exact_command_exit_and_streams(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "command.json"
            command = [sys.executable, "-c", "import sys;print('evidence');print('cause',file=sys.stderr);sys.exit(7)"]
            record = probe.run_logged(command, log)
            self.assertEqual(record["exit_code"], 7)
            self.assertEqual(record["command"], command)
            self.assertIn("evidence", record["stdout"])
            self.assertIn("cause", record["stderr"])
            self.assertEqual(json.loads(log.read_text()), record)

    def test_missing_executable_preserves_failure_not_empty_success(self):
        with tempfile.TemporaryDirectory() as folder:
            record = probe.run_logged([str(Path(folder) / "missing.exe")], Path(folder) / "log.json")
            self.assertIsNone(record["exit_code"])
            self.assertTrue(record["stderr"])

    def test_existing_output_refused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sentinel = root / "report.json"
            sentinel.write_text("previous evidence")
            with self.assertRaises(FileExistsError):
                probe.build_probe(root, root, root, {})
            self.assertEqual(sentinel.read_text(), "previous evidence")


if __name__ == "__main__":
    unittest.main()
