## Latest local candidate:735-r9

735-r9 supersedes the timing status below. Malachite now passes the defined
reserve workloads with preserved data:1990us six-VA/all-FX,2039us repeated
chords,2141us dense4T/edit stress. [CPU report, memory and remaining gates](CPU_735.md).
The actual-renderer screen atlas is available as `FMER Screen Sheets 735.zip`.
No public assets changed.

## Earlier local candidate:735-r4

The735-r3 status below is historical.735-r4 is installed on Malachite with
preserved banks/projects. [Voice transition fix, USB capture and current gates](CLICK_FIX_735.md).
Six-VA/all-FX reserve still misses by5us; heavy4T stress is close to its guard.
This remains a local owner test, not a public release qualification.

# FMER735 development candidate — 24 October 2026

Local branch: `release/next-package-compat`. This is an owner test build, not a
replacement for published734-r2 or Companion734r5. No remote publication is
authorized in this increment. Malachite is the development unit; Citrine and
Amethyst remain untouched.

## Changes and boundaries

* Single-instrument polyphony supports six simultaneous voices. Mode selection
  and shortcuts now say6V. Four-track mode still reserves one mono voice per
  track; glide remains1V. Changing sounds does not select a different mode.
* Native12 admits a voice budget of1..6 without increasing the4000-byte record.
  Older native records migrate explicitly; old headers cannot admit six voices.
  Compact instrument records retain their existing size. Companion converts
  outgoing records for supported733/734 units, capping their budget at four.
  Downgrading an already735 unit to733/734 is blocked before flashing because
  persistent native12 storage needs a separate migration procedure.
* Expressions2 contains192 original instruments and four64-slot profiles.
  Spectrum A contains every one of the62 survey favorites (34FM,28VA), plus
  Marrow and Arcade Pop for a final36FM/28VA mix. B emphasizes drums/bass,
  C leads/arps, D pads/ambient/unusual sounds. Twenty-five recipes have targeted
  revisions; the earlier64-instrument Classic collection remains available.
  No OEM/V16 patch data was copied into these original recipes.
  All four profiles group musical categories across engines, with kicks, snares,
  claps and hats grouped within percussion. Personal profiles retain user order.
* The device's built-in default bank is Spectrum. PRESETS now walks Bank A
  slots0–63 then Bank B slots0–63, independent of engine. K1 jumps banks. Both
  banks accept any FM/VA mixture, matching Companion's exact profile order.
* Companion supports independent Bank A/Bank B loadouts during installation or
  later, reusable user profiles, slot reordering and local auditions. A plain
  reflash also captures full musical-data backups and preserves inherited
  instrument slots whose sounds would otherwise change with firmware defaults.
  Explicitly selected destinations are replaced; projects retain slot references.
* The self-describing FWSC uses the existing reviewed updater and preserves the
  protected boot/configuration regions. An unmodified public FM-1 emulator
  boots this package at its60MHz setting. This does not qualify arbitrary
  third-party installers, other firmware migrations, or emulator sound fidelity.

* My instruments stores16 local named setups, each with two loadout references,
  Library collection and notes. Names label jobs but do not identify hardware.
  Connect one intended unit for writes/flashing; switching clears cached views.
* Bank A/B are equally editable. Stable wire/API identifiers remain default/user
  for compatibility. Bank A stays populated; Bank B can be cleared independently.
* First octave shift now lights above ready glow:50%,75%,100% scan duty for
  one/two/three octaves in either direction. Held feedback temporarily uses full
  brightness. The additional mask is bounded matrix-scan work, not audio work.

## Evidence and resources

735-r3 candidate ELF SHA256:
`bf99d06cbf9ebadb88a5bddc794517fe5761a4e9a117c46d43a2a5623a044568`.
FWSC SHA256:
`e93b4f70eb2ae57d882c87e2df94fcd83375510c0beb92e93563438fcc6b2c4c`.
Artifacts are under `artifacts/development-735/`; immutable command logs and
the full baseline summary live under `artifacts/runs/`.

| Allocation | Final linked size | Meaning |
|---|---:|---|
| Flash text/constants |224596B|Includes compact Spectrum recipes|
| RAM-executed code |2840B|Copied from flash at startup|
| Initialized data |2084B|Mutable RAM|
| BSS |82508B|Zero-initialized RAM|
| Startup arena reservation |294912B|Existing preallocated musical engine pool|
| Display/cache workspace |44272B|Fixed RAM;4880B remain before its guard|
| Retained diagnostics |76B|Crash information|

These are linker regions, not interchangeable free-memory totals. Six voices
use the existing preallocated engine capacity, not a new runtime heap. No
overclock, second core, reduced sample rate, or audio-callback allocation was
introduced. CPU headroom is the principal six-voice constraint.

The735-r1 final repeat covers FM/VA, dry/all FX and1/4/6 notes, including
sustain/release and full-screen scope. Maxima were1987us FM and2092us VA against
a2902us block deadline; the test gate reserves25%. A concurrent90s USB recording
captured3,969,024 stereo frames with nonzero PCM. No observed underrun, load-shed,
MIDI-overflow, LCD-timeout or retained-crash increments. Single-track playback
plus five incoming notes reached six voices while cycling every sequencer page.
Glide/poly return and4T navigation passed, preserving musical state/settings.
These are bounded bench scenarios, not an exhaustive192-patch stress guarantee.
Final735-r3 installed both Spectrum banks through the production Companion.
All128 slot writes were read back; saved projects0,11,12,13,14 and MIDI settings
match the pre-install backup. Octave telemetry distinguishes the first shift
from ambient glow; host scan tests verify50/75/100% duty.

The final735-r3 stress repeat passed11 of12 timing cases. Six VA notes with
all effects reached2294us against the2902us deadline, missing our stricter
25% reserve gate (2177us). No audio underruns, load shedding, MIDI overflow,
LCD timeout or crash increments occurred. A follow-up eight-burst test isolated
the concern to simultaneous note attacks: four bursts exceeded the reserve
gate; sustained maxima were2060..2083us. Sustain/release and panic passed.
This is an OPEN release-performance gate, not a fully qualified six-voice
release. Retain the original failing evidence; do not relax the threshold.
Next: profile attack initialization/coefficient work, optimize without changing
sound, then repeat dense-note/FX/USB/display tests and extended live testing.

The complete Release host baseline passes1163 Python tests (19 explicit skips)
and34/34 CTest suites. Product, loadout and named-unit browser workflows pass.
An unmodified public fm1-emu boots the exact735-r3 package at60MHz. A90-second
USB PCM capture completed alongside the target stress test. Portable rehearsal
and final workflow receipts are indexed in TEST_REPORT.md and the development
 evidence ledger; their scope does not imply a separate clean-machine test.

Offline sound review generated2688 shared-core renders across all192 sounds.
No automatic metric failures occurred. Five high-output warnings are retained
for listening review: Marrow, Dub Knock, Tin Rattle, Rubber Low and Acid Tooth.
Metrics catch silence/clipping/range problems; they do not establish artistic
quality. The owner's comparative listening remains the acceptance gate.

## Owner handoff and next gates

Malachite now has fresh Spectrum in Bank A and Bank B. Every saved
project/pattern was preserved and compared with the pre-install backup.
Existing songs reference slot numbers and consequently use the new sounds.
Retain the pre-update backup for optional recovery; do not erase projects.

Use `artifacts/development-735/sound-review/index.html` to compare performance,
soft-touch and dry clips and export another review. Companion includes all four
profiles, Classic and the192-sound library for independent bank deployment.

Before public release: listen to the revised sounds, exercise long real
performances with six voices and dense FX, verify a power-cycle save/recall,
and repeat the portable package test on the separate Windows computer.
The selectable-palette request remains queued in PLAN.md: custom RGB settings,
save slots and monochrome accessibility have not been implemented in735.
Bluetooth remains deferred; USB direct link and existing MIDI remain the
supported multi-unit path. No published package is replaced by this build.
