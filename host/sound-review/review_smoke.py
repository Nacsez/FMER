"""Offline actual-browser regressions for the sound audition desk; no device I/O.

Run: python host/sound-review/review_smoke.py [--output artifacts/path]
SPDX-License-Identifier: GPL-3.0-only
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from sound_collection_review import validate_manifest, write_review


def fixture() -> dict:
    patches = []
    for i in range(192):
        patches.append(dict(id=f"review-{i:03d}", name=f"SOUND{i:03d}", title=f"Original sound {i + 1}",
                            engine="FM" if i < 96 else "VA", category="percussion" if i % 2 else "texture",
                            family=["Bass", "Percussion", "Lead", "Ambient"][i % 4],
                            tags=["squelchy" if i % 3 == 0 else "floaty"], description="Illustrative browser fixture, not a released instrument.",
                            technique="Independent envelopes and detuned operators.", audition_note=48,
                            clips=[dict(label="Performance", kind="performance", path="audio/probe.wav", peak=0.12, rms=0.06)]))
    patches[0]["title"] = 'Readable <sound> & "name" </script><script>window.injected=true</script>'
    patches[-1]["clips"] = []
    collections = [dict(id=letter, title=f"Collection {letter} — {title}", description="Illustrative loadout for UI regression.",
                        patch_ids=[patches[(offset + i) % 192]["id"] for i in range(64)])
                   for letter, title, offset in [("A", "Balanced", 0), ("B", "Drums & bass", 48), ("C", "Leads & arps", 96), ("D", "Ambient", 144)]]
    return dict(title="Original sound collections", version="review-browser-fixture-v1", patches=patches, collections=collections,
                downloads=[dict(label="Example catalog", path="example-catalog.json")],
                qualification=dict(render="Browser fixture only; not an audio-quality measurement.", hardware="No hardware access."))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/sound-collections-review-smoke")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = dict(checks=[], errors=[], external_requests=[], hardware_access=False,
                  generated_at=datetime.now(timezone.utc).isoformat(),
                  generator_sha256=hashlib.sha256((ROOT / "tools/sound_collection_review.py").read_bytes()).hexdigest())
    manifest = fixture()
    audio = out / "audio"
    audio.mkdir(exist_ok=True)
    with wave.open(str(audio / "probe.wav"), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(22050)
        # A synthetic 3-second fixture tests playback mechanics only.
        stream.writeframes(b"".join(struct.pack("<hh", n, n) for n in (round(4000 * math.sin(i * math.tau * 220 / 22050)) for i in range(3 * 22050))))
    (out / "example-catalog.json").write_text("{}\n", encoding="utf-8")
    page_path = write_review(out, manifest)
    for bad in ("../escape.wav", "https://example.org/a.wav", "C:/secret.wav", "/absolute.wav", "audio\\sound.wav", "audio/%2e%2e/outside.wav"):
        invalid = deepcopy(manifest)
        invalid["patches"][0]["clips"][0]["path"] = bad
        try:
            validate_manifest(invalid)
        except ValueError:
            continue
        raise AssertionError(f"Accepted unsafe media path: {bad}")
    report["checks"].append("Unsafe/nonlocal media paths rejected before generating HTML")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1050}, accept_downloads=True)
            page = context.new_page()
            page.on("pageerror", lambda error: report["errors"].append(str(error)))
            page.on("request", lambda request: report["external_requests"].append(request.url) if request.url.startswith(("http:", "https:")) else None)
            page.goto(page_path.as_uri())
            assert page.locator("#cards .card").count() == 192
            assert page.locator("#detail-title").inner_text() == manifest["patches"][0]["title"]
            assert not page.evaluate("Boolean(window.injected)")
            assert page.evaluate("document.querySelector('#player').paused")
            report["checks"].append("192-patch offline catalog loads with safe text rendering and no autoplay")
            page.locator("#engine").select_option("VA")
            assert page.locator("#cards .card").count() == 96
            page.locator("#family").select_option("Bass")
            assert page.locator("#cards .card").count() == 24
            page.locator("#search").fill("squelchy")
            assert page.locator("#cards .card").count() == 8
            page.locator("#search").fill("impossible-search")
            assert page.locator("#cards .card").count() == 0
            assert "No sounds" in page.locator("#cards").inner_text()
            page.locator("#search").fill("")
            page.locator("#engine").select_option("")
            page.locator("#family").select_option("")
            report["checks"].append("Engine/family/texture search filters compose and empty state is explicit")
            page.locator("[data-patch='review-001']").click()
            page.locator("[data-rating='keep']").click()
            page.locator("#favorite").click()
            page.locator("#notes").fill("Good attack; try a darker release.")
            page.locator("#notes").press("Tab")
            page.locator("[data-collection='B']").click()
            page.locator("#slots").click()
            assert page.locator("#slot-table select").count() == 64
            page.locator("[data-slot='0']").select_option("review-001")
            page.locator("#close-slots").click()
            with page.expect_download() as download_info:
                page.locator("#export").click()
            download_path = out / "exported-curation.json"
            download_info.value.save_as(download_path)
            exported = json.loads(download_path.read_text(encoding="utf-8"))
            assert exported["ratings"]["review-001"] == dict(rating="keep", favorite=True, notes="Good attack; try a darker release.")
            assert exported["collections"]["B"][0] == "review-001"
            assert all(len(ids) == 64 for ids in exported["collections"].values())
            report["checks"].append("Ratings, favorites, notes and 64-slot substitutions export together without bank writes")
            page.locator("#undo").click()
            page.locator("#slots").click()
            assert page.locator("[data-slot='0']").input_value() == "review-048"
            page.locator("#close-slots").click()
            page.reload()
            page.locator("[data-patch='review-001']").click()
            assert page.locator("[data-rating='keep']").get_attribute("aria-pressed") == "true"
            assert page.locator("#notes").input_value() == "Good attack; try a darker release."
            report["checks"].append("One edit Undo restores the preceding slot; file-origin review survives reload")
            bad_review = deepcopy(exported)
            bad_review["collections"]["A"][0] = "unknown-patch"
            page.locator("#import-file").set_input_files({"name": "bad-review.json", "mimeType": "application/json", "buffer": json.dumps(bad_review).encode()})
            page.wait_for_function("document.querySelector('#toast').textContent.includes('Import not applied')")
            assert page.locator("#notes").input_value() == "Good attack; try a darker release."
            bad_review["library_version"] = "another-version"
            page.locator("#import-file").set_input_files({"name": "wrong-version.json", "mimeType": "application/json", "buffer": json.dumps(bad_review).encode()})
            page.wait_for_function("document.querySelector('#toast').textContent.includes('different library version')")
            report["checks"].append("Unknown patch and library-version imports rejected atomically, preserving current notes")
            page.on("dialog", lambda dialog: dialog.accept())
            page.locator("#import-file").set_input_files(str(download_path))
            page.wait_for_function("document.querySelector('#toast').textContent.includes('Review imported')")
            page.locator("[data-collection='B']").click()
            page.locator("#slots").click()
            assert page.locator("[data-slot='0']").input_value() == "review-001"
            page.locator("#close-slots").click()
            report["checks"].append("Validated exported review restores loadout choices with explicit replacement confirmation")
            page.locator("[data-collection='']").click()
            page.locator("[data-patch='review-001']").click()
            page.locator("[data-clip='0']").click()
            page.wait_for_function("!document.querySelector('#player').paused && document.querySelector('#player').currentTime>0")
            page.locator("#volume").fill("37")
            assert abs(page.evaluate("document.querySelector('#player').volume") - 0.37) < 0.0001
            assert page.locator("#volume-value").inner_text() == "37%"
            page.locator("[data-patch='review-002']").click()
            assert page.evaluate("document.querySelector('#player').paused && !document.querySelector('#player').hasAttribute('src')")
            report["checks"].append("Local WAV plays; numeric monitor gain agrees with audio; patch switching stops previous audio")
            page.locator("[data-patch='review-191']").click()
            assert "not been rendered" in page.locator("#audio-status").inner_text()
            assert page.locator("#clips button").count() == 0
            report["checks"].append("Missing-render state never displays a functioning playback action")
            page.locator("[data-patch='review-006']").click()
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(out / "desktop.png"), full_page=False)
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(out / "mobile.png"), full_page=False)
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            page.locator("#favorite").focus()
            assert page.evaluate("document.activeElement.id") == "favorite"
            page.locator("#favorite").press("Space")
            assert page.locator("#favorite").get_attribute("aria-pressed") == "true"
            report["checks"].append("Desktop/mobile have no horizontal overflow; native keyboard activation works")
            assert not report["errors"], report["errors"]
            assert not report["external_requests"], report["external_requests"]
            report["checks"].append("No JavaScript errors, HTTP requests, hosted service or device access")
            browser.close()
        report["status"] = "pass"
    except Exception as error:
        report["status"] = "fail"
        report["failure"] = repr(error)
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report.get("status"), "checks": len(report["checks"]), "report": str(out / "report.json")}))


if __name__ == "__main__":
    main()
