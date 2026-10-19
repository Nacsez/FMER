#!/usr/bin/env python3
"""Local FMER listening rig. Renders with the compiled C++ core; no device APIs."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ["FMER_DATA_DIR"]) / "logs/sandbox" if "FMER_DATA_DIR" in os.environ else ROOT / "artifacts/sandbox"
LIBRARY = Path(os.environ["FMER_DATA_DIR"]) / "legacy-library" if "FMER_DATA_DIR" in os.environ else ROOT / "local/library"
SCENARIOS = {"note", "chord", "sequence", "arp", "midi", "stress"}


def journal(event, *, output=None, **details):
    # A diagnostic disk failure must never turn an already committed Save into
    # a reported failure. The library's pre-commit audit remains mandatory.
    destination = OUTPUT if output is None else output
    try:
        destination.mkdir(parents=True, exist_ok=True)
        with (destination / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(library.canonical({"time": datetime.now(timezone.utc).isoformat(),
                         "event": event, "hardware_access": False, **details}).decode() + "\n")
        return True
    except OSError as exc:
        print(f"FMER diagnostic log unavailable ({event}): {exc}", file=sys.stderr)
        return False


def pattern_text(pattern):
    rows = [f"FMER_PATTERN_1 {pattern['length']} {pattern.get('channel', 0)} {len(pattern['steps'])}"]
    for step in pattern["steps"]:
        notes = step.get("notes", [])
        rows.append(" ".join(map(str, [step.get("gate", 75), int(step.get("tie", False)), len(notes),
                                      *[value for note in notes for value in (note["pitch"], note["velocity"])]])))
    return "\n".join(rows) + "\n"


def find_executable(config: str = "Debug") -> Path:
    if (ROOT / "bin/fmer_host.exe").is_file():return ROOT / "bin/fmer_host.exe"
    build = ROOT / "artifacts/build/host/host"
    for path in (build / config / "fmer_host.exe", build / "fmer_host", build / "fmer_host.exe"):
        if path.is_file():
            return path
    raise ValueError("Build the host first: python tools/dev.py build")


def bounded_int(value, lower, upper, name):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer {lower}..{upper}")
    return value


def render_request(data: dict, executable: Path, output: Path | None = None) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Request must be a JSON object")
    library.fields(data, {"scenario", "note", "velocity", "bpm", "duration", "voice", "engine", "wave",
                         "cutoff", "pattern", "effects", "arp", "tail", "edits", "sysex", "vced", "va", "budget", "lfo_enabled", "mono", "glide"}, "render")
    library.validate_settings({key: value for key, value in data.items() if key not in ("edits", "sysex", "vced")})
    scenario = data.get("scenario", "note")
    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    args = [str(executable), "--render", scenario]
    engine = data.get("engine", "fm")
    waveform = data.get("wave", "saw")
    if engine not in ("fm", "va") or waveform not in ("sine", "saw", "square", "triangle", "noise"):
        raise ValueError("Unsupported engine/waveform")
    cutoff = bounded_int(data.get("cutoff", 6000), 20, 18000, "cutoff")
    args += ["--engine", engine, "--wave", waveform, "--cutoff", str(cutoff)]
    for key,value in data.get("va",{}).items():args += ["--va", f"{key}={value}"]
    if "lfo_enabled" in data:args += ["--lfo-enabled",str(int(data["lfo_enabled"]))]
    if 'mono' in data:args += ['--mono',str(int(data['mono']))]
    for key,flag in (('mode','--glide-mode'),('time_ms','--glide-ms'),('curve','--glide-curve')):
        if key in data.get('glide',{}):args += [flag,str(data['glide'][key])]
    if "budget" in data:args += ["--budget",str(data["budget"])]
    args += ["--tail", str(bounded_int(data.get("tail", 1), 1, 10, "tail"))]
    for key, value in data.get("effects", {}).items():
        args += ["--fx-order", ",".join(value)] if key == "order" else ["--fx", f"{key}={value}"]
    for key, value in data.get("arp", {}).items():
        args += ["--arp-" + key.replace("_", "-"), str(int(value)) if type(value) is bool else str(value)]
    for field, low, high, default in (("note",0,127,60), ("velocity",1,127,100),
                                     ("bpm",20,300,120), ("duration",1,20,3)):
        value = bounded_int(data.get(field, default), low, high, field)
        args += ["--" + field, str(value)]
    edits = data.get("edits", {})
    if not isinstance(edits, dict) or len(edits) > 145:
        raise ValueError("edits must map at most 145 parameter IDs to values")
    for key, value in edits.items():
        if not isinstance(key, str) or not re.fullmatch(r"\d{1,3}", key):
            raise ValueError("Invalid parameter ID")
        bounded_int(int(key), 0, 144, "parameter ID")
        bounded_int(value, 0, 127, "parameter value")
        args += ["--set", f"{key}={value}"]
    patch = data.get("sysex")
    vced = data.get("vced")
    if vced is not None:
        library.validate_preset({"name": "Audition", "vced": vced, "settings": {}})
        if patch is not None:
            raise ValueError("Choose raw VCED or SysEx, not both")
    payload = None
    if patch is not None:
        if not isinstance(patch, str) or len(patch) > 5500:
            raise ValueError("SysEx must contain one single or 32-voice bank")
        try:
            payload = base64.b64decode(patch, validate=True)
        except ValueError as exc:
            raise ValueError("Malformed base64 patch") from exc
        if len(payload) not in (163, 4104):
            raise ValueError("Only standard 163/4104-byte DX7 messages are supported")
    voice = bounded_int(data.get("voice", 1), 1, 32, "voice")
    output = OUTPUT if output is None else output
    request_id = uuid.uuid4().hex
    directory = output / request_id
    directory.mkdir(parents=True)
    if vced is not None:
        # Store the native audition bytes before invoking the authoritative codec.
        (directory / "input.vced").write_bytes(bytes(vced))
        codec = library.PatchCodec(executable, lambda event, **details: journal(event, output=output, request_id=request_id, **details))
        payload = codec.encode([vced]); voice = 1
    if payload is not None:
        patch_file = directory / "input.syx"
        patch_file.write_bytes(payload)
        args += ["--patch", str(patch_file), "--voice", str(voice)]
    if "pattern" in data:
        pattern_file = directory / "pattern.txt"
        pattern_file.write_text(pattern_text(data["pattern"]), encoding="ascii")
        args += ["--pattern", str(pattern_file)]
    wav = directory / "render.wav"
    report = directory / "report.json"
    args += ["--out", str(wav), "--report", str(report)]
    started = time.monotonic()
    try:
        result = subprocess.run(args, creationflags=(subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0), capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        (directory / "process.json").write_text(json.dumps({
            "argv": args, "returncode": None, "stderr": str(exc), "stdout": "",
            "elapsed_seconds": time.monotonic() - started, "input": data,
            "hardware_access": False}, indent=2) + "\n", encoding="utf-8")
        raise
    (directory / "process.json").write_text(json.dumps({
        "argv": args, "returncode": result.returncode, "stdout": result.stdout,
        "stderr": result.stderr, "elapsed_seconds": time.monotonic() - started,
        "input": data, "hardware_access": False,
    }, indent=2) + "\n", encoding="utf-8")
    if result.returncode:
        raise ValueError(result.stderr.strip() or "C++ render failed; see process.json")
    measured = json.loads(report.read_text(encoding="utf-8"))
    measured.update(request_id=request_id, audio_url=f"/audio/{request_id}.wav",
                    wav_sha256=hashlib.sha256(wav.read_bytes()).hexdigest(), settings=data)
    (directory / "result.json").write_text(json.dumps(measured, indent=2) + "\n", encoding="utf-8")
    return measured


def handler_for(executable: Path, library_root: Path | None = None):
    presets = library.PatchLibrary(LIBRARY if library_root is None else library_root, executable)
    class Handler(BaseHTTPRequestHandler):
        # Single-threaded requests serialize MSFA renders and bound work in flight.
        def send(self, status, payload, mime="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                journal("client_disconnected", path=self.path, status=status)

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, fmt, *args):
            journal("http", method=self.command, path=self.path, message=(fmt % args)[:1000])

        def local_request(self):
            host = self.headers.get("Host", "")
            expected = f"127.0.0.1:{self.server.server_port}"
            return host == expected and self.headers.get("Origin", f"http://{expected}") == f"http://{expected}"

        def do_GET(self):
            if not self.local_request():
                self.send(403, b'{"error":"Use the printed loopback URL"}')
            elif self.path == "/":
                self.send(200, (ROOT / "host/sandbox.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/parameters":
                result = subprocess.run([str(executable), "--parameters"], creationflags=(subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0), capture_output=True, timeout=10)
                self.send(200 if result.returncode == 0 else 500, result.stdout)
            elif self.path == "/api/library":
                try:
                    self.send(200, library.canonical(presets.snapshot()))
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    journal("library_read_error", error=str(exc))
                    self.send(400, library.canonical({"error": str(exc)}))
            elif re.fullmatch(r"/audio/[0-9a-f]{32}\.wav", self.path):
                path = OUTPUT / self.path[7:-4] / "render.wav"
                self.send(200, path.read_bytes(), "audio/wav") if path.is_file() else self.send(404, b"{}")
            else:
                self.send(404, b'{"error":"Not found"}')

        def do_POST(self):
            if not self.local_request():
                self.send(403, b'{"error":"Cross-origin requests are disabled"}'); return
            if self.path not in ("/api/render", "/api/library", "/api/patch", "/api/telemetry"):
                self.send(404, b"{}"); return
            request_id = uuid.uuid4().hex
            started = time.monotonic()
            try:
                size = int(self.headers.get("Content-Length", "0"))
                maximum = 8 * 1024 * 1024 if self.path == "/api/library" else 65536
                if not 0 < size <= maximum:
                    raise ValueError("Invalid request length")
                request = library.strict_loads(self.rfile.read(size))
                if self.path == "/api/render":
                    result = render_request(request, executable)
                elif self.path == "/api/library":
                    result = presets.dispatch(request)
                elif self.path == "/api/patch":
                    library.fields(request, {"sysex"}, "patch")
                    decoded = presets.decode(request.get("sysex"))
                    result = {"voices": decoded["patches"], "count": decoded["count"]}
                else:
                    library.fields(request, {"event", "details", "session_id"}, "telemetry")
                    if not isinstance(request.get("event"), str) or len(request["event"]) > 80:
                        raise ValueError("Invalid telemetry event")
                    if not isinstance(request.get("details", {}), dict):
                        raise ValueError("Invalid telemetry details")
                    if not isinstance(request.get("session_id", ""), str) or len(request.get("session_id", "")) > 80:
                        raise ValueError("Invalid telemetry session")
                    if len(library.canonical(request)) > 8192:
                        raise ValueError("Telemetry exceeds bound")
                    journal("browser", client=request)
                    result = {"recorded": True}
                journal("request_complete", request_id=request_id, path=self.path,
                        render_id=result.get("request_id"), elapsed_seconds=time.monotonic() - started)
                self.send(200, library.canonical(result))
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                journal("request_refused", request_id=request_id, path=self.path, error=str(exc),
                        elapsed_seconds=time.monotonic() - started)
                self.send(409 if isinstance(exc, library.LibraryConflict) else 400,
                          library.canonical({"error": str(exc), "request_id": request_id}))

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", choices=("Debug", "Release"), default="Debug")
    parser.add_argument("--library", type=Path, default=LIBRARY, help="Persistent companion data directory")
    parser.add_argument("--render-demo", action="store_true", help="Render examples and an offline listening report, then exit")
    args = parser.parse_args()
    executable = find_executable(args.config)
    if args.render_demo:
        demos = [render_request({"scenario": scenario}, executable) for scenario in sorted(SCENARIOS)]
        demos.append(dict(render_request({"scenario":"note", "edits":{"100":75,"102":2}}, executable),
                          demo_label="Original modulated FM voice"))
        demos.extend(dict(render_request({"scenario":"chord","engine":"va","wave":waveform}, executable),
                          demo_label=f"VA {waveform} chord")
                     for waveform in ("sine","saw","square","triangle"))
        demos.append(dict(render_request({"scenario":"arp", "duration":4, "tail":3,
            "arp":{"order":"random","seed":42,"swing":65},
            "effects":{"delay":0.3,"delay_ms":333,"feedback":0.45}}, executable),
            demo_label="Seeded swinging arp with echoes"))
        demos.append(dict(render_request({"scenario":"arp", "duration":4, "tail":4,
            "engine":"va", "wave":"saw", "cutoff":2600,
            "arp":{"order":"repeat","octaves":1,"rate":8},
            "effects":{"chorus":0.25,"reverb":0.2}}, executable),
            demo_label="VA repeated chords with chorus and reverb"))
        demos.append(dict(render_request({"scenario":"sequence", "duration":4,
            "pattern":{"length":4,"channel":0,"steps":[
                {"notes":[{"pitch":60,"velocity":88},{"pitch":67,"velocity":75}],"gate":60},
                {"notes":[],"tie":True,"gate":90}, {"notes":[]},
                {"notes":[{"pitch":72,"velocity":100}],"gate":40}]}}, executable),
            demo_label="Edited chord, tie, rest and accent phrase"))
        rows = []
        for result in demos:
            label = result.get("demo_label", f'{result["engine"]} / {result["scenario"]}')
            rows.append(f'<section><h2>{label}</h2><audio controls src="{result["request_id"]}/render.wav"></audio>'
                        f'<p>SHA-256: {result["wav_sha256"]}</p><a href="{result["request_id"]}/result.json">Trace and metrics</a></section>')
        (OUTPUT / "index.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>FMER listening tests</title>'
            '<style>:root{color-scheme:dark}body{font:14px system-ui;max-width:900px;margin:40px auto;padding:0 14px;background:#070709;color:#f5f7fa}section{padding:20px;background:#101014;border:1px solid #727684;border-radius:3px;margin:16px 0}a{color:#76ff53}p{color:#b6bbc6;overflow-wrap:anywhere}audio{max-width:100%}:focus-visible{outline:2px solid #ff78d4;outline-offset:3px}</style>'
            '<h1>FMER listening tests</h1><p>Audio rendered by the shared C++ core. Host evidence; device fidelity is unmeasured.</p>'
            + ''.join(rows) + '</html>', encoding="utf-8")
        print(OUTPUT / "index.html")
        return 0
    server = HTTPServer(("127.0.0.1", args.port), handler_for(executable, args.library))
    journal("server_start", port=server.server_port, executable=str(executable), library=str(args.library.resolve()))
    print(f"FMER sandbox: http://127.0.0.1:{server.server_port}/\nShared C++ rendering; no hardware access. Ctrl+C stops the server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        journal("server_stop", port=args.port)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"Sandbox error: {exc}", file=sys.stderr)
        raise SystemExit(1)
