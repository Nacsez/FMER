# FMER 735 / Companion r11

Six-voice playing, a broader sound library, and a more reliable Companion startup.
This is an unpublished release candidate for maintainer review. The numbered build
system continues; this is not a 1.0 declaration.

![FMER 735: 42 screen views](https://raw.githubusercontent.com/Nacsez/FMER/build-735-r11/docs/release/media/fmer735-screen-sheet.png)

## Downloads

- **FMER-Companion-735-Windows-x64.zip**: extract the entire ZIP and launch
  `FMER Companion.exe`. Windows 10/11 Intel/AMD x64; no separate Python install.
  Includes firmware, libraries, profile management and offline Help.
- **fmer735-compatible-r9.fwsc**: firmware alone, in the self-describing FWSC
  format. Use a compatible installer; file-format compatibility does not qualify
  every third-party flashing procedure.
- **FMER-735-Screen-Atlas.zip**: all 56 captured views, six social cards, and
  the 42-view overview in PNG/PDF. Screens use the production renderer with
  illustrative state, rather than photographs of the LCD.
- **FMER-735-Source.zip**: corresponding source, build instructions and notices.
- Separate screen-sheet PNG/PDF, default-sound catalog and SHA256 checksums.

## Instrument and performance improvements

- **6V polyphony** replaces 4V for single-instrument playing. 1V glide and four
  independent mono tracks in 4T remain available.
- **192 original Expressions instruments**, organized into four 64-instrument
  profiles: Spectrum, Rhythm, Voltage (leads/arps), and Atmosphere. Spectrum
  incorporates the owner's listening-survey favorites. Classic sounds and the
  separately attributed OEM V15 catalog remain available in Companion.
- **Two editable banks, A and B**, each holding 64 FM or VA instruments. Choose
  separate loadouts for each bank during installation or later library work.
  Custom profiles and named instrument setups support managing several units.
- Preset browsing follows bank order; curated instruments are grouped by sound
  family. The first octave shift now has a visible LED indication.
- Active-voice replacement and VA note-start changes address reported clicks.
  CPU optimizations retain the sample rate, synthesis arithmetic and effects.
  The qualified heavy four-track comparison used about 16.9% less processing
  than the earlier development baseline; dense workloads still need care.
- Self-describing packaging supports the unmodified FM1 emulator preview at
  60 MHz while preserving the protected boot region during FMER installation.

## Companion improvements

- Startup no longer lets an idle browser connection block delivery of the
  interface scripts. Application operations remain serialized.
- Clear loading/failure feedback and browser diagnostics replace a silent shell
  when initialization fails. The optional editor loads when opened.
- Missing-device messages explicitly describe the USB MIDI connection, rather
  than suggesting the sound library is missing. Discovery history is retained
  for troubleshooting.
- The owner's separate-computer retest initialized successfully, installed735,
  and verified all128 instrument writes with Rhythm in Bank A and Atmosphere in
  Bank B. A later probe found no FM-1 MIDI port; that was separate from the
  completed installation. See [returned-session QA](COMPANION_R11_QA.md).

## Installation and limits

Read [735 installation notes](INSTALLATION_735.md). Back up instruments and
projects before updating. Choose deliberately whether to retain or replace each
bank. The735 save format supports six voices; an automatic downgrade to733/734
is blocked until a separate migration is provided.

Bluetooth remains deferred. Windows x64 is the packaged Companion target.
USB audio is the combined mix, effects are shared across tracks, direct USB
links support one peer, TRS MIDI is input-only, and battery percentage is an
estimate. Unknown device layouts are rejected; stock V16 migration is not
qualified by this release. No universal flashing or dead-device recovery claim
is made. The full sound library and long-duration performance still benefit from
real-world testing.

FMER code, Companion, original instruments and artwork are GPL-3.0-only, with
included third-party notices. No private device dumps or vendor firmware
executables are distributed. Feedback is welcome through GitHub issues;
outside pull requests require prior maintainer permission.
