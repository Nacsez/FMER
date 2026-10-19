# FMER 734 — writing drafts

19 October 2026. Copy for owner review, based on the implemented 734 feature set.
Use the same build number for public testing; no separate beta firmware line is
introduced. Add the actual repository/download link after publication is approved.

## One line

FMER brings six-operator FM, Virtual Analog sound design and four-track performance
to the M-VAVE FM-1, with an offline companion for your sounds and projects.

## Short description

Turn an FM-1 into a portable synth and sequencer. FMER combines FM and Virtual
Analog engines, editable instrument banks, an arpeggiator, rearrangeable effects
and a four-track song workflow. Play a single sound with glide or four-voice
polyphony, build patterns on the unit, or synchronize two FMER instruments over
USB. The local Companion manages instruments, projects, backups and compatible
firmware installation without an account or hosted service.

## Longer introduction

FMER is alternative firmware for the M-VAVE FM-1, built around sound design and
hands-on performance. Its six-operator FM engine offers 32 algorithm diagrams,
operator envelopes and keyboard scaling. The Virtual Analog engine provides
sine, saw, square, triangle and noise waveforms with direct filter and envelope
controls. A set of 64 original sounds supplies a starting point, alongside 64
independent user slots. Both banks accept either engine.

Choose one instrument with glide, one instrument with four-voice polyphony, or
four independent mono tracks. Record notes or arpeggios into patterns, edit rests
and held notes, then arrange repeats and transpositions in Song mode. The mixer
keeps each track's volume, mute, solo, effect routing, sound and pattern close at
hand. Expanded oscilloscope views make the music visible while it plays.

Shape the result with a reorderable filter, reverb, delay, chorus, phaser and
drive chain. Store a preferred effect order, recall it, or start again from the
FMER default. Wired MIDI supports external control and clock synchronization;
a direct USB link lets two powered FMER units perform together.

FMER Companion runs locally on Windows 10/11 x64. Use it to organize sounds and
projects, exchange standard DX7 FM voices, back up a supported installation,
and install bundled or local firmware. The offline handbook includes annotated
screens, workflows, a complete parameter reference and a one-page shortcut guide.

## Public testing invitation

FMER is opening for public testing before 1.0. Try the parts that interest you:
sound design, navigation, effects, arpeggios, recording, arrangements, MIDI or
the Companion workflow. Tell us what you expected, what happened and which build
you used. You do not need to test every feature. Companion can export a diagnostic
summary for you to review and share. Feedback goes through the published issue
tracker; code contributions require prior maintainer approval.

## Feature highlights

| Feature | Copy suitable for a caption or post | Demonstration |
|---|---|---|
| Six-operator FM | Build bright bells, moving textures and basses from six operators and 32 visible algorithms. Shape each operator's envelope, tuning and response. | Play one phrase; change algorithm and modulator level. |
| FM envelopes | Shape loudness and harmonics separately. The ENV page works across carriers; EDIT opens the individual operator stages and keyboard scaling. | Compare a pluck and a sustained sound. |
| Virtual Analog | Start with sine, saw, square, triangle or noise, then sculpt the sound with a voice filter and envelope. | Use the same notes for a saw lead, a noise hit and a rounded bass. |
| Sound banks | Keep 64 editable defaults and 64 independent user sounds onboard. Either bank can hold FM or VA instruments. | Browse from FM to VA to USER, then save a variation. |
| Playing modes | Glide through a mono line, play four-voice chords, or give four mono tracks their own instruments. | Show the 1V, 4V and 4T header indicators. |
| Glide | Connect notes with Legato or Always glide and adjustable time and contour. | Hold a low note, add a higher note, then release it. |
| Filter | Sweep low-pass, high-pass or band-pass cutoff with a separate resonance control and directional visual shading. | Keep levels comparable while switching the three types. |
| Reverb | Choose Room, Plate, Hall or Cloud, then set the return and decay to fit the part. | Leave silence after each note to hear the tail. |
| Delay | Set an exact time in milliseconds or choose a beat division tied to tempo. | Compare free time with eighth-note and dotted repeats. |
| Chorus | Dream, Wide, Shimmer and Rush offer four motion characters from one amount control. | Play a sustained sound and vary the return amount. |
| Phaser | Drift, Sweep, Pulse and Storm add changing spectral movement. | Compare the four profiles on a harmonically rich sound. |
| Drive | Add distortion to the effect chain and move it before or after other stages. | Compare drive before and after the filter. |
| LFO | Keep modulation settings with the sound and toggle them from LFO or FX. | Hold a note; enable and disable the stored movement. |
| FX order | Rearrange six audio stages, save your own default chain and recall it on demand. | Move Delay relative to Reverb; show the chain changing. |
| Arpeggiator | Eleven types, including Played, Outside In and Strum, turn held notes into a part. Add octave range, latch, triplets, gate and swing. | Use one chord and change type. |
| Arp recording | Capture the generated arpeggio directly into a pattern, then edit the result as notes. | Record a short Strum phrase and replay it without held keys. |
| Recording | A four-beat lead-in supports quantized Overdub or Replace recording with rests and held notes. Step entry remains available. | Record a phrase with a deliberate gap and sustained ending. |
| Pattern editing | Move a note in time, change its held length, insert rests or ties, and copy sections without recording again. | Fix one note in an existing phrase. |
| Patterns | Build up to 16 patterns per project, each up to 64 steps. Reuse them across the tracks. | Switch between a short fill and a longer phrase. |
| Performance mixer | One knob per track controls the selected layer: volume, mute, solo, effects, sound, pattern or run state. | Bring drums and bass into a playing arrangement. |
| Song mode | Arrange patterns with transposition and repeats across four aligned lanes, or one active lane in single-instrument mode. | Repeat a bass pattern, transpose the next entry and show the blocks. |
| Live launches | Queue a selected track or all tracks for the next 16-step bar to bring an arrangement back together. | Queue the change, then let the downbeat land. |
| Visual feedback | Expand the main waveform or the four part traces and combined mix. | Press HOME again while the music continues. |
| Onboard saving | Store sounds and projects on the unit for standalone use. Companion adds organization and backup when a computer is useful. | Save, reload and play a project. |
| Wired MIDI | Receive notes and controls, send generated parts, and synchronize to an external clock. Split or merge track MIDI channels. | Record the four tracks into separate DAW MIDI channels. |
| Two-unit USB link | Connect two powered FMER units directly over USB and choose clock, notes or both. | Start and stop a paired performance from the leader. |
| Battery display | Read an estimated battery percentage in the header, with low-battery highlighting. | Show the status legend alongside the header. |
| Companion library | Organize instruments and projects with collections, tags, favorites, duplicate, move and Trash/Undo. | Make a small set for a performance. |
| DX7 interchange | Import and export standard DX7 FM voices and banks, with conversion limits made explicit. | Review an import and save a separate copy. |
| Backup and restore | Keep dated musical backups for each supported FMER unit and review the restore scope before writing. | Show two clearly named backup archives. |
| Local installation | Extract the portable Windows package and launch Companion. Firmware, original libraries and help are included. | Show the included-firmware inspection and progress flow. |

## Exact specification and wording guardrails

- Four simultaneous voices total; 4T is four mono parts, not four polyphonic synths.
- Six-operator FM with DX7-style interchange; do not promise exact DX7 emulation.
- DEFAULT starts with 32 FM + 32 VA sounds. The USER bank begins as independent
  copies. Reset DEFAULT, Reset USER and Clear USER are distinct operations.
- The effect is **Phaser**, not Flanger. LFO is modulation, not a seventh chain stage.
- There are **11** arp types: Up, Down, Exclusive, Played, Inclusive, Random,
  Repeat, Down Exclusive, Down Inclusive, Outside In and Strum.
- Patterns have 1–64 steps. Song has **32 entries per lane**, each with 1–32 repeats
  and −24 to +24 semitone transposition; do not call this a 64-entry song.
- Projects reference instrument-bank slots. Save the sounds as well as the project.
- Shared effects with per-track routing, not four independent effects processors.
- TRS MIDI is input-only. Direct USB supports one peer. Bluetooth is deferred.
- USB audio is the combined mix; separate USB audio stems are not implemented.
- Battery percentage is an estimate. Green indicates USB data connection, not
  measured charging current or guaranteed remaining runtime.
- Companion uses bundled/local firmware; automatic update downloading is absent.
- Installation checks supported layouts. Avoid “any firmware,” “all units,”
  “unbrickable,” “zero latency,” or other unqualified reliability claims.
- Windows 10/11 x64 is the portable release target. No macOS/Linux binary is promised.
- Public feedback is welcome; a beta label does not remove distribution obligations.

All feature copy should travel with the actual build number. Do not use private
stock patches, ROMs, owner songs or third-party demo music as promotional assets
without separate permission. No subjective sound-quality ranking is presented
as a measured result.
