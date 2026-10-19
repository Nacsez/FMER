Post-install packaged companion complete backup PASS:128 instrument slots and16 project slots scanned. No restore or sound edits performed. Baseline:1,029 Python tests (12 explicit skips),33 compiled/host suites; final focused tests and42 loader checks also passed. ZIP source snapshot predates final result annotations; runtime and firmware are unchanged.

Final physical result: Amethyst stock015 -> FMER733 PASS through the unmodified packaged companion installer, 16:29:28-16:30:00 UTC. No private data or per-unit package override. Portable ZIP rehearsal PASS, including server exit after last-tab close. Current ZIP: FMER Companion 733.4 Windows.zip. Exact hashes/procedure: evidence/companion-733-4.json. Second-PC retry and audio acceptance remain pending; this supersedes pending-install notes below.

2026-10-17: Latest work: companion733.4, diagnostic934 and corrected updater935. See docs/COMPANION_AMETHYST_733_4.md. Earlier733.3 handoff below is historical.

Final733.3 handoff: `FMER Companion 733.3 Windows.zip`, SHA256 `47f5cb6b1bb7fad99f3b3f246a90d05d4c999db2a9e3444c80ef116d259bf134`. Full baseline passed (1,024 Python tests,12 skips,33 compiled/host suites);14 focused checks validate final shutdown/lease changes. Extracted archive lifecycle rehearsal and browser workflow tests passed. Exact records: evidence/companion-733-3.json. ZIP source snapshot precedes final result annotations; executable/runtime/firmware bytes are unchanged.

## Companion733.3 second-PC repair

The new owner logs show733.2 never reached loader transfer. The32-byte descriptor alone was insufficient; the stock reader also requires the JLFS top directory. New metadata includes160 public format bytes, identical to the successful Citrine package; everything after those bytes through16KiB is FF and never written. The application, updater code and write limits remain unchanged. Firmware install remains a physical retry candidate, not qualified on Amethyst.

Closing the final tab releases an idle server after45s; active jobs retain ownership. Starting an updated build requests shutdown of an older same-library companion, which refuses during a transfer. Renderer subprocesses use CREATE_NO_WINDOW. Connection attachment is polled without opening MIDI; disconnect clears verification and cached catalogs. Stock restore and recovery-mode stock backup are documented as unsupported in the portable UI; recovered ROM patches remain feasible through the existing separate verified-dump tools.

Final733.2 ZIP SHA256: `65a5e56407f682f7dc15e5206bb5cd13977c796eb7505940355807d029d4b094`. Final extracted archive rehearsal: `artifacts/companion-repair-20261017/portable-final/report.json` (PASS). The bundled source snapshot precedes this final checksum/test-result annotation; runtime and firmware are unchanged.

## Companion733.2 repair and expanded installation - 17 October2026

The current handoff is `FMER Companion 733.2 Windows.zip`; prior preview ZIPs remain historical. New updater image: fmer733-compatible-r2.fwsc, SHA2564c0d5ad05925b0f6c53315b4c152e173a1d55368eff7a718851e1ca05ee8d3ca. Synth application remains733. No instrument was touched this pass.

The supplied logs show checksum-valid FM-1_015 identity. Backup/catalog incorrectly required733 and therefore never reached native reads; this was a capability mismatch, not proof of disconnection. Four installation attempts requested logical offsets0,512,1024, received the blank protected-head sentinel at the third request and stopped with zero loader coverage. A fifth attempt timed out during discovery. Cable differences did not change this recorded failure pattern. The shipped package had discarded a required public descriptor along with the private boot head. Restoring the32-byte public descriptor removes that defect; the next physical run must verify stock-worker acceptance.

Installation now admits different application bytes rather than one original firmware digest. It still requires the supported layout/calibration: encrypted spans[4,32),[36,0x120),[0x8DE3C,0x8F000) relative to app region0x4000 hash to98d079265f7f5b8e9ab5421816ba43985c6c23b55dff6ccbbc84eaf0daa86b8a. Thus only code and its two CRC pairs can differ; all copied metadata/calibration is proven identical. The known device key/JEDEC remain checked. One complete staged-loader match at0xE7F00(stock) or0xE4F00(FMER) is required; two-byte CRC invalidation only, no record-sector erase, no native-journal writes. Exact original digest is retained for abort safety. The new updater identifies as ota-FM-1_933; old733 updaters do not inherit recovery admission.

Progress covers every device job, with per-slot counts for complete backups/restores and per-phase byte counts for installation. Other editor/device controls and Quit are locked during work. Reopening the same browser session continues monitoring; browser communication loss does not cancel or restart the write. Completion/failure remains visible. Connection checking identifies stock/other firmware before selecting available commands; stock native backup is honestly unavailable. Primary UI no longer names bench units or internal qualification stages.

Tests and remaining gates: see TEST_REPORT.md. Second-PC launch and Amethyst physical installation remain owner tests; universal arbitrary firmware/layout compatibility and dead-boot recovery are not claimed. Next run: extract the new folder, close the old companion, Check connection, inspect included firmware, install, then export the operation record if anything stops. Preserve saves with a complete native backup when reinstalling existing733.

## MIDI guide documentation edition - 16 October2026

The separately named `FMER Companion 733 MIDI Guide Preview.zip` refreshes offline Help without changing firmware, runtime control mappings or installer admission. It adds explicit no-Learn/NRPN status,198 fixed-ID/CC-access rows, external-controller and DAW setup, exact USB SysEx examples and save/context limitations. Original preview archives and their evidence below remain unchanged. This edition retains the same exact-stock first-install restriction; it is not the broader installer discussed subsequently. New package hashes and test evidence are in `evidence/midi-help-733.json` and TEST_REPORT.md.

# FMER Companion 733: Windows deployment review

16 October 2026. Scope: offline companion/help audit, portable Windows package,
and an exact-stock first-install candidate. No instrument was accessed or flashed.
Malachite and Citrine retain their installed 733 firmware and saved data.

## Final delivered package

The workbook-root ZIP is 26,864,980 bytes. SHA-256:

`f95c7499d2156dfc2cc98f6e73464d087f802038d5025608ef997934a4468506`

The exact delivered ZIP passed the full extraction/startup/import/audio/help/
firmware-inspection/persistence rehearsal:
`artifacts/companion-release-733/portable-delivery/report.json`.
Machine-readable delivery identity:
`evidence/companion-733-portable-2026-10-16.json`.
The ZIP's source snapshot contains the review immediately before this final
checksum annotation; executable, runtime, firmware and help hashes are unchanged.

## Deliverable

Extract **FMER Companion 733 Windows Preview.zip** from the workbook base folder.
Double-click **FMER Companion.exe** inside the extracted folder. Keep the entire
folder together. The browser opens a local `127.0.0.1` application; no account,
hosted page, internet connection or separately installed Python is needed.

Windows 10/11 x64 on Intel/AMD is the target. The launcher uses Windows .NET 4
support and the system browser. This unsigned private preview may show Windows
reputation warnings. A different Windows computer is the next qualification step;
the local extraction rehearsal is not a substitute for it.

| Included | Purpose |
|---|---|
| FMER Companion.exe | One-click local launcher; no elevated install or machine changes |
| Embedded Python 3.13.16 and runtime DLLs | Isolated backend and Windows MIDI transport |
| Statically linked host renderer | Audition original FM/VA sounds locally |
| Libraries | 64 original FMER instruments as merge-import catalog; 128-slot DEFAULT/USER PC-bank backup |
| Help.html and host/help | Offline index, 27 illustrated articles/references, search, 198 parameter definitions, 45 physical menu diagrams |
| firmware/releases | Hash-pinned stock V15 to FMER 733 preview package and admission catalog |
| notices and Corresponding Source.zip | Retained dependency notices, provenance and source snapshot; public release review remains open |
| manifest.json | SHA-256 of every distributed file; ZIP checksum is alongside the download |

The library profile remains **FMER Default 726.1**, the actual current sound recipe
version. It is not a stale firmware label. There are 32 FM and 32 VA defaults;
USER begins with independent copies. Stock/proprietary patch banks, private ROM
dumps and the owner's projects are excluded. Existing user data is never replaced
by these packaged defaults automatically.

## Current companion behavior

Library supports instruments/projects, collections, tags, favorites, search,
multi-selection, rename, duplicate, move between collections, Trash/recovery,
permanent Trash clearing, one-transaction Undo, export, merge import and explicit
replacement restore. PC banks add destination-based copy/swap, USER-to-empty move,
USER slot deletion and separate default/user/clear reset scopes.

The editor retains exact numeric values alongside visual controls, the 32 FM
algorithm diagrams, VA controls, shared FX order, modulation recipes, local PCM
audition and native11 song preservation. Device operations are explicit and
serialized: read/load/send instruments and projects, rename/copy/swap sounds,
save projects, reset banks, capture diagnostics, download battery history, and
back up/restore all musical data. Existing limitations remain visible: one FM-1
connected at a time, no individual hardware-slot deletion, no independent hardware
project titles, and no automatic deployment/remapping of project sound references.

Data and operation evidence live in `%LOCALAPPDATA%\FMER\Companion`, separate
from the program folder. Use **Quit companion** to release MIDI and stop the
local server before replacing the executable folder or returning to a DAW.
Export Library and PC banks separately when moving to another computer.

## Help audit and pictures

The handbook uses 80 actual firmware-renderer captures, 45 original physical
control-map SVGs and seven actual companion browser captures. Figures are labeled
as illustrative renderer/browser states, not hardware photographs or connection
proof. Every topic has linked pictures, with alt text and captions. All 32 FM
algorithms are shown. The panel reference covers every documented page; the
parameter reference includes all 198 canonical controls and their ranges.

Corrections include HOME cutoff/resonance/reverb/delay order; FM left/right key
scaling; locked Voices in 4TRK/glide; new chorus/phaser recipe access; SINGLE
sequencing/song continuity; five-trace fullscreen; USB return-to-PC procedure;
and portable deployment instructions. Encoding damage in older prose is repaired.

One remaining panel limitation is explicit: Clean/Warm delay selection is in the
companion Editor and saved FX profile, but has no dedicated 733 panel shortcut
after recipe selection replaced the earlier mapping. No firmware behavior was
invented to conceal this. Bluetooth pairing/group sync remains deferred.

## Firmware admission and limits

The included profile is `stock-v15-to-733-preview1`, target `FM-1_733`, generic
USB product `FMER`, with origin identity `FM-1_015`. The complete original encrypted
application/calibration region must hash to:

`8c1d13a5934eb3c70a5fec644577618a31b2a96c8748a7b692c506a86505dbb1`

This is the identical stock region measured on the two previously examined units.
It is **not** evidence that every unit with a V15 screen label is identical.
Amethyst's label is owner-reported and believed V15; its bytes have not been read.

The companion validates bundled package bytes, source pins, loader bytes,
application identity and boundaries before opening MIDI. The device stages a
loader, which checks its chip/layout, unique staging record and original app
fingerprint before the host begins application writing. The stock staging record
must be at `0xE7F00`. The loader restricts application writes to
`0x4000..0x93000` and the proven record's two CRC bytes. The package's first
16 KiB is an all-FF sentinel; the real protected boot head is never included or
written. Calibration/identity preservation is checked during construction and
enforced by the exact original-region admission.

This package is not an upgrade for installed FMER or arbitrary stock/custom
variants. A mismatched origin can remain in update mode with application writing
refused. The UI provides no blind resume, rollback or stock-ROM recovery image.
Do not use the .fwsc as an unrestricted raw-chip image. Its checksums establish
integrity, not an independent signing authority.

Stock patch export/translation is unavailable in this installer. Companion
backups require FMER 733 and contain musical data, not a boot/firmware dump.
The first FMER installation initializes its own banks from the original defaults.

## Evidence and remaining gates

| Check | State and scope |
|---|---|
| Generic 733 target build | PASS; application 213,252 bytes; compiled, not executed on Amethyst |
| Independent stock-profile loader | PASS, 35 checks; protected regions, wrong records/chips, CRC corruption, missing finish and interrupted-write behavior |
| Release admission regressions | PASS, seven new tests including image coverage and absence of private-reference lookups |
| Extracted Windows deployment | PASS; minimal PATH, bundled runtime, startup, fresh banks, library import, host PCM, all help images, inspection and persistent relaunch |
| Companion real-browser product flow | PASS; catalog, bank editing, mock-only device jobs, firmware refusal, offline search, traversal/Origin guards and mobile layouts |
| Full current baseline | PASS: 1,019 Python tests (12 explicit skips), 20 corpus tests and 33 compiled/host CTest suites |
| Clean Windows 10/11 computer | PENDING owner test |
| Amethyst first installation | PENDING owner test; no hardware success claimed |
| Public release | PENDING license/source/calibration redistribution review, hardware recovery and existing audio/endurance gates |

Final full run: `artifacts/runs/20261016T061619.033435Z-test-00fb26cb/summary.json`.
Both browser suites passed; editor evidence is under
`artifacts/companion-browser/20261016T061629/report.json`. A focused rerun of all
17 product/help tests also passed after the final menu-reference corrections.
The host PE imports only KERNEL32; the launcher imports mscoree (Windows .NET).
Dependency evidence: `artifacts/companion-release-733/pe-dependencies.json`.

Primary artifacts:

- `artifacts/companion-release-733/target-reviewed/report.json`
- `artifacts/companion-release-733/package-final/report.json`
- `artifacts/companion-release-733/package-final/loader-tests.json`
- `artifacts/companion-release-733/portable-test2/report.json` (initial extracted rehearsal)
- `artifacts/companion-product/20261016T061331/report.json`

The first full-test attempt is retained under
`artifacts/runs/20261016T060949.573141Z-test-5607df53/`: a text-only help-link
assertion rejected image links, and CP1252 console output then failed while
printing that large assertion. Image targets now receive filesystem checks;
child Python diagnostics are UTF-8 and console encoding failures are escaped.
Earlier loader-test failure was caused by initializing the simulated device
head from the new all-FF package sentinel. The test now receives the existing
device head separately, matching the real loader's read-only chip-key source.
These failures were diagnosed and corrected; none involved a physical unit.

## Amethyst test procedure

1. Copy the ZIP and checksum to the second PC; extract **all** files.
2. Double-click the EXE. Before connecting the instrument, audition an FM and VA
   preset, open Help, import `Libraries/FMER Default Library.json`, and restart
   the app to confirm persistence.
3. Connect only Amethyst, powered on, using its USB data cable. Close music apps
   using MIDI. Open Firmware and inspect the included package.
4. Review its exact-origin limitation and confirm installation. Keep power and
   USB connected. If it fails, export the operation record and retain the full
   operations directory; do not try unrelated firmware or a blind retry.
5. On success, confirm the 733 screen, play physical notes, switch FM/VA, test
   SINGLE/4TRK, and check saved project recall after a normal restart.
6. Read its catalog and make a complete FMER musical-data backup. Try a named
   test sound in an expendable slot, verify readback, then restore that slot.
7. Report the installer result and share the operation logs for reconciliation.

The next pass should qualify that real installation and backup/restore workflow
before expanding packaging to an installer or other platforms. Firmware audio
reserve, prolonged USB/audio operation and physical recovery remain separate
release gates; a successful local executable test does not close them.
