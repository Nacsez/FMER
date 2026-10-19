#!/usr/bin/env python3
"""Explicit FMER716 complete native backup / RAM restore and explicit onboard slot sync.

Run only while the session recorder and other MIDI clients are closed. Importing
performs no device access. The exact checksum-valid FM-1_716 identity is required
before native commands. Restore validates the entire file before opening MIDI,
saves a complete pre-restore host backup, uses a live revision guard, then verifies
the whole applied state. Device transport is stopped by a successful restore.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
import zlib

import fm1_native_state_v3 as native
import fm1_flash_transport as transport
import hardware_bridge

IDENTITY = "FM-1_716"

MIDI_KEYS=('route','tx_channel','local','clock_source','clock_send','transport_rx','cc_send','reserved')
MIDI_LIMITS=(3,15,1,2,1,1,1,0)
MIDI_FIELDS=('schema','generation','applied','persisted',*MIDI_KEYS,
 'received_clock','received_start','received_stop','sent_notes','sent_clock','output_refused',
 'clock_timeouts','clock_period_frames','external_running','received_song_position',
 'queue_depth','queue_overflows','usb_connected','recovery_mask')

def midi_status_request():return native.PREFIX+bytes([25,247])

def midi_settings_request(settings,generation):
    if not isinstance(settings,list) or len(settings)!=8:raise ValueError('Eight MIDI settings required')
    for value,limit in zip(settings,MIDI_LIMITS):native._integer(value,0,limit,'MIDI setting')
    native._integer(generation,0,0xffffffff,'MIDI generation')
    return native.PREFIX+bytes([26])+native._u7(generation)+bytes(settings)+bytes([247])

def parse_midi_status(frame):
    values=native._decimal_fields(frame,25)
    if len(values)!=len(MIDI_FIELDS):raise ValueError('MIDI status extent')
    result=dict(zip(MIDI_FIELDS,values))
    if result['schema']!=1 or result['persisted']>1 or result['external_running']>1 or result['usb_connected']>1 or result['queue_depth']>64 or result['recovery_mask']>65535:raise ValueError('MIDI status bounds')
    for key,limit in zip(MIDI_KEYS,MIDI_LIMITS):native._integer(result[key],0,limit,'MIDI status '+key)
    result['settings']=[result[key] for key in MIDI_KEYS]
    return result

STORE_FIELDS = ("schema", "ready", "busy", "action", "slot", "result", "job", "finished_job",
                "valid_slots", "latest_slot", "generation_low", "generation_high", "blank_cells",
                "foreign_cells", "incomplete_cells", "boot_crc", "boot_result", "native_bytes")
STORE_RESULTS = ("ok", "empty", "argument", "io", "verify", "full", "foreign", "limit", "size",
                 "not_ready", "busy", "stale", "native_format")


def slot_number(slot: int) -> int:
    native._integer(slot, 0, 127, "Onboard slot")
    return slot


def store_status_request() -> bytes:
    return native.PREFIX + bytes([21, 247])


def slot_request(opcode: int, slot: int) -> bytes:
    if opcode not in (23, 24):
        raise native.NativeStateError("Slot read opcode must be23 or24")
    return native.PREFIX + bytes([opcode, slot_number(slot), 247])


def store_action_request(action: int, slot: int, live_generation: int, store_generation: int) -> bytes:
    native._integer(action, 1, 6, "Storage action")
    slot_number(slot)
    native._integer(live_generation, 0, 0xffffffff, "Expected live generation")
    native._integer(store_generation, 0, 0xffffffffffffffff, "Expected store generation")
    # The716 guarded form is the only form this client emits: both the live
    # state and journal generation must still match the durable pre-backups.
    return (native.PREFIX + bytes([22, action, slot]) + native._u7(live_generation) +
            native._u7(store_generation & 0xffffffff) + native._u7(store_generation >> 32) + bytes([247]))


def parse_store_status(frame: bytes) -> dict:
    values = native._decimal_fields(frame, 21)
    if len(values) != len(STORE_FIELDS):
        raise native.NativeStateError("Unexpected onboard status field count")
    result = dict(zip(STORE_FIELDS, values))
    if (result["schema"] != 2 or result["ready"] > 1 or result["busy"] > 3 or
            result["action"] > 6 or result["slot"] > 127 or result["result"] >= len(STORE_RESULTS) or
            result["boot_result"] >= len(STORE_RESULTS) or result["valid_slots"] > 128 or
            result["latest_slot"] not in (*range(128), 65535) or result["native_bytes"] != native.SIZE or
            any(result[field] > 73 for field in ("blank_cells", "foreign_cells", "incomplete_cells")) or
            sum(result[field] for field in ("blank_cells", "foreign_cells", "incomplete_cells")) > 73):
        raise native.NativeStateError("Onboard status exceeds716 storage ranges")
    result["generation"] = result["generation_low"] | (result["generation_high"] << 32)
    result["result_name"] = STORE_RESULTS[result["result"]]
    return result


def parse_slot_catalog(frame: bytes, slot: int) -> dict:
    slot_number(slot)
    values = native._decimal_fields(frame, 23)
    if (len(values) != 15 or values[0] != slot or values[1] > 1 or
            any(value > 126 or (value < 32 and value != 0) for value in values[5:]) or
            (values[1] and any(value < 32 for value in values[5:]))):
        raise native.NativeStateError("Onboard slot catalog identity/name/ranges mismatch")
    return dict(slot=slot, present=bool(values[1]), generation=values[2] | (values[3] << 32),
                crc=values[4], name_bytes=values[5:], name=bytes(values[5:]).decode("ascii").rstrip(" \0"))


# Public spelling shared by the716 session recorder.
parse_storage_status = parse_store_status


def parse_slot_result(frame: bytes, *, opcode: int, slot: int) -> dict:
    if opcode not in (22, 24):
        raise native.NativeStateError("Unsupported slot result opcode")
    slot_number(slot)
    values = native._decimal_fields(frame, opcode)
    if len(values) != 2 or values[0] != slot or values[1] >= len(native.RESULT_NAMES):
        raise native.NativeStateError("Slot result does not match requested destination")
    return dict(slot=slot, result=values[1], result_name=native.RESULT_NAMES[values[1]])


class NativeBridge:
    def midi_status(self):
        value=parse_midi_status(self.request(midi_status_request(),'midi_status'))
        self.journal.record('midi_status',**value);return value

    def midi_configure(self,settings,*,persist=False,backup_directory=None):
        before=self.midi_status()
        packet=midi_settings_request(settings,before['generation'])
        self.journal.record('midi_settings_intent',before=before,settings=settings,persist=persist)
        response=self.request(packet,'midi_configure')
        if response[6]==26:raise RuntimeError('MIDI settings refused: '+repr(native._decimal_fields(response,26)))
        after=parse_midi_status(response)
        for _ in range(100):
            if after['generation']==after['applied']:break
            self.sleep(.02);after=self.midi_status()
        if after['generation']!=after['applied'] or after['settings']!=settings:raise RuntimeError('MIDI setting adoption differs')
        if persist:
            if backup_directory is None:raise ValueError('Live backup directory required for explicit persistent MIDI Save')
            raw,status,saved=self._backup_live(backup_directory,'before persistent global MIDI settings')
            store=self.store_status();self._idle_store(store)
            check=self.midi_status()
            if check['generation']!=after['generation'] or check['settings']!=settings:raise RuntimeError('MIDI settings changed before Save')
            self._storage_action(6,0,status['live_generation'],store)
            after=self.midi_status()
            if not after['persisted'] or after['settings']!=settings:raise RuntimeError('Persistent MIDI settings readback differs')
        return after

    def __init__(self, session, journal, *, monotonic=time.monotonic, sleep=time.sleep):
        if getattr(session, "verified_identity", None) != IDENTITY:
            raise RuntimeError("Native bridge requires exact checksum-valid FM-1_716 identity")
        self.session, self.journal = session, journal
        self.monotonic, self.sleep = monotonic, sleep

    def request(self, wire: bytes, purpose: str) -> bytes:
        if getattr(self.session, "verified_identity", None) != IDENTITY:
            raise RuntimeError("Native bridge lost exact checksum-valid FM-1_716 identity")
        self.session._send(wire, purpose)
        frame = self.session.read(2.0)
        if frame is None:
            raise TimeoutError("Native response timed out: " + purpose)
        return frame

    def status(self) -> dict:
        state = native.parse_status(self.request(native.status_request(), "native_status"))
        self.journal.record("native_status", **state)
        return state

    def read_token(self, token: int) -> bytes:
        result = bytearray()
        for offset in range(0, native.SIZE, 64):
            # A frozen-token read is idempotent. Retry only rejected chunk
            # frames, never a write/commit or a whole-state CRC failure. Keep
            # the bad frame in the transport journal; validation stays strict.
            for attempt in range(3):
                raw = self.request(native.chunk_request(token, offset), "native_read_chunk")
                try:
                    chunk = native.parse_chunk(raw, token=token, offset=offset)
                    break
                except native.NativeStateError as error:
                    self.journal.record("native_chunk_rejected", token=token, offset=offset,
                                        attempt=attempt+1, error=str(error), retry=attempt<2)
                    if attempt == 2:
                        raise
                    self.sleep(.01)
            result.extend(chunk)
        state = native.decode(bytes(result))
        self.journal.record("native_snapshot_validated", token=token, source_generation=state["source_generation"],
                            bytes=len(result), sha256=hashlib.sha256(result).hexdigest(), preset_id=state["preset_id"])
        return bytes(result)

    def snapshot(self) -> tuple[bytes, dict]:
        before = self.status()
        request = native.snapshot_request()
        if self.request(request, "native_snapshot_request") != request:
            raise native.NativeStateError("Native frozen-snapshot request echo mismatch")
        deadline = self.monotonic() + 2.0
        # Count and wall-clock limits bound polling even with an unusual clock.
        for _ in range(100):
            after = self.status()
            if after["export_token"] and after["export_token"] != before["export_token"]:
                return self.read_token(after["export_token"]), after
            if self.monotonic() >= deadline:
                break
            self.sleep(.02)
        raise TimeoutError("Audio owner did not publish a complete native snapshot")

    def backup(self, directory: Path, *, source="explicit native backup") -> dict:
        raw, status = self.snapshot()
        saved = native.save_backup(raw, directory, device_identity=IDENTITY, source=source)
        self.journal.record("native_backup_committed", **saved)
        return dict(backup=saved, status=status)

    def acknowledge_save(self, token: int, raw: bytes) -> dict:
        """Caller must already have committed these exact bytes to host storage."""
        native.decode(raw)
        packet = native.backup_ack_request(token, int.from_bytes(raw[28:32], "little"))
        response = native.parse_result(self.request(packet, "native_backup_ack"), opcode=19, transaction=token)
        self.journal.record("native_backup_ack", **response)
        if response["result"]:
            raise RuntimeError("Device refused host backup acknowledgement: " + response["result_name"])
        return response

    def abort_staging(self, transaction: int = 0) -> dict:
        response = native.parse_result(self.request(native.abort_request(transaction), "native_abort_staging"),
                                       opcode=20, transaction=transaction)
        self.journal.record("native_abort_staging", **response)
        return response

    def _upload(self, raw: bytes, transaction: int, generation: int) -> dict:
        """A timeout after commit is ambiguous; it must never imply rollback."""
        staging, commit_attempted = False, False
        try:
            begin = native.begin_request(transaction, generation)
            # A begin timeout can leave incomplete staging. Addressing our exact
            # transaction for cleanup is safe even if begin was never accepted.
            staging = True
            result = native.parse_result(self.request(begin, "native_restore_begin"), opcode=16, transaction=transaction)
            if result["result"]:
                raise RuntimeError("Native restore begin refused: " + result["result_name"])
            for offset in range(0, native.SIZE, 64):
                packet = native.write_chunk_request(transaction, offset, raw[offset:offset + 64])
                result = native.parse_result(self.request(packet, "native_restore_chunk"), opcode=17, transaction=transaction)
                if result["result"]:
                    raise RuntimeError("Native restore chunk refused: " + result["result_name"])
            commit_attempted = True
            result = native.parse_result(self.request(native.commit_request(transaction), "native_restore_commit"),
                                         opcode=18, transaction=transaction)
            if result["result"] not in (0, 9):
                commit_attempted = False  # Explicit refusal guarantees no queued adoption.
                raise RuntimeError("Native restore commit refused: " + result["result_name"])
            deadline = self.monotonic() + 2.0
            for _ in range(100):
                final_status = self.status()
                if final_status["last_import_tx"] == transaction and final_status["last_import_result"] != 9:
                    if final_status["last_import_result"]:
                        raise RuntimeError("Audio owner refused native restore: " + native.RESULT_NAMES[final_status["last_import_result"]])
                    return final_status
                if self.monotonic() >= deadline:
                    raise TimeoutError("Native restore publication result timed out; do not assume rollback")
                self.sleep(.02)
            raise TimeoutError("Native restore publication poll limit reached; do not assume rollback")
        except Exception:
            if staging and not commit_attempted:
                # Preserve the primary failure. Cleanup refuses an already
                # queued transaction and never claims to undo musical changes.
                try:
                    self.abort_staging(transaction)
                except Exception as cleanup_error:
                    try:
                        self.journal.record("native_staging_cleanup_failed", transaction=transaction,
                                            error=repr(cleanup_error), musical_rollback_claimed=False)
                    except Exception:
                        pass
            raise

    def restore(self, raw: bytes, backup_directory: Path, *, transaction: int | None = None) -> dict:
        requested = native.decode(raw)  # No command at all if invalid.
        before, before_status = self.snapshot()
        prior = native.decode(before)
        saved = native.save_backup(before, backup_directory, device_identity=IDENTITY,
                                   source="complete pre-restore RAM snapshot")
        self.journal.record("native_pre_restore_backup_committed", **saved)
        current = self.status()
        if current["live_generation"] != prior["source_generation"]:
            raise RuntimeError("Live state changed after pre-restore backup; restore refused without musical writes")
        if transaction is None:
            transaction = uuid.uuid4().int & 0xffffffff or 1
            if transaction == current["last_import_tx"]:
                transaction = (transaction + 1) & 0xffffffff or 1
        elif transaction == current["last_import_tx"]:
            raise RuntimeError("Restore transaction ID must differ from the previous import ID")
        # Validate before issuing the housekeeping command.
        native.begin_request(transaction, current["live_generation"])
        aborted = self.abort_staging()
        if aborted["result"]:
            raise RuntimeError("Unable to discard prior incomplete native staging: " + aborted["result_name"])
        self.journal.record("native_restore_intent", transaction=transaction,
                            expected_live_generation=current["live_generation"],
                            requested_sha256=hashlib.sha256(raw).hexdigest(),
                            pre_restore_backup=saved["path"], ram_only=True, flash_writes=False)
        self._upload(raw, transaction, current["live_generation"])
        actual, readback_status = self.snapshot()
        observed = native.decode(actual)
        # Snapshot generations identify observations, not the musical data being
        # restored. Every other field, including exact name/inactive steps, must
        # match; no partial-control comparison masquerades as full verification.
        requested["source_generation"] = observed["source_generation"]
        if observed != requested:
            self.journal.record("native_restore_readback_mismatch", expected=requested, observed=observed)
            raise RuntimeError("Post-restore complete native state differs from requested file")
        self.journal.record("native_restore_verified", transaction=transaction,
                            sha256=hashlib.sha256(actual).hexdigest(), generation=observed["source_generation"],
                            excluded_comparison_fields=["source_generation"], ram_only=True)
        return dict(pre_restore_backup=saved, before_status=before_status, after_status=readback_status,
                    transaction=transaction, verified_generation=observed["source_generation"],
                    complete_state_verified=True, ram_only=True, flash_writes=False)


    def store_status(self) -> dict:
        result = parse_store_status(self.request(store_status_request(), "onboard_status"))
        self.journal.record("onboard_status", **result)
        return result

    @staticmethod
    def _idle_store(status: dict) -> None:
        if not status["ready"]:
            raise RuntimeError("Onboard store is not ready; no storage mutation attempted")
        if status["busy"]:
            raise RuntimeError("Onboard store is busy; no storage mutation attempted")

    def slot_catalog(self, slot: int) -> dict:
        result = parse_slot_catalog(self.request(slot_request(23, slot), "onboard_slot_catalog"), slot)
        self.journal.record("onboard_slot_catalog", **result)
        return result

    def list_slots(self) -> dict:
        before = self.store_status()
        self._idle_store(before)
        slots = [self.slot_catalog(slot) for slot in range(128)]
        after = self.store_status()
        self._idle_store(after)
        if before["generation"] != after["generation"] or before["job"] != after["job"]:
            raise RuntimeError("Onboard catalog changed while reading; mixed catalog refused")
        if sum(slot["present"] for slot in slots) != after["valid_slots"]:
            raise RuntimeError("Onboard journal/catalog disagree about readable slots")
        return dict(status=after, slots=slots, flash_writes=False, ram_writes=False)

    def read_slot(self, slot: int) -> tuple[bytes, dict]:
        slot_number(slot)
        store = self.store_status()
        self._idle_store(store)
        before = self.slot_catalog(slot)
        if not before["present"]:
            raise RuntimeError(f"Onboard slot {slot} is empty")
        previous_token = self.status()["export_token"]
        result = parse_slot_result(self.request(slot_request(24, slot), "onboard_slot_export"),
                                   opcode=24, slot=slot)
        if result["result"]:
            raise RuntimeError("Onboard slot export refused: " + result["result_name"])
        deadline = self.monotonic() + 2.0
        for _ in range(100):
            status = self.status()
            token = status["export_token"]
            if token and token != previous_token:
                raw = self.read_token(token)
                break
            if self.monotonic() >= deadline:
                raise TimeoutError("Onboard slot export did not publish frozen bytes")
            self.sleep(.02)
        else:
            raise TimeoutError("Onboard slot export poll limit reached")
        after = self.slot_catalog(slot)
        current = self.store_status()
        self._idle_store(current)
        if (before != after or store["generation"] != current["generation"] or
                store["job"] != current["job"]):
            raise RuntimeError("Onboard slot changed while exporting; mixed revision refused")
        if (zlib.crc32(raw) & 0xffffffff) != before["crc"]:
            raise native.NativeStateError("Onboard exported bytes disagree with catalog payload CRC")
        return raw, dict(catalog=after, store_status=current, export_token=token)

    def export_slot(self, slot: int, backup_directory: Path) -> dict:
        raw, state = self.read_slot(slot)
        saved = native.save_backup(raw, backup_directory, device_identity=IDENTITY,
                                   source=f"complete onboard slot{slot} generation{state['catalog']['generation']}")
        self.journal.record("onboard_slot_backup_committed", slot=slot, **saved)
        return dict(slot=slot, backup=saved, **state, flash_writes=False, ram_writes=False)

    def _backup_live(self, directory: Path, source: str) -> tuple[bytes, dict, dict]:
        raw, status = self.snapshot()
        saved = native.save_backup(raw, directory, device_identity=IDENTITY, source=source)
        self.journal.record("onboard_pre_action_live_backup_committed", **saved)
        return raw, status, saved

    def _backup_slot(self, slot: int, directory: Path) -> dict:
        slot_number(slot)
        store = self.store_status()
        self._idle_store(store)
        catalog = self.slot_catalog(slot)
        if catalog["present"]:
            raw, state = self.read_slot(slot)
            saved = native.save_backup(raw, directory, device_identity=IDENTITY,
                                       source=f"complete pre-action onboard slot{slot} generation{state['catalog']['generation']}")
            self.journal.record("onboard_pre_action_slot_backup_committed", slot=slot, **saved)
            return dict(raw=raw, backup=saved, **state)
        return dict(raw=None, backup=None, catalog=catalog, store_status=store)

    def _guard_slot(self, prior: dict) -> dict:
        current = self.store_status()
        self._idle_store(current)
        catalog = self.slot_catalog(prior["catalog"]["slot"])
        if (current["generation"] != prior["store_status"]["generation"] or
                current["job"] != prior["store_status"]["job"] or catalog != prior["catalog"]):
            raise RuntimeError("Onboard destination changed after its backup; action refused")
        return current

    def _storage_action(self, action: int, slot: int, generation: int, prior_store: dict) -> dict:
        packet = store_action_request(action, slot, generation, prior_store["generation"])
        self.journal.record("onboard_action_intent", action=action, slot=slot,
                            expected_live_generation=generation, expected_store_generation=prior_store["generation"],
                            flash_writes=action != 2, ram_writes=action == 2)
        # A timeout after this command is ambiguous. Never retry a mutation or
        # claim rollback: the journal may already contain a committed record.
        try:
            response = self.request(packet, "onboard_guarded_action")
            if response.startswith(native.PREFIX + bytes([22])):
                refusal = parse_slot_result(response, opcode=22, slot=slot)
                raise RuntimeError("Guarded onboard action refused: " + refusal["result_name"])
            accepted = parse_store_status(response)
            job = accepted["job"]
            if not job or job == prior_store["job"] or accepted["action"] != action or accepted["slot"] != slot:
                raise native.NativeStateError("Onboard action acknowledgement belongs to another job")
            deadline = self.monotonic() + 8.0
            final = accepted
            for _ in range(400):
                if final["job"] != job or final["action"] != action or final["slot"] != slot:
                    raise RuntimeError("Onboard job changed before its result was observed; outcome ambiguous")
                if final["finished_job"] == job and not final["busy"]:
                    if final["result"]:
                        raise RuntimeError("Onboard action failed: " + final["result_name"])
                    self.journal.record("onboard_action_completed", **final)
                    return final
                if self.monotonic() >= deadline:
                    break
                self.sleep(.02)
                final = self.store_status()
            raise TimeoutError("Onboard action result timed out; do not assume rollback")
        except Exception as error:
            self.journal.record("onboard_action_unverified", action=action, slot=slot,
                                error=repr(error), rollback_claimed=False, automatic_retry=False)
            raise

    def _verify_state(self, wanted: bytes, actual: bytes, event: str) -> dict:
        expected, observed = native.decode(wanted), native.decode(actual)
        expected["source_generation"] = observed["source_generation"]
        if expected != observed:
            self.journal.record(event + "_mismatch", expected=expected, observed=observed)
            raise RuntimeError("Complete native state differs from requested sound/pattern bank")
        result = dict(sha256=hashlib.sha256(actual).hexdigest(), generation=observed["source_generation"],
                      complete_state_verified=True, excluded_comparison_fields=["source_generation"])
        self.journal.record(event + "_verified", **result)
        return result

    def reset_bank(self, action: int, backup_directory: Path, originals: list[bytes]) -> dict:
        if action not in (3,4,5) or len(originals)!=64:raise ValueError('Exact reset action and64 original records required')
        for raw in originals:native.decode(raw)
        before=self.list_slots();start=64 if action==3 else 0
        live,_,saved=self._backup_live(backup_directory,'before explicit bank reset')
        backups=[]
        for slot in range(start,start+64):
            if before['slots'][slot]['present']:backups.append(self.export_slot(slot,backup_directory)['backup'])
        current=self.list_slots()
        if current!=before or self.status()['live_generation']!=native.decode(live)['source_generation']:
            raise RuntimeError('Unit changed during bank backup; reset refused')
        self.journal.record('bank_reset_intent',action=action,backups=backups,live_backup=saved,automatic_retry=False)
        final=self._storage_action(action,0,native.decode(live)['source_generation'],current['status'])
        after=self.list_slots()
        for slot in range(128):
            if not start<=slot<start+64:
                for field in ('present','crc','name_bytes'):
                    if before['slots'][slot][field]!=after['slots'][slot][field]:raise RuntimeError('Unrelated bank changed during reset')
            elif action==5:
                if after['slots'][slot]['present']:raise RuntimeError('Cleared USER slot is still present')
            else:
                raw,_=self.read_slot(slot);self._verify_state(originals[slot%64],raw,'bank_reset_slot')
        return dict(status=final,backups=backups,live_backup=saved,complete_bank_verified=True,flash_writes=True,transport_stopped=True)

    def save_slot(self, slot: int, backup_directory: Path) -> dict:
        slot_number(slot)
        before, _, saved = self._backup_live(backup_directory, f"complete live state before onboard save slot{slot}")
        prior = self._backup_slot(slot, backup_directory)
        current = self.status()
        if current["live_generation"] != native.decode(before)["source_generation"]:
            raise RuntimeError("Live state changed after pre-save backup; save refused")
        store = self._guard_slot(prior)
        final = self._storage_action(1, slot, current["live_generation"], store)
        actual, slot_state = self.read_slot(slot)
        verified = self._verify_state(before, actual, "onboard_save")
        return dict(slot=slot, pre_action_live_backup=saved, pre_action_slot_backup=prior["backup"],
                    status=final, slot_state=slot_state, **verified, flash_writes=True,
                    persistent_location="instrument NOR", ram_writes=False, transport_stopped=True)

    def load_slot(self, slot: int, backup_directory: Path) -> dict:
        slot_number(slot)
        before, _, saved = self._backup_live(backup_directory, f"complete live state before onboard load slot{slot}")
        prior = self._backup_slot(slot, backup_directory)
        if prior["raw"] is None:
            raise RuntimeError(f"Onboard slot {slot} is empty; load refused")
        current = self.status()
        if current["live_generation"] != native.decode(before)["source_generation"]:
            raise RuntimeError("Live state changed after pre-load backup; load refused")
        store = self._guard_slot(prior)
        final = self._storage_action(2, slot, current["live_generation"], store)
        actual, after = self.snapshot()
        verified = self._verify_state(prior["raw"], actual, "onboard_load")
        return dict(slot=slot, pre_action_live_backup=saved, pre_action_slot_backup=prior["backup"],
                    status=final, native_status=after, **verified, flash_writes=False, ram_writes=True,
                    transport_stopped=True)

    def push_slot(self, raw: bytes, slot: int, backup_directory: Path, *, transaction: int | None = None) -> dict:
        native.decode(raw)  # Validate before any command or backup artifact.
        slot_number(slot)
        prior = self._backup_slot(slot, backup_directory)
        self._guard_slot(prior)
        # restore() durably backs up live RAM before its first musical write.
        # Once it begins, any later failure leaves RAM potentially changed.
        try:
            ram = self.restore(raw, backup_directory, transaction=transaction)
            store = self._guard_slot(prior)
            current = self.status()
            if current["live_generation"] != ram["verified_generation"]:
                raise RuntimeError("Live state changed after PC restore; onboard save refused")
            final = self._storage_action(1, slot, current["live_generation"], store)
            actual, slot_state = self.read_slot(slot)
            verified = self._verify_state(raw, actual, "onboard_push")
            return dict(slot=slot, pre_action_live_backup=ram["pre_restore_backup"],
                        pre_action_slot_backup=prior["backup"], ram_restore=ram, status=final,
                        slot_state=slot_state, **verified, flash_writes=True, ram_writes=True,
                        persistent_location="instrument NOR", transport_stopped=True)
        except Exception as error:
            self.journal.record("onboard_push_incomplete", slot=slot, error=repr(error),
                                ram_may_have_changed=True, rollback_claimed=False,
                                pre_action_slot_backup=prior["backup"])
            raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--backup", action="store_true", help="Save a complete new host backup of live RAM")
    action.add_argument("--restore", type=Path, help="Restore a2176-byte file to RAM; stops transport")
    action.add_argument("--list-slots", action="store_true", help="Read all128 onboard catalog entries")
    action.add_argument("--export-slot", type=int, help="Back up one onboard slot to a new host file")
    action.add_argument("--load-slot", type=int, help="Back up live RAM and load the named onboard slot")
    action.add_argument("--save-slot", type=int, help="Back up destination and save current RAM to the named onboard slot")
    action.add_argument("--push", type=Path, help="Back up RAM/destination, restore this file, then save it to --slot")
    parser.add_argument("--slot", type=int, help="Explicit destination0..127, required only with --push")
    parser.add_argument("--backup-directory", type=Path, default=transport.ROOT / "local/library/device-backups/Test01")
    args = parser.parse_args(argv)
    if (args.push is None) != (args.slot is None):
        parser.error("--push requires --slot; --slot is only meaningful with --push")
    try:
        for value in (args.slot, args.export_slot, args.load_slot, args.save_slot):
            if value is not None:
                slot_number(value)
        requested = native.read_record(args.restore or args.push) if args.restore or args.push else None
    except (OSError, ValueError) as error:
        print(json.dumps(dict(success=False, error=str(error), device_opened=False)))
        return 1
    name = next(name for name in ("backup", "restore", "list_slots", "export_slot", "load_slot", "save_slot", "push")
                if getattr(args, name) is not None and getattr(args, name) is not False)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    journal = transport.Journal(transport.ROOT / "artifacts/fm1-native-bridge-v3" / stamp)
    result = dict(success=False, identity=IDENTITY, action=name,
                  flash_write_requested=name in ("save_slot", "push"),
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    session = None
    try:
        journal.record("native_bridge_start", **result)
        session = transport.find_session(hardware_bridge.WinMM(), IDENTITY, journal, wait=2)
        bridge = NativeBridge(session, journal)
        if name == "backup": outcome = bridge.backup(args.backup_directory)
        elif name == "restore": outcome = bridge.restore(requested, args.backup_directory)
        elif name == "list_slots": outcome = bridge.list_slots()
        elif name == "export_slot": outcome = bridge.export_slot(args.export_slot, args.backup_directory)
        elif name == "load_slot": outcome = bridge.load_slot(args.load_slot, args.backup_directory)
        elif name == "save_slot": outcome = bridge.save_slot(args.save_slot, args.backup_directory)
        else: outcome = bridge.push_slot(requested, args.slot, args.backup_directory)
        result.update(outcome, success=True)
    except Exception as error:
        result["error"] = repr(error)
    finally:
        if session is not None:
            try:
                failures = session.close()
                if failures: result.update(success=False, midi_cleanup_errors=failures)
            except Exception as error:
                result.update(success=False, midi_cleanup_errors=[repr(error)])
        try:
            journal.record("native_bridge_finished", **result)
            native._write_new(journal.directory / "report.json", (json.dumps(result, indent=2) + "\n").encode("utf-8"))
        except Exception as error:
            result.update(success=False, final_logging_error=repr(error))
        try:
            journal.close()
        except Exception as error:
            result.update(success=False, journal_close_error=repr(error))
    print(json.dumps(dict(success=result["success"], error=result.get("error"), artifacts=str(journal.directory),
                         slots=result.get("slots"))))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
