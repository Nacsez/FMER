# FMER FM-1 board candidate

This directory is target bring-up work, not a qualified installable release.
The C adapter uses the same FMER Synth/MSFA and Effects sources as the host.
Installed bench build 707 includes contextual FM/VA and effects editing, bounded
sequence/arp controls, a small-screen PCM scope, USB MIDI identity and
diagnostics to the shared musical engine. The full web companion and its
persistent library are not thereby ported. Every linked artifact and flash has separate evidence.

## Build 707 handoff (installed 2026-10-06)

Normal FM-1_707 was verified at19:35:03 UTC. The exact corrected package,
preflash source qualification,24 native/MIDI/preset cases,97 feature cases,
35 chord cases and release checks are indexed in [the test report](../../TEST_REPORT.md).
The original factory bank, compact effects, channel/program controls and
[complete native state](../../docs/FM1_NATIVE_STATE.md) now share the audio owner.
SAVE requests a verified PC file; it does not write a device flash partition.

The compiled/measured arena is176,448/294,912 bytes. Native-import IRQ tests use
the actual extracted board block and commit guard, reproducing the two fixed
preflash races. Source-guided stack estimates and observed timing remain bounded
evidence. [Owner test guide](../../docs/USER_TESTING.md).

## Build 706 handoff (installed 2026-10-06)

Normal `FM-1_706` was verified on Test01 at **17:47:22.764047 UTC** in the
[installation journal](../../artifacts/fm1-flash/20261006T174657.189904Z-7b7508d8/events.jsonl),
SHA-256 `c514b429a3d8a741dbef84aef4e81aa2420e0aa81f7911f0dae8592c3736c265`.
The installed package SHA-256 is
`bc6e3f238a2caf143b8f296c659a2b0d43090a961c96cd1b65108731cd2546b5`.
This is the reviewed exact-Test01 development update; it does not establish
general hardware compatibility or interrupted-update recovery.

706 adds meaningful panel and keyboard LED feedback to the accepted 705 scope
and navigation workflow. The pure [LED model](led_model.h) distinguishes active
page, enabled arp, recording, sequencer beat, octave, held SEL and physical key
contacts. A new audio-owned 40-byte snapshot reports actual active/gated MIDI
pitches and voice count: release tails can dim, while stolen or finished voices
disappear. The sequencer pulse follows its real 24-PPQ clock, including rests;
arp motion follows gated notes. These are voice-state indicators, not audio
level meters. Physical colors, brightness and usability still need observation.

Main builds the 22-byte lit/dim frame and publishes both HAL arrays together
under a short IRQ guard. The musical core gains only bounded fixed-slot
inspection; it changes no voice capacity or sound processing. Operation 12
reports commanded LED state for testing, not optical feedback. Native preset
and pattern saving remains unavailable, and SAVE has no false success light.

The [installed build](../../artifacts/fm1-candidate/20261006T173911.454823Z-2defafe9/report.json)
has ELF SHA-256
`7d85cd9dd717e2e9c81392f5c8db0b2f164ad5c67d3415cde832e436d31473c6`.
The [independent source/ELF review](../../artifacts/dsp-review-20261006/706-target/report.json)
has SHA-256
`bd537281cbca561f125319b5c44453d85cb08e8931c392314a48f34522dc978c`.
Text is 79,544 bytes, RAM code 2,776 bytes, data 1,432 bytes and BSS 56,180
bytes. The inferred startup arena use remains 272,784 bytes, with 22,128 bytes
spare; the UI still uses 13,944 bytes. The reviewed audio-plus-nested-timer
stack estimate is 4,104 bytes and startup estimate 7,748 bytes. These are
source/prologue estimates, not measured stack watermarks or execution bounds.

The [four focused test groups](../../artifacts/dsp-review-20261006/706-activity/report.json)
pass on MSVC Release desktop and `FMER_DEVICE` x64 branches, covering pitch-mask
boundaries, sustain, tails, stealing, overlapping sources, panic, exact
sequencer pulse boundaries and no allocation or audio changes during queries.
That report's SHA-256 is
`7a42939176bb4519f202c4d9b1f314f98b417766cdee108e63682e273c981acd`.
Canonical boot FM controls reproduce initial PCM when reapplied.

The [97-case feature run](../../artifacts/fm1-706-bench/20261006T175110.235818Z-cd8a8b44/report.json),
[35-case note matrix](../../artifacts/fm1-bench/20261006T174934.686850Z-3fe15524/report.json)
and [release/sustain checks](../../artifacts/fm1-bench/20261006T175026.137022Z-9dbffe89/report.json)
passed with zero listed fault counters. The feature run observed maxima of
1,276 us for render, 1,020 us for DSP, 354 us for event work, 1,332 us for LCD
and 2,943 us for control adoption. The matrix's render maximum was 742 us;
release checks inherited that peak. Measured startup arena use was 272,784
bytes. These are observed diagnostic windows, not worst-case execution bounds.
The feature run's 32 additional Repeat admission drops were expected; eight
new LED cases checked commanded pages, octave, gates/tails, sustain, stealing,
arp, sequence/recording and panic. These counters and virtual inputs do not
measure visible brightness/colors, physical gestures or audio fidelity.

[Fresh-start defaults](../../artifacts/fm1-706-bench/20261006T174731.272594Z-61ce67bf/report.json)
and [post-test defaults](../../artifacts/fm1-706-bench/20261006T175238.273350Z-e851dba5/report.json)
both matched all 193 canonical controls and all 64 retained pattern steps,
with a quiet HOME LED command state. The audits are read-only; the benches
restored their temporary RAM edits. Native persistence remains unimplemented.

An earlier test attempt passed 93 cases, then the host refused two test
pitches outside its existing smoke allowlist before sending them. The
[fixture issue](../../artifacts/fm1-handoff/706-20261006/harness-issue.json)
was fixed by using already permitted pitches and adding a validator regression.
The successful 97-case rerun used that corrected host fixture. The
[post-flash tool attestation](../../artifacts/fm1-handoff/706-20261006/postflash-tool-attestation.json)
records the tool/test changes and unchanged firmware sources and package;
there was no firmware rebuild or reflash for this correction.

The read-only [706 recorder](../../artifacts/fm1-sessions/20261006T1753Z-live706/status.json)
started as PID 45748 at 17:53:18.753614 UTC, with 32 segments of 8 MiB and stop
file `local/stop-fmer706-20261006T1753Z`. At 17:54:37 UTC it was capturing with
zero listed faults. Its initial 4,048 missing historical events precede this
capture and belong to the separately journaled bench period. Current liveness
requires an advancing status timestamp; no audio or optical video is recorded.

The first exact-unit installation completed on FMER Test01 at 23:02:29 UTC on
2026-10-05. Normal identity `FM-1_701` and the short USB MIDI note test passed;
audio counters advanced, voices changed 0→1→0, maximum render time was 650
microseconds and no overruns, MIDI errors or crashes were reported. This does
not qualify listening quality, physical controls, cold-start recovery or full
polyphony. The owner later confirmed audio, filter and engine operation but
reported flicker and cutouts above two voices. Build 702 was installed at
12:09:30 UTC on 2026-10-06; the owner confirmed the flicker stopped, then found
its screen labels confusing and text too small/crowded. Its later diagnostic
snapshot showed zero listed faults and a 344-microsecond maximum with an
observed peak of two voices. Higher-load checks remain separate. See
[the bench log](../../BENCH_LOG.md) and [hardware test guide](../../docs/USER_TESTING.md).

## Historical build 705 handoff (installed 2026-10-06)

Normal `FM-1_705` was verified on Test01 at **16:23:59.985841 UTC** in the
[installation journal](../../artifacts/fm1-flash/20261006T162334.491773Z-80341d33/events.jsonl).
Its package SHA-256 is
`312d045e7d9fe67ce42242e9563eb1d9c42583cde9a906c4535518fc3898840a`.
The update preserves the exact installed 704 origin gate and original private
stock calibration template. Independent package parsing verified protected
regions; interrupted-update recovery remains a separate qualification.

705 adds coarse continuous adjustment, held-SEL exact adjustment, suppression
of page changes after a held-SEL edit, repeated ARP enable toggles that keep
the current subpage, and graphical pattern/parameter views. Operation11 reads
all 64 retained mono-pattern steps with a content revision. Input/control peak
measurement excludes the earlier startup artifacts and has an explicit reset
window. The [control contract](../../docs/FM1_CONTROLS.md) describes scope and
timing limits; the [panel guide](../../docs/PANEL_WORKFLOW.md) describes use.

The [89-case feature run](../../artifacts/fm1-705-bench/20261006T162804.977801Z-bfa4d524/report.json),
[35-case note matrix](../../artifacts/fm1-bench/20261006T162920.746120Z-fb895f7c/report.json)
and [release/sustain checks](../../artifacts/fm1-bench/20261006T162952.350774Z-788498c2/report.json)
passed. The feature run observed a 1254-us render maximum and 2907-us control
adoption maximum, with zero listed fault counters. Its 32 intentional Repeat
admission drops matched the exact four-attack budget trace. Virtual panel
checks cover coarse/fine edits, SEL release, repeated ARP held-note ownership
and the 16-step grid boundary; they do not verify actual LCD pixels or physical
encoder gestures. The owner subsequently accepted the 705 scope and workflow,
while requesting useful LEDs. Audio fidelity and general load limits remain
separate. The owner's 193 canonical controls and all 64 retained pattern steps
were [restored and checked](../../artifacts/fm1-705-state-transfer/restore-20261006T162959.911219Z-5415037a/report.json)
after the benches; this state is still RAM-only.

The read-only recorder launched as PID 48140 at 16:30:46 UTC and **closed cleanly
at 17:27:15.989700 UTC**. Its [final report](../../artifacts/fm1-sessions/20261006T163046Z-live705/report.json)
has SHA-256
`45558916bf8ce321abcb642c5f81a75700a2bd814bfd234df90e3d485668e213`.
The [independent session review](../../artifacts/fm1-session-review/705-20261006/report.json)
has SHA-256
`c9f9a238cd60ebbe58718aba8707fc23bcbbd53eaca14cd4edacff1295b3a959`.
After the 16:39:47 handoff, it retained 6,937 consecutive user events, including
276 local note pairs, 2,751 arp pairs, 15 sequence pairs and 254 adopted control
edits. No listed fault counter increased; the inherited 32 Repeat admission
drops remained unchanged. User control-adoption events ranged from 187 to
2,469 microseconds; the older 2,961-us peak came from state restoration.

The owner-reported power cycle produced one observed target reset and a
3.563-second connection gap. Read-only cleanup released all driver resources,
then the recorder reacquired exact normal 705 and retained its boot event.
Controls and pattern returned to defaults, as expected for RAM-only state.
The initial 4,890 missing historical events predate capture; no new within-epoch
trace gap occurred. Unobserved events across the power-off boundary cannot be
counted after the target counter resets. The session contains no audio, video
or optical LED feedback. See the [session guide](../../docs/FM1_SESSION.md).

## Historical build 704 handoff (installed 2026-10-06)

The following describes the superseded 704 installation. Its recorder closed
cleanly at 16:01:14 UTC before the 705 work; old paths and observations are retained
to interpret that evidence, not to describe the current process.

Normal `FM-1_704` was verified on Test01 at 14:37:25 UTC on 2026-10-06 in
the [flash journal](../../artifacts/fm1-flash/20261006T143659.670098Z-cf92f425/events.jsonl).
The installed package SHA-256 is
`60dea90e94377af318e452f08282812df4305baeaa2ab5b98a060e9fc4e61f37`.
The hidden session recorder was observed capturing as PID 51020 at
14:47:51 UTC on 2026-10-06; current liveness requires an advancing heartbeat. The owner confirmed
703 readability and basic FM/VA playing, and supplied a photograph confirming
the printed control grid. This is not approval of the new 704 layout or actions.
The pure C [panel model](panel_model.h) maps all 145 raw FM fields and the shared
VA/effects/performance controls. The [workflow guide](../../docs/PANEL_WORKFLOW.md)
records page navigation, four persistent knob assignments, next-note versus
master-effect behavior, stored-only FM limitations and the explicit RAM-only
SAVE notice. PRESETS temporarily navigates pages; no preset load is implied.

HOME's four knobs are master cutoff, FM feedback/VA resonance, delay mix and
reverb mix. SELECT picks the engine on HOME, an operator on FM EDIT/operator
ENV, or a subpage elsewhere. SEL/repeated family buttons cycle subpages;
ALGORITHM retains global FM algorithm/VA waveform selection. PLAY short-release
toggles sequence playback from any page. A hold of at least 800 ms panics and
resumes protective pause without subsequently triggering PLAY; local held keys
need release/repress. REC opens SEQ and toggles single-note step entry. ARP enable
is explicit; sequence playback and step entry disable it. SAVE is RAM-only,
and native preset storage, timed/chord recording, multitrack/chained sequencing
and browser-library synchronization remain unimplemented.

Sound edits normally snapshot at Note On; master effects apply to the mixed
signal. FM AM sensitivity/depth and oscillator sync remain stored-only. LFO
sync changes each note's starting phase and is labeled PER NOTE LFO; a shared
free-running LFO is not implemented. The [testing guide](../../docs/USER_TESTING.md)
leads with the new workflow and keeps earlier assignments historical.

The [session recorder](../../docs/FM1_SESSION.md) passed a ten-second physical
smoke run, then started in a hidden process. Its live run is
`artifacts/fm1-sessions/20261006T144631Z-live704/`, with command/stdout/stderr at
`artifacts/fm1-session-launch/20261006T144631Z/`. The advancing `status.json`
heartbeat, not a saved PID alone, establishes recent liveness. It captures
input, control, generated-note and diagnostic events through read-only telemetry;
there is no audio/video capture. The 3,344 missing old events predate capture
(oldest available sequence 3,345); no additional loss was observed in the live
window. Its 32 x 8 MiB budget stops at capacity without deleting evidence.
Create `local/stop-fmer704-20261006T144631Z` to stop this run cleanly. Do not run a
second bench/updater against the same endpoints while capture is active.

HOME takes an actual 128-sample signed post-mix PCM snapshot from the board,
drawn at most 10 Hz in three strips. It never fabricates an animation. Focused
values use 21-pixel glyphs and are considered before waveform changes on each
service. The 11,520-byte DMA pixel buffer plus row/scope caches remain below
15.5 KiB. Main code supplies immutable snapshots for each UI call. The pure
model does no HAL/DSP work, allocation, logging or persistent writes.

The isolated LCD and panel tests pass: every mapped page at both bounds,
all 145 FM fields reachable with correct operator order, cross-field sequence
step/length invariants, valid arp rates, timer wrap, DMA ownership, actual-PCM
scope response and next-service global algorithm feedback on every family.
These do not qualify actual 704 latency, scope load, transport or output.
The control-mailbox regression additionally uses the real DSP adapter to
exercise recording advancement during a length/step edit and preserve explicit
pitch/velocity/gate edits. Critical-section trace tests cover pre-IRQ startup and
already-locked publication. The four focused host suites passed in
`artifacts/fm1-integration-review/20261006T142645.985991Z-bdc0ca6c/`; this is not
target timing evidence.

The new [704 note-load matrix](../../artifacts/fm1-bench/20261006T143930.129739Z-c07379a1/report.json)
passed 35 cases, including eight input notes bounded to four active voices.
Case snapshots reached 735 microseconds with zero listed firmware error,
overrun, pause, shed or LCD-timeout counters. The independent
[release/sustain run](../../artifacts/fm1-bench/20261006T144007.653672Z-b9220ab6/report.json)
passed isolated Note Off, zero-velocity Note On, CC123, CC120 and sustain.
Neither run recorded audio. The
[expanded 85-case run](../../artifacts/fm1-704-bench/20261006T144324.926943Z-72580e47/report.json)
also passed, including 32 FM algorithms across two patches, four VA cases,
six effect cases, sequence/step entry and all seven arp orders. It retained
1,772 target events, reached 1,251 microseconds peak render time and recorded
zero listed firmware faults. Controls and modified mono steps were restored
exactly; transport stopped and HOME was selected. Its first attempt had stopped
on an overly strict harness check; the corrected run explicitly admits the
32 expected arp Repeat drops. Actual 704 UI acceptance, physical input actions,
long sessions and listening quality remain separate evidence. Future images
still require their own source, package and exact-unit review.

## Historical build 703 interface handoff (installed 2026-10-06)

The previous 703 build identifies itself as `FM-1_703`; the
[flash journal](../../artifacts/fm1-flash/20261006T131228.274806Z-483a8173/events.jsonl)
confirms this normal identity on Test01 at 13:12:53 UTC. Its focused interface
addresses the readability feedback; the owner confirmed readability and basic
FM/VA playing. The later owner photo confirms the printed layout, while full action mapping remains a bench item. HOME presents engine, algorithm/waveform, exact gain,
octave and active voice count/limit. Turning SELECT or ALGORITHM returns HOME.
Turning KNOB 1, 2, 3 or 4 opens CUTOFF, DELAY, ATTACK or RELEASE respectively,
with the exact numeric value, range and a visual bar. Cutoff and delay affect
both engines. Attack/release are VA-only and apply to subsequent notes; FM
shows `VA ONLY`. VA waveform selection also affects subsequent notes.

The pinned upstream panel mapping assigns HOME to bit 8, FX to bit 2, ENV to
bit 4 and GLO to bit 7: HOME returns to the overview, FX opens cutoff, ENV
opens attack, and GLO opens diagnostics. These older assignments are retained only to interpret 703 evidence. Other page buttons and PRESETS remain unassigned.
PLAY and REC both panic notes/effects and resume paused audio. Held keys stay
silent until released and pressed again; these are not sequencer controls.

The normal UI retains CADER colors and uses ten 24-pixel strips. Primary
values use scale-3 original 5x7 glyphs (21 pixels high, versus 14 in 702);
secondary labels use scale 2, with no two-line tiny text. A single 11,520-byte
RGB565 buffer and cached descriptions use less than 13 KiB. Only a changed
strip is transferred, at most once per 8 ms outside interrupts. Statistics
are sampled every 250 ms, and unchanged state performs no pixel transfer.
Cache reset never overwrites a buffer still owned by DMA. Initial drawing
and page changes complete progressively, without a visible full-screen clear.
Startup/fault/update screens are separate paths.

The default budget is four voices. Excess notes replace existing voices;
overload protection can reduce the budget and records load sheds, with a
protective pause if overload persists at the minimum. Resume does not erase
the lifetime counters. The LCD mock covers bounded DMA ownership, unchanged
frames, focused field changes, maximum-value fit, page text, statistic cadence
and timer wrap. The complete Release host baseline passed 11/11 CTests in
`artifacts/runs/20261006T130637.093663Z-test-3f865582/`. These remain host results.

703 also routes each received SysEx frame to one consumer, addressing the
missing control acknowledgment that stopped the 702 load matrix before notes.
The fresh [703 target matrix](../../artifacts/fm1-bench/20261006T131303.778094Z-f6ae4141/report.json)
passed all 35 cases: 1/2/3/4/8 input notes across FM algorithm 0, the four VA
waveforms, and FM/VA filter-plus-delay scenarios. Eight input notes remained
bounded to four active voices. Maximum reported render time was 651
microseconds; sampled overrun, pause, load-shed, MIDI overflow, rejected-message,
LCD-timeout, initialization-failure and crash counters were zero.
The [isolated release run](../../artifacts/fm1-bench/20261006T131341.390943Z-feb36f15/report.json)
passed Note Off, zero-velocity Note On, CC123, CC120 and sustain hold/release,
using VA with 50 ms release. It restored the normal initial musical settings.
These are short target-counter tests, without an audio recording. Physical
page navigation/readability, sound quality, all FM algorithms, long-load runs
and interrupted-update recovery remain separate checks. Build 703 did not add native preset
save, sequencer, arpeggiator UI or companion-library synchronization; 704
changes the sequence/arp scope described above.

The board reference is pinned Felucca GPL-3.0-only HAL/startup/USB/LCD code.
The combined board candidate is a GPL-3.0-compatible derivative for local
development; retain its notices and complete source if distributing it.
Original shared-core distribution terms remain a separate project decision.
No vendor firmware or preset bank is a source dependency. Imported sample,
font and musical-engine assets are not used by this adapter.

Allocation is bounded to a startup arena and the audio path has one owner.
No settings or presets are written to flash by this candidate. Board transport
and protected-region handling have an exact-unit qualification and successful
transfer record. Independent recovery remains unqualified; future images need
their own source/package checks before selection for an authorized flash.

## Historical build 701 memory evidence (2026-10-05)

`python tools/build_fm1_candidate.py` verifies the acquired Felucca Git blobs
against commit `20c275e39f75fa820978032efaceddfc5283c8cb`, the MSFA source lock,
and the target compiler/libc++ file hashes before compiling. It runs no upstream
build script and has no package, device-open or flash operation. Outputs include
the ELF, linker map, exact compiler logs, disassembly, source/object hashes and
the retained USB descriptor patch (`FMER` / `FMER Test01`). Current builds use
bench wire identity `FM-1_706`, with no release-version claim. The measurements
below apply only to the original 701 ELF; later maps and startup counters must
be read from their own artifacts.

The reviewed candidate is
`artifacts/fm1-candidate/20261005T220547.524862Z-b1b5e606/fm1.elf`, SHA-256
`3d36f65da52f648e852f906c80e4961d67bc509becca8186e98343679c890ec0`.
Its ELF entry is `0x02000120`; text is 48,604 bytes, RAM code 2,776 bytes,
initialized data 16 bytes, BSS 32,564 bytes, pool 294,912 bytes and retained
NOINIT 76 bytes. The linker and ELF inspection reject unsupported static C++
constructors, unexpected/overlapping sections, invalid load addresses and
memory-region overflow. There are no unresolved symbols.

`memory-review.json` beside that ELF records independent source/disassembly
review. Four startup allocations request 4, 28,916, 4 and 221,548 bytes; allocator
alignment brings their total to 250,512 bytes, leaving 44,400 bytes in the 288 KiB
arena. No other retained code calls the allocator. The largest explicit local
stack allocation is the 2,248-byte Synth reset frame. Known direct call paths,
including register saves, estimate 2,928 bytes for startup, 2,628 for audio and
104 for the timer; hardware frames and indirect targets are excluded. These are
static evidence, not measured stack high-water or execution-time guarantees.
The RAM flash routines have no disassembled direct branch outside RAMTEXT and
no indirect calls. Timing, output levels, memory guards, cold/warm boots and
rescue enumeration still need target measurements.

