# Release preparation — build 734

19 October 2026. The owner authorized uploading the reviewed source and assets to
the private Nacsez/FMER repository and creating a draft release. The repository
must remain private and the release unpublished for owner review. Firmware bytes,
wire identity and the 700-series build system are unchanged. Companion feedback
export version labels are corrected to734; the source and media package is refreshed.

| Area | Status |
|---|---|
| Feature specification | Reconciled against source: 11 arp types, Phaser, 32 song entries per lane, 64-step patterns and shared effects. |
| Manual graphics | 30 annotated feature sheets, five workflow diagrams and one shortcuts sheet; production renderer/browser captures, with illustrative state identified. |
| Copy and video preparation | General descriptions, individual highlights, exact limits, eight video plans and short-form alternatives drafted. |
| Help integration | Sheets appear in related offline handbook topics and a searchable visual gallery. Parameter/menu references remain available. |
| Source/public metadata | Clean allowlisted export, public README/AGENTS, feedback template, ignore rules and file hashes; no existing private history exported. |
| Extracted target source | Compiles and links with pinned external toolchain; all three loadable ELF sections match qualified734 byte-for-byte. Whole-file metadata differs. No device write. |
| Firmware and radio | Qualified734 firmware retained. Bluetooth first after release and primary feedback; not advertised as working. |
| Automated verification | See VERIFICATION.md and the local release manifest; no new physical-device qualification is implied. |
| Publication | Nacsez/FMER: private upload and draft release authorized; public visibility and publication reserved for owner review. |
| Original splash artwork | Owner confirmed ownership and GPL-3.0-only permission on 19 October; original PNG, generator and source notice included in both source packages. |

## Gates before public binary distribution

The owner has selected GPL-3.0-only for original FMER firmware, Companion and
default instruments and the original splash artwork. Dependency notices remain in
force. The artwork permission item is closed; [ARTWORK.md](ARTWORK.md) records the
owner's grant and the delivered source form. One material distribution review
remains unresolved in the existing record:

- Redistribution/source basis and GPL compatibility of the exact linked vendor
  runtime libraries. The target links `libc`, `libm` and `compiler-rt`; having the
  compiler locally or pinning archive hashes does not settle that review.

Source-rebuild results should be read at their actual scope: an extracted-tree
build on the development computer is not a clean Windows VM or universal binary
reproducibility qualification. Keep second-computer installation evidence separate
from source reconstruction and from physical audio/reliability tests.

Retained qualification limits include loaded audio reserve, long transport/power
endurance, optical display behavior and the complete recovery/starting-firmware
matrix. Public feedback can help prioritize these, but cannot turn an untested
transport or installation path into a supported claim. The portable release is
Windows10/11 x64; macOS/Linux and Bluetooth are deferred. Unknown layouts are
rejected before application writing.

## Requested feature list corrections

The named modulation stage is Phaser, not Flanger. Resonance emphasizes the cutoff
region; it is not a separate frequency parameter. LFO is a stored modulation
source rather than a seventh reorderable audio stage. Song has 32 entries per
lane with repeats/transposition; the 64 limit refers to pattern steps. Companion
installs bundled or local files and does not automatically download updates.
Battery percentage is an estimate; its USB color does not measure charger current.

Use MARKETING_COPY.md for publishable descriptions and the exact limits. The
visual guide is a manual aid: waveform captures are illustrative inputs rendered
by production code, not a new recorded performance or a physical LCD photograph.
