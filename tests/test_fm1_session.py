import hashlib
import errno
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fm1_session as capture


def frame(op, values):
    return capture.PREFIX + bytes([op]) + " ".join(map(str, values)).encode() + b"\xf7"


def trace(*, newest=1, oldest=1, uptime=100, events=None):
    events = [(1, 99, 8, 704, 0, 0)] if events is None else events
    return frame(5, [1, uptime, newest, oldest, len(events), *(x for row in events for x in row)])


class MemoryJournal:
    def __init__(self):
        self.events = []
        self.saved = []

    def record(self, event, **values):
        self.events.append({"event": event, **values})

    def checkpoint(self, state):
        self.saved.append(dict(state))

    def status(self, **values):
        self.latest_status = values


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


def diagnostic_frame():
    result = dict.fromkeys(capture.fm1_bench.FIELDS + capture.fm1_bench.EXTRA_FIELDS, 0)
    result.update(cutoff_hz=20000, voice_limit=4, release_ms=50)
    return frame(2, result.values())


class FakeSession:
    def __init__(self, *, timeout=False, cleanup=None, identity=capture.IDENTITY):
        self.sent, self.closed = [], 0
        self.timeout, self.cleanup = timeout, cleanup or []
        self.identity = identity
        from collections import deque
        self.short_received=deque();self.short_overflow=0

    def _send(self, packet, purpose):
        self.sent.append(packet)

    def read(self, timeout):
        if self.timeout:
            return None
        packet = self.sent[-1]
        if packet[6] == 5:
            cursor = sum(value << (7 * i) for i, value in enumerate(packet[7:12]))
            return trace(events=[] if cursor else None)
        if packet[6] == 2:
            return diagnostic_frame()
        if packet[6] == 6:
            start = packet[7] + 128 * packet[8]
            count = capture.parameter_count(self.identity)
            if self.identity in capture.SYNC_IDENTITIES:
                from tests.test_fm1_native_v7 import fixture
                return frame(6,[start,min(24,count-start),*fixture()['controls'][start:start+24]])
            return frame(6, [start, min(24, count - start), *([0] * min(24, count - start))])
        if packet[6] == 8:
            return frame(8, [2,100,*([0]*25),0,0,8,1,0] if self.identity in capture.ONBOARD_IDENTITIES else [1,100,*([0]*25)])
        if packet[6] == 11:
            start = packet[7] + 128 * packet[8]
            return frame(11, [7, 4, start, min(16, 64-start), *([128, 100, 75] * min(16, 64-start))])
        if packet[6] == 12:
            return frame(12, [1, 100, 1, 99, 0, 3, 0, 0, 0, 0, *([0] * 30)])
        if packet[6] == 13:
            return frame(13, [2 if self.identity in capture.ONBOARD_IDENTITIES else 1,7,0,0,0,0,0,0,0])
        if packet[6] == 21:
            if self.identity in capture.PROJECT_IDENTITIES:
                return frame(21,[4 if self.identity in (capture.DEFAULTS_IDENTITY,capture.SONG_IDENTITY,capture.LINK_IDENTITY,capture.REFINEMENT_IDENTITY,capture.NAVIGATION_IDENTITY) else 3,1,0,0,0,0,0,0,0,65535,0,0,73,0,0,0x7944953e,0,4000 if self.identity in (capture.SONG_IDENTITY,capture.LINK_IDENTITY,capture.REFINEMENT_IDENTITY,capture.NAVIGATION_IDENTITY) else 3728,3,65535,0,16]+([0] if self.identity in (capture.DEFAULTS_IDENTITY,capture.SONG_IDENTITY,capture.LINK_IDENTITY,capture.REFINEMENT_IDENTITY,capture.NAVIGATION_IDENTITY) else []))
            return frame(21,[2 if self.identity in (capture.BANK_IDENTITY,*capture.MIDI_IDENTITIES) else 1,1,0,0,0,0,0,0,0,65535,0,0,73,0,0,0x7944953e,0,2176])
        if packet[6]==27 and self.identity in ('FM-1_715','FM-1_716','FM-1_717','FM-1_718','FM-1_719','FM-1_720','FM-1_721','FM-1_722','FM-1_723','FM-1_724','FM-1_725','FM-1_726','FM-1_727','FM-1_728','FM-1_729','FM-1_730','FM-1_731','FM-1_733','FM-1_734'):
            return frame(27,[1,0,0,0,0,0,0])
        if packet[6]==25:
            return frame(25,[1,1,1,1,0,0,1,0,0,1,0,0,0,0,0,0,0,0,0,919,0,0,0,0,1,0])
        if packet[6]==31 and self.identity in (capture.PERFORMANCE_IDENTITY,*capture.SYNC_IDENTITIES):
            return frame(31,[1,100,1,1,1,1,1,64,*([0]*12)])
        if packet[6]==33 and self.identity in (capture.LINK_IDENTITY,capture.REFINEMENT_IDENTITY,capture.NAVIGATION_IDENTITY):
            return frame(33,[1,*([0]*16)])
        raise AssertionError("Non-read-only request")

    def close(self):
        self.closed += 1
        return self.cleanup


class ProtocolTests(unittest.TestCase):
    def test_led_schema_exact_fields_bounds_pitch_subsets_and_matrix_overlap(self):
        good = [1, 123, 7, 120, 8, 6, 16383, (1 << 27)-1, 255, 12,
                1, 0, 0, 1 << 31, 1, 0, 0, 0, *([2] * 9 + [4, 4]), *([4] * 9 + [8, 8])]
        result = capture.parse_leds(frame(12, good))
        self.assertEqual(result["active_pitches"], [0, 127])
        self.assertEqual(result["gated_pitches"], [0])
        self.assertEqual(result["flag_labels"], list(capture.LED_FLAG_NAMES))
        for index, value in ((0, 2), (1, -1), (1, 1 << 32), (2, 0), (4, 9), (5, 7), (6, 1 << 14),
                             (7, 1 << 27), (8, 256), (9, 13), (9, 1), (14, 2), (18, 1), (18, 32),
                             (27, 2), (38, 2), (29, 2)):
            wrong = good.copy(); wrong[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                capture.parse_leds(frame(12, wrong))
        for fields in (good[:-1], good + [0]):
            with self.assertRaises(ValueError): capture.parse_leds(frame(12, fields))

    def test_led_allowlist_is706_or707_and_empty_request_only(self):
        session = object.__new__(capture.ReadOnlySession)
        packet = capture.PREFIX + bytes([12, 247])
        with patch.object(capture.transport.MidiSession, "_send") as send:
            for identity in capture.SUPPORTED_IDENTITIES:
                session.expected_identity = session.verified_identity = identity
                if identity in capture.LED_IDENTITIES: session._send(packet, "test")
                else:
                    with self.assertRaises(capture.CaptureError): session._send(packet, "test")
            with self.assertRaises(capture.CaptureError): session._send(packet[:-1] + bytes([0, 247]), "test")
            self.assertEqual(send.call_count, len(capture.LED_IDENTITIES))

    def test_pattern_framing_extent_and_canonical_steps(self):
        good = [0xFFFFFFFF, 64, 63, 1, 128, 127, 100]
        self.assertEqual(capture.pattern_request(63), capture.PREFIX + bytes([11, 63, 0, 247]))
        self.assertEqual(capture.parse_pattern(frame(11, good), 63)["steps"], [[128, 127, 100]])
        for start in (-1, 64, True, 1.0):
            with self.assertRaises(ValueError): capture.pattern_request(start)
        for index, value in ((0, -1), (0, 0), (0, 1 << 32), (1, 0), (1, 65), (2, 62), (3, 0),
                             (4, 129), (5, 0), (5, 128), (6, 0), (6, 101)):
            wrong = good.copy(); wrong[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                capture.parse_pattern(frame(11, wrong), 63)
        with self.assertRaises(ValueError): capture.parse_pattern(frame(11, good + [0]), 63)

    def test_pattern_allowlist_is_exact705_or706_only(self):
        session = object.__new__(capture.ReadOnlySession)
        with patch.object(capture.transport.MidiSession, "_send") as send:
            for identity in ("FM-1_704", "FM-1_705", "FM-1_706"):
                session.expected_identity = session.verified_identity = identity
                if identity in capture.PATTERN_IDENTITIES:
                    session._send(capture.pattern_request(0), "test")
                else:
                    with self.assertRaises(capture.CaptureError): session._send(capture.pattern_request(0), "test")
            for packet in (capture.PREFIX + bytes([11, 64, 0, 247]), capture.PREFIX + bytes([11, 0, 128, 247])):
                with self.assertRaises(capture.CaptureError): session._send(packet, "test")
            self.assertEqual(send.call_count, 2)

    def test_trace_cursor_unsigned32_five_septets(self):
        self.assertEqual(capture.trace_request(0), capture.PREFIX + bytes([5, 0, 0, 0, 0, 0, 247]))
        self.assertEqual(capture.trace_request(0xFFFFFFFF), capture.PREFIX + bytes([5, 127, 127, 127, 127, 15, 247]))
        for value in (-1, 1 << 32, 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError): capture.trace_request(value)

    def test_exact_trace_parser_signed_encoder_and_labels(self):
        batch = capture.parse_trace(trace(newest=2, events=[(1, 90, 1, 6, -3, 2), (2, 91, 3, 162, 2200, 9)]))
        self.assertEqual(batch["events"][0]["value"], -3)
        self.assertEqual(batch["events"][0]["kind_name"], "encoder")
        self.assertEqual(batch["events"][1]["parameter"], "cutoff_hz")
        self.assertEqual(capture.parse_trace(trace(newest=0, events=[]))["newest_seq"], 0)

    def test_invalid_trace_never_accepted(self):
        invalid = [b"", trace()[:-1], trace().replace(b"\x05", b"\x06", 1),
                   frame(5, [2, 0, 0, 1, 0]), frame(5, [1, 0, 0, 0, 0]),
                   frame(5, [1, 0, 257, 1, 0]), frame(5, [1, 1 << 32, 0, 1, 0]),
                   trace(events=[(1, 0, 11, 0, 0, 0)]), trace(events=[(1, 0, 1, 0, 1 << 31, 0)]),
                   trace(events=[(1, 0, 1, -1, 0, 0)]), trace(events=[(1, 0, 1, 0, 0, -1)]),
                   trace(newest=3, events=[(1, 0, 1, 0, 0, 0), (3, 0, 1, 0, 0, 0)]),
                   frame(5, [1, 0, 1, 1, 7]), trace().replace(b"100", b"+100"),
                   trace().replace(b"100", b"0100"), trace().replace(b"100", b"- 100")]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError): capture.parse_trace(value)

    def test_control_chunks_cover_full_registry_and_reserve_zeros(self):
        self.assertEqual(capture.controls_request(192), capture.PREFIX + bytes([6, 64, 1, 247]))
        self.assertEqual(capture.parse_controls(frame(6, [192, 1, 65535]), 192), [65535])
        for packet, expected in [(frame(6, [192, 1, -1]), 192), (frame(6, [192, 1, 65536]), 192),
                                 (frame(6, [192, 1, 0]), 191), (frame(6, [192, 0]), 192),
                                 (frame(6, [144, 24, 0, 1, *([0] * 22)]), 144)]:
            with self.subTest(packet=packet), self.assertRaises(ValueError): capture.parse_controls(packet, expected)
        for value in (-1, 193, True):
            with self.assertRaises(ValueError): capture.controls_request(value)

    def test_generated_note_direct_route_and_virtual_input_are_distinct(self):
        events = [(1, 1, 10, (4 << 8) | 60, 90, 0xFFFFFFFF),
                  (2, 1, 10, (5 << 8) | 64, 0, 128),
                  (3, 1, 4, 67, 70, (15 << 8) | 2),
                  (4, 1, 1, 2, -1, 0x80000000 | 4)]
        result = capture.parse_trace(trace(newest=4, events=events))["events"]
        self.assertEqual(result[0]["source_name"], "sequencer")
        self.assertEqual(result[0]["audio_frame_low32"], 0xFFFFFFFF)
        self.assertEqual(result[1]["source_name"], "arpeggiator")
        self.assertEqual((result[2]["source_name"], result[2]["channel"]), ("trs_midi", 15))
        self.assertTrue(result[3]["virtual_panel"])
        self.assertEqual(result[3]["panel_aux"], 4)
        for identifier, velocity in ((60, 40), ((4 << 8) | 128, 40), ((5 << 8) | 60, -1)):
            with self.assertRaises(ValueError): capture.parse_trace(trace(events=[(1, 1, 10, identifier, velocity, 0)]))

    def test_send_allowlist_cannot_send_writes_notes_reset_or_wrong_identity(self):
        session = object.__new__(capture.ReadOnlySession)
        session.verified_identity = capture.IDENTITY
        with patch.object(capture.transport.MidiSession, "_send") as send:
            for packet in (capture.device_protocol.IDENTITY_QUERY, capture.PREFIX + bytes([2, 247]),
                           capture.trace_request(0xFFFFFFFF), capture.controls_request(192), capture.PREFIX + bytes([8, 247])):
                session._send(packet, "test")
            self.assertEqual(send.call_count, 5)
            for packet in (capture.transport.UPGRADE, b"\x90\x3c\x40", capture.PREFIX + bytes([3, 247]),
                           capture.PREFIX + bytes([4, 247]), capture.PREFIX + bytes([5, 0, 0, 0, 0, 16, 247]),
                           capture.PREFIX + bytes([6, 65, 1, 247]), capture.PREFIX + bytes([6, 0, 128, 247])):
                with self.assertRaises(capture.CaptureError): session._send(packet, "test")
            session.verified_identity = "FM-1_703"
            with self.assertRaises(capture.CaptureError): session._send(capture.trace_request(0), "test")
            self.assertEqual(send.call_count, 5)

    def test_performance_input_metrics_exact27_fields_and_bounds(self):
        good = [1, 100, *([0] * 25)]
        self.assertEqual(capture.parse_performance(frame(8, good))["uptime_ms"], 100)
        for values in (good[:-1], good + [0], [2] + good[1:]):
            with self.assertRaises(ValueError): capture.parse_performance(frame(8, values))
        for index, value in ((1, -1), (2, 1 << 32), (11, 2), (13, 64), (20, 129), (21, 128), (22, 101), (25, 7)):
            wrong = good.copy(); wrong[index] = value
            with self.subTest(index=index), self.assertRaises(ValueError): capture.parse_performance(frame(8, wrong))


class CursorTests(unittest.TestCase):
    def test_gap_count_and_checkpoint_follow_durable_batch(self):
        journal = MemoryJournal(); cursor = capture.TraceCursor(journal)
        batch = capture.parse_trace(trace(newest=300, oldest=45, events=[(i, 1, 4, 60, 40, 0) for i in range(45, 51)]))
        self.assertTrue(cursor.accept(batch))
        self.assertEqual(cursor.cursor, 50)
        self.assertEqual(cursor.dropped, 44)
        self.assertEqual([e["event"] for e in journal.events], ["target_event_gap", "target_event_batch"])
        self.assertEqual(journal.saved[-1]["cursor"], 50)

    def test_reboot_and_wrap_create_epoch_and_requery_from_zero(self):
        for prior in ({"cursor": 9, "uptime_ms": 200, "epoch": 3}, {"cursor": 0, "uptime_ms": 0xFFFFFFFF, "epoch": 3}):
            journal = MemoryJournal(); cursor = capture.TraceCursor(journal, prior)
            self.assertTrue(cursor.accept(capture.parse_trace(trace())))
            self.assertEqual((cursor.cursor, cursor.epoch), (0, 4))
            self.assertEqual(journal.events[0]["event"], "target_epoch_changed")
            self.assertFalse(cursor.accept(capture.parse_trace(trace())))
            self.assertEqual(cursor.cursor, 1)

    def test_unrequested_omitted_or_duplicate_events_do_not_advance(self):
        for events in ([], [(2, 1, 4, 60, 40, 0)]):
            journal = MemoryJournal(); cursor = capture.TraceCursor(journal)
            with self.assertRaises(ValueError): cursor.accept(capture.parse_trace(trace(newest=2, events=events)))
            self.assertEqual(cursor.cursor, 0); self.assertEqual(journal.saved, [])

    def test_failed_journal_write_preserves_cursor(self):
        journal = MemoryJournal(); cursor = capture.TraceCursor(journal)
        journal.record = Mock(side_effect=OSError("disk failure"))
        with self.assertRaises(OSError): cursor.accept(capture.parse_trace(trace()))
        self.assertEqual(cursor.cursor, 0); self.assertEqual(journal.saved, [])


class DiskTests(unittest.TestCase):
    def test_checkpoint_cannot_resume_across_firmware_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = capture.DurableJournal(Path(directory) / "run", identity="FM-1_704")
            journal.checkpoint(dict(cursor=0, epoch=0, dropped_events=0))
            with self.assertRaisesRegex(ValueError, "identity"):
                capture.load_checkpoint(journal.directory)
            self.assertEqual(capture.load_checkpoint(journal.directory, identity="FM-1_704")["identity"], "FM-1_704")
            journal.close()

    def test_rotation_preserves_old_bytes_and_stops_at_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = capture.DurableJournal(Path(directory) / "run", segment_bytes=4096, segments=2)
            journal.record("data", data="x" * 3000)
            first = journal.paths[0].read_bytes()
            journal.record("data", data="y" * 3000)
            with self.assertRaises(capture.DiskBudgetReached): journal.record("data", data="z" * 3000)
            journal.close()
            self.assertEqual(len(journal.paths), 2)
            self.assertEqual(journal.paths[0].read_bytes(), first)
            self.assertLessEqual(sum(p.stat().st_size for p in journal.paths), 8192)
            with self.assertRaises(FileExistsError): capture.DurableJournal(Path(directory) / "run")

    def test_atomic_checkpoint_resume_validates_identity_and_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = capture.DurableJournal(Path(directory) / "run")
            state = {"cursor": 100, "epoch": 2, "uptime_ms": 123, "dropped_events": 7}
            journal.checkpoint(state)
            self.assertEqual(capture.load_checkpoint(journal.directory)["cursor"], 100)
            journal.checkpoint(dict(state, cursor=101))
            self.assertEqual(capture.load_checkpoint(journal.directory)["cursor"], 101)
            path = journal.directory / "checkpoint.json"
            for changes in ({"identity": "FM-1_703"}, {"cursor": 1 << 32}, {"epoch": -1}, {"uptime_ms": True}):
                path.write_text(json.dumps(dict(state, schema=1, identity=capture.IDENTITY) | changes))
                with self.assertRaises(ValueError): capture.load_checkpoint(journal.directory)
            journal.close()


class AtomicSidecarTests(unittest.TestCase):
    @staticmethod
    def denial(code):
        error=PermissionError(errno.EACCES,"simulated Windows publication denial")
        error.winerror=code
        return error

    def publish(self,journal,kind,value):
        if kind=='status':journal.status(phase=value)
        else:journal.checkpoint(dict(cursor=value,epoch=0,uptime_ms=1,dropped_events=0))

    def test_transient_windows_replace_keeps_old_and_complete_new_until_commit(self):
        for kind in ('status','checkpoint'):
            for code in (5,32,33):
                with self.subTest(kind=kind,code=code),tempfile.TemporaryDirectory() as directory:
                    journal=capture.DurableJournal(Path(directory)/'run')
                    try:
                        self.publish(journal,kind,1);destination=journal.directory/(kind+'.json');old=destination.read_bytes()
                        real_replace=capture.os.replace;attempts=[]
                        def replace(source,target):
                            attempts.append((source,target));self.assertEqual(destination.read_bytes(),old)
                            pending=json.loads(source.read_text());self.assertEqual(pending['phase' if kind=='status' else 'cursor'],2)
                            if len(attempts)<3:raise self.denial(code)
                            real_replace(source,target)
                        with patch.object(capture.os,'replace',side_effect=replace),patch.object(capture.time,'sleep') as sleep:
                            self.publish(journal,kind,2)
                        self.assertEqual(len(attempts),3);self.assertEqual([c.args[0] for c in sleep.call_args_list],[.02,.04])
                        self.assertEqual(journal.sidecar_publish_stats(),dict(retries=2,wait_ms=60))
                        self.assertEqual(json.loads(destination.read_text())['phase' if kind=='status' else 'cursor'],2)
                        self.assertFalse((journal.directory/(kind+'.next')).exists())
                        rows=[json.loads(line) for line in journal.paths[0].read_text().splitlines()]
                        self.assertEqual([row['event'] for row in rows],['sidecar_publish_retry','sidecar_publish_retry','sidecar_publish_recovered'])
                    finally:journal.close()

    def test_permanent_denial_is_bounded_and_preserves_both_durable_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=capture.DurableJournal(Path(directory)/'run')
            try:
                journal.status(phase='old');destination=journal.directory/'status.json';old=destination.read_bytes();failure=self.denial(5)
                with patch.object(capture.os,'replace',side_effect=failure) as replace,patch.object(capture.time,'sleep') as sleep:
                    with self.assertRaises(PermissionError) as raised:journal.status(phase='new')
                self.assertIs(raised.exception,failure);self.assertEqual(replace.call_count,6)
                self.assertEqual([c.args[0] for c in sleep.call_args_list],[.02,.04,.06,.08,.1])
                self.assertEqual(journal.sidecar_publish_stats(),dict(retries=5,wait_ms=300))
                self.assertEqual(destination.read_bytes(),old)
                self.assertEqual(json.loads((journal.directory/'status.next').read_text())['phase'],'new')
            finally:journal.close()

    def test_unrelated_replace_and_temporary_fsync_failures_are_not_retried(self):
        for error in (PermissionError(errno.EACCES,'non-Windows ACL'),OSError(errno.ENOSPC,'disk full'),FileNotFoundError('missing source')):
            with self.subTest(error=error),tempfile.TemporaryDirectory() as directory:
                journal=capture.DurableJournal(Path(directory)/'run')
                try:
                    with patch.object(capture.os,'replace',side_effect=error) as replace,patch.object(capture.time,'sleep') as sleep:
                        with self.assertRaises(OSError) as raised:journal.status(phase='new')
                    self.assertIs(raised.exception,error);self.assertEqual(replace.call_count,1);sleep.assert_not_called()
                    self.assertEqual(journal.sidecar_publish_stats(),dict(retries=0,wait_ms=0))
                finally:journal.close()
        with tempfile.TemporaryDirectory() as directory:
            journal=capture.DurableJournal(Path(directory)/'run')
            try:
                failure=OSError(errno.ENOSPC,'disk full while flushing new checkpoint')
                with patch.object(capture.os,'fsync',side_effect=failure),patch.object(capture.os,'replace') as replace,patch.object(capture.time,'sleep') as sleep:
                    with self.assertRaises(OSError) as raised:self.publish(journal,'checkpoint',2)
                self.assertIs(raised.exception,failure);replace.assert_not_called();sleep.assert_not_called()
            finally:journal.close()

    def test_final_status_can_recover_after_journal_stream_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=capture.DurableJournal(Path(directory)/'run');journal.close();real_replace=capture.os.replace;calls=[]
            def replace(source,target):
                calls.append(target)
                if len(calls)==1:raise self.denial(32)
                real_replace(source,target)
            with patch.object(capture.os,'replace',side_effect=replace),patch.object(capture.time,'sleep'):
                journal.status(phase='stopped')
            self.assertEqual(json.loads((journal.directory/'status.json').read_text())['phase'],'stopped')
            self.assertEqual(journal.sidecar_publish_stats(),dict(retries=1,wait_ms=20))

    @unittest.skipUnless(sys.platform=='win32','Windows file-sharing semantics')
    def test_actual_windows_reader_without_delete_sharing_then_release(self):
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        for kind in ('status','checkpoint'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                journal=capture.DurableJournal(Path(directory)/'run');handle=None
                try:
                    self.publish(journal,kind,1);destination=journal.directory/(kind+'.json');old=destination.read_bytes()
                    handle=kernel.CreateFileW(str(destination),0x80000000,3,None,3,0,None)
                    self.assertNotEqual(handle,ctypes.c_void_p(-1).value,ctypes.get_last_error())
                    def release_reader(delay):
                        nonlocal handle
                        self.assertEqual(delay,.02);self.assertEqual(destination.read_bytes(),old)
                        self.assertTrue(kernel.CloseHandle(handle));handle=None
                    with patch.object(capture.time,'sleep',side_effect=release_reader) as sleep:
                        self.publish(journal,kind,2)
                    sleep.assert_called_once_with(.02)
                    self.assertEqual(json.loads(destination.read_text())['phase' if kind=='status' else 'cursor'],2)
                    self.assertEqual(journal.sidecar_publish_stats(),dict(retries=1,wait_ms=20))
                finally:
                    if handle not in (None,ctypes.c_void_p(-1).value):kernel.CloseHandle(handle)
                    journal.close()


class Defaults729TraceTests(unittest.TestCase):
    def test_personal_default_events_require729_capability(self):
        raw=trace(newest=2,events=[(1,80,11,0,0,11),(2,90,11,0,0,12)])
        rows=capture.parse_trace(raw,maximum_storage_action=12,allow_native_timing=True)['events']
        self.assertEqual([r['action'] for r in rows],['save_fx_default','reset_fx_default'])
        for limit in (5,6,10):
            with self.assertRaises(ValueError):capture.parse_trace(raw,maximum_storage_action=limit)
        with self.assertRaises(ValueError):capture.parse_trace(trace(events=[(1,80,11,0,0,13)]),maximum_storage_action=12)


class Projects720Tests(unittest.TestCase):
    def test_native_load_timing_retains_apply_and_total_quiet_duration(self):
        raw=trace(newest=3,events=[(1,80,12,0,2194,2870),(2,90,12,14,0,500),(3,95,12,14,10,20)])
        rows=capture.parse_trace(raw,maximum_storage_action=10,allow_native_timing=True)['events']
        self.assertEqual((rows[0]['kind_name'],rows[0]['result_name'],rows[0]['apply_us'],rows[0]['quiet_us']),
                         ('native_load_timing','ok',2194,2870))
        self.assertEqual((rows[1]['result'],rows[1]['result_name'],rows[1]['apply_us'],rows[1]['quiet_us']),
                         (14,'stale',0,500))
        self.assertEqual((rows[2]['result'],rows[2]['apply_us'],rows[2]['quiet_us']),(14,10,20))
        # Legacy identity parsers must not mistake these diagnostics for storage
        # completions, and720 capability alone does not silently opt in.
        for maximum in (5,6,10):
            with self.subTest(maximum=maximum),self.assertRaises(ValueError):
                capture.parse_trace(raw,maximum_storage_action=maximum)
        for maximum in (5,6):
            with self.assertRaises(ValueError):
                capture.parse_trace(raw,maximum_storage_action=maximum,allow_native_timing=True)

    def test_native_load_timing_rejects_inconsistent_or_unknown_results(self):
        for result,apply_us,quiet_us in [(1,10,20),(8,10,20),(15,0,20),(0,-1,20),(0,21,20),(14,21,20)]:
            with self.subTest(values=(result,apply_us,quiet_us)),self.assertRaises(ValueError):
                capture.parse_trace(trace(events=[(1,90,12,result,apply_us,quiet_us)]),
                                    maximum_storage_action=10,allow_native_timing=True)
        with self.assertRaises(ValueError):
            capture.parse_trace(trace(),maximum_storage_action=10,allow_native_timing=1)

    def test_high_pattern_chain_and_record_modes_only720(self):
        fields=[2,100,*([0]*25),15,15,16,65535,1]
        parsed=capture.parse_performance(frame(8,fields),maximum_pitch=129,pattern_banks=16)
        self.assertEqual(parsed['selected_pattern'],15)
        with self.assertRaises(ValueError):capture.parse_performance(frame(8,fields),maximum_pitch=129)
        self.assertEqual(capture.parameter_count(capture.PROJECT_IDENTITY),198)
        storage=trace(events=[(1,99,11,0,0,10)])
        # Trace validates action according to exact firmware capability.
        capture.parse_trace(storage,maximum_storage_action=10)
        with self.assertRaises(ValueError):capture.parse_trace(storage,maximum_storage_action=6)


class SchedulerTests(unittest.TestCase):
    def test_pattern_snapshot_all64_inactive_and_unchanged_probe(self):
        session, journal = FakeSession(), MemoryJournal()
        result = capture.pattern_snapshot(session, journal)
        self.assertEqual((result["length"], result["count"], len(result["steps"])), (4, 64, 64))
        self.assertEqual([p[7] for p in session.sent if p[6] == 11], [0, 16, 32, 48, 0])
        count = len(session.sent)
        self.assertIsNone(capture.pattern_snapshot(session, journal, previous_revision=7))
        self.assertEqual(len(session.sent), count + 1)
        self.assertEqual(sum(e["event"] == "pattern_snapshot" for e in journal.events), 1)

    def test_pattern_snapshot_revision_retry_and_bounded_failure(self):
        for revisions, succeeds in (([7, 8, 8, 8, 8] + [8] * 5, True), ([1, 2, 2, 2, 2] * 3, False)):
            session, journal = FakeSession(), MemoryJournal()
            normal_read = session.read
            revisions = list(revisions)
            def read(timeout):
                if session.sent[-1][6] != 11: return normal_read(timeout)
                values = capture.decimal_fields(normal_read(timeout), 11)
                values[0] = revisions.pop(0)
                return frame(11, values)
            session.read = read
            if succeeds:
                self.assertEqual(capture.pattern_snapshot(session, journal)["attempt"], 2)
            else:
                with self.assertRaises(capture.PatternSnapshotUnstable): capture.pattern_snapshot(session, journal)
                self.assertFalse(any(e["event"] == "pattern_snapshot" for e in journal.events))
            self.assertFalse(revisions)

    def test_capture704_never_queries705_pattern_and705_deduplicates(self):
        for identity in capture.SUPPORTED_IDENTITIES:
            session, journal, clock = FakeSession(identity=identity), MemoryJournal(), Clock()
            with patch.object(capture, "connect", return_value=(session, None)) as connect:
                capture.capture(Mock(), journal, duration=2.1, identity=identity, clock=clock, sleep=clock.sleep)
            self.assertEqual(connect.call_args.kwargs["expected_identity"], identity)
            patterns = [e for e in journal.events if e["event"] == "pattern_snapshot"]
            self.assertEqual(len(patterns), int(identity in capture.PATTERN_IDENTITIES))
            self.assertEqual(any(p[6] == 11 for p in session.sent), identity in capture.PATTERN_IDENTITIES)
            self.assertEqual(any(p[6] == 12 for p in session.sent), identity in capture.LED_IDENTITIES)
            self.assertEqual(any(p[6]==31 for p in session.sent),identity in (capture.PERFORMANCE_IDENTITY,*capture.SYNC_IDENTITIES))
            has_meter=identity in capture.OUTPUT_METRIC_IDENTITIES
            self.assertEqual(any(p[6] == 27 for p in session.sent),has_meter)
            self.assertEqual(any(e['event']=='output_metrics' for e in journal.events),has_meter)
            self.assertEqual(journal.latest_status["leds"] is not None, identity in capture.LED_IDENTITIES)
            self.assertEqual(any(p[6] == 13 for p in session.sent), identity in capture.NATIVE_IDENTITIES)
            controls = [e for e in journal.events if e["event"] == "control_snapshot"]
            self.assertEqual(controls[0]["count"], capture.parameter_count(identity))

    def test_continuous_edits_skip_snapshot_but_preserve_recorder(self):
        session, journal, clock = FakeSession(), MemoryJournal(), Clock()
        with patch.object(capture, "connect", return_value=(session, None)), \
             patch.object(capture, "pattern_snapshot", side_effect=capture.PatternSnapshotUnstable("editing")):
            result = capture.capture(Mock(), journal, duration=.2, clock=clock, sleep=clock.sleep)
        self.assertEqual(result["reason"], "duration")
        self.assertEqual(result["cursor"], 1)

    def test_control_snapshot_detects_recorded_step_without_board_generation_change(self):
        for generation, revision, uptime, consistent in ((12, 31, 101, True), (12, 32, 101, False),
                                                         (13, 31, 101, False), (12, 31, 1, False)):
            journal = MemoryJournal()
            session = FakeSession()
            normal_read = session.read
            replies = []
            for gen, rev, milliseconds in ((12, 31, 100), (generation, revision, uptime)):
                fields = dict.fromkeys(capture.PERFORMANCE_FIELDS, 0)
                fields.update(schema=1, uptime_ms=milliseconds, controls_generation=gen, performance_revision=rev)
                replies.append(frame(8, fields.values()))
            def read(timeout):
                return replies.pop(0) if session.sent[-1][6] == 8 else normal_read(timeout)
            session.read = read
            capture.control_snapshot(session, journal)
            snapshot = next(e for e in journal.events if e["event"] == "control_snapshot")
            with self.subTest(generation=generation, revision=revision, uptime=uptime):
                self.assertEqual(snapshot["consistent"], consistent)
                self.assertEqual(snapshot["performance_revision_before"], 31)
                self.assertEqual(snapshot["performance_revision_after"], revision)
                self.assertEqual([packet[6] for packet in session.sent], [8] + [6] * 9 + [8, 2])

    def test_finite_capture_reads_only_and_retains_complete_controls(self):
        clock, journal, session = Clock(), MemoryJournal(), FakeSession()
        with patch.object(capture, "connect", return_value=(session, None)):
            report = capture.capture(Mock(), journal, duration=.31, clock=clock, sleep=clock.sleep)
        self.assertEqual(report["reason"], "duration")
        self.assertEqual(report["cursor"], 1)
        self.assertEqual(session.closed, 1)
        self.assertEqual(set(packet[6] for packet in session.sent), {2, 5, 6, 8, 11, 12})
        snapshot = next(e for e in journal.events if e["event"] == "control_snapshot")
        self.assertEqual(len(snapshot["values"]), 193)
        self.assertTrue(snapshot["consistent"])
        self.assertFalse(snapshot["atomic"])
        self.assertEqual(journal.latest_status["phase"], "capturing")

    def test_timeout_cleanly_reconnects_and_records_gap(self):
        clock, journal = Clock(), MemoryJournal()
        first, second = FakeSession(timeout=True), FakeSession()
        with patch.object(capture, "connect", side_effect=[(first, []), (second, [])]) as connect:
            result = capture.capture(Mock(), journal, duration=.8, clock=clock, sleep=clock.sleep)
        self.assertEqual(result["cursor"], 1)
        self.assertEqual(connect.call_count, 2)
        self.assertEqual((first.closed, second.closed), (1, 1))
        self.assertIn("connection_gap_start", [e["event"] for e in journal.events])
        self.assertIn("connection_gap_end", [e["event"] for e in journal.events])

    def test_cleanup_failure_never_reopens(self):
        clock, journal, session = Clock(), MemoryJournal(), FakeSession(timeout=True, cleanup=["busy buffer"])
        with patch.object(capture, "connect", return_value=(session, [])) as connect, self.assertRaisesRegex(capture.CaptureError, "cleanup"):
            capture.capture(Mock(), journal, duration=1, clock=clock, sleep=clock.sleep)
        self.assertEqual(connect.call_count, 1)

    def test_stop_file_and_reconnect_budget_are_bounded(self):
        clock, journal = Clock(), MemoryJournal()
        with tempfile.TemporaryDirectory() as directory:
            stop = Path(directory) / "stop"; stop.touch()
            with patch.object(capture, "connect") as connect:
                result = capture.capture(Mock(), journal, duration=None, stop_file=stop, clock=clock, sleep=clock.sleep)
            connect.assert_not_called(); self.assertEqual(result["reason"], "stop_file")
        with patch.object(capture, "connect", side_effect=capture.Disconnected("absent")) as connect, self.assertRaisesRegex(capture.CaptureError, "exhausted"):
            capture.capture(Mock(), journal, duration=30, max_reconnects=2, clock=clock, sleep=clock.sleep)
        self.assertEqual(connect.call_count, 3)

    def test_unexpected_protocol_is_fatal_and_handles_close(self):
        clock, journal, session = Clock(), MemoryJournal(), FakeSession()
        session.read = lambda timeout: b"\xf0\xf7"
        with patch.object(capture, "connect", return_value=(session, [])) as connect, self.assertRaises(ValueError):
            capture.capture(Mock(), journal, duration=1, clock=clock, sleep=clock.sleep)
        self.assertEqual(connect.call_count, 1); self.assertEqual(session.closed, 1)


class ConnectionTests(unittest.TestCase):
    def caps(self, identifier=0):
        return {"id": identifier, "name": "FMER Test01", "driver_manufacturer_id": 1,
                "driver_product_id": 2, "driver_version": 3}

    def test_ambiguous_changed_or_wrong_identity_cannot_send_telemetry(self):
        api, journal = Mock(), MemoryJournal()
        api.enumerate.return_value = {"inputs": [self.caps(), self.caps(1)], "outputs": [self.caps()]}
        with patch.object(capture, "ReadOnlySession") as factory, self.assertRaises(capture.transport.UpdateError):
            capture.connect(api, journal)
        factory.assert_not_called()
        api.enumerate.return_value = {"inputs": [self.caps()], "outputs": [self.caps()]}
        with patch.object(capture, "ReadOnlySession") as factory, self.assertRaisesRegex(capture.CaptureError, "metadata changed"):
            capture.connect(api, journal, [{"name": "different"}])
        factory.assert_not_called()
        session = Mock(); session.__enter__ = Mock(); session.identify.return_value = "FM-1_703"; session.close.return_value = []
        with patch.object(capture, "ReadOnlySession", return_value=session), self.assertRaisesRegex(capture.CaptureError, "expected"):
            capture.connect(api, journal)
        session.close.assert_called_once(); session._send.assert_not_called()

    def test_disconnected_stop6_requires_every_resource_released(self):
        from tests.test_fm1_flash_transport import FakeWinMM, caps_row
        for disconnected, extra, result in ((True, None, 6), (False, None, 6),
                                             (True, "midiInReset", 6), (True, "midiInUnprepareHeader", 6),
                                             (True, "midiOutClose", 6), (True, None, 5)):
            class Backend(FakeWinMM):
                def checked(self, name, *args):
                    super().checked(name, *args)
                    if name == "midiInStop": raise capture.hardware_bridge.WinMMError(name, result)
                    if name == extra: raise capture.hardware_bridge.WinMMError(name, 5)
            journal = MemoryJournal()
            session = capture.ReadOnlySession(Backend(), (caps_row(), caps_row(2)), journal)
            session.__enter__(); session.capture_disconnected = disconnected
            errors = session.close()
            admitted = disconnected and extra is None and result == 6
            with self.subTest(disconnected=disconnected, extra=extra, result=result):
                self.assertEqual(not errors, admitted)
                self.assertTrue(next(row for row in journal.events if row["event"] == "session_closed")["errors"])
                self.assertEqual(any(row["event"] == "expected_read_only_disconnect" for row in journal.events), admitted)
                self.assertEqual(session in capture.hardware_bridge._unreleased_sessions, not admitted)
                self.assertEqual(session.close(), errors)  # A second close cannot hide a first failed release.
            if session in capture.hardware_bridge._unreleased_sessions:
                capture.hardware_bridge._unreleased_sessions.remove(session)

    def test_disk_limit_during_cleanup_still_releases_all_handles(self):
        from tests.test_fm1_flash_transport import FakeWinMM, caps_row
        journal = MemoryJournal()
        session = capture.ReadOnlySession(FakeWinMM(), (caps_row(), caps_row(2)), journal)
        session.__enter__()
        journal.record = Mock(side_effect=capture.DiskBudgetReached("full"))
        with self.assertRaises(capture.DiskBudgetReached): session.close()
        self.assertFalse(session.input); self.assertFalse(session.output)
        self.assertTrue(all(row["ok"] for row in session.cleanup_results))


class CommandTests(unittest.TestCase):
    def test_main_retains_pid_heartbeat_final_hashes_and_read_only_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            session = FakeSession(identity=capture.SHOWCASE_IDENTITY)
            pins = {"source_files": [{"path": "synthetic", "sha256": "0" * 64}]}
            with patch.object(capture.hardware_bridge, "WinMM"), patch.object(capture, "source_pins", return_value=pins), \
                 patch.object(capture, "connect", return_value=(session, None)), patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(capture.main(["--firmware", "715", "--duration", ".05", "--output", str(output)]), 0)
            report = json.loads((output / "report.json").read_text())
            status = json.loads((output / "status.json").read_text())
            process = json.loads((output / "process.json").read_text())
            self.assertEqual(report["reason"], "duration")
            self.assertEqual(status["phase"], "stopped")
            self.assertEqual(status["pid"], process["pid"])
            self.assertEqual(report['sidecar_publish'],dict(retries=0,wait_ms=0))
            self.assertEqual(report["last_persisted_checkpoint"]["cursor"], 1)
            self.assertFalse(report["flash_writes"] or report["preset_writes"] or report["volatile_control_writes"])
            self.assertFalse(report["source_files_changed"])
            for segment in report["segments"]:
                self.assertEqual(segment["sha256"], hashlib.sha256((output / segment["path"]).read_bytes()).hexdigest())

    def test_source_change_or_disappearance_still_retains_failed_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            stop = Path(directory) / "stop"; stop.touch()
            with patch.object(capture.hardware_bridge, "WinMM"), \
                 patch.object(capture, "source_pins", side_effect=[{"source_files": []}, FileNotFoundError("source vanished")]), \
                 patch.object(capture, "connect") as connect, patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(capture.main(["--duration", "0", "--stop-file", str(stop), "--output", str(output)]), 1)
            connect.assert_not_called()
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["end_pin_error"], "source vanished")
            self.assertEqual(report["status"], "failed")


class FakeNativeSaveSession(FakeSession):
    authorize_backup_ack = capture.ReadOnlySession.authorize_backup_ack
    def __init__(self):
        super().__init__(identity=capture.NATIVE_IDENTITY)
        from tests.test_fm1_native_state import state_fixture
        self.raw = capture.native.encode(state_fixture())
        self.verified_identity = self.expected_identity = capture.NATIVE_IDENTITY
        self.native_ack_enabled = True
        self._native_pending_save_token = 0
        self._native_authorized_ack = None
        self.token, self.acked, self.ack_result = 41, 0, 0

    def _send(self, packet, purpose):
        if packet[6] == 19:
            if packet != self._native_authorized_ack:
                raise capture.CaptureError("Unauthorized fake ACK")
            self._native_authorized_ack = None
        super()._send(packet, purpose)

    def read(self, timeout):
        packet = self.sent[-1]
        if packet[6] == 13:
            return frame(13, [1, 7, 15, 0, self.token, self.acked, 0, 0, 0])
        if packet[6] == 15:
            token = sum(byte << (7 * i) for i, byte in enumerate(packet[7:12]))
            offset = packet[12] + 128 * packet[13]
            raw = self.raw[offset:offset+64]
            return frame(15, [token, offset, len(raw), *raw])
        if packet[6] == 19:
            if not self.ack_result: self.acked = self.token
            return frame(19, [self.token, self.ack_result])
        return super().read(timeout)


class NativeSaveTests(unittest.TestCase):
    def test_707_registry_and_led_family_explicit_legacy_contract_retained(self):
        self.assertEqual(capture.parameter_count("FM-1_706"), 193)
        self.assertEqual(capture.parameter_count("FM-1_707"), 195)
        packet = frame(6, [192, 3, 1, 16, 100])
        self.assertEqual(capture.parse_controls(packet, 192, parameter_count=195), [1,16,100])
        with self.assertRaises(ValueError): capture.parse_controls(packet, 192)
        good = [1, 100, 1, 99, 9, 3, 0, 0, 0, 0, *([0] * 30)]
        self.assertEqual(capture.parse_leds(frame(12,good), maximum_family=9)["family"], 9)
        with self.assertRaises(ValueError): capture.parse_leds(frame(12,good))

    def test_recorder_stays_read_only_without_opt_in(self):
        session, journal = FakeNativeSaveSession(), MemoryJournal()
        service = capture.NativeBackupService(journal)
        service.poll(session, 0)
        self.assertEqual([packet[6] for packet in session.sent], [13])
        self.assertIsNone(service.committed)

    def test_complete_durable_file_precedes_exact_save_ack(self):
        session, journal = FakeNativeSaveSession(), MemoryJournal()
        with tempfile.TemporaryDirectory() as directory:
            service = capture.NativeBackupService(journal, directory)
            service.poll(session, 0)
            self.assertEqual(session.acked, session.token)
            self.assertEqual(Path(service.committed["path"]).read_bytes(), session.raw)
            self.assertEqual(service.committed["bytes"], 784)
            self.assertEqual(session.sent[-1], capture.native.backup_ack_request(session.token, int.from_bytes(session.raw[28:32],"little")))
            count = len(list(Path(directory).glob("*.fmer-native")))
            service.poll(session, 1)
            self.assertEqual(len(list(Path(directory).glob("*.fmer-native"))), count)
        events = [event["event"] for event in journal.events]
        self.assertLess(events.index("native_save_backup_committed"), events.index("native_save_ack"))
        self.assertNotIn(14, [packet[6] for packet in session.sent])

    def test_bad_crc_never_creates_backup_or_ack_and_retry_is_bounded(self):
        session, journal = FakeNativeSaveSession(), MemoryJournal()
        session.raw = session.raw[:100] + bytes([session.raw[100] ^ 1]) + session.raw[101:]
        with tempfile.TemporaryDirectory() as directory:
            service = capture.NativeBackupService(journal, directory)
            service.poll(session, 0)
            first = len(session.sent)
            service.poll(session, 1)
            self.assertEqual(len(session.sent), first + 1)
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertNotIn(19, [packet[6] for packet in session.sent])
        self.assertIn("native_save_backup_failed", [event["event"] for event in journal.events])

    def test_disk_failure_preserves_telemetry_and_never_acknowledges(self):
        session, journal = FakeNativeSaveSession(), MemoryJournal()
        with tempfile.TemporaryDirectory() as directory, patch.object(capture.native, "save_backup", side_effect=OSError("disk full")):
            service = capture.NativeBackupService(journal, directory)
            self.assertEqual(service.poll(session, 0)["save_token"], 41)
            self.assertEqual(service.poll(session, 1)["save_token"], 41)
        self.assertEqual(session.acked, 0)
        self.assertNotIn(19, [packet[6] for packet in session.sent])
        self.assertEqual(sum(row["event"] == "native_save_backup_failed" for row in journal.events), 1)

    def test_ack_refusal_retries_existing_backup_without_duplicate(self):
        session, journal = FakeNativeSaveSession(), MemoryJournal()
        session.ack_result = 12
        with tempfile.TemporaryDirectory() as directory:
            service = capture.NativeBackupService(journal, directory)
            service.poll(session, 0)
            self.assertEqual(session.acked, 0)
            service.poll(session, 1)
            session.ack_result = 0
            service.poll(session, 10)
            self.assertEqual(session.acked, 41)
            self.assertEqual(len(list(Path(directory).glob("*.fmer-native"))), 1)
        self.assertEqual(sum(packet[6] == 19 for packet in session.sent), 2)

    def test_recorder_final_allowlist_refuses_every_write_and_unapproved_ack(self):
        session = object.__new__(capture.ReadOnlySession)
        session.expected_identity = session.verified_identity = capture.NATIVE_IDENTITY
        session.native_ack_enabled = False
        with patch.object(capture.transport.MidiSession, "_send") as send:
            session._send(capture.native.status_request(), "test")
            session._send(capture.native.chunk_request(1,783), "test")
            session._send(capture.controls_request(194,count=195), "test")
            for packet in (capture.native.snapshot_request(), capture.native.begin_request(1,0),
                           capture.native.write_chunk_request(1,0,b"x"), capture.native.commit_request(1),
                           capture.native.abort_request(), capture.native.backup_ack_request(1,0)):
                with self.assertRaises(capture.CaptureError): session._send(packet, "test")
            self.assertEqual(send.call_count, 3)

    def test_opt_in_ack_requires_pending_token_exact_committed_bytes_and_is_one_shot(self):
        from tests.test_fm1_native_state import state_fixture
        raw = capture.native.encode(state_fixture())
        session = object.__new__(capture.ReadOnlySession)
        session.expected_identity = session.verified_identity = capture.NATIVE_IDENTITY
        session.native_ack_enabled = True
        session._native_pending_save_token = 41
        session._native_authorized_ack = None
        with tempfile.TemporaryDirectory() as directory, patch.object(capture.transport.MidiSession, "_send") as send:
            saved = capture.native.save_backup(raw, Path(directory), device_identity="test")
            with self.assertRaises(capture.CaptureError): session.authorize_backup_ack(42, raw, saved["path"])
            with self.assertRaises(capture.CaptureError): session.authorize_backup_ack(41, raw[:-1], saved["path"])
            session.authorize_backup_ack(41, raw, saved["path"])
            exact = capture.native.backup_ack_request(41, int.from_bytes(raw[28:32],"little"))
            with self.assertRaises(capture.CaptureError): session._send(capture.native.backup_ack_request(41,0), "test")
            session._send(exact, "test")
            with self.assertRaises(capture.CaptureError): session._send(exact, "test")
            self.assertEqual(send.call_count, 1)

    def test_save_service_disconnect_remains_a_reconnect_condition(self):
        session, journal = FakeNativeSaveSession(), MemoryJournal()
        original = session.read
        session.read = lambda timeout: None if session.sent[-1][6] == 15 else original(timeout)
        with tempfile.TemporaryDirectory() as directory:
            service = capture.NativeBackupService(journal, directory)
            with self.assertRaises(capture.Disconnected): service.poll(session, 0)

    def test_legacy_identity_cannot_opt_into_native_mode(self):
        with self.assertRaises(ValueError):
            capture.capture(Mock(), MemoryJournal(), duration=1, identity="FM-1_706", native_backup_directory="unused")



class Native708TelemetryTests(unittest.TestCase):
    def test_719_controls_and_ties_require_explicit_workstation_capability(self):
        values=[2,430,1,1,2,70,75,0,1,0]+[0]*14
        packet=frame(6,[150,len(values),*values])
        self.assertEqual(capture.parse_controls(packet,150,parameter_count=198,fx=True,workstation=True),values)
        with self.assertRaises(ValueError):capture.parse_controls(packet,150,parameter_count=198,fx=True)
        for index,bad in [(0,3),(1,2001),(2,3),(3,2),(4,4),(5,128),(6,101),(7,2),(8,2),(9,1)]:
            invalid=values.copy();invalid[index]=bad
            with self.subTest(index=index),self.assertRaises(ValueError):
                capture.parse_controls(frame(6,[150,len(invalid),*invalid]),150,parameter_count=198,fx=True,workstation=True)
        tie=frame(11,[1,64,63,1,129,100,75])
        self.assertEqual(capture.parse_pattern(tie,63,maximum_pitch=129)['steps'],[[129,100,75]])
        with self.assertRaises(ValueError):capture.parse_pattern(tie,63)
        performance=[2,100,*([0]*25),7,6,8,255,1];performance[20]=129
        self.assertEqual(capture.parse_performance(frame(8,performance),maximum_pitch=129)['step_pitch'],129)
        with self.assertRaises(ValueError):capture.parse_performance(frame(8,performance))

    def test_output_meter_allowlist_tracks_exact_capabilities(self):
        session=object.__new__(capture.ReadOnlySession)
        packet=capture.PREFIX+bytes([27,247])
        with patch.object(capture.transport.MidiSession,'_send') as send:
            for identity in (*capture.SUPPORTED_IDENTITIES,'FM-1_732'):
                session.expected_identity=session.verified_identity=identity
                if identity in ('FM-1_715','FM-1_716','FM-1_717','FM-1_718','FM-1_719','FM-1_720','FM-1_721','FM-1_722','FM-1_723','FM-1_724','FM-1_725','FM-1_726','FM-1_727','FM-1_728','FM-1_729','FM-1_730','FM-1_731','FM-1_733','FM-1_734'):
                    session._send(packet,'read output meter')
                else:
                    with self.assertRaises(capture.CaptureError):session._send(packet,'unsupported meter')
            self.assertEqual(send.call_count,len(capture.OUTPUT_METRIC_IDENTITIES))

    def test_expanded_registry_and_bank_metrics_are_exact(self):
        self.assertEqual(capture.parameter_count('FM-1_708'),198)
        self.assertEqual(capture.parameter_count('FM-1_707'),195)
        self.assertEqual(capture.parameter_name(197),'sequence_chain_mask')
        values=[2,100,*([0]*25),7,6,8,255,1]
        self.assertEqual(capture.parse_performance(frame(8,values))['queued_pattern'],8)
        for index,bad in [(0,3),(27,8),(28,8),(29,9),(30,0),(30,256),(31,2)]:
            invalid=values.copy();invalid[index]=bad
            with self.subTest(index=index,bad=bad),self.assertRaises(ValueError):capture.parse_performance(frame(8,invalid))
        with self.assertRaises(ValueError):capture.parse_performance(frame(8,values[:-1]))
        with self.assertRaises(ValueError):capture.parse_performance(frame(8,[1,*values[1:]]))

    def test_storage_status_read_never_authorizes_storage_writes_or_slot_exports(self):
        session=object.__new__(capture.ReadOnlySession)
        with patch.object(capture.transport.MidiSession,'_send') as send:
            for identity in capture.SUPPORTED_IDENTITIES:
                session.expected_identity=session.verified_identity=identity
                packet=capture.PREFIX+bytes([21,247])
                if identity in capture.ONBOARD_IDENTITIES:session._send(packet,'status')
                else:
                    with self.assertRaises(capture.CaptureError):session._send(packet,'status')
            for packet in [capture.PREFIX+bytes([22,1,0])+bytes(15)+bytes([247]),capture.PREFIX+bytes([24,0,247]),capture.PREFIX+bytes([14,247])]:
                with self.assertRaises(capture.CaptureError):session._send(packet,'forbidden')
            self.assertEqual(send.call_count,len(capture.ONBOARD_IDENTITIES))

    def test_record_extent_selected_by_exact_firmware(self):
        session=object.__new__(capture.ReadOnlySession)
        packet=capture.native_v2.chunk_request(1,2175)
        with patch.object(capture.transport.MidiSession,'_send') as send:
            session.expected_identity=session.verified_identity='FM-1_708';session._send(packet,'last-byte')
            session.expected_identity=session.verified_identity='FM-1_707'
            with self.assertRaises(capture.CaptureError):session._send(packet,'wrong-extent')
            self.assertEqual(send.call_count,1)

    def test_storage_trace_has_bounded_slot_result_and_action(self):
        row=capture.parse_trace(trace(events=[(1,99,11,63,0,1)]))['events'][0]
        self.assertEqual((row['slot'],row['result'],row['action']),(63,0,'save'))
        for slot,result,action in [(128,0,1),(0,13,1),(0,0,0),(0,0,6)]:
            with self.assertRaises(ValueError):capture.parse_trace(trace(events=[(1,99,11,slot,result,action)]))

    def test_710_midi_save_event_does_not_stop_capture(self):
        raw=trace(events=[(1,99,11,0,0,6)])
        with self.assertRaises(ValueError):capture.parse_trace(raw)
        row=capture.parse_trace(raw,maximum_storage_action=6)['events'][0]
        self.assertEqual((row['slot'],row['result'],row['action']),(0,0,'save_midi'))
        with self.assertRaises(ValueError):capture.parse_trace(trace(events=[(1,99,11,0,0,7)]),maximum_storage_action=6)
        with self.assertRaises(ValueError):capture.parse_trace(raw,maximum_storage_action=7)

if __name__ == "__main__":
    unittest.main()
