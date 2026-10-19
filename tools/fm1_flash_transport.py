#!/usr/bin/env python3
"""Strict FMER Test01 pull-update transport; the inspect action is offline.

Protocol sources (inspected, not executed):
AL-255/FM-1-RE ec832f281ca165a7d5e0722985f3acb1465046d5,
docs/io/11-ota-protocol.md; Felucca 20c275e39f75fa820978032efaceddfc5283c8cb,
tools/fm1_install.py. This independently implemented transport serves only an
exact-hash-qualified historical development transition or an exact
catalog-pinned release package.
Importing opens no DLL, port or device. Origin identity and actual-app admission
are separate gates.

The first upgrade stage can write loader staging/records. A later error MUST
NOT be reported as 'nothing written'. Finish is not success until exact normal
identity returns. Package validation does not itself qualify board/recovery.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import ctypes as ct
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import uuid

import device_protocol as protocol
import hardware_bridge as bridge

ROOT = Path(__file__).resolve().parents[1]
UPGRADE = bytes.fromhex("F0 22 24 35 7F F7")
VERIFY_DONE, WRITE_DONE = 0xE0000000, 0xF0000000
TARGET_ID, LOADER_ID, STOCK_ID = "FM-1_701", "ota-FM-1_701", "FM-1_015"
NEXT_TARGET_ID, NEXT_LOADER_ID = "FM-1_702", "ota-FM-1_702"
CURRENT_TARGET_ID, CURRENT_LOADER_ID = "FM-1_703", "ota-FM-1_703"
BUILD_TARGET_ID, BUILD_LOADER_ID = "FM-1_704", "ota-FM-1_704"
LATEST_TARGET_ID, LATEST_LOADER_ID = "FM-1_705", "ota-FM-1_705"
DEVELOPMENT_TARGET_ID, DEVELOPMENT_LOADER_ID = "FM-1_706", "ota-FM-1_706"
CANDIDATE_TARGET_ID, CANDIDATE_LOADER_ID = "FM-1_707", "ota-FM-1_707"
INSTRUMENT_TARGET_ID, INSTRUMENT_LOADER_ID = "FM-1_708", "ota-FM-1_708"
BANK_TARGET_ID, BANK_LOADER_ID = "FM-1_709", "ota-FM-1_709"
MIDI_TARGET_ID,MIDI_LOADER_ID="FM-1_710","ota-FM-1_710"
WORKSPACE_TARGET_ID,WORKSPACE_LOADER_ID="FM-1_711","ota-FM-1_711"
FX_TARGET_ID,FX_LOADER_ID="FM-1_712","ota-FM-1_712"
OPTIMIZED_FX_TARGET_ID,OPTIMIZED_FX_LOADER_ID="FM-1_713","ota-FM-1_713"
FINAL_FX_TARGET_ID,FINAL_FX_LOADER_ID="FM-1_714","ota-FM-1_714"
SHOWCASE_TARGET_ID,SHOWCASE_LOADER_ID="FM-1_715","ota-FM-1_715"
TIMBRE_TARGET_ID,TIMBRE_LOADER_ID="FM-1_716","ota-FM-1_716"
VISUAL_TARGET_ID,VISUAL_LOADER_ID="FM-1_717","ota-FM-1_717"
REACTIVE_TARGET_ID,REACTIVE_LOADER_ID="FM-1_718","ota-FM-1_718"
WORKSTATION_TARGET_ID,WORKSTATION_LOADER_ID="FM-1_719","ota-FM-1_719"
PROJECT_TARGET_ID,PROJECT_LOADER_ID="FM-1_720","ota-FM-1_720"
PERFORMANCE_TARGET_ID,PERFORMANCE_LOADER_ID="FM-1_721","ota-FM-1_721"
SYNC_TARGET_ID,SYNC_LOADER_ID="FM-1_722","ota-FM-1_722"
CLEANUP_TARGET_ID,CLEANUP_LOADER_ID="FM-1_723","ota-FM-1_723"
PREVIEW_TARGET_ID,PREVIEW_LOADER_ID="FM-1_724","ota-FM-1_724"
ROUTING_TARGET_ID,ROUTING_LOADER_ID="FM-1_728","ota-FM-1_728"
DEFAULTS_TARGET_ID,DEFAULTS_LOADER_ID="FM-1_729","ota-FM-1_729"
SONG_TARGET_ID,SONG_LOADER_ID="FM-1_730","ota-FM-1_730"
LINK_TARGET_ID,LINK_LOADER_ID="FM-1_731","ota-FM-1_731"
REFINEMENT_TARGET_ID,REFINEMENT_LOADER_ID="FM-1_733","ota-FM-1_733"
NAVIGATION_TARGET_ID="FM-1_734"  # Catalog release only; no legacy ota734 path.
WORKFLOW_TARGET_ID,WORKFLOW_LOADER_ID="FM-1_727","ota-FM-1_727"
POLISH_TARGET_ID,POLISH_LOADER_ID="FM-1_726","ota-FM-1_726"
RELEASE_TARGET_ID,RELEASE_LOADER_ID="FM-1_725","ota-FM-1_725"
SUPPORTED_TARGET_IDS = (TARGET_ID, NEXT_TARGET_ID, CURRENT_TARGET_ID, BUILD_TARGET_ID, LATEST_TARGET_ID, DEVELOPMENT_TARGET_ID, CANDIDATE_TARGET_ID, INSTRUMENT_TARGET_ID, BANK_TARGET_ID, MIDI_TARGET_ID, WORKSPACE_TARGET_ID, FX_TARGET_ID, OPTIMIZED_FX_TARGET_ID, FINAL_FX_TARGET_ID, SHOWCASE_TARGET_ID, TIMBRE_TARGET_ID, VISUAL_TARGET_ID, REACTIVE_TARGET_ID, WORKSTATION_TARGET_ID, PROJECT_TARGET_ID, PERFORMANCE_TARGET_ID, SYNC_TARGET_ID, CLEANUP_TARGET_ID, PREVIEW_TARGET_ID, RELEASE_TARGET_ID, POLISH_TARGET_ID, WORKFLOW_TARGET_ID, ROUTING_TARGET_ID, DEFAULTS_TARGET_ID, SONG_TARGET_ID, LINK_TARGET_ID, REFINEMENT_TARGET_ID)
SUPPORTED_LOADER_IDS = (LOADER_ID, NEXT_LOADER_ID, CURRENT_LOADER_ID, BUILD_LOADER_ID, LATEST_LOADER_ID, DEVELOPMENT_LOADER_ID, CANDIDATE_LOADER_ID, INSTRUMENT_LOADER_ID, BANK_LOADER_ID, MIDI_LOADER_ID, WORKSPACE_LOADER_ID, FX_LOADER_ID, OPTIMIZED_FX_LOADER_ID, FINAL_FX_LOADER_ID, SHOWCASE_LOADER_ID, TIMBRE_LOADER_ID, VISUAL_LOADER_ID, REACTIVE_LOADER_ID, WORKSTATION_LOADER_ID, PROJECT_LOADER_ID, PERFORMANCE_LOADER_ID, SYNC_LOADER_ID, CLEANUP_LOADER_ID, PREVIEW_LOADER_ID, RELEASE_LOADER_ID, POLISH_LOADER_ID, WORKFLOW_LOADER_ID, ROUTING_LOADER_ID, DEFAULTS_LOADER_ID, SONG_LOADER_ID, LINK_LOADER_ID, REFINEMENT_LOADER_ID)
SUPPORTED_LOADER_IDS += ('ota-FM-1_933','ota-FM-1_934','ota-FM-1_935')
SUPPORTED_TARGET_IDS += (NAVIGATION_TARGET_ID,)
MAX_PACKAGE = 2 * 1024 * 1024
MAX_DATA, MAX_REQUESTS, MAX_DUPLICATES = 512, 32768, 16
PORT_NAME = re.compile(r"^(?:[0-9]+\s*-\s*)?(?:FM[- ]?1(?:\s+Midi)?|ota-FM-1|FMER (?:Test01|Citrine)(?: Update| Midi)?|FMER Update|FMER(?: Midi)?)(?:\s+[0-9]+)?$", re.I)
CONTROL_PREFIX = b"\xF0\x7D" + b"FMER\x01"
CONTROL_STATUS, CONTROL_ABORT = 1, 2


class UpdateError(RuntimeError):
    pass


class IdentityTimeout(UpdateError):
    """Only the documented read-only identity exchange reached its deadline."""


@dataclass(frozen=True)
class ReadRequest:
    flags: int
    address: int
    length: int


def parse_request(frame: bytes) -> ReadRequest:
    if not isinstance(frame, bytes) or len(frame) != 20 or frame[0] != 0xF0 or frame[-1] != 0xF7:
        raise UpdateError("Read request must be one 20-byte SysEx frame")
    try:
        data = protocol.unpack_seven_bit(frame[1:-1], 15)
    except (ValueError, TypeError) as error:
        raise UpdateError(str(error)) from error
    if data[:3] != b"\x00\x59\x30" or int.from_bytes(data[3:6], "little") != 8:
        raise UpdateError("Unexpected command or declared request body length")
    if data[14] != (~sum(data[6:14]) & 255):
        raise UpdateError("Read request checksum mismatch")
    return ReadRequest(data[6], int.from_bytes(data[7:11], "little"), int.from_bytes(data[11:14], "little"))


def response(request: ReadRequest, payload: bytes, *, terminal: bool = False) -> bytes:
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_DATA or len(payload) != request.length:
        raise UpdateError("Response must contain the exact bounded requested payload")
    if type(request.flags) is not int or not 0 <= request.flags <= 255 or type(request.address) is not int or not 0 <= request.address <= 0xFFFFFFFF:
        raise UpdateError("Invalid response address or flags")
    body = (b"\x00\x59\x30" + (len(payload) + 8).to_bytes(3, "little") +
            bytes([0 if terminal else request.flags]) + request.address.to_bytes(4, "little") +
            len(payload).to_bytes(3, "little") + payload)
    return b"\xF0" + protocol.pack_seven_bit(body + bytes([~sum(body[6:]) & 255])) + b"\xF7"


def loader_control_request(operation: int) -> bytes:
    """New FMER-only protocol; never send this to stock or another loader."""
    if type(operation) is not int or operation not in (CONTROL_STATUS, CONTROL_ABORT):
        raise UpdateError("Unknown FMER loader operation")
    return CONTROL_PREFIX + bytes([operation, 0xF7])


def parse_loader_control_reply(frame: bytes, operation: int) -> dict:
    loader_control_request(operation)  # validate operation, no I/O
    if not isinstance(frame, bytes) or len(frame) != 28 or frame[:8] != CONTROL_PREFIX + bytes([operation | 0x40]) or frame[-1] != 0xF7:
        raise UpdateError("Unexpected FMER loader reply framing/version/operation")
    try:
        payload = protocol.unpack_seven_bit(frame[8:-1], 16)
    except (ValueError, TypeError) as error:
        raise UpdateError(str(error)) from error
    if payload[-1] != (~sum(payload[:-1]) & 255) or payload[0] > 5 or payload[5] not in (0, 1):
        raise UpdateError("Invalid FMER loader status/checksum")
    return {"protocol_version": 1, "operation": operation, "state": payload[0],
            "error": int.from_bytes(payload[1:5], "little", signed=True),
            "app_dirty": bool(payload[5]), "match_count": payload[6],
            "record_address": int.from_bytes(payload[7:11], "little"),
            "loader_length": int.from_bytes(payload[11:15], "little")}


@dataclass(frozen=True)
class QualifiedPackage:
    image: bytes
    report: dict
    app_begin: int
    app_end: int


def qualify_package(path: Path, expected_sha256: str, expected_loader_sha256: str) -> QualifiedPackage:
    """Read bounded bytes once, validate format, and bind both external hash pins."""
    import fm1_package
    for name, value in (("package", expected_sha256), ("loader", expected_loader_sha256)):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise UpdateError(f"An explicit lowercase SHA-256 is required for the {name}")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_PACKAGE + 1)
    if len(raw) > MAX_PACKAGE or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise UpdateError("Package exceeds size bound or differs from the expected SHA-256")
    try:
        import release_firmware
        report = release_firmware.inspect_bytes(raw) or fm1_package.validate_package(raw)
        product, image, files = fm1_package.decode_package(raw)
    except (ValueError, IndexError, KeyError, OverflowError) as error:
        raise UpdateError(f"Package qualification failed: {error}") from error
    if product not in SUPPORTED_TARGET_IDS or report["product"] != product or report["loader_sha256"] != expected_loader_sha256:
        raise UpdateError("Package product or loader differs from the qualified FMER Test01 build")
    start = files["flash.bin"]["offset"]
    report["loader_image_bytes"] = len(fm1_package.validate_loader(files["ota.bin"]["payload"]))
    package = QualifiedPackage(image, report, start + 0x4000, start + 0x93000)
    update_identities(package)
    return package


def update_identities(package) -> tuple[str, str, str]:
    """Return only reviewed origin/loader/target combinations; never a CLI override."""
    report = package.report
    if report.get('release_profile'):
        import release_firmware
        return release_firmware.update_identities(package)
    target = report.get("product")
    if target == NAVIGATION_TARGET_ID:
        raise UpdateError("FMER734 requires its exact catalog-pinned release profile")
    if target == TARGET_ID:
        expected = (STOCK_ID, LOADER_ID, TARGET_ID)
    elif target in SUPPORTED_TARGET_IDS[1:]:
        import fm1_package
        if target == NEXT_TARGET_ID:
            expected = (TARGET_ID, NEXT_LOADER_ID, NEXT_TARGET_ID)
            digest, package_hash = fm1_package.INSTALLED_701_APP_SHA256, fm1_package.INSTALLED_701_PACKAGE_SHA256
        elif target == CURRENT_TARGET_ID:
            expected = (NEXT_TARGET_ID, CURRENT_LOADER_ID, CURRENT_TARGET_ID)
            digest, package_hash = fm1_package.INSTALLED_702_APP_SHA256, fm1_package.INSTALLED_702_PACKAGE_SHA256
        elif target == BUILD_TARGET_ID:
            expected = (CURRENT_TARGET_ID, BUILD_LOADER_ID, BUILD_TARGET_ID)
            digest, package_hash = fm1_package.INSTALLED_703_APP_SHA256, fm1_package.INSTALLED_703_PACKAGE_SHA256
        elif target == LATEST_TARGET_ID:
            expected = (BUILD_TARGET_ID, LATEST_LOADER_ID, LATEST_TARGET_ID)
            digest, package_hash = fm1_package.INSTALLED_704_APP_SHA256, fm1_package.INSTALLED_704_PACKAGE_SHA256
        elif target == DEVELOPMENT_TARGET_ID:
            expected = (LATEST_TARGET_ID, DEVELOPMENT_LOADER_ID, DEVELOPMENT_TARGET_ID)
            digest, package_hash = fm1_package.INSTALLED_705_APP_SHA256, fm1_package.INSTALLED_705_PACKAGE_SHA256
        elif target == CANDIDATE_TARGET_ID:
            expected = (DEVELOPMENT_TARGET_ID, CANDIDATE_LOADER_ID, CANDIDATE_TARGET_ID)
            digest, package_hash = fm1_package.INSTALLED_706_APP_SHA256, fm1_package.INSTALLED_706_PACKAGE_SHA256
        elif target == INSTRUMENT_TARGET_ID:
            expected = (CANDIDATE_TARGET_ID, INSTRUMENT_LOADER_ID, INSTRUMENT_TARGET_ID)
            digest, package_hash = fm1_package.INSTALLED_707_APP_SHA256, fm1_package.INSTALLED_707_PACKAGE_SHA256
        elif target == BANK_TARGET_ID:
            expected = (INSTRUMENT_TARGET_ID, BANK_LOADER_ID, BANK_TARGET_ID)
            digest, package_hash = fm1_package.INSTALLED_708_APP_SHA256, fm1_package.INSTALLED_708_PACKAGE_SHA256
        elif target == MIDI_TARGET_ID:
            expected=(BANK_TARGET_ID,MIDI_LOADER_ID,MIDI_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_709_APP_SHA256,fm1_package.INSTALLED_709_PACKAGE_SHA256
        elif target == WORKSPACE_TARGET_ID:
            expected=(MIDI_TARGET_ID,WORKSPACE_LOADER_ID,WORKSPACE_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_710_APP_SHA256,fm1_package.INSTALLED_710_PACKAGE_SHA256
        elif target == FX_TARGET_ID:
            expected=(WORKSPACE_TARGET_ID,FX_LOADER_ID,FX_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_711_APP_SHA256,fm1_package.INSTALLED_711_PACKAGE_SHA256
        elif target == OPTIMIZED_FX_TARGET_ID:
            expected=(FX_TARGET_ID,OPTIMIZED_FX_LOADER_ID,OPTIMIZED_FX_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_712_APP_SHA256,fm1_package.INSTALLED_712_PACKAGE_SHA256
        elif target == FINAL_FX_TARGET_ID:
            expected=(OPTIMIZED_FX_TARGET_ID,FINAL_FX_LOADER_ID,FINAL_FX_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_713_APP_SHA256,fm1_package.INSTALLED_713_PACKAGE_SHA256
        elif target == SHOWCASE_TARGET_ID:
            expected=(FINAL_FX_TARGET_ID,SHOWCASE_LOADER_ID,SHOWCASE_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_714_APP_SHA256,fm1_package.INSTALLED_714_PACKAGE_SHA256
        elif target == TIMBRE_TARGET_ID:
            expected=(SHOWCASE_TARGET_ID,TIMBRE_LOADER_ID,TIMBRE_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_715_APP_SHA256,fm1_package.INSTALLED_715_PACKAGE_SHA256
        elif target == VISUAL_TARGET_ID:
            expected=(TIMBRE_TARGET_ID,VISUAL_LOADER_ID,VISUAL_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_716_APP_SHA256,fm1_package.INSTALLED_716_PACKAGE_SHA256
        elif target == REACTIVE_TARGET_ID:
            expected=(VISUAL_TARGET_ID,REACTIVE_LOADER_ID,REACTIVE_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_717_APP_SHA256,fm1_package.INSTALLED_717_PACKAGE_SHA256
        elif target == SYNC_TARGET_ID:
            if report.get('origin_identity')==SYNC_TARGET_ID:
                expected=(SYNC_TARGET_ID,SYNC_LOADER_ID,SYNC_TARGET_ID)
                digest,package_hash=fm1_package.INSTALLED_722_RELEASE1_APP_SHA256,fm1_package.INSTALLED_722_RELEASE1_PACKAGE_SHA256
            else:
                expected=(PERFORMANCE_TARGET_ID,SYNC_LOADER_ID,SYNC_TARGET_ID)
                digest,package_hash=fm1_package.INSTALLED_721_APP_SHA256,fm1_package.INSTALLED_721_PACKAGE_SHA256
        elif target == REFINEMENT_TARGET_ID:
            expected=(LINK_TARGET_ID,REFINEMENT_LOADER_ID,REFINEMENT_TARGET_ID)
            prefix='INSTALLED_CITRINE_731' if report.get('template')==fm1_package.CITRINE_TEMPLATE else 'INSTALLED_731'
            digest=getattr(fm1_package,prefix+'_APP_SHA256');package_hash=getattr(fm1_package,prefix+'_PACKAGE_SHA256')
        elif target == LINK_TARGET_ID:
            expected=(SONG_TARGET_ID,LINK_LOADER_ID,LINK_TARGET_ID)
            prefix='INSTALLED_CITRINE_730' if report.get('template')==fm1_package.CITRINE_TEMPLATE else 'INSTALLED_730'
            digest=getattr(fm1_package,prefix+'_APP_SHA256');package_hash=getattr(fm1_package,prefix+'_PACKAGE_SHA256')
        elif target == SONG_TARGET_ID:
            if report.get('template') == fm1_package.CITRINE_TEMPLATE:
                expected=(STOCK_ID,SONG_LOADER_ID,SONG_TARGET_ID)
                digest,package_hash=fm1_package.CITRINE_APP_SHA256,None
                if (report.get('reference_backup_sha256') != fm1_package.CITRINE_DUMP_SHA256 or
                        report.get('reference_backup_report_sha256') != fm1_package.CITRINE_REPORT_SHA256):
                    raise UpdateError('Citrine backup evidence differs')
            else:
                expected=(DEFAULTS_TARGET_ID,SONG_LOADER_ID,SONG_TARGET_ID)
                digest,package_hash=fm1_package.INSTALLED_729_RELEASE2_APP_SHA256,fm1_package.INSTALLED_729_RELEASE2_PACKAGE_SHA256
        elif target == DEFAULTS_TARGET_ID:
            if report.get('origin_identity')==DEFAULTS_TARGET_ID:
                expected=(DEFAULTS_TARGET_ID,DEFAULTS_LOADER_ID,DEFAULTS_TARGET_ID)
                digest,package_hash=fm1_package.INSTALLED_729_RELEASE1_APP_SHA256,fm1_package.INSTALLED_729_RELEASE1_PACKAGE_SHA256
            else:
                expected=(ROUTING_TARGET_ID,DEFAULTS_LOADER_ID,DEFAULTS_TARGET_ID)
                digest,package_hash=fm1_package.INSTALLED_728_RELEASE3_APP_SHA256,fm1_package.INSTALLED_728_RELEASE3_PACKAGE_SHA256
        elif target == ROUTING_TARGET_ID:
            if report.get('origin_identity')==ROUTING_TARGET_ID:
                expected=(ROUTING_TARGET_ID,ROUTING_LOADER_ID,ROUTING_TARGET_ID)
                digest,package_hash=fm1_package.INSTALLED_728_RELEASE1_APP_SHA256,fm1_package.INSTALLED_728_RELEASE1_PACKAGE_SHA256
            else:
                expected=(WORKFLOW_TARGET_ID,ROUTING_LOADER_ID,ROUTING_TARGET_ID)
                digest,package_hash=fm1_package.INSTALLED_727_APP_SHA256,fm1_package.INSTALLED_727_PACKAGE_SHA256
        elif target == WORKFLOW_TARGET_ID:
            expected=(POLISH_TARGET_ID,WORKFLOW_LOADER_ID,WORKFLOW_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_726_APP_SHA256,fm1_package.INSTALLED_726_PACKAGE_SHA256
        elif target == POLISH_TARGET_ID:
            expected=(PREVIEW_TARGET_ID,POLISH_LOADER_ID,POLISH_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_724_RELEASE3_APP_SHA256,fm1_package.INSTALLED_724_RELEASE3_PACKAGE_SHA256
        elif target == RELEASE_TARGET_ID:
            expected=(PREVIEW_TARGET_ID,RELEASE_LOADER_ID,RELEASE_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_724_RELEASE3_APP_SHA256,fm1_package.INSTALLED_724_RELEASE3_PACKAGE_SHA256
        elif target == PREVIEW_TARGET_ID:
            expected=(CLEANUP_TARGET_ID,PREVIEW_LOADER_ID,PREVIEW_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_723_RELEASE4_APP_SHA256,fm1_package.INSTALLED_723_RELEASE4_PACKAGE_SHA256
        elif target == CLEANUP_TARGET_ID:
            expected=(SYNC_TARGET_ID,CLEANUP_LOADER_ID,CLEANUP_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_722_RELEASE2_APP_SHA256,fm1_package.INSTALLED_722_RELEASE2_PACKAGE_SHA256
        elif target == PERFORMANCE_TARGET_ID:
            expected=(PROJECT_TARGET_ID,PERFORMANCE_LOADER_ID,PERFORMANCE_TARGET_ID)
            digest,package_hash=fm1_package.INSTALLED_720_RELEASE6_APP_SHA256,fm1_package.INSTALLED_720_RELEASE6_PACKAGE_SHA256
        elif target == PROJECT_TARGET_ID:
            if report.get('origin_identity') == PROJECT_TARGET_ID:
                expected=(PROJECT_TARGET_ID,PROJECT_LOADER_ID,PROJECT_TARGET_ID)
                admitted_pairs = (
                    (fm1_package.INSTALLED_720_RELEASE4_APP_SHA256, fm1_package.INSTALLED_720_RELEASE4_PACKAGE_SHA256),
                    (fm1_package.INSTALLED_720_RELEASE5_APP_SHA256, fm1_package.INSTALLED_720_RELEASE5_PACKAGE_SHA256),
                )
                origin_pair = (report.get('origin_app_sha256'), report.get('origin_package_sha256'))
                if origin_pair not in admitted_pairs:
                    raise UpdateError("Successor origin/profile differs from the exact installed Test01 package")
                digest,package_hash=origin_pair
            else:
                expected=(WORKSTATION_TARGET_ID,PROJECT_LOADER_ID,PROJECT_TARGET_ID)
                digest,package_hash=fm1_package.INSTALLED_719_INLINE_APP_SHA256,fm1_package.INSTALLED_719_INLINE_PACKAGE_SHA256
        else:
            if report.get('origin_identity')==WORKSTATION_TARGET_ID:
                expected=(WORKSTATION_TARGET_ID,WORKSTATION_LOADER_ID,WORKSTATION_TARGET_ID)
                admitted_pairs = (
                    (fm1_package.INSTALLED_719_APP_SHA256, fm1_package.INSTALLED_719_PACKAGE_SHA256),
                    (fm1_package.INSTALLED_719_CORRECTED_APP_SHA256, fm1_package.INSTALLED_719_CORRECTED_PACKAGE_SHA256),
                    (fm1_package.INSTALLED_719_FINAL_APP_SHA256, fm1_package.INSTALLED_719_FINAL_PACKAGE_SHA256),
                    (fm1_package.INSTALLED_719_OPTIMIZED_APP_SHA256, fm1_package.INSTALLED_719_OPTIMIZED_PACKAGE_SHA256),
                    (fm1_package.INSTALLED_719_ARITHMETIC_APP_SHA256, fm1_package.INSTALLED_719_ARITHMETIC_PACKAGE_SHA256),
                    (fm1_package.INSTALLED_719_PHASER_APP_SHA256, fm1_package.INSTALLED_719_PHASER_PACKAGE_SHA256),
                )
                origin_pair = (report.get('origin_app_sha256'), report.get('origin_package_sha256'))
                if origin_pair not in admitted_pairs:
                    raise UpdateError("Successor origin/profile differs from the exact installed Test01 package")
                digest, package_hash = origin_pair
            else:
                expected=(REACTIVE_TARGET_ID,WORKSTATION_LOADER_ID,WORKSTATION_TARGET_ID)
                digest,package_hash=fm1_package.INSTALLED_718_APP_SHA256,fm1_package.INSTALLED_718_PACKAGE_SHA256
        required = {"origin_identity": expected[0], "loader_identity": expected[1],
                    "origin_app_sha256": digest, "origin_package_sha256": package_hash,
                    "template": fm1_package.CITRINE_TEMPLATE if (target == SONG_TARGET_ID and expected[0] == STOCK_ID or target in (LINK_TARGET_ID,REFINEMENT_TARGET_ID) and report.get("template")==fm1_package.CITRINE_TEMPLATE) else fm1_package.TEST01_TEMPLATE}
        if any(report.get(key) != value for key, value in required.items()):
            raise UpdateError("Successor origin/profile differs from the exact installed Test01 package")
    else:
        raise UpdateError("Unsupported firmware transition")
    if (report.get("origin_identity", expected[0]) != expected[0] or
            report.get("loader_identity", expected[1]) != expected[1]):
        raise UpdateError("Package origin/loader identity does not match its target")
    return expected


class PullStage:
    """Offline request/reply state machine. Arbitrary read order is legitimate.

    Repeated requests receive byte-identical replies within explicit limits.
    Stage 1 requires every loader byte; stage 2 requires every application byte.
    No request causes a write to disk, a MIDI port or the connected device here.
    """
    def __init__(self, package: QualifiedPackage, stage: int, now: float = 0.0):
        if stage not in (1, 2) or not isinstance(package.image, bytes) or not 960 <= len(package.image) <= MAX_PACKAGE:
            raise UpdateError("Invalid stage or logical package size")
        if not 0 <= package.app_begin < package.app_end <= len(package.image):
            raise UpdateError("Invalid qualified application extent")
        if not math.isfinite(now):
            raise UpdateError("Invalid monotonic clock")
        self.package, self.stage = package, stage
        self.started = self.last = now
        self.idle_timeout = 8.0 if stage == 1 else 180.0
        self.total_timeout = 180.0 if stage == 1 else 900.0
        self.requests = self.data_requests = self.served_bytes = 0
        self.duplicates = Counter()
        if stage == 1:
            try:
                extent = package.report["files"]["ota.bin"]
                self.required_begin = extent["offset"]
                self.required_end = self.required_begin + extent["bytes"]
            except (KeyError, TypeError) as error:
                raise UpdateError("Missing qualified loader extent") from error
        else:
            self.required_begin, self.required_end = package.app_begin, package.app_end
        if not 0 <= self.required_begin < self.required_end <= len(package.image):
            raise UpdateError("Required transfer extent exceeds logical image")
        self.coverage = bytearray(self.required_end - self.required_begin)
        self.covered = 0
        self.finished = False

    def check_timeout(self, now: float) -> None:
        if not math.isfinite(now) or now < self.last:
            raise UpdateError("Monotonic clock moved backwards or became nonfinite")
        if now - self.last > self.idle_timeout or now - self.started > self.total_timeout:
            raise UpdateError(f"Stage {self.stage} timed out; device writes may already have occurred")

    def accept(self, frame: bytes, now: float) -> tuple[bytes, dict]:
        self.check_timeout(now)
        request = parse_request(frame)
        terminal = request.address in (VERIFY_DONE, WRITE_DONE)
        expected = VERIFY_DONE if self.stage == 1 else WRITE_DONE
        if terminal:
            if request.address != expected or request.length != 8:
                raise UpdateError("Unexpected stage terminal or terminal length")
            if not self.data_requests:
                raise UpdateError("Premature finish before any package read")
            if self.covered != len(self.coverage):
                raise UpdateError("Premature finish before complete loader/application coverage")
            payload = b"success\0"
        else:
            if self.finished:
                raise UpdateError("New data request after the stage finished")
            if not 1 <= request.length <= MAX_DATA or request.address > len(self.package.image) - request.length:
                raise UpdateError("Device requested bytes outside the qualified logical package")
            payload = self.package.image[request.address:request.address + request.length]
        if self.requests >= MAX_REQUESTS or self.duplicates[request] >= MAX_DUPLICATES:
            raise UpdateError("Bounded request/retry budget exhausted")
        answer = response(request, payload, terminal=terminal)
        self.requests += 1
        self.duplicates[request] += 1
        self.last = now
        if terminal:
            self.finished = True
        else:
            self.data_requests += 1
            self.served_bytes += request.length
            lo = max(request.address, self.required_begin) - self.required_begin
            hi = min(request.address + request.length, self.required_end) - self.required_begin
            if hi > lo:
                self.covered += self.coverage[lo:hi].count(0)
                self.coverage[lo:hi] = b"\1" * (hi - lo)
        return answer, {"stage": self.stage, "address": request.address, "length": request.length,
                        "flags": request.flags, "duplicate_count": self.duplicates[request],
                        "request_count": self.requests, "covered_app_bytes": self.covered if self.stage == 2 else 0,
                        "app_bytes": self.package.app_end - self.package.app_begin,
                        "covered_required_bytes": self.covered, "required_bytes": len(self.coverage),
                        "required_kind": "loader" if self.stage == 1 else "application", "terminal": terminal}


class Journal:
    """Exclusive, fsynced JSONL. A failed intent record prevents the action."""
    def __init__(self, directory: Path, progress=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.stream = (self.directory / "events.jsonl").open("x", encoding="utf-8")
        self.sequence = 0
        self.progress = progress
        self.device_writes_possible = False

    def record(self, event: str, **values) -> None:
        record = {"sequence": self.sequence, "utc": datetime.now(timezone.utc).isoformat(), "event": event, **values}
        self.stream.write(json.dumps(record, allow_nan=False) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.sequence += 1
        if self.progress is not None:self.progress(event, **values)
        if event in ("upgrade_intent", "explicit_abort_intent"):
            self.device_writes_possible = True

    def close(self):
        self.stream.close()


def select_pair(endpoints: dict) -> tuple[dict, dict]:
    chosen = []
    for direction in ("inputs", "outputs"):
        rows = [r for r in endpoints[direction] if PORT_NAME.fullmatch(r["name"])]
        if len(rows) != 1:
            raise UpdateError(f"Expected one uniquely named FM-1/FMER Test01 {direction}; found {len(rows)}")
        chosen.append(rows[0])
    # Windows direction indices differ; names, unlike indices, must pair.
    if chosen[0]["name"] != chosen[1]["name"]:
        raise UpdateError("Input/output endpoint names do not match")
    return chosen[0], chosen[1]


class MidiSession(bridge.IdentitySession):
    """Reuses typed WinMM ABI and conservative driver-buffer lifetime rules.

    Opened-handle GetDevCapsW is documented by Microsoft, not an index requery:
    https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midiingetdevcapsw
    https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midioutgetdevcapsw
    """
    def __init__(self, backend, selected: tuple[dict, dict], journal: Journal):
        self.selected, self.journal = selected, journal
        self.frames = deque()
        self.assembler = bridge.SysexAssembler(1024)
        self.closed = False
        self.verified_identity = None
        self.completed_stage = None
        super().__init__(backend, selected[0]["id"], selected[1]["id"], [])

    def _caps_match(self, direction, handle, expected):
        kind = bridge.MidiInCaps if direction == "In" else bridge.MidiOutCaps
        caps = kind()
        self.api.checked(f"midi{direction}GetDevCapsW", handle.value, ct.byref(caps), ct.sizeof(caps))
        actual = {"name": caps.szPname, "driver_manufacturer_id": caps.wMid,
                  "driver_product_id": caps.wPid, "driver_version": caps.vDriverVersion}
        if any(actual[key] != expected[key] for key in actual):
            raise UpdateError("Opened MIDI handle changed since enumeration; refusing all sends")
        if 'interface_sha256' in expected:
            import unit_endpoints
            unit_endpoints.verify_opened(self.api,direction,handle,expected)
        self.journal.record("opened_handle_verified", direction=direction, **actual)

    def __enter__(self):
        self.journal.record("open_intent", selected=self.selected)
        try:
            super().__enter__()
            self._caps_match("In", self.input, self.selected[0])
            self._caps_match("Out", self.output, self.selected[1])
            return self
        except BaseException:
            self.close()
            raise

    def _send(self, packet: bytes, purpose: str):
        if self.closed or not self.output or not isinstance(packet, bytes) or len(packet) > 1024:
            raise UpdateError("Closed session or oversized MIDI message")
        if self.out_buffer is not None:
            raise UpdateError("Previous MIDI output buffer still owned")
        self.journal.record("send_intent", purpose=purpose, bytes=len(packet), hex=packet.hex(" "))
        storage = ct.create_string_buffer(packet)
        header = bridge.MidiHeader(lpData=ct.addressof(storage), dwBufferLength=len(packet))
        self.api.checked("midiOutPrepareHeader", self.output, ct.byref(header), ct.sizeof(header))
        self.out_buffer = header, storage
        self.api.checked("midiOutLongMsg", self.output, ct.byref(header), ct.sizeof(header))
        deadline = time.monotonic() + 5.0
        while not header.dwFlags & bridge.MHDR_DONE:
            if time.monotonic() > deadline:
                raise UpdateError("MIDI output completion timed out; buffer retained until cleanup")
            time.sleep(.001)
        self.api.checked("midiOutUnprepareHeader", self.output, ct.byref(header), ct.sizeof(header))
        self.out_buffer = None

    def identify(self):
        self._send(protocol.IDENTITY_QUERY, "identity_query")
        frame = self.read(2.0)
        if frame is None:
            raise IdentityTimeout("Identity reply timed out")
        identity = protocol.parse_identity_reply(frame)
        self.journal.record("identity", **identity)
        self.verified_identity = identity["identity"]
        return identity["identity"]

    def loader_control(self, operation: int):
        expected = getattr(self, "expected_loader_identity", None)
        if expected not in SUPPORTED_LOADER_IDS or self.verified_identity != expected:
            raise UpdateError("FMER loader control requires the package's exact loader handshake")
        self._send(loader_control_request(operation), "loader_status" if operation == CONTROL_STATUS else "loader_abort")
        frame = self.read(2.0)
        if frame is None:
            raise UpdateError("FMER loader control reply timed out")
        status = parse_loader_control_reply(frame, operation)
        self.journal.record("loader_status_reply", **status)
        return status

    def metadata_page(self, page):
        if self.verified_identity not in ('ota-FM-1_934','ota-FM-1_935') or type(page)!=int or not 0<=page<20:
            raise UpdateError('This updater does not support metadata diagnosis. Power off and on, then retry with the included updater.')
        self._send(CONTROL_PREFIX+bytes((3,page,127-page,0xf7)), 'read_compatibility_metadata')
        frame=self.read(2.0)
        return parse_metadata_page(frame,page)

    def begin_stage(self, stage: int):
        self.journal.record("upgrade_intent", stage=stage, device_writes_possible=True)
        self._send(UPGRADE, f"begin_stage_{stage}")

    def answer(self, stage: PullStage, frame: bytes):
        packet, details = stage.accept(frame, time.monotonic())
        self.journal.record("accepted_request", **details)
        self._send(packet, "read_response")
        if details["terminal"]:
            # Set only after the terminal reply's output buffer completed and
            # was unprepared. This is the point a mode-switch is expected.
            self.completed_stage = stage.stage

    def read(self, timeout: float):
        deadline = time.monotonic() + timeout
        while True:
            if self.callback_overflow:
                raise UpdateError("MIDI callback queue overflow")
            while self.received:
                message, address, timestamp = self.received.popleft()
                pair = next((p for p in self.buffers if ct.addressof(p[0]) == address), None)
                if pair is None or message == bridge.MIM_LONGERROR:
                    raise UpdateError("Malformed input or unknown MIDI callback buffer")
                header, data = pair
                size = header.dwBytesRecorded
                if size > header.dwBufferLength:
                    raise UpdateError("Driver input length exceeds prepared buffer")
                chunk = bytes(data.raw[:size])
                if chunk:
                    self.journal.record("receive", timestamp_ms=timestamp, hex=chunk.hex(" "))
                    self.frames.extend(self.assembler.feed(chunk))
                if len(self.frames) > 64:
                    raise UpdateError("Complete MIDI frame queue overflow")
                header.dwBytesRecorded = 0
                self.api.checked("midiInAddBuffer", self.input, ct.byref(header), ct.sizeof(header))
            if self.frames:
                return self.frames.popleft()
            if time.monotonic() >= deadline:
                return None
            time.sleep(.002)

    def close(self):
        if self.closed:
            return []
        self.closed = True
        failures = super().close()
        cleanup = self.cleanup_results
        failed_calls = [call for call in cleanup if not call["ok"]]
        expected_disconnect = (
            self.completed_stage in (1, 2) and not self.input and not self.output and
            len(failed_calls) == 1 and failed_calls[0]["operation"] == "midiInStop" and
            failed_calls[0]["result"] == 6 and
            sum(call["operation"] == "midiInUnprepareHeader" and call["ok"] for call in cleanup) == len(self.buffers)
        )
        if expected_disconnect:
            # MMRESULT 6 is MMSYSERR_NODRIVER. After a completed stage the
            # device deliberately disconnects. Stop alone may report this;
            # reset, every unprepare and both closes MUST still have succeeded.
            self.journal.record("expected_mode_switch_disconnect", stage=self.completed_stage,
                                original_errors=failures, cleanup=cleanup,
                                all_driver_resources_released=True)
            if self in bridge._unreleased_sessions:
                bridge._unreleased_sessions.remove(self)
            failures = []
        self.journal.record("session_closed", errors=failures, lifecycle=self.events, cleanup=cleanup)
        return failures


def serve(session, package, stage_number, journal):
    stage = PullStage(package, stage_number, time.monotonic())
    session.begin_stage(stage_number)
    while not stage.finished:
        frame = session.read(.25)
        stage.check_timeout(time.monotonic())
        if frame is not None:
            session.answer(stage, frame)
    # Vendor worker holds the link for 3 seconds after verification terminal.
    # Reply to bounded terminal retries during this interval; never skip stage2.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        frame = session.read(min(.1, max(0, deadline - time.monotonic())))
        if frame is not None:
            session.answer(stage, frame)
    journal.record("stage_finished", stage=stage_number, requests=stage.requests,
                   served_bytes=stage.served_bytes, covered_required_bytes=stage.covered)


def find_session(api, expected: str, journal, *, wait: float, transitional: str | None = None,
                 retry_identity_timeout: bool = False):
    deadline = time.monotonic() + wait
    while True:
        endpoints = api.enumerate()
        if getattr(api, 'target_location', None):
            import unit_endpoints
            endpoints = unit_endpoints.filter_location(unit_endpoints.annotate(api,endpoints),api.target_location)
        counts = [sum(bool(PORT_NAME.fullmatch(r["name"])) for r in endpoints[d]) for d in ("inputs", "outputs")]
        if any(count > 1 for count in counts):
            raise UpdateError("Multiple candidate instruments; refusing ambiguous updater connection")
        if counts == [1, 1]:
            selected = select_pair(endpoints)
            session = MidiSession(api, selected, journal)
            try:
                session.__enter__()
                identity = session.identify()
                compatible = expected == 'compatible-FM-1' and (re.fullmatch(r'FM-1_[0-9]{3}',identity) or identity=='ota-FM-1_935')
                if identity == expected or compatible or expected is None:
                    session.expected_loader_identity = expected if expected in SUPPORTED_LOADER_IDS else None
                    return session
                if identity != transitional and not (transitional=='compatible-FM-1' and re.fullmatch(r'FM-1_[0-9]{3}',identity)):
                    raise UpdateError(f"Unexpected identity {identity!r}; expected {expected!r}")
            except IdentityTimeout:
                failures = session.close()
                journal.record("identity_timeout", expected_identity=expected,
                               retry_allowed=retry_identity_timeout, cleanup_errors=failures,
                               remaining_seconds=max(0, deadline - time.monotonic()))
                if failures:
                    raise UpdateError("Identity timeout cleanup failed; refusing retry")
                if not retry_identity_timeout:
                    raise
                session = None
            except BaseException:
                session.close()
                raise
            if session is not None and session.close():
                raise UpdateError("Transition identity cleanup failed; refusing retry")
        if time.monotonic() >= deadline:
            raise UpdateError(f"Timed out waiting for {expected}; no automatic reset or rollback sent")
        time.sleep(.25)


def require_write_qualification(package):
    update_identities(package)
    if package.report.get("runtime_preflight_qualified") is not True:
        raise UpdateError("Firmware-origin handoff evidence is unqualified; no device access permitted")


def require_loader_ready(status: dict, package: QualifiedPackage, *, resume: bool):
    """Validate the target's read-only admission result before stage2 upgrade.

    Explicit resume may retry transport/flash failures, but never wrong-key,
    unknown-flash or record-proof failures. Target independently repeats all
    admission checks before erasing and recomputes origin integrity from flash
    across resets; a fresh abort rehashes the complete original application.
    """
    record = status["record_address"]
    if package.report.get('release_profile') and not package.report.get('compatible_layout') and (resume or record != package.report['record_address']):
        raise UpdateError('First-install preview requires its exact stock staging record; automatic resume is unavailable')
    if package.report.get('compatible_layout') and record not in (0xE4F00,0xE7F00):
        raise UpdateError('This update-record layout is not supported; no application data sent')
    expected_length = package.report.get("loader_image_bytes")
    if (type(record) is not int or not 0x93000 <= record < 0xE9000 or record & 0xFFF != 0xF00 or
            status["match_count"] != 1 or type(expected_length) is not int or expected_length <= 0 or
            status["loader_length"] != expected_length):
        raise UpdateError("Loader admission record or executable length does not match the qualified package")
    if package.report.get('compatible_layout') and status['app_dirty'] and status['state']==0:
        raise UpdateError('This unit has a different memory layout or calibration; application writing was not started')
    ready = status["state"] == 0 and status["error"] == 0
    retryable = resume and status["state"] == 4 and status["error"] in (-5, -7, -8, -9, -10, -11, -12, -13)
    if not (ready or retryable) or (status["app_dirty"] and not resume):
        raise UpdateError("Loader is not ready for this operation; explicit resume is required for an interrupted application write")


def parse_metadata_page(frame, page):
    if not isinstance(frame,bytes) or len(frame)!=305 or frame[:8]!=CONTROL_PREFIX+b'\x43' or frame[-1]!=0xf7:
        raise UpdateError('Incomplete metadata reply; no application writing started')
    try:data=protocol.unpack_seven_bit(frame[8:-1])
    except ValueError as error:raise UpdateError('Invalid metadata encoding') from error
    if len(data)!=259 or data[0]!=page or data[1]!=0 or (sum(data)&255)!=255:
        raise UpdateError('Metadata reply failed its page/read/checksum check')
    return data[2:258]


def collect_metadata(session, package, journal):
    records=[];flash_start=package.app_begin-0x4000
    journal.record('update_phase',phase='Reading device compatibility details (no application write)',stage=2)
    for page in range(20):
        off=0x4000+page*256 if page<2 else 0x91e00+(page-2)*256
        data=session.metadata_page(page)
        expected=package.image[flash_start+off:flash_start+off+256]
        record=dict(page=page,offset=off,hex=data.hex(),sha256=hashlib.sha256(data).hexdigest(),
                    differing_bytes=sum(a!=b for a,b in zip(data,expected)))
        records.append(record);journal.record('metadata_page',**record)
    header=bytes.fromhex(records[0]['hex']+records[1]['hex']);tail=b''.join(bytes.fromhex(x['hex']) for x in records[2:])
    compatibility_sha256=hashlib.sha256(header[4:32]+header[36:0x120]+tail[0x3c:]).hexdigest()
    result=dict(scope='20 fixed pages: application directory and configuration tail; excludes boot identity and saved banks',
                pages=records,compatibility_sha256=compatibility_sha256,application_write_started=False,
                interpretation='A mismatch is not proof of different hardware. Compare directory fields and calibration separately.')
    journal.record('compatibility_metadata',metadata=result)
    return result


def perform_update(api, package: QualifiedPackage, journal, *, resume: bool = False):
    require_write_qualification(package)
    origin, loader, target = update_identities(package)
    stages = ((2, loader, None, 2.0),) if resume else ((1, origin, None, 10.0), (2, loader, origin, 40.0))
    for stage, expected, transitional, wait in stages:
        journal.record('update_phase',phase='Connecting to instrument' if stage==1 else 'Waiting for updater',stage=stage)
        session = find_session(api, expected, journal, wait=wait, transitional=transitional,retry_identity_timeout=True)
        try:
            if stage==1 and package.report.get('compatible_layout') and session.verified_identity==loader:
                resume=True
                journal.record('update_phase',phase='Resuming firmware transfer',stage=2)
                continue
            if stage == 2:
                status = session.loader_control(CONTROL_STATUS)
                journal.record("explicit_resume_status" if resume else "stage2_admission_status", status=status)
                if session.verified_identity=='ota-FM-1_935' and status['state']==0 and status['app_dirty']:
                    collect_metadata(session,package,journal)
                require_loader_ready(status, package, resume=resume)
            serve(session, package, stage, journal)
        finally:
            failures = session.close()
            if failures:
                raise UpdateError("MIDI cleanup failed; retained driver buffers, refusing next stage")
    journal.record("update_phase",phase="Restarting and verifying firmware",stage=3)
    session = find_session(api, target, journal, wait=45.0, transitional=loader,retry_identity_timeout=True)
    try:
        journal.record("post_reboot_identity_verified", identity=target,
                       limits="Identity only; audio/panel/storage/recovery require separate checks")
    finally:
        if session.close():
            raise UpdateError("Post-verify MIDI cleanup failed")


def perform_loader_probe(api, package: QualifiedPackage, journal, *, duration: float = 190.0, metadata_only: bool = False):
    """Stage only the qualified loader, then observe it without starting stage2.

    Keep one exact-identity loader session open. A disconnect, invalid status or
    timeout ends the observation; silently reconnecting would conceal a reset.
    Stage1 still writes loader staging/records. This is not an application flash
    or recovery action, and never sends an abort or a second upgrade command.
    """
    require_write_qualification(package)
    origin, loader, target = update_identities(package)
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 190:
        raise UpdateError("Loader probe duration must be finite and within 0..190 seconds")
    session, last_status, sample_count = None, None, 0
    phase, started = "origin_identity", time.monotonic()
    journal.record("loader_probe_intent", duration_seconds=duration, interval_seconds=5,
                   stages_allowed=[1], app_upgrade_allowed=False, abort_allowed=False)
    try:
        session = find_session(api, origin, journal, wait=2.0)
        phase = "stage1"
        serve(session, package, 1, journal)
        phase = "stage1_cleanup"
        failures = session.close()
        session = None
        if failures:
            raise UpdateError("Loader probe stage1 cleanup failed; refusing loader observation")
        phase = "loader_identity"
        journal.record("loader_probe_transition", expected_identity=loader, wait_seconds=45,
                       identity_timeout_retry=True)
        session = find_session(api, loader, journal, wait=45.0, transitional=origin,
                               retry_identity_timeout=True)
        phase = "loader_status"
        journal.record("loader_probe_sample_intent", sample=0, elapsed_seconds=0)
        last_status = session.loader_control(CONTROL_STATUS)
        journal.record("loader_probe_sample", sample=0, elapsed_seconds=0, status=last_status)
        if metadata_only:
            if session.verified_identity != 'ota-FM-1_935' or last_status['state'] != 0 or last_status['error'] or last_status['match_count'] != 1:
                raise UpdateError('Diagnostic updater is not ready for metadata reads')
            collect_metadata(session, package, journal)
            journal.record('metadata_probe_completed', app_upgrade_sent=False)
            return
        require_loader_ready(last_status, package, resume=False)
        sample_count = 1
        # Begin the full observation window only after identity AND admission
        # status have arrived; startup hashing time is not observation time.
        observation_started = time.monotonic()
        while True:
            remaining = duration - (time.monotonic() - observation_started)
            if remaining <= 0:
                break
            time.sleep(min(5.0, remaining))
            elapsed = time.monotonic() - observation_started
            journal.record("loader_probe_sample_intent", sample=sample_count, elapsed_seconds=elapsed)
            last_status = session.loader_control(CONTROL_STATUS)
            journal.record("loader_probe_sample", sample=sample_count, elapsed_seconds=elapsed,
                           status=last_status)
            sample_count += 1
            require_loader_ready(last_status, package, resume=False)
        phase = "loader_cleanup"
        failures = session.close()
        session = None
        if failures:
            raise UpdateError("Loader probe cleanup failed")
        journal.record("loader_probe_completed", identity=loader, samples=sample_count,
                       observation_seconds=time.monotonic() - observation_started,
                       last_status=last_status, stages_completed=[1], app_upgrade_sent=False,
                       limits="Loader identity/status only; application firmware was not requested")
    except BaseException as error:
        journal.record("loader_probe_failed", phase=phase, samples=sample_count,
                       elapsed_seconds=time.monotonic() - started, last_status=last_status,
                       error=f"{type(error).__name__}: {error}", app_upgrade_sent=False)
        raise
    finally:
        if session is not None and session.close():
            raise UpdateError("Loader probe failed and MIDI cleanup also failed; see lifecycle log")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "flash", "resume", "probe-loader", "diagnose-layout", "loader-status", "loader-abort"))
    parser.add_argument("package", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-loader-sha256", required=True)
    parser.add_argument("--unit-label", choices=("FMER Test01", "Citrine", "Amethyst"), default="FMER Test01")
    parser.add_argument("--artifacts-root", type=Path, default=ROOT / "artifacts/fm1-flash")
    args = parser.parse_args(argv)
    journal = None
    try:
        package = qualify_package(args.package, args.expected_sha256, args.expected_loader_sha256)
        origin, loader, target = update_identities(package)
        if args.action == "inspect":
            print(json.dumps({"status": "format_and_hashes_valid", "device_access": False, **package.report}, indent=2))
            return 0
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        journal = Journal(args.artifacts_root / f"{stamp}-{uuid.uuid4().hex[:8]}")
        import fm1_package
        journal.record("qualified_before_device_access", unit_label=args.unit_label, package=package.report,
                       tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       bridge_sha256=hashlib.sha256(Path(bridge.__file__).read_bytes()).hexdigest(),
                       protocol_sha256=hashlib.sha256(Path(protocol.__file__).read_bytes()).hexdigest(),
                       validator_sha256=hashlib.sha256(Path(fm1_package.__file__).read_bytes()).hexdigest())
        if args.action in ("flash", "resume", "probe-loader", "diagnose-layout"):
            # Qualification comes only from the validator's inspected loader
            # and matching evidence, never a CLI force flag or external boolean.
            require_write_qualification(package)
            if args.action in ("probe-loader", "diagnose-layout"):
                perform_loader_probe(bridge.WinMM(), package, journal, metadata_only=args.action == 'diagnose-layout')
                print(f"Updater diagnostic complete; stage2 not requested; log: {journal.directory}")
            else:
                perform_update(bridge.WinMM(), package, journal, resume=args.action == "resume")
                journal.record("completed", identity=target, unit_label=args.unit_label)
                print(f"Verified {target}; log: {journal.directory}")
        else:
            if args.action == "loader-abort":
                require_write_qualification(package)
            session = find_session(bridge.WinMM(), loader, journal, wait=2.0)
            try:
                status = session.loader_control(CONTROL_STATUS)
                if args.action == "loader-abort":
                    require_loader_ready(status, package, resume=False)
                    if status["app_dirty"] or status["match_count"] != 1:
                        raise UpdateError("Abort refused: application changed or active loader record is not unique")
                    journal.record("explicit_abort_intent", previous_status=status)
                    status = session.loader_control(CONTROL_ABORT)
                    if status["state"] != 5 or status["error"] or status["app_dirty"]:
                        raise UpdateError("Loader refused abort; no automatic reset requested")
                journal.record("loader_control_completed", action=args.action, status=status)
                print(json.dumps({"status": status, "log": str(journal.directory)}, indent=2))
            finally:
                if session.close():
                    raise UpdateError("Loader control cleanup failed")
        return 0
    except (Exception, KeyboardInterrupt) as error:
        if journal is not None:
            try:
                journal.record("failed", error=f"{type(error).__name__}: {error}",
                               device_writes_possible=journal.device_writes_possible, recovery_attempted=False)
            except Exception:
                pass
        print(f"Update stopped: {error}", file=sys.stderr)
        return 1
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
