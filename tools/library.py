"""Transactional, file-only FMER companion library; the C++ core owns DX7 validation.

This is host persistence, not the device's preset/flash format. No MIDI endpoint is
opened. Mutations require the revision last read by the caller; audition is read-only.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

CAPACITY = 128
MAX_SETTINGS_BYTES = 32768
MAX_FILE_BYTES = 10 * 1024 * 1024


class LibraryConflict(ValueError):
    """A stale browser must refresh before retrying a deliberate mutation."""


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def strict_loads(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Non-finite JSON number: {value}")

    try:
        return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)
    except (UnicodeError, RecursionError) as error:
        raise ValueError("Malformed or excessively nested JSON") from error


def integer(value, lower, upper, name):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer {lower}..{upper}")
    return value


def number(value, lower, upper, name):
    if (type(value) not in (int, float) or not lower <= value <= upper or
            (type(value) is float and not math.isfinite(value))):
        raise ValueError(f"{name} must be a finite number {lower}..{upper}")


def fields(value, allowed, name):
    if not isinstance(value, dict) or any(key not in allowed for key in value):
        raise ValueError(f"{name} must be an object with supported fields: {', '.join(sorted(allowed))}")


def choice(value, allowed, name):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"Unsupported {name}")


def boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f"{name} must be true or false")


def validate_settings(settings):
    fields(settings, {"scenario", "note", "velocity", "bpm", "duration", "voice", "engine", "wave",
                      "cutoff", "tail", "pattern", "effects", "arp", "va", "budget", "lfo_enabled", "mono", "glide"}, "settings")
    if "lfo_enabled" in settings:boolean(settings["lfo_enabled"],"lfo_enabled")
    if 'mono' in settings:boolean(settings['mono'],'mono')
    if 'glide' in settings:
        fields(settings['glide'],{'mode','time_ms','curve'},'glide')
        for key,maximum in (('mode',2),('time_ms',2000),('curve',2)):
            if key in settings['glide']:integer(settings['glide'][key],0,maximum,'glide '+key)
    if "budget" in settings:
        integer(settings["budget"],1,12,"budget")
    if "va" in settings:
        ranges={"resonance":(0,.95),"attack_ms":(0,10000),"decay_ms":(0,10000),
                "sustain":(0,1),"release_ms":(0,10000),"lfo_rate_hz":(.1,10),"lfo_depth_cents":(0,100)}
        fields(settings["va"],set(ranges),"va")
        for key,value in settings["va"].items():number(value,*ranges[key],key)
    for key, bounds in {"note": (0, 127), "velocity": (1, 127), "bpm": (20, 300),
                        "duration": (1, 20), "voice": (1, 32), "cutoff": (20, 18000), "tail": (1, 10)}.items():
        if key in settings:
            integer(settings[key], *bounds, key)
    for key, options in {"scenario": {"note", "chord", "sequence", "arp", "midi", "stress"},
                         "engine": {"fm", "va"}, "wave": {"sine", "saw", "square", "triangle", "noise"}}.items():
        if key in settings:
            choice(settings[key], options, key)
    if "arp" in settings:
        arp = settings["arp"]
        fields(arp, {"order", "octaves", "gate", "latch", "rate", "triplet", "swing", "seed", "held_release"}, "arp")
        if "order" in arp:
            choice(arp["order"], {"up", "down", "inclusive", "exclusive", "random", "played", "repeat", "up_down", "down_exclusive", "down_inclusive", "outside_in", "strum"}, "arp order")
        for key, bounds in {"octaves": (1, 4), "gate": (0, 100), "swing": (50, 75), "seed": (1, 2147483647)}.items():
            if key in arp:
                integer(arp[key], *bounds, "arp " + key)
        for key in ("latch", "triplet", "held_release"):
            if key in arp:
                boolean(arp[key], "arp " + key)
        if "rate" in arp and (type(arp["rate"]) is not int or arp["rate"] not in (1, 2, 4, 8, 16, 32)):
            raise ValueError("arp rate must be 1, 2, 4, 8, 16 or 32")
    if "pattern" in settings:
        pattern = settings["pattern"]
        fields(pattern, {"length", "channel", "steps"}, "pattern")
        length = integer(pattern.get("length"), 1, 64, "pattern length")
        integer(pattern.get("channel", 0), 0, 15, "pattern channel")
        steps = pattern.get("steps")
        if not isinstance(steps, list) or not length <= len(steps) <= 64:
            raise ValueError("pattern must retain between active length and 64 steps")
        for step in steps:
            fields(step, {"notes", "gate", "tie"}, "step")
            integer(step.get("gate", 75), 1, 100, "step gate")
            boolean(step.get("tie", False), "step tie")
            notes = step.get("notes", [])
            if not isinstance(notes, list) or len(notes) > 9:
                raise ValueError("A step contains at most nine notes")
            if step.get("tie", False) and notes:
                raise ValueError("A tie continues the previous step and cannot contain new notes")
            pitches = []
            for note in notes:
                fields(note, {"pitch", "velocity"}, "step note")
                pitches.append(integer(note.get("pitch"), 0, 127, "step pitch"))
                integer(note.get("velocity"), 1, 127, "step velocity")
            if len(set(pitches)) != len(pitches):
                raise ValueError("A chord cannot contain duplicate pitches")
    if "effects" in settings:
        effects = settings["effects"]
        ranges = {"cutoff_hz": (20, 20000),
                  "drive": (0, 1), "chorus": (0, 1), "phaser": (0, 1),
                  "delay": (0, 1), "delay_ms": (20, 1000), "feedback": (0, 0.85),
                  "reverb": (0, 1), "chorus_rate_hz": (0.1, 1), "chorus_depth": (0, 1),
                  "phaser_rate_hz": (0.5, 6), "phaser_depth": (0, 1), "reverb_decay": (0, 1)}
        fields(effects, set(ranges) | {"order","filter_mode","reverb_model","delay_model","resonance"}, "effects")
        for key,hi in (("filter_mode",2),("reverb_model",3),("delay_model",1)):
            if key in effects:integer(effects[key],0,hi,key)
        if "resonance" in effects:number(effects["resonance"],0,1,"resonance")
        for key, bounds in ranges.items():
            if key in effects:
                number(effects[key], *bounds, key)
        if "order" in effects:
            order = effects["order"]
            expected = {"filter", "reverb", "delay", "drive", "chorus", "phaser"}
            if not isinstance(order, list) or len(order) != 6 or any(not isinstance(x, str) for x in order) or set(order) != expected:
                raise ValueError("effects order must contain each of the six stages exactly once")
    try:
        encoded = canonical(settings)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError("settings must be bounded JSON") from error
    if len(encoded) > MAX_SETTINGS_BYTES:
        raise ValueError("settings exceed 32 KiB; no data was saved")


def validate_preset(preset):
    fields(preset, {"name", "vced", "settings"}, "preset")
    name = preset.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError("Preset name must contain 1..80 printable characters")
    vced = preset.get("vced")
    if not isinstance(vced, list) or len(vced) != 155 or any(type(v) is not int or not 0 <= v <= 127 for v in vced):
        raise ValueError("Preset vced must contain exactly 155 seven-bit integer bytes")
    validate_settings(preset.get("settings", {}))


class PatchCodec:
    """All voice-field/framing validation remains in the compiled C++ codec."""
    def __init__(self, executable: Path, log):
        self.executable = Path(executable)
        self.log = log

    def _run(self, operation, payload):
        with tempfile.TemporaryDirectory(prefix="fmer-codec-") as directory:
            source = Path(directory) / "input.bin"
            target = Path(directory) / "output.syx"
            source.write_bytes(payload)
            args = [str(self.executable), "--patch-tool", operation, "--in", str(source)]
            if operation.startswith("encode-"):
                args += ["--out", str(target)]
            started = time.monotonic()
            try:
                result = subprocess.run(args, creationflags=(subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0), capture_output=True, text=True, timeout=20, check=False)
                self.log("codec", operation=operation, input_sha256=hashlib.sha256(payload).hexdigest(),
                         argv=args, returncode=result.returncode, stderr=result.stderr,
                         elapsed_seconds=time.monotonic() - started)
            except (OSError, subprocess.SubprocessError) as error:
                self.log("codec_error", operation=operation, error=str(error))
                raise ValueError("Cannot run shared patch codec: " + str(error)) from error
            if result.returncode:
                raise ValueError(result.stderr.strip() or "Shared patch codec refused the input")
            report = strict_loads(result.stdout)
            return report, target.read_bytes() if target.is_file() else None

    def validate(self, voices):
        if voices:
            for offset in range(0, len(voices), CAPACITY):
                self._run("validate", bytes(value for voice in voices[offset:offset + CAPACITY] for value in voice))

    def decode(self, payload):
        return self._run("decode", payload)[0]["patches"]

    def encode(self, voices):
        if len(voices) not in (1, 32):
            raise ValueError("DX7 export requires exactly one or 32 voices")
        return self._run("encode-single" if len(voices) == 1 else "encode-bank",
                         bytes(value for voice in voices for value in voice))[1]


class PatchLibrary:
    def __init__(self, root: Path, executable: Path, *, codec=None):
        self.root = Path(root)
        self.path = self.root / "library.json"
        self.previous_path = self.root / "library.previous.json"
        self.codec = codec if codec is not None else PatchCodec(executable, self._log)

    def _log(self, event, **details):
        self.root.mkdir(parents=True, exist_ok=True)
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": event,
                  "hardware_access": False, **details}
        with (self.root / "library.log.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(canonical(record).decode("utf-8") + "\n")

    @contextmanager
    def _lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / "library.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise LibraryConflict("Library is locked by another operation; retry after it finishes. A crash lock requires explicit recovery.") from error
        ownership = canonical({"pid": os.getpid(), "time": datetime.now(timezone.utc).isoformat(),
                               "token": uuid.uuid4().hex})
        cleanup_warnings = []
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(ownership)
                stream.flush()
                os.fsync(stream.fileno())
            yield cleanup_warnings
        finally:
            try:
                # Another process or explicit recovery may have replaced the
                # pathname. Never remove a lock whose owner token changed.
                if lock.read_bytes() != ownership:
                    raise OSError("lock ownership changed; foreign lock was preserved")
                lock.unlink()
            except OSError as error:
                warning = f"library lock cleanup failed ({error}); inspect the lock and stop its owner before explicit recovery"
                cleanup_warnings.append(warning)
                try:
                    self._log("lock_cleanup_failed", error=str(error), lock=str(lock))
                except OSError:
                    pass
                # Preserve a pre-commit exception if one is already propagating.
                # On success, _mutate adds this warning to the committed result.

    @staticmethod
    def _empty():
        return {"format": "FMER-LIBRARY", "version": 1, "capacity": CAPACITY,
                "revision": 0, "slots": [None] * CAPACITY, "undo_slots": None}

    @staticmethod
    def _envelope(state):
        return {"format": "FMER-LIBRARY-FILE", "version": 1,
                "sha256": hashlib.sha256(canonical(state)).hexdigest(), "payload": state}

    def _validate_state(self, state):
        fields(state, {"format", "version", "capacity", "revision", "slots", "undo_slots"}, "library payload")
        if set(state) != {"format", "version", "capacity", "revision", "slots", "undo_slots"}:
            raise ValueError("Library payload is missing required fields")
        if state.get("format") != "FMER-LIBRARY" or type(state.get("version")) is not int or state["version"] != 1 or state.get("capacity") != CAPACITY:
            raise ValueError("Unsupported library format/version/capacity; original data preserved")
        integer(state.get("revision"), 0, 2**53 - 1, "revision")
        voices = []
        for name in ("slots", "undo_slots"):
            slots = state.get(name)
            if name == "undo_slots" and slots is None:
                continue
            if not isinstance(slots, list) or len(slots) != CAPACITY:
                raise ValueError(f"{name} must contain exactly 128 slots")
            for preset in slots:
                if preset is not None:
                    validate_preset(preset)
                    voices.append(preset["vced"])
        self.codec.validate(voices)

    def _unpack(self, envelope):
        fields(envelope, {"format", "version", "sha256", "payload"}, "backup")
        if envelope.get("format") != "FMER-LIBRARY-FILE" or type(envelope.get("version")) is not int or envelope["version"] != 1:
            raise ValueError("Unsupported backup format/version")
        state = envelope.get("payload")
        try:
            encoded = canonical(state)
        except (TypeError, RecursionError, ValueError) as error:
            raise ValueError("Malformed backup payload") from error
        if len(encoded) > MAX_FILE_BYTES:
            raise ValueError("Library exceeds the host record limit")
        if hashlib.sha256(encoded).hexdigest() != envelope.get("sha256"):
            raise ValueError("Library checksum mismatch; original data preserved")
        self._validate_state(state)
        return state

    def _read(self):
        if not self.path.exists():
            if self.previous_path.exists():
                raise ValueError("Primary library is missing but its previous backup exists; recovery must be explicit")
            return self._empty()
        if self.path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Library record exceeds 10 MiB; original data preserved")
        return self._unpack(strict_loads(self.path.read_bytes()))

    @staticmethod
    def _snapshot(state):
        # A JSON copy prevents callers from mutating library state by reference.
        return strict_loads(canonical({key: state[key] for key in ("format", "version", "capacity", "revision", "slots")} |
                                     {"can_undo": state["undo_slots"] is not None}))

    def snapshot(self):
        return self._snapshot(self._read())

    def _atomic(self, destination, payload):
        staged = self.root / ("." + destination.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with staged.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, destination)
            # Windows does not expose portable directory fsync. POSIX hosts do.
            if os.name != "nt":
                descriptor = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            if staged.exists():
                staged.unlink()

    def _mutate(self, revision, action, change):
        integer(revision, 0, 2**53 - 2, "revision")
        with self._lock() as cleanup_warnings:
            state = self._read()
            if revision != state["revision"]:
                self._log("conflict", action=action, supplied_revision=revision, current_revision=state["revision"])
                raise LibraryConflict(f"Library changed: expected revision {revision}, current revision {state['revision']}; refresh before saving")
            old_slots = state["slots"]
            new_slots = change(state)
            candidate = {**state, "revision": revision + 1, "slots": new_slots,
                         "undo_slots": None if action == "undo" else old_slots}
            self._validate_state(candidate)
            payload = canonical(self._envelope(candidate)) + b"\n"
            if len(payload) > MAX_FILE_BYTES:
                raise ValueError("Library exceeds 10 MiB; no data was saved")
            self._log("transaction_prepared", action=action, revision=revision,
                      next_revision=revision + 1, sha256=hashlib.sha256(payload).hexdigest())
            if self.path.exists():
                self._atomic(self.previous_path, self.path.read_bytes())
            self._atomic(self.path, payload)
            result = self._snapshot(candidate)
            try:
                self._log("transaction_committed", action=action, revision=revision + 1,
                          occupied=sum(p is not None for p in new_slots))
            except OSError as error:
                # A failed final diagnostic must not report a committed save as
                # refused and invite a duplicate retry at the old revision.
                result["warnings"] = [f"Library saved at revision {revision + 1}; final diagnostic append failed: {error}"]
        if cleanup_warnings:
            result.setdefault("warnings", []).extend(
                f"Library saved at revision {result['revision']}; {warning}" for warning in cleanup_warnings)
        return result

    def save(self, slot, preset, revision):
        integer(slot, 0, CAPACITY - 1, "slot")
        validate_preset(preset)
        stored = strict_loads(canonical({"name": preset["name"], "vced": preset["vced"], "settings": preset.get("settings", {})}))
        return self._mutate(revision, "save", lambda state: state["slots"][:slot] + [stored] + state["slots"][slot + 1:])

    def load(self, slot):
        integer(slot, 0, CAPACITY - 1, "slot")
        state = self._read()
        if state["slots"][slot] is None:
            raise ValueError("Selected slot is empty")
        return {"preset": state["slots"][slot], "revision": state["revision"]}

    def delete(self, slot, revision):
        integer(slot, 0, CAPACITY - 1, "slot")
        def remove(state):
            if state["slots"][slot] is None:
                raise ValueError("Selected slot is already empty")
            return state["slots"][:slot] + [None] + state["slots"][slot + 1:]
        return self._mutate(revision, "delete", remove)

    def undo(self, revision):
        def previous(state):
            if state["undo_slots"] is None:
                raise ValueError("No library change to undo")
            return state["undo_slots"]
        return self._mutate(revision, "undo", previous)

    def backup(self):
        state = self._read()
        return {"backup": self._envelope({**state, "undo_slots": None}), "revision": state["revision"]}

    def restore(self, backup, revision):
        restored = self._unpack(backup)
        return self._mutate(revision, "restore", lambda state: restored["slots"])

    @staticmethod
    def _sysex(encoded):
        if not isinstance(encoded, str) or len(encoded) > 5500:
            raise ValueError("SysEx must be one base64 DX7 single or bank")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise ValueError("Malformed base64 SysEx") from error
        if len(payload) not in (163, 4104):
            raise ValueError("SysEx must contain 163 or 4104 bytes")
        return payload

    def decode(self, sysex):
        patches = self.codec.decode(self._sysex(sysex))
        return {"patches": patches, "count": len(patches), "hardware_access": False}

    def import_bank(self, sysex, start_slot, revision, overwrite=False):
        integer(start_slot, 0, CAPACITY - 1, "start_slot")
        boolean(overwrite, "overwrite")
        patches = self.decode(sysex)["patches"]
        if start_slot + len(patches) > CAPACITY:
            raise ValueError("Import exceeds the 128-slot library; no data was saved")
        imported = [{"name": "".join(c if 32 <= ord(c) < 127 else " " for c in patch["name"]).strip() or f"Imported {index + 1}",
                     "vced": patch["vced"], "settings": {"engine": "fm"}}
                    for index, patch in enumerate(patches)]
        def insert(state):
            if not overwrite and any(p is not None for p in state["slots"][start_slot:start_slot + len(imported)]):
                raise LibraryConflict("Import would replace occupied slots; select empty destinations or explicitly allow overwrite")
            return state["slots"][:start_slot] + imported + state["slots"][start_slot + len(imported):]
        return self._mutate(revision, "import_bank", insert)

    def export(self, slot=None, start_slot=None, count=None):
        if slot is not None:
            if start_slot is not None or count is not None:
                raise ValueError("Choose a single slot or a 32-slot bank")
            start_slot = integer(slot, 0, CAPACITY - 1, "slot")
            count = 1
        else:
            integer(start_slot, 0, CAPACITY - 32, "start_slot")
            if type(count) is not int or count != 32:
                raise ValueError("Bank export requires exactly 32 occupied slots")
        state = self._read()
        presets = state["slots"][start_slot:start_slot + count]
        if any(p is None for p in presets):
            raise ValueError("DX7 export requires every selected slot to be occupied; empty slots are never silently filled")
        payload = self.codec.encode([p["vced"] for p in presets])
        return {"sysex": base64.b64encode(payload).decode("ascii"),
                "filename": f"fmer-{'voice' if count == 1 else 'bank'}-{start_slot + 1:03d}.syx",
                "revision": state["revision"], "losses": [
                    "Standard DX7 stores only the 155-byte FM voice, including its original 10-byte name.",
                    "Native library names, VA settings, effects, patterns, arp and lab settings are omitted; use native backup to preserve them."],
                "hardware_access": False}

    def export_voice(self, vced):
        validate_preset({"name": "Working voice", "vced": vced, "settings": {}})
        payload = self.codec.encode([vced])
        return {"sysex": base64.b64encode(payload).decode("ascii"), "filename": "fmer-working-voice.syx",
                "losses": ["Standard DX7 retains only the FM voice; VA, effects, patterns, arp and native names require a native session or library backup."],
                "hardware_access": False}

    def dispatch(self, request):
        if not isinstance(request, dict):
            raise ValueError("Library request must be an object")
        action = request.get("action")
        specs = {"save": {"revision", "slot", "preset"}, "load": {"slot"},
                 "delete": {"revision", "slot"}, "undo": {"revision"}, "backup": set(),
                 "restore": {"revision", "backup"}, "import_bank": {"revision", "start_slot", "sysex", "overwrite"},
                 "export": {"slot", "start_slot", "count"}, "export_voice": {"vced"}, "decode": {"sysex"}}
        if not isinstance(action, str) or action not in specs:
            raise ValueError("Unknown library action")
        fields(request, specs[action] | {"action"}, "library request")
        args = {key: value for key, value in request.items() if key != "action"}
        required = specs[action] - ({"overwrite"} if action == "import_bank" else set())
        if action != "export" and not required <= args.keys():
            raise ValueError("Missing library request fields")
        try:
            return getattr(self, action)(**args)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            self._log("request_refused", action=action, error=str(error))
            raise
