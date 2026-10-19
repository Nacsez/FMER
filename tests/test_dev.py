"""Regression checks for honest evidence reporting and host diagnostic scope."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("fmer_dev", Path(__file__).resolve().parents[1] / "tools/dev.py")
dev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dev)


class RunEvidenceTests(unittest.TestCase):
    def test_source_identity_changes_with_uncommitted_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "host").mkdir()
            source = root / "host/main.cpp"
            source.write_bytes(b"before")
            before = dev.source_identity(root)
            source.write_bytes(b"after")
            after = dev.source_identity(root)
            self.assertEqual(before["git"], {"status": "not-a-git-worktree", "head": None})
            self.assertEqual(after["sha256"]["host/main.cpp"], hashlib.sha256(b"after").hexdigest())
            self.assertNotEqual(before["sha256"], after["sha256"])

    def test_nonzero_command_is_logged_and_fails_summary(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            run = dev.Run("regression", Path(temporary))
            result = run.execute("failure", [sys.executable, "-B", "-c",
                                 "import sys; print('evidence'); print('cause', file=sys.stderr); sys.exit(7)"])
            self.assertEqual(result.returncode, 7)
            self.assertEqual(run.finish(), 1)
            summary = json.loads((run.directory / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["steps"][0]["returncode"], 7)
            log = Path(summary["steps"][0]["log"]).read_text(encoding="utf-8")
            self.assertIn("evidence", log)
            self.assertIn("cause", log)
            latest = json.loads((Path(temporary) / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["summary"], str(run.directory / "summary.json"))

    def test_missing_executable_is_failure_evidence(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            run = dev.Run("regression", Path(temporary))
            result = run.execute("missing", [str(Path(temporary) / "absent-program")])
            self.assertEqual(result.returncode, 127)
            self.assertEqual(run.finish(), 1)

    def test_success_after_failure_cannot_hide_failure(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            run = dev.Run("regression", Path(temporary))
            run.record("failed", False, "Earlier check failed")
            run.record("passed", True, "Later check passed")
            self.assertEqual(run.finish(), 1)

    def test_empty_run_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            run = dev.Run("regression", Path(temporary))
            self.assertEqual(run.finish(), 1)


class CorpusExecutionGateTests(unittest.TestCase):
    def test_failed_integrity_gate_prevents_corpus_execution_but_runs_local_tests(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temporary)
            corpus = root / "corpus"
            for directory in (root / "tools", root / "tests", corpus / "tools", corpus / "tests"):
                directory.mkdir(parents=True, exist_ok=True)
            (root / "tools/verify_workspace.py").write_text(
                "raise SystemExit(1)\n", encoding="utf-8")
            # These stand in for modified shipped scripts. Executing any one is a regression.
            marker_script = "from pathlib import Path\nPath('CORPUS_EXECUTED').touch()\n"
            for relative in ("tools/check_manifest.py", "tools/fetch_sources.py", "tests/test_changed.py"):
                (corpus / relative).write_text(marker_script, encoding="utf-8")
            (root / "tests/test_local.py").write_text(
                "from pathlib import Path\nimport unittest\n"
                "class LocalTests(unittest.TestCase):\n"
                "    def test_local(self):\n"
                "        Path('LOCAL_TEST_EXECUTED').touch()\n", encoding="utf-8")
            with patch.object(dev, "ROOT", root), patch.object(dev, "CORPUS", corpus):
                run = dev.Run("check", root / "artifacts")
                dev.check(run)
                self.assertEqual(run.finish(), 1)
            self.assertFalse((corpus / "CORPUS_EXECUTED").exists())
            self.assertTrue((root / "LOCAL_TEST_EXECUTED").exists())
            statuses = {step["name"]: step["status"] for step in run.summary["steps"]}
            self.assertEqual(statuses["workspace-contract"], "failed")
            self.assertEqual(statuses["workspace-tests"], "passed")
            for name in ("corpus-manifest", "corpus-tests", "acquisition-dry-run"):
                self.assertEqual(statuses[name], "skipped")


class DiagnosticContractTests(unittest.TestCase):
    def setUp(self):
        self.valid = {
            "schema_version": 1, "project": "FMER", "component": "fmer_host",
            "implementation": "host-musical-prototype", "project_version": "0.2.0",
            "build_id": "test", "compiler_id": "TestCompiler", "compiler_version": "1",
            "build_configuration": "Debug", "cpp_standard": 17, "pointer_bits": 64,
            "hardware_access": False, "audio_engine": True,
        }

    def test_valid_contract(self):
        dev.validate_host_diagnostics(self.valid)

    def test_wrong_hardware_or_audio_scope_is_rejected(self):
        for field, value in (("hardware_access", True), ("audio_engine", False)):
            with self.subTest(field=field):
                altered = dict(self.valid, **{field: value})
                with self.assertRaises(ValueError):
                    dev.validate_host_diagnostics(altered)

    def test_boolean_integer_confusion_is_rejected(self):
        for field, value in (("schema_version", True), ("hardware_access", 0)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                dev.validate_host_diagnostics(dict(self.valid, **{field: value}))

    def test_missing_build_identity_is_rejected(self):
        for field in ("project_version", "build_id", "compiler_id", "compiler_version"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                altered = copy.copy(self.valid)
                del altered[field]
                dev.validate_host_diagnostics(altered)

    def test_wrong_scope_and_nonobject_are_rejected(self):
        for invalid in ([], dict(self.valid, implementation="synthesizer")):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                dev.validate_host_diagnostics(invalid)


if __name__ == "__main__":
    unittest.main()
