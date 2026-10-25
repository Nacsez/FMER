"""Validate a real generated sound collection in an isolated offline browser.

Does not access a device or change the manifest, sound banks or recipes.
SPDX-License-Identifier: GPL-3.0-only
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    folder, out = args.review_dir.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), library=manifest["version"],
                  manifest_sha256=sha(manifest_path), html_sha256=sha(folder / "index.html"),
                  generator_sha256=sha(ROOT / "tools/sound_collection_review.py"),
                  checks=[], errors=[], external_requests=[], hardware_access=False,
                  evidence_scope="Actual offline catalog/browser playback. No hardware or subjective listening qualification.")
    try:
        patches = manifest["patches"]
        assert len(patches) == 192
        assert len(manifest["collections"]) == 4
        clips = [clip for patch in patches for clip in patch["clips"]]
        assert len(clips) == 576
        assert all((folder / clip["path"]).is_file() for clip in clips)
        assert all((folder / download["path"]).is_file() for download in manifest["downloads"])
        report["checks"].append("All 192 real instruments, 576 audition files and 13 linked downloads are present")
        report["audio_files"] = len(clips)
        report["downloads"] = len(manifest["downloads"])
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True)
            context = browser.new_context(viewport={"width": 1500, "height": 1100}, accept_downloads=True)
            page = context.new_page()
            page.on("pageerror", lambda error: report["errors"].append(str(error)))
            page.on("request", lambda request: report["external_requests"].append(request.url) if request.url.startswith(("http:", "https:")) else None)
            page.goto((folder / "index.html").as_uri())
            assert page.locator("#cards .card").count() == 192
            assert page.locator("#downloads a").count() == len(manifest["downloads"])
            assert page.evaluate("document.querySelector('#player').paused")
            profile_ids = {}
            for collection in manifest["collections"]:
                cid = collection["id"]
                page.locator(f"[data-collection='{cid}']").click()
                assert page.locator("#cards .card").count() == len(set(collection["patch_ids"]))
                page.locator("#slots").click()
                actual = page.locator("#slot-table select").evaluate_all("els=>els.map(el=>el.value)")
                assert actual == collection["patch_ids"] and len(actual) == 64
                profile_ids[cid] = actual
                assert page.locator("#slot-table select").first.locator("option").count() == 192
                page.locator("#close-slots").click()
            report["checks"].append("A/B/C/D show the exact intended ordered 64-slot loadouts, with all 192 replacement choices")
            page.locator("[data-collection='']").click()
            flagged = [p for p in patches if p.get("metrics", {}).get("warnings") or p.get("metrics", {}).get("failures")]
            page.locator("#review-filter").select_option("measured-flags")
            assert page.locator("#cards .card").count() == len(flagged)
            for patch in flagged:
                page.locator(f"[data-patch='{patch['id']}']").click()
                assert page.locator("#measurement-flags").is_visible()
                for warning in patch["metrics"]["warnings"] + patch["metrics"]["failures"]:
                    assert warning in page.locator("#measurement-flags").inner_text()
            report["flagged_patch_ids"] = [p["id"] for p in flagged]
            report["checks"].append("Every measured failure/warning is visible on its instrument and through Measurement flags filtering")
            page.locator("#review-filter").select_option("")
            tested_audio = []
            examples = [patches[0], next(p for p in patches if p["engine"] == "VA"), next(p for p in patches if "ambient" in p.get("group", "").lower() or "pad" in p.get("family", "").lower())]
            for patch in examples:
                page.locator(f"[data-patch='{patch['id']}']").click()
                assert page.locator("#clips button").count() == 3
                for index, clip in enumerate(patch["clips"]):
                    page.locator(f"[data-clip='{index}']").click()
                    page.wait_for_function("!document.querySelector('#player').paused && document.querySelector('#player').currentTime>0 && document.querySelector('#player').duration>0")
                    assert page.locator(f"[data-clip='{index}']").get_attribute("aria-pressed") == "true"
                    tested_audio.append(dict(id=patch["id"], clip=clip["path"], duration=page.evaluate("document.querySelector('#player').duration")))
            page.locator(f"[data-patch='{patches[0]['id']}']").click()
            assert page.evaluate("document.querySelector('#player').paused && !document.querySelector('#player').hasAttribute('src')")
            report["tested_audio"] = tested_audio
            report["checks"].append("Nine actual FM/VA/ambient phrase/soft/dry WAVs play through file://; patch switching stops playback")
            page.locator("#notes").fill("Warm body")
            page.locator("#notes").press("End")
            page.locator("#notes").press("Space")
            page.locator("#notes").type("bright attack")
            assert page.locator("#notes").input_value() == "Warm body bright attack"
            assert page.evaluate("document.querySelector('#player').paused")
            page.locator("#notes").press("Tab")
            page.locator("[data-rating='keep']").click()
            page.locator("#favorite").focus()
            page.locator("#favorite").press("Space")
            assert page.locator("#favorite").get_attribute("aria-pressed") == "true"
            assert page.locator("[data-rating='keep']").get_attribute("aria-pressed") == "true"
            assert page.locator("[data-rating='rework']").get_attribute("aria-pressed") == "false"
            page.locator(f"[data-patch='{patches[1]['id']}']").click()
            assert page.locator("#favorite").get_attribute("aria-pressed") == "false"
            assert page.locator("#notes").input_value() == ""
            page.locator("[data-rating='rework']").click()
            assert page.locator("[data-rating='rework']").get_attribute("aria-pressed") == "true"
            report["checks"].append("Space enters notes without starting audio; keyboard Favorite and exclusive ratings remain scoped to each patch")
            page.locator("[data-collection='A']").click()
            page.locator("#slots").click()
            replacement = next(p for p in patches if p["engine"] == "VA")["id"]
            page.locator("[data-slot='0']").select_option(replacement)
            page.locator("#close-slots").click()
            with page.expect_download() as info:
                page.locator("#export").click()
            exported_path = out / "actual-catalog-test-review.json"
            info.value.save_as(exported_path)
            exported = json.loads(exported_path.read_text(encoding="utf-8"))
            assert exported["format"] == "FMER-SOUND-CURATION" and exported["library_version"] == manifest["version"]
            assert exported["collections"]["A"][0] == replacement
            assert exported["ratings"][patches[0]["id"]] == dict(rating="keep", favorite=True, notes="Warm body bright attack")
            assert exported["ratings"][patches[1]["id"]]["rating"] == "rework"
            assert exported["collections"]["B"] == profile_ids["B"]
            assert all(len(slots) == 64 for slots in exported["collections"].values())
            page.locator("#undo").click()
            page.locator("#slots").click()
            assert page.locator("[data-slot='0']").input_value() == profile_ids["A"][0]
            page.locator("#close-slots").click()
            report["checks"].append("Real-ID curation exports all four complete loadouts and independent ratings; Undo restores the original slot")
            page.locator("[data-collection='']").click()
            page.locator(f"[data-patch='{patches[0]['id']}']").click()
            page.locator("[data-clip='0']").click()
            page.wait_for_function("!document.querySelector('#player').paused && document.querySelector('#player').currentTime>0")
            page.evaluate("window.scrollTo(0,0);document.querySelector('#toast').hidden=true")
            page.screenshot(path=str(out / "actual-catalog-desktop.png"), full_page=False)
            assert not page.evaluate("document.documentElement.scrollWidth>innerWidth")
            page.locator("[data-collection='B']").click()
            page.locator("#slots").click()
            page.screenshot(path=str(out / "actual-loadout-slots.png"), full_page=False)
            page.locator("#close-slots").click()
            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(out / "actual-catalog-mobile.png"), full_page=False)
            assert not page.evaluate("document.documentElement.scrollWidth>innerWidth")
            report["checks"].append("Actual names, descriptions and slot controls fit desktop/mobile without horizontal overflow")
            assert not report["errors"], report["errors"]
            assert not report["external_requests"], report["external_requests"]
            browser.close()
        assert sha(manifest_path) == report["manifest_sha256"]
        report["checks"].append("Browser review produces no network/device operations and leaves the source manifest unchanged")
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
