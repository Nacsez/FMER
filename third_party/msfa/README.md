# Selected Google MSFA engine

Original project: <https://github.com/google/music-synthesizer-for-android>

Pinned commit: `f67d41d313b7dc85f6fb99e79e515cc9d208cfff` (2017-09-13).
Acquired and audited: 2026-10-02. Corpus source: S26.

The 23 source/header files in `src/` are a selected portable engine and patch
decoder from `app/src/main/jni/`. The complete upstream Apache-2.0 license is
retained as [COPYING](COPYING). Existing copyright and license headers are kept.
The pinned repository tree contains no separate NOTICE file.

No Android/macOS application wrapper, build script, assembly kernel, firmware,
SDK, sound bank, font, image, or binary is included. FMER's CMake explicitly
compiles the selected C++ files; no upstream build script has been executed.

[The source lock](../../evidence/msfa-source.json) records original SHA-256,
verified upstream Git blob IDs, local SHA-256, and changed-file status. Each
pristine download was checked against both its initial download hash and the
pinned Git tree's blob ID. [The portability patch](fmer-port.patch) records all
changes from upstream. Apply/review it as text; it is not an automatic updater.

The local changes select the scalar path, replace platform-specific barriers,
define signed/modular arithmetic where needed, reset feedback on note reuse,
correct the historical VCED declaration, expose envelope completion, and guard
extreme frequency-table shifts. All modified files identify FMER changes in
comments. They do not add the later Dexed feedback fixes for algorithms 4/6 or
claim FM1 hardware calibration.

The 2026-10-05 target port adds an explicit `FMER_DEVICE` branch to `synth.h`:
the selected single-owner engine requires no C++ thread library. Its unused
`SynthMemoryBarrier` macro becomes a compiler barrier in that branch; it is not
a peripheral/DMA barrier. The board HAL must provide any device bus ordering.
The normal host branch retains the standard atomic fence. The separate FMER
adapter initializes its tables before device callbacks start; host initialization
continues to use `std::call_once`. No synthesis arithmetic changed in this port.

Original FMER adapter/VA code and tests live outside this dependency directory.
Its distribution terms remain separate from the Apache-2.0 grant over the
imported code. See [engine scope and validation](../../docs/SYNTH_ENGINE.md).

The 2026-10-06 707 development adds original FMER amplitude modulation in
`Dx7Note`. The retained AMD field and each operator's AMS now attenuate its
envelope before the existing gain interpolation. At AMD99, AMS0/1/2/3 reaches
0/1/2/4 octaves of attenuation (approximately 0/6/12/24 dB) at the LFO peak;
AMD scales that depth linearly and the existing LFO delay ramps it in. This is
an explicit original curve, not a measured DX7 depth calibration. AMD0 and
AMS0 preserve the prior signal exactly. It adds 24 bytes per voice, bounded
integer work per 64-frame control block, and no allocation or sample-loop
transcendental calls. The upstream source pin and notices are unchanged; the
complete local patch and hashes identify this behavior change.

The 2026-10-11 719 port adds `Dx7Note::shift_ratio_pitch`, a bounded Q24
log-frequency shift applied only to ratio oscillators. FMER's mono glide
trajectory calls it at the existing 64-frame control cadence using the voice's
retained VCED snapshot. Fixed oscillators, envelopes, feedback, phase and the
initial note's key/velocity scaling are preserved; no MSFA state is added.
Default glide-off arithmetic is unchanged. Regressions check glide contours,
exact fixed-oscillator PCM preservation, release, chunk invariance and no
allocations in the musical path. This is original portamento behavior, not a
claim of the DX7's portamento modes or key-follow calibration.

The 2026-10-11 719 timing refinement narrows the sine-table delta
interpolation to signed 32-bit arithmetic. The unchanged 1024-entry integer
table recurrence has maximum absolute delta 102,943; its largest product with
the 14-bit interpolation fraction is 1,686,515,169, below `INT32_MAX`.
An exhaustive test compares all 16,777,216 phase values with the original
64-bit expression. Operator output products still use full 64-bit precision;
the shifted result is narrowed before accumulation, whose unsigned addition
defines the retained low 32 bits. Separate references cover all three kernels,
both add modes, feedback state and output wrap. A before/after host capture
also preserves 1,501,760 PCM samples and voice counters byte-for-byte across
104 instrument/performance cases. No tables, phase timing, voice state,
envelopes or sound recipes change. Target timing remains a separate bench
qualification; fewer compiled instructions alone do not establish a deadline.
