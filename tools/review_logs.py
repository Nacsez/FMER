#!/usr/bin/env python3
"""Summarize retained render evidence without changing or deleting a session."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def review(directory: Path) -> dict:
    jobs, malformed = [], []
    for path in sorted(directory.glob("*/process.json"), key=lambda p: p.stat().st_mtime):
        try:
            process = json.loads(path.read_text(encoding="utf-8"))
            result_path = path.with_name("result.json")
            result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
            jobs.append({"job": path.parent.name,
                         "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                         "input": process.get("input", {}), "returncode": process.get("returncode"),
                         "stderr": process.get("stderr", ""), "elapsed_seconds": process.get("elapsed_seconds"),
                         "result_present": bool(result),
                         **{key: result.get(key) for key in ("build_id", "peak", "rms", "clipped_samples",
                             "fx_clipped_samples", "rejected_events", "active_voices_end", "tail_truncated", "wav_sha256")}})
        except (OSError, ValueError, TypeError) as exc:
            malformed.append({"file": str(path), "error": str(exc)})
    return {"schema_version": 1, "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "source": str(directory.resolve()), "hardware_access": False,
            "scope": "Retained jobs only; old UI actions and unlogged request refusals cannot be reconstructed.",
            "counts": {"jobs": len(jobs), "failed": sum(j["returncode"] != 0 for j in jobs),
                       "missing_result": sum(not j["result_present"] for j in jobs),
                       "clipping_jobs": sum(bool(j["clipped_samples"] or j["fx_clipped_samples"]) for j in jobs),
                       "rejected_event_jobs": sum(bool(j["rejected_events"]) for j in jobs),
                       "truncated_tail_jobs": sum(bool(j["tail_truncated"]) for j in jobs)},
            "scenario_counts": dict(Counter(j["input"].get("scenario", "note") for j in jobs)),
            "malformed": malformed, "jobs": jobs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "artifacts/sandbox")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = review(args.directory)
    target = args.out or ROOT / "artifacts/reviews" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2); stream.write("\n")
    print(json.dumps(result["counts"], indent=2)); print(target)
    return 1 if result["malformed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
