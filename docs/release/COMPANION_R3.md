# Companion 734 r3 / release-candidate workflow

20 October 2026. Firmware is locked at **734-r2**, SHA-256
`a953cd928543a333b9065e911b8b452757fce71944d4344cc8cb7c0e1b4e5e41`.
This revision changes Companion, its tests, documentation and release packaging.
It does not change the musical application, original sounds or updater binary.

## Updating software and sounds

**Updates & downloads** in the sidebar opens the project's GitHub releases.
Firmware also has **Download updates**; Library links to updates and sound packs.
These are explicit browser links, not background downloads or automatic installs.
The private repository still requires access until the owner makes it public.

Quit Companion before extracting a new ZIP into a new folder. Start
`FMER Companion.exe` in that folder. Libraries, backups and logs remain in
`%LOCALAPPDATA%/FMER/Companion`; do not overwrite this directory with program files.
The release manifest and SHA256SUMS identify the exact program/firmware pair.

The separate **FMER-734-Default-Sounds.fmer-catalog.json** download contains the
same 64 original sounds as the portable application's Libraries folder. Library
**Import file** merges catalog/sound-bank copies without replacing existing items.
A sound-bank file imports both populated PC banks; **Restore PC banks** instead
replaces those PC banks. Standard DX7 single voices and 32-voice banks use
**Import DX7 FM**, with explicit conversion limits.

Select a Library instrument, change **Instrument name on unit**, and choose
**Save name & details**. This changes the saved ten-character ASCII name; the
longer **Library title · computer only** is separate. Then send the renamed
instrument to a chosen unit destination. Existing onboard names can also be
changed from **FM-1 → Unit instruments → Apply rename**.

## Reviewed deployment

- Library: **Send selected to unit** chooses a destination for every item.
- PC sound banks: **Send sound to unit** or **Send this bank to unit**. DEFAULT
  maps to onboard DEFAULT and USER to onboard USER, despite opposite raw ordering.
- Project details: **Send project with sounds** includes embedded snapshots at
  their referenced slots. They are PC snapshots, not a fresh unit readback.
- A normal project transfer sends only the project. It does not implicitly
  replace referenced instruments.

The review lists every name and destination. Instrument-only sets can be placed consecutively into USER or DEFAULT from a chosen starting slot; the selector prevents crossing a bank boundary. Project bundles retain reference-based destinations. Duplicate destinations, invalid
records and a changed confirmation are rejected before opening MIDI. The complete
unit is backed up durably before the first write. Instruments are written before
projects, with the existing bridge's exact readback verification. Working state
is restored afterward with transport stopped. The backup downloads on success;
failed jobs retain the backup path and verified completion list in diagnostics.
The operation banner also offers **Download pre-transfer backup**, including
after an interrupted write, so recovery does not require finding an AppData file.
No automatic retry or atomic rollback is claimed. Empty PC slots leave hardware
slots unchanged. Other projects retain their slot references.

Manage one USB-connected instrument at a time. Rename downloaded backups for the
instrument/date. Port numbers and identical MIDI names are not permanent unit IDs.

## Firmware compatibility boundary

There are two distinct questions: whether the **currently installed** firmware
can hand control to the updater, and whether a **replacement file** uses a
supported write procedure. A valid FWSC extension/checksum answers neither alone.

The included release stays hash-pinned. A custom application is now accepted by
the separate `fm1-935-application-v1` profile when all of these hold:

1. Valid, canonical two-file FWSC envelope and `FM-1_` numeric identity.
2. Exactly the reviewed **ota-FM-1_935** loader bytes.
3. Public boot descriptor sentinel, application extent `0x4000..0x93000`, and
   the same app slot, configuration, calibration, padding and partition metadata.
4. Only application bytes and their two affected directory CRC pairs differ.
5. Valid target entry instruction and matching application identity string.
6. Revalidation immediately before device access; the device still performs its
   independent flash/key/layout/calibration/staging checks before application writes.

The application must retain a discoverable FM-1/FMER-compatible USB MIDI endpoint
(the supported product names include `FM-1`, `FM-1 Midi`, `FMER`, and `FMER Midi`),
the normal identity reply and the two-stage updater handshake. The desktop cannot
prove those runtime behaviors from a string embedded in an image; installation
completion still requires the expected identity to return.

This broadens application admission without changing loader write boundaries.
The file is labeled **custom application**, with a separate confirmation warning.
It is not an FMER quality endorsement, signature/authenticity check or promise
that the application interprets saved projects in the same way. Only install
trusted firmware. Library management still requires FMER 733/734.

Existing alternate firmware packages generally carry their own updater and may
use other layouts. They are not automatically compliant. Companion explains the
rejection and offers no force option; use the publisher's installation procedure.
The newly published M-VAVE V15/open V13 layouts still need separate migrations.
No untested third-party application was installed on an owner's instrument in
this pass. Custom-profile validation is host evidence; retained physical install
evidence applies to the unchanged included FMER package.

The existing pinned SLOOP installer/protocol source reviewed in
[INSTALLATION.md](INSTALLATION.md) explains why FWSC is an envelope containing
an executable updater. The compatibility policy here comes from our own package,
loader and protected-layout audit; it is not a claim that SLOOP or another
publisher has qualified this new Companion workflow.

## Verification and limits

Regression coverage includes a changed-application identity with the exact
loader/layout; changed boot metadata, payload CRC, write extent and report
tampering; batch cancellation, duplicate destinations, invalid trailing records,
durable backup before writes, partial failure without retry, dependency ordering,
working-state restoration and local import Undo. Browser tests exercise the actual
review screens and HTTP boundary with device operations mocked.

The exact portable ZIP must also pass extraction, launch, offline content,
firmware inspection and lifecycle checks before draft staging. This does not
replace the owner's next clean-computer and hardware acceptance session.
Bluetooth, universal firmware recovery, macOS/Linux device binaries and automatic
downloads remain outside the release. Existing audio/endurance limits still apply.
