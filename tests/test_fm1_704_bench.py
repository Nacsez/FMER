import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fm1_704_bench as tool
from tests.test_fm1_session import MemoryJournal, FakeSession, frame, trace


def controls_fixture(count=193):
    result = [0] * count
    for i in range(count):
        if not 145 <= i < 160:
            result[i] = tool.parameter_bounds(i, parameter_count=count)[0]
    result[186], result[187], result[188], result[189], result[190], result[191] = 4, 3, 70, 100, 66, 4
    return result


def performance(**changes):
    result = dict.fromkeys(tool.telemetry.PERFORMANCE_FIELDS, 0)
    result.update(schema=1, uptime_ms=100, scope_generation=1)
    result.update(changes)
    return result


class ProjectParameterTests(unittest.TestCase):
    def test726_noise_and_strum_bounds_remain_version_specific(self):
        kwargs=dict(parameter_count=198,fx=True,workstation=True,projects=True,sync=True)
        for identifier,value in ((161,4),(180,10)):
            with self.assertRaises(ValueError):tool.parameter_packet(identifier,value,**kwargs)
            self.assertEqual(tool.parameter_packet(identifier,value,polish=True,**kwargs)[6],7)
            with self.assertRaises(ValueError):tool.parameter_packet(identifier,value+1,polish=True,**kwargs)

    def test720_bounds_do_not_leak_into719(self):
        for identifier,value in ((195,15),(197,65535),(158,2)):
            kwargs=dict(parameter_count=198,fx=True,workstation=True)
            tool.parameter_packet(identifier,value,projects=True,**kwargs)
            with self.assertRaises(ValueError):tool.parameter_packet(identifier,value,**kwargs)


class ModelBench(tool.Bench):
    """Observable host workflow model; not a firmware/DSP emulation claim."""
    def __init__(self, *, identity="FM-1_706"):
        super().__init__(SimpleNamespace(journal=MemoryJournal()), MemoryJournal(), identity=identity)
        self.values = controls_fixture(self.parameter_count)
        if self.parameter_count == 195:
            self.values[193], self.values[194] = 5, 67
        self.original = list(self.values)
        self.steps = {0: [128, 100, 60], 1: [71, 90, 80], 3: self.values[188:191]}
        self.original_steps = {i: list(values) for i, values in self.steps.items()}
        self.running = self.recording = False
        self.active, self.held, self.emitted = 0, 0, 0
        self.calls = []
        self.fail_first_set = False

    def performance(self):
        if self.running or self.values[179] and self.held: self.emitted += 1
        return performance(seq_running=int(self.running), seq_recording=int(self.recording),
                           arp_held=self.held, emitted_notes=self.emitted, edit_step=self.values[187],
                           scope_generation=1 + len(self.calls))

    def controls(self): return list(self.values)

    def set(self, identifier, value):
        self.calls.append(("set", identifier, value))
        if self.fail_first_set:
            self.fail_first_set = False
            raise RuntimeError("original parameter failure")
        tool.parameter_packet(identifier, value, parameter_count=self.parameter_count)
        self.values[identifier] = value
        if identifier == 186 and self.values[187] >= value: self.values[187] = value - 1
        if identifier in (186, 187):
            self.values[188:191] = self.steps.setdefault(self.values[187], [128, 100, 75])
        if identifier in (188, 189, 190):
            self.steps[self.values[187]] = list(self.values[188:191])
        if identifier == 179 and not value: self.held = 0

    def transport(self, command):
        self.calls.append(("transport", command))
        if command == 5:
            self.running = self.recording = False
            self.active = self.held = 0

    def button(self, identifier):
        self.calls.append(("button", identifier))
        if identifier == 12: self.running = not self.running
        if identifier == 13:
            self.recording = not self.recording
            self.running = False

    def panel(self, kind, identifier, value):
        self.calls.append(("panel", kind, identifier, value))
        if kind == 2 and identifier == 12: self.transport(5)

    def notes(self, pitches=tool.NOTES, on=True):
        self.active = len(pitches) if on else 0
        if self.values[179]:
            if on or not self.values[184]: self.held = len(pitches) if on else 0
        if on and self.recording:
            for pitch in pitches:
                step = self.values[187]
                old = self.steps.setdefault(step, [128, 100, 75])
                self.steps[step] = [pitch, 32, old[2]]
                self.set(187, (step + 1) % self.values[186])

    def cleanup(self): self.transport(5)

    def trace(self, initial=False):
        self.calls.append(("trace", initial))
        if not initial:
            self.events += [{"kind": 10, "source": source, "value": value}
                            for source in (4, 5) for value in (0, 32)]
            self.events.append({"kind": 1, "virtual_panel": True})

    def check(self, baseline):
        self.trace()
        return dict(baseline, active_voices=self.active, audio_halves=1000)


class ProtocolTests(unittest.TestCase):
    def test_workstation_bounds_and_readback_are_identity_gated(self):
        values=[2,430,1,1,2,70,75,0,1]
        for i,value in enumerate(values,150):
            packet=tool.parameter_packet(i,value,parameter_count=198,fx=True,workstation=True)
            self.assertEqual(packet,tool.PREFIX+bytes([7,i&127,i>>7,value&127,(value>>7)&127,value>>14,247]))
            with self.assertRaises(ValueError):tool.parameter_packet(i,value,parameter_count=198,fx=True)
        tool.parameter_packet(188,129,parameter_count=198,fx=True,workstation=True)
        with self.assertRaises(ValueError):tool.parameter_packet(188,129,parameter_count=198,fx=True)
        with self.assertRaises(ValueError):tool.parameter_packet(159,0,parameter_count=198,fx=True,workstation=True)
        with self.assertRaises(ValueError):tool.parameter_packet(150,0,parameter_count=195,workstation=True)
        bench=tool.Bench(FakeSession(identity='FM-1_719'),MemoryJournal(),identity='FM-1_719')
        reply=frame(6,[151,24,430,1,1,2,70,75,0,1,0,*([0]*15)])
        with patch.object(bench,'echo') as echo,patch.object(bench,'performance',return_value=performance()),patch.object(tool.telemetry,'request',return_value=reply):
            bench.set(151,430)
        self.assertEqual(echo.call_args.args[0],tool.parameter_packet(151,430,parameter_count=198,fx=True,workstation=True))
        legacy=tool.Bench(FakeSession(identity='FM-1_718'),MemoryJournal(),identity='FM-1_718')
        with patch.object(legacy,'echo') as echo,self.assertRaises(ValueError):legacy.set(151,430)
        echo.assert_not_called()

    def test_identity_selects_complete_control_reply_extent_without_loosening_legacy(self):
        for identity,count in (("FM-1_704",193),("FM-1_705",193),("FM-1_706",193),("FM-1_707",195),("FM-1_708",198)):
            session=FakeSession(identity=identity)
            bench=tool.Bench(session,MemoryJournal(),identity=identity)
            self.assertEqual(bench.parameter_count,count)
            values=bench.controls()
            self.assertEqual(len(values),count)
            self.assertEqual(session.sent[-2],tool.telemetry.controls_request(192,count=count))
        with self.assertRaises(ValueError):tool.Bench(FakeSession(),MemoryJournal(),identity="FM-1_732")

    def test_new707_parameter_writes_require_explicit_registry_and_validate_limits(self):
        for identifier,maximum in ((193,16),(194,100)):
            for value in (0,maximum):
                packet=tool.parameter_packet(identifier,value,parameter_count=195)
                self.assertEqual(packet,tool.PREFIX+bytes([7,identifier&127,identifier>>7,value,0,0,247]))
                with self.assertRaises(ValueError):tool.parameter_packet(identifier,value)
            for value in (-1,maximum+1,True):
                with self.assertRaises(ValueError):tool.parameter_packet(identifier,value,parameter_count=195)
        for count in (194,196,True):
            with self.assertRaises(ValueError):tool.parameter_packet(160,0,parameter_count=count)
        for identifier in (145,159,195,True):
            with self.assertRaises(ValueError):tool.parameter_packet(identifier,0,parameter_count=195)
        bench=tool.Bench(FakeSession(identity="FM-1_707"),MemoryJournal(),identity="FM-1_707")
        packet=tool.parameter_packet(193,16,parameter_count=195)
        with patch.object(tool.telemetry,"request",side_effect=[packet,frame(6,[193,2,16,50])]) as request, \
             patch.object(bench,"performance",return_value=performance()):
            bench.set(193,16)
        self.assertEqual(request.call_args.args[1],tool.telemetry.controls_request(193,count=195))
        legacy=tool.Bench(FakeSession(),MemoryJournal())
        with patch.object(tool.telemetry,"request") as request,self.assertRaises(ValueError):legacy.set(193,0)
        request.assert_not_called()

    def test_707_led_legacy_runner_leaves_native_save_handshake_to_native_bench(self):
        bench=tool.Bench(Mock(),MemoryJournal(),identity="FM-1_707")
        for name in ("cleanup","set","button","panel","check","trace","notes"):
            setattr(bench,name,Mock())
        result={"cases":[]}
        with patch.object(tool,"wait_leds",return_value={}),patch.object(tool,"set_octave"),patch.object(tool.time,"sleep"):
            tool.led706_checks(bench,result,{})
        self.assertFalse(any(call.args[0]==9 for call in bench.button.call_args_list))
        self.assertFalse(any(call.args[:2]==(2,9) for call in bench.panel.call_args_list))
        self.assertIsNone(result["cases"][0]["save_pressed"])
        self.assertIn("excluded",result["cases"][0]["save_scope"])

    def test_every_led_case_note_uses_real_smoke_validator_and_vetted_stolen_chord(self):
        # Exercise the complete LED workflow's MIDI notes through the real
        # validator and a fake WinMM backend. LED observation is separately
        # tested; no device API or sound renderer runs in this regression.
        session = Mock(); bench = tool.Bench(session, MemoryJournal())
        for name in ("cleanup", "set", "button", "panel", "check", "trace"):
            setattr(bench, name, Mock())
        with patch.object(tool, "wait_leds", return_value={}) as observe, \
             patch.object(tool, "set_octave"), patch.object(tool.time, "sleep"):
            tool.led706_checks(bench, {"cases": []}, {})
        packed = [call.args[2] for call in session.api.checked.call_args_list]
        note_ons = [(value >> 8) & 127 for value in packed if value & 255 == 0x9F]
        self.assertEqual(set(note_ons), {60, 64, 67, 71, 74})
        self.assertIn([60, 64, 67, 71, 74], [note_ons[i:i+5] for i in range(len(note_ons)-4)])
        stolen_test = next(call.args[1] for call in observe.call_args_list if call.args[2].startswith("stolen pitch"))
        state = dict(active_voices=4, gated_pitches=[64, 67, 71, 74], octave_plus3=3, lit=[0]*11, dim=[0]*11)
        self.assertTrue(stolen_test(state))
        self.assertFalse(stolen_test(dict(state, gated_pitches=[62, 64, 65, 67])))
        before = session.api.checked.call_count
        for pitch in (62, 65):
            with self.assertRaisesRegex(ValueError, "permitted bench smoke"):
                tool.legacy.short_message(session, bench.journal, 0x9F, pitch, 32)
        self.assertEqual(session.api.checked.call_count, before)

    def test_led_matrix_coordinates_distinguish_green_play_and_actual_keys(self):
        state = dict(lit=[0] * 11, dim=[0] * 11, octave_plus3=3)
        state["lit"][8] = 2  # Separate green PLAY, not a physical key ID.
        state["dim"][10] = 4  # Ordinary PLAY.
        state["lit"][9] = 16  # C4/MIDI60.
        self.assertEqual(tool.green_play_level(state), 2)
        self.assertEqual(tool.led_level(state, 12), 1)
        self.assertEqual(tool.pitch_led_level(state, 60), 2)
        self.assertEqual(len(set(tool.LED_POSITIONS.values())), 41)
        with self.assertRaises(ValueError): tool.led_level(state, 41)
        with self.assertRaises(ValueError): tool.pitch_led_level(state, 52)

    def test_led_wait_settles_and_timeout_retains_last_state(self):
        bench = Mock(); bench.journal = MemoryJournal()
        with patch.object(tool.telemetry, "led_state", side_effect=[{"generation": 1}, {"generation": 2}]), \
             patch.object(tool.time, "sleep"):
            self.assertEqual(tool.wait_leds(bench, lambda state: state["generation"] == 2, "changed"), {"generation": 2})
        bench.trace.assert_called_once()
        times = iter((0, .1, .2, 2))
        with patch.object(tool.telemetry, "led_state", return_value={"generation": 1}), \
             patch.object(tool.time, "sleep"), patch.object(tool.time, "monotonic", side_effect=lambda: next(times)), \
             self.assertRaisesRegex(RuntimeError, "did not settle"):
            tool.wait_leds(bench, lambda state: False, "stale")
        self.assertEqual(bench.journal.events[-1]["latest"], {"generation": 1})

    def test_octave_changes_are_bounded_and_use_expected_buttons(self):
        bench = Mock()
        with patch.object(tool.telemetry, "led_state", return_value={"octave_plus3": 5}), \
             patch.object(tool, "wait_leds", side_effect=[{"octave_plus3": 4}, {"octave_plus3": 3}]):
            tool.set_octave(bench, 3)
        self.assertEqual([call.args for call in bench.button.call_args_list], [(0,), (0,)])
        for wanted in (-1, 7, True):
            with self.assertRaises(ValueError): tool.set_octave(bench, wanted)

    def test_exact_parameter_and_panel_packets_validate_canonical_values(self):
        self.assertEqual(tool.parameter_packet(162, 20000), tool.PREFIX + bytes([7, 34, 1, 32, 28, 1, 247]))
        self.assertEqual(tool.panel_packet(1, 6, -64), tool.PREFIX + bytes([10, 1, 6, 0, 247]))
        self.assertEqual(tool.panel_packet(2, 13, 1), tool.PREFIX + bytes([10, 2, 13, 65, 247]))
        for identifier, value in ((145, 0), (193, 0), (True, 0), (134, 32), (181, 3), (162, 19), (191, 5), (188, 129), (160, True)):
            with self.subTest(identifier=identifier, value=value), self.assertRaises(ValueError): tool.parameter_packet(identifier, value)
        for args in ((True, 1, 0), (1, 7, 0), (2, 14, 1), (2, 0, 2), (1, 0, -65)):
            with self.subTest(args=args), self.assertRaises(ValueError): tool.panel_packet(*args)

    def test_set_echo_failure_cannot_claim_adoption(self):
        session = FakeSession(); session.read = lambda timeout: b"wrong"
        bench = tool.Bench(session, MemoryJournal())
        with self.assertRaisesRegex(RuntimeError, "echo mismatch"): bench.set(160, 1)
        self.assertEqual(len(session.sent), 1)

    def test_set_requires_matching_generation_and_exact_readback(self):
        session = Mock(); journal = MemoryJournal(); bench = tool.Bench(session, journal)
        responses = [tool.parameter_packet(160, 1), frame(6, [160, 24, *([0] * 24)])]
        with patch.object(tool.telemetry, "request", side_effect=responses), \
             patch.object(bench, "performance", return_value=performance()):
            with self.assertRaisesRegex(RuntimeError, "readback"): bench.set(160, 1)

    def test_snapshot_rejects_audio_revision_change(self):
        bench = tool.Bench(FakeSession(), MemoryJournal())
        with patch.object(bench, "performance", side_effect=[performance(performance_revision=1), performance(performance_revision=2)]):
            with self.assertRaisesRegex(RuntimeError, "changed during"): bench.controls()


class TraceTests(unittest.TestCase):
    def test_initial_history_is_logged_but_not_counted_as_current_bench_evidence(self):
        journal = MemoryJournal(); bench = tool.Bench(FakeSession(), journal)
        with patch.object(tool.telemetry, "request", return_value=trace()): bench.trace(initial=True)
        self.assertEqual(bench.cursor, 1); self.assertEqual(bench.events, [])
        with patch.object(tool.telemetry, "request", return_value=trace(newest=2, events=[(2, 100, 10, (4 << 8) | 60, 32, 64)])):
            bench.trace()
        self.assertEqual(len(bench.events), 1); self.assertEqual(bench.events[0]["source"], 4)

    def test_gaps_reboots_and_omitted_events_are_failures(self):
        bad = [trace(newest=300, oldest=45, events=[(i, 100, 4, 60, 0, 1) for i in range(45, 51)]),
               trace(newest=2, events=[]), trace(newest=0, events=[]),
               trace(newest=2, uptime=1, events=[(2, 1, 4, 60, 0, 1)])]
        for packet in bad:
            bench = tool.Bench(FakeSession(), MemoryJournal()); bench.cursor = 1; bench.uptime = 100
            with patch.object(tool.telemetry, "request", return_value=packet), self.assertRaises(RuntimeError): bench.trace()
            self.assertEqual(bench.events, [])


class WorkflowTests(unittest.TestCase):
    def before(self, **values):
        return dict(dict.fromkeys(tool.FAILURES, 0), active_voices=0, audio_halves=100, **values)

    def test_707_workflow_restores_both_appended_controls_and_selects_current_compatibility_checks(self):
        bench=ModelBench(identity="FM-1_707");result={"identity":"FM-1_707"}
        with patch.object(tool.legacy,"query",side_effect=lambda *args:dict(self.before(),active_voices=bench.active)), \
             patch.object(tool.legacy,"reset_peaks"),patch.object(tool.time,"sleep"), \
             patch.object(tool,"repeat_admission",return_value={"expected_drops":0}), \
             patch.object(tool.telemetry,"led_state",return_value={"held_buttons":0,"physical_keys":0,"octave_plus3":3}) as read_leds, \
             patch.object(tool,"panel705_checks") as panel,patch.object(tool,"led706_checks") as lights, \
             patch.object(tool,"set_octave"):
            tool.run(bench,result)
        self.assertEqual(bench.values,bench.original)
        self.assertEqual(len(result["restored_controls"]),195)
        self.assertIn(("set",193,0),bench.calls)
        self.assertIn(("set",193,5),bench.calls)
        self.assertIn(("set",194,67),bench.calls)
        self.assertEqual(result["cleanup_errors"],[])
        panel.assert_called_once();lights.assert_called_once()
        self.assertEqual(read_leds.call_args.kwargs["identity"],"FM-1_707")

    def test_registry_identity_mismatch_refuses_all_reads_and_mutation(self):
        bench=ModelBench()
        with patch.object(tool.legacy,"query") as read,self.assertRaisesRegex(ValueError,"identity"):
            tool.run(bench,{"identity":"FM-1_707"})
        read.assert_not_called();self.assertEqual(bench.calls,[])

    def test_all64_fm_cases_and_deterministic_step_checks_restore_original_state(self):
        bench, result = ModelBench(), {}
        with patch.object(tool.legacy, "query", side_effect=lambda *args: dict(self.before(), active_voices=bench.active)), \
             patch.object(tool.legacy, "reset_peaks"), patch.object(tool.time, "sleep"), \
             patch.object(tool, "repeat_admission", return_value={"expected_drops": 0}):
            tool.run(bench, result)
        fm = [case for case in result["cases"] if case["case"] == "FM algorithm"]
        self.assertEqual(len(fm), 64)
        self.assertEqual({case["patch"] for case in fm}, {"original patch", "dense six-operator synthetic"})
        self.assertEqual(bench.values, bench.original)
        for step, old in bench.original_steps.items(): self.assertEqual(bench.steps[step], old)
        self.assertEqual(result["cleanup_errors"], [])
        self.assertGreater(sum(call[0] == "trace" for call in bench.calls), 24)
        for operator in range(6):
            self.assertIn(("set", operator * 21 + 16, 75), bench.calls)
            self.assertIn(("set", operator * 21 + 18, operator + 1), bench.calls)

    def test_primary_failure_survives_failed_restoration(self):
        bench, result = ModelBench(), {}; bench.fail_first_set = True
        with patch.object(tool.legacy, "query", return_value=self.before()), patch.object(tool.time, "sleep"), \
             patch.object(tool, "restore_state", return_value=[{"error": "restore failed"}]) as restore:
            with self.assertRaisesRegex(RuntimeError, "original parameter failure"): tool.run(bench, result)
        restore.assert_called_once()

    def test_busy_original_state_refuses_all_mutation(self):
        for changed in ({"seq_running": 1}, {"seq_recording": 1}, {"arp_held": 1}, {"controls_generation": 1}):
            bench, result = ModelBench(), {}
            with patch.object(tool.legacy, "query", return_value=self.before()), \
                 patch.object(bench, "performance", return_value=performance(**changed)):
                with self.assertRaises(RuntimeError): tool.run(bench, result)
            self.assertEqual(bench.calls, [])
        bench = ModelBench()
        with patch.object(tool.legacy, "query", return_value=dict(self.before(), active_voices=1)):
            with self.assertRaises(RuntimeError): tool.run(bench, {})
        self.assertEqual(bench.calls, [])

    def test_restoration_failure_attempts_remaining_values_and_reports_mismatch(self):
        bench, result = ModelBench(), {}
        original = bench.controls(); bench.values[160] = 1
        real_set = bench.set
        def fail_one(identifier, value):
            if identifier == 160: raise RuntimeError("engine restore failed")
            real_set(identifier, value)
        with patch.object(bench, "set", side_effect=fail_one):
            errors = tool.restore_state(bench, result, original, {})
        self.assertTrue(any("engine restore" in row.get("error", "") for row in errors))
        self.assertTrue(any(row.get("mismatched_ids") == [160] for row in errors))
        self.assertIn(("set", 192, original[192]), bench.calls)
        self.assertIn(("set", 179, original[179]), bench.calls)

    def test_cleanup_and_panic_continue_when_logging_fails(self):
        journal = MemoryJournal(); journal.record = Mock(side_effect=OSError("disk unavailable"))
        session = SimpleNamespace(journal=journal)
        bench = tool.Bench(session, journal); bench.held_buttons = {12, 13}
        sent = []
        def request(session, packet, purpose):
            session.journal.record("send_intent", hex=packet.hex())
            sent.append(packet); return packet
        with patch.object(tool.telemetry, "request", side_effect=request), patch.object(tool.legacy, "short_message") as short, \
             patch.object(tool.legacy, "cleanup_notes") as cleanup, patch.object(tool.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "failed durable logging"): bench.cleanup()
        self.assertEqual(sent[-1], tool.PREFIX + bytes([9, 5, 247]))
        self.assertEqual(len(sent), 3)
        short.assert_called_once(); cleanup.assert_called_once()
        self.assertEqual(bench.held_buttons, set())
        self.assertIs(session.journal, journal)
        self.assertTrue(bench.recovery_logs[0]["logging_errors"])

    def test_full_restoration_continues_with_failed_logging_and_reports_degradation(self):
        bench, result = ModelBench(), {}
        original = list(bench.original); bench.values[160] = 1
        original_set = bench.set
        bench.journal.record = Mock(side_effect=OSError("disk unavailable"))
        def logged_set(identifier, value):
            bench.session.journal.record("restore_send", identifier=identifier, value=value)
            original_set(identifier, value)
        with patch.object(bench, "set", side_effect=logged_set):
            errors = tool.restore_state(bench, result, original, {})
        self.assertEqual(bench.values, original)
        self.assertTrue(any(row["action"] == "restoration logging" for row in errors))
        self.assertTrue(result["recovery_logging"][0]["retained_records"])

    def test_failed_button_echo_still_schedules_release(self):
        bench = tool.Bench(FakeSession(), MemoryJournal())
        with patch.object(bench, "echo", side_effect=RuntimeError("lost echo")):
            with self.assertRaises(RuntimeError): bench.panel(2, 12, 1)
        self.assertEqual(bench.held_buttons, {12})

    def test_fallback_log_memory_is_bounded(self):
        journal = Mock(); journal.record.side_effect = OSError("full")
        fallback = tool.RecoveryJournal(journal)
        for i in range(200): fallback.record("restore", value=i)
        self.assertEqual(len(fallback.records), 128); self.assertEqual(fallback.dropped, 72)
        self.assertEqual(len(fallback.failures), 1)


class CommandTests(unittest.TestCase):
    def test_historical_default_reference_cannot_qualify707(self):
        with patch.object(tool.transport,"Journal") as journal,patch.object(tool.bridge,"WinMM") as backend, \
             patch("sys.stderr",new=io.StringIO()),self.assertRaises(SystemExit) as exit_status:
            tool.main(["--defaults","--firmware","707"])
        self.assertEqual(exit_status.exception.code,2);journal.assert_not_called();backend.assert_not_called()
    def test_default_reference_failure_happens_before_any_port_open(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Mock(); journal.directory = Path(directory)
            with patch.object(tool.transport, "Journal", return_value=journal), \
                 patch.object(tool.bridge, "WinMM") as backend, patch.object(tool, "load_default_reference", side_effect=ValueError("changed pin")), \
                 patch.object(tool.transport, "find_session") as find, patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(tool.main(["--defaults"]), 1)
            backend.assert_not_called(); find.assert_not_called()
            report = json.loads((Path(directory) / "report.json").read_text())
            self.assertFalse(report["volatile_control_writes"])
            self.assertIn("changed pin", report["error"])

    def test_default_action_uses_read_only_session_and_never_feature_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Mock(); journal.directory = Path(directory)
            session = Mock(); session.close.return_value = []
            with patch.object(tool.transport, "Journal", return_value=journal), patch.object(tool.bridge, "WinMM"), \
                 patch.object(tool, "load_default_reference", return_value={"source_files": []}), \
                 patch.object(tool.telemetry, "connect", return_value=(session, None)) as connect, \
                 patch.object(tool, "audit_defaults") as audit, patch.object(tool, "run") as run, \
                 patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(tool.main(["--defaults", "--firmware", "706"]), 0)
            self.assertEqual(connect.call_args.kwargs["expected_identity"], "FM-1_706")
            audit.assert_called_once(); run.assert_not_called(); session.close.assert_called_once()

    def test_firmware_selection_controls_exact_handshake_and_artifact_identity(self):
        for version in ("704", "705", "706", "707"):
            with tempfile.TemporaryDirectory() as directory:
                journal = Mock(); journal.directory = Path(directory)
                session = Mock(); session.close.return_value = []
                with patch.object(tool.transport, "Journal", return_value=journal) as factory, \
                     patch.object(tool.bridge, "WinMM"), \
                     patch.object(tool.transport, "find_session", return_value=session) as connect, \
                     patch.object(tool, "run") as run, patch("sys.stdout", new=io.StringIO()):
                    self.assertEqual(tool.main(["--firmware", version]), 0)
                self.assertEqual(connect.call_args.args[1], "FM-1_" + version)
                self.assertEqual(run.call_args.args[0].parameter_count,195 if version=="707" else 193)
                self.assertIn("fm1-" + version + "-bench", str(factory.call_args.args[0]))
                self.assertEqual(json.loads((Path(directory) / "report.json").read_text())["identity"], "FM-1_" + version)

    def test_failed_final_log_keeps_primary_error_and_still_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Mock(); journal.directory = Path(directory)
            journal.record.side_effect = [None, OSError("final log failed")]
            session = Mock(); session.close.return_value = ["close also failed"]
            with patch.object(tool.transport, "Journal", return_value=journal), patch.object(tool.bridge, "WinMM"), \
                 patch.object(tool.transport, "find_session", return_value=session), \
                 patch.object(tool, "run", side_effect=RuntimeError("primary")), patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(tool.main([]), 1)
            report = json.loads((Path(directory) / "report.json").read_text())
            self.assertEqual(report["error"], "RuntimeError('primary')")
            self.assertEqual(report["midi_cleanup_errors"], ["close also failed"])
            self.assertIn("final log failed", report["final_logging_error"])
            session.close.assert_called_once(); journal.close.assert_called_once()


class Panel705Model(ModelBench):
    def __init__(self, *, broken_release=False, broken_arp=False):
        super().__init__()
        self.family = self.page = 0
        self.select = self.used = False
        self.broken_release, self.broken_arp = broken_release, broken_arp

    def performance(self):
        return dict(super().performance(), page_family=self.family, page_index=self.page)

    def panel(self, kind, identifier, value):
        self.calls.append(("panel", kind, identifier, value))
        if kind == 2:
            if identifier == 3:
                if value: self.select, self.used = True, False
                else:
                    if not self.used or self.broken_release:
                        self.page = (self.page + 1) % (3 if self.family == 5 else 1)
                    self.select = False
            elif value and identifier == 8: self.family, self.page = 0, 0
            elif value and identifier == 10:
                if self.family != 5: self.family, self.page = 5, 0
                elif not self.broken_arp:
                    self.values[179] ^= 1
                    self.held = self.active if self.values[179] else 0
            elif value and identifier == 11: self.family, self.page = 6, 0
            return
        self.used = self.used or self.select
        if identifier == 0: self.page = (self.page + value) % (3 if self.family == 5 else 2)
        elif self.family == 0 and identifier == 4: self.set(170, self.values[170] + (1 if self.select else 5) * value)
        elif self.family == 0 and identifier == 2: self.set(162, 1235 if self.select else 1600)
        elif self.family == 5 and self.page == 1 and identifier == 3: self.set(183, self.values[183] + value)
        elif self.family == 6 and self.page == 0 and identifier == 2: self.set(187, self.values[187] + value)

    def button(self, identifier):
        self.panel(2, identifier, 1); self.panel(2, identifier, 0)


class Panel705Tests(unittest.TestCase):
    def test_successful_virtual_workflow_retains_inactive_steps(self):
        bench, result = Panel705Model(), {"cases": []}
        original_steps = dict(bench.steps)
        def snapshot(*args):
            return dict(length=32, steps=[bench.steps.get(i, [128, 100, 75]) for i in range(64)], count=64)
        with patch.object(tool.time, "sleep"), patch.object(tool.legacy, "query", return_value={"active_voices": 3}), \
             patch.object(tool.telemetry, "pattern_snapshot", side_effect=snapshot):
            tool.panel705_checks(bench, result, {})
        self.assertEqual(len(result["cases"]), 4)
        self.assertEqual(bench.values[186], bench.original[186])
        self.assertTrue(all(bench.steps[i] == step for i, step in original_steps.items()))
        self.assertFalse(any(call[0] == "set" and call[1] in (188, 189, 190) for call in bench.calls))

    def test_wrong_arp_toggle_or_held_select_release_fails(self):
        for changes in ({"broken_arp": True}, {"broken_release": True}):
            bench = Panel705Model(**changes)
            ticks = iter(range(10000))
            with patch.object(tool.time, "sleep"), patch.object(tool.time, "monotonic", side_effect=lambda: next(ticks) * .1), \
                 self.assertRaisesRegex(RuntimeError, "705 panel failed"):
                tool.panel705_checks(bench, {"cases": []}, {})


class DefaultAuditTests(unittest.TestCase):
    def fixture(self):
        values = controls_fixture(); values[187:191] = [0, 128, 100, 75]
        reference = dict(controls=values, steps=[[128, 100, 75] for _ in range(64)], length=4, source_files=[])
        leds = tool.telemetry.parse_leds(frame(12, [1, 100, 1, 99, 0, 3, 0, 0, 0, 0, *([0] * 30)]))
        leds["lit"][7] = 2
        return reference, leds

    def test_comparison_checks_all_inactive_cells_without_mutating(self):
        reference, leds = self.fixture()
        for mismatch in (None, "control", "inactive_step", "led", "generation"):
            bench = Mock(); bench.journal = MemoryJournal()
            controls = list(reference["controls"])
            steps = [list(step) for step in reference["steps"]]
            state = dict(leds, lit=list(leds["lit"]))
            if mismatch == "control": controls[170] = 1
            if mismatch == "inactive_step": steps[63][0] = 60
            if mismatch == "led": state["lit"][6] |= 2
            bench.controls.return_value = controls
            bench.performance.side_effect = [performance(), performance(controls_generation=int(mismatch == "generation"))]
            with patch.object(tool.legacy, "query", return_value=dict.fromkeys(tool.FAILURES + ("active_voices",), 0)), \
                 patch.object(tool.telemetry, "pattern_snapshot", return_value=dict(steps=steps, length=4)), \
                 patch.object(tool.telemetry, "led_state", return_value=state):
                if mismatch:
                    with self.subTest(mismatch=mismatch), self.assertRaisesRegex(RuntimeError, "Read-only audit"):
                        tool.audit_defaults(bench, {}, reference)
                else: tool.audit_defaults(bench, {}, reference)
            bench.set.assert_not_called(); bench.notes.assert_not_called(); bench.transport.assert_not_called()

    def test_restoration_includes_original_octave_and_retains_its_failure(self):
        bench = ModelBench(); result = {"original_octave_plus3": 4}
        with patch.object(tool, "set_octave", side_effect=RuntimeError("octave restore failed")) as restore:
            errors = tool.restore_state(bench, result, bench.original, {})
        restore.assert_called_once_with(bench, 4)
        self.assertTrue(any(error["action"] == "restore octave" for error in errors))


class RepeatAdmissionTests(unittest.TestCase):
    def fixture(self):
        events = []
        groups = [(60, 64, 72, 76)] + [(60, 64, 67, 72)] * 16
        for index, pitches in enumerate(groups):
            for pitch in pitches:
                events.append(dict(seq=len(events) + 1, kind=10, value=32, source=5, pitch=pitch,
                                   audio_frame_low32=2697600 + index * 2000))
        before = performance(trace_newest=0, generated_drops=7, emitted_notes=117)
        after = performance(trace_newest=len(events), generated_drops=39, emitted_notes=185)
        return before, after, events

    def test_known_six_note_repeat_exactly_matches_budget_and_partial_startup(self):
        result = tool.repeat_admission(*self.fixture())
        self.assertEqual(result["groups"], 17)
        self.assertEqual(result["six_note_groups"], 16)
        self.assertEqual(result["partial_groups"], 1)
        self.assertEqual(result["requested_attacks"], 100)
        self.assertEqual(result["admitted_attacks"], 68)
        self.assertEqual(result["expected_drops"], 32)

    def test_extra_drop_missing_event_wrong_pitch_or_source_cannot_be_excused(self):
        before, after, events = self.fixture()
        failures = [(before, dict(after, generated_drops=40), events),
                    (before, dict(after, emitted_notes=184), events),
                    (before, after, events[:-1]),
                    (before, after, [dict(events[0], source=4)] + events[1:]),
                    (before, after, [dict(events[0], pitch=61)] + events[1:]),
                    (before, after, [dict(events[0], value=80)] + events[1:]),
                    (before, dict(after, uptime_ms=0), events)]
        for args in failures:
            with self.subTest(after=args[1]), self.assertRaises(RuntimeError): tool.repeat_admission(*args)

    def test_other_cases_and_latch_cannot_add_unexplained_drops(self):
        bench = tool.Bench(FakeSession(), MemoryJournal())
        bench.performance_baseline = performance(generated_drops=7)
        baseline = dict.fromkeys(tool.FAILURES, 0); baseline.update(audio_halves=10)
        state = dict(baseline, audio_halves=11, maximum_render_us=100)
        with patch.object(tool.legacy, "query", return_value=state), patch.object(bench, "trace"):
            with patch.object(bench, "performance", return_value=performance(generated_drops=9)), self.assertRaisesRegex(RuntimeError, "generated_drops"):
                bench.check(baseline)
            bench.expected_generated_drops = 32
            with patch.object(bench, "performance", return_value=performance(generated_drops=39)):
                bench.check(baseline)
            with patch.object(bench, "performance", return_value=performance(generated_drops=41)), self.assertRaisesRegex(RuntimeError, "generated_drops"):
                bench.check(baseline)


if __name__ == "__main__": unittest.main()
