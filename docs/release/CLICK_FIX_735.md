# 735-r4 voice transitions and USB audio — 24 October 2026

Local development build on Malachite only. Published 734, Citrine and Amethyst
are unchanged. This candidate addresses two mechanisms found during the owner's
click/pop tests. It is **not release-qualified**: CPU reserve and owner listening
remain open.

## Changes

An active voice replacement now starts at that voice's previous output sample,
then removes the correction over 128 samples (about 2.9 ms at 44.1 kHz).
This covers mono retriggers, held-note return and polyphonic capacity steals.
Free voices retain their original attacks; legato/glide retains its existing
path. Panic does not leave a correction tail. The correction is bounded,
preallocated and independent of render chunk size. It is not a limiter or an
extra sounding voice. It removes the discontinuous step, not every possible
musical transient or intentional distortion.

VA filter coefficients are cached per instrument/part instead of recalculating
the same tangent on every note. VA starts reset the state they use, without
clearing unused FM scratch space. Centered VA pitch bend avoids an unnecessary
exponential. Four-track shared-FX changes use the existing FX-only update path;
the regression compares its exact PCM, MIDI and complete native state against
full application for both modes and both engines.

The overload handler now counts a voice reduction only when it succeeds. It
never requests fewer than four reserved parts in 4T. Three consecutive severe
unsheddable blocks request a protective pause/panic. This is a last-resort
guard, not a substitute for sufficient CPU headroom. An extracted production
branch regression checks accepted 6V reduction and rejected 4T reduction.

No patch formats, saved slots, sequencing features, sample rate, clock speed or
UI controls were removed or changed. Text/constants grew by 1,616 bytes to
226,212 bytes. Linked BSS, data, display workspace and arena reservation are
unchanged; the engine's small new state is inside the existing fixed arena.

## Target evidence

| Workload | Maximum block time | Result |
|---|---:|---|
| FM/VA dry/all FX, 1/4/6 voices | 2,182 µs | Eleven reserve passes; six-VA/all-FX misses 2,177 µs gate by 5 µs |
| Dry repeated 4T mono replacement | 481 µs | No new diagnostic faults |
| Dry repeated 6V capacity replacement | 679 µs | No new diagnostic faults |
| Four tracks, 480 BPM, synchronized attacks, all FX and live FX edits | 2,578 µs | No new faults; only 22 µs below 2,600 µs publication guard |
| Repeated six-note chords, all FX, no diagnostic polling | FM 2,071 / VA 2,257 µs | No new faults; VA remains above the 2,177 µs reserve gate |

The final chord run exercised 24 successive chords per engine and 138 voice
steals per engine. Both restored the working state. It confirms that removing
diagnostic polling does not by itself close the VA reserve gap.
The audio period is approximately 2,902 µs. The 25% reserve gate was not weakened.
No observed overrun, false load-shed, MIDI rejection/overflow, display timeout,
retained crash or audio pause occurred in the completed workloads. These are
bounded scenarios with USB telemetry and recording, not an exhaustive guarantee
for every patch, FX order or physical output. The six-voice qualification script
deliberately exits nonzero on the reserve failure; its failure is retained.

The continuity regression fails against the previous `b4212e2` synth and passes
against this candidate. It checks FM and VA, held-note return, one-sample versus
257-sample render calls, panic, and six-voice stealing. Correction to the prior
investigation: its probe supplied an invalid VA cutoff of 20,000 Hz and ignored
the setter result, so its reported numbers were **not a validated sine fixture**.
The replacement regression uses a valid 18,000 Hz cutoff and checks all setters.
The original logs remain preserved; their interpretation is superseded here.

Production Companion installed the exact candidate after a complete backup.
Readback matches all 128 instruments, all five saved projects, MIDI settings and
the saved FX order. Automated benches restore the complete editable working
state and leave onboard storage generation unchanged. No instrument reset was
performed in this pass.

## USB audio diagnosis and operation

`waveInOpen` returned MMRESULT1 inside the restricted agent process. The identical
endpoint and capture command succeeded outside that restriction with no driver,
Windows privacy-setting or firmware change between attempts. This establishes
an execution-environment access problem for those failed opens; it does not
establish that Companion needs administrator privileges on ordinary desktops.

Two completed 90-second captures each contain 3,969,024 stereo 16-bit frames at
44.1 kHz. The extra fraction of a second is the last complete capture buffer.
Both contain nonzero PCM and no capture stall/cleanup error. Their buffer logs
and hashes are retained. Successful delivery alone does not prove every sample
is artifact-free, nor does USB capture validate the built-in speaker/analog path.

From an authorized Windows desktop process, enumerate with:

```text
python tools/winmm_audio_capture.py
```

Then select exactly the FMER input name returned on that computer:

```text
python tools/winmm_audio_capture.py --device-exact "Line (FMER Test01)" --seconds 90 --output artifacts/my-audio-test
```

The output directory must be new. The tool writes `capture.wav` and `report.json`,
keeps partial evidence on failure and never selects an unrelated microphone.
The displayed Windows endpoint name can remain cached from an earlier firmware.
An agent's restricted environment may need an authorized device-access tool call;
do not change system configuration to work around that restriction.

## Identity and next gate

FWSC SHA256: `1274cb463668d0e94bdf4e3653e864dd62bcd5bb8a2526873b2c9c9d205ee463`.
ELF SHA256: `c9c96af144f6916f7b9a7528bc1ea2c967db754c7dd233220d65a554c6385c69`.
Wire identity remains `FM-1_735`; the package hash/install journal identifies r4.
Evidence: `evidence/click-fix-735-r4-20261024.json` and ignored local artifacts
under `artifacts/development-735-r4/`.

Next: owner listening on Malachite; further profile/optimize the combined
four-track event/FX workload and six-VA attack path; repeat the unchanged reserve
gate with and without telemetry before release integration. Do not solve the
margin by silently removing effects, lowering polyphony or weakening the gate.
