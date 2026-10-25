# Install FMER 735 with Companion r11

1. Download `FMER-Companion-735-Windows-x64.zip` and extract the entire archive
   into a writable folder on a Windows10/11 Intel/AMD computer. Keep its files
   together. Start `FMER Companion.exe`; it opens a local browser interface.
2. Connect one powered-on FM-1 using a USB data cable. Close other applications
   using its MIDI ports. Use the connection scan and select the detected unit.
3. Export a backup before changing firmware or instrument banks. Keep the backup
   outside the extracted application folder.
4. Open Firmware, select the included735 package and follow the compatibility
   check. The installer preserves compatible identity/calibration regions.
   Unknown memory layouts are rejected instead of guessed.
5. Choose whether each64-slot instrument bank should be preserved or populated
   with a selected loadout. Installing a profile replaces that bank's sounds;
   existing project references are not automatically rearranged to match it.
6. Start installation and leave the unit connected with its controls untouched
   until all firmware, bank-writing and verification stages finish. Large bank
   deployments can take several minutes. Follow any restart instruction shown.
7. Play the instrument and check your projects. Use Help for library management,
   MIDI, controls and shortcuts. Quit from Companion when finished.

If the shell does not become usable, retain the startup error shown and export
diagnostics. If no USB MIDI connection is found, check power, cable, PC/NORMAL
USB mode and competing applications. A later disconnected-device error does
not undo an already completed firmware installation.

The program is unsigned. There is no cloud account or hosted website requirement.
The standalone `.fwsc` is provided for compatible installers; acceptance of its
format does not establish that every tool safely handles every starting firmware.
Stock V16 migration and unknown layouts remain outside this release's qualified
installation paths. Downgrading735 saves to733/734 needs a separate migration.

See [release notes](RELEASE_NOTES_735.md), [source builds](../SOURCE_BUILD.md), and
the historical [734 installation/recovery notes](INSTALLATION.md) for context.
