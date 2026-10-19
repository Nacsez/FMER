#!/usr/bin/env python3
"""Offline, hash-pinned Test01 dump comparison; never opens a device or builds an image."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import uuid

import acquire_stock_reference as stock
import fm1_package as package

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_FLASH_SHA256 = "c1068a403c04a6378a626afb66cc217f72d13f10aa200e983b7a9817cc1dac03"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def differences(actual: bytes, reference: bytes, base: int = 0) -> dict:
    if len(actual) != len(reference):
        raise ValueError("Comparison lengths differ")
    changed = [i for i, (a, b) in enumerate(zip(actual, reference)) if a != b]
    return {"bytes": len(actual), "actual_sha256": sha(actual), "reference_sha256": sha(reference),
            "changed_bytes": len(changed), "first_difference": base + changed[0] if changed else None,
            "last_difference": base + changed[-1] if changed else None,
            "changed_sectors": sorted({(base + i) & ~4095 for i in changed})}


def decode_key(data: bytes) -> int:
    for offset in range(32, 1024, 32):
        entry = bytearray(data[offset:offset + 32])
        package.enc(entry, 0, len(entry))
        header = package.jlfs_header(entry)
        if header[7].split(b"\0", 1)[0] == b"isd_config.ini":
            start = header[2]
            if not 0 <= start <= 0x4000 - 34:
                raise ValueError("Chip-key record leaves protected head")
            record = data[start:start + 34]
            if package.crc16(record[:32]) != int.from_bytes(record[32:], "little"):
                raise ValueError("Chip-key record CRC failed")
            return package.chipkey_decode(record[:32])
        if header[6]:
            break
    raise ValueError("No validated chip-key record")


def decode_app(raw: bytes, key: int) -> tuple[bytes, dict]:
    """Decode a bounded stock JLFS layout without assuming a publisher slot size.

    The known directory structure and flash map remain required. Every header,
    file extent and nested data CRC is checked; shifted file contents are never
    substituted with the published package's calibration or padding.
    """
    if len(raw) != 0x8F000:
        raise ValueError("Unexpected application-region length")
    plain = bytearray(raw)
    package.sfc(plain, 0, len(plain), 0, key)
    area = package.jlfs_header(plain[:32])
    app = package.jlfs_header(plain[32:64])
    if (area[2], area[7].split(b"\0", 1)[0]) != (0x02000120, b"app_area_head"):
        raise ValueError("Unrecognized app-area layout")
    if (app[2], app[7].split(b"\0", 1)[0]) != (0x120, b"app.bin") or not 4 <= app[3] <= len(plain) - 0x120:
        raise ValueError("Unrecognized app payload extent")
    app_end = app[2] + app[3]
    cfg_at = area[3]
    if not app_end <= cfg_at <= len(plain) - 64:
        raise ValueError("App-area/cfg extent leaves the known application region")
    if package.crc16(plain[32:cfg_at]) != area[1] or package.crc16(plain[app[2]:app[2] + app[3]]) != app[1]:
        raise ValueError("App-area or executable data CRC failed")
    tool = package.jlfs_header(plain[64:96])
    if (tool[7].split(b"\0", 1)[0] != b"cfg_tool.bin" or tool[2] != app_end
            or not 1 <= tool[3] <= cfg_at - app_end or tool[2] + tool[3] != cfg_at):
        raise ValueError("Configuration tool extent overlaps or leaves its app area")
    if package.crc16(plain[tool[2]:cfg_at]) != tool[1]:
        raise ValueError("Configuration tool data CRC failed")
    descriptors = []
    for index, (name, start, size) in enumerate((
            (b"VM", 0x93000, 352256), (b"PRCT", 0, 0x93000),
            (b"BTIF", 0xE9000, 0x1000), (b"USR", 0xEA000, 0x12000))):
        offset = 96 + index * 32
        record = package.jlfs_header(plain[offset:offset + 32])
        if (record[7].split(b"\0", 1)[0], record[2], record[3]) != (name, start, size):
            raise ValueError("Unrecognized flash-region descriptor")
        descriptors.append({"name": name.decode("ascii"), "offset": start, "bytes": size,
                            "attributes": record[4], "reserved": record[5], "index": record[6],
                            "header_sha256": sha(plain[offset:offset + 32])})
    cfg = package.jlfs_header(plain[cfg_at:cfg_at + 32])
    eq = package.jlfs_header(plain[cfg_at + 32:cfg_at + 64])
    if cfg[7].split(b"\0", 1)[0] != b"cfg" or eq[7].split(b"\0", 1)[0] != b"eq_cfg_hw.bin":
        raise ValueError("Unknown calibration directory")
    cfg_end = cfg_at + cfg[3]
    eq_start, eq_end = cfg_at + eq[2], cfg_at + eq[2] + eq[3]
    if cfg[2] != 32 or not cfg_at + 64 <= eq_start < eq_end <= cfg_end <= len(plain):
        raise ValueError("Calibration extents leave their directory")
    if package.crc16(plain[cfg_at + 32:cfg_end]) != cfg[1] or package.crc16(plain[eq_start:eq_end]) != eq[1]:
        raise ValueError("Calibration data CRC failed")
    return bytes(plain), {"app_start": app[2], "app_end": app_end, "app_bytes": app[3],
                          "cfg_tool_start": tool[2], "cfg_tool_end": cfg_at, "cfg_tool_bytes": tool[3],
                          "cfg_tool_sha256": sha(plain[tool[2]:cfg_at]),
                          "cfg_start": cfg_at, "cfg_end": cfg_end, "eq_start": eq_start,
                          "eq_end": eq_end, "eq_sha256": sha(plain[eq_start:eq_end]),
                          "app_sha256": sha(plain[app[2]:app_end]),
                          "calibration_sha256": sha(plain[cfg_at:cfg_end]),
                          "descriptors": descriptors, "validated_crcs": True}


def region_comparison(actual: bytes, reference: bytes, actual_start: int, reference_start: int) -> dict:
    """Align two logical files by relative offset, reporting physical starts.

    Different file lengths/positions are valid comparison results. This does
    not pretend bytes in relocated files occupy the same physical addresses.
    """
    common = min(len(actual), len(reference))
    shared = differences(actual[:common], reference[:common])
    return {"actual_start": actual_start, "reference_start": reference_start,
            "actual_bytes": len(actual), "reference_bytes": len(reference),
            "actual_sha256": sha(actual), "reference_sha256": sha(reference),
            "byte_equal": actual == reference, "common_bytes": common,
            "common_changed_bytes": shared["changed_bytes"],
            "first_common_difference_relative": shared["first_difference"],
            "last_common_difference_relative": shared["last_difference"],
            "actual_unpaired_bytes": len(actual) - common,
            "reference_unpaired_bytes": len(reference) - common}


def region_spans(layout: dict, length: int) -> dict:
    return {"area_header": (0, 32), "directory": (32, 0x120),
            "app_payload": (layout["app_start"], layout["app_end"]),
            "cfg_tool": (layout["cfg_tool_start"], layout["cfg_tool_end"]),
            "calibration": (layout["cfg_start"], layout["cfg_end"]),
            "eq_payload": (layout["eq_start"], layout["eq_end"]),
            "tail_padding": (layout["cfg_end"], length)}


def compare(data: bytes, expected_sha256: str, reference: bytes) -> dict:
    if len(data) != 0x100000 or sha(data) != expected_sha256:
        raise ValueError("Dump size or required SHA-256 mismatch")
    if (len(reference) != 0x93000 or sha(reference) != PUBLISHED_FLASH_SHA256 or
            sha(reference[0x4000:]) != stock.APP_SHA):
        raise ValueError("Published reference does not match its pinned flash/application hashes")
    key, reference_key = decode_key(data), decode_key(reference)
    actual, layout = decode_app(data[0x4000:0x93000], key)
    original, original_layout = decode_app(reference[0x4000:], reference_key)
    result = {"schema": "FMER_FLASH_COMPARISON", "version": 2,
              "dump_sha256": sha(data), "flash_bytes": len(data), "chip_key": key,
              "reference_chip_key": reference_key, "chip_keys_match": key == reference_key,
              "actual_layout": layout,
              "reference_layout": original_layout, "device_access": False, "writes": False,
              "scope": "Offline comparison of supplied bytes; device origin and acquisition timing require separate evidence. Not permission to flash.",
              "raw_app": differences(data[0x4000:0x93000], reference[0x4000:], 0x4000),
              "protected_head": differences(data[:0x4000], reference[:0x4000]),
              "private_tail_sha256": sha(data[0x93000:]), "plaintext_regions": {}, "region_comparisons": {}}
    spans, old_spans = region_spans(layout, len(actual)), region_spans(original_layout, len(original))
    result["layout_matches"] = spans == old_spans
    for name, (start, end) in spans.items():
        old_start, old_end = old_spans[name]
        result["region_comparisons"][name] = region_comparison(
            actual[start:end], original[old_start:old_end], 0x4000 + start, 0x4000 + old_start)
        if (start, end) == (old_start, old_end):
            result["plaintext_regions"][name] = differences(actual[start:end], original[start:end], 0x4000 + start)
    # The published final padding is raw FF, outside the encrypted JLFS files.
    # Decrypting it is useful only as a same-key byte comparison; different keys
    # otherwise create apparent differences even when physical bytes are equal.
    pad_start, old_pad_start = 0x4000 + layout["cfg_end"], 0x4000 + original_layout["cfg_end"]
    actual_pad, original_pad = data[pad_start:0x93000], reference[old_pad_start:]
    result["raw_tail_padding"] = (differences(actual_pad, original_pad, pad_start)
                                  if pad_start == old_pad_start else
                                  region_comparison(actual_pad, original_pad, pad_start, old_pad_start))
    result["raw_tail_padding"].update(actual_all_ff=all(b == 255 for b in actual_pad),
                                      reference_all_ff=all(b == 255 for b in original_pad),
                                      actual_non_ff_bytes=sum(b != 255 for b in actual_pad),
                                      reference_non_ff_bytes=sum(b != 255 for b in original_pad))
    result["region_comparisons"]["tail_padding"]["same_key_comparison"] = key == reference_key
    result["region_comparisons"]["tail_padding"]["same_physical_extent"] = pad_start == old_pad_start
    result["region_comparisons"]["tail_padding"]["decrypted_padding_comparable"] = key == reference_key and pad_start == old_pad_start
    if "tail_padding" in result["plaintext_regions"]:
        result["plaintext_regions"]["tail_padding"]["same_key_comparison"] = key == reference_key
    result["padding_scope"] = "Padding is not necessarily encrypted data. Decrypted padding comparisons require the same key and physical extent; raw_tail_padding compares recorded padding ranges without interpreting their contents."
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    out = ROOT / "artifacts/fm1-flash-comparison" / stamp
    out.mkdir(parents=True)
    report = {"success": False, "tool_sha256": sha(Path(__file__).read_bytes()), "device_access": False,
              "decoder_sources_sha256": {Path(module.__file__).name: sha(Path(module.__file__).read_bytes())
                                          for module in (package, stock)}}
    try:
        with args.dump.open("rb") as stream:
            data = stream.read(0x100001)
        reference = stock.decode_reference((stock.CACHE / "FM-1.fwsc").read_bytes())["stock-v15-flash.bin"]
        report.update(compare(data, args.expected_sha256, reference), success=True)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success": report["success"], "report": str(out / "report.json"), "error": report.get("error")}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
