# Local next-release development

Branch: `release/next-package-compat`. This branch is local only. No merge, push,
publication is authorized. The owner designated Malachite for development and
authorized its backed-up package installation and verification on22October.
Citrine remains the released-build reference; Amethyst remains the stockV16 reference.
The published `build-734-r5` downloads remain immutable.

## Companion r7 follow-up: instrument loadouts

The local r7 candidate adds ordered64-instrument profiles and independent DEFAULT
and USER assignments before installation or for bank-only deployment. Includes
Expressions A?D and Classic, preserving all published artifacts and firmware r3.
See [loadout workflow](LOADOUT_PROFILES.md). Owner curation and physical combined
install/deployment acceptance remain open. The r6 build below records the first
packaging increment, not the current Companion UI revision.

## First increment: self-describing firmware packages

Firmware734 **package r3** adds34 generated decoding/key-CRC bytes in the existing
protected-head padding. The FWSC checksums are rebuilt. Application and935 updater
bytes, saved-data layout, sound bank and total613169-byte package size are unchanged.
The unit continues to identify as `FM-1_734`; package revision is not a new musical
firmware version. No stock boot executable or private device data is included.

Companion734 **r6**, a local development candidate, prefers r3 and retains bundled
r2 support. Admission checks recognize only two exact generated heads and bind
release profiles to their expected header format. Wrong metadata, arbitrary boot
content, different updaters and changed protected layout remain rejected. The
existing updater continues to obtain the unit key from the unit and never writes
the first16KiB. Original-V15 recovery continues using the retained r2 baseline.

The Firmware page displays the included package revision; the offline handbook
explains old/new packages and browser-preview limits. Current factory libraries
remain unchanged; the192 Expressions candidates still await owner curation.

## Build and qualification workflow

For this metadata-only increment, start with the exact published r2 and run:

```powershell
python tools/stage_release_package.py --out artifacts/next-release-package/new-run --loader-test artifacts/publication-734-r5/export-loader/Release/fmer_portable_loader_test.exe --activate
```

Use a new output directory. The script verifies the baseline/updater pins, builds
r3, runs the independent C loader suite, validates an isolated two-package catalog,
and only then updates the local catalog when `--activate` is supplied. It refuses
to replace an existing firmware file with different bytes. The loader-test EXE is
local build output; rebuild it from `firmware/fm1/loader/tests` when needed.

Full source builds retain reproducibility of r2 with the existing default
`--package-format application-only-v1`. Select
`--package-format self-describing-v1` on `tools/build_release_firmware.py` to build
r3 from a qualified target ELF. Prefer `--stage-only` during development. The
staged catalog resolves packages relative to itself, without a bundled-file lookup.

After any reviewed change to a catalog-pinned admission/transport source, restage
and rerun qualification. Do not simply weaken or remove source-pin validation.

```powershell
python tools/dev.py check
python tools/dev.py test
python tools/build_companion_portable.py --out "FMER Companion 734 r6 Local Candidate"
python tools/test_portable_companion.py --zip "FMER Companion 734 r6 Local Candidate.zip" --out artifacts/next-release-package/portable-qualified
```

The ZIP includes the executable, embedded runtime, both firmware packages, current
default/OEM libraries, illustrated Help, licenses and corresponding source.
Building it never publishes or contacts a unit. Its manifest identifies revision6
and the `local-next-release` channel. This is a candidate for owner testing.

## Gates before replacing the public release

- Pass package/Companion regressions and portable deployment rehearsal.
- Install the exact candidate through Companion on a backed-up designated unit;
  verify boot/identity/calibration and user content preservation. Host fault
  simulation does not qualify a real-device installation.
- Test the unmodified browser emulator with the exact release candidate. Initial
  HOME/key/scope/audio evidence does not qualify all FX, sequencer, MIDI and save
  behavior. Browser saves are separate from device libraries.
- Triage beta feedback, document unresolved issues and agree the final sound bank.
- Export reviewed public source through the existing source-only mirror workflow;
  do not push the private development repository/history. Merge and release only
  when the owner requests it.

See [emulator research](../research/FM1_EMULATOR_COMPATIBILITY_2026-10-22.md) and
[beta feedback workflow](BETA_FEEDBACK.md). Exact build/test results are recorded
in `evidence/next-release-package-20261022.json` when this increment completes.
