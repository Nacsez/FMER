import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fm1_rom_entry as entry


class RomEntryTests(unittest.TestCase):
    def run_entry(self, status, journal=None):
        session = Mock()
        session.loader_control.return_value = status
        session.close.return_value = []
        package = Mock(report={"product": "FM-1_701", "runtime_preflight_qualified": True, "loader_image_bytes": 11112})
        with patch.object(entry.update, "find_session", return_value=session):
            entry.enter(Mock(), package, journal or Mock())
        return session

    def test_reference_mismatch_can_enter_readback_without_stage2(self):
        session = self.run_entry({"state": 0, "error": 0, "app_dirty": True, "match_count": 1,
                                  "record_address": 0xE7F00, "loader_length": 11112})
        session._send.assert_called_once_with(bytes.fromhex("F0 22 24 35 7D F7"), "documented_mask_rom_entry")
        session.begin_stage.assert_not_called()

    def test_busy_or_failed_loader_cannot_reset(self):
        for state, error in [(2, 0), (4, -7), (4, -15)]:
            session = Mock()
            session.loader_control.return_value = {"state": state, "error": error, "app_dirty": True,
                "match_count": 1, "record_address": 0xE7F00, "loader_length": 11112}
            session.close.return_value = []
            package = Mock(report={"product": "FM-1_701", "runtime_preflight_qualified": True, "loader_image_bytes": 11112})
            with patch.object(entry.update, "find_session", return_value=session), self.assertRaises(entry.update.UpdateError):
                entry.enter(Mock(), package, Mock())
            session._send.assert_not_called()

    def test_failed_intent_log_prevents_reset(self):
        session = Mock()
        session.loader_control.return_value = {"state": 0, "error": 0, "app_dirty": True,
            "match_count": 1, "record_address": 0xE7F00, "loader_length": 11112}
        session.close.return_value = []
        package = Mock(report={"product": "FM-1_701", "runtime_preflight_qualified": True, "loader_image_bytes": 11112})
        journal = Mock()
        journal.record.side_effect = OSError("disk full")
        with patch.object(entry.update, "find_session", return_value=session), self.assertRaises(OSError):
            entry.enter(Mock(), package, journal)
        session._send.assert_not_called()
        session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
