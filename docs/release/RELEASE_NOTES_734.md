# FMER 734

![FMER: six-operator FM, Virtual Analog and four-track performance](https://github.com/Nacsez/FMER/blob/build-734/docs/release/media/fmer-overview.png?raw=true)

FMER brings six-operator FM, Virtual Analog sound design and four-track performance
to the M-VAVE FM-1, with an offline Companion for your sounds and projects.
Build 734 is the current tested pre-1.0 build. This release remains a private
draft until the maintainer finishes review and chooses to publish it.

## Choose your download

| Asset | What it contains |
|---|---|
| **FMER-Companion-734-Windows-x64.zip** | Extract-and-run Windows app, embedded runtime, firmware installer, 64 original sounds, library tools, offline Help and corresponding source. |
| **fmer734-compatible-r1.fwsc** | Firmware alone, in FM-1 FWSC update format. Same bytes as Companion. Third-party installer caveats are in the installation guide. |
| **FMER-734-Source.zip** | Reviewed source tree, original splash, original patch recipes, build scripts and dependency notices. |
| **FMER-734-Press-Pack.zip** | Original logo, exact screen captures, 36 annotated sheets/workflows, PDFs, feature descriptions, copy and video drafts. |
| **FMER-734-Feature-Overview.pdf** | Two-page introduction and feature summary. |
| **FMER-734-Visual-Guide.pdf** | The complete 36-page annotated screen and workflow guide. |
| **FMER-734-Shortcuts.pdf** | One-page shortcut sheet. |
| **INSTALLATION.md**, **SHA256SUMS.txt**, **release-manifest.json** | Installation instructions, exact download hashes and source/binary correspondence. |

[Installation and compatibility](https://github.com/Nacsez/FMER/blob/build-734/docs/release/INSTALLATION.md)
· [Complete feature tour](https://github.com/Nacsez/FMER/blob/build-734/docs/release/FEATURES.md)
· [Feedback](https://github.com/Nacsez/FMER/issues/new/choose)

## Two engines, three playing modes

- Six-operator FM with 32 algorithm diagrams, operator envelopes and standard
  DX7 voice/bank interchange. Exact DX7 emulation is not claimed.
- Virtual Analog with sine, saw, square, triangle and noise.
- 1V glide, 4V polyphony, or four independent mono parts in 4T.
- 64 editable DEFAULT instruments plus 64 USER slots; either engine in either bank.

![FM sound design](https://github.com/Nacsez/FMER/blob/build-734/docs/release/media/feature-fm-synthesis.png?raw=true)

## Sound shaping and performance

Reorder six shared effects: low/high/band-pass filter with resonance, Room/Plate/
Hall/Cloud reverb, beat-synced or millisecond delay, four chorus profiles, four
phaser profiles and drive. Store your preferred chain. Keep LFO settings with
each sound and toggle modulation directly.

![FX routing](https://github.com/Nacsez/FMER/blob/build-734/docs/release/media/feature-fx-routing.png?raw=true)

## Patterns, songs and live control

- 11 arp types, including Strum; latch, octave range, gate, swing and triplets.
- Record played notes or generated arpeggios with a four-beat count-in,
  Overdub/Replace, rests and held notes.
- 16 patterns per project, up to 64 steps each; 16 onboard project destinations.
- Four-track mixer with volume, mute, solo, FX routing, pattern, patch and run state.
- Song mode: 32 entries per lane with repeats and transposition. Single-instrument
  sequencing remains available alongside live playing within the four-voice budget.
- Next-bar launches, expanded waveforms and direct performance shortcuts.

![Song mode](https://github.com/Nacsez/FMER/blob/build-734/docs/release/media/feature-song.png?raw=true)

## Wired MIDI and local library management

Send and receive USB MIDI, control patches and documented parameters, follow an
external clock, split generated tracks across MIDI channels, or directly link two
powered FMER units over USB. TRS MIDI is input-only. Bluetooth is deferred.

Companion organizes local sounds/projects, imports and exports DX7 FM voices,
backs up supported FMER units and installs compatible firmware. Everything runs
on your computer; no cloud account or hosted page is required.

![Companion library](https://github.com/Nacsez/FMER/blob/build-734/docs/release/media/feature-companion-library.png?raw=true)

## Testing and feedback

Feedback is welcome on installation, Companion, navigation, sounds, effects,
arpeggios, sequencing, playing modes and MIDI. Test only the areas that interest
you. Use **Beta feedback** in Companion to export an optional diagnostic summary,
review it, and attach it to an issue with your observations. Nothing uploads
automatically. Outside code pull requests require prior maintainer permission.

Four voices are shared across the instrument; effects are shared across tracks.
Battery percentage is an estimate. Unknown firmware layouts cannot be forced
through the installer. Loaded-audio reserve, USB-audio endurance and the wider
recovery matrix remain qualification limits. Firmware bytes are unchanged from
the tested 734 installation; this package refresh adds release media and corrects
the version labels in exported Companion feedback.

Original FMER software, defaults and splash are GPL-3.0-only. Felucca supplies
incorporated board support; MSFA supplies the FM foundation; the updater derives
from SLOOP. Their notices remain included. See LICENSE, LICENSING.md and NOTICE.

**Maintainer review before publication:** linked vendor-runtime distribution/source
terms remain unresolved. Keep this release draft and the repository private until
that review is complete. No automatic publishing workflow is installed.
