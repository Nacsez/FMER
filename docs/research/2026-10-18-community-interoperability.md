# Community patch exchange and official firmware recovery

Reviewed 18 October 2026. Standard DX7 files provide useful FM6 exchange with Felucca today. M-VAVE's new **Open V13** is a separate firmware line from **Original V15**, and changes the storage map. The two public vendor images are recognized by FMER Companion but are not admitted by its existing application-only updater. This distinction preserves the tested recovery path instead of treating a memory-layout conversion as an ordinary update.

Evidence is [community-20261018.json](../../evidence/community-20261018.json). Classification: publisher source and binary inspection, plus offline tests. No Open V13 installation or rollback was performed in this investigation. Raw vendor downloads remain in ignored acquisition storage; private device dumps are not included.

## FM6 patch exchange

Felucca 1.6.1's FM6 editor exports a standard DX7 single-voice `.syx` file and imports DX7 voices/banks. Its native library JSON can also contain engine parameters, a packed FM6 voice, patterns and drum grids. Those additional structures are not the FMER project format. Sharing the hardware layer does not make their state files interchangeable. [Felucca editor source at the reviewed revision](https://github.com/hugelton/Felucca/blob/5738617968a22b5d4c0d3470cfcc95559052f446/web/editor.html)

The new production-companion bridge uses FMER's existing compiled DX7 codec, rather than introducing another interpretation of Yamaha parameters:

| Exchange | Behavior |
| --- | --- |
| One DX7 voice | Accept a 163-byte Yamaha VCED SysEx file; create one FMER FM instrument. |
| One DX7 bank | Accept a 4,104-byte, 32-voice VMEM bank; review and import as one local Library transaction with one Undo. |
| Export | One FM voice or exactly 32 FM voices; reject VA instead of exporting its unused FM fields. |
| Validation | Shared C++ framing, checksum and parameter-range checks; no hardware access during decoding. |
| Imported FMER extras | Dry effects, enabled source DX7 LFO, blank project and default performance setup. Editor adoption can retain the existing project and playing mode. |
| Names | Ten-character source names; nonprinting/empty names receive a disclosed display normalization. Numeric FM parameters remain unchanged. |
| Not exchanged | Effects, VA engines, mixer, sequencer, song, sample data and native performance settings. Use native FMER backup to preserve FMER state. |

Recommended workflow: read the desired sound in Felucca's FM6 editor, export `.syx`, import it in FMER Companion, audition and adjust, then explicitly send/save to an FMER slot. Reverse the path with FMER's DX7 export. Sounds may differ between synthesis implementations even when their parameter bytes match. Imported community files retain their own rights; importing a patch does not relicense it as an FMER default.

`tools/companion_dx7.py` is file-only. Seven regressions pass, including actual C++ single/bank round trips, corrupt checksum and invalid parameter refusal, VA refusal, one-transaction Library Undo and preservation of editor pattern/song/mixer/mode. Multiple concatenated banks, arbitrary Yamaha SysEx messages and Felucca native JSON are explicitly refused in this first version.

## The two official firmware lines

The [M-VAVE download center](https://www.m-vave.com/download) still lists Original V15 dated 30 July 2026. The newly published [FM1 Open repository](https://github.com/m-vave/fm1_open/tree/b178ac43c25f010c60a878056fb5331fe693fd62) identifies Open V13, with eight tracks, samples and its own Workbench. V13 and V15 numbers belong to different release lines.

The exact public assets and the existing device-derived recovery image differ:

| Layout property | Existing qualified device V15 / FMER layout | Published Original V15 | Published Open V13 |
| --- | --- | --- | --- |
| Application slot bytes | 580,892 | 581,564 | 440,028 |
| Package flash image end | `0x93000` | `0x93000` | `0x70000` |
| VM range | `0x93000–0xE9000` | `0x93000–0xE9000` | `0x70000–0x7B000` |
| BTIF range | `0xE9000–0xEA000` | `0xE9000–0xEA000` | `0x7B000–0x7C000` |
| Vendor user range | `0xEA000–0xFC000` | `0xEA000–0xFC000` | `0x7C000–0xFF000` |
| Existing loader935 admission | Qualified application restore, device checks still apply | Refused | Refused |

FMER stores its instruments/projects in reserved areas distinct from the vendor's user descriptors. Open's enlarged USER region overlaps FMER application/data addresses. A new application may initialize settings or samples there after startup, so backup preservation cannot be inferred merely from a successful initial write.

Published Original V15 has a 672-byte larger application than the qualified device image, shifted configuration/EQ records and a different USR descriptor. It cannot fit the current slot by substituting its code. Open V13 has a different directory structure and an EXT_RESERVED user declaration. The existing loader's layout, calibration, first-16-KiB and final-sector preservation checks must remain intact.

`tools/inspect_official_firmware.py` independently inspects the exact pinned files without exposing a write path. It verifies the package directory and flash/OTA payload CRCs and reports component hashes and decoded descriptors. Additional stock resource entry formats are hash-pinned but not interpreted as ordinary raw-CRC payloads. `companion_stock.known_file_info()` provides actionable recognition results with `installable: false`; unknown or changed files do not inherit that recognition.

## Recovery rights and migration gates

M-VAVE now explicitly licenses its published `sdk/firmware/FM-1_015.fwsc` and named boot/update resources under Apache-2.0. That grant permits distribution subject to its terms and retained component notices; it does not cover our private device dumps. The Open application's GPLv3 SDK exception and separate proprietary FM1-engine permissions must also be preserved if distributing that complete product. These are separate component terms, not a reason to relabel the FMER project. [Pinned M-VAVE notices](https://github.com/m-vave/fm1_open/blob/b178ac43c25f010c60a878056fb5331fe693fd62/THIRD_PARTY.md)

The official Workbench offers migration from another firmware with an explicit confirmation, and restoration of V15 plus 128 factory sounds. Its browser source passes the publisher package to the supplied native updater. That native updater is a binary in this release; the reviewed browser/package source does not establish its boot, calibration or interrupted-write preservation behavior. Its published Open package metadata also marks `hardware_validated: false`. This is a publisher field, not a statement that no manufacturer has ever tested a unit.

A bounded future qualification should:

1. Preserve a verified full-ROM backup and FMER library/project backups for an isolated unit, plus an independently reviewed recovery route that works if normal MIDI no longer starts.
2. Audit or obtain authoritative bounds for the vendor loader, especially boot, calibration, user-region migration and interrupted updates. Confirm expected identity and layout before execution.
3. Install the exact pinned Open image using the documented vendor path, record every transition and inspect startup/persistence/audio behavior.
4. Exercise the vendor's return-to-V15 workflow, inspect the resulting layout and defaults, then qualify a published-V15-to-FMER migration that retains that unit's protected data.
5. Test failure/reconnect handling and package the reversible workflow before exposing it as a normal Companion recovery option.

The migration is not established to be irreversible. It is unqualified and crosses the boundaries of our current updater. The current loop therefore keeps the tested original-device V15 restoration and FMER installation path, adds clear official-file recognition, and records the new route for a dedicated migration pass. No vendor loader, proprietary engine or new SDK implementation was integrated into FMER.

## Reproduction and source pins

The acquisition manifest in the evidence record pins HTTPS URLs, UTC acquisition times and SHA-256 values. Source revisions: Felucca `5738617968a22b5d4c0d3470cfcc95559052f446`; M-VAVE Open `b178ac43c25f010c60a878056fb5331fe693fd62`.

```text
python tools/inspect_official_firmware.py third_party/acquired/community-20261018/open-v13-package.bin --output artifacts/community-20261018/open-layout.json
python tools/inspect_official_firmware.py third_party/acquired/community-20261018/stock-v15-package.bin --output artifacts/community-20261018/stock-layout.json
python -m unittest discover -s tests -p test_companion_official_firmware.py -v
```

For actual-core DX7 checks, set `FMER_HOST_EXE` to the current compiled host executable and run `python -m unittest discover -s tests -p test_companion_dx7.py -v`. Without that variable the two actual-codec tests are explicit skips; file/model tests still run. No command above accesses a device.
