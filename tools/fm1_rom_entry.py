#!/usr/bin/env python3
"""Explicit RAM-mailbox ROM entry from the exact qualified FMER loader only.

Source: firmware/fm1/loader/src/usb.c UBOOT_KEY and hal/fm1_sys.h
fm1_enter_uboot. This action resets the unit; it writes no flash. The separate
ROM backup tool must be prepared before use. No automatic retry or exit command.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

import fm1_flash_transport as update
import hardware_bridge as bridge

ROOT = Path(__file__).resolve().parents[1]
ROM_KEY = bytes.fromhex("F0 22 24 35 7D F7")


def enter(api, package, journal):
    update.require_write_qualification(package)
    _, loader, _ = update.update_identities(package)
    session = update.find_session(api, loader, journal, wait=2)
    try:
        status = session.loader_control(update.CONTROL_STATUS)
        # A reference mismatch does not prevent ROM readback. Busy, failed,
        # unknown-record and wrong-image states do. Nothing invokes stage2.
        update.require_loader_ready(status, package, resume=True)
        if status["state"] != 0 or status["error"]:
            raise update.UpdateError("ROM entry requires the idle, error-free loader")
        journal.record("rom_entry_intent", previous_status=status, flash_writes=False,
                       ram_mailbox_write=True, reset_requested=True,
                       expected_usb_vid=0x4C4A, expected_usb_pid=0x8057)
        session._send(ROM_KEY, "documented_mask_rom_entry")
        journal.record("rom_entry_command_completed", flash_writes=False,
                       limits="Command sent; ROM enumeration/readback still unverified")
    finally:
        if session.close():
            raise update.UpdateError("ROM entry MIDI cleanup reported an error; inspect log before continuing")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-loader-sha256", required=True)
    args = parser.parse_args(argv)
    journal = None
    try:
        package = update.qualify_package(args.package, args.expected_sha256, args.expected_loader_sha256)
        update.require_write_qualification(package)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
        journal = update.Journal(ROOT / "artifacts/fm1-rom-entry" / stamp)
        journal.record("qualified_before_device_access", unit_label="FMER Test01", package=package.report,
                       tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       transport_sha256=hashlib.sha256(Path(update.__file__).read_bytes()).hexdigest(),
                       bridge_sha256=hashlib.sha256(Path(bridge.__file__).read_bytes()).hexdigest())
        enter(bridge.WinMM(), package, journal)
        print(json.dumps({"command_sent": True, "rom_verified": False, "log": str(journal.directory)}))
        return 0
    except Exception as error:
        if journal:
            journal.record("failed", error=f"{type(error).__name__}: {error}", flash_writes=False)
        print(f"ROM entry stopped: {error}", file=sys.stderr)
        return 1
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
