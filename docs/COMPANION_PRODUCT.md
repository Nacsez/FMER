## Companion734 r3 - 20 October 2026

Firmware is locked at734-r2. This Companion revision adds manual GitHub update
links, clear name editing, selected set/PC-bank/project-bundle deployment and
full pre-transfer backup with failure download. Imports merge sound packs into
the local Library; hardware writes always require a reviewed destination list.
A custom-application profile accepts only the reviewed935 updater and protected
layout; applications themselves are not release-certified. See
[the current contract](release/COMPANION_R3.md). Historical sections follow.

## Current 734 Companion — 19 October 2026

The portable Windows10/11 x64 app contains its runtime, original defaults,
firmware and offline Help. The visual guide now adds31 annotated feature sheets,
five workflow diagrams and a shortcut sheet, reachable from the handbook sidebar.
Source material and release drafts are in docs/release. No website or account is
required; firmware files are bundled/local, not automatically downloaded.

Current installation admits supported memory/calibration layouts rather than an
exact original application fingerprint. Unknown layouts remain blocked. The
included updater supports verified resume of its matching package; arbitrary
update modes/damaged bootloaders remain outside that guarantee. Supported stock
application restore uses a separately supplied compatible image. FMER musical
backup/restore and stock application restore are different workflows.

Standard DX7 voice/bank import/export, loss review, isolated library Undo and
current native FMER data are supported. Native Felucca projects and vendor patch
banks are not implicitly interchangeable. Original code/defaults are GPL-3.0-only;
remaining distribution gates are documented in docs/release/RELEASE_READINESS.md.

No runtime or firmware behavior changes are introduced by this media pass. The
older descriptions below are retained as history and are not current admission
policy or a current feature specification.

## Historical 733 portable companion preview - 2026-10-16

This was the companion state on16 October; current734 details above supersede it.
Windows 10/11 x64 is the release-test target. The ZIP contains a one-click EXE,
official embedded Python 3.13.16, statically linked host renderer, original
64-instrument catalog and DEFAULT/USER bank files, illustrated offline help,
exact-stock first-install firmware, dependency notices and a source snapshot.
No hosted site, account, separately installed Python, owner library or private
device dump is required. A normal system browser and Windows .NET 4 launcher
support are the remaining OS prerequisites.

The six existing workspaces remain centralized. Firmware now offers inspection
of the included stock-V15-to-733 package, then explicit installation. All source,
package, loader and origin pins are rechecked before device access. The loader
checks the complete original application/calibration region before application
writing; V15 text alone is insufficient. This is an offline-qualified preview
for Amethyst, not universal V15 support or an upgrade for installed FMER.
A mismatch may leave the device in update mode. No automatic resume is exposed.
Stock patch export, factory ROM backup and rollback are not provided by this
portable installer. Its backups require FMER733 and contain musical data.

The handbook has 27 illustrated pages, 198 canonical parameter definitions,
45 physical menu diagrams, all32 FM routing diagrams, actual firmware renderer
captures and actual companion browser captures. The audit corrected stale HOME
FX positions, voice-lock behavior, key-scaling controls, modulation-recipe access,
SINGLE sequencing and packaging instructions. Clean/Warm delay selection remains
companion-only in733; this is documented rather than inventing a panel action.

Fresh user data lives in `%LOCALAPPDATA%/FMER/Companion`. Replacing the program
folder does not replace music. DEFAULT and USER start with independent copies;
Library catalog import is explicit and merges items. Device management supports
one connected FM-1 at a time. Backup files can be organized per named instrument,
but automatic stable-serial device selection is not claimed. Native11, songs,
modulation recipes and current wired MIDI capabilities are preserved.

See [the portable release review](COMPANION_RELEASE_733.md) for evidence,
remaining gates and the Amethyst procedure. Bluetooth remains deferred.

## 725 offline release preparation - 2026-10-13

725 is compiled and independently audited but **not installed**: the owner disconnected Test01, which remains724. Global page1 now exposes SINGLE/4TRK; editing VOICES exits mono tracks into the single-instrument allocator. Four physical-source chord notes and return to four tracks have host regression coverage. All128 instruments, projects0/13/14 and live state were backed up before disconnect;132-record C/Python migration passes. No new device write or hardware qualification is claimed.

Companion725 has current protocol labels, centralized device workflows, an explicit playing-mode selector, offline Help and a portable Windows EXE rehearsal with per-user persistence and Quit. General factory flashing, public redistribution, clean-machine testing, runtime servicing, USB reliability, optical acceptance and the prior combined-load timing reserve failure remain open. [Development and release-readiness report](DEVELOPMENT_725.md).

# Companion Library preview 1

Updated 2026-10-11 (America/New_York). Firmware remains 721. The owner is testing the unit; this pass changes host software only. Windows is the tested target. macOS and Linux remain goals, with the owner's explicit permission to defer them.

## What is implemented

| Area | Behavior | Boundary |
|---|---|---|
| Library | Instruments/projects, collections, tags, favorites, search, multiselection, rename, duplicate, move, Trash/recover/purge, one transaction Undo | Up to 512 items; 10 MiB including Undo; isolated from hardware slots |
| Files | Checksummed export/merge-import/replacement restore; revision guards, previous copy, atomic commit | JSON formats are explicit, not interchangeable with DX7/native files |
| Projects | Complete native state including 16 patterns and four track references; optional PC instrument snapshots; extract snapshots into independent Library instruments | Device references are not silently remapped or deployed; hardware project names are not independent fields |
| PC banks | Rename/copy/swap, move USER to empty, clear USER slot, backup/restore/Undo, three separately named bank reset scopes | DEFAULT stays populated; existing owner bank file is retained |
| Editor | Existing shared-core audition and visual sound/pattern controls embedded into the workspace | Working state, PC bank destination and Library copies remain explicit |
| FM-1 | Catalog/pull/load/send, project load/save/send, instrument rename/copy/swap, named bank resets, diagnostic capture | Exact 721 identity and Windows WinMM; explicit confirmation for writes; no individual hardware delete command |
| Unit backup | All 128 instrument positions, 16 projects, live native state and eight persistent MIDI settings; stable-generation checks | Musical data, not boot/calibration/firmware dump |
| Unit restore | Validates first, commits destination backup before first write, then verified populated-slot overlay and MIDI/live restore | Empty source slots preserve destination; multi-write operation is not atomic; failure does not retry |
| Firmware | File inspection, qualification report, background install through the existing reviewed transport | Historical Test01 image is not a public installer; changed source pins disable install; no qualification bypass |
| Operations | Serialized background work, progress, durable result/error/traceback, downloadable last-operation record, interrupted-job recovery | Restart reports interrupted state; it never replays an uncertain write |
| Help | 24 local HTM articles, search, 197 editable parameter definitions, 38 panel/menu rows, glossary and workflows | Works in browser through the app or directly offline; generated from reviewed prose and canonical bounds |

## Design and persistence

Use CADER's established dark palette and compact navigation. Library, Sound banks, Editor, FM-1, Backups and Firmware are separate top-level destinations. Help opens a new tab. Empty states explain the next useful action. Exact sound values remain visible in the editor; names/collections use text because they are text data. No device I/O occurs on page load.

Existing `local/companion709` remains the persistent PC bank root. New catalog state is under `catalog/`, job records under `operations/`. Tests must inject temporary or artifact-only library roots. Collections never become filesystem paths. The browser cannot choose arbitrary server-side paths. Existing loopback Host/Origin checks remain; help serves allowlisted basenames only. Firmware inspection stores immutable bytes under a generated operation identity and rechecks qualification immediately before opening MIDI.

Project snapshots captured in the Editor resolve references against the **PC banks**, refreshed at capture time. This is explicit provenance, not an assertion about hardware contents. A native device project pull alone has no embedded sound bank. For exact physical composition preservation, use a complete unit backup. Extract embedded sounds before deliberately deploying to their referenced slots.

## Packaging options for the next turn

| Option | Advantages | Costs and qualification |
|---|---|---|
| Portable Windows bundle with local browser UI — recommended first | Reuses tested backend; bundle Python and host executable; unzip and launch; optional installer later | Need release manifest, persistent user-data location, shutdown/update behavior, dependency notices, clean Windows machine test, redistributable firmware qualification |
| Desktop wrapper | App window, native dialogs and familiar installer/update experience | Larger runtime and another release stack; unsigned distribution warnings and update policy need explicit handling |
| Browser-first Web MIDI | No native application install for supported browsers | Browser support/SysEx permissions, file persistence and firmware reconnect behavior require a separate transport implementation and hardware tests |

PyInstaller builds must be produced on each target operating system; it is not a cross-compiler. [Official operating-mode documentation](https://pyinstaller.org/en/stable/operating-mode.html), [usage](https://www.pyinstaller.org/en/stable/usage.html). Web MIDI is not universally available and requires a secure context/permission handling: [MDN Web MIDI](https://developer.mozilla.org/en-US/docs/Web/API/Web_MIDI_API). Desktop signing/update implications: [Electron signing documentation](https://github.com/electron/electron/blob/main/docs/tutorial/code-signing.md).

Future native transport candidate: python-rtmidi 1.5.8, [maintainer documentation](https://spotlightkid.github.io/python-rtmidi/rtmidi.html). Only source was downloaded and selected files inspected; no upstream script was executed, package installed or runtime dependency introduced. Source SHA-256 `7f9ade68b068ae09000ecb562ae9521da3a234361ad5449e83fc734544d004fa`; per-file hashes and MIT/modified-MIT notices are in `artifacts/companion-product/dependency-review/source.json`.

## Verification and remaining gates

`tests/test_companion_product.py` exercises catalog durability, stale revisions, malformed data, PC slot operations, snapshot extraction, stable read-only backup, populated restore ordering, committed prebackup before failure, single-flight jobs, interrupted-job evidence and complete help coverage. `tools/companion_product_smoke.py` uses Chrome with an isolated library, blocking WinMM and mocking device requests. The existing editor smoke continues separately at `/editor`.

Run `python tools/build_companion_help.py --check`, `python tools/dev.py check`, `python tools/dev.py test --config Release`, and both browser smoke scripts. Run artifacts and screenshots retain source identities and exact outcomes. No new physical device conclusion follows from these host tests.

The historical installed qualification remains untouched. It pins some host companion files now intentionally changed. Therefore the old package's runtime preflight fails from this tree; this is an expected release gate, not a reason to overwrite qualification. Next firmware work needs an exact-origin package and fresh reviewed qualification. Public distribution additionally needs removal of private Test01 dependencies and corresponding-source/license review.

Before general availability: qualify real backup/restore/rename/swap on a designated idle unit; add firmware support for individual slot/project deletion and independent project names if wanted; decide project reference remapping; test clean-machine Windows packaging; then qualify CoreMIDI/ALSA on actual macOS/Linux systems. The current launch script remains a workbook development launcher, not an installer.
