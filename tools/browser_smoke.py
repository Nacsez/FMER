#!/usr/bin/env python3
"""Optional visual smoke using an already installed Playwright and Chromium browser."""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
from http.server import HTTPServer
import json
from pathlib import Path
import threading
import traceback
import sandbox


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, default=Path("C:/Program Files/Google/Chrome/Application/chrome.exe"))
    parser.add_argument("--config", choices=("Debug", "Release"), default="Debug")
    args = parser.parse_args()
    directory = sandbox.ROOT / "artifacts/browser-smoke" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    directory.mkdir(parents=True)
    # Never mutate the owner's companion library, or mix test telemetry with play sessions.
    sandbox.OUTPUT = directory / "renders"
    executable = sandbox.find_executable(args.config)
    library_root = directory / "library"
    server = HTTPServer(("127.0.0.1", 0), sandbox.handler_for(executable, library_root=library_root))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    summary = {"hardware_access": False, "config": args.config, "library_root": str(library_root), "checks": [], "errors": []}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=str(args.browser), headless=True)
            page = browser.new_page(viewport={"width":1280,"height":1000}, reduced_motion="reduce")
            page.on("pageerror", lambda error: summary["errors"].append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="domcontentloaded")
            page.wait_for_function("document.querySelectorAll('#parameters [data-parameter]').length === 145")
            page.wait_for_function("document.querySelectorAll('#librarySlot option').length === 128")
            summary["checks"].append("145 parameter controls loaded from C++ registry")
            assert page.locator("#waveform").is_disabled() and page.locator("#cutoff").is_disabled()
            summary["checks"].append("VA-only controls disabled for FM; shared effects remain editable")

            def change(selector, value):
                page.locator(selector).fill(str(value))
                page.locator(selector).press("Tab")

            def render(button="#render"):
                before = page.locator("#report").text_content()
                page.locator(button).click()
                page.wait_for_function("old => document.querySelector('#report').textContent !== old || document.querySelector('#status').classList.contains('error')", arg=before)
                assert not page.locator("#status").evaluate("e => e.classList.contains('error')"), page.locator("#status").text_content()
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Rendered')")
                page.wait_for_function("document.querySelector('audio').readyState >= 2")
                page.locator("#stop").click()
                return json.loads(page.locator("#report").text_content())

            change("#note", 69); change("#duration", 1)
            fm = render()
            assert fm["engine"] == "MSFA" and fm["peak"] > 0 and fm["hardware_access"] is False
            summary["checks"].append("FM renders through C++ and browser loads actual WAV")
            page.locator("#engine").select_option("va")
            assert page.locator("#waveform").is_enabled()
            page.locator("#waveform").select_option("square")
            va = render()
            assert va["engine"] == "FMER-VA" and va["wav_sha256"] != fm["wav_sha256"]
            summary["checks"].append("VA square render differs from FM")

            # Exercise native visual controls, not just their precision inputs.
            baseline = page.evaluate("collect()")
            cutoff_range = page.locator("#cutoffRange")
            cutoff_range.press("Home")
            assert page.locator("#cutoff").input_value() == "20"
            assert page.evaluate("collect().cutoff") == 20
            page.locator("#undo").click()
            assert page.evaluate("collect()") == baseline
            cutoff_range.press("End")
            assert page.locator("#cutoff").input_value() == "18000"
            page.locator("#undo").click()
            cutoff_range.focus()
            page.keyboard.down("Home")
            for _ in range(5):
                page.keyboard.down("ArrowRight")
            page.keyboard.up("ArrowRight"); page.keyboard.up("Home")
            assert int(page.locator("#cutoff").input_value()) > 20
            page.locator("#undo").click()
            assert page.evaluate("collect()") == baseline
            page.locator("#fx_cutoff_hzRange").press("Home")
            assert page.locator("#fx_cutoff_hz").input_value() == "20"
            page.locator("#undo").click()
            assert page.evaluate("collect()") == baseline
            summary["checks"].append("log cutoff endpoints and held keyboard gesture restore exact pre-edit state")

            cutoff_range.scroll_into_view_if_needed()
            bounds = cutoff_range.bounding_box()
            x, y = bounds["x"], bounds["y"] + bounds["height"] / 2
            # Native thumb inset is approximately 8px in this installed Chrome.
            position = lambda p: x + 8 + (bounds["width"] - 16) * p
            page.mouse.move(position(.84), y); page.mouse.down()
            page.mouse.move(position(.2), y, steps=10)
            low = int(page.locator("#cutoff").input_value())
            page.mouse.move(position(.5), y, steps=10)
            middle = int(page.locator("#cutoff").input_value())
            assert 20 < low < middle and 500 < middle < 720, (low, middle)
            assert page.locator("#cutoffRange").evaluate("e => e === document.activeElement")
            page.mouse.up()
            assert page.evaluate("collect().cutoff") == middle
            page.locator("#undo").click()
            assert page.evaluate("collect()") == baseline
            change("#cutoff", 6001)
            assert page.evaluate("collect().cutoff") == 6001
            assert page.locator("#cutoff").input_value() == "6001"
            page.locator("#undo").click()
            summary["checks"].append("native multi-move logarithmic drag updates real Hz and has one Undo; exact values are not quantized on sync")

            page.locator("#parameters details").last.locator("summary").click()
            page.locator("#param134Choice").select_option("4")
            assert page.locator("#param134").input_value() == "4"
            assert page.evaluate("collect().vced[134]") == 4
            page.locator("#undo").click()
            initial_sync = bool(baseline["vced"][136])
            page.locator("#param136Choice").set_checked(not initial_sync)
            assert page.locator("#param136").input_value() == str(int(not initial_sync))
            page.locator("#undo").click()
            assert page.locator("#param136Choice").is_checked() == initial_sync
            page.locator("#parameters details").first.locator("summary").click()
            page.locator("#param121Range").press("Home")
            assert page.evaluate("collect().vced[121]") == 0
            page.locator("#undo").click()
            assert page.evaluate("collect()") == baseline
            summary["checks"].append("algorithm selector, sync switch and operator slider agree with canonical raw bytes and Undo")

            change("#fx_delay", .271828)
            assert page.evaluate("collect().effects.delay") == .271828
            assert page.locator("#fx_delay").input_value() == "0.271828"
            page.locator("#fx_delay").focus(); page.locator("#fx_delay").hover()
            page.mouse.wheel(0, 100)
            assert page.evaluate("collect().effects.delay") == .271828
            page.locator("#undo").click()
            change("#cutoff", 18001)
            assert page.evaluate("collect()") == baseline
            assert page.locator("#status").evaluate("e => e.classList.contains('error')")
            summary["checks"].append("precise fractional values survive slider sync and wheel scrolling; invalid exact entry is atomic")

            palette = page.evaluate("""() => {
                const style = getComputedStyle(document.documentElement);
                return ['--background','--panel','--accent','--focus'].map(k=>style.getPropertyValue(k).trim());
            }""")
            assert palette == ["#070709", "#101014", "#76ff53", "#ff78d4"], palette
            cutoff_range.focus()
            assert cutoff_range.evaluate("e=>getComputedStyle(e).outlineColor") == "rgb(255, 120, 212)"
            assert cutoff_range.bounding_box()["height"] >= 44
            summary["checks"].append("CADER source tokens, visible pink keyboard focus and 44px slider hit region")

            page.locator("#captureA").click(); change("#cutoff", 900)
            page.locator("#undo").click(); assert page.locator("#cutoff").input_value() == "6000"
            page.locator("#undo").click(); assert page.locator("#cutoff").input_value() == "900"
            page.locator("#compare").click(); assert page.locator("#cutoff").input_value() == "6000"
            page.locator("#compare").click(); assert page.locator("#cutoff").input_value() == "900"
            summary["checks"].append("whole-edit Undo/redo and A/B restore prior state")

            change("#fx_delay", .3); change("#fx_chorus", .2); change("#tail", 2)
            wet = render()
            assert wet["wav_sha256"] != va["wav_sha256"] and wet["settings"]["effects"]["delay"] == .3
            summary["checks"].append("effects and selectable release window reach compiled render")

            page.locator("#useSequence").click(); page.locator("#clearPattern").click()
            change("#patternLength", 4); change("#duration", 2)
            for pitch in (60, 64, 67):
                page.locator(f'#stepKeys [data-pitch="{pitch}"]').click()
            page.locator("#noteVelocity_64Range").press("Home")
            assert page.evaluate("collect().pattern.steps[0].notes[1].velocity") == 1
            page.locator("#undo").click()
            assert page.locator("#noteVelocity_64").input_value() == "100"
            change("#noteVelocity_64", 80); change("#noteVelocity_67", 70)
            assert page.evaluate("collect().pattern.steps[0].notes") == [
                {"pitch":60,"velocity":100},{"pitch":64,"velocity":80},{"pitch":67,"velocity":70}]
            summary["checks"].append("visual chord keys and individual velocity controls edit the persisted pattern with Undo")
            page.locator("#advancedStep summary").click()
            page.locator('[data-step="1"]').click(); page.locator("#stepTie").check(); page.locator("#applyStep").click()
            page.locator('[data-step="3"]').click(); page.locator("#stepNotes").fill("72:65")
            page.locator("#stepGateRange").press("Home")
            assert page.locator("#stepNotes").input_value() == "72:65"
            assert page.evaluate("collect().pattern.steps[3].notes") == []
            page.locator("#applyStep").click()
            assert page.evaluate("collect().pattern.steps[3].notes") == [{"pitch":72,"velocity":65}]
            summary["checks"].append("advanced chord draft survives gate gestures and commits only on Apply")
            page.locator('[data-step="63"]').click(); page.locator("#stepNotes").fill("80:90"); page.locator("#applyStep").click()
            change("#patternLength", 64); change("#patternLength", 4)
            assert page.locator("#stepNotes").input_value() == "80:90"
            sequence = render()
            first = [e for e in sequence["events"] if e["frame"] == 0 and e["type"] == "NoteOn"]
            assert sorted(e["data1"] for e in first) == [60, 64, 67], first
            assert sorted((e["data1"], e["data2"]) for e in first) == [(60,100),(64,80),(67,70)]
            assert sequence["settings"]["pattern"]["steps"][63]["notes"][0]["pitch"] == 80
            summary["checks"].append("editable chord/tie/rest pattern renders expected notes; hidden step 64 survives length edits")

            with page.expect_download() as download:
                page.locator("#save").click()
            session = directory / "session.json"; download.value.save_as(session)
            saved = json.loads(session.read_text())
            assert saved["format"] == "FMER-LAB" and saved["version"] == 2
            assert len(saved["settings"]["pattern"]["steps"]) == 64 and saved["settings"]["effects"]["delay"] == .3
            change("#note", 60)
            page.locator("#restore").set_input_files(session)
            page.wait_for_function("document.querySelector('#status').textContent.startsWith('Session restored')")
            assert page.locator("#note").input_value() == "69"
            summary["checks"].append("v2 session export/restore retains sound, effects, hidden steps and settings")

            before_invalid = page.evaluate("collect()")
            invalid = json.loads(json.dumps(saved)); invalid["settings"]["future_unknown_field"] = 123
            invalid_file = directory / "invalid-session.json"
            invalid_file.write_text(json.dumps(invalid))
            page.locator("#restore").set_input_files(invalid_file)
            page.wait_for_function("document.querySelector('#status').classList.contains('error')")
            assert page.evaluate("collect()") == before_invalid
            assert "Unsupported session field" in page.locator("#status").text_content()
            invalid = json.loads(json.dumps(saved)); invalid["settings"]["effects"]["chorus_rate_hz"] = 9
            invalid_file.write_text(json.dumps(invalid))
            page.locator("#restore").set_input_files(invalid_file)
            page.wait_for_function("document.querySelector('#status').textContent.includes('chorus_rate_hz')")
            assert page.evaluate("collect()") == before_invalid
            summary["checks"].append("unknown session fields and invalid hidden effect settings refuse without changing working state")

            pending = []
            page.route("**/api/render", lambda route: pending.append(route))
            before_stop = page.locator("#report").text_content()
            with page.expect_request("**/api/render"):
                page.locator("#render").click()
            page.locator("#stop").click()
            assert pending, "Render interception was not reached"
            response = pending[0].fetch(); pending[0].fulfill(response=response)
            page.wait_for_function("old => document.querySelector('#report').textContent !== old", arg=before_stop)
            page.wait_for_function("document.querySelector('audio').readyState >= 2")
            assert page.locator("#audio").evaluate("audio => audio.paused")
            page.unroute("**/api/render")
            summary["checks"].append("Stop during an in-flight render suppresses late autoplay while retaining its result")

            page.locator("#libraryName").fill("Smoke original")
            page.locator("#librarySave").click()
            page.wait_for_function("document.querySelector('#libraryStatus').textContent.startsWith('Saved slot')")
            assert "Smoke original" in page.locator("#librarySlot option").first.text_content()
            change("#note", 62)
            audition = render("#libraryAudition")
            assert audition["settings"]["note"] == 69 and page.locator("#note").input_value() == "62"
            page.locator("#libraryLoad").click()
            page.wait_for_function("document.querySelector('#status').textContent.startsWith('Loaded Smoke original')")
            assert page.locator("#note").input_value() == "69"
            with page.expect_download() as download:
                page.locator("#libraryBackup").click()
            backup = directory / "library-backup.json"; download.value.save_as(backup)
            page.locator("#libraryName").fill("Smoke replacement")
            page.locator("#librarySave").click()
            page.wait_for_function("document.querySelector('#librarySlot option').textContent.includes('Smoke replacement')")
            page.locator("#libraryRestoreFile").set_input_files(backup); page.locator("#libraryRestore").click()
            page.wait_for_function("document.querySelector('#libraryStatus').textContent.startsWith('Library restored')")
            assert "Smoke original" in page.locator("#librarySlot option").first.text_content()
            page.locator("#libraryUndo").click()
            page.wait_for_function("document.querySelector('#libraryStatus').textContent.startsWith('Library change undone')")
            assert "Smoke replacement" in page.locator("#librarySlot option").first.text_content()
            summary["checks"].append("persistent library Save/load, non-destructive audition, backup/restore and Undo")

            with page.expect_download() as download:
                page.locator("#exportVoice").click()
            exported = directory / "exported.syx"; download.value.save_as(exported)
            assert len(exported.read_bytes()) == 163 and exported.read_bytes()[6:161] == bytes(saved["settings"]["vced"])
            assert "omitted" in page.locator("#status").text_content()
            summary["checks"].append("working voice exports standard DX7 with visible extension-loss notice")

            # Import an original synthetic voice, with valid Yamaha envelope.
            payload = bytes(fm["patch_vced"])
            patch = directory / "original.syx"
            patch.write_bytes(bytes([240,67,0,0,1,27])+payload+bytes([(-sum(payload))&127,247]))
            page.locator("#engine").select_option("fm")
            page.locator("#scenario").select_option("note"); change("#duration", 1); change("#tail", 1)
            page.locator("#dry").click()
            page.locator("#patch").set_input_files(patch)
            page.wait_for_function("document.querySelector('#status').textContent.startsWith('Import loaded')")
            assert page.locator('[data-parameter="121"]').input_value() == str(payload[121])
            imported = render()
            assert imported["wav_sha256"] == fm["wav_sha256"]
            summary["checks"].append("C++ DX7 decode updates controls immediately and imported FM audio is identical")

            legacy = directory / "legacy-v1.json"
            legacy.write_text(json.dumps({"format":"FMER-LAB", "version":1, "settings":{
                "scenario":"note", "note":69, "velocity":100, "bpm":120, "duration":1, "voice":1,
                "engine":"fm", "wave":"saw", "cutoff":6000, "sysex":base64.b64encode(patch.read_bytes()).decode(), "edits":{"121":55}}}))
            page.locator("#restore").set_input_files(legacy)
            page.wait_for_function("document.querySelector('#status').textContent.startsWith('Session restored (version 1)')")
            assert page.locator('[data-parameter="121"]').input_value() == "55"
            summary["checks"].append("legacy v1 sessions migrate imports and parameter overrides")

            page.locator("#useArp").click(); page.locator("#arpOrder").select_option("random")
            page.locator("#arpRate").select_option("8"); change("#arpSwing", 65); change("#arpSeed", 42)
            page.locator("#arpRelease").check(); page.locator("#arpLatch").check()
            arp = render(); repeated = render()
            assert arp["wav_sha256"] == repeated["wav_sha256"] and arp["settings"]["arp"]["seed"] == 42
            summary["checks"].append("seeded arp, rate, swing and latch fixture render reproducibly")

            bank_voices = []
            for index in range(32):
                voice = list(payload); voice[121] = 40 + index
                voice[145:155] = list(f"VOICE {index+1:02d}  ".encode("ascii"))
                bank_voices.append(voice)
            bank = directory / "original-bank.syx"
            bank.write_bytes(sandbox.library.PatchCodec(executable, lambda *a, **kw: None).encode(bank_voices))
            page.locator("#patch").set_input_files(bank)
            page.wait_for_function("document.querySelector('#voice').options.length === 32")
            page.locator("#voice").select_option("7")
            assert page.locator('[data-parameter="121"]').input_value() == "46"
            page.locator("#librarySlot").select_option("32")
            page.locator("summary").filter(has_text="Manage 32-voice DX7 banks").click()
            assert "33–64" in page.locator("#bankRange").text_content()
            page.locator("#libraryImportBank").click()
            page.wait_for_function("document.querySelector('#libraryStatus').textContent.startsWith('Saved 32 original')")
            assert "32 occupied" in page.locator("#bankRange").text_content()
            with page.expect_download() as download:
                page.locator("#libraryExportBank").click()
            exported_bank = directory / "exported-bank.syx"; download.value.save_as(exported_bank)
            assert exported_bank.read_bytes() == bank.read_bytes()
            page.locator("#libraryImportBank").click()
            page.wait_for_function("document.querySelector('#libraryStatus').classList.contains('error')")
            assert "occupied" in page.locator("#libraryStatus").text_content().lower()
            summary["checks"].append("32-voice bank selection, range/occupancy preview, library import/export exact round trip and overwrite refusal")

            page.evaluate("scrollTo(0,0)")
            page.screenshot(path=str(directory / "desktop-viewport.png"))
            page.screenshot(path=str(directory / "desktop.png"), full_page=True)
            page.set_viewport_size({"width":430,"height":920})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(directory / "mobile-viewport.png"))
            page.screenshot(path=str(directory / "mobile.png"), full_page=True)
            summary["checks"].append("desktop/mobile layout and no document overflow")
            browser.close()
        restarted = sandbox.library.PatchLibrary(library_root, executable).snapshot()
        assert restarted["slots"][0]["name"] == "Smoke replacement"
        summary["checks"].append("library survives reopening from disk")
        events = [json.loads(line) for line in (sandbox.OUTPUT / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert any(event.get("event") == "browser" and event["client"]["event"] == "render_complete" for event in events)
        summary["checks"].append("browser actions and render IDs persisted in isolated telemetry")
        assert not summary["errors"], summary["errors"]
        summary["status"] = "passed"
    except Exception:
        summary["status"] = "failed"; summary["exception"] = traceback.format_exc()
    finally:
        server.shutdown(); thread.join(timeout=5); server.server_close()
    (directory / "summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2)); print(directory)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
