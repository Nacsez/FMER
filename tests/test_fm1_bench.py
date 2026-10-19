import sys
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from fm1_bench import QUERY, parse_diagnostics, short_message, set_controls, run_matrix, EXTRA_FIELDS, query
import fm1_bench as tool


class BenchDiagnostics(unittest.TestCase):
    def test_707_identity_reaches_existing_diagnostic_matrix_and_release_workflows(self):
        for action in ("diagnostics","matrix","release-checks"):
            with tempfile.TemporaryDirectory() as directory:
                journal=MagicMock();journal.directory=Path(directory)
                session=MagicMock();session.close.return_value=[]
                before={"active_voices":0,"audio_paused":0,"dsp_init_failed":0}
                with patch.object(tool.transport,"Journal",return_value=journal),patch.object(tool.bridge,"WinMM"), \
                     patch.object(tool.transport,"find_session",return_value=session) as find, \
                     patch.object(tool,"query",return_value=before),patch.object(tool,"run_matrix") as matrix, \
                     patch.object(tool,"run_releases") as releases,patch("sys.stdout",new=io.StringIO()):
                    self.assertEqual(tool.main([action,"--firmware","707"]),0)
                self.assertEqual(find.call_args.args[1],"FM-1_707")
                self.assertEqual(matrix.call_count,int(action=="matrix"))
                self.assertEqual(releases.call_count,int(action=="release-checks"))
                self.assertTrue(json.loads((Path(directory)/"report.json").read_text())["success"])
                session.close.assert_called_once()

    def test_missing_response_reports_timeout_without_inventing_diagnostics(self):
        session,journal=MagicMock(),MagicMock()
        session.read.return_value=None
        with self.assertRaisesRegex(TimeoutError,"diagnostic response timed out"):
            query(session,journal,2)
        journal.record.assert_not_called()

    def frame(self, body="100 1600 0 0 0 2 250512 8740884 0 0 0"):
        return QUERY[:7]+body.encode("ascii")+b"\xF7"

    def test_actual_field_contract(self):
        values=parse_diagnostics(self.frame())
        self.assertEqual(values["startup_heap_bytes"],250512)
        self.assertEqual(values["active_voices"],2)
        self.assertEqual(values["maximum_render_us"],1600)

    def test_malformed_diagnostics_rejected(self):
        invalid=[None,b"",self.frame()[:-1],b"\xF0\x7Dother\xF7",
                 self.frame("-1 "+"0 "*9+"0"),self.frame("0 "*11),
                 self.frame("4294967296 "+"0 "*9+"0"),
                 self.frame("0 0 0 0 0 13 0 0 0 0 0"),
                 self.frame("0 0 0 0 0 0 0 0 2 0 0")]
        for frame in invalid:
            with self.subTest(frame=frame), self.assertRaises((ValueError,UnicodeDecodeError)):
                parse_diagnostics(frame)

    def test_cleanup_survives_failed_logging(self):
        session,journal=MagicMock(),MagicMock()
        journal.record.side_effect=OSError("disk unavailable")
        for message in ((0x8F,60,0),(0xBF,120,0)):
            with self.assertRaisesRegex(RuntimeError,"cleanup sent"):
                short_message(session,journal,*message)
        self.assertEqual(session.api.checked.call_count,2)

    def test_new_note_requires_durable_log(self):
        session,journal=MagicMock(),MagicMock()
        journal.record.side_effect=OSError("disk unavailable")
        with self.assertRaises(OSError): short_message(session,journal,0x9F,60,32)
        session.api.checked.assert_not_called()

    def test_extended_real_time_diagnostics_and_unknown_schemas(self):
        base="100 1600 0 0 0 4 250512 8740884 0 0 0"
        extra="1 0 2 2200 30 5 200 512 3 4 2 0 120 1450 1500 20 500 0 4 4 4 1 20 1400 2900 2905"
        frame=QUERY[:6]+b"\x02"+(base+" "+extra).encode()+b"\xF7"
        noise=frame.replace(b"1 0 2 2200",b"1 0 4 2200")
        for identity in ("FM-1_726","FM-1_727","FM-1_728","FM-1_729","FM-1_730"):
            self.assertEqual(parse_diagnostics(noise,identity=identity)["va_wave"],4)
        with self.assertRaises(ValueError):parse_diagnostics(noise,identity="FM-1_725")
        data=parse_diagnostics(frame)
        self.assertEqual(data["engine"],1)
        self.assertEqual(data["voice_limit"],4)
        self.assertEqual(data["maximum_dsp_us"],1450)
        self.assertEqual(data["lcd_strips"],20)
        for bad in (frame[:6]+b"\x03"+frame[7:],frame.replace(b"1 0 2 2200",b"1 0 4 2200"),
                    frame.replace(b"200 512 3 4",b"200 512 3 0")):
            with self.assertRaises(ValueError): parse_diagnostics(bad)

    def test_control_bounds_fail_before_any_message(self):
        session,journal=MagicMock(),MagicMock()
        for kwargs in ({"engine":2},{"engine":True},{"engine":0,"wave":4},
                       {"engine":0,"budget":0},{"engine":0,"cutoff_step":19},
                       {"engine":0,"attack_step":13}):
            with self.assertRaises(ValueError): set_controls(session,journal,**kwargs)
        session._send.assert_not_called()

    def test_zero_velocity_release_survives_failed_journal(self):
        session,journal=MagicMock(),MagicMock()
        journal.record.side_effect=OSError("disk unavailable")
        with self.assertRaisesRegex(RuntimeError,"cleanup sent"):
            short_message(session,journal,0x9F,60,0)
        self.assertEqual(session.api.checked.call_count,1)

    def test_matrix_failure_keeps_original_error_and_attempts_all_cleanup(self):
        session,journal=MagicMock(),MagicMock()
        result={}
        with patch("fm1_bench.set_controls",side_effect=[{"overruns":0},RuntimeError("restore failed")]), \
             patch("fm1_bench.reset_peaks",side_effect=RuntimeError("original profiling failure")), \
             patch("fm1_bench.cleanup_notes") as cleanup:
            with self.assertRaisesRegex(RuntimeError,"original profiling failure"):
                run_matrix(session,journal,result)
        cleanup.assert_called_once()
        self.assertEqual(len(cleanup.call_args.args[2]),8)
        self.assertEqual(result["matrix_cleanup_errors"],["restore failed"])


if __name__ == "__main__": unittest.main()
