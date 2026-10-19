#!/usr/bin/env python3
"""Passive Windows PnP evidence; never open an FM-1 or send device commands."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT_BYTES = 2 * 1024 * 1024
NAME_MATCH = re.compile(r"(?<![A-Z0-9])(?:FM[-_ ]?1|M[-_ ]?VAVE)(?![A-Z0-9])", re.I)
USB_IDS = re.compile(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})(?![0-9A-F])", re.I)
INTERFACE = re.compile(r"(?:^|&)MI_([0-9A-F]{2})(?:&|$)", re.I)
# Replace the complete instance/serial component, including composite suffixes.
INSTANCE = re.compile(r"\b([A-Za-z0-9_&.{}#+:=\-]+)\\+([A-Za-z0-9_&.{}#+:=\-]+)\\+([^\r\n\"'<>;,]+)")
REPORTED_IDS = {("4C4A", "C755"): "reported_normal", ("4D4A", "4155"): "reported_update"}
POWERSHELL_QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    $rows = @(Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Select-Object FriendlyName,Class,Status,InstanceId)
    @{status='ok';devices=$rows} | ConvertTo-Json -Depth 5 -Compress
    exit 0
} catch {
    @{status='error';devices=@();error=$_.Exception.Message} | ConvertTo-Json -Depth 5 -Compress
    exit 1
}
"""


def redact(text: str) -> str:
    """Do not retain any third PnP-instance component in text or error evidence."""
    return INSTANCE.sub(lambda match: match[1] + "\\" + match[2] + "\\[redacted]", text)


def text_field(value: object, field: str, maximum: int, *, nullable: bool = False) -> str:
    if nullable and value is None:
        return ""
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f"Invalid {field}; expected bounded text without control characters")
    return value


def parse_envelope(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("status") not in ("ok", "error"):
        raise ValueError("Query envelope must contain status=ok or status=error")
    if set(payload) - {"status", "devices", "error"}:
        raise ValueError("Unknown query envelope fields")
    rows = payload.get("devices")
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("Query envelope devices must be a bounded array")
    if payload["status"] == "error":
        error = payload.get("error")
        if not isinstance(error, str) or len(error) > 8192:
            raise ValueError("Invalid query error; expected bounded text")
        raise RuntimeError(redact(error))
    if "error" in payload:
        raise ValueError("Successful query cannot contain an error")
    candidates = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"FriendlyName", "Class", "Status", "InstanceId"}:
            raise ValueError("Malformed PnP row; expected FriendlyName, Class, Status, InstanceId")
        name = text_field(row["FriendlyName"], "friendly name", 1024, nullable=True)
        device_class = text_field(row["Class"], "class", 128, nullable=True)
        status = text_field(row["Status"], "status", 128, nullable=True)
        instance = text_field(row["InstanceId"], "instance ID", 4096)
        parts = instance.split("\\")
        ids = USB_IDS.search(parts[1]) if len(parts) >= 2 else None
        pair = tuple(part.upper() for part in ids.groups()) if ids else None
        interface = INTERFACE.search(parts[1]) if len(parts) >= 2 else None
        reasons = []
        if pair in REPORTED_IDS:
            reasons.append("reported_vid_pid")
        if NAME_MATCH.search(name):
            reasons.append("friendly_name")
        if not reasons:
            continue
        candidates.append({
            "name": redact(name), "class": redact(device_class), "status": redact(status),
            "vid": pair[0] if pair else None, "pid": pair[1] if pair else None,
            "interface": interface[1].upper() if interface else None,
            "match_reasons": reasons,
            "identity_hint": REPORTED_IDS.get(pair, "name_only_ambiguous"),
            "identity_confirmed": False,
        })
    return candidates


def decode_payload(raw: str) -> object:
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("Query payload exceeds the 2 MiB bound")
    try:
        return json.loads(raw.lstrip("\ufeff"))
    except (ValueError, RecursionError) as error:
        # A parser exception may quote private input. Keep only the failure category.
        raise ValueError("Query returned malformed JSON") from error


def query_windows() -> tuple[object, int]:
    if os.name != "nt":
        raise OSError("Passive PnP query requires Windows; use --input for an offline fixture")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_QUERY],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )
    if not completed.stdout.strip():
        message = redact(completed.stderr.strip())[:8192] or "PowerShell returned no query envelope"
        raise RuntimeError(f"PnP query exit {completed.returncode}: {message}")
    payload = decode_payload(completed.stdout)
    if completed.returncode != 0 and isinstance(payload, dict) and payload.get("status") == "ok":
        raise RuntimeError(f"PnP query exited {completed.returncode} despite a success envelope")
    return payload, completed.returncode


def collect(*, fixture: Path | None = None, unit_label: str | None = None,
            firmware_noted: str | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    report = {
        "schema_version": 1, "captured_at_utc": now,
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source": "offline_fixture" if fixture is not None else "windows_get_pnp_device_present_only",
        "hardware_access": "none_fixture" if fixture is not None else "passive_os_enumeration",
        "device_opened": False, "device_writes": False,
        "owner_observations": {"unit_label": unit_label, "firmware_noted": firmware_noted,
                               "classification": "owner_noted_unverified"},
        "status": "error", "candidates": [], "candidate_count": 0,
        "identity_confirmed": False,
        "reference": "corpus/upstream/ip2k/docs/01-hardware.md:105-106; reported IDs, not identity proof",
    }
    try:
        if unit_label is not None:
            text_field(unit_label, "unit label", 128)
        if firmware_noted is not None:
            text_field(firmware_noted, "owner firmware observation", 256)
        if fixture is not None:
            with fixture.open("rb") as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
            if len(raw) > MAX_INPUT_BYTES:
                raise ValueError("Fixture exceeds the 2 MiB bound")
            try:
                payload = decode_payload(raw.decode("utf-8-sig"))
            except UnicodeError as error:
                raise ValueError("Fixture must be UTF-8 JSON") from error
            report["fixture_sha256"] = hashlib.sha256(raw).hexdigest()
        else:
            payload, returncode = query_windows()
            report["query_returncode"] = returncode
        candidates = parse_envelope(payload)
        report.update(status="success", candidates=candidates, candidate_count=len(candidates))
        report["observation"] = (
            "Matching present OS nodes found; exact unit, firmware and capabilities remain unconfirmed"
            if candidates else "OS query succeeded with no matching present nodes; device absence is not established")
        report["update_identity_observed"] = any(c["identity_hint"] == "reported_update" for c in candidates)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        # Never claim an empty result when access or the query itself failed.
        message = "PnP query timed out" if isinstance(error, subprocess.TimeoutExpired) else str(error)
        report["error"] = {"type": type(error).__name__, "message": redact(message)[:8192]}
        report["observation"] = "Inventory inconclusive: query or input failed; connected-device state is unknown"
    return report


def write_report(report: dict, out: Path | None = None) -> Path:
    if out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        out = ROOT / "artifacts" / "hardware-inventory" / f"{stamp}-{uuid.uuid4().hex[:8]}" / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Preserve prior evidence; a specified output is always exclusive.
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-label", help="Owner alias; never an inferred unit identity")
    parser.add_argument("--firmware-noted", help="Owner's displayed firmware observation; retained verbatim")
    parser.add_argument("--input", type=Path, help="Offline raw PnP JSON envelope fixture; no OS query")
    parser.add_argument("--out", type=Path, help="Exclusive output file; defaults to a unique artifact directory")
    args = parser.parse_args(argv)
    report = collect(fixture=args.input, unit_label=args.unit_label, firmware_noted=args.firmware_noted)
    try:
        out = write_report(report, args.out)
    except OSError as error:
        print(f"Inventory evidence could not be written: {redact(str(error))}", file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "report": str(out),
                      "candidate_count": report["candidate_count"], "device_writes": False}))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
