#!/usr/bin/env python3
"""Enter ROM from checksum-valid stock V15, without staging an update.

Reviewed source: Transporter a632d923, docs/PROTOCOL.md, Entry section.
Only identity and the documented soft key are sent. No generic send, flash
write, fallback, retry, or restore operation is provided.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

import hardware_bridge as bridge
import fm1_flash_transport as transport

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "third_party/acquired/fm1-target-review/recovery/transporter/source/docs/PROTOCOL.md"
SOURCE_SHA = "c5b9b25136383c5684451bda63eaa737ffe2d10d4ea1e63d62908316124813bf"
ROM_KEY = bytes.fromhex("F0 22 24 35 7D F7")


def enter(session, journal):
    if session.identify() != "FM-1_015":
        raise transport.UpdateError("Stock ROM entry requires exact checksum-valid FM-1_015")
    journal.record("stock_rom_entry_intent", flash_writes=False,
                   update_loader_staged=False, reset_requested=True,
                   expected_usb_vid=0x4C4A, expected_usb_pid=0x8057)
    session._send(ROM_KEY, "documented_stock_v15_rom_entry")
    journal.record("stock_rom_entry_sent", rom_verified=False, flash_writes=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-label", required=True)
    parser.add_argument("--input-id", required=True, type=int)
    parser.add_argument("--output-id", required=True, type=int)
    args = parser.parse_args(argv)
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA:
        parser.error("Reviewed stock-entry source hash differs")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    journal = transport.Journal(ROOT / "artifacts/fm1-stock-rom-entry" / stamp)
    session = None
    outcome = 1
    try:
        api = bridge.WinMM()
        selected = bridge.select_pair(api.enumerate(), args.input_id, args.output_id)
        if any(row["name"] != "FM-1 Midi" for row in selected):
            raise transport.UpdateError("Stock entry requires matching exact FM-1 Midi endpoint names")
        journal.record("start", unit_label=args.unit_label, source_sha256=SOURCE_SHA,
                       tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        session = transport.MidiSession(api, selected, journal)
        session.__enter__()
        enter(session, journal)
        print(json.dumps({"command_sent": True, "rom_verified": False,
                          "flash_writes": False, "journal": str(journal.directory)}))
        outcome = 0
    except Exception as error:
        journal.record("failed", error=f"{type(error).__name__}: {error}")
        print(json.dumps({"status": "failed", "error": str(error), "journal": str(journal.directory)}))
    finally:
        if session is not None:
            errors = session.close()
            if errors:
                journal.record("cleanup_errors", errors=errors)
                outcome = 1
        journal.close()
    return outcome


if __name__ == "__main__":
    raise SystemExit(main())
