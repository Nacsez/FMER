# Installing FMER 734

Download files only from [Nacsez/FMER releases](https://github.com/Nacsez/FMER/releases).
This release is currently staged privately as a draft for owner review.

## Companion: the qualified installation workflow

1. Download **FMER-Companion-734-Windows-x64.zip** on Windows 10 or 11 x64
   (Intel/AMD). Extract the entire ZIP, keeping its folders together.
2. Double-click **FMER Companion.exe**. Its interface opens in your local browser.
   Runtime, firmware, original instruments and offline Help are included. No
   separate Python installation, account or hosted website is needed.
3. Connect one powered-on FM-1 using a USB data cable. Close other applications
   using its MIDI ports. Select **Check connection**.
4. Back up an existing FMER installation from **Backups**. Stock firmware does
   not expose FMER's musical-backup protocol; existing stock patches are not
   automatically imported or backed up by this action.
5. Open **Firmware**, inspect the bundled FMER 734 image, then start installation.
   Keep power and USB connected and the controls untouched while progress is shown.
6. Completion requires the unit to restart and identify as **FM-1_734**. A timeout
   is not success. Follow the displayed recovery instructions and export diagnostics
   if installation stops; do not bypass a compatibility refusal.

The application is unsigned. The ZIP contains a portable launcher and the
firmware installer inside Companion; it is not an MSI or a system-wide setup wizard.
Your library and diagnostics remain in your Windows user-data directory.

## Firmware-only download

**fmer734-compatible-r2.fwsc** is the actual firmware update package, identical
byte-for-byte to the one bundled in Companion. It is a standard FM-1 FWSC package
with a guarded update loader; it is not a raw flash dump or a desktop executable.

SHA-256: `a953cd928543a333b9065e911b8b452757fce71944d4344cc8cb7c0e1b4e5e41`

The package uses the two-stage FM-1 USB-MIDI update flow: stage the updater,
reconnect to it, transfer the application, then verify the restarted identity.
The target independently checks the supported memory layout and calibration
before application writing. Unsupported layouts remain unsupported regardless
of which desktop application transfers the file.

Other installers need to accept this package's format and identities, discover
the **FMER** endpoint, handle both transfer stages and verify **FM-1_734** at the
end. Do not rename this file to `.bin`, write it directly at address zero, or
replace its loader. The file is available separately for compatible installers;
physical installation through third-party installers is not yet qualified.
The Companion route is the supported path in this release.

The community [SLOOP installer source](https://github.com/isod89/sloop-fm1/blob/4ec1ac829fd2bdf2c571ea215fb3d62477d01220/tools/fm1_install.py)
documents the same FWSC/two-stage transport. Its automatic MIDI-port filter does
not include the name FMER. A common file extension alone does not establish
end-to-end compatibility. See the release verification record for offline
format checks. On 19 October, the unmodified parser functions from that pinned
source accepted this exact file without a force override, agreed on the logical
image and FM-1_734 identity, and rejected a corrupted copy. This is format-level
interoperability; no upstream installer was used to write a unit during this pass.

## Preservation and limits

Supported installations preserve protected boot/identity/calibration regions.
Back up saved sounds and projects before changing firmware. Original-firmware
restore requires a separately supplied supported image; no private stock ROM,
stock bank or universal recovery file is distributed here. Returning to a stock
application is not a promise of restoring all stock settings.

Bluetooth, macOS/Linux binaries and four separate USB audio stems are deferred.
The existing USB-audio endurance and heavy-load timing limitations are documented
in the offline handbook. See [release readiness](RELEASE_READINESS.md) before
making the draft public.

## Companion updates, sound packs and custom applications

The sidebar opens GitHub releases for manual downloads. Quit Companion before
extracting a newer program ZIP into a new folder; your user-profile Library stays
in place. Import the separate default-sound catalog in Library to add copies,
then review explicit unit destinations before deployment.

Companion734 r3 accepts custom applications with the exact reviewed935 updater
and the same protected layout. It does not accept arbitrary FWSC updaters or
change flash boundaries. Back up first; application behavior and saved-data
compatibility are the firmware publisher's responsibility. See
[the complete compatibility contract and deployment workflow](COMPANION_R3.md).
