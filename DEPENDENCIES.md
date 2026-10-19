## 2026-10-19 ? Source-built runtime734-r2

Newlib2.2.0 and LLVM compiler-rt4.0.1:49 unmodified source units plus local
headers/notices, pinned in third_party/runtime/PROVENANCE.json. LLVM MIT option;
Newlib per-file/default notices retained. No upstream build scripts ran. HTTPS
archive hashes are verified; the retained LLVM signature was not verified.
Additional llvm-ar executable pin is in tools/source_runtime.py. Vendor runtime
archives are neither needed nor linked by the default build.

Only383-byte configuration and2,873-byte EQ blocks from the already-pinned
M-VAVE public OriginalV15 resource are included under its Apache-2.0 grant.
Their decoded bytes match the qualified layout; the complete publisher notices
and provenance accompany them in third_party/fm1_resources. No vendor engine,
stock application, boot image or private dump is added.
See docs/release/RUNTIME_REVIEW_734.md.

## 2026-10-19 — Original FMER splash license

Owner-supplied FMER SPLASH.png is now explicitly GPL-3.0-only, including its
editable source, by owner confirmation. The PNG remains byte-identical; the
source packages include it with the generator and source notice. See
[artwork provenance](docs/release/ARTWORK.md). No external dependency changed.

2026-10-19: Bluetooth release review reverified all19 retained SDK/runtime files at pin5fa84a9b2f723a5e9337ad79dc2ad741fc98fe2d. Three selected bitcode objects were compiled and partially linked only as an offline dependency audit. No vendor runtime was executed, installed or added to production; no new dependency or license grant is inferred. Official documentation and Baud101 author documentation were refreshed as references. Live SDK repository retrieval was unavailable; the retained pin is not claimed as latest. See docs/BLUETOOTH_RELEASE_DECISION_2026-10-19.md.

2026-10-18: Original FMER firmware, Companion and original default instruments are GPL-3.0-only by owner decision. Root LICENSE/LICENSING.md/NOTICE record scope; no third-party dependency is relicensed. Felucca provides startup/HAL/I/O, SLOOP the updater foundation, and Apache-2.0 MSFA the FM engine. Portable source inclusion now uses the exact reviewed Felucca files plus required tree metadata. Final toolchain/runtime/asset distribution review remains separate. Earlier dated deferred-decision records below remain historical.

2026-10-17: No new external runtime dependencies. Stock restore uses existing qualified935 loader and validates a user-supplied stock application; no proprietary stock bytes enter the companion or git. License decision deferred; no blanket relicense.

2026-10-17: 733.4 adds no external dependencies. New fixed-window metadata readback and trailer-preserving updater are original local code; pinned Jieli toolchain and existing runtime remain in use.

## Companion733.3

No added dependencies. The160-byte top-level format directory is reconstructed from reviewed descriptor fields and compared to previously captured successful-install evidence. It contains no boot executable, key blob or private patch payload. Existing bundled runtime/source notices remain.

## 2026-10-17 - Companion733.2 repair

No new dependency was acquired. The distributed32-byte descriptor is generated from the existing reviewed FLASH_HDR constant and CRC/cipher code, matching the inspected stock descriptor without carrying its SPL, key blob or unit identity. Portable layout-admission code is original FMER source. Existing Python, MSFA and loader provenance/licenses remain unchanged.

## Portable Windows runtime - 2026-10-16

Python3.13.16 official Windows x64 embeddable ZIP, verified against the official
Windows release manifest; SHA256
589dc1e9d02549ca5f680710307ff9b77f6e3ffc4aa3efccd7fa54eeeafac94b.
Per-file pins and acquisition URLs: evidence/python-portable-runtime.json.
PSF and incorporated component notices are retained in LICENSE.txt. Binaries
are unchanged; only the packaged python313._pth adds ../tools and keeps site
import disabled. No upstream installer/script or pip dependency was executed.
The runtime includes its DLL dependencies from the official distribution.
[Python embedded distribution documentation](https://docs.python.org/3/using/windows.html#the-embeddable-package).

The C# launcher uses built-in Windows .NET4 support. Host C++ remains statically
linked to its MSVC runtime. This does not bundle Visual Studio or the Jieli
compiler. Apache2 MSFA and GPL3 loader notices, provenance and the relevant
source snapshot accompany the private preview. Public distribution is not
approved merely by packaging these notices.

## 2026-10-16 — radio runtime research only

Six additional files were acquired at the already-pinned official Jieli SDK
revision5fa84a9b2f723a5e9337ad79dc2ad741fc98fe2d. Git object IDs and SHA256 are
recorded in evidence/ble-runtime-research-2026-10-16.json. Twelve archive members
were inspected as LLVM IR with the pinned compiler. Payloads remain ignored
research artifacts; none is linked into733. No new production dependency or
license grant is inferred from archive availability. FMER's modulation recipes,
native11 schema and LED PWM helper are original project code.

## Bluetooth SDK refresh, research only — 2026-10-15

Official AC79 SDK pin5fa84a9b2f723a5e9337ad79dc2ad741fc98fe2d,
AC79NN_SDK_V1.2.14_2026-10-13. Thirteen files (including two LLVM archives)
match pinned Git blobs and SHA256; metadata is retained in
evidence/ble-sdk-research-2026-10-15.json. Raw files remain ignored under
artifacts/development-732/sdk. Sixteen members were inspected as LLVM IR;
three were compiled for an explicitly failing runtime-dependency link probe.
No acquired target program or upstream build script was executed.

Root license: Apache-2.0; per-file vendor notices retained. Complete archive
dependency/provenance and redistribution review is required before integration.
No new vendor runtime is included in FMER. core/ble_midi.* is original
GPL-3.0-only code, tested against protocol behavior. Existing toolchain pins,
stock payload privacy and the delivered corpus are unchanged.
Primary references and evidence boundaries: docs/BLUETOOTH_732.md.

## USB host register evidence ? 2026-10-15

Reviewed official AC79 SDK commit d179b4484759423312073f5fbb232501aa491047:
USB host/control/bulk sources, USB/OTG headers and USB objects from cpu.a.
Each retrieved file is verified against the pinned Git blob and SHA256 in
artifacts/development-731/usb-research/manifest.json. The previously pinned
compiler disassembled the object evidence to LLVM IR. This is research-only
material under ignored artifacts; no downloaded runtime, build script, RTOS or
vendor library was executed/integrated into the firmware. New usb_link.h and
usb_link_board.h are original GPL-3.0-only code using the existing qualified HAL.
Read-only Windows identity queries use documented WinMM and Configuration
Manager APIs. Details and primary links: docs/USB_DIRECT_LINK.md.

## Citrine private acquisition evidence - 2026-10-15

Verified Citrine V15 double dump is retained privately, SHA256
4c4cd71657c9f5665adb4561ae22aa47f219d46cf28a836eb07fcf191f4bd3a7.
Both128-voice regions, normalized codec exports,128 host WAV previews and the
additive companion import have hashed evidence under private/Citrine.
No new external dependency or public patch-bank license is introduced.
The current locally pinned SDK/toolchain builds the Citrine730 USB identity;
its separate loader profile uses the stock E7F00 record address. Source and
binary provenance for package/loader/harness live under artifacts/citrine-acquisition.

## Citrine stock acquisition tools - 2026-10-15

No new runtime dependency or upstream program was integrated. Stock ROM entry
uses the already pinned Transporter a632d923 protocol documentation
(SHA256 c5b9b25136383c5684451bda63eaa737ffe2d10d4ea1e63d62908316124813bf).
Readback retains the existing pinned private vendor RAM bootstrap and its
documented provenance limits. Original extraction code uses the established
DX7 format and checks conversions with the existing compiled FMER codec.
Private device voices and decoded firmware remain ignored, never source assets.
See docs/CITRINE_STOCK_ACQUISITION.md.

## 730 arrangement/visual pass - no new runtime dependencies

Song scheduler, compact persistence and track visualizers are original repository changes. Existing pinned compiler, HAL and MSFA provenance applies. No upstream payload, patch bank, typeface or radio stack was acquired or integrated. Delivered corpus bytes remain unchanged.

## 729 research references; no new runtime dependency - 2026-10-14

MIDI Association CC/Bank Select and BLE MIDI references, and the Little Sound Dj8.3.1 manual, informed control and arrangement designs. No upstream code, proprietary patch bank, audio sample or radio runtime was integrated. Exact links and evidence scopes: [MIDI](docs/MIDI_729.md), [song](docs/SONG_MODE_DESIGN.md), [network](docs/MIDI_NETWORK_PLAN.md). Existing compiler/HAL/MSFA provenance and portable-runtime servicing/distribution review still apply. Delivered research corpus remains unchanged.

## 728 Bluetooth SDK review — no integrated dependency

Official Jieli AC79 SDK commit d179b4484759423312073f5fbb232501aa491047: repository tree and five source/header files reviewed and hash-pinned under artifacts/development-728/ble-sdk-review. No radio archives, source or runtime incorporated into FMER. Licensing/redistribution, ABI, scheduler services, interrupts and resource allocation require a separate integration audit. [Evidence and plan](docs/BLUETOOTH_728.md).

## 727 cleanup candidate - 2026-10-14

No added dependency, imported sample/patch bank or radio stack. Existing pinned compiler/HAL provenance applies. Bluetooth multi-peer references are informational; no capability qualification. See [727 report](docs/DEVELOPMENT_727.md) and [future flavors](docs/FLAVORS.md).

## 726 checkpoint - 2026-10-14 UTC

726 adds no acquired dependency or proprietary bank. Noise PRNG, compact glyphs and percussion settings are original local changes. Existing toolchain, MSFA, HAL and runtime provenance remains applicable. Bluetooth research is informational only; no radio stack was imported. Windows portable runtime servicing/licensing/public distribution review remains open.

## 725 offline release preparation - 2026-10-13

725 is compiled and independently audited but **not installed**: the owner disconnected Test01, which remains724. Global page1 now exposes SINGLE/4TRK; editing VOICES exits mono tracks into the single-instrument allocator. Four physical-source chord notes and return to four tracks have host regression coverage. All128 instruments, projects0/13/14 and live state were backed up before disconnect;132-record C/Python migration passes. No new device write or hardware qualification is claimed.

Companion725 has current protocol labels, centralized device workflows, an explicit playing-mode selector, offline Help and a portable Windows EXE rehearsal with per-user persistence and Quit. General factory flashing, public redistribution, clean-machine testing, runtime servicing, USB reliability, optical acceptance and the prior combined-load timing reserve failure remain open. [Development and release-readiness report](docs/DEVELOPMENT_725.md).

## 724 installed repair ? 2026-10-12

No acquired code, font, sound bank or runtime dependency; original local preview routing and existing UI renderer. 724 release3 is installed. All128 saved instruments and projects0/13/14 match pre-update records; working state, MIDI and octave are restored. No bank reset. Silent keys were caused by selecting a muted mixer track, not a missing physical-key scan:128 local note edges were recorded. Stopped physical keys and arps now audition through stored mute/solo while preserving levels, FX flags, Local Off and the saved mix. Playback/recording restores normal mixer gating. Incoming raw MIDI retains mixer gating. Battery percentage is right-aligned in the top-right header; its provisional calibration is unchanged.

Full regression:963 Python tests (12 expected skips),31 compiled suites, browser smoke,132-record C/Python codec verification, independent package/loader/resource/RAM audits. Connected USB PCM verifies stopped arp audio, running mute and external-note mute, followed by notes/MIDI/multitrack regression and all eight combined-load cases. Combined peak 2193 us;2176 us reserve gate FAILED. The prior7232205us failure remains open evidence of variability. Physical keyboard operation/optical placement still need owner acceptance. Program payload+904B, static RAM+16B; startup arena/workspace unchanged.

[724 report](docs/DEVELOPMENT_724.md) and [exact evidence](artifacts/development-724/report.json).

## 723 dependency review ? 2026-10-12

No new runtime dependency, sound bank, font or upstream code. The original local battery curve uses Test01 ADC evidence and existing audited stock bar thresholds as explicitly provisional priors. TI SLUAAA1 provides primary-source background on voltage-based state-of-charge characterization; no TI implementation or hardware capability is imported. Existing pinned compiler, HAL and loader write-policy code remain in use. [723 rationale](docs/DEVELOPMENT_723.md).

## 722 development checkpoint ? 2026-10-12 UTC

722 adds no acquired dependency. Original local FDN gets two length/damping/modulation profiles. Research references: TI battery gauge overview and voltage/charge-state guidance, EarLevel TPT/state-variable filter explanation. No third-party code or sound/font payload integrated. Existing toolchain used without machine configuration changes.

## Companion product research ? 2026-10-11

No new runtime dependency integrated. Inspected python-rtmidi1.5.8 source only for future CoreMIDI/ALSA support; no upstream build script executed and no installation. Source/per-file pins and MIT/modified-MIT licenses retained at artifacts/companion-product/dependency-review/source.json. Existing Python stdlib, shared C++ host and development Chrome/Playwright support this pass. PyInstaller/Web MIDI/Electron options are research, not installed components. See [primary sources and packaging comparison](docs/COMPANION_PRODUCT.md).

## 721 final evidence -- 2026-10-11

721 adds no acquired dependency, sound bank or font. Existing pinned USB implementation is unchanged; new local read-only counters expose its stream state. Windows capture uses standard WinMM through Python ctypes; objective MP3 decoding used the existing Chrome/WebAudio runtime. Original corpus/dependency locks remain unchanged. See [721 review](artifacts/development-721/review.html).

# Dependencies and acquisition status

<!-- FMER720-HANDOFF-BEGIN -->
## 720 release6 installed test prototype - 2026-10-11 UTC

720 adds no upstream code, sound bank, font or other dependency. Default719.1 recipes and existing dependency pins/licenses remain unchanged. Native-v5 tools, layout3 journal code, panel changes, quiet native-load ownership and regressions are local work. The current 257 installed source pins are retained in `artifacts/development-720/installed-qualification.json`, including the explicit host recorder correction and bench sources. The historical `artifacts/development-720/preflash-release6-qualification.json` remains immutable. The recorder overlay records both original and updated hashes; firmware/package hashes are unchanged. Independent release6 loader/package/source review is `artifacts/development-720/package-audit-release6.json`. Historical release4/release5 audits and exact-origin routes remain preserved.

[720 review and controls](artifacts/development-720/review.html) | [Source-pinned evidence](artifacts/development-720/report.json). Earlier dated entries retain their historical scope.

<!-- FMER720-HANDOFF-END -->

## 718 provenance — 2026-10-10 UTC

No new runtime dependency or imported sound bank. `encoder_model.h` is local; `build_fm1_candidate.py` verifies upstream input source SHA and patches only staged `fm1__frame`. Final target report and resource review pin original/staged input and verify unchanged surrounding code. Primary Yamaha/Plogue research citations and original recipe experiments are recorded in `artifacts/development-718/research.txt`. Delivered research corpus remains immutable.


## 717 dependency review — 2026-10-10 UTC

No new runtime dependency, sound bank, font, visual asset or upstream code imported. New visuals are native strip-renderer code. Novation's official Circuit Tracks guide informed clip/scene workflow research only; source linked in `artifacts/development-717/sequencer-proposal.html`. Corpus unchanged. Existing loader origin pins advanced from qualified716 to717 and were independently audited.


## 715 asset provenance - 2026-10-09 UTC

Owner-supplied `FMER SPLASH.png` SHA256 `73697123943ac81da6d294466c0f0d0c1bbee4bbf4c4b2d10d096414766b96f8` is retained unchanged and packed for the target by tools/generate_fm1_visuals.py. The FMER segmented wordmark and715.1 instrument recipes are original project work. Routing is derived from already pinned MSFA source, whose existing provenance/license remains unchanged. Pillow is used only by the existing local asset-generation/test environment; no new firmware runtime dependency or imported font/sample/patch library.

## 714 FX pass - 2026-10-08 UTC

No new external code, binary DSP library, weights, font or dependency was imported. Simper TPT-SVF and published FDN/delay research informed original local implementations; primary references and alternative algorithms are recorded in [the714 report](docs/FM1_714_FX.md#research-and-evidence-classification). Existing MSFA and pinned target toolchain provenance remains. Builds required the same build-only compiler escalation; no machine settings changed. The loader binary differs only in exact installed-origin hash and product identity.

## 711 memory pass - 2026-10-08 UTC

No dependency, upstream source, license or toolchain change. The same pinned pi32 compiler built711; its sandbox argument-access failure was resolved by a build-only escalation. The independent loader audit verifies only identity/origin changes relative to710 and preserves calibration/protected bytes. New local `tools/fx_audit.cpp` is an offline measurement utility, not an external DSP dependency. [711 resource and regression report](docs/FM1_711.md).

## 710 pass — 2026-10-08 UTC

No runtime dependency or third-party patch/sample content was added. MIDI Association, Ableton and Microsoft primary documentation informed the original implementation and workflow. [References and interpretations](docs/research/2026-10-08-midi-integration.md). Existing Felucca USB/UART sources are hash-checked and patched only in the build staging tree; the acquired source snapshot is unchanged. The audited loader changes are the710 identity and exact installed709-origin digest. Existing license/distribution obligations remain.

2026-10-07 companion/default-bank pass: no runtime dependency was added. The local app uses Python's standard library and the existing C++ core; browser checks use the already-installed Playwright/Chrome. Yamaha educational pages informed original programming principles; no vendor patch bank or third-party audio sample was acquired or incorporated. [Primary references and interpretation](docs/research/2026-10-07-default-sound-design.md). Installed-device status is tracked in [TEST_REPORT.md](TEST_REPORT.md), which supersedes historical acquisition notes below.

Updated: 2026-10-05. The C++ core integrates selected original MSFA source; target platform/package work is now active. A separate Windows WinMM identity query measured FMER Test01 reporting `FM-1_015`; no flash has occurred. Python core tooling uses only the standard library. Optional browser smoke uses the already installed Playwright/Chrome. Current community pins and licensing distinctions are in [the dated refresh](docs/research/2026-10-05-community-refresh.md) and [its evidence inventory](evidence/community-refresh.json).

## Local build tools

Python 3.11.7 and Git 2.42.0.windows.1 were found. Visual Studio Community 2022 17.14 and MSVC 14.44.35207 are installed. The build driver discovers its bundled CMake; exact executable/compiler versions are recorded in run artifacts. Reproduction requires Python 3.10+, CMake compatible with the root minimum, and a C++17 host compiler. These are observed tools, not a bundled or bit-for-bit reproducible toolchain image. The pi32v2 compiler is now privately extracted in the workspace for compile/link-only work; no vendor installer or global setup was run. Exact inventory and limitations are in [target-toolchain.json](evidence/target-toolchain.json).

## Source inventory

| Source | Pin / status | Rights recorded in handoff | Intended use |
|---|---|---|---|
| Research delivery | [corpus.lock.json](evidence/corpus.lock.json); original 2026-09-29 bytes | Original research for owner's use; retained third-party terms | Design/evidence and offline helper seed |
| ip2k research (S12–S16, S40, S44) | `93c80a5769ba8a6e72442d1470ae056cf6a413a5`; three complete docs plus license included | MIT with retained notice | Evidence; errata and later findings take precedence for conclusions |
| Benny editor (S18–S20 / C05) | Current `4c4c336c835e66e6a1257626b082d34f1e2f42d8`; selected identity/preset codec source, fixtures, research and license retained; corpus pin unchanged | MIT original code; assets/banks require separate checks | Audited protocol reference; no editor runtime or preset banks integrated |
| AL-255 main (S08–S11 / C07) | `ec832f281ca165a7d5e0722985f3acb1465046d5`; selected protocol/tool/license source retained | WTFPL original material, not vendor payload | Protocol/ABI research |
| AL-255 experimental branch (S10) | Unpinned, not acquired | Mixed dependencies; per-file audit | Investigation only |
| Original MSFA (S26) | `f67d41d313b7dc85f6fb99e79e515cc9d208cfff`; selected engine and unpacker vendored | Apache-2.0; COPYING and per-file notices retained | Integrated FM reference; local changes and hashes in evidence/msfa-source.json |
| Baud FM-1+VA (S03 / C09) | Current 093 and beta 094, publisher dated 2026-09-30; creator-page snapshots retained, payloads not downloaded by survey | Complete reusable source not located in inspected current pages; no inferred license grant | Functional/protocol reference |
| Felucca (C01) | `20c275e39f75fa820978032efaceddfc5283c8cb`, v1.0.1; 206 source/asset files in ignored audited acquisition cache | GPL-3.0-only platform; Apache/MIT engine parts, OFL fonts and CC0/MIT/own-GPL assets separately identified | Leading platform/HAL/loader candidate; adaptation and package review underway, no target-run qualification |
| SLOOP / X0X (C02/C03) | Pinned current revisions and selected sources documented in community-refresh.json | GPL-3.0-only code; pinned fork asset/permission notices differ | Performance workflows, update-path comparison and overload tests; not independent board evidence |
| FM-1 Transporter (C04) | `a632d923203170e3a08565f4056dbb3fd3d65ca5`; README/license/protocol/author logs retained | MIT project; external loader and hardware dependencies require separate review | External recovery candidate; no FMER physical test |
| AC79/WL82 SDK (S29–S30) | Narrow platform/archive/package prerequisites under current target audit | Source repository license does not settle closed libraries/compiler terms | Narrow HAL/build inputs only after exact-file audit |

Synth_Dexed, Dexed, MIDIpal, OpenPatches and recovery tools remain leads in the corpus's 18-entry `data/codebases.json`, not approved dependencies. The original setup deferred public licensing; the 18 October 2026 decision in LICENSING.md now selects GPL-3.0-only for original FMER software and defaults without altering included notices.

## Acquisition procedure

1. Record origin, exact commit, files needed and the question acquisition will answer.
2. Acquire into `third_party/acquired/` or another explicit workspace-local staging directory. Review all build scripts before execution.
3. Record file hashes, license/NOTICE, transitive dependencies, binary blobs and omitted assets. A repository pin without downloaded files is not an installed dependency.
4. Integrate only reviewed files with notices; update this inventory, decisions, tests and build instructions.

The corpus `tools/fetch_sources.py` is a text-only acquisition helper with a 23-entry pinned plan. Its default is a dry run. A later explicit `--fetch --output third_party/acquired/documents` invocation from the root can retrieve documentation, but cannot supply MSFA, the editor runtime, or a firmware base. The present checks run only its dry mode. Download success must be reported separately from plan validation.

MSFA was separately acquired from the pinned original repository over HTTPS on 2026-10-02. Only reviewed engine/unpacker source and licensing were included; upstream build scripts, Android application, presets and binaries were excluded. Our CMake enumerates selected source files explicitly. See [SYNTH_ENGINE.md](docs/SYNTH_ENGINE.md) and the vendor README for adaptation details and remaining limitations.

Prototype 0.3 adds no third-party dependency. The mono effect chain, arp extensions, pattern transport, companion persistence and browser controls are original FMER code. Python HTTP/filesystem/hash tooling remains standard library. Browser smoke still uses the already installed optional Playwright/Chrome. Documentation links to the current primary manual as behavioral evidence; no released firmware or preset bank was downloaded for this pass.

Prototype 0.4 adds no runtime dependency. CADER's locally inspected palette and design conventions are recorded with source hashes in [DESIGN.md](docs/DESIGN.md); no CADER code, artwork or font is included. Native browser controls keep the existing session/library formats. Passive device inventory uses Python's standard library and Windows' installed PowerShell/Get-PnpDevice; offline tests mock the OS query.

The initial 2026-10-05 target source/compiler audit is in [HARDWARE_PLAN.md](docs/HARDWARE_PLAN.md). Its candidate URLs and upstream build prerequisites began as investigation evidence. Subsequent extraction and pinned source acquisition below advance that status; a compiled target is still distinct from a qualified board/package. Record exact payload hashes and separate source/tool/library terms, and exclude automatic download/flash steps from compile-only workflows.

The official Windows JieLi 2.5.2 installer was subsequently downloaded into ignored `third_party/acquired/toolchain-review/20261005T205558.909611Z-9fcedabb/`: 52,840,808 bytes, SHA-256 `1ec78e3315a5987d4e82ecd002536c84240e5c832b1875beff7ce55450124ee5`, valid vendor Authenticode observation. This is an acquisition for review, not an adopted runtime/build dependency. Existing extractors expose only the outer PE container; internal licensing, setup actions and compiler payload remain unreviewed. No installer/compiler execution or installation occurred. The hardware plan links the acquisition and inspection record.

Later extraction supersedes that initial extractor limit: pinned **innoextract 1.9** exposed 1,927 files (284,868,547 bytes) in `third_party/acquired/toolchain-extraction/20261005T213625.124017Z-7721e1b6/`. The installer remained unexecuted; setup, PATH, driver/debug and download helpers were not run. Reviewed executable/header hashes, extractor origin/signature scope and compile flags are recorded in [target-toolchain.json](evidence/target-toolchain.json). The JieLi payload contains clang 4.0.1 and pi32v2 r3 tools. Complete vendor redistribution terms remain unresolved, so the payload stays in private ignored acquisition storage.

The target C++ header probe separately uses LLVM **libc++ 4.0.1**, archive SHA-256 `520a1171f272c9ff82f324d5d89accadcec9bc9f3c78de11f5575cdb99accc4c`, with its MIT option selected and upstream license retained. Its detached signature is retained but not verified; HTTPS origin and exact archive/file hashes are recorded without implying a signature pass. These are target build inputs, not a change to the host runtime.

The full Felucca source/asset acquisition is pinned in `third_party/acquired/fm1-target-review/community/felucca-full-manifest.json`; no generated firmware or vendor tool binary was included in that source acquisition. Selected additional community and protocol references are hashed in `evidence/community-refresh.json` and `artifacts/protocol-research/source-inventory.json`. Source review and native build work do not authorize redistributing proprietary firmware, unknown banks, unit dumps or vendor toolchains. Felucca-derived distribution must preserve its GPL obligations and the separate component notices; current Felucca licensing must not be assumed to replace older SLOOP asset notices automatically.



706 lighting uses the already pinned Felucca HAL matrix and scan driver. The
original portable FMER model records the audited factual map and the separate
green PLAY coordinate from `firmware/src/ui_input.c`. No additional upstream
UI, engine, font, binary, build script or dependency was adopted. Existing
license/provenance and immutable corpus pins remain unchanged.


## 709 provenance update — 2026-10-08 UTC

No new upstream synth, preset bank, font or audio sample was adopted. Original709.1 recipes and the compact bank implementation are workspace source. The existing pinned loader differs from708 only in its expected application identity and original-app digest; independent binary comparison and33 unchanged loader tests passed. PROVENANCE.json and exact package/source qualification bind these changes. Proprietary calibration/template bytes and device backups remain local artifacts. Existing license obligations and unresolved distribution terms are unchanged.

[709 guide](docs/FM1_709.md) contains current scope and evidence.
