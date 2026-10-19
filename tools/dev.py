#!/usr/bin/env python3
"""Offline FMER workspace checks and host build; Python 3.10+, stdlib only.

All external commands use argument arrays, log both output streams and exit codes,
and run without writing Python bytecode into the preserved research corpus.
No command installs software, acquires network sources, or accesses a device.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback
import uuid


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "FM1_Research_Corpus_2026-09-29" / "FM1_Research_Corpus_2026-09-29"
ARTIFACTS = ROOT / "artifacts"
BUILD = ARTIFACTS / "build" / "host"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_identity(root: Path) -> dict:
    """Identify first-party inputs even before the workspace has its first commit."""
    paths = [root / name for name in ("CMakeLists.txt", "CMakePresets.json", ".editorconfig",
             ".gitattributes", ".gitignore", "evidence/corpus.lock.json", "evidence/msfa-source.json")]
    source_suffixes = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".cmake", ".py", ".json", ".html", ".htm", ".css", ".js"}
    for directory in ("core", "host", "tools", "tests", "ui", "hal", "third_party/msfa", "docs/help"):
        paths.extend(path for path in (root / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and (path.suffix in source_suffixes or path.name == "CMakeLists.txt"))
    hashes = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(set(paths)) if path.is_file()}
    git_identity = {"status": "not-a-git-worktree", "head": None}
    if (root / ".git").exists():
        git = shutil.which("git")
        git_identity["status"] = "git-unavailable"
        if git:
            # This exact workspace is owned by the user, while the agent may run
            # as a sandbox account. Scope trust to this query; change no config.
            command = [git, "-c", f"safe.directory={root.resolve().as_posix()}",
                       "rev-parse", "--verify", "HEAD"]
            git_identity["query"] = command
            try:
                result = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", check=False, timeout=10,
                                        env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
                git_identity.update(returncode=result.returncode, stderr=result.stderr.strip(),
                                    status="resolved" if result.returncode == 0 else "head-unresolved",
                                    head=result.stdout.strip() if result.returncode == 0 else None)
            except (OSError, subprocess.SubprocessError) as exc:
                git_identity.update(status="query-error", error=f"{type(exc).__name__}: {exc}")
    return {"git": git_identity, "sha256": hashes,
            "scope": "first-party source/config inputs and corpus lock, sampled at run start"}


class Run:
    """Persist failure evidence even if a tool is absent or exits unsuccessfully."""

    def __init__(self, command: str, artifacts: Path = ARTIFACTS):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.directory = artifacts / "runs" / f"{stamp}-{command}-{uuid.uuid4().hex[:8]}"
        self.directory.mkdir(parents=True)
        self.artifacts = artifacts
        self.summary = {
            "schema_version": 1,
            "command": command,
            "started_at": utc_now(),
            "workspace": str(ROOT),
            "platform": {"system": platform.system(), "release": platform.release(),
                         "version": platform.version(), "machine": platform.machine(),
                         "python": platform.python_version(), "python_executable": sys.executable},
            "source_identity": source_identity(ROOT),
            "scope": "offline-workspace-and-host-musical-prototype",
            "hardware_access": False,
            "network_access": False,
            "status": "running",
            "steps": [],
        }
        self.save()

    def save(self) -> None:
        (self.directory / "summary.json").write_text(
            json.dumps(self.summary, indent=2) + "\n", encoding="utf-8"
        )

    def record(self, name: str, okay: bool, details: str) -> None:
        self.summary["steps"].append({
            "name": name, "status": "passed" if okay else "failed", "details": details
        })
        print(f"[{'PASS' if okay else 'FAIL'}] {name}: {details}", flush=True)
        self.save()

    def skip(self, name: str, details: str) -> None:
        self.summary["steps"].append({"name": name, "status": "skipped", "details": details})
        print(f"[SKIP] {name}: {details}", flush=True)
        self.save()

    def execute(self, name: str, command: list[str], cwd: Path = ROOT,
                timeout: int = 600) -> subprocess.CompletedProcess:
        started = time.monotonic()
        log = self.directory / f"{len(self.summary['steps']) + 1:02d}-{name}.log"
        step = {"name": name, "argv": command, "cwd": str(cwd),
                "started_at": utc_now(), "log": str(log), "timeout_seconds": timeout,
                "environment_overrides": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}}
        print(f"[RUN] {name}\n      {json.dumps(command)}", flush=True)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        try:
            result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace",
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or b""
            errors = exc.stderr or b""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            if isinstance(errors, bytes):
                errors = errors.decode("utf-8", errors="replace")
            result = subprocess.CompletedProcess(command, 124, output,
                                                 errors + f"\nTimed out after {timeout}s: {exc}")
        except OSError as exc:
            result = subprocess.CompletedProcess(command, 127, "", f"{type(exc).__name__}: {exc}")
        step.update(returncode=result.returncode,
                    status="passed" if result.returncode == 0 else "failed",
                    elapsed_seconds=round(time.monotonic() - started, 3))
        log.write_text(json.dumps(step, indent=2) + "\n\n--- stdout ---\n" + result.stdout
                       + "\n--- stderr ---\n" + result.stderr, encoding="utf-8")
        self.summary["steps"].append(step)
        self.save()
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
        if result.stderr:
            print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", flush=True)
        print(f"[{'PASS' if result.returncode == 0 else 'FAIL'}] {name} "
              f"(exit {result.returncode}; {step['elapsed_seconds']}s)", flush=True)
        return result

    def finish(self) -> int:
        okay = bool(self.summary["steps"]) and all(
            step["status"] == "passed" for step in self.summary["steps"]
        )
        self.summary.update(status="passed" if okay else "failed", finished_at=utc_now())
        self.save()
        # Each immutable run is authoritative; latest.json is only a convenience pointer.
        (self.artifacts / "latest.json").write_text(json.dumps({
            "schema_version": 1, "status": self.summary["status"],
            "summary": str(self.directory / "summary.json")
        }, indent=2) + "\n", encoding="utf-8")
        print(f"Result: {self.summary['status'].upper()}\nSummary: {self.directory / 'summary.json'}")
        return 0 if okay else 1


def discover_tools(run: Run) -> dict:
    """Discover installed tools without changing PATH or configuring the machine."""
    cmake = shutil.which("cmake")
    compiler_candidates = [path for name in ("c++", "clang++", "g++", "cl")
                           if (path := shutil.which(name))]
    installations = []
    if os.name == "nt":
        vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / (
            "Microsoft Visual Studio/Installer/vswhere.exe")
        if vswhere.is_file():
            result = run.execute("vswhere", [str(vswhere), "-products", "*", "-requires",
                                 "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-format", "json"])
            if result.returncode == 0:
                try:
                    installations = [Path(item["installationPath"]) for item in json.loads(result.stdout)]
                except (ValueError, TypeError, KeyError) as exc:
                    run.record("vswhere-json", False, str(exc))
        for installation in installations:
            bundled = installation / "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
            if cmake is None and bundled.is_file():
                cmake = str(bundled)
            compiler_candidates.extend(str(path) for path in sorted(
                (installation / "VC/Tools/MSVC").glob("*/bin/Hostx64/x64/cl.exe"), reverse=True))
    ctest = None
    if cmake:
        sibling = Path(cmake).with_name("ctest.exe" if os.name == "nt" else "ctest")
        if sibling.is_file():
            ctest = str(sibling)
    ctest = ctest or shutil.which("ctest")
    info = {"python": sys.executable, "cmake": cmake, "ctest": ctest,
            "compiler_candidates": compiler_candidates,
            "visual_studio_installations": [str(path) for path in installations],
            "generator": os.environ.get("CMAKE_GENERATOR", "CMake default discovery")}
    run.summary["tools"] = info
    run.save()
    return info


def check(run: Run) -> None:
    verified = run.execute("workspace-contract", [sys.executable, "-B",
                           str(ROOT / "tools/verify_workspace.py")], cwd=ROOT)
    corpus_commands = [
        ("corpus-manifest", CORPUS, [sys.executable, "-B", "tools/check_manifest.py"]),
        ("corpus-tests", CORPUS, [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("acquisition-dry-run", CORPUS, [sys.executable, "-B", "tools/fetch_sources.py"]),
    ]
    for name, cwd, command in corpus_commands:
        if verified.returncode == 0:
            run.execute(name, command, cwd=cwd)
        else:
            run.skip(name, "Not executed: workspace integrity validation failed; corpus code is untrusted.")
    run.execute("workspace-tests", [sys.executable, "-B", "-m", "unittest", "discover",
                                   "-s", "tests", "-v"], cwd=ROOT)


def build(run: Run, tools: dict, config: str) -> bool:
    if not tools["cmake"]:
        run.record("cmake-available", False, "Install CMake >= 3.20 or use an installed Visual Studio CMake component.")
        return False
    configure = run.execute("cmake-configure", [tools["cmake"], "-S", str(ROOT), "-B", str(BUILD),
                           f"-DCMAKE_BUILD_TYPE={config}", "-DBUILD_TESTING=ON",
                           f"-DPython3_EXECUTABLE={sys.executable}"])
    if configure.returncode:
        return False
    return run.execute("cmake-build", [tools["cmake"], "--build", str(BUILD),
                       "--config", config, "--parallel"]).returncode == 0


def validate_host_diagnostics(data: object) -> None:
    if not isinstance(data, dict):
        raise ValueError("Diagnostic output must be a JSON object")
    expected = {"schema_version": 1, "project": "FMER", "component": "fmer_host",
                "implementation": "host-musical-prototype", "cpp_standard": 17,
                "hardware_access": False, "audio_engine": True}
    for name, value in expected.items():
        if type(data.get(name)) is not type(value) or data[name] != value:
            raise ValueError(f"Unexpected diagnostic field {name}: {data.get(name)!r}")
    for name in ("project_version", "build_id", "compiler_id", "compiler_version"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise ValueError(f"Missing build identity field: {name}")
    if not isinstance(data.get("build_configuration"), str):
        raise ValueError("Missing build configuration")
    if type(data.get("pointer_bits")) is not int or data["pointer_bits"] not in (32, 64):
        raise ValueError("Unsupported or missing pointer width")


def verify_host(executable: str) -> int:
    """CTest helper: validate real output and failure behavior of the built binary."""
    try:
        result = subprocess.run([executable, "--diagnostics"], capture_output=True,
                                text=True, timeout=5, check=True)
        validate_host_diagnostics(json.loads(result.stdout))
        if result.stderr:
            raise ValueError(f"Unexpected diagnostics on stderr: {result.stderr}")
        invalid = subprocess.run([executable, "--invalid-option"], capture_output=True,
                                 text=True, timeout=5, check=False)
        if invalid.returncode != 2 or invalid.stdout or "Usage:" not in invalid.stderr:
            raise ValueError("Invalid arguments must fail with exit 2 and usage on stderr")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Host diagnostic contract FAILED: {exc}", file=sys.stderr)
        return 1
    print(result.stdout, end="")
    print("Host diagnostic contract passed; hardware fidelity remains unmeasured.")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Preserve diagnostics even when the parent Windows terminal is CP1252.
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("doctor", "check", "build", "test", "verify-host"))
    parser.add_argument("executable", nargs="?", help="Internal CTest helper executable")
    parser.add_argument("--config", choices=("Debug", "Release", "RelWithDebInfo"), default="Debug")
    args = parser.parse_args(argv)
    if args.command == "verify-host":
        if not args.executable:
            parser.error("verify-host requires an executable")
        return verify_host(args.executable)
    if args.executable:
        parser.error("executable is only valid for verify-host")
    run = Run(args.command)
    try:
        run.record("python-version", sys.version_info >= (3, 10), sys.version.split()[0])
        if sys.version_info < (3, 10):
            return run.finish()
        if args.command in ("check", "test"):
            check(run)
        if args.command in ("doctor", "build", "test"):
            tools = discover_tools(run)
            if args.command == "doctor":
                for name in ("cmake", "ctest"):
                    if tools[name]:
                        run.execute(f"{name}-version", [tools[name], "--version"])
                    else:
                        run.record(f"{name}-available", False, "Tool was not found")
                run.record("compiler-discovery", bool(tools["compiler_candidates"]),
                           json.dumps(tools["compiler_candidates"]) + "; build verifies usability")
            elif build(run, tools, args.config) and args.command == "test":
                if tools["ctest"]:
                    run.execute("host-ctest", [tools["ctest"], "--test-dir", str(BUILD),
                                "--build-config", args.config, "--verbose", "--output-on-failure", "--no-tests=error"])
                else:
                    run.record("ctest-available", False, "CTest was not found")
    except Exception as exc:
        # Keep failures visible in the machine-readable summary as well as the terminal.
        run.record("driver-error", False, traceback.format_exc())
    return run.finish()


if __name__ == "__main__":
    raise SystemExit(main())
