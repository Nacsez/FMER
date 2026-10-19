#!/usr/bin/env python3
"""Validate the immutable research delivery and FMER traceability; no devices/network."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_FIELDS = ["id", "area", "requirement", "milestone", "mode", "status", "evidence"]
STATUSES = {"planned", "partial_seed", "partial", "passed", "failed", "blocked", "not_applicable"}
MODES = {"host", "host_then_bench", "host_and_bench", "recovery_bench", "bench"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def local_path(root: Path, relative: str) -> Path:
    """Resolve only workspace-relative, forward-slash paths, including on Windows."""
    item = PurePosixPath(relative)
    require(bool(relative) and not item.is_absolute() and ".." not in item.parts
            and "\\" not in relative and ":" not in relative,
            f"Unsafe relative path: {relative!r}")
    resolved = (root / Path(*item.parts)).resolve()
    require(resolved.is_relative_to(root.resolve()), f"Path escapes root: {relative}")
    return resolved


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(corpus: Path, expected_sha: str, expected_count: int) -> int:
    manifest = corpus / "MANIFEST.sha256"
    require(sha256(manifest) == expected_sha, "Delivered MANIFEST.sha256 identity changed")
    seen = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, f"Malformed manifest entry: {line!r}")
        expected, relative = match.groups()
        require(relative not in seen, f"Duplicate manifest entry: {relative}")
        seen.add(relative)
        path = local_path(corpus, relative)
        require(path.is_file(), f"Missing corpus file: {relative}")
        require(sha256(path) == expected, f"Corpus checksum mismatch: {relative}")
    require(len(seen) == expected_count, f"Expected {expected_count} manifest files; got {len(seen)}")
    # Discovery/imports can execute added files even when every shipped hash matches.
    # Only the documented, unused root acquisition area may contain later evidence.
    expected_paths = seen | {"MANIFEST.sha256"}
    for relative in seen:
        expected_paths.update(str(parent) for parent in PurePosixPath(relative).parents
                              if str(parent) != ".")
    actual = set()
    for path in corpus.rglob("*"):
        relative = path.relative_to(corpus)
        if relative.parts[0] == "acquired":
            continue
        require(path.resolve() == path.absolute(), f"Linked corpus path: {relative}")
        actual.add(relative.as_posix())
    unexpected = actual - expected_paths
    require(not unexpected, f"Unlisted corpus paths: {', '.join(sorted(unexpected))}")
    return len(seen)


def corpus_acceptance(markdown: str) -> dict[str, str]:
    return {row[0]: f"{row[1]} | Pass: {row[2]}" for row in re.findall(
        r"^\|\s*([PMQAD]\d{2})\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$", markdown, re.MULTILINE)}


def verify_acceptance(path: Path, original: dict[str, str]) -> int:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == ACCEPTANCE_FIELDS, "Acceptance CSV header changed")
        rows = list(reader)
    ids = [row["id"] for row in rows]
    require(len(ids) == len(set(ids)), "Duplicate acceptance ID")
    require(set(original).issubset(ids), "Original acceptance IDs are missing")
    require({"UI01", "PL01"}.issubset(ids), "Derived UI/platform acceptance rows missing")
    for row in rows:
        require(all(isinstance(row.get(key), str) and row[key].strip() for key in ACCEPTANCE_FIELDS)
                and None not in row, f"Empty or malformed acceptance row: {row.get('id')}")
        require(row["status"] in STATUSES, f"Unknown status: {row['id']}")
        require(row["mode"] in MODES, f"Unknown mode: {row['id']}")
        require(re.fullmatch(r"M[0-8]", row["milestone"]) is not None,
                f"Unknown milestone: {row['id']}")
        if row["id"] in original:
            require(row["requirement"] == original[row["id"]],
                    f"Original acceptance requirement changed: {row['id']}")
    return len(rows)


def verify_links(root: Path, documents: list[Path]) -> int:
    count = 0
    for document in documents:
        for target in re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", document.read_text(encoding="utf-8")):
            parts = urlsplit(target.strip("<>"))
            if parts.scheme or parts.netloc or not parts.path:
                continue
            path = (document.parent / unquote(parts.path)).resolve()
            require(path.is_relative_to(root.resolve()) and path.exists(),
                    f"Broken local link: {document.relative_to(root)} -> {target}")
            count += 1
    return count


def verify_dependencies(root: Path) -> int:
    lock = json.loads((root / "evidence/msfa-source.json").read_text(encoding="utf-8"))
    require(lock["schema_version"] == 1 and re.fullmatch(r"[0-9a-f]{40}", lock["commit"]) is not None,
            "MSFA dependency needs a pinned commit")
    vendor = local_path(root, lock["vendor_root"])
    seen = set()
    for entry in lock["files"]:
        require(entry["path"] not in seen, "Duplicate dependency file")
        seen.add(entry["path"])
        path = local_path(vendor, entry["path"])
        require(path.is_file() and sha256(path) == entry["local_sha256"],
                f"MSFA dependency hash mismatch: {entry['path']}")
    actual = {path.relative_to(vendor).as_posix() for path in vendor.rglob("*") if path.is_file()}
    require(actual == seen and "COPYING" in seen, "MSFA inventory/license mismatch")
    return len(seen)


def verify_parity(root: Path, corpus: Path) -> int:
    with (corpus / "data/feature_matrix.csv").open(encoding="utf-8-sig", newline="") as stream:
        original = list(csv.DictReader(stream))
    with (root / "docs/parity.csv").open(encoding="utf-8-sig", newline="") as stream:
        current = list(csv.DictReader(stream))
    require(len(current) == len(original) == 45, "Parity inventory must retain all 45 features")
    for index, (before, after) in enumerate(zip(original, current), 1):
        require(after["id"] == f"F{index:02d}", "Parity IDs/order changed")
        require(all(after[key] == value for key, value in before.items()),
                f"Original feature evidence changed: {after['id']}")
        require(after["fmer_status"] in {"implemented_host", "partial_host", "planned", "blocked_hardware", "reference_only"},
                f"Unknown parity status: {after['id']}")
    return len(current)


def verify(root: Path = ROOT) -> dict:
    lock = json.loads((root / "evidence/corpus.lock.json").read_text(encoding="utf-8"))
    require(lock["schema_version"] == 1, "Unsupported corpus lock schema")
    corpus = local_path(root, lock["corpus_path"])
    count = verify_manifest(corpus, lock["manifest_sha256"], lock["manifest_file_count"])
    # Syntax-check all delivered JSON inventories, then verify snapshot-level provenance.
    json_files = [path for path in corpus.rglob("*.json")
                  if path.relative_to(corpus).parts[0] != "acquired"]
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))
    snapshots = json.loads((corpus / "upstream/SNAPSHOT_INVENTORY.json").read_text(encoding="utf-8"))
    for snapshot in snapshots:
        payload = local_path(corpus, snapshot["path"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload).hexdigest()
        require(len(payload) == snapshot["bytes"] and blob == snapshot["git_blob_sha1"]
                and hashlib.sha256(payload).hexdigest() == snapshot["sha256"],
                f"Upstream snapshot provenance mismatch: {snapshot['path']}")
    for name, expected in lock["inventory_counts"].items():
        payload = json.loads((corpus / "data" / f"{name}.json").read_text(encoding="utf-8"))
        require(len(payload) == expected, f"Unexpected inventory count: {name}")
    source_rows = json.loads((corpus / "data/sources.json").read_text(encoding="utf-8"))
    require(len({row["id"] for row in source_rows}) == len(source_rows), "Duplicate source ID")
    archive = local_path(root, lock["archive_path"])
    archive_status = "not present (optional delivery archive; extracted corpus verified)"
    if archive.exists():
        require(sha256(archive) == lock["archive_sha256"], "Delivery ZIP checksum changed")
        with zipfile.ZipFile(archive) as bundle:
            require(bundle.testzip() is None, "Delivery ZIP has a CRC failure")
        archive_status = "SHA-256 and ZIP CRC verified"
    original = corpus_acceptance((corpus / "agent/ACCEPTANCE_TESTS.md").read_text(encoding="utf-8"))
    require(len(original) == 36, "Unexpected original acceptance inventory")
    rows = verify_acceptance(root / "docs/acceptance.csv", original)
    dependencies = verify_dependencies(root)
    parity = verify_parity(root, corpus)
    documents = list(root.glob("*.md")) + list((root / "docs").glob("*.md"))
    documents += [root / "third_party/README.md"]
    links = verify_links(root, documents)
    return {"schema_version": 1, "status": "passed", "scope": "corpus-integrity-and-traceability",
            "manifest_files": count, "json_inventories": len(json_files),
            "upstream_snapshot_files": len(snapshots), "acceptance_rows": rows,
            "dependency_files": dependencies, "parity_features": parity,
            "local_document_links": links, "archive": archive_status,
            "hardware_access": False, "musical_acceptance_executed": False}


def main() -> int:
    try:
        result = verify()
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
