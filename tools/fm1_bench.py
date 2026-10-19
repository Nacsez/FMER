#!/usr/bin/env python3
"""Explicit normal-FMER diagnostics / low-velocity MIDI smoke; never updates flash.

Requires the explicitly selected checksum-valid FMER identity before the read. The optional
note smoke uses channel 16, note 60, velocity 32 and always attempts note-off.
Counters are target evidence, not an audio recording or proof of audible output.
"""
from __future__ import annotations
import argparse
import ctypes as ct
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid
import hardware_bridge as bridge
import fm1_flash_transport as transport

QUERY = bytes.fromhex("F0 7D 46 4D 45 52 01 F7")
FIELDS = ("audio_halves", "maximum_render_us", "overruns", "midi_overflows",
          "rejected_messages", "active_voices", "startup_heap_bytes", "flash_jedec",
          "audio_paused", "dsp_init_failed", "retained_crash_count")
EXTRA_FIELDS = ("engine", "algorithm", "va_wave", "cutoff_hz", "delay_percent",
                "attack_ms", "release_ms", "gain_q10", "octave_plus3", "voice_limit",
                "stolen_voices", "load_sheds", "maximum_event_us", "maximum_dsp_us",
                "last_render_us", "lcd_strips", "maximum_lcd_us", "lcd_timeouts",
                "controls_generation", "controls_applied", "maximum_render_voices",
                "maximum_render_engine", "last_event_us", "last_dsp_us",
                "minimum_half_period_us", "maximum_half_period_us")


def parse_diagnostics(frame: bytes, *, identity=None) -> dict:
    if not isinstance(frame, bytes) or not 8 <= len(frame) <= 512 or frame[:6] != QUERY[:6] or frame[6] not in (1,2) or frame[-1] != 0xF7:
        raise ValueError("Invalid FMER normal-application diagnostic frame")
    text = frame[7:-1].decode("ascii", errors="strict")
    words = text.split(" ")
    fields = FIELDS + (EXTRA_FIELDS if frame[6] == 2 else ())
    if len(words) != len(fields) or any(not w or not w.isascii() or not w.isdecimal() for w in words):
        raise ValueError("Invalid diagnostic field count or unsigned decimal value")
    numbers = [int(w) for w in words]
    if any(n > 0xFFFFFFFF for n in numbers) or numbers[8] > 1 or numbers[9] > 1 or numbers[5] > 12:
        raise ValueError("Diagnostic value exceeds its contract")
    result = dict(zip(fields, numbers))
    if frame[6] == 2:
        for key,low,high in (("engine",0,1),("algorithm",0,31),("va_wave",0,4 if identity in ("FM-1_726","FM-1_727","FM-1_728","FM-1_729","FM-1_730","FM-1_731","FM-1_732","FM-1_733","FM-1_734") else 3),
                             ("cutoff_hz",20,20000),("delay_percent",0,100),
                             ("attack_ms",0,10000),("release_ms",0,10000),
                             ("gain_q10",0,1024),("octave_plus3",0,6),("voice_limit",1,12),
                             ("maximum_render_engine",0,1),("maximum_render_voices",0,12)):
            if not low <= result[key] <= high: raise ValueError("Invalid extended field: " + key)
    return result


def query(session, journal, version=1) -> dict:
    if version not in (1,2): raise ValueError("Unsupported diagnostic schema")
    session._send(QUERY[:6]+bytes([version,0xF7]), "fmer_read_only_diagnostics")
    frame = session.read(2.0)
    if frame is None: raise TimeoutError("FMER diagnostic response timed out after 2 seconds")
    if len(frame)<7 or frame[6]!=version: raise ValueError("Diagnostic schema did not match request")
    result = parse_diagnostics(frame,identity=getattr(session,"verified_identity",None))
    journal.record("normal_diagnostics", **result)
    return result


def set_controls(session, journal, engine, wave=1, cutoff_step=18, delay=0,
                 attack_step=2, release_step=7, budget=4):
    values=(engine,wave,cutoff_step,delay,attack_step,release_step,budget)
    for value,(lo,hi) in zip(values,((0,1),(0,3),(0,18),(0,100),(0,12),(0,12),(1,12))):
        if type(value) is not int or not lo<=value<=hi: raise ValueError("Invalid RAM control value")
    wire=QUERY[:6]+bytes([3,*values,0xF7])
    session._send(wire,"fmer_volatile_controls")
    if session.read(2.0)!=wire: raise RuntimeError("RAM control echo did not match")
    deadline=time.monotonic()+1
    while time.monotonic()<deadline:
        time.sleep(.02)
        state=query(session,journal,2)
        if state["controls_applied"]==state["controls_generation"]:
            if state["engine"]!=engine or state["va_wave"]!=wave or state["voice_limit"]!=budget:
                raise RuntimeError("Applied controls/budget differ from request")
            return state
    raise RuntimeError("Audio owner did not adopt controls")


def reset_peaks(session):
    wire=QUERY[:6]+bytes([4,0xF7])
    session._send(wire,"fmer_reset_profiling_peaks")
    if session.read(2.0)!=wire: raise RuntimeError("Profiling reset echo did not match")


def cleanup_notes(session,journal,notes):
    errors=[]
    for message in [(0x8F,note,0) for note in notes]+[(0xBF,120,0)]:
        try: short_message(session,journal,*message)
        except Exception as error: errors.append(str(error))
    if errors: raise RuntimeError("Note cleanup failed: "+"; ".join(errors))


def run_matrix(session,journal,result):
    notes=(60,64,67,71,74,77,81,84)
    result["matrix"]=[]
    scenarios=[("FM dry",0,1,18,0)]+[("VA wave "+str(w),1,w,18,0) for w in range(4)]
    scenarios += [("FM filter+delay",0,1,12,30),("VA filter+delay",1,1,12,30)]
    try:
        for label,engine,wave,cutoff,delay in scenarios:
            baseline=set_controls(session,journal,engine,wave,cutoff,delay)
            for count in (1,2,3,4,8):
                reset_peaks(session)
                step={"scenario":label,"requested_notes":count,"budget":4}
                result["matrix"].append(step)
                try:
                    for note in notes[:count]: short_message(session,journal,0x9F,note,32)
                    time.sleep(.5)
                    step["during"]=during=query(session,journal,2)
                    if during["active_voices"]!=min(count,4): raise RuntimeError("Chord admission mismatch: "+label)
                    if during["audio_halves"]==baseline["audio_halves"] or during["audio_paused"]:
                        raise RuntimeError("Audio failed to progress: "+label)
                    for key in ("overruns","midi_overflows","rejected_messages","retained_crash_count","load_sheds","lcd_timeouts"):
                        if during[key]!=baseline[key]: raise RuntimeError("Counter advanced in "+label+": "+key)
                finally: cleanup_notes(session,journal,notes[:count])
                time.sleep(.1)
                step["after"]=after=query(session,journal,2)
                if after["active_voices"] or after["audio_paused"]: raise RuntimeError("Chord cleanup failed")
    finally:
        import sys
        pending=sys.exc_info()[0] is not None
        errors=[]
        try: cleanup_notes(session,journal,notes)
        except Exception as error: errors.append(str(error))
        try: set_controls(session,journal,0)
        except Exception as error: errors.append(str(error))
        if errors:
            result["matrix_cleanup_errors"]=errors
            if not pending: raise RuntimeError("Matrix cleanup failed: "+"; ".join(errors))


def run_releases(session,journal,result):
    result["release_checks"]=[]
    baseline=set_controls(session,journal,1,release_step=5) # 50ms release
    try:
        for label,message in (("Note Off",(0x8F,60,0)),("Note On velocity zero",(0x9F,60,0)),
                              ("All Notes Off",(0xBF,123,0)),("All Sound Off",(0xBF,120,0))):
            short_message(session,journal,0x9F,60,32)
            time.sleep(.1)
            during=query(session,journal,2)
            if during["active_voices"]!=1: raise RuntimeError("Release check did not start one voice")
            short_message(session,journal,*message)
            time.sleep(.2)
            after=query(session,journal,2)
            result["release_checks"].append({"command":label,"during":during,"after":after})
            if after["active_voices"] or after["audio_paused"]: raise RuntimeError(label+" did not release the note")
            for key in ("overruns","midi_overflows","rejected_messages","load_sheds"):
                if after[key]!=baseline[key]: raise RuntimeError("Release check changed "+key)
        short_message(session,journal,0xBF,64,127)
        short_message(session,journal,0x9F,60,32)
        time.sleep(.1)
        short_message(session,journal,0xBF,123,0)
        time.sleep(.2)
        held=query(session,journal,2)
        if held["active_voices"]!=1: raise RuntimeError("All Notes Off did not respect sustain")
        short_message(session,journal,0xBF,64,0)
        time.sleep(.2)
        released=query(session,journal,2)
        result["sustain_check"]={"held":held,"released":released}
        if released["active_voices"]: raise RuntimeError("Pedal-up did not release sustained note")
    finally:
        import sys
        pending=sys.exc_info()[0] is not None
        errors=[]
        for action in (lambda:short_message(session,journal,0xBF,64,0),
                       lambda:cleanup_notes(session,journal,(60,)),
                       lambda:set_controls(session,journal,0)):
            try: action()
            except Exception as error: errors.append(str(error))
        if errors:
            result["release_cleanup_errors"]=errors
            if not pending: raise RuntimeError("Release cleanup failed: "+"; ".join(errors))


def short_message(session, journal, status: int, data1: int, data2: int):
    # Internal smoke messages only; no arbitrary message CLI is exposed.
    notes = (60, 64, 67, 71, 74, 77, 81, 84)
    allowed = (status == 0x9F and data1 in notes and data2 in (0,32)) or \
              (status == 0x8F and data1 in notes and data2 == 0) or \
              (status == 0xBF and data1 in (120,123) and data2 == 0) or \
              (status == 0xBF and data1 == 64 and data2 in (0,127))
    if not allowed:
        raise ValueError("Not a permitted bench smoke message")
    logging_error=None
    try:
        journal.record("short_message_intent", status=status, data1=data1, data2=data2)
    except Exception as error:
        if (status==0x9F and data2) or (status==0xBF and data1==64 and data2): raise
        logging_error=error    # note cleanup still runs if the log disk fails
    function = session.api.dll.midiOutShortMsg
    function.argtypes, function.restype = [bridge.HANDLE, bridge.DWORD], bridge.UINT
    session.api.checked("midiOutShortMsg", session.output, status | data1 << 8 | data2 << 16)
    if logging_error is not None:
        raise RuntimeError("Note cleanup sent but logging failed: "+str(logging_error))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("diagnostics", "note-smoke", "voice-ladder", "matrix", "release-checks"))
    parser.add_argument("--firmware", choices=("701", "702", "703", "704", "705", "706", "707"), default="706")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")+"-"+uuid.uuid4().hex[:8]
    journal = transport.Journal(transport.ROOT / "artifacts/fm1-bench" / stamp)
    result = {"success": False, "action": args.action, "unit": "FMER Test01",
              "flash_writes": False, "audio_recorded": False,
              "expected_firmware": args.firmware,
              "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    session = None
    try:
        journal.record("bench_start", **result)
        session = transport.find_session(bridge.WinMM(), "FM-1_" + args.firmware, journal, wait=2.0)
        version=1 if args.firmware=="701" else 2
        result["before"] = before = query(session,journal,version)
        if args.action == "note-smoke":
            if before["audio_paused"] or before["dsp_init_failed"] or before["active_voices"]:
                raise RuntimeError("DSP is unavailable or notes are already active; note smoke refused")
            try:
                short_message(session,journal,0x9F,60,32)
                time.sleep(.25)
                result["during"] = during = query(session,journal,version)
                time.sleep(.75)
            finally:
                # Both attempts are made even if one transport operation fails.
                errors=[]
                for message in ((0x8F,60,0),(0xBF,120,0)):
                    try: short_message(session,journal,*message)
                    except Exception as error: errors.append(str(error))
                if errors: raise RuntimeError("Note cleanup failed: "+"; ".join(errors))
            time.sleep(.15)
            result["after"] = after = query(session,journal,version)
            if during["active_voices"] != 1 or after["active_voices"] != 0:
                raise RuntimeError("Note lifecycle counter check failed")
            if after["audio_halves"] == before["audio_halves"] or after["overruns"] != before["overruns"] or after["audio_paused"]:
                raise RuntimeError("Audio did not progress without overload")
            if any(after[key]!=before[key] for key in ("midi_overflows","rejected_messages")):
                raise RuntimeError("MIDI messages were dropped or rejected during smoke")
        if args.action == "voice-ladder":
            if before["audio_paused"] or before["dsp_init_failed"] or before["active_voices"]:
                raise RuntimeError("DSP is unavailable or notes are already active; voice ladder refused")
            result["engine_scope"] = "Current panel engine; legacy diagnostics do not expose engine"
            result["ladder"] = []
            notes = (60,64,67,71,74,77,81,84)
            for count in (1,2,3,4,6,8):
                step = {"requested_voices": count}
                result["ladder"].append(step)
                try:
                    for note in notes[:count]: short_message(session,journal,0x9F,note,32)
                    time.sleep(.35)
                    step["during"] = during = query(session,journal)
                    if during["audio_paused"] or during["overruns"] != before["overruns"]:
                        raise RuntimeError("Voice ladder reached an audio overrun at " + str(count) + " requested notes")
                    if during["audio_halves"] == before["audio_halves"] or during["active_voices"] != count:
                        raise RuntimeError("Voice ladder activity did not match requested chord")
                finally:
                    errors=[]
                    for note in notes[:count]:
                        try: short_message(session,journal,0x8F,note,0)
                        except Exception as error: errors.append(str(error))
                    try: short_message(session,journal,0xBF,120,0)
                    except Exception as error: errors.append(str(error))
                    if errors: raise RuntimeError("Voice-ladder cleanup failed: " + "; ".join(errors))
                time.sleep(.15)
                step["after"] = after = query(session,journal)
                if after["active_voices"] or after["audio_paused"]:
                    raise RuntimeError("Voice ladder cleanup did not leave an idle engine")
            result["after"] = after
        if args.action == "matrix":
            if args.firmware not in ("702","703","704","705","706","707"): raise RuntimeError("Extended matrix requires firmware702..707")
            if before["audio_paused"] or before["dsp_init_failed"] or before["active_voices"]:
                raise RuntimeError("DSP is unavailable or notes are already active; matrix refused")
            run_matrix(session,journal,result)
            result["after"]=query(session,journal,2)
        if args.action == "release-checks":
            if args.firmware not in ("702","703","704","705","706","707"): raise RuntimeError("Release matrix requires firmware702..707")
            if before["audio_paused"] or before["dsp_init_failed"] or before["active_voices"]:
                raise RuntimeError("DSP is unavailable or notes are active; release tests refused")
            run_releases(session,journal,result)
            result["after"]=query(session,journal,2)
        result["success"] = True
    except Exception as error:
        result["error"] = str(error)
    finally:
        try:
            if session is not None:
                errors=session.close()
                if errors: result.update(success=False,cleanup_errors=errors)
        except Exception as error: result.update(success=False,cleanup_errors=[str(error)])
        try:
            journal.record("bench_finished", **result)
            (journal.directory/"report.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        except Exception as error: result.update(success=False,evidence_error=str(error))
        finally: journal.close()
    print(json.dumps({**result,"artifacts":str(journal.directory)}))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
