# 734 release preparation verification

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
