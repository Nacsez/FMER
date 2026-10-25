## 24 October 2026 development735 update

Current names are Bank A (old DEFAULT, device64..127) and Bank B (old USER,
device0..63). Both are editable mixed FM/VA banks. Both resets now restore the
compiled Spectrum collection. Bank A stays populated; Bank B may also be
cleared explicitly. Classic remains the legacy734 collection. The four included
Expressions2 profiles retain all192 sounds, with Spectrum containing all62
survey favorites plus two complementary voices. Profiles are now grouped by
musical category across both engines; personal profile order remains unchanged.

My instruments supports16 named local setups, each with Bank A and Bank B
loadout references, a Library collection and notes. Prepare loadouts copies
those selections into the ordinary reviewed deployment workflow. Names are
organizational labels, not device serial numbers: connect one intended unit at
a time. Switching profiles clears cached device views and installer inspection;
renaming/deleting a profile does not alter a physical instrument or its sounds.

Plain FMER upgrades also perform full musical-data backups and preserve inherited
instrument sounds when compiled defaults change. Explicit loadout selection
replaces only the chosen banks. Source generation changes during capture abort
the backup before firmware writing. Native12/6-voice records convert for supported
733/734 sound writes, while a735 firmware downgrade remains blocked pending a
persistent-storage migration. See DEVELOPMENT_735.md for physical qualification.

The dated design below describes the original734r7 increment.

# Instrument loadout profiles

23 October 2026. Local Companion734 r7 development on
`release/next-package-compat`. Firmware734 package r3 is unchanged.

## User workflow

Instrument loadouts are ordered snapshots of64 complete FMER instruments. Every
slot accepts FM or VA. Included A / Spectrum, B / Rhythm, C / Voltage and
D / Atmosphere use the192 Expressions candidates. They remain subject to owner
curation. Classic contains the64 compiled firmware defaults.

Save a copy to customize an included profile. Name it, replace instruments from
the included catalog, Library or PC banks, audition through the local renderer,
and move slots earlier/later or to an exact destination. Every committed edit is
one Undo action. A complete PC bank can also become a profile. Export/import
checksummed `.fmer-loadout.json` files for transfer between computers. Twelve
personal profiles fit the existing bounded local-library storage, independently
of the included profiles; export before deleting one to make room.

DEFAULT and USER are independent64-slot destinations. Choose A for DEFAULT and B
for USER, the same profile for both, or preserve either bank. The same two-bank
review is available without flashing and on the Firmware page. Wire addressing
remains USER0..63 and DEFAULT64..127; display slots are00..63 within each bank.
Profile files are complete snapshots, not references to mutable Library items.

Replacing instruments changes the sounds used by projects that reference those
slots. Projects are preserved and references are not remapped. A selected
loadout updates the writable onboard bank; firmware's Reset to FMER Default and
Reset User Bank still restore the compiled Classic collection. It does not
personalize the executable's reset image. The unit works standalone after writes.

## Installation transaction and recovery

Optional loadouts are admitted only for the included reviewed FMER release, not
arbitrary custom firmware or stock recovery. Both bank snapshots and their exact
transfer digest are validated before opening MIDI. Editing a saved profile after
confirmation cannot alter the running operation.

The combined job binds to one identified physical USB location, serializes device
access, captures a full native backup when the starting firmware supports it,
performs the existing reviewed firmware installation, verifies FMER identity,
captures initialized banks again, then writes/verifies each requested instrument.
It restores the pre-install working state when available; otherwise it restores
the newly installed working state. Supported saved projects remain untouched.
Stock/other firmware lacks this native backup interface; no unverified read
commands are substituted. Unknown layouts still fail the updater's admission.

Progress follows backup, updater and instrument phases. Completion means all
requested writes and working-state restoration finished. On failure, the durable
job retains whether firmware installation completed, verified slot writes and
backup paths. A partial loadout is not rolled back or retried automatically.
Download the backup/operation record, inspect the banks, then explicitly deploy
the profile again. Reflashing is unnecessary for a bank-only failure.

Physical port continuity is not a cryptographic device identity: do not unplug
or swap units during the job. The app refuses multiple candidates, and the
existing transport rechecks opened-handle identity at every transition.

## Development and curation

`tools/build_loadout_profiles.py` generates `host/loadout_profiles.json` from
original Expressions recipes. `--curation path/to/review.json` applies the
owner's existing four-collection review export. No OEM/V16 material is an input.
Native imported Library sounds retain their available title and notes when
placed in a profile. All generated profile data and first-party tools are GPL-3.0-only.

Portable packaging includes all included profiles and the offline illustrated
Help; no renderer/runtime dependencies are added. New installation modules are
included in both runtime source closure and release admission pins. Restage
catalog pins after changing them, preserving the exact firmware binary.

See TEST_REPORT.md and `evidence/companion-loadouts-20261023.json` for results.
Host/fake-transport and browser evidence must not be described as a physical
first-install or128-slot write qualification. This pass leaves units untouched
while the owner reviews the sound collection.
