# FMER and the browser FM-1 emulator

## Implementation follow-up: local release branch

`release/next-package-compat` now implements this as734 package r3 with Companion
r6. The exact generated613169-byte package was loaded on the unmodified website
at60MHz; HOME/key/scope behavior matched the earlier proof. This remains a smoke
check, not full emulated feature qualification. Publishedr2/r5 remain unchanged.
See [next-release workflow](../release/NEXT_RELEASE.md) and the dated next-package
evidence for loader, deployment and Malachite qualification.

## Follow-up: package-side compatibility is viable

The owner's follow-up prompted a direct test of a valid, repacked FWSC on the
**unmodified public website**. This succeeds: HOME, key lighting and the scope
respond at60MHz. Unlike the initial browser interception below, this candidate
has rebuilt package checksums and needs no page modification. Its34-byte synthetic
key/CRC record occupies existing padding at flash14544..14577. Package size stays
613169 bytes; the application region and updater remain byte-identical.

This revises the initial preference below: **a self-describing FMER package is a
reasonable next-release improvement**, without waiting for an emulator change.
Both files already use FWSC; this fills missing metadata rather than changing the
synth/storage format. No vendor boot executable, private identity or calibration
payload is added. No application/RAM/CPU/voice/preset capacity cost is introduced.

Remaining work is packaging qualification: retain the existing release, update
Companion's exact header/hash/profile validation to admit the new reviewed header
while retaining old-package support, run protected-region and interrupted-write
regressions, and qualify installation/readback. The existing935 updater reads its
decoding key from the device and never writes the first16KiB; adding a record to
the package does not require changing that rule. Released Companion intentionally
rejects the new header today. Do not relax validation to arbitrary headers.

This record is decoding metadata, not a complete factory boot/config image. Do
not claim compatibility with installers that overwrite the whole device, or all
other installer platforms, from the emulator result. Full emulator musical/save
qualification also remains open.

Local candidate: `artifacts/emulator-20261022/synthetic-key-original.fixture`
(research-only; not an approved installation download). SHA256:
`607a6d60cc87071bfdbd21a03d9e9f014dd0951fb4d4d1c11a3a3374eacb9b35`.
Comparison: `package-format-comparison.json`; browser probe: `format_probe.py`;
output/screenshot: `metadata-package-60.json` / `metadata-package-60-note.png`
in the same directory. No firmware or Companion source/release changes, device
flashes or publications were made in this follow-up.

The following sections preserve the initial investigation and recommendation;
this follow-up supersedes its preference for an emulator-only fix.

Date: 22 October 2026. Scope: published FMER734-r2, browser emulator and offline
loader diagnostics. No physical device, release artifact or firmware source was
changed. The public website has not been updated by this work.

## Result

The immediate failure is a **package-loader assumption**, not an observed FMER
synthesis or CPU incompatibility. The website rejects the package before running
its application. A browser-only experiment supplying synthetic decoding metadata
boots the unchanged application, draws HOME, responds to keys and generates
nonzero digital audio for a single note and four keys at 60 MHz.

Recommend adding application-only package support to the emulator, keeping the
published FMER firmware unchanged. A local candidate Rust loader patch accepts
the original release file without modifying it and extracts exactly the expected
application bytes. This is promising smoke evidence, not full emulator support.

## Reproduction and cause

1. Open <https://joakimeriksson.github.io/fm1-emu/?fw=local&mhz=60> in a fresh
   Chrome context; choose `fmer734-compatible-r2.fwsc`; press Start.
2. The page reports `boot: Error: not an FM-1 update package (or a DX7 bank it cannot use)`.
3. The exact pinned Rust unpacker gives the more useful underlying error:
   `app area runs past the flash image`.

FMER's package contains generated top-level directory descriptors, but fills the
protected boot/configuration payload at flash offsets160..0x3fff with0xff.
`tools/release_firmware.py::distribution_head()` constructs this deliberately;
updater935 preserves the existing unit's boot/calibration/identity region.
The firmware does not require shipping another manufacturer's boot executable.

The emulator's `fwsc.rs::unpack_n()` expects `isd_config.ini` to supply the SFC
decoding key. It permits an unchecked key as a compatibility fallback for some
other packages. For FMER, the erased bytes yield0xffff, while the public FMER
application packing key is0x980f. Decoding with the wrong key produces a bogus
application-area size. `fm1_boot_fwsc()` discards the specific error and the page
reports the generic package error above. The JavaScript `appFromPackage()`
extractor separately rejects FMER because the absent key record fails its CRC.
The active browser boot path uses the Rust/WASM loader.

This failure occurs before CPU execution. Changing `mhz=60` cannot fix it.
Also, `fw=local` does not identify or fetch FMER; a file must still be selected.

## Evidence

| Check | Observed result | Limit |
|---|---|---|
| Public website, original package | Reproduced rejection | No application execution |
| Pinned original Rust unpacker | Wrong-key path produces extent error | Loader only |
| Candidate Rust patch, original package | Accepted; extracted padded app SHA matches release | Not compiled into the deployed website |
| Browser-only synthetic key metadata | HOME, scope and key response; nonzero audio | In-memory experiment, not a distributable update |
| Single note / four keys / release | Peaks0.017456 /0.053467 /0; CPU not halted | Default FM Keys only; not a listening-quality judgment |
| Audio short-quanta counter |93 after startup; unchanged through measured notes/release | Startup was not glitch-free; no full performance qualification |
| Loader regression cases |7/7 expected outcomes; upstream container unit test1/1 | Synthetic normal-key fixture, not a stock firmware matrix |

The browser experiment intercepts the page's boot message and provides34 synthetic
key/CRC bytes in its in-memory package copy. It neither modifies the application
nor writes a new installable package. Its containing flash-file checksum is not
rebuilt; the emulator does not check that checksum. This is a diagnostic bridge,
**not** a proposed distribution format or installer workaround.

The separate native patch tests use the **unchanged valid release package**.
The patch detects the erased protected payload and expected app-area location,
uses the known public packing key, and validates application header CRC, area CRC,
application extent and application CRC. It rejects damaged headers/apps and
does not apply that fallback to a nonblank protected payload. Existing normal-key
handling is retained. Further parser hardening and upstream review remain useful.

## Recommended path

1. **Preferred: emulator loader support.** Review the candidate Rust fallback,
   update the JavaScript extractor consistently, and surface actual loader errors.
   Rebuild WASM and test the original FMER download directly. No FMER DSP or
   on-device memory change is needed for the demonstrated blocker.
2. **Optional development preview.** If upstream integration takes time, maintain
   a clearly separate local emulator profile that supplies decoding metadata.
   Prefer emulator configuration over another flashable-looking firmware file.
3. **Do not change the stable release packaging solely for this.** Reintroducing
   boot payloads would cross a deliberately established distribution and recovery
   boundary. A future synthetic metadata format would need installer preservation
   tests and a new version; it offers little advantage over fixing the loader.

Before claiming support, test FM/VA patch browsing, worst-case chords/FX, all
sequencer modes, timing, saves/reloads and MIDI against real-device behavior.
The emulator also initializes a stock-style USR bank and supports DX7 loading;
those assumptions must be checked against FMER's own storage layout before using
its bank-import/save features. Browser MIDI input is not proof of USB audio,
USB host linking or physical MIDI transport emulation. No hardware performance
or recovery conclusion follows from browser success.

No upstream issue, message, PR, release or public upload was made. No browser
hardware permission was granted. All isolated browser processes were closed.

## Pins and reproduction records

- Upstream: [joakimeriksson/fm1-emu](https://github.com/joakimeriksson/fm1-emu),
  MIT, commit `db8d472e62f35d18e392e3abc66474daed65ffe9`.
- [Rust loader](https://github.com/joakimeriksson/fm1-emu/blob/db8d472e62f35d18e392e3abc66474daed65ffe9/crates/fm1-soc/src/fwsc.rs)
  and [browser boot wrapper](https://github.com/joakimeriksson/fm1-emu/blob/db8d472e62f35d18e392e3abc66474daed65ffe9/crates/fm1-web/src/lib.rs).
- FWSC SHA256: `a953cd928543a333b9065e911b8b452757fce71944d4344cc8cb7c0e1b4e5e41`.
- Extracted padded application SHA256:
  `8c8f9342cb3095d83160e6e2fbd239aa7babc38a3126c752718fa83670d38c61`.
- Machine-readable receipt: `evidence/fm1-emulator-20261022.json`.
- Local research directory: `artifacts/emulator-20261022/` contains pinned source,
  `probe.py`, `prepare_patch.py`, `test_loader.py`, the candidate
  `fm1-emu-application-only.patch`, JSON logs and screenshots.
- `unpack.exe` is the pinned upstream module compiled directly with rustc;
  `unpack_patched.exe` is the same module plus the local candidate patch. No
  upstream build script or downloaded executable was run.

Reproduction commands from the repository root (source acquisition is separate):

```powershell
python artifacts/emulator-20261022/prepare_patch.py
rustc --edition=2021 -A dead_code artifacts/emulator-20261022/unpack.rs -o artifacts/emulator-20261022/unpack.exe
rustc --edition=2021 -A dead_code artifacts/emulator-20261022/unpack_patched.rs -o artifacts/emulator-20261022/unpack_patched.exe
python artifacts/emulator-20261022/test_loader.py
python artifacts/emulator-20261022/probe.py
python artifacts/emulator-20261022/probe.py --synthetic-key
```

Browser probes require the existing Playwright/Chrome installation and internet.
They use fresh, disposable browser contexts, never the owner's browser profile.
