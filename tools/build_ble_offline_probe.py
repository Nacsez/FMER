#!/usr/bin/env python3
"""Retain BLE transport in a separate target ELF to measure cost. No device I/O.

Requires a successful, current build_fm1_candidate output. Reuses verified
objects and pinned tools; never links vendor radio archives or produces an
update package. The probe entry is retained but is not called by board startup.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
try:
    from . import build_fm1_candidate as build, target_probe as probe
except ImportError:
    import build_fm1_candidate as build, target_probe as probe

ROOT = Path(__file__).resolve().parents[1]

def memory(elf: dict) -> dict:
    sections = elf["sections"]
    loads = [s["load_address"] + s["size"] for s in sections if s["load_address"] is not None]
    return {"application_bytes": max(loads) - build.XIP[0],
            "static_bytes": elf["startup_symbols"]["_bss_end"] - build.REGIONS[".data"][0],
            "workspace_bytes": sum(s["size"] for s in sections if s["name"] == ".workspace")}

def run(candidate: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": 1, "success": False, "created_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Offline retained transport probe; no radio runtime, no RF qualification",
              "device_opened": False, "flashable": False, "candidate": str(candidate), "commands": []}
    try:
        base = json.loads((candidate / "report.json").read_text(encoding="utf-8"))
        if not base["success"]: raise ValueError("Base build did not succeed")
        lock = json.loads(probe.LOCK.read_text(encoding="utf-8"))
        toolchain = ROOT / lock["toolchain"]["local_root"]
        probe.verify_files(toolchain, lock["toolchain"]["files"])
        for item in base["sources"] + base["local_headers"]:
            path = ROOT / item["path"]
            if path.is_file() and probe.sha256(path) != item["sha256"]:
                raise ValueError(f"Stale source/header: {path}")
        for item in base["objects"]:
            if probe.sha256(candidate / item["path"]) != item["sha256"]:
                raise ValueError(f"Changed object: {item['path']}")
        if probe.sha256(ROOT / "firmware/fm1/app.ld") != base["linker_script_sha256"]:
            raise ValueError("Stale linker script")
        def checked(name, command):
            result = probe.run_logged(command, output / (name + ".json"))
            report["commands"].append({"log": name + ".json", "exit_code": result["exit_code"]})
            if result["exit_code"]: raise RuntimeError(f"{name} failed; inspect its log")
            return result
        source = ROOT / "tests/ble_target_probe.cpp"
        obj = output / "ble_target_probe.o"
        compile_command = json.loads((candidate / "core__ble_midi.cpp.json").read_text())["command"]
        compile_command[compile_command.index("-c")+1] = str(source)
        compile_command[compile_command.index("-o")+1] = str(obj)
        checked("compile-probe", compile_command)
        link = json.loads((candidate / "link.json").read_text())["command"]
        link[link.index("-o")+1] = str(output / "fm1-ble-offline.elf")
        link[link.index("-Map")+1] = str(output / "fm1-ble-offline.map")
        link += ["--undefined=fmer_ble_offline_probe", str(obj)]
        checked("link-probe", link)
        undefined = checked("undefined-symbols", [str(toolchain / "bin/llvm-nm.exe"), "--undefined-only", str(output / "fm1-ble-offline.elf")])
        if undefined["stdout"].strip(): raise ValueError("Probe has unresolved symbols")
        dis = checked("disassembly", [str(toolchain / "bin/llvm-objdump.exe"), "-d", str(output / "fm1-ble-offline.elf")])
        (output / "disassembly.txt").write_text(dis["stdout"], encoding="utf-8")
        checked("symbols", [str(toolchain / "bin/llvm-nm.exe"), "--print-size", "--size-sort", str(output / "fm1-ble-offline.elf")])
        info = build.inspect_elf((output / "fm1-ble-offline.elf").read_bytes())
        baseline, retained = memory(base["elf"]), memory(info)
        report.update(success=True, baseline=baseline, retained=retained,
                      delta={key: retained[key]-baseline[key] for key in retained},
                      # Qualified Test01/Citrine application slot, stricter than
                      # the generic linker's XIP span by the package overhead.
                      measured_application_slot_bytes=580892,
                      free_application_bytes=580892-retained["application_bytes"],
                      free_static_bytes=98304-retained["static_bytes"],
                      elf_sha256=probe.sha256(output / "fm1-ble-offline.elf"),
                      probe_source_sha256=probe.sha256(source),
                      base_report_sha256=probe.sha256(candidate / "report.json"), elf=info)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        report["error"] = str(error)
    (output / "report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.candidate.resolve(), args.out.resolve())
    print(json.dumps({k: report[k] for k in ("success", "delta", "free_static_bytes", "error") if k in report}))
    return 0 if report["success"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
