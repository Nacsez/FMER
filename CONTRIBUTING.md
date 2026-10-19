# Testing and feedback

Public testing and feedback are welcome when the maintainer publishes a beta. The owner retains directorship of the official project. Code-contributor status is reserved: outside pull requests require explicit prior maintainer permission; unsolicited pull requests are not the beta feedback channel. Please open an issue using the Beta feedback form. This contribution policy does not alter applicable software-license rights.

Download the companion ZIP from a published GitHub release, extract everything, launch FMER Companion.exe, connect one powered-on FM-1, inspect the included firmware and install. Keep power and USB connected until Complete. The portable Windows x64 package includes its dependencies and offline help. Raw firmware is for a compatible update interface, not a whole-ROM programmer.

Use Beta feedback in the companion to export optional observations and a bounded diagnostic summary. Attach the JSON to an issue (or ZIP it if GitHub will not accept JSON). No account or automatic upload is built into the companion. Please review files before sharing: never attach ROM dumps, private patch libraries, personal recordings, credentials or full AppData folders publicly. A specific operation export may contain more diagnostic detail than the beta summary; share it privately when requested.

Test whatever interests you. Unused categories may remain blank: companion usability; installation; FMER usability; menus/navigation; sounds/options; FX; arp; sequencer;4T/4V/1V; MIDI; other observations. Include expected versus actual behavior, reproducible steps, starting firmware, computer OS and relevant connection type. A pass is useful evidence too.

## Compatibility boundaries

The installer identifies the device and verifies the supported flash layout and calibration. Different application versions can be admitted; arbitrary hardware or firmware compatibility is not established. An unknown updater/layout is a reason to stop and export a record, not to force a flash. Restoring stock is not a universal workaround for an unverified layout. Alternative firmware catalog management is deferred.

Restore Original Firmware accepts a supported user-provided V15 image; stock payloads are not distributed with FMER. It restores the application while preserving device-specific data; it is not a full factory-settings reset.

## Current release gate

Original FMER firmware, Companion and original default patches are GPL-3.0-only; see [LICENSING.md](LICENSING.md), [LICENSE](LICENSE) and [NOTICE](NOTICE). Existing third-party licenses remain effective. Maintainer-only official development does not restrict recipients' GPL rights to modify, fork or redistribute. Beta preparation remains private until final source/provenance and redistribution checks are complete and publication is authorized.
