#!/usr/bin/env python3
"""Compile/link-only pi32v2 proof. Never opens a device or emits a flash image."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "evidence/target-toolchain.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_files(root: Path, files: list[dict]) -> None:
    """Reject missing, changed and path-escaping pinned inputs before execution."""
    root = root.resolve()
    for item in files:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Missing or unsafe pinned input: {item['path']}")
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Pinned input SHA-256 mismatch: {item['path']}")


def elf_identity(data: bytes, expected_type: int) -> dict:
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Expected complete little-endian ELF32 header")
    elf_type, machine, version, entry = struct.unpack_from("<HHII", data, 16)
    if machine != 0xF1 or elf_type != expected_type or version != 1:
        raise ValueError("Expected pi32v2 ELF with the requested object/executable type")
    return {"class": "ELF32", "byte_order": "little", "machine": machine,
            "type": elf_type, "entry": entry}


def run_logged(command: list[str], path: Path) -> dict:
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False)
        record = {"command": command, "exit_code": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr}
    except OSError as error:
        record = {"command": command, "exit_code": None,
                  "stdout": "", "stderr": str(error)}
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def build_probe(toolchain: Path, libcxx: Path, output: Path, lock: dict) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": 1, "kind": "compile_link_probe", "flashable": False,
              "device_opened": False, "device_writes": False,
              "target_executed": False, "success": False,
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "toolchain_lock_sha256": sha256(LOCK), "commands": [],
              "objects": [], "sources": []}
    try:
        verify_files(toolchain, lock["toolchain"]["files"])
        verify_files(libcxx, lock["libcxx"]["files"])

        def checked(name: str, command: list[str]) -> dict:
            record = run_logged(command, output / f"{name}.json")
            report["commands"].append({"log": f"{name}.json",
                                       "exit_code": record["exit_code"]})
            if record["exit_code"] != 0:
                raise RuntimeError(f"{name} failed; see {name}.json")
            return record

        compiler = str(toolchain / "bin/clang.exe")
        checked("compiler-version", [compiler, "--version"])
        common = [compiler, "-target", "pi32v2", "-mcpu=r3", "-Oz",
                  "-fno-common", "-D__GCC_PI32V2__", "-DFMER_DEVICE",
                  "-D_XOPEN_SOURCE=700", "-ffunction-sections", "-fdata-sections",
                  "-resource-dir", str(toolchain / "lib/clang/4.0.1")]
        cxx = ["-std=c++1z", "-fno-rtti", "-fno-threadsafe-statics",
               "-nostdinc++",
               "-D_LIBCPP_HAS_NO_THREADS", "-D_LIBCPP_HAS_NO_MONOTONIC_CLOCK",
               "-isystem", str(libcxx / "include")]
        includes = ["-isystem", str(toolchain / "pi32v2-include"),
                    "-I", str(ROOT / "core"), "-I", str(ROOT / "third_party/msfa/src")]
        sources = [ROOT / "firmware/probes/c_abi.c",
                   ROOT / "firmware/probes/language.cpp",
                   ROOT / "firmware/probes/standard_library.cpp"]
        sources += sorted((ROOT / "core").glob("*.cpp"))
        sources += sorted((ROOT / "third_party/msfa/src").glob("*.cc"))
        sources += [ROOT / "firmware/probes/shared_core.cpp",
                    ROOT / "firmware/probes/runtime.cpp"]
        link_objects = []
        for source in sources:
            relative = source.relative_to(ROOT).as_posix()
            name = relative.replace("/", "__")
            obj = output / (name + ".o")
            flags = ["-std=c11"] if source.suffix == ".c" else cxx + [
                "-fexceptions" if relative == "core/patch.cpp" else "-fno-exceptions"]
            checked(name, common + flags + includes + ["-c", str(source), "-o", str(obj)])
            identity = elf_identity(obj.read_bytes(), 1)
            report["objects"].append({"path": obj.name, "sha256": sha256(obj), **identity})
            report["sources"].append({"path": relative, "sha256": sha256(source)})
            if source.name not in {"c_abi.c", "language.cpp", "standard_library.cpp"}:
                link_objects.append(str(obj))
        elf = output / "shared_core.elf"
        checked("link", [str(toolchain / "bin/pi32v2-ld.exe"), "-m", "elf32pi32v2",
                "--gc-sections", "-T", str(ROOT / "firmware/probes/synthetic.ld"),
                "-Map", str(output / "shared_core.map"), "-o", str(elf)] + link_objects +
                ["-L", str(toolchain / "pi32v2-lib/r3"), "--start-group", "-lc", "-lm",
                 "-lcompiler-rt", "--end-group"])
        identity = elf_identity(elf.read_bytes(), 2)
        undefined = checked("undefined-symbols", [str(toolchain / "bin/llvm-nm.exe"),
                            "--undefined-only", str(elf)])
        if undefined["stdout"].strip():
            raise RuntimeError("Linked probe contains unresolved symbols")
        checked("elf-sections", [str(toolchain / "bin/llvm-readobj.exe"),
                                  "--file-headers", "--sections", str(elf)])
        report["linked_elf"] = {"path": elf.name, "sha256": sha256(elf), **identity}
        report["linker_script_sha256"] = sha256(ROOT / "firmware/probes/synthetic.ld")
        report["success"] = True
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        report["error"] = str(error)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain-root", type=Path)
    parser.add_argument("--libcxx-root", type=Path)
    parser.add_argument("--out", type=Path, help="New output directory; existing paths are refused")
    args = parser.parse_args(argv)
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    toolchain = (args.toolchain_root or ROOT / lock["toolchain"]["local_root"]).resolve()
    libcxx = (args.libcxx_root or ROOT / lock["libcxx"]["local_root"]).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    output = (args.out or ROOT / "artifacts/target-probe" / stamp).resolve()
    try:
        report = build_probe(toolchain, libcxx, output, lock)
    except OSError as error:
        print(f"Target probe refused output: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"success": report["success"], "report": str(output / "report.json"),
                      "error": report.get("error"), "flashable": False}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
