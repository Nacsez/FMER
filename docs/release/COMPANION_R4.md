# Companion 734 r4 — OEM catalog and community FM capture

20 October 2026. Firmware remains the exact 734-r2 release candidate. Companion
changes independently; the previously uploaded private r3 draft is not replaced
or published by this work.

## Delivered workflow

Library → Included & community sounds adds either the 64 original FMER Defaults
or **OEM Patches — V15**, containing all 128 original V15 voices. This is a local
catalog import with review and Undo, not an automatic bank or unit replacement.
The ZIP also includes both standalone catalog files in Libraries. Source slot
numbers and names remain visible; instrument renaming, audition and explicit
destination transfer use the existing Companion workflows.

The public Original V15 recovery resource contains two identical 16,384-byte
voice banks. Its USR payload is SFC-encoded using the absolute UFW payload
address; decoding that resource verifies CRC16 E3BC. All 128 packed voices
match the earlier pristine Citrine acquisition byte-for-byte. Public source
bank SHA-256: ecad0b8620f9d784d46c8da1e3c5de02c40214649ed8dec218026431046aad25.

The public asset is explicitly Apache-2.0-licensed by M-VAVE. Only extracted
voice data is included, alongside complete publisher/component notices and
the reproducible extraction tool. No private ROM, bootloader, executable,
settings or opaque resource is added to the release. FMER defaults remain GPL.

Slots 23,36,47,77,85,110,115,116,117,120,124 have values outside standard DX7
ranges. Import normalizes those fields and records each original/replacement
value in Notes. The original packed data remains included. FX, sequences and
identical sound are not part of FM conversion.

The workspace's previous 128-item Citrine collection is now visibly labeled
OEM Patches - V15 (Citrine capture), with its private provenance retained.
64 original FMER Defaults were added. The prior catalog is backed up locally;
PC banks and onboard presets were not replaced.

## Cross-firmware support and its boundaries

| Family | What works in this increment | Still blocked |
|---|---|---|
| FMER 733/734 | Existing complete backup, restore, instruments/projects and guarded installation | No scope expansion to unknown native formats |
| Original-device V15 | Existing compatible application recovery, now round-trip tested through production Companion Jobs | Requires the supported user-supplied application/ROM; not a full factory-settings reset |
| Public Original V15 | Recognized exact package; complete OEM library extracted offline | Larger executable slot and shifted configuration require a migration updater |
| Felucca 1.6.1 | DX7 exchange; read-only FM6 capture implementation | Physical capture qualification, 32-voice cartridge readback, native backups, install/return migration |
| SLOOP 2.7.1 | DX7 exchange; read-only FM6 capture implementation | Physical capture qualification, native projects/samples, install/return migration |
| Reviewed JIANT FM6 family | DX7 exchange; capability-gated read-only FM6 capture implementation | Exact binary/source alignment, physical qualification, separate cartridge and migration |
| X0X 1.1.0 / Open V14 / Baud102 | Pinned package recognition with specific refusal explanation | Different protocols/layouts, native conversion and migration qualification |

The community reader emits only editor INFO(1), FM6_LIST(70), FM6_GET(68), plus
the normal identity query. It never selects a preset, enables WATCH, stops
playback, writes a patch or stages an updater. It requires a matching physical
input/output pair and refuses multiple community candidates. The INFO family
and capabilities distinguish SLOOP/JIANT despite their shared FM-1_900 identity.

Felucca/JIANT capture covers factory FM6, four stored track FM6 snapshots and
available user-preset FM6 voices. Their separate 32-voice cartridge is explicitly
excluded. SLOOP covers factory FM6, its 27-slot FM6 bank and three synth-track
snapshots. Non-FM track snapshots may contain a dormant FM voice. No other
engines, FX, native settings, songs or samples are translated.

Each populated voice is read twice, slot/response lengths and parameter ranges
are checked, and INFO/list are rechecked at completion. Raw packed voices and
source identity are saved with a checksum before conversion/import. A failure
does not create a partial library. This is not a native recovery backup. The
reader is a protocol-tested preview, not hardware-qualified community support.

## Connected recovery evidence

Both attached units were identified through the existing physical USB locations
and backed up with controls idle. Amethyst was tested using the actual
companion_jobs inspection/install path and unchanged 935 updater:

1. Full FMER instrument/project/working/MIDI/FX-default backup.
2. Supported original-device V15 application restored and FM-1_015 verified.
3. Exact FMER734-r2 reinstalled and FM-1_734 verified.
4. Saved instrument/project records, MIDI and FX-default compared equal.
5. Original working state restored and compared, ignoring generation only.

Citrine was backed up and kept as the unchanged reference. No third-party
firmware was installed. The test verifies Windows transport/reboot/preservation,
not a fresh acoustic or endurance qualification or a separate-PC UI flash.

Retained intermediate failures: initial inspection correctly refused stale
Companion source pins before hardware access. Pins were refreshed only for the
reviewed job/recognition changes, with the same firmware/loader bytes. A later
verification helper used a nonexistent midi_set method after all saved-data
comparisons passed; no settings write occurred. A fresh read verified the
already-restored working state and original MIDI settings. Neither failure is
reported as a successful test attempt or attributed to the device.

Raw backups and journals: artifacts/community-integration-20261020/live/.
Sanitized evidence: evidence/companion-community-20261020.json.

## Next compatibility milestone

Implement a separately versioned migration updater before enabling public V15
or other publisher packages. The V15 581,564-byte executable actually occupies
its larger slot; it cannot be trimmed to FMER's 580,892-byte slot as padding.
The migration must map configuration/EQ and protected tail, preserve each unit's
boot/key/radio metadata, validate source and destination layouts, and survive
forward/return tests with native saves. Shared runtime save regions also require
family-specific archive/restore adapters before a safe user-facing transition.

Prioritize public V15 recovery, then Felucca, then SLOOP. Keep the musical
734-r2 firmware locked. Do not treat file recognition, the common SysEx prefix
or successful voice reads as firmware-write permission. The new OEM pack and
read-only workflow can ship independently of that migration work.
