# Current Companion 734 r5 verification

21 October 2026. Firmware remains the exact 734-r2 package. The returned-PC
installation, backup and restore succeeded; the stale PC-bank save issue was
reproduced and corrected. See [r5 QA](COMPANION_R5_QA.md). The workspace regression
completed 1,101 Python cases with 19 explicit skips; browser coverage includes
conflicting saves, cancellation and preservation of edits. The portable package
passes 11 extraction/lifecycle/content checks, including all 128 OEM voices.
The current draft manifest binds the final package to its exact rehearsal hash.
No hardware is accessed during this publication preparation. Historical results
below describe their dated builds and are not new test claims.

## Companion734 r3 verification - 20 October 2026

Firmware734-r2 and its updater are unchanged. No instrument was opened or flashed.
The workspace suite completed1,086 Python cases (1,069 pass,17 explicit skips)
and all34 compiled/host suites. All34 suites also pass from the fresh source
export. The exported target/package build reproduces the exact locked FWSC;
all42 independent loader checks pass. Eleven new boundary/transfer tests pass,
including a validly repacked but unapproved updater rejection. The actual browser
suite covers reviewed bank/set transfers, duplicate destinations, cancellation,
bank-file imports with Undo, partial-write explanations and backup download.

The37-sheet visual guide renders without script errors or text overflow.
[Sanitized verification](companion-r3-verification.json) records the scope and
source hashes. Portable ZIP lifecycle evidence is bound by the final asset manifest;
no new third-party application or batch transfer on physical hardware is claimed.
The owner's next Companion/hardware acceptance remains separate.

# 734-r2 runtime release verification

19 October 2026. This revision replaces the vendor runtime archives and private
packaging reference. The musical application and updater write policy are unchanged.
The current firmware package is `fmer734-compatible-r2.fwsc`, SHA256
`a953cd928543a333b9065e911b8b452757fce71944d4344cc8cb7c0e1b4e5e41`.
See [the runtime review](RUNTIME_REVIEW_734.md) and
[sanitized evidence](runtime-verification.json) for scope, source pins and limits.

| Check | Result |
|---|---|
| Complete workspace regression | 1,075 Python tests: 1,058 pass, 17 explicitly skipped; all 34 compiled/host suites pass |
| Runtime behavior | 1,172,204 checks pass on the host; target code generation is tested separately |
| Extracted source | Fresh source tree builds; all 34 CTest suites pass |
| Extracted target | Default source-runtime build succeeds with external pinned compiler/headers; entire application payload matches the tested build |
| Extracted installer | Produces the exact current FWSC hash, without private ROM or vendor runtime archives; all 42 independent loader checks pass |
| Live Amethyst regression | Before/after 64 preset cases and 35 chord/effect cases pass; no new audio overruns, MIDI overflow, rejected messages, crash, load shed or LCD timeout |
| USB audio and MIDI | 100-second PCM capture before/after; eight MIDI cases pass; no analog listening or long endurance claim |
| Saved data | All 128 instrument slots, 16 project destinations and default FX order compare equal; working state and MIDI settings restored |
| Navigation | Five mode/navigation/route-save cases pass |
| External installer format | Pinned SLOOP parser accepts the exact r2 package without force, matches logical bytes/identity and rejects corruption; no external installer wrote hardware |

The exported ELF hash is
`4551464a20a336770ac81b5f56a291e5c3139891b60654e9cb7baa926f10e5b9`;
the live-tested ELF hash is
`263c5c2fa278a4d117d3d2985c91a5db89ffc8a1ac064770d6c31386df730f58`.
Non-payload ELF metadata differs. Both produce the same 214,720-byte application,
SHA256 `7fe7aeff7469756a2af456f317d13d85324d4860c60825cee8ecd812f06de647`,
and the same final FWSC bytes. This is a development-computer reconstruction,
not an independent clean-machine or cross-compiler reproducibility claim.

The exact Companion ZIP must pass the ten launch/lifecycle/content checks before
release staging accepts it. The accompanying release manifest records that ZIP
and rehearsal evidence by hash. Checks cover extraction with spaces, isolated user
data, bundled runtime, Help, firmware inspection, notices/source, default-library
rendering, quit/relaunch, idle-server replacement and last-tab shutdown. No device
is opened by that rehearsal. This separates package verification from the live
Amethyst installation above. Citrine remains the prior runtime reference.

The public repository stays private and the release stays draft. Source provenance
does not expand installation compatibility or waive remaining performance,
power/endurance, listening and recovery-matrix qualifications.

## Earlier 734-r1 documentation/package rehearsal (historical)

19 October2026. No device was opened or flashed during this documentation and
packaging pass. Existing firmware payload remains
`204a292ea499af8ac157024510c8324199fe950912f45c4a03fe93bd55cbecd9`.

## Screens and media

The new capture executable uses the production firmware renderer and existing
mock LCD/DMA implementation. Each captured frame is compared with the complete
reference frame before export. The fixtures show illustrative parameter, pattern
and waveform states. Screens are not reconstructed with a drawing or image model.

All36 SVG sheets render without browser errors or text outside the canvas.
Embedded PNG bytes match the source image hashes. The combined PDF has36 pages;
the shortcut PDF has exactly one. Manual review corrected mismatched sequencer
page captions and aimed pointers at the corresponding controls. The full Help
still defines198 canonical parameters and45 panel pages.

The first aggregate test found a real generator contract failure: the new gallery
was linked from Help but was not returned as one of the Help generator's outputs.
It was available on disk, yet a clean generated Help set was incomplete. The
gallery is now part of the generator's output set. The failure and its log are
retained; it is not described as an initial clean pass.

## Extracted source

A fresh source-only tree configured and built with the installed CMake/MSVC
toolchain. All33 compiled/host CTest suites passed. A separate target build used
the pinned compiler and libc++ headers supplied from outside the exported tree.
Source pin validation remained enabled. The initial restricted compiler invocation
failed with “couldn't get arguments: permission denied”; a reviewed compile-only
retry succeeded.

| Loaded ELF section | Bytes | Comparison with qualified734 |
|---|---:|---|
| .text |209604| Identical |
| .ram_text |2840| Identical |
| .data |2084| Identical |

Qualified ELF SHA256:
`cbf11b610b6b6eb01f8f3ad101632c86dc3345a78e856ec8fc60f2bf39c7e2f5`.
Reconstructed ELF SHA256:
`b8e374ac00fd4d20838f6cbbb3b6abb2856c305fec9722513cebe04f9d66e6a3`.
The complete files differ outside the loadable sections. This is a successful
source reconstruction on the development computer, not a clean VM or whole-file
bit-identical build claim. It does not settle vendor-library licensing.

## Packaged app and scope

The portable rehearsal extracts into a path with spaces, uses isolated user data
and a minimal PATH, checks every manifest hash, and launches the bundled EXE and
Python runtime. It exercises firmware inspection without hardware, local Help and
figures, GPL/notices/source presence,64-default import and audible host rendering,
quit/relaunch preservation, replacement of an idle older server, and last-tab
shutdown. Version734 is unchanged; package hashes identify the Help refresh.

The final local evidence index and TEST_REPORT.md retain exact run/package hashes.
No connected-unit backup, flash, radio, physical audio or endurance qualification
is claimed by this pass. Distribution and remaining hardware gates are listed in
RELEASE_READINESS.md.
