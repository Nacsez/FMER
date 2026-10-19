import copy
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fm1_707_bench as bench707
from tests.test_fm1_native_state import state_fixture


class ShortMessageTests(unittest.TestCase):
    def setUp(self):
        self.api = SimpleNamespace(dll=SimpleNamespace(midiOutShortMsg=Mock()), checked=Mock())
        self.session = SimpleNamespace(verified_identity='FM-1_707', api=self.api, output=123)
        self.journal = Mock()

    def test_all_bounded_message_classes_have_exact_packed_bytes(self):
        messages = [(0xc0, 0, 0), (0xcf, 15, 0), (0x90, 60, 32), (0x9f, 71, 32),
                    (0x80, 60, 0), (0x8f, 71, 0), (0xb0, 120, 0), (0xbf, 120, 0)]
        messages += [(status, cc, value) for status in (0xb0, 0xbf)
                     for cc in (71, 72, 73, 74) for value in (0, 64, 127)]
        for status, data1, data2 in messages:
            bench707.short_message(self.session, self.journal, status, data1, data2)
            self.api.checked.assert_called_with('midiOutShortMsg', 123, status | data1 << 8 | data2 << 16)
        self.assertEqual(self.api.checked.call_count, len(messages))

    def test_invalid_identity_and_messages_cannot_reach_api(self):
        for message in ((0x90, 60, 0), (0x90, 60, 127), (0x91, 60, 32), (0xc0, 16, 0),
                        (0xc0, 1, 1), (0xb0, 7, 127), (0xbf, 74, 63), (0x80, 61, 0),
                        (0x9f, 60, True)):
            with self.assertRaises(ValueError):
                bench707.short_message(self.session, self.journal, *message)
        self.session.verified_identity = 'FM-1_706'
        with self.assertRaises(ValueError): bench707.short_message(self.session, self.journal, 0xc0, 0)
        self.api.checked.assert_not_called()

    def test_logging_failure_blocks_new_sound_but_still_releases(self):
        self.journal.record.side_effect = OSError('disk full')
        with self.assertRaises(OSError): bench707.short_message(self.session, self.journal, 0x90, 60, 32)
        self.api.checked.assert_not_called()
        for message in ((0x80, 60), (0xbf, 120)):
            with self.assertRaisesRegex(RuntimeError, 'Cleanup sent'):
                bench707.short_message(self.session, self.journal, *message)
        self.assertEqual(self.api.checked.call_count, 2)


class CleanupTests(unittest.TestCase):
    def test_every_cleanup_and_restore_attempt_survives_prior_failures(self):
        bench, bridge = Mock(), Mock()
        bench.cleanup.side_effect = RuntimeError('panic failed')
        result = dict(success=False, error='original bench failure')
        bridge.restore.return_value = {'complete_state_verified': True}
        with patch.object(bench707, 'short_message', side_effect=RuntimeError('MIDI release failed')) as short:
            bench707.cleanup_and_restore(object(), bench, bridge, b'original', Path('backups'), result)
        self.assertEqual(short.call_count, 8)
        self.assertEqual({call.args[2] for call in short.call_args_list}, {0x80, 0x8f})
        bench.cleanup.assert_called_once()
        bridge.restore.assert_called_once_with(b'original', Path('backups'))
        bench.button.assert_called_once_with(8)
        self.assertEqual(result['error'], 'original bench failure')
        self.assertEqual(len(result['final_cleanup_errors']), 9)
        self.assertTrue(result['final_restore']['complete_state_verified'])

    def test_restore_and_home_errors_retained_independently(self):
        bench, bridge = Mock(), Mock()
        bridge.restore.side_effect = RuntimeError('restore failed')
        bench.button.side_effect = RuntimeError('HOME failed')
        result = dict(success=True)
        with patch.object(bench707, 'short_message'):
            bench707.cleanup_and_restore(object(), bench, bridge, b'original', Path('.'), result)
        self.assertFalse(result['success'])
        self.assertIn('restore failed', result['restoration_error'])
        self.assertEqual(result['final_cleanup_errors'][0]['action'], 'return HOME')


class NativeProbeTests(unittest.TestCase):
    def test_save_pending_uses_actual_wire_fields_and_ack_identity(self):
        self.assertFalse(bench707.pending_save(dict(save_token=0, save_acked_token=0)))
        self.assertTrue(bench707.pending_save(dict(save_token=2, save_acked_token=1)))
        self.assertFalse(bench707.pending_save(dict(save_token=2, save_acked_token=2)))

    def test_full_length_last_selected_step_and_raw_name_probe_is_valid(self):
        source = state_fixture()
        raw = bench707.native.encode(source)
        records = list(bench707.restore_probe_records(raw))
        self.assertEqual([budget for budget, _ in records], [1, 4])
        for budget, record in records:
            state = bench707.native.decode(record)
            self.assertEqual(state['controls'][191], budget)
            self.assertEqual(state['length'], 63)
            self.assertEqual(state['controls'][187], 62)
            self.assertEqual(state['controls'][188:191], state['steps'][62])
            self.assertEqual(state['steps'][63], [128, 77, 93])
            self.assertEqual(state['steps'][:63], source['steps'][:63])
            self.assertEqual(bytes(state['vced'][145:]), b'TEST707 OK')
            self.assertEqual(state['preset_id'], bench707.native.CUSTOM_PRESET)
            for identifier in set(range(195)) - {186,187,188,189,190,191}:
                self.assertEqual(state['controls'][identifier], source['controls'][identifier])
        self.assertEqual(bench707.native.decode(raw), source)

    def test_short_pattern_keeps_selected_cell_and_length(self):
        source = state_fixture()
        source['length'] = source['controls'][186] = 1
        source['controls'][187] = 0
        source['controls'][188:191] = source['steps'][0]
        for _, record in bench707.restore_probe_records(bench707.native.encode(source)):
            state = bench707.native.decode(record)
            self.assertEqual(state['length'], 1)
            self.assertEqual(state['controls'][187:191], source['controls'][187:191])


class MainLifecycleTests(unittest.TestCase):
    def run_main(self, mode='native', *, backup_error=False, run_error=False,
                 close_error=False, final_log_error=False, pending=False):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            path = Path(directory)
            journal = Mock(directory=path)
            if final_log_error: journal.record.side_effect = OSError('final log failed')
            session = Mock()
            session.close.return_value = []
            if close_error: session.close.side_effect = RuntimeError('close failed')
            feature = Mock(journal=journal)
            feature.performance.return_value = dict(seq_running=0, seq_recording=0, arp_held=0)
            native = Mock()
            native.status.return_value = dict(save_token=2 if pending else 0, save_acked_token=0)
            original = bench707.native.encode(state_fixture())
            native.snapshot.return_value = (original, {})
            native.restore.return_value = dict(complete_state_verified=True)
            stack.enter_context(patch.object(bench707.transport, 'Journal', return_value=journal))
            stack.enter_context(patch.object(bench707.hardware, 'WinMM'))
            stack.enter_context(patch.object(bench707.transport, 'find_session', return_value=session))
            stack.enter_context(patch.object(bench707.feature, 'Bench', return_value=feature))
            stack.enter_context(patch.object(bench707.bridge, 'NativeBridge', return_value=native))
            stack.enter_context(patch.object(bench707.telemetry, 'led_state', return_value=dict(
                physical_keys=0, held_buttons=0, active_voices=0)))
            backup = stack.enter_context(patch.object(bench707.native, 'save_backup',
                side_effect=OSError('backup failed') if backup_error else None, return_value={'path': 'saved'}))
            short = stack.enter_context(patch.object(bench707, 'short_message'))
            runners = [stack.enter_context(patch.object(owner, name,
                side_effect=RuntimeError('primary run failed') if run_error else None))
                for owner, name in ((bench707, 'run_native'), (bench707.feature, 'run'),
                                    (bench707.legacy, 'run_matrix'), (bench707.legacy, 'run_releases'))]
            output = io.StringIO()
            with redirect_stdout(output): code = bench707.main(['--mode', mode])
            report = json.loads((path / 'report.json').read_text())
            return SimpleNamespace(code=code, report=report, summary=json.loads(output.getvalue()),
                session=session, bench=feature, nb=native, short=short, runners=runners,
                original=original, backup=backup)

    def test_modes_restore_complete_original_after_success(self):
        for index, mode in enumerate(('native', 'features', 'matrix', 'releases')):
            with self.subTest(mode=mode):
                result = self.run_main(mode)
                self.assertEqual(result.code, 0)
                self.assertTrue(result.report['success'])
                self.assertEqual([r.call_count for r in result.runners], [int(n == index) for n in range(4)])
                self.assertEqual(result.nb.restore.call_args.args[0], result.original)
                self.assertEqual(result.short.call_count, 8)
                result.session.close.assert_called_once()

    def test_failed_backup_has_no_musical_mutation_cleanup_or_restore(self):
        result = self.run_main(backup_error=True)
        self.assertEqual(result.code, 1)
        self.assertIn('backup failed', result.report['error'])
        result.short.assert_not_called()
        result.bench.cleanup.assert_not_called()
        result.nb.restore.assert_not_called()
        self.assertTrue(all(r.call_count == 0 for r in result.runners))
        result.session.close.assert_called_once()

    def test_pending_owner_save_prevents_backup_and_mutation(self):
        result = self.run_main(pending=True)
        self.assertEqual(result.code, 1)
        self.assertIn('pending SAVE', result.report['error'])
        result.nb.snapshot.assert_not_called()
        result.backup.assert_not_called()
        result.short.assert_not_called()
        result.nb.restore.assert_not_called()

    def test_primary_failure_restores_and_retains_close_and_log_errors(self):
        result = self.run_main(run_error=True, close_error=True, final_log_error=True)
        self.assertEqual(result.code, 1)
        self.assertIn('primary run failed', result.report['error'])
        self.assertIn('close failed', result.report['close_errors'][0])
        self.assertIn('final log failed', result.report['final_logging_error'])
        self.assertTrue(result.report['final_restore']['complete_state_verified'])
        self.assertEqual(result.nb.restore.call_args.args[0], result.original)


if __name__ == '__main__': unittest.main()
