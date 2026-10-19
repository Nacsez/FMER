# Runtime and distribution review — 734-r2

19 October 2026. The selected path is to build FMER's required runtime from
publicly licensed source, keep the compiler external, and retain the existing
musical application. No rights holder was contacted and no new permission is
required by the selected source licenses. This closes the identified binary
archive/source gap for **734-r2**, not for every vendor SDK or older FMER binary.
The repository and release remain private/draft for the owner's review.

| Option | Consequence | Decision |
|---|---|---|
| Keep the vendor's precompiled runtime archives | Least code change, but exact composition/redistribution basis remains unresolved | Retain privately as reference only |
| Build the required routines from licensed source | Small binary change, inspectable source and notices, targeted regression required | Implemented and tested |
| Replace the compiler or broader platform | Much larger code-generation, timing and recovery qualification project | Defer; unnecessary for this release |

## What was replaced

The original734 map selected48 objects: five from libc,33 from libm,10 from
compiler-rt. The replacement uses49 unmodified source units from Newlib2.2.0 and
LLVM compiler-rt4.0.1. Vendor memcpy also supplied memmove, which has its own
upstream source. The selected sources and required local headers are included
under `third_party/runtime`, with per-file hashes and complete notices.

The math code carries its individual Sun/Red Hat/Cygnus notices and Newlib's
collection notices. The compiler helpers use the offered MIT option of the
legacy MIT/UIUC dual license. The combined application remains GPL-3.0-only;
these permissive components retain their licenses. The compiler itself and its
normal headers remain separately obtained build prerequisites. No vendor runtime
archive, proprietary synth engine or radio runtime is linked into734-r2.

The source builder verifies every included file and the archiver executable,
uses no upstream build scripts, and records exact compile/link commands.
Default builds select `--runtime source`. `--runtime vendor-reference` remains
an explicit comparison option and cannot be promoted by the release builder.
The loader is freestanding and links no runtime archive.

## Public package construction

The existing installer used a private reference image to preserve format and
configuration bytes. Its383-byte configuration block and2,873-byte EQ block
match the corresponding blocks in M-VAVE's publicly licensed Original V15
resource at commit `b178ac43c25f010c60a878056fb5331fe693fd62`.

Only those two data blocks are retained, in editable hexadecimal JSON under
`third_party/fm1_resources`. Their decoded bytes are unchanged; provenance,
the publisher's complete notices and Apache-2.0 accompany them. FMER generates
directory records/padding from format constants at its existing supported
addresses. This is not an installation of the vendor's larger V15 application.
No stock application, boot code, patch bank or private dump is bundled.

The generated region matches the former package byte-for-byte before its last
32 opaque bytes. Those bytes are now FF in the distributed image. Updater935
already preserves the device's entire final sector and excludes only those32
bytes from its compatibility comparison. No write boundary or compatibility
guard changed. The same fixed layout/calibration digest remains mandatory:
`3c96f791076cb529d42be1225d42e4e5c820728e91c187e58682e3d7708acd88`.

The build now needs no private ROM or stock firmware download. Its loader test
uses a synthetic device header, including a generated format-test key blob;
this fixture is never a boot image or a distributed installer payload.

## Binary and resource comparison

| Measurement | Original734 | Source runtime734-r2 | Change |
|---|---:|---:|---:|
| Program `.text` |209,604B|209,796B|+192B|
| RAM code `.ram_text` |2,840B|2,840B|0|
| Initialized `.data` |2,084B|2,084B|0|
| `.bss` |82,492B|82,492B|0|
| `.pool` |294,912B|294,912B|0|
| `.workspace` |44,272B|44,272B|0|
| `.noinit` |76B|76B|0|

All25 application objects are byte-identical. Forty of the48 reference runtime
objects have equal allocated code/data, relocation contracts and exported
symbol definitions. Eight differ: memcmp, memcpy/memmove, memset, adddf3,
divdf3, muldf3, double rem_pio2 and float rem_pio2. This is not a claim that
unrelocated bytes prove whole-program equivalence. The differing routines receive
behavioral tests and the complete candidate receives hardware tests.

Source-built final ELF:
`263c5c2fa278a4d117d3d2985c91a5db89ffc8a1ac064770d6c31386df730f58`.
The final rebuild is whole-file identical to the candidate tested on Amethyst.
Standalone `fmer734-compatible-r2.fwsc`:
`a953cd928543a333b9065e911b8b452757fce71944d4344cc8cb7c0e1b4e5e41`.
Updater935 remains unchanged:
`c640eff6f75a2a4a5cceb9d3cbb8dc9b461ae908d3aff4ce1cd4b554ff575634`.
Wire identity remains FM-1_734; package revision and hashes distinguish builds.

## Verification and limits

Both attached units were fully backed up with explicit physical USB selectors.
Amethyst received the candidate; Citrine remained the reference. Port location
is a session selector, not a permanent serial number.

- 1,172,204 host behavioral checks pass: memory guards/alignment/overlap, signed
  conversion,64-bit integer division/remainder, software double arithmetic and
  trigonometric reduction. These exercise upstream algorithms on the host, not
  pi32v2 code generation or cycle counts.
- All42 independent updater preservation/failure checks pass with the public
  image and synthetic fixture. Live updater935 installation completed and734
  re-identified normally.
- Same-unit before/after target runs pass64 quiet four-note preset cases,35
  FM/VA/effects/chord cases, four release commands and sustain cleanup. No new
  audio overrun, MIDI overflow, rejected message, crash, load shed or LCD timeout
  occurs. Highest preset render observations are1,005/1,044us; matrix maxima
  are1,182/1,206us (reference/replacement). These short observed maxima are not
  a worst-case execution-time proof or evidence that the change is cost-free.
-100s USB stereo PCM capture passes before and after,4,411,392 frames each.
  The active Amethyst stream is nonzero; the idle reference stream stays at
  digital idle. Timing/levels vary with live event arrival, so this is not a
  bit-identical audio null test or a listening-quality acceptance claim.
- USB notes/CCs, no-echo behavior,24PPQN, Start/Stop, Song Position/Continue,
  clock-loss stop, clocked Exclusive/Repeat arp, channel filtering, sustain,
  bend and Active Sensing release pass. Physical TRS and cable-linked pair
  testing were not repeated in this narrow runtime pass.
- Mode-aware navigation, single-song plus three MIDI notes through every SEQ
  page, explicit4V/glide behavior and FX/SEL route-save protection pass.
- All128 saved instruments,16 project destinations and default FX order compare
  equal after installation. Working state and MIDI settings are restored and
  verified. No musical storage records were intentionally changed.

Full host/package/export results are recorded in [VERIFICATION.md](VERIFICATION.md).
Private command logs, captured PCM, backups and failed attempts remain under
`artifacts/runtime-review-734`; sanitized hashes and results are in the release
evidence record. None of the private unit material is part of the public export.

Two numerical boundaries are explicit. LLVM4 double division flushes underflow
to zero as its source states. Broad exploratory tests also found float argument
reduction outside the expected interval at approximately5e33 radians. FMER's
float oscillator/LFO phases and filter angles are bounded; the regression covers
a much wider +/-4096-radian domain. No full-range IEEE/libm certification is
claimed. Do not reuse this restricted runtime as a general-purpose math library
without reviewing those limits. No DSP algorithms were changed to hide them.

The first target harness rejected the valid VA Noise waveform because its older
diagnostic parser stopped recognizing it after731. That parser and regression
were corrected. Another harness missed48 trace-ring events while running its
long chord loop; sampling between each diagnostic query fixes the harness.
The original failures are retained. Neither is reported as a firmware success.
Windows initially refused sandbox audio capture; the approved native retry
captured the two explicitly selected FMER inputs, not ambient microphones.

## Distribution boundaries and future work

The project can follow this source-built route without a bespoke permission
request or vendor approval on each release. Keep corresponding source, notices,
provenance and exact hashes with every binary. The earlier unreviewed runtime
archives are not retroactively cleared. Do not redistribute the external compiler
package or assume this review covers a future proprietary radio/synth SDK.

Existing beta limitations remain: clean-machine breadth, owner listening and
paired-use acceptance, heavy combined-load reserve, power/endurance and the full
recovery matrix. Public publication remains the owner's action. Bluetooth stays
deferred. The small runtime change does not expand hardware capabilities or make
unknown firmware layouts safe to flash.

Primary sources: [Newlib licensing](https://sourceware.org/newlib/COPYING.NEWLIB),
[LLVM4 runtime license](https://raw.githubusercontent.com/llvm-mirror/compiler-rt/release_40/LICENSE.TXT),
[pinned M-VAVE resource terms](https://github.com/m-vave/fm1_open/blob/b178ac43c25f010c60a878056fb5331fe693fd62/THIRD_PARTY.md),
[GPLv3 system-library/source definitions](https://www.gnu.org/licenses/gpl-3.0.html).
These sources establish the selected components' terms; they do not grant rights
over unrelated vendor material.
