## Companion734 r3 candidate - 20 October 2026

The owner has locked firmware734-r2. This package revision changes Companion,
Help and release assets only. New custom-application support is bounded to the
reviewed935 updater and protected layout; the broader third-party installation
matrix is not hardware-qualified. The next owner acceptance session is still
required. Public visibility and release publication remain withheld.
[Current workflows and limits](COMPANION_R3.md).

# Release preparation — build 734

19 October 2026. The owner authorized uploading the reviewed source and assets to
the private Nacsez/FMER repository and creating a draft release. The repository
must remain private and the release unpublished for owner review. 734-r2 keeps the wire identity and700-series system, but replaces vendor runtime
archives with the reviewed source build. The exact tested package, corresponding
source, notices and Companion are refreshed together.

| Area | Status |
|---|---|
| Feature specification | Reconciled against source: 11 arp types, Phaser, 32 song entries per lane, 64-step patterns and shared effects. |
| Manual graphics | 31 annotated feature sheets, five workflow diagrams and one shortcuts sheet; production renderer/browser captures, with illustrative state identified. |
| Copy and video preparation | General descriptions, individual highlights, exact limits, eight video plans and short-form alternatives drafted. |
| Help integration | Sheets appear in related offline handbook topics and a searchable visual gallery. Parameter/menu references remain available. |
| Source/public metadata | Clean allowlisted export, public README/AGENTS, feedback template, ignore rules and file hashes; no existing private history exported. |
| Extracted target source | Source-built runtime and public configuration inputs reproduce the exact 734-r2 application and FWSC; all 34 extracted-tree CTest suites and 42 loader checks pass. External compiler/headers required. |
| Firmware and radio | Source-built734-r2 tested on Amethyst; Citrine retained as734-r1 reference. Bluetooth first after release and primary feedback; not advertised as working. |
| Automated verification | Full workspace regression passes; live Amethyst comparison and preservation pass. See VERIFICATION.md and the exact portable rehearsal referenced by the release manifest. |
| Publication | Nacsez/FMER: private upload and draft release authorized; public visibility and publication reserved for owner review. |
| Original splash artwork | Owner confirmed ownership and GPL-3.0-only permission on 19 October; original PNG, generator and source notice included in both source packages. |

## Gates before public binary distribution

The owner has selected GPL-3.0-only for original FMER firmware, Companion and
default instruments and the original splash artwork. Dependency notices remain in
force. The artwork permission item is closed; [ARTWORK.md](ARTWORK.md) records the
owner's grant and the delivered source form. The linked-runtime gap is addressed for734-r2 by licensed source replacement,
with the compiler external and public configuration-data provenance. Read the
[options and boundaries](RUNTIME_REVIEW_734.md). No vendor proprietary engine
or runtime archive is linked; no bespoke permission request was made.

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
