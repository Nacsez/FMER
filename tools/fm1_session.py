#!/usr/bin/env python3
"""FMER704..708 telemetry with optional SAVE-to-PC. No musical/flash writes.

Records target events, diagnostics and canonical controls in durable JSONL.
Rotates without deleting evidence, stops at the configured disk budget, and
reconnects only after clean resource release and an exact firmware handshake.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

import device_protocol
import fm1_bench
import fm1_native_state as native
import fm1_native_state_v2 as native_v2
import fm1_native_state_v3 as native_v3
import fm1_native_state_v4 as native_v4
import fm1_native_state_v5 as native_v5
import fm1_native_state_v6 as native_v6
import fm1_native_state_v7 as native_v7
import fm1_native_state_v8 as native_v8
import fm1_native_state_v9 as native_v9
import fm1_native_state_v10 as native_v10
import fm1_native_state_v11 as native_v11
import fm1_native_state_v12 as native_v12
import fm1_flash_transport as transport
import hardware_bridge

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "FM-1_706"
NATIVE_IDENTITY = "FM-1_707"
ONBOARD_IDENTITY = "FM-1_708"
BANK_IDENTITY = "FM-1_709"
MIDI_IDENTITY = "FM-1_710"
WORKSPACE_IDENTITY = "FM-1_711"
FX_IDENTITY = "FM-1_712"
OPTIMIZED_FX_IDENTITY = "FM-1_713"
FINAL_FX_IDENTITY = "FM-1_714"
SHOWCASE_IDENTITY = "FM-1_715"
TIMBRE_IDENTITY = "FM-1_716"
VISUAL_IDENTITY = "FM-1_717"
REACTIVE_IDENTITY = "FM-1_718"
WORKSTATION_IDENTITY = "FM-1_719"
PROJECT_IDENTITY = "FM-1_720"
PERFORMANCE_IDENTITY = "FM-1_721"
SYNC_IDENTITY = "FM-1_722"
CLEANUP_IDENTITY = "FM-1_723"
PREVIEW_IDENTITY = "FM-1_724"
RELEASE_IDENTITY = "FM-1_725"
ROUTING_IDENTITY = "FM-1_728"
DEFAULTS_IDENTITY = "FM-1_729"
SONG_IDENTITY = "FM-1_730"
LINK_IDENTITY = "FM-1_731"
REFINEMENT_IDENTITY = "FM-1_733"
NAVIGATION_IDENTITY = "FM-1_734"
POLYPHONY_IDENTITY = "FM-1_735"
WORKFLOW_IDENTITY = "FM-1_727"
POLISH_IDENTITY = "FM-1_726"
SYNC_IDENTITIES = (SYNC_IDENTITY,CLEANUP_IDENTITY,PREVIEW_IDENTITY,RELEASE_IDENTITY,POLISH_IDENTITY,WORKFLOW_IDENTITY,ROUTING_IDENTITY,DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY)
PROJECT_IDENTITIES = (PROJECT_IDENTITY,PERFORMANCE_IDENTITY,*SYNC_IDENTITIES)
WORKSTATION_IDENTITIES = (WORKSTATION_IDENTITY,*PROJECT_IDENTITIES)
OUTPUT_METRIC_IDENTITIES = (SHOWCASE_IDENTITY,TIMBRE_IDENTITY,VISUAL_IDENTITY,REACTIVE_IDENTITY,WORKSTATION_IDENTITY,*PROJECT_IDENTITIES)
FX_IDENTITIES = (FX_IDENTITY,OPTIMIZED_FX_IDENTITY,FINAL_FX_IDENTITY,SHOWCASE_IDENTITY,TIMBRE_IDENTITY,VISUAL_IDENTITY,REACTIVE_IDENTITY,WORKSTATION_IDENTITY,*PROJECT_IDENTITIES)
MIDI_IDENTITIES = (MIDI_IDENTITY, WORKSPACE_IDENTITY, *FX_IDENTITIES)
ONBOARD_IDENTITIES = (ONBOARD_IDENTITY, BANK_IDENTITY, MIDI_IDENTITY, WORKSPACE_IDENTITY, *FX_IDENTITIES)
NATIVE_IDENTITIES = (NATIVE_IDENTITY, ONBOARD_IDENTITY, BANK_IDENTITY, MIDI_IDENTITY, WORKSPACE_IDENTITY, *FX_IDENTITIES)
SUPPORTED_IDENTITIES = ("FM-1_704", "FM-1_705", IDENTITY, NATIVE_IDENTITY, ONBOARD_IDENTITY, BANK_IDENTITY, MIDI_IDENTITY, WORKSPACE_IDENTITY, *FX_IDENTITIES)
PATTERN_IDENTITIES = ("FM-1_705", IDENTITY, NATIVE_IDENTITY, ONBOARD_IDENTITY, BANK_IDENTITY, MIDI_IDENTITY, WORKSPACE_IDENTITY, *FX_IDENTITIES)
LED_IDENTITIES = (IDENTITY, NATIVE_IDENTITY, ONBOARD_IDENTITY, BANK_IDENTITY, MIDI_IDENTITY, WORKSPACE_IDENTITY, *FX_IDENTITIES)
PREFIX = bytes.fromhex("F0 7D 46 4D 45 52")
PARAMETER_COUNT = 193
EVENT_KINDS = {1: "encoder", 2: "button", 3: "control", 4: "note", 5: "transport",
               6: "audio_fault", 7: "page", 8: "boot", 9: "applied", 10: "generated_note", 11: "storage",
               12: "native_load_timing"}
CONTROL_NAMES = ("engine", "va_wave", "cutoff_hz", "resonance_percent", "attack_ms",
                 "decay_ms", "sustain_percent", "release_ms", "drive_percent", "chorus_percent",
                 "delay_percent", "delay_ms", "feedback_percent", "reverb_percent", "phaser_percent",
                 "lfo_rate_centihz", "lfo_depth_cents", "va_cutoff_hz", "tempo_bpm", "arp_enable",
                 "arp_order", "arp_rate", "arp_octaves", "arp_gate_percent", "arp_latch",
                 "arp_swing_percent", "sequence_length", "sequence_edit_step", "sequence_pitch",
                 "sequence_velocity", "sequence_gate_percent", "voice_budget", "arp_triplet",
                 "midi_receive_channel", "reverb_decay_percent", "sequence_pattern", "sequence_chain", "sequence_chain_mask")
PERFORMANCE_FIELDS = ("schema", "uptime_ms", "input_gap_max_us", "input_scan_cost_max_us",
                      "controls_generation", "controls_applied", "last_control_us", "max_control_us",
                      "trace_newest", "trace_oldest", "scope_generation", "seq_running", "seq_recording",
                      "seq_position", "edit_step", "arp_held", "generated_drops", "emitted_notes",
                      "performance_errors", "performance_revision", "step_pitch", "step_velocity",
                      "step_gate", "page_family", "page_index", "operator_number", "input_frames")
LED_HEADER_FIELDS = ("schema", "uptime_ms", "generation", "updated_ms", "family", "octave_plus3",
                     "held_buttons", "physical_keys", "flags", "active_voices")
LED_FLAG_NAMES = ("fine", "sequence_running", "recording", "arp_enabled", "arp_held", "beat_on",
                  "audio_paused", "dsp_init_failed")


class CaptureError(RuntimeError):
    pass


class DiskBudgetReached(CaptureError):
    pass


class Disconnected(CaptureError):
    pass


class PatternSnapshotUnstable(CaptureError):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_identity(identity):
    if identity not in SUPPORTED_IDENTITIES:
        raise ValueError("Capture requires an explicit supported firmware identity")
    return identity


def parameter_count(identity):
    require_identity(identity)
    return native_v2.CONTROL_COUNT if identity in ONBOARD_IDENTITIES else native.CONTROL_COUNT if identity == NATIVE_IDENTITY else PARAMETER_COUNT


def parameter_name(identifier):
    if 0 <= identifier < 145:
        return "dx7_vced_" + str(identifier)
    if 145 <= identifier < 150:return ("filter_type","fx_resonance","lfo_enable","reverb_model","delay_model")[identifier-145]
    if 150 <= identifier < 159:
        return ("glide_mode","glide_ms","glide_curve","sequence_mode","sequence_edit_track",
                "track_sound_ref","track_level","track_mute","sequence_record_mode")[identifier-150]
    if identifier==159:return 'delay_sync'
    return CONTROL_NAMES[identifier - 160] if 160 <= identifier < native_v2.CONTROL_COUNT else "unknown"


def trace_request(cursor):
    if type(cursor) is not int or not 0 <= cursor <= 0xFFFFFFFF:
        raise ValueError("Trace cursor must be unsigned32")
    return PREFIX + bytes([5, *((cursor >> shift) & 127 for shift in range(0, 35, 7)), 247])


def controls_request(start, *, count=PARAMETER_COUNT):
    if type(count) is not int or count not in (193, 195, 198):
        raise ValueError("Unsupported control registry count")
    if type(start) is not int or not 0 <= start < count:
        raise ValueError("Control start ID outside registry")
    return PREFIX + bytes([6, start & 127, start >> 7, 247])


def pattern_request(start):
    if type(start) is not int or not 0 <= start < 64:
        raise ValueError("Pattern start outside retained64 steps")
    return PREFIX + bytes([11, start & 127, start >> 7, 247])


def decimal_fields(frame, opcode):
    if not isinstance(frame, bytes) or not 9 <= len(frame) <= 1024 or frame[:7] != PREFIX + bytes([opcode]) or frame[-1] != 247:
        raise ValueError("Unexpected telemetry framing/opcode")
    try:
        words = frame[7:-1].decode("ascii").split(" ")
    except UnicodeDecodeError as error:
        raise ValueError("Telemetry is not ASCII") from error
    if any(re.fullmatch(r"-?(?:0|[1-9][0-9]{0,9})", word) is None for word in words):
        raise ValueError("Invalid canonical telemetry decimal")
    return [int(word) for word in words]


def parse_output_metrics(frame):
    fields=decimal_fields(frame,27)
    if len(fields)!=7 or fields[0]!=1 or any(not 0<=v<=0xffffffff for v in fields) or fields[5]>65535 or fields[6]>32111:
        raise ValueError('Invalid715 output meter schema/range')
    return dict(zip(('schema','guarded_samples','sanitized_samples','clipped_inputs','soft_limited_samples','peak_input_q15','peak_output_q15'),fields))


def parse_trace(frame, *, maximum_storage_action=5, allow_native_timing=False):
    if type(maximum_storage_action) is not int or maximum_storage_action not in (5, 6, 10, 12):
        raise ValueError("Unsupported storage trace action limit")
    if type(allow_native_timing) is not bool or (allow_native_timing and maximum_storage_action not in (10, 12)):
        raise ValueError("Native load timing requires explicit720 trace capability")
    fields = decimal_fields(frame, 5)
    if len(fields) < 5:
        raise ValueError("Missing trace header")
    schema, uptime, newest, oldest, count = fields[:5]
    if schema != 1 or not 0 <= count <= 6 or len(fields) != 5 + 6 * count:
        raise ValueError("Unsupported trace schema/count")
    if any(not 0 <= n <= 0xFFFFFFFF for n in (uptime, newest, oldest)):
        raise ValueError("Trace header exceeds unsigned32")
    if (newest == 0 and (oldest != 1 or count)) or (newest and not 1 <= oldest <= newest) or newest - oldest >= 256:
        raise ValueError("Invalid trace ring bounds")
    events = []
    for offset in range(5, len(fields), 6):
        seq, milliseconds, kind, identifier, value, aux = fields[offset:offset + 6]
        if (not oldest <= seq <= newest or not 0 <= milliseconds <= 0xFFFFFFFF or
                kind not in EVENT_KINDS or not 0 <= identifier <= 0xFFFFFFFF or
                not -0x80000000 <= value <= 0x7FFFFFFF or not 0 <= aux <= 0xFFFFFFFF):
            raise ValueError("Trace event outside contract")
        if events and seq != events[-1]["seq"] + 1:
            raise ValueError("Nonconsecutive trace events")
        item = dict(seq=seq, ms=milliseconds, kind=kind, kind_name=EVENT_KINDS[kind],
                    id=identifier, value=value, aux=aux)
        if kind == 3:
            item["parameter"] = parameter_name(identifier)
        elif kind == 5 and identifier>>28 in (1,2,3):
            group=identifier>>28
            if group==1:
                delta=identifier&1023;delta=delta-1024 if delta&512 else delta
                item.update(command_group='mixer',track=(identifier>>18)&3,layer=(identifier>>20)&15,delta=delta)
            else:
                item.update(command_group='note_edit' if group==2 else 'block_edit',pattern=(identifier>>20)&15,
                            step=(identifier>>14)&63,action=(identifier>>24)&15)
                if group==2:
                    delta=identifier&16383;item['delta']=delta-16384 if delta&8192 else delta
                else:item.update(count=((identifier>>8)&63)+1,destination=identifier&63)
        elif kind == 4:
            item.update(pitch=identifier, source=aux & 255, channel=(aux >> 8) & 15,
                        source_name={1: "usb_midi", 2: "trs_midi", 3: "local"}.get(aux & 255, "unknown"))
        elif kind == 12:
            if (not allow_native_timing or identifier not in (0,14) or
                    value < 0 or aux < value):
                raise ValueError("Invalid native load timing event")
            item.update(result=identifier, result_name="ok" if identifier == 0 else "stale",
                        apply_us=value, quiet_us=aux)
        elif kind == 11:
            if identifier >= 128 or not 0 <= value <= 12 or not 1 <= aux <= maximum_storage_action:
                raise ValueError("Invalid storage result event")
            if aux in (8,9) and identifier>=16:
                raise ValueError('Invalid project storage slot')
            item.update(slot=identifier, result=value, action={1:"save",2:"load",3:"reset_defaults",4:"reset_user",5:"clear_user",6:"save_midi",7:"initialize_layout",8:"save_project",9:"load_project",10:"clear_projects",11:"save_fx_default",12:"reset_fx_default"}[aux])
        elif kind == 10:
            if identifier >> 8 not in (4, 5) or identifier & 255 > 127 or not 0 <= value <= 127:
                raise ValueError("Invalid admitted generated-note event")
            item.update(pitch=identifier & 255, source=identifier >> 8, audio_frame_low32=aux,
                        source_name="sequencer" if identifier >> 8 == 4 else "arpeggiator")
        if kind in (1, 2, 7):
            item.update(virtual_panel=bool(aux & 0x80000000), panel_aux=aux & 0x7FFFFFFF)
        events.append(item)
    return dict(schema=schema, uptime_ms=uptime, newest_seq=newest, oldest_seq=oldest, events=events)


def parse_controls(frame, expected_start, *, parameter_count=PARAMETER_COUNT, fx=False, workstation=False, projects=False, sync=False, polish=False, six_voice=False):
    controls_request(expected_start, count=parameter_count)
    fields = decimal_fields(frame, 6)
    if len(fields) < 2:
        raise ValueError("Missing controls header")
    start, count = fields[:2]
    if (start != expected_start or not 0 <= start < parameter_count or
            count != min(24, parameter_count - start) or len(fields) != 2 + count):
        raise ValueError("Unexpected control snapshot extent")
    values = fields[2:]
    if any(not 0 <= n <= 65535 for n in values):
        raise ValueError("Control readback exceeds unsigned16")
    if any(value for identifier, value in enumerate(values, start) if (160 if sync else 159 if workstation else 150 if fx else 145) <= identifier < 160):
        raise ValueError("Reserved control IDs must read zero")
    if sync:
        codec = native_v12 if six_voice else native_v8 if polish else native_v7
        for identifier,value in enumerate(values,start):codec._integer(value,*codec.control_bounds(identifier),f'Control {identifier}')
    if workstation:
        for identifier,value in enumerate(values,start):
            if 150<=identifier<159:(native_v5 if projects else native_v4)._integer(value,*(native_v5 if projects else native_v4).control_bounds(identifier),f'Control {identifier}')
    return values


def parse_performance(frame, *, maximum_pitch=128, pattern_banks=8):
    if pattern_banks not in (8,16):raise ValueError("Unsupported pattern count")
    if maximum_pitch not in (128,129):raise ValueError('Unsupported performance pitch range')
    fields = decimal_fields(frame, 8)
    names = PERFORMANCE_FIELDS + (("selected_pattern", "playing_pattern", "queued_pattern", "chain_mask", "chain_enabled") if fields and fields[0] == 2 else ())
    if len(fields) != len(names) or any(not 0 <= n <= 0xFFFFFFFF for n in fields):
        raise ValueError("Invalid performance/input metrics extent or unsigned32 field")
    result = dict(zip(names, fields))
    if (result["schema"] not in (1, 2) or result["seq_running"] > 1 or result["seq_recording"] > 1 or
            result["seq_position"] > 63 or result["edit_step"] > 63 or result["step_pitch"] > maximum_pitch or
            result["step_velocity"] > 127 or result["step_gate"] > 100 or result["operator_number"] > 6):
        raise ValueError("Performance/input metrics exceed schema1 bounds")
    if result["schema"] == 2 and (result["selected_pattern"]>=pattern_banks or result["playing_pattern"]>=pattern_banks or result["queued_pattern"]>pattern_banks or
        not 1<=result["chain_mask"]<=(1<<pattern_banks)-1 or result["chain_enabled"]>1):
        raise ValueError("Performance pattern bank metadata exceeds schema2 bounds")
    return result


def parse_pattern(frame, expected_start, *, maximum_pitch=128):
    if maximum_pitch not in (128,129):raise ValueError('Unsupported pattern pitch range')
    pattern_request(expected_start)
    fields = decimal_fields(frame, 11)
    if len(fields) < 4:
        raise ValueError("Missing pattern header")
    revision, length, start, count = fields[:4]
    if (not 1 <= revision <= 0xFFFFFFFF or not 1 <= length <= 64 or start != expected_start or
            count != min(16, 64 - start) or len(fields) != 4 + count * 3):
        raise ValueError("Invalid pattern revision/length/extent")
    steps = [fields[i:i + 3] for i in range(4, len(fields), 3)]
    if any(not 0 <= pitch <= maximum_pitch or not 1 <= velocity <= 127 or not 1 <= gate <= 100
           for pitch, velocity, gate in steps):
        raise ValueError("Pattern step exceeds canonical bounds")
    return dict(revision=revision, length=length, start=start, count=count, steps=steps)


def parse_leds(frame, *, maximum_family=8):
    if type(maximum_family) is not int or maximum_family not in (8, 9):
        raise ValueError("Unsupported LED page-family limit")
    fields = decimal_fields(frame, 12)
    if len(fields) != 40 or any(not 0 <= value <= 0xFFFFFFFF for value in fields):
        raise ValueError("LED reply requires40 unsigned32 fields")
    result = dict(zip(LED_HEADER_FIELDS, fields[:10]))
    if (result["schema"] != 1 or result["generation"] == 0 or result["family"] > maximum_family or
            result["octave_plus3"] > 6 or result["held_buttons"] >= 1 << 14 or
            result["physical_keys"] >= 1 << 27 or result["flags"] > 255 or result["active_voices"] > 12):
        raise ValueError("LED metadata exceeds schema1 bounds")
    active, gated, lit, dim = fields[10:14], fields[14:18], fields[18:29], fields[29:40]
    if any(held & ~sounding for held, sounding in zip(gated, active)):
        raise ValueError("Gated LED pitches must be a subset of active pitches")
    masks = [30] * 9 + [28, 28]  # No row1 emitter exists at columns9 or10.
    if any((on | low) & ~mask or on & low for on, low, mask in zip(lit, dim, masks)):
        raise ValueError("LED matrix values exceed rows1..4 or overlap brightness states")
    if sum(word.bit_count() for word in active) > result["active_voices"]:
        raise ValueError("LED active pitches exceed actual active voice count")
    pitches = lambda words: [pitch for pitch in range(128) if words[pitch // 32] & (1 << (pitch % 32))]
    result.update(active_pitch_words=active, gated_pitch_words=gated, lit=lit, dim=dim,
                  active_pitches=pitches(active), gated_pitches=pitches(gated),
                  flag_labels=[name for bit, name in enumerate(LED_FLAG_NAMES) if result["flags"] & (1 << bit)],
                  scope="sampled commanded LED matrix; no optical measurement")
    return result


class ReadOnlySession(transport.MidiSession):
    """A final send allowlist, independent of the capture scheduler."""
    capture_disconnected = False
    expected_identity = IDENTITY

    def __init__(self, api, selected, journal, *, expected_identity=IDENTITY, allow_native_backup_ack=False):
        self.expected_identity = require_identity(expected_identity)
        if allow_native_backup_ack and expected_identity not in NATIVE_IDENTITIES:
            raise ValueError("SAVE-to-PC requires exact707/708 identity")
        self.native_ack_enabled = bool(allow_native_backup_ack)
        self._native_pending_save_token = 0
        self._native_authorized_ack = None
        super().__init__(api, selected, journal)

    def authorize_backup_ack(self, token, raw, saved_path):
        native = native_v12 if self.expected_identity == POLYPHONY_IDENTITY else native_v11 if self.expected_identity in (REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v10 if self.expected_identity in (SONG_IDENTITY, LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v9 if self.expected_identity in (ROUTING_IDENTITY,DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v8 if self.expected_identity in (POLISH_IDENTITY,WORKFLOW_IDENTITY,ROUTING_IDENTITY,DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v7 if self.expected_identity in SYNC_IDENTITIES else native_v6 if self.expected_identity == PERFORMANCE_IDENTITY else native_v5 if self.expected_identity == PROJECT_IDENTITY else native_v4 if self.expected_identity == WORKSTATION_IDENTITY else native_v3 if self.expected_identity in FX_IDENTITIES else native_v2 if self.expected_identity in ONBOARD_IDENTITIES else globals()["native"]
        """Permit one exact metadata acknowledgement after validated disk readback."""
        if (not getattr(self, "native_ack_enabled", False) or self.expected_identity not in NATIVE_IDENTITIES or
                self.verified_identity != self.expected_identity or token != getattr(self, "_native_pending_save_token", 0)):
            raise CaptureError("No opted-in pending SAVE permits this acknowledgement")
        if native.read_record(Path(saved_path)) != raw:
            raise CaptureError("Committed native backup bytes differ from pending SAVE")
        self._native_authorized_ack = native.backup_ack_request(token, int.from_bytes(raw[28:32], "little"))

    def _send(self, packet, purpose):
        native = native_v12 if self.expected_identity == POLYPHONY_IDENTITY else native_v11 if self.expected_identity in (REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v10 if self.expected_identity in (SONG_IDENTITY, LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v9 if self.expected_identity in (ROUTING_IDENTITY,DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v8 if self.expected_identity in (POLISH_IDENTITY,WORKFLOW_IDENTITY,ROUTING_IDENTITY,DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v7 if self.expected_identity in SYNC_IDENTITIES else native_v6 if self.expected_identity == PERFORMANCE_IDENTITY else native_v5 if self.expected_identity == PROJECT_IDENTITY else native_v4 if self.expected_identity == WORKSTATION_IDENTITY else native_v3 if self.expected_identity in FX_IDENTITIES else native_v2 if self.expected_identity in ONBOARD_IDENTITIES else globals()["native"]
        allowed = packet == device_protocol.IDENTITY_QUERY
        if not allowed and self.verified_identity == self.expected_identity and isinstance(packet, bytes):
            allowed = packet in (PREFIX + bytes([2, 247]), PREFIX + bytes([8, 247]))
            if self.expected_identity in OUTPUT_METRIC_IDENTITIES and packet==PREFIX+bytes([27,247]):allowed=True
            if self.expected_identity in WORKSTATION_IDENTITIES and packet==PREFIX+bytes([28,247]):allowed=True
            if self.expected_identity in MIDI_IDENTITIES and packet==PREFIX+bytes([25,247]):allowed=True
            if self.expected_identity in (PERFORMANCE_IDENTITY,*SYNC_IDENTITIES) and packet==PREFIX+bytes([31,247]):allowed=True
            if self.expected_identity in (LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) and packet==PREFIX+bytes([33,247]):allowed=True
            if self.expected_identity in ONBOARD_IDENTITIES and packet == PREFIX + bytes([21, 247]):
                allowed = True
            if self.expected_identity in LED_IDENTITIES and packet == PREFIX + bytes([12, 247]):
                allowed = True
            if self.expected_identity in NATIVE_IDENTITIES:
                if packet == native.status_request():
                    allowed = True
                if len(packet) == 15 and packet[:7] == PREFIX + bytes([15]) and packet[-1] == 247:
                    token = sum(value << (7 * index) for index, value in enumerate(packet[7:12]))
                    offset = packet[12] + 128 * packet[13]
                    allowed = (all(value < 128 for value in packet[7:14]) and 1 <= token <= 0xffffffff and
                               offset < native.SIZE and packet == native.chunk_request(token, offset))
                if (getattr(self, "native_ack_enabled", False) and
                        packet == getattr(self, "_native_authorized_ack", None)):
                    allowed = True
            if len(packet) == 13 and packet[:7] == PREFIX + bytes([5]) and packet[-1] == 247:
                cursor = sum(value << (7 * index) for index, value in enumerate(packet[7:12]))
                allowed = all(value < 128 for value in packet[7:12]) and cursor <= 0xFFFFFFFF and packet == trace_request(cursor)
            if len(packet) == 10 and packet[:7] == PREFIX + bytes([6]) and packet[-1] == 247:
                start = packet[7] + 128 * packet[8]
                count = parameter_count(self.expected_identity)
                allowed = all(value < 128 for value in packet[7:9]) and start < count and packet == controls_request(start, count=count)
            if self.expected_identity in PATTERN_IDENTITIES and len(packet) == 10 and packet[:7] == PREFIX + bytes([11]) and packet[-1] == 247:
                start = packet[7] + 128 * packet[8]
                allowed = all(value < 128 for value in packet[7:9]) and start < 64 and packet == pattern_request(start)
        if not allowed:
            raise CaptureError("Recorder refused a non-read-only or unidentified command")
        try:
            super()._send(packet, purpose)
        finally:
            if packet == getattr(self, "_native_authorized_ack", None):
                self._native_authorized_ack = None

    def close(self):
        if self.closed:
            return list(getattr(self, "capture_close_failures", []))
        try:
            failures = super().close()
        except (DiskBudgetReached, OSError) as error:
            # Shared close releases resources before writing its final record.
            # A disk fault must not conceal a simultaneous driver-release error.
            if self.input or self.output or any(not row["ok"] for row in getattr(self, "cleanup_results", [])):
                self.capture_close_failures = ["Cleanup and cleanup-log persistence failed"]
                raise CaptureError("Cleanup and cleanup-log persistence failed; no reconnect permitted") from error
            raise
        self.capture_close_failures = list(failures)
        cleanup = getattr(self, "cleanup_results", [])
        failed_calls = [row for row in cleanup if not row["ok"]]
        expected_disconnect = (self.capture_disconnected and not self.input and not self.output and
                               len(failed_calls) == 1 and failed_calls[0]["operation"] == "midiInStop" and
                               failed_calls[0]["result"] == 6 and
                               sum(row["operation"] == "midiInUnprepareHeader" and row["ok"] for row in cleanup) == len(self.buffers))
        if expected_disconnect:
            # The original failed Stop and complete lifecycle remain in the
            # shared session_closed record; this only qualifies resource release.
            self.journal.record("expected_read_only_disconnect", original_errors=failures,
                                cleanup=cleanup, all_driver_resources_released=True)
            if self in hardware_bridge._unreleased_sessions:
                hardware_bridge._unreleased_sessions.remove(self)
            self.capture_close_failures = []
            return []
        return failures


class DurableJournal:
    """Append-only segments, never overwritten/deleted; bounded total retention."""
    def __init__(self, directory, *, segment_bytes=8 * 1024 * 1024, segments=8, identity=IDENTITY, wire_log=True):
        self.wire_log=bool(wire_log); self.suppressed=0; self.recent_wire=deque(maxlen=8)
        self.identity = require_identity(identity)
        if type(segment_bytes) is not int or segment_bytes < 4096 or type(segments) is not int or not 1 <= segments <= 128:
            raise ValueError("Invalid journal budget")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.segment_bytes, self.max_segments = segment_bytes, segments
        self.index, self.sequence, self.written = 0, 0, 0
        self.sidecar_publish_retries = 0
        self.sidecar_publish_wait_ms = 0
        self.paths = []
        self.stream = None
        self._open()

    def _open(self):
        path = self.directory / f"events-{self.index:04d}.jsonl"
        self.stream = path.open("xb")
        self.paths.append(path)
        self.written = 0

    def record(self, event, **values):
        if not self.wire_log:
            if event in ('send_intent','receive'):
                self.recent_wire.append(dict(event=event,utc=utc(),**values));self.suppressed+=1;return
            if event=='target_event_batch' and not values.get('events'):
                self.suppressed+=1;return
            if 'error' in values or event in ('connection_gap_start','reconnect_failed'):
                values['recent_wire']=list(self.recent_wire)
        record = {"sequence": self.sequence, "utc": utc(), "host_monotonic_ns": time.monotonic_ns(), "event": event, **values}
        data = (json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(data) > self.segment_bytes:
            raise DiskBudgetReached("Single record exceeds journal segment budget")
        if self.written + len(data) > self.segment_bytes:
            if self.index + 1 >= self.max_segments:
                raise DiskBudgetReached("Journal retention budget reached; existing evidence preserved")
            self.stream.close()
            self.index += 1
            self._open()
        self.stream.write(data)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.written += len(data)
        self.sequence += 1

    def _replace_sidecar(self, temporary, destination):
        # Windows readers can briefly deny rename/delete sharing even though
        # this writer owns both paths. Keep the durable old file and complete
        # new temporary intact; never unlink the destination as a workaround.
        # A permanent ACL denial still fails after a bounded300ms of waits.
        waits = (20, 40, 60, 80, 100)
        for attempt in range(len(waits) + 1):
            try:
                os.replace(temporary, destination)
            except OSError as error:
                code = getattr(error, "winerror", None)
                if code not in (5, 32, 33) or attempt == len(waits):
                    raise
                self.sidecar_publish_retries += 1
                self.sidecar_publish_wait_ms += waits[attempt]
                if self.stream is not None and not self.stream.closed:
                    self.record("sidecar_publish_retry", file=destination.name,
                                attempt=attempt + 1, winerror=code, wait_ms=waits[attempt], error=str(error))
                time.sleep(waits[attempt] / 1000)
            else:
                if attempt and self.stream is not None and not self.stream.closed:
                    self.record("sidecar_publish_recovered", file=destination.name, retries=attempt)
                return

    def sidecar_publish_stats(self):
        return {"retries": self.sidecar_publish_retries, "wait_ms": self.sidecar_publish_wait_ms}

    def checkpoint(self, state):
        temporary = self.directory / "checkpoint.next"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump({"schema": 1, "identity": self.identity, **state}, stream, allow_nan=False)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        self._replace_sidecar(temporary, self.directory / "checkpoint.json")

    def status(self, **values):
        temporary = self.directory / "status.next"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump({"schema": 1, "pid": os.getpid(), "utc": utc(), "identity": self.identity,
                       "journal_sequence": self.sequence, "wire_log":self.wire_log, "suppressed_idle_records":self.suppressed,
                       "sidecar_publish": self.sidecar_publish_stats(), **values}, stream, allow_nan=False)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        self._replace_sidecar(temporary, self.directory / "status.json")

    def close(self):
        if self.stream:
            self.stream.close()


class TraceCursor:
    def __init__(self, journal, state=None):
        self.journal = journal
        state = state or {}
        self.cursor, self.epoch = state.get("cursor", 0), state.get("epoch", 0)
        self.uptime = state.get("uptime_ms")
        self.dropped = state.get("dropped_events", 0)
        self.endpoint_signature = state.get("endpoint_signature")

    def state(self):
        return dict(cursor=self.cursor, epoch=self.epoch, uptime_ms=self.uptime, dropped_events=self.dropped,
                    endpoint_signature=self.endpoint_signature)

    def accept(self, batch):
        newest, oldest, uptime = batch["newest_seq"], batch["oldest_seq"], batch["uptime_ms"]
        if newest < self.cursor or (self.uptime is not None and uptime < self.uptime):
            self.journal.record("target_epoch_changed", previous=self.state(), newest_seq=newest,
                                uptime_ms=uptime, reason="reboot_or_uint32_wrap", lost_events="unknown")
            self.cursor, self.uptime, self.epoch = 0, None, self.epoch + 1
            self.journal.checkpoint(self.state())
            return True  # Requery from zero; do not interpret an old-cursor response.
        start = max(self.cursor + 1, oldest)
        expected_count = min(6, max(0, newest - start + 1))
        events = batch["events"]
        if len(events) != expected_count or (events and events[0]["seq"] != start):
            raise ValueError("Trace reply skipped or repeated requested events")
        lost = max(0, oldest - self.cursor - 1)
        if lost:
            self.journal.record("target_event_gap", epoch=self.epoch, first_missing=self.cursor + 1,
                                next_available=oldest, dropped_events=lost)
        self.journal.record("target_event_batch", epoch=self.epoch, **batch)
        # Only durable events advance the checkpoint. A crash can duplicate an
        # already retained event, but cannot silently skip an unretained one.
        self.dropped += lost
        if events:
            self.cursor = events[-1]["seq"]
        self.uptime = uptime
        self.journal.checkpoint(self.state())
        return self.cursor < newest


def request(session, packet, purpose):
    session._send(packet, purpose)
    reply = session.read(2.0)
    if reply is None:
        raise Disconnected("Read-only telemetry response timed out")
    return reply


def diagnostics(session, journal):
    frame = request(session, PREFIX + bytes([2, 247]), "recorder_diagnostics_read")
    if len(frame) < 7 or frame[6] != 2:
        raise ValueError("Recorder requires diagnostic schema2")
    result = fm1_bench.parse_diagnostics(frame,identity=getattr(session,"verified_identity",None))
    journal.record("diagnostics", **result)
    return result


class BatteryTelemetry:
    """Opt-in cached ADC observation; older719 is probed at most once/connection."""
    def __init__(self,journal):
        self.journal=journal;self.supported=None;self.next_due=0.;self.latest=None

    def poll(self,session,now):
        if self.supported is False or now<self.next_due:return self.latest
        from fm1_native_bridge_v13 import battery_status_request,parse_battery_status
        session._send(battery_status_request(),'recorder_battery_status')
        frame=session.read(2.0)
        if frame is None:
            if self.supported:raise Disconnected('Previously supported battery telemetry timed out')
            self.supported=False
            self.journal.record('battery_telemetry_unavailable',reason='No response to optional719 ADC query',
                limitation='An older719 build may reject this one opt-in probe; no voltage or percentage inferred')
            return None
        self.latest=parse_battery_status(frame)  # Malformed responses are errors, never fabricated samples.
        self.supported=True;self.next_due=now+5.0
        self.journal.record('battery_status',**self.latest)
        return self.latest


def performance_metrics(session, journal):
    result = parse_performance(request(session, PREFIX + bytes([8, 247]), "recorder_performance_read"),
                               maximum_pitch=129 if getattr(session,'expected_identity',None) in WORKSTATION_IDENTITIES else 128,pattern_banks=16 if getattr(session,'expected_identity',None) in PROJECT_IDENTITIES else 8)
    journal.record("performance_input_metrics", **result)
    return result


def led_state(session, journal, *, identity=IDENTITY):
    result = parse_leds(request(session, PREFIX + bytes([12, 247]), "recorder_led_read"),
                        maximum_family=9 if identity in NATIVE_IDENTITIES else 8)
    journal.record("led_state", **result)
    return result


def control_snapshot(session, journal, *, identity=IDENTITY):
    # Board generation covers published controls, while step recording changes
    # readback values through the audio owner's independent performance revision.
    # Read both in one fresh board snapshot on each side of the chunked read.
    before = performance_metrics(session, journal)
    values = []
    count = parameter_count(identity)
    for start in range(0, count, 24):
        values.extend(parse_controls(request(session, controls_request(start, count=count), "recorder_controls_read"), start,
                                     parameter_count=count,fx=identity in FX_IDENTITIES,
                                     workstation=identity in WORKSTATION_IDENTITIES,projects=identity in PROJECT_IDENTITIES,six_voice=identity==POLYPHONY_IDENTITY,sync=identity in SYNC_IDENTITIES,polish=identity in (POLISH_IDENTITY,WORKFLOW_IDENTITY,ROUTING_IDENTITY,DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY)))
    after = performance_metrics(session, journal)
    same_epoch = after["uptime_ms"] >= before["uptime_ms"] and after["trace_newest"] >= before["trace_newest"]
    journal.record("control_snapshot", values=values, count=len(values),
                   generation_before=before["controls_generation"], generation_after=after["controls_generation"],
                   performance_revision_before=before["performance_revision"], performance_revision_after=after["performance_revision"],
                   uptime_ms_before=before["uptime_ms"], uptime_ms_after=after["uptime_ms"],
                   consistent=same_epoch and before["controls_generation"] == after["controls_generation"] and
                              before["performance_revision"] == after["performance_revision"],
                   atomic=False)
    return diagnostics(session, journal)


class NativeBackupService:
    """One-second status polling; pending SAVE disk/ACK failures retry after10s.

    Only the opt-in service can authorize metadata ACK19, after an exact durable
    host record and disk readback. There are no parameter/preset/flash writes.
    Failed writes or CRC validation never ACK. Committed backups are retained
    across an ACK retry, without duplicate files for the same token and bytes.
    """
    def __init__(self, journal, directory=None, identity=NATIVE_IDENTITY):
        self.identity = identity
        self.journal = journal
        self.directory = Path(directory) if directory is not None else None
        self.last_attempt_token = 0
        self.retry_at = 0.0
        self.committed = None

    def poll(self, session, now):
        native = native_v12 if self.identity == POLYPHONY_IDENTITY else native_v11 if self.identity in (REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v10 if self.identity in (SONG_IDENTITY, LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v9 if self.identity in (ROUTING_IDENTITY,DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v8 if self.identity in (POLISH_IDENTITY,WORKFLOW_IDENTITY,ROUTING_IDENTITY,DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else native_v7 if self.identity in SYNC_IDENTITIES else native_v6 if self.identity == PERFORMANCE_IDENTITY else native_v5 if self.identity == PROJECT_IDENTITY else native_v4 if self.identity == WORKSTATION_IDENTITY else native_v3 if self.identity in FX_IDENTITIES else native_v2 if self.identity in ONBOARD_IDENTITIES else globals()["native"]
        state = native.parse_status(request(session, native.status_request(), "recorder_native_status_read"))
        self.journal.record("native_status", **state)
        token = state["save_token"]
        pending = bool(token and token != state["save_acked_token"])
        session._native_pending_save_token = token if pending else 0
        if self.directory is None or not pending:
            return state
        if token == self.last_attempt_token and now < self.retry_at:
            return state
        self.last_attempt_token, self.retry_at = token, now + 10.0
        try:
            raw = bytearray()
            for offset in range(0, native.SIZE, 64):
                packet = native.chunk_request(token, offset)
                raw.extend(native.parse_chunk(request(session, packet, "recorder_native_save_read"), token=token, offset=offset))
            raw = bytes(raw)
            snapshot = native.decode(raw)
            digest = hashlib.sha256(raw).hexdigest()
            if not self.committed or (self.committed["token"], self.committed["sha256"]) != (token, digest):
                saved = native.save_backup(raw, self.directory, device_identity=self.identity,
                                           source=f"device SAVE token {token}, native generation {snapshot['source_generation']}")
                self.committed = dict(token=token, **saved)
                self.journal.record("native_save_backup_committed", **self.committed)
            session.authorize_backup_ack(token, raw, self.committed["path"])
            ack = native.backup_ack_request(token, int.from_bytes(raw[28:32], "little"))
            response = native.parse_result(request(session, ack, "recorder_native_save_ack"), opcode=19, transaction=token)
            self.journal.record("native_save_ack", token=token, backup_path=self.committed["path"],
                                sha256=digest, **response)
            if response["result"]:
                raise CaptureError("SAVE acknowledgement refused: " + response["result_name"])
        except (OSError, ValueError, CaptureError) as error:
            if isinstance(error, Disconnected):
                raise
            session._native_authorized_ack = None
            self.journal.record("native_save_backup_failed", token=token, error_type=type(error).__name__,
                                error=str(error), acknowledged=False, retry_after_seconds=10,
                                committed_path=self.committed["path"] if self.committed and self.committed["token"] == token else None)
        return state


def pattern_snapshot(session, journal, *, previous_revision=None, attempts=3):
    """Read all64 retained steps coherently, bounded retries on concurrent edits.

    A first-chunk revision probe avoids retaining duplicate unchanged patterns.
    A fresh first chunk after the full read closes the snapshot interval. The
    revision belongs to the pattern, independently of board control generation.
    """
    if type(attempts) is not int or not 1 <= attempts <= 5:
        raise ValueError("Pattern snapshot attempts must be1..5")
    maximum_pitch=129 if getattr(session,'expected_identity',None) in WORKSTATION_IDENTITIES else 128
    for attempt in range(attempts):
        first = parse_pattern(request(session, pattern_request(0), "recorder_pattern_read"), 0,maximum_pitch=maximum_pitch)
        if first["revision"] == previous_revision:
            return None
        before = performance_metrics(session, journal)
        chunks = [first]
        for start in (16, 32, 48):
            chunks.append(parse_pattern(request(session, pattern_request(start), "recorder_pattern_read"), start,maximum_pitch=maximum_pitch))
        last = parse_pattern(request(session, pattern_request(0), "recorder_pattern_verify"), 0,maximum_pitch=maximum_pitch)
        after = performance_metrics(session, journal)
        consistent = all((part["revision"], part["length"]) == (first["revision"], first["length"])
                         for part in chunks[1:] + [last]) and first["steps"] == last["steps"]
        consistent = consistent and after["uptime_ms"] >= before["uptime_ms"] and after["trace_newest"] >= before["trace_newest"]
        if consistent:
            result = dict(revision=first["revision"], length=first["length"],
                          steps=[step for part in chunks for step in part["steps"]], count=64,
                          consistent=True, atomic=False, attempt=attempt + 1)
            journal.record("pattern_snapshot", **result)
            return result
        journal.record("pattern_snapshot_retry", attempt=attempt + 1,
                       revisions=[part["revision"] for part in chunks + [last]])
    journal.record("pattern_snapshot_unstable", attempts=attempts, retained=False)
    raise PatternSnapshotUnstable("Pattern changed during every bounded snapshot attempt")


def endpoint_signature(selected):
    keys = ("name", "driver_manufacturer_id", "driver_product_id", "driver_version")
    return [{key: row[key] for key in keys} for row in selected]


def connect(api, journal, previous_signature=None, *, expected_identity=IDENTITY, allow_native_backup_ack=False):
    require_identity(expected_identity)
    endpoints = api.enumerate()
    counts = [sum(bool(transport.PORT_NAME.fullmatch(row["name"])) for row in endpoints[direction]) for direction in ("inputs", "outputs")]
    if counts == [0, 0]:
        raise Disconnected("No FMER MIDI endpoints present")
    if counts in ([0, 1], [1, 0]):
        raise Disconnected("FMER endpoint pair is still enumerating")
    selected = transport.select_pair(endpoints)  # Ambiguity/name mismatch is fatal.
    signature = endpoint_signature(selected)
    if previous_signature is not None and signature != previous_signature:
        raise CaptureError("Reconnected endpoint metadata changed; refusing automatic substitution")
    session = ReadOnlySession(api, selected, journal, expected_identity=expected_identity,
                              allow_native_backup_ack=allow_native_backup_ack)
    session.capture_short=expected_identity in MIDI_IDENTITIES
    try:
        session.__enter__()
        identity = session.identify()
        if identity != expected_identity:
            raise CaptureError(f"Recorder expected {expected_identity}, got {identity!r}")
        journal.record("connection_verified", identity=identity, endpoint_signature=signature,
                       limitation="MIDI identity is a firmware identity, not a unique unit serial")
        return session, signature
    except BaseException as error:
        session.capture_disconnected = isinstance(error, (transport.IdentityTimeout, hardware_bridge.WinMMError))
        failures = session.close()
        if failures:
            raise CaptureError("Connection cleanup failed; automatic reconnect refused") from error
        if isinstance(error, transport.IdentityTimeout):
            raise Disconnected(str(error)) from error
        raise


def source_pins(package=None, *, identity=IDENTITY):
    require_identity(identity)
    names = ["tools/fm1_session.py", "tools/fm1_bench.py", "tools/fm1_flash_transport.py",
             "tools/hardware_bridge.py", "tools/device_protocol.py", "firmware/fm1/board.c",
             "firmware/fm1/control_model.h", "firmware/fm1/panel_model.h", "firmware/fm1/panel_gesture.h",
             "firmware/fm1/led_model.h"]
    if identity in NATIVE_IDENTITIES:
        names += ["tools/fm1_native_state.py", "firmware/fm1/native_state.h", "tools/fm1_native_state_v2.py", "firmware/fm1/onboard_store.h", "firmware/fm1/preset_store.h",
                  "core/factory_presets.hpp", "core/factory_presets.cpp"]
    if identity==POLYPHONY_IDENTITY:names += ["tools/fm1_native_bridge_v28.py","tools/fm1_native_state_v12.py"]
    if identity==NAVIGATION_IDENTITY:names += ["tools/fm1_native_bridge_v27.py"]
    if identity in (REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY):names += ["tools/fm1_native_bridge_v26.py","tools/fm1_native_state_v11.py"]
    if identity in (SONG_IDENTITY, LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY):names += ["tools/fm1_native_bridge_v24.py","tools/fm1_native_state_v10.py"]
    if identity in (DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY):names += ["tools/fm1_native_bridge_v23.py","tools/fm1_native_state_v9.py","tools/fm1_native_state_v8.py"]
    if identity == ROUTING_IDENTITY:names += ["tools/fm1_native_bridge_v22.py","tools/fm1_native_state_v9.py","tools/fm1_native_state_v8.py"]
    if identity in (POLISH_IDENTITY,WORKFLOW_IDENTITY):names += ["tools/fm1_native_bridge_v20.py","tools/fm1_native_state_v8.py"]
    if identity == RELEASE_IDENTITY:names += ["tools/fm1_native_bridge_v19.py","tools/fm1_native_state_v7.py"]
    if identity == PREVIEW_IDENTITY:names += ["tools/fm1_native_bridge_v18.py","tools/fm1_native_state_v7.py"]
    if identity == CLEANUP_IDENTITY:names += ["tools/fm1_native_bridge_v17.py","tools/fm1_native_state_v7.py"]
    elif identity == SYNC_IDENTITY:names += ["tools/fm1_native_bridge_v16.py","tools/fm1_native_state_v7.py"]
    if identity == PERFORMANCE_IDENTITY:names += ["tools/fm1_native_bridge_v15.py","tools/fm1_native_state_v6.py"]
    if identity == PROJECT_IDENTITY:names += ["tools/fm1_native_bridge_v14.py","tools/fm1_native_state_v5.py"]
    if identity == WORKSTATION_IDENTITY:names += ["tools/fm1_native_bridge_v13.py","tools/fm1_native_state_v4.py"]
    if identity == REACTIVE_IDENTITY:names += ["tools/fm1_native_bridge_v12.py","tools/fm1_native_state_v3.py"]
    if identity == VISUAL_IDENTITY:names += ["tools/fm1_native_bridge_v11.py","tools/fm1_native_state_v3.py"]
    if identity == TIMBRE_IDENTITY:names += ["tools/fm1_native_bridge_v10.py","tools/fm1_native_state_v3.py"]
    if identity == SHOWCASE_IDENTITY:names += ["tools/fm1_native_bridge_v9.py","tools/fm1_native_state_v3.py"]
    if identity == FINAL_FX_IDENTITY:names += ["tools/fm1_native_bridge_v8.py","tools/fm1_native_state_v3.py"]
    if identity == OPTIMIZED_FX_IDENTITY:names += ["tools/fm1_native_bridge_v7.py","tools/fm1_native_state_v3.py"]
    if identity == FX_IDENTITY:names += ["tools/fm1_native_bridge_v6.py","tools/fm1_native_state_v3.py"]
    if identity == WORKSPACE_IDENTITY:names += ["tools/fm1_native_bridge_v5.py"]
    if identity in MIDI_IDENTITIES:names += ["tools/fm1_native_bridge_v4.py","firmware/fm1/midi_settings.h"]
    if identity in (BANK_IDENTITY,*MIDI_IDENTITIES):names += ["firmware/fm1/bank_store.h","tools/fm1_native_bridge_v3.py"]
    result = {"source_files": [{"path": name, "sha256": sha256(ROOT / name)} for name in names if (ROOT / name).is_file()]}
    if package is not None:
        import fm1_package
        path = Path(package).resolve()
        raw = path.read_bytes()
        product, _, _ = fm1_package.decode_package(raw)
        if product != identity:
            raise ValueError(f"Capture package must identify {identity}")
        result["package"] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                             "scope": "operator-selected source package; identity alone cannot prove installed bytes"}
    return result


def load_checkpoint(directory, *, identity=IDENTITY):
    require_identity(identity)
    path = Path(directory) / "checkpoint.json"
    if path.stat().st_size > 16384:
        raise ValueError("Oversized capture checkpoint")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema") != 1 or state.get("identity") != identity:
        raise ValueError("Checkpoint identity/schema mismatch")
    for key in ("cursor", "epoch", "dropped_events"):
        if type(state.get(key)) is not int or not 0 <= state[key] <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("Invalid checkpoint counter")
    if state["cursor"] > 0xFFFFFFFF or (state.get("uptime_ms") is not None and
            (type(state["uptime_ms"]) is not int or not 0 <= state["uptime_ms"] <= 0xFFFFFFFF)):
        raise ValueError("Invalid checkpoint target time/sequence")
    signature = state.get("endpoint_signature")
    if signature is not None:
        if not isinstance(signature, list) or len(signature) != 2:
            raise ValueError("Invalid checkpoint endpoint signature")
        for row in signature:
            if (not isinstance(row, dict) or not isinstance(row.get("name"), str) or len(row["name"]) > 80 or
                    any(type(row.get(key)) is not int or not 0 <= row[key] <= 0xFFFFFFFF
                        for key in ("driver_manufacturer_id", "driver_product_id", "driver_version"))):
                raise ValueError("Invalid checkpoint endpoint metadata")
    return state


def capture(api, journal, *, duration=600.0, stop_file=None, prior_state=None, clock=time.monotonic,
            sleep=time.sleep, max_reconnects=30, identity=IDENTITY, native_backup_directory=None,battery_telemetry=False):
    require_identity(identity)
    if battery_telemetry and identity not in WORKSTATION_IDENTITIES:
        raise ValueError('Battery telemetry requires explicit719 or720 firmware')
    if native_backup_directory is not None and identity not in NATIVE_IDENTITIES:
        raise ValueError("Native SAVE-to-PC requires exact707/708 identity")
    if duration is not None and not 0 < duration <= 86400:
        raise ValueError("Duration must be within (0,86400] seconds")
    if duration is None and stop_file is None:
        raise ValueError("Indefinite recording requires a stop file")
    start = clock()
    tracker = TraceCursor(journal, prior_state)
    session = None
    signature = tracker.endpoint_signature
    reconnects = 0
    next_diag = next_controls = next_trace = start
    latest = None
    metrics = None
    leds = None
    gap_started = None
    pattern_revision = pattern_epoch = None
    native_service = NativeBackupService(journal, native_backup_directory, identity)
    native_status = None
    battery_service = None
    def stopping():
        return (duration is not None and clock() - start >= duration) or (stop_file is not None and Path(stop_file).exists())
    try:
        while not stopping():
            try:
                if session is None:
                    session, signature = connect(api, journal, signature, expected_identity=identity,
                                                 allow_native_backup_ack=native_backup_directory is not None)
                    pattern_revision = pattern_epoch = None
                    battery_service=BatteryTelemetry(journal) if battery_telemetry else None
                    tracker.endpoint_signature = signature
                    if gap_started is not None:
                        journal.record("connection_gap_end", seconds=clock() - gap_started, retries=reconnects,
                                       event_loss="determined from target cursor or unknown after reboot")
                    gap_started = None
                    reconnects = 0
                    next_diag = next_controls = next_trace = clock()
                now = clock()
                if identity in MIDI_IDENTITIES:
                    packets=[]
                    for _ in range(512):
                        if not session.short_received:break
                        packed,stamp,bad=session.short_received.popleft()
                        packets.append(dict(status=packed&255,data1=(packed>>8)&127,data2=(packed>>16)&127,driver_ms=stamp,malformed=bad))
                    if packets:journal.record('midi_output_batch',packets=packets,callback_overflow=session.short_overflow)
                if now >= next_trace:
                    backlog = False
                    for _ in range(8):  # At most48 events per turn; diagnostics retain service.
                        batch = parse_trace(request(session, trace_request(tracker.cursor), "recorder_trace_read"),
                                            maximum_storage_action=12 if identity in (DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY) else 10 if identity in PROJECT_IDENTITIES else 6 if identity in MIDI_IDENTITIES else 5,
                                            allow_native_timing=identity in PROJECT_IDENTITIES)
                        backlog = tracker.accept(batch)
                        if not backlog or stopping():
                            break
                    next_trace = clock() + (.01 if backlog else .1)
                if now >= next_diag and not stopping():
                    latest = diagnostics(session, journal)
                    metrics = performance_metrics(session, journal)
                    if battery_service is not None:battery_service.poll(session,clock())
                    if identity in OUTPUT_METRIC_IDENTITIES:
                        journal.record("output_metrics",**parse_output_metrics(request(session,PREFIX+bytes([27,247]),"recorder_output_metrics")))
                    if identity in (LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY):
                        from fm1_native_bridge_v25 import parse_usb_link,usb_link_request
                        journal.record("usb_link_status",**parse_usb_link(request(session,usb_link_request(),"recorder_usb_link")))
                    if identity in MIDI_IDENTITIES:
                        from fm1_native_bridge_v4 import parse_midi_status,midi_status_request
                        if identity in (PERFORMANCE_IDENTITY,*SYNC_IDENTITIES):
                            from fm1_native_bridge_v15 import parse_midi_status,parse_usb_audio,usb_audio_request
                            journal.record("usb_audio_status",**parse_usb_audio(request(session,usb_audio_request(),"recorder_usb_audio")))
                        journal.record("midi_status",**parse_midi_status(request(session,midi_status_request(),"recorder_midi_status")))
                    if identity in LED_IDENTITIES:
                        leds = led_state(session, journal, identity=identity)
                    if identity in NATIVE_IDENTITIES:
                        native_status = native_service.poll(session, clock())
                        if identity in ONBOARD_IDENTITIES:
                            from fm1_native_bridge_v2 import parse_storage_status
                            if identity == BANK_IDENTITY:
                                from fm1_native_bridge_v3 import parse_storage_status
                            if identity in MIDI_IDENTITIES:
                                from fm1_native_bridge_v4 import parse_storage_status
                            if identity in PROJECT_IDENTITIES:
                                from fm1_native_bridge_v14 import parse_storage_status
                            if identity in (DEFAULTS_IDENTITY,SONG_IDENTITY,LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY):
                                from fm1_native_bridge_v23 import parse_storage_status
                                if identity in (SONG_IDENTITY, LINK_IDENTITY,REFINEMENT_IDENTITY,NAVIGATION_IDENTITY,POLYPHONY_IDENTITY):
                                    from fm1_native_bridge_v24 import parse_storage_status
                            storage = parse_storage_status(request(session, PREFIX+bytes([21,247]), "recorder_storage_status"))
                            journal.record("storage_status", **storage)
                    journal.status(phase="capturing", elapsed_seconds=clock() - start,
                                   trace=tracker.state(), diagnostics=latest, performance=metrics, leds=leds,
                                   battery=battery_service.latest if battery_service is not None else None,
                                   native=native_status, native_backup_enabled=native_backup_directory is not None)
                    next_diag = clock() + 1.0
                if now >= next_controls and not stopping():
                    if latest is None:
                        latest = diagnostics(session, journal)
                    latest = control_snapshot(session, journal, identity=identity)
                    if identity in PATTERN_IDENTITIES:
                        try:
                            pattern = pattern_snapshot(session, journal,
                                                       previous_revision=pattern_revision if pattern_epoch == tracker.epoch else None)
                        except PatternSnapshotUnstable:
                            # Active editing can invalidate every chunked attempt;
                            # preserve trace capture and retry next snapshot cadence.
                            pattern = None
                        if pattern is not None:
                            pattern_revision, pattern_epoch = pattern["revision"], tracker.epoch
                    next_controls = clock() + 2.0
                sleep(min(.02, max(0, next_trace - clock())))
            except (Disconnected, hardware_bridge.WinMMError) as error:
                journal.record("connection_gap_start" if gap_started is None else "reconnect_failed",
                               error_type=type(error).__name__, error=str(error), cursor=tracker.cursor)
                if gap_started is None:
                    gap_started = clock()
                if session is not None:
                    session.capture_disconnected = True
                    failures = session.close()
                    session = None
                    if failures:
                        raise CaptureError("Disconnected handle cleanup failed; refusing reconnect")
                reconnects += 1
                journal.status(phase="reconnecting", elapsed_seconds=clock() - start,
                               trace=tracker.state(), reconnect_attempts=reconnects, error=str(error))
                if reconnects > max_reconnects:
                    raise CaptureError("Bounded reconnect attempts exhausted")
                deadline = clock() + min(5.0, .25 * 2 ** min(reconnects, 5))
                while clock() < deadline and not stopping():
                    sleep(min(.1, deadline - clock()))
        return {"status": "stopped", "reason": "stop_file" if stop_file and Path(stop_file).exists() else "duration",
                "elapsed_seconds": clock() - start, **tracker.state()}
    finally:
        if session is not None:
            failures = session.close()
            if failures:
                raise CaptureError("MIDI cleanup failed; driver buffers retained")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", choices=("704", "705", "706", "707", "708", "709", "710", "711", "712", "713", "714", "715", "716", "717", "718", "719", "720", "721", "722", "723", "724", "725", "726", "727", "728", "729", "730", "731", "733", "734", "735"), default="735", help="Exact expected identity; no automatic version substitution")
    parser.add_argument("--native-backup-directory", type=Path,
                        help="707/708 opt-in SAVE-to-PC: complete host files and metadata acknowledgements; no musical/flash writes")
    parser.add_argument("--duration", type=float, default=600.0, help="Seconds; 0 requires --stop-file")
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume-from", type=Path, help="Prior capture directory; creates a new run")
    parser.add_argument("--package", type=Path, help="Optional matching source package for hash provenance")
    parser.add_argument("--segment-mib", type=int, default=8)
    parser.add_argument("--segments", type=int, default=32)
    parser.add_argument("--wire-log",action="store_true",help="Also retain every raw MIDI request/reply and empty trace poll")
    parser.add_argument('--battery-telemetry',action='store_true',help='719 opt-in cached ADC logging every5s; older719 may reject the first probe')
    args = parser.parse_args(argv)
    identity = require_identity("FM-1_" + args.firmware)
    if args.battery_telemetry and identity not in WORKSTATION_IDENTITIES:parser.error('--battery-telemetry requires --firmware719 or720')
    if args.native_backup_directory is not None and identity not in NATIVE_IDENTITIES:
        parser.error("--native-backup-directory requires --firmware707 or708")
    if not 0 <= args.duration <= 86400 or (args.duration == 0 and args.stop_file is None):
        parser.error("Use 0..86400 seconds; zero requires a stop file")
    if not 1 <= args.segment_mib <= 64 or not 1 <= args.segments <= 128:
        parser.error("Use 1..64 MiB segments and 1..128 retained segments")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    directory = args.output or ROOT / "artifacts/fm1-sessions" / stamp
    prior = load_checkpoint(args.resume_from, identity=identity) if args.resume_from else None
    pins = source_pins(args.package, identity=identity)
    journal = DurableJournal(directory, segment_bytes=args.segment_mib * 1024 * 1024, segments=args.segments, identity=identity, wire_log=args.wire_log)
    report = {"schema": 1, "identity": identity, "started_utc": utc(), "pid": os.getpid(),
              "status": "failed", "flash_writes": False, "preset_writes": False,
              "volatile_control_writes": False, "stop_file": str(args.stop_file.resolve()) if args.stop_file else None,
              "native_backup_directory": str(args.native_backup_directory.resolve()) if args.native_backup_directory else None,
              "metadata_acknowledgements": args.native_backup_directory is not None,
              "battery_telemetry_requested":args.battery_telemetry,
              "requested_duration": args.duration, "retention": "stop at capacity; never delete old evidence",
              "start_pins": pins, "resume_from": str(args.resume_from) if args.resume_from else None}
    try:
        with (directory / "process.json").open("x", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "identity": identity, "started_utc": report["started_utc"], "stop_file": report["stop_file"]}, stream)
            stream.flush(); os.fsync(stream.fileno())
        journal.record("capture_start", **report)
        count = parameter_count(identity)
        journal.record("parameter_registry", count=count,
                       labels={str(i): parameter_name(i) for i in range(count)},
                       fm_order="0..125: operators6..1,21fields each;126..144:global VCED offsets")
        if prior:
            journal.record("host_restart", prior_checkpoint=prior, source_directory=str(args.resume_from),
                           continuity="cursor retained; target reset/gaps are detected on next response")
        journal.status(phase="starting", trace=prior)
        report.update(capture(hardware_bridge.WinMM(), journal, duration=args.duration or None,
                              stop_file=args.stop_file, prior_state=prior, identity=identity,
                              native_backup_directory=args.native_backup_directory,battery_telemetry=args.battery_telemetry))
    except DiskBudgetReached as error:
        report.update(status="stopped", reason="disk_budget", error=str(error))
    except KeyboardInterrupt:
        report.update(status="stopped", reason="keyboard_interrupt")
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error))
    finally:
        report["finished_utc"] = utc()
        try:
            report["end_pins"] = source_pins(args.package, identity=identity)
            report["source_files_changed"] = report["start_pins"] != report["end_pins"]
        except Exception as error:
            report.update(status="failed", end_pin_error=str(error))
        if (directory / "checkpoint.json").is_file():
            report["last_persisted_checkpoint"] = load_checkpoint(directory, identity=identity)
        try:
            journal.record("capture_end", **report)
        except DiskBudgetReached:
            report["end_record_in_summary_only"] = True
        finally:
            journal.close()
        journal.status(phase=report["status"], reason=report.get("reason"), error=report.get("error"),
                       trace=report.get("last_persisted_checkpoint"))
        report["sidecar_publish"] = journal.sidecar_publish_stats()
        report["segments"] = [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in journal.paths]
        with (directory / "report.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({"status": report["status"], "report": str(directory / "report.json"), "error": report.get("error")}))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
