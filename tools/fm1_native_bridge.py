#!/usr/bin/env python3
"""Explicit FMER707 complete native backup / RAM restore; never writes flash.

Run only while the session recorder and other MIDI clients are closed. Importing
performs no device access. The exact checksum-valid FM-1_707 identity is required
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

import fm1_native_state as native
import fm1_flash_transport as transport
import hardware_bridge

IDENTITY = "FM-1_707"


class NativeBridge:
    def __init__(self, session, journal, *, monotonic=time.monotonic, sleep=time.sleep):
        if getattr(session, "verified_identity", None) != IDENTITY:
            raise RuntimeError("Native bridge requires exact checksum-valid FM-1_707 identity")
        self.session, self.journal = session, journal
        self.monotonic, self.sleep = monotonic, sleep

    def request(self, wire: bytes, purpose: str) -> bytes:
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
            raw = self.request(native.chunk_request(token, offset), "native_read_chunk")
            result.extend(native.parse_chunk(raw, token=token, offset=offset))
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
                    transaction=transaction, complete_state_verified=True, ram_only=True, flash_writes=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--backup", action="store_true", help="Read complete native RAM state into a new host file")
    action.add_argument("--restore", type=Path, help="Restore this validated complete file to device RAM; stops transport")
    parser.add_argument("--backup-directory", type=Path, default=transport.ROOT / "local/native-backups")
    args = parser.parse_args(argv)
    # File validity is decided before opening the port or any output artifacts.
    try:
        requested = native.read_record(args.restore) if args.restore else None
    except (OSError, ValueError) as exc:
        print(json.dumps(dict(success=False, error=str(exc), device_opened=False)))
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    journal = transport.Journal(transport.ROOT / "artifacts/fm1-native-bridge" / stamp)
    result = dict(success=False, identity=IDENTITY, action="restore" if requested is not None else "backup",
                  flash_writes=False, tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    session = None
    try:
        journal.record("native_bridge_start", **result)
        session = transport.find_session(hardware_bridge.WinMM(), IDENTITY, journal, wait=2)
        bridge = NativeBridge(session, journal)
        result.update(bridge.restore(requested, args.backup_directory) if requested is not None else bridge.backup(args.backup_directory))
        result["success"] = True
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        if session is not None:
            try:
                failures = session.close()
                if failures:
                    result.update(success=False, midi_cleanup_errors=failures)
            except Exception as exc:
                result.update(success=False, midi_cleanup_errors=[repr(exc)])
        try:
            journal.record("native_bridge_finished", **result)
            native._write_new(journal.directory / "report.json", (json.dumps(result, indent=2) + "\n").encode("utf-8"))
        except Exception as exc:
            result.update(success=False, final_logging_error=repr(exc))
        try:
            journal.close()
        except Exception as exc:
            result.update(success=False, journal_close_error=repr(exc))
    print(json.dumps(dict(success=result["success"], error=result.get("error"), artifacts=str(journal.directory))))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
