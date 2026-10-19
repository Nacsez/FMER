#!/usr/bin/env python3
"""Bounded, logged RAM-only feature bench for exact FMER704/705/706/707; never flashes.

Sends quiet channel16 notes, edits canonical controls and exercises virtual
panel events. These establish transport/state/timing, not audible fidelity or
physical encoder wiring. Always attempts note/pedal cleanup and initial-state
restoration. Keep the automatic recorder closed while this owns the MIDI port.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import sys
import uuid
import fm1_bench as legacy
import fm1_flash_transport as transport
import fm1_session as telemetry
import hardware_bridge as bridge

PREFIX = telemetry.PREFIX
FAILURES = ("overruns", "midi_overflows", "rejected_messages", "load_sheds",
            "lcd_timeouts", "retained_crash_count", "dsp_init_failed", "audio_paused")
NOTES = (60, 64, 67, 71)
EFFECT_IDS = (168, 169, 170, 173, 174)
# Independent row/column view of the audited physical matrix. -1 has no key;
# column8/row1 is the separate green PLAY emitter, never a button bit.
LED_MATRIX = ((5,11,4,10,3,9,2,8,-1,-1,-1), (34,35,36,37,38,40,39,13,7,6,12),
              (23,24,25,26,27,28,29,30,31,32,33), (0,1,15,14,17,16,19,18,20,21,22))
LED_POSITIONS = {identifier: (column, 1 << row) for row, columns in enumerate(LED_MATRIX, 1)
                 for column, identifier in enumerate(columns) if identifier >= 0}
DEFAULT_REFERENCE_FILES = (
    ("artifacts/fm1-session-review/705-20261006/boot-default-controls.json", "458ac1026af4f633ce065522a0210a90aa20787c01c77b75876b33aaed150ed2"),
    ("artifacts/fm1-session-review/705-20261006/pattern-before-and-after-reset.json", "71cf8e69374ae80b1ebbce54c7f5938b4f2905457e7e832cd6419960444b1983"))


def load_default_reference():
    records, pins = [], []
    for name, digest in DEFAULT_REFERENCE_FILES:
        raw = (transport.ROOT / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Audited boot-default reference hash changed: " + name)
        records.append(json.loads(raw))
        pins.append(dict(path=name, sha256=digest))
    controls, pattern = records[0], records[1]["after"]
    if (not controls.get("consistent") or controls.get("count") != 193 or len(controls["values"]) != 193 or
            not pattern.get("consistent") or pattern.get("count") != 64 or len(pattern["steps"]) != 64 or
            not 1 <= pattern["length"] <= 64):
        raise ValueError("Audited boot-default records are incomplete/inconsistent")
    for identifier, value in enumerate(controls["values"]):
        if 145 <= identifier < 160:
            if value != 0: raise ValueError("Reserved boot default is nonzero")
        else: parameter_packet(identifier, value)
    for step in pattern["steps"]:
        if len(step) != 3: raise ValueError("Invalid reference pattern cell")
        for identifier, value in zip((188, 189, 190), step): parameter_packet(identifier, value)
    if (controls["values"][186] != pattern["length"] or controls["values"][187] != 0 or
            controls["values"][188:191] != pattern["steps"][0]):
        raise ValueError("Audited default controls/pattern disagree")
    return dict(controls=controls["values"], steps=pattern["steps"], length=pattern["length"], source_files=pins,
                scope="Observed705 cold-boot defaults audited against unchanged706 initialization; no reset command")


def audit_defaults(bench, result, reference):
    """Strict read-only comparison, usable before and after musical benches."""
    result["before"] = legacy.query(bench.session, bench.journal, 2)
    before = bench.performance()
    controls = bench.controls()
    pattern = telemetry.pattern_snapshot(bench.session, bench.journal)
    leds = telemetry.led_state(bench.session, bench.journal)
    after = bench.performance()
    wrong_controls = [i for i, values in enumerate(zip(controls, reference["controls"])) if values[0] != values[1]]
    wrong_steps = [i for i, values in enumerate(zip(pattern["steps"], reference["steps"])) if values[0] != values[1]]
    lit = [0] * 11; lit[7] = 2  # Only HOME at the neutral octave.
    coherent = (before["controls_generation"] == after["controls_generation"] == after["controls_applied"] and
                before["performance_revision"] == after["performance_revision"] and
                after["uptime_ms"] >= before["uptime_ms"] and after["trace_newest"] >= before["trace_newest"])
    quiet = not any(after[key] for key in ("seq_running", "seq_recording", "arp_held", "performance_errors"))
    clean_leds = (leds["family"] == 0 and leds["octave_plus3"] == 3 and not leds["held_buttons"] and
                  not leds["physical_keys"] and not leds["flags"] and not leds["active_voices"] and
                  not leds["active_pitches"] and not leds["gated_pitches"] and leds["lit"] == lit and leds["dim"] == [0] * 11)
    result["defaults"] = dict(reference=reference, controls=controls, pattern=pattern, leds=leds,
                               mismatched_controls=wrong_controls, mismatched_steps=wrong_steps,
                               coherent=coherent, quiet=quiet, home_leds=clean_leds,
                               performance_before=before, performance_after=after)
    if (len(controls) != 193 or len(pattern["steps"]) != 64 or wrong_controls or wrong_steps or
            pattern["length"] != reference["length"] or not coherent or not quiet or not clean_leds or
            any(result["before"][key] for key in FAILURES) or result["before"]["active_voices"]):
        raise RuntimeError("Read-only audit differs from the reviewed cold-boot defaults or idle HOME state")
    bench.journal.record("default_audit_passed", controls=193, retained_steps=64, writes=False)


def led_level(state, identifier):
    if identifier not in LED_POSITIONS:
        raise ValueError("Unknown physical LED identifier")
    column, mask = LED_POSITIONS[identifier]
    return 2 if state["lit"][column] & mask else 1 if state["dim"][column] & mask else 0


def green_play_level(state):
    return 2 if state["lit"][8] & 2 else 1 if state["dim"][8] & 2 else 0


def pitch_led_level(state, pitch):
    identifier = pitch - (53 + 12 * (state["octave_plus3"] - 3)) + 14
    if not 14 <= identifier <= 40:
        raise ValueError("Pitch is outside the currently displayed keyboard")
    return led_level(state, identifier)


def wait_leds(bench, predicate, label, *, timeout=1.5):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = telemetry.led_state(bench.session, bench.journal, identity=bench.identity)
        if predicate(latest):
            bench.trace()
            return latest
        time.sleep(.005)
    bench.journal.record("led_assertion_failed", assertion=label, latest=latest)
    raise RuntimeError("LED state did not settle: " + label)


def set_octave(bench, wanted):
    if type(wanted) is not int or not 0 <= wanted <= 6:
        raise ValueError("Octave readback must be0..6")
    current = telemetry.led_state(bench.session, bench.journal, identity=bench.identity)["octave_plus3"]
    for _ in range(6):
        if current == wanted: return
        next_value = current + (1 if wanted > current else -1)
        bench.button(1 if next_value > current else 0)
        current = wait_leds(bench, lambda state: state["octave_plus3"] == next_value,
                            "octave=" + str(next_value))["octave_plus3"]
    if current != wanted:
        raise RuntimeError("Octave restoration exceeded physical bounds")


def parameter_bounds(identifier, *, parameter_count=193, fx=False, workstation=False, projects=False,sync=False,polish=False):
    if type(parameter_count) is not int or parameter_count not in (193, 195, 198):
        raise ValueError("Unsupported canonical registry count")
    if sync:
        if not projects or not workstation or not fx:raise ValueError('Sync requires full722 registry')
        return (telemetry.native_v8 if polish else telemetry.native_v7).control_bounds(identifier)
    if projects and not workstation:raise ValueError('Projects require workstation controls')
    if projects and identifier in (158,195,197):return telemetry.native_v5.control_bounds(identifier)
    if workstation and parameter_count!=198:raise ValueError('Workstation registry requires198 controls')
    if type(identifier) is not int or not 0 <= identifier < parameter_count or (159 if workstation else 150 if fx else 145) <= identifier < 160 or (145<=identifier<150 and not fx):
        raise ValueError("Parameter outside the canonical registry")
    if workstation and 150<=identifier<159:
        return telemetry.native_v4.control_bounds(identifier)
    if fx and 145<=identifier<150:
        if parameter_count!=198:raise ValueError('FX registry requires198 controls')
        return 0,(2,100,1,1,1)[identifier-145]
    if identifier < 126:
        return 0, (99,99,99,99,99,99,99,99,99,99,99,3,3,7,3,7,99,1,31,99,14)[identifier % 21]
    if identifier < 145:
        return 0, (99,99,99,99,99,99,99,99,31,7,1,99,99,99,99,1,5,7,48)[identifier - 126]
    minima = {162:20,177:20,171:20,175:10,178:20,181:1,182:1,186:1,189:1,190:1,191:1,185:50}
    maxima = {160:1,179:1,184:1,192:1,161:3,162:20000,177:18000,163:95,164:10000,165:10000,
              167:10000,171:1000,175:1000,172:85,178:300,180:6,181:32,182:4,191:4,185:75,
              186:64,187:63,188:128,189:127,193:16}
    if parameter_count == 198:
        minima[197] = 1
        maxima.update({180:9,195:7,196:1,197:255})
    if workstation:maxima[188]=129
    return minima.get(identifier, 0), maxima.get(identifier, 100)


def parameter_packet(identifier, value, *, parameter_count=193, fx=False, workstation=False, projects=False,sync=False,polish=False):
    low, high = parameter_bounds(identifier, parameter_count=parameter_count,fx=fx,workstation=workstation,projects=projects,sync=sync,polish=polish)
    if type(value) is not int or not low <= value <= high or (identifier == 181 and value & (value - 1)):
        raise ValueError("Parameter exceeds canonical bounds")
    return PREFIX + bytes([7, identifier & 127, identifier >> 7,
                           value & 127, (value >> 7) & 127, value >> 14, 247])


def panel_packet(kind, identifier, value):
    if any(type(n) is not int for n in (kind, identifier, value)) or not ((kind == 1 and 0 <= identifier < 7 and -64 <= value <= 63) or
            (kind == 2 and 0 <= identifier < 14 and value in (0, 1))):
        raise ValueError("Invalid virtual panel action")
    return PREFIX + bytes([10, kind, identifier, value + 64, 247])


def repeat_admission(before, after, events):
    """Exact Repeat case: notes60/64/67, two octaves, four attacks per block.

    Startup/release can expose a proper subset of the held notes. Each subset
    has a unique sorted admission prefix, so the trace determines its expected
    requested/admitted/skipped counts without guessing a wall-clock step count.
    """
    if (after["uptime_ms"] < before["uptime_ms"] or after["trace_newest"] < before["trace_newest"] or
            any(after[key] < before[key] for key in ("generated_drops", "emitted_notes"))):
        raise RuntimeError("Repeat admission counters reset")
    patterns = {}
    for mask in range(1, 8):
        held = [pitch for index, pitch in enumerate(NOTES[:3]) if mask & (1 << index)]
        expanded = sorted(pitch + 12 * octave for octave in range(2) for pitch in held)
        patterns[tuple(expanded[:4])] = len(expanded)
    groups = defaultdict(list)
    for event in events:
        if not before["trace_newest"] < event["seq"] <= after["trace_newest"] or event["kind"] != 10 or event["value"] <= 0:
            continue
        if event["source"] != 5 or event["value"] != 32:
            raise RuntimeError("Unexpected generated source/velocity in Repeat case")
        groups[event["audio_frame_low32"]].append(event["pitch"])
    requested = admitted = expected_drops = saturated = 0
    for pitches in groups.values():
        candidate_count = patterns.get(tuple(pitches))
        if candidate_count is None:
            raise RuntimeError("Repeat trace does not match a known held-note admission group")
        requested += candidate_count
        admitted += len(pitches)
        expected_drops += candidate_count - len(pitches)
        saturated += candidate_count == 6
    observed_drops = after["generated_drops"] - before["generated_drops"]
    observed_admitted = after["emitted_notes"] - before["emitted_notes"]
    if not saturated or observed_drops != expected_drops or observed_admitted != admitted:
        raise RuntimeError("Repeat admission counters do not match complete generated-note trace")
    return dict(policy="Repeat three held notes x two octaves, four-attack budget", groups=len(groups),
                six_note_groups=saturated, partial_groups=len(groups) - saturated,
                requested_attacks=requested, admitted_attacks=admitted, expected_drops=expected_drops,
                observed_drops=observed_drops, observed_emitted=observed_admitted)


class RecoveryJournal:
    """Only cleanup/restoration can continue when durable logging fails."""
    def __init__(self, original):
        self.original = original
        self.records = []
        self.failures = []
        self.dropped = 0

    def record(self, event, **values):
        try:
            self.original.record(event, **values)
        except Exception as error:
            if len(self.failures) < 16 and repr(error) not in self.failures:
                self.failures.append(repr(error))
            if len(self.records) < 128:
                self.records.append({"event": event, "utc": datetime.now(timezone.utc).isoformat(), **values})
            else:
                self.dropped += 1


class Bench:
    def __init__(self, session, journal, *, identity="FM-1_706"):
        self.session, self.journal = session, journal
        self.identity = telemetry.require_identity(identity)
        self.parameter_count = telemetry.parameter_count(identity)
        self.cursor = 0
        self.events = []
        self.peak_render = self.peak_control = 0
        self.uptime = None
        self.held_buttons = set()
        self.recovery_logs = []
        self.performance_baseline = None
        self.expected_generated_drops = 0

    @contextmanager
    def recovery_logging(self):
        if isinstance(self.journal, RecoveryJournal):
            yield
            return
        original = self.journal
        session_journal = getattr(self.session, "journal", None)
        replacement = RecoveryJournal(original)
        self.journal = self.session.journal = replacement
        try:
            yield
        finally:
            self.journal, self.session.journal = original, session_journal
            if replacement.failures:
                self.recovery_logs.append({"logging_errors": replacement.failures,
                                           "retained_records": replacement.records, "dropped_fallback_records": replacement.dropped})

    def echo(self, packet, label):
        reply = telemetry.request(self.session, packet, label)
        if reply != packet:
            raise RuntimeError(label + " echo mismatch")

    def performance(self):
        result = telemetry.parse_performance(telemetry.request(
            self.session, PREFIX + bytes([8, 247]), "bench_performance_read"),
            maximum_pitch=129 if self.identity in telemetry.WORKSTATION_IDENTITIES else 128,pattern_banks=16 if self.identity in telemetry.PROJECT_IDENTITIES else 8)
        self.journal.record("performance", **result)
        self.peak_control = max(self.peak_control, result["max_control_us"])
        return result

    def controls(self):
        before = self.performance()
        result = []
        for start in range(0, self.parameter_count, 24):
            result.extend(telemetry.parse_controls(telemetry.request(
                self.session, telemetry.controls_request(start, count=self.parameter_count), "bench_control_read"),
                start, parameter_count=self.parameter_count,fx=self.identity in telemetry.FX_IDENTITIES,
                workstation=self.identity in telemetry.WORKSTATION_IDENTITIES,projects=self.identity in telemetry.PROJECT_IDENTITIES,sync=self.identity in telemetry.SYNC_IDENTITIES,polish=self.identity in (telemetry.POLISH_IDENTITY,telemetry.WORKFLOW_IDENTITY,telemetry.ROUTING_IDENTITY)))
        after = self.performance()
        consistent = (before["controls_generation"] == after["controls_generation"] and
                      before["performance_revision"] == after["performance_revision"] and
                      after["uptime_ms"] >= before["uptime_ms"] and after["trace_newest"] >= before["trace_newest"])
        self.journal.record("control_snapshot", values=result, before=before, after=after, consistent=consistent)
        if not consistent:
            raise RuntimeError("Controls changed during bench snapshot")
        return result

    def set(self, identifier, value):
        self.echo(parameter_packet(identifier, value, parameter_count=self.parameter_count,fx=self.identity in telemetry.FX_IDENTITIES,
                                   workstation=self.identity in telemetry.WORKSTATION_IDENTITIES,projects=self.identity in telemetry.PROJECT_IDENTITIES,sync=self.identity in telemetry.SYNC_IDENTITIES,polish=self.identity in (telemetry.POLISH_IDENTITY,telemetry.WORKFLOW_IDENTITY,telemetry.ROUTING_IDENTITY)), "bench_parameter_write")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = self.performance()
            if state["controls_generation"] == state["controls_applied"]:
                # The matching generation is adoption, not just a queue echo.
                page = telemetry.parse_controls(telemetry.request(
                    self.session, telemetry.controls_request(identifier, count=self.parameter_count), "bench_parameter_readback"),
                    identifier, parameter_count=self.parameter_count,fx=self.identity in telemetry.FX_IDENTITIES,
                    workstation=self.identity in telemetry.WORKSTATION_IDENTITIES,projects=self.identity in telemetry.PROJECT_IDENTITIES,sync=self.identity in telemetry.SYNC_IDENTITIES,polish=self.identity in (telemetry.POLISH_IDENTITY,telemetry.WORKFLOW_IDENTITY,telemetry.ROUTING_IDENTITY))
                if page[0] != value:
                    raise RuntimeError(f"Parameter {identifier} readback {page[0]} != {value}")
                return
            time.sleep(.005)
        raise RuntimeError("Control generation not adopted")

    def transport(self, command):
        if type(command) is not int or command not in range(1, 9 if self.identity in telemetry.SYNC_IDENTITIES else 6):
            raise ValueError("Invalid transport command")
        self.echo(PREFIX + bytes([9, command, 247]), "bench_transport")
        time.sleep(.025)

    def panel(self, kind, identifier, value):
        packet = panel_packet(kind, identifier, value)
        if kind == 2 and value:
            self.held_buttons.add(identifier)  # Include a press whose echo is lost.
        self.echo(packet, "bench_virtual_panel")
        if kind == 2 and not value:
            self.held_buttons.discard(identifier)

    def button(self, identifier):
        self.panel(2, identifier, 1)
        self.panel(2, identifier, 0)

    def notes(self, pitches=NOTES, on=True):
        for pitch in pitches:
            legacy.short_message(self.session, self.journal, 0x9F if on else 0x8F, pitch, 32 if on else 0)

    def cleanup(self):
        errors = []
        old_logs = len(self.recovery_logs)
        with self.recovery_logging():
            actions = [lambda identifier=identifier: self.panel(2, identifier, 0) for identifier in sorted(self.held_buttons)]
            actions += [lambda: legacy.short_message(self.session, self.journal, 0xBF, 64, 0),
                        lambda: legacy.cleanup_notes(self.session, self.journal, NOTES), lambda: self.transport(5)]
            for action in actions:
                try: action()
                except Exception as error: errors.append(str(error))
        if len(self.recovery_logs) > old_logs:
            errors.append("Cleanup attempted with failed durable logging; fallback records retained")
        if errors:
            raise RuntimeError("Cleanup: " + "; ".join(errors))

    def trace(self, initial=False):
        for _ in range(64):
            batch = telemetry.parse_trace(telemetry.request(
                self.session, telemetry.trace_request(self.cursor), "bench_trace_read"),
                maximum_storage_action=12 if self.identity == telemetry.DEFAULTS_IDENTITY else 10 if self.identity in telemetry.PROJECT_IDENTITIES else 6 if self.identity in telemetry.MIDI_IDENTITIES else 5,
                allow_native_timing=self.identity in telemetry.PROJECT_IDENTITIES)
            lost = max(0, batch["oldest_seq"] - self.cursor - 1)
            if batch["newest_seq"] < self.cursor or (self.uptime is not None and batch["uptime_ms"] < self.uptime):
                raise RuntimeError("Target trace reset during feature bench")
            expected_start = max(self.cursor + 1, batch["oldest_seq"])
            expected_count = min(6, max(0, batch["newest_seq"] - expected_start + 1))
            if len(batch["events"]) != expected_count or (batch["events"] and batch["events"][0]["seq"] != expected_start):
                raise RuntimeError("Target trace skipped or repeated requested events")
            self.journal.record("target_event_batch", initial=initial, dropped_events=lost, **batch)
            if lost and not initial:
                raise RuntimeError(f"Feature bench missed {lost} target events")
            if not initial:
                self.events.extend(batch["events"])
            self.uptime = batch["uptime_ms"]
            if batch["events"]:
                self.cursor = batch["events"][-1]["seq"]
            if self.cursor >= batch["newest_seq"]:
                return
        raise RuntimeError("Trace producer exceeded bounded bench drain")

    def check(self, baseline):
        state = legacy.query(self.session, self.journal, 2)
        self.peak_render = max(self.peak_render, state["maximum_render_us"])
        if any(state[k] != baseline[k] for k in FAILURES):
            raise RuntimeError("New failure counters: " + str({k: (baseline[k], state[k]) for k in FAILURES if state[k] != baseline[k]}))
        if state["audio_halves"] <= baseline["audio_halves"]:
            raise RuntimeError("Audio did not advance")
        performance = self.performance()
        if self.performance_baseline is not None:
            for key in ("performance_errors", "generated_drops"):
                expected = self.performance_baseline[key] + (self.expected_generated_drops if key == "generated_drops" else 0)
                if performance[key] != expected:
                    raise RuntimeError("Performance engine counter advanced: " + key)
        self.trace()
        return state


def restore_state(bench, result, original, saved_steps):
    errors = []
    old_logs = len(bench.recovery_logs)
    with bench.recovery_logging():
        actions = [("panic and release", bench.cleanup), ("disable arp", lambda: bench.set(179, 0))]
        if saved_steps:
            actions.append(("expand for saved steps", lambda: bench.set(186, max(original[186], max(saved_steps) + 1))))
        for step, values in saved_steps.items():
            actions.append((f"select saved step {step}", lambda step=step: bench.set(187, step)))
            for identifier, value in zip(range(188, 191), values):
                actions.append((f"restore step {step} parameter {identifier}", lambda identifier=identifier, value=value: bench.set(identifier, value)))
        for identifier, value in enumerate(original):
            if 145 <= identifier < 160 or identifier in (179, 186, 187, 188, 189, 190):
                continue
            actions.append((f"restore parameter {identifier}", lambda identifier=identifier, value=value: bench.set(identifier, value)))
        actions.extend([("restore length", lambda: bench.set(186, original[186])),
                        ("restore selected step", lambda: bench.set(187, original[187])),
                        ("final panic", bench.cleanup), ("restore arp enable", lambda: bench.set(179, original[179])),
                        ("return HOME", lambda: bench.button(8))])
        if "original_octave_plus3" in result:
            actions.append(("restore octave", lambda: set_octave(bench, result["original_octave_plus3"])))
        for index, (label, action) in enumerate(actions):
            try: action()
            except Exception as error: errors.append({"action": label, "error": repr(error)})
            if index % 8 == 7:
                try: bench.trace()
                except Exception as error: errors.append({"action": "drain restoration trace", "error": repr(error)})
        try:
            restored = bench.controls()
            result["restored_controls"] = restored
            mismatches = [i for i, (old, new) in enumerate(zip(original, restored)) if old != new]
            if len(restored) != len(original) or mismatches:
                errors.append({"action": "verify restored controls", "mismatched_ids": mismatches})
            state = bench.performance()
            result["restored_performance"] = state
            if state["seq_running"] or state["seq_recording"] or state["arp_held"]:
                errors.append({"action": "verify stopped performance", "error": "performance state is not idle"})
        except Exception as error:
            errors.append({"action": "verify restored state", "error": repr(error)})
    if len(bench.recovery_logs) > old_logs:
        errors.append({"action": "restoration logging", "error": "durable log failed; bounded fallback records retained"})
    result["cleanup_errors"] = errors
    result["recovery_logging"] = bench.recovery_logs
    result["restoration_scope"] = "Canonical controls and modified mono steps; stopped transport; panel returns HOME, inactive page memories are not restored"
    return errors


def panel705_checks(bench, result, baseline):
    """Virtual705 panel routing and readback; does not inspect physical pixels.

    Existing outer restoration owns the canonical controls. This helper only
    selects retained steps; it never changes their pitch/velocity/gate contents.
    """
    def expect(identifier, value, *, family=None, page=None):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = bench.performance()
            if (state["controls_generation"] == state["controls_applied"] and
                    (family is None or state["page_family"] == family) and
                    (page is None or state["page_index"] == page)):
                values = bench.controls()
                if values[identifier] == value:
                    bench.trace()
                    return state
            time.sleep(.005)
        raise RuntimeError(f"705 panel failed parameter{identifier}={value}, family={family}, page={page}")

    cases = result["cases"]
    bench.cleanup()
    bench.set(179, 0)
    bench.set(184, 0)
    bench.button(8)
    bench.set(170, 0)
    bench.panel(1, 4, 1)
    coarse = expect(170, 5, family=0, page=0)
    bench.set(170, 0)
    bench.panel(2, 3, 1)
    bench.panel(1, 4, 1)
    bench.panel(2, 3, 0)
    fine = expect(170, 1, family=0, page=0)
    bench.set(162, 1234)
    bench.panel(1, 2, 1)
    expect(162, 1600, family=0)
    bench.set(162, 1234)
    bench.panel(2, 3, 1)
    bench.panel(1, 2, 1)
    bench.panel(2, 3, 0)
    expect(162, 1235, family=0)
    cases.append(dict(case="705 coarse and SEL fine edits", coarse=coarse, fine=fine,
                      frequency_values=[1234, 1600, 1235], physical_pixels_observed=False))

    # Entering ARP must leave enable unchanged; repeated presses toggle it.
    bench.button(10)
    entered = expect(179, 0, family=5)
    for enabled in (1, 0, 1, 0):
        bench.button(10)
        expect(179, enabled, family=5, page=entered["page_index"])
    # Holding SEL for a fine edit must not also page on release.
    bench.panel(1, 0, 1 - entered["page_index"])
    expect(179, 0, family=5, page=1)
    bench.set(183, 65)
    bench.panel(2, 3, 1)
    bench.panel(1, 3, 1)  # ARP GATE/LATCH K2 is gate.
    bench.panel(2, 3, 0)
    expect(183, 66, family=5, page=1)
    bench.button(3)  # An unused short SEL release still pages.
    expect(183, 66, family=5, page=2)
    cases.append(dict(case="705 repeated ARP and SEL release routing", after=bench.check(baseline)))

    # Toggle arp while notes remain physically owned by this bench's USB route.
    # One octave keeps requested attacks within the four-attack budget.
    bench.set(180, 0)
    bench.set(182, 1)
    bench.notes(NOTES[:3])
    bench.button(10)
    expect(179, 1, family=5, page=2)
    time.sleep(.15)
    if bench.performance()["arp_held"] != 3:
        raise RuntimeError("705 repeated ARP did not acquire held notes")
    bench.button(10)
    expect(179, 0, family=5, page=2)
    if legacy.query(bench.session, bench.journal, 2)["active_voices"] != 3:
        raise RuntimeError("705 repeated ARP did not restore held live notes")
    bench.notes(NOTES[:3], on=False)
    bench.cleanup()
    cases.append(dict(case="705 ARP button toggles with held chord", after=bench.check(baseline)))

    old_length = bench.controls()[186]
    bench.set(186, 32)
    bench.button(11)
    seq_page = bench.performance()["page_index"]
    if seq_page:
        bench.panel(1, 0, -seq_page)
    bench.set(187, 15)
    bench.panel(1, 2, 1)  # Crossing16 selects the next grid bank.
    expect(187, 16, family=6, page=0)
    snapshot = telemetry.pattern_snapshot(bench.session, bench.journal)
    selected = bench.controls()
    if snapshot["length"] != 32 or selected[188:191] != snapshot["steps"][16]:
        raise RuntimeError("705 grid selection and full pattern snapshot disagree")
    bench.panel(1, 2, -1)
    expect(187, 15, family=6, page=0)
    bench.set(186, old_length)
    cases.append(dict(case="705 grid bank boundary and64-step readback", selected_bank=1,
                      selected_step=16, pattern=snapshot, physical_pixels_observed=False,
                      after=bench.check(baseline)))


def led706_checks(bench, result, baseline):
    """Settled commanded matrix checks; no fault injection or optical claim."""
    cases = result["cases"]
    bench.cleanup()
    bench.set(179, 0)
    bench.set(184, 0)
    set_octave(bench, 3)
    frames = []
    for family, button in enumerate((8, 6, 4, 2, 5, 10, 11, 7, 9)):
        if bench.identity == "FM-1_707" and button == 9:
            continue  # SAVE now requests a native backup; the dedicated707 bench owns its acknowledgement.
        bench.button(button)
        level = 0 if family == 8 else 1 if family == 5 else 2
        frames.append(wait_leds(bench, lambda state: state["family"] == family and not state["held_buttons"] and
                               led_level(state, button) == level, "selected page"))
    save_pressed = None
    if bench.identity != "FM-1_707":
        bench.panel(2, 9, 1)
        save_pressed = wait_leds(bench, lambda state: state["held_buttons"] & (1 << 9) and led_level(state, 9) == 1,
                                 "SAVE acknowledges press without saved status")
        bench.panel(2, 9, 0)
        wait_leds(bench, lambda state: not state["held_buttons"] and led_level(state, 9) == 0, "SAVE release")
    bench.panel(2, 3, 1)
    fine = wait_leds(bench, lambda state: state["flags"] & 1 and led_level(state, 3) == 2, "held SEL")
    bench.panel(2, 3, 0)
    wait_leds(bench, lambda state: not state["flags"] & 1 and led_level(state, 3) == 0, "released SEL")
    cases.append(dict(case="706 LED page and button semantics", pages=frames, save_pressed=save_pressed, fine=fine,
                      save_scope="707 SAVE request/acknowledgement is excluded here; dedicated native bench required" if bench.identity=="FM-1_707" else "legacy informational SAVE press and release",
                      physical_illumination_observed=False))

    bench.button(8)
    octaves = []
    for octave in (4, 2, 3):
        set_octave(bench, octave)
        octaves.append(wait_leds(bench, lambda state: led_level(state, 0) == (2 if octave < 3 else 0) and
                                 led_level(state, 1) == (2 if octave > 3 else 0), "octave direction"))
    cases.append(dict(case="706 LED octave directions", frames=octaves))

    for identifier, value in ((160, 1), (161, 1), (164, 2), (165, 50), (166, 70), (167, 500), (191, 4)):
        bench.set(identifier, value)
    for identifier in EFFECT_IDS: bench.set(identifier, 0)
    bench.notes((60, 64, 67))
    gated = wait_leds(bench, lambda state: state["gated_pitches"] == [60, 64, 67] and
                      all(pitch_led_level(state, pitch) == 2 for pitch in (60, 64, 67)), "USB gated chord")
    bench.notes((60, 64, 67), on=False)
    tails = wait_leds(bench, lambda state: not state["gated_pitches"] and set((60, 64, 67)) <= set(state["active_pitches"]) and
                      all(pitch_led_level(state, pitch) == 1 for pitch in (60, 64, 67)), "released chord tails")
    ended = wait_leds(bench, lambda state: not state["active_pitches"] and
                      all(pitch_led_level(state, pitch) == 0 for pitch in (60, 64, 67)), "finished tails", timeout=2)
    cases.append(dict(case="706 LED gates and release tails", gated=gated, tails=tails, ended=ended))

    bench.notes((60,))
    wait_leds(bench, lambda state: state["gated_pitches"] == [60], "sustain note admitted")
    legacy.short_message(bench.session, bench.journal, 0xBF, 64, 127)
    bench.notes((60,), on=False)
    sustained = wait_leds(bench, lambda state: state["gated_pitches"] == [60] and pitch_led_level(state, 60) == 2,
                          "sustain keeps actual gate bright")
    legacy.short_message(bench.session, bench.journal, 0xBF, 64, 0)
    released = wait_leds(bench, lambda state: not state["gated_pitches"] and 60 in state["active_pitches"] and
                         pitch_led_level(state, 60) == 1, "pedal release tail")
    bench.cleanup()
    cases.append(dict(case="706 LED sustain ownership", sustained=sustained, released=released))

    chord = (60, 64, 67, 71, 74)
    bench.notes(chord)
    stolen = wait_leds(bench, lambda state: state["active_voices"] == 4 and state["gated_pitches"] == [64, 67, 71, 74] and
                       pitch_led_level(state, 60) == 0, "stolen pitch clears without stale latch")
    bench.notes(chord, on=False)
    bench.cleanup()
    cases.append(dict(case="706 LED stolen voice cleanup", after=stolen))

    for identifier, value in ((180, 0), (181, 16), (182, 1), (183, 50), (179, 1)):
        bench.set(identifier, value)
    waiting = wait_leds(bench, lambda state: state["flags"] & 8 and not state["flags"] & 16 and led_level(state, 10) == 2,
                        "enabled arp waits visibly")
    bench.notes((60, 64, 67))
    arp_on = wait_leds(bench, lambda state: state["flags"] & 16 and state["gated_pitches"] and led_level(state, 10) == 2,
                       "actual arp gate")
    arp_between = wait_leds(bench, lambda state: state["flags"] & 16 and not state["gated_pitches"] and led_level(state, 10) == 1,
                            "arp between gates")
    bench.notes((60, 64, 67), on=False)
    bench.set(179, 0)
    bench.cleanup()
    cases.append(dict(case="706 LED arp gates", waiting=waiting, gate=arp_on, between=arp_between))

    bench.button(8)
    bench.button(12)
    on = wait_leds(bench, lambda state: state["flags"] & 2 and state["flags"] & 32 and
                   green_play_level(state) == 2 and led_level(state, 11) == 2, "sequencer beat")
    between = wait_leds(bench, lambda state: state["flags"] & 2 and not state["flags"] & 32 and
                        green_play_level(state) == 1 and led_level(state, 11) == 1, "sequencer between beats")
    bench.button(12)
    wait_leds(bench, lambda state: not state["flags"] & 2 and green_play_level(state) == 0, "sequencer stopped")
    bench.button(13)
    recorded = wait_leds(bench, lambda state: state["flags"] & 4 and led_level(state, 13) == 2,
                         "armed recording")
    bench.button(13)
    wait_leds(bench, lambda state: not state["flags"] & 4 and led_level(state, 13) == 0, "recording disarmed")
    cases.append(dict(case="706 LED sequencer and recording", beat=on, between=between, recording=recorded))

    bench.button(12)
    wait_leds(bench, lambda state: state["flags"] & 2, "run before panic")
    bench.panel(2, 12, 1)
    wait_leds(bench, lambda state: state["held_buttons"] & (1 << 12) and led_level(state, 12) == 2, "held PLAY feedback")
    time.sleep(.85)
    bench.panel(2, 12, 0)
    panic = wait_leds(bench, lambda state: not state["flags"] & (2 | 4 | 16) and not state["active_pitches"] and
                      green_play_level(state) == 0 and led_level(state, 12) == 0, "panic clears run and voice LEDs")
    bench.cleanup()
    cases.append(dict(case="706 LED panic cleanup", after=panic, diagnostics=bench.check(baseline)))


def run(bench, result):
    if result.get("identity", bench.identity) != bench.identity:
        raise ValueError("Bench registry identity differs from requested firmware")
    before = result["before"] = legacy.query(bench.session, bench.journal, 2)
    if before["active_voices"] or before["audio_paused"] or before["dsp_init_failed"]:
        raise RuntimeError("Feature bench requires idle, available DSP")
    initial_perf = bench.performance()
    if initial_perf["seq_running"] or initial_perf["seq_recording"] or initial_perf["arp_held"]:
        raise RuntimeError("Feature bench requires stopped performance state")
    if initial_perf["controls_generation"] != initial_perf["controls_applied"]:
        raise RuntimeError("Feature bench requires all original controls adopted")
    bench.performance_baseline = initial_perf
    result["initial_performance"] = initial_perf
    original = bench.controls()
    for identifier, value in enumerate(original):
        if not 145 <= identifier < 160:
            parameter_packet(identifier, value, parameter_count=bench.parameter_count)
    if original[187] >= original[186]:
        raise RuntimeError("Original selected step lies outside its sequence")
    result["original_controls"] = original
    bench.trace(initial=True)
    if result.get("identity") in ("FM-1_706", "FM-1_707"):
        initial_leds = telemetry.led_state(bench.session, bench.journal, identity=bench.identity)
        if initial_leds["held_buttons"] or initial_leds["physical_keys"]:
            raise RuntimeError("LED feature bench requires released physical/virtual inputs")
        result["original_octave_plus3"] = initial_leds["octave_plus3"]
        result["original_leds"] = initial_leds
    cases = result["cases"] = []
    saved_steps = {}
    try:
        bench.transport(5)
        if bench.parameter_count == 195:
            bench.set(193, 0)  # The bounded note harness uses channel16; restore the owner's channel below.
        bench.set(179, 0)
        for identifier in (168, 169, 170, 173, 174):
            bench.set(identifier, 0)
        bench.set(162, 20000)
        bench.set(191, 4)
        bench.set(160, 0)
        for patch_name in ("original patch", "dense six-operator synthetic"):
            if patch_name.startswith("dense"):
                for operator in range(6):
                    bench.set(operator * 21 + 16, 75)
                    bench.set(operator * 21 + 18, operator + 1)
                bench.set(135, 7)
            for algorithm in range(32):
                bench.set(134, algorithm)
                legacy.reset_peaks(bench.session)
                bench.notes()
                time.sleep(.15)
                during = bench.check(before)
                if during["active_voices"] != 4:
                    raise RuntimeError("FM algorithm failed four-note admission")
                cases.append(dict(case="FM algorithm", patch=patch_name, algorithm=algorithm, during=during))
                bench.cleanup()
        # Other checks use the owner's original patch shape at algorithm31.
        for operator in range(6):
            for offset in (16, 18): bench.set(operator * 21 + offset, original[operator * 21 + offset])
        bench.set(135, original[135])
        bench.set(160, 1)
        for identifier, value in ((164, 2), (165, 200), (166, 75), (167, 50),
                                  (177, 6000), (163, 50), (175, 500), (176, 40)):
            bench.set(identifier, value)
        for wave in range(4):
            bench.set(161, wave)
            legacy.reset_peaks(bench.session)
            bench.notes()
            time.sleep(.3)
            during = bench.check(before)
            if during["active_voices"] != 4:
                raise RuntimeError("VA waveform failed four-note admission")
            bench.notes(on=False)
            time.sleep(.2)
            if bench.check(before)["active_voices"]:
                raise RuntimeError("VA ADSR failed release")
            cases.append(dict(case="VA vibrato/filter/ADSR", wave=wave, during=during))
        # Exercise each new effect separately, then all six with panel activity.
        bench.set(160, 0)
        bench.set(134, 31)
        for effect in (168, 169, 170, 173, 174, -1):
            for identifier in (168, 169, 170, 173, 174):
                bench.set(identifier, 40 if effect in (identifier, -1) else 0)
            bench.set(162, 6000 if effect == -1 else 20000)
            legacy.reset_peaks(bench.session)
            bench.notes()
            if effect == -1:
                for button in (6, 4, 2, 5, 7, 10, 11, 8):
                    bench.button(button)
                    time.sleep(.05)
                bench.panel(1, 2, -1)  # Actual common panel model, HOME cutoff.
                bench.panel(1, 2, 1)
                time.sleep(1.0)
            else:
                time.sleep(.35)
            cases.append(dict(case="effects", effect=effect, during=bench.check(before)))
            bench.cleanup()
        for identifier in (168, 169, 170, 173, 174):
            bench.set(identifier, 0)
        bench.set(162, 20000)
        bench.set(178, 240)
        # Capture every step we will overwrite, including a previously hidden
        # second step when the owner's original length was one. The short test
        # pattern prevents inherited high-velocity notes or empty steps from
        # affecting the PLAY test. Restore its original length afterward.
        bench.set(186, 2)
        for step in (0, 1):
            bench.set(187, step)
            snapshot = bench.controls()
            saved_steps[step] = snapshot[188:191]
        for step, pitch in ((0, 60), (1, 67)):
            bench.set(187, step)
            for identifier, value in ((188, pitch), (189, 32), (190, 75)):
                bench.set(identifier, value)
        bench.set(187, 0)
        start = bench.performance()
        bench.button(12)  # Short PLAY from HOME starts the sequencer.
        time.sleep(.8)
        playing = bench.performance()
        if not playing["seq_running"] or playing["emitted_notes"] <= start["emitted_notes"]:
            raise RuntimeError("Sequence did not start/emit through PLAY")
        bench.set(187, 1)
        selected_while_playing = bench.controls()
        if selected_while_playing[187:191] != [1, 67, 32, 75]:
            raise RuntimeError("Step selection during PLAY did not adopt/read back its selected values")
        bench.button(12)
        stopped = bench.performance()
        if stopped["seq_running"]:
            raise RuntimeError("Sequence did not stop through PLAY")
        cases.append(dict(case="sequence PLAY toggle", playing=playing, stopped=stopped,
                          selected_while_playing=selected_while_playing[187:191]))
        bench.check(before)
        bench.set(187, 0)
        bench.button(13)
        if not bench.performance()["seq_recording"]:
            raise RuntimeError("REC did not enable step entry")
        for pitch in (60, 67):
            bench.notes((pitch,))
            time.sleep(.08)
            bench.notes((pitch,), on=False)
        recorded = bench.performance()
        bench.button(13)
        if recorded["edit_step"] != 0 or bench.performance()["seq_recording"]:
            raise RuntimeError("Step entry did not advance/exit")
        for step, pitch in ((0, 60), (1, 67)):
            bench.set(187, step)
            if bench.controls()[188:190] != [pitch, 32]:
                raise RuntimeError("Recorded pitch/velocity readback mismatch")
        cases.append(dict(case="two-note step entry", state=recorded))
        bench.cleanup()
        bench.check(before)
        for identifier, value in ((181, 16), (182, 2), (183, 65), (184, 0), (185, 58), (192, 1)):
            bench.set(identifier, value)
        for order in range(7):
            bench.set(180, order)
            bench.set(179, 1)
            start = bench.performance()
            bench.notes(NOTES[:3])
            time.sleep(.65)
            playing = bench.performance()
            if playing["arp_held"] != 3 or playing["emitted_notes"] <= start["emitted_notes"]:
                raise RuntimeError("Arp order did not admit/emit held notes")
            bench.notes(NOTES[:3], on=False)
            time.sleep(.08)
            if bench.performance()["arp_held"]:
                raise RuntimeError("Arp lost release ownership")
            bench.set(179, 0)
            bench.cleanup()
            admission = None
            if order == 6:
                after_repeat = bench.performance()
                bench.trace()
                admission = repeat_admission(start, after_repeat, bench.events)
                bench.expected_generated_drops += admission["expected_drops"]
                bench.journal.record("expected_repeat_admission", **admission)
            cases.append(dict(case="arp order", order=order, during=playing, admission=admission, after=bench.check(before)))
        # Disabling arp with held notes must restore their live-note ownership.
        bench.set(180, 0)
        bench.set(179, 1)
        bench.notes(NOTES[:3])
        time.sleep(.1)
        bench.set(179, 0)
        restored_live = legacy.query(bench.session, bench.journal, 2)
        if restored_live["active_voices"] != 3:
            raise RuntimeError("Arp disable did not restore three held live notes")
        bench.notes(NOTES[:3], on=False)
        bench.cleanup()
        cases.append(dict(case="arp disable restores held notes", restored_live=restored_live, after=bench.check(before)))
        # Latch retains notes after release; held PLAY is panic without restart.
        bench.set(180, 6)
        bench.set(184, 1)
        bench.set(179, 1)
        bench.notes(NOTES[:2])
        bench.notes(NOTES[:2], on=False)
        start = bench.performance()
        time.sleep(.25)
        if bench.performance()["emitted_notes"] <= start["emitted_notes"]:
            raise RuntimeError("Latched arp stopped after physical releases")
        bench.panel(2, 12, 1)
        time.sleep(.9)
        bench.panel(2, 12, 0)
        time.sleep(.1)
        stopped = bench.performance()
        if stopped["seq_running"] or stopped["arp_held"] or legacy.query(bench.session, bench.journal, 2)["active_voices"]:
            raise RuntimeError("Held PLAY did not panic, or release restarted transport")
        cases.append(dict(case="arp latch and held PLAY panic", after=stopped))
        bench.set(179, 0)
        bench.check(before)
        if stopped["scope_generation"] <= initial_perf["scope_generation"]:
            raise RuntimeError("Real PCM scope stopped advancing")
        for source in (4, 5):
            events = [e for e in bench.events if e["kind"] == 10 and e["source"] == source]
            if not any(e["value"] > 0 for e in events) or not any(e["value"] == 0 for e in events):
                raise RuntimeError("Missing generated note on/off telemetry")
        if not any(e["kind"] == 1 and e.get("virtual_panel") for e in bench.events):
            raise RuntimeError("Missing explicit virtual encoder telemetry")
        if result.get("identity") in ("FM-1_705", "FM-1_706", "FM-1_707"):
            panel705_checks(bench, result, before)
        if result.get("identity") in ("FM-1_706", "FM-1_707"):
            led706_checks(bench, result, before)
    finally:
        pending = sys.exc_info()[0] is not None
        try:
            errors = restore_state(bench, result, original, saved_steps)
        except Exception as error:
            errors = [{"action": "restoration setup", "error": repr(error)}]
            result["cleanup_errors"] = errors
        if errors and not pending:
            raise RuntimeError("Feature restoration failed: " + repr(errors))
    result["after"] = bench.check(before)
    result["maximum_render_us"] = bench.peak_render
    result["maximum_control_adoption_us"] = bench.peak_control
    result["target_events_retained"] = len(bench.events)
    result["expected_repeat_generated_drops"] = bench.expected_generated_drops


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", choices=("704", "705", "706", "707"), default="706")
    parser.add_argument("--defaults", action="store_true", help="706-only read-only boot-default audit; sends no reset, notes or control writes")
    args = parser.parse_args(argv)
    if args.defaults and args.firmware != "706":
        parser.error("--defaults requires exact firmware706")
    identity = "FM-1_" + args.firmware
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    journal = transport.Journal(transport.ROOT / ("artifacts/fm1-" + args.firmware + "-bench") / stamp)
    result = dict(success=False, identity=identity, flash_writes=False, audio_recorded=False,
                  action="defaults" if args.defaults else "features", volatile_control_writes=not args.defaults,
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    session = None
    try:
        journal.record("bench_start", **result)
        if args.defaults:
            reference = load_default_reference()  # All reference pins checked before opening any port.
            session, _ = telemetry.connect(bridge.WinMM(), journal, expected_identity=identity)
            audit_defaults(Bench(session, journal, identity=identity), result, reference)
        else:
            session = transport.find_session(bridge.WinMM(), identity, journal, wait=2)
            run(Bench(session, journal, identity=identity), result)
        result["success"] = True
    except Exception as error:
        result["error"] = repr(error)
    finally:
        if session is not None:
            try:
                failures = session.close()
                if failures:
                    result.update(success=False, midi_cleanup_errors=failures)
            except Exception as error:
                result.update(success=False, midi_cleanup_errors=[repr(error)])
        try:
            journal.record("bench_finished", **result)
        except Exception as error:
            result.update(success=False, final_logging_error=repr(error))
        try:
            with (journal.directory / "report.json").open("x", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        except Exception as error:
            result.update(success=False, report_write_error=repr(error))
        try:
            journal.close()
        except Exception as error:
            result.update(success=False, journal_close_error=repr(error))
    print(json.dumps(dict(success=result["success"], error=result.get("error"), artifacts=str(journal.directory))))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
