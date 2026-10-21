# Companion 734 r5: returned-PC QA review

21 October 2026. Firmware remains the exact 734-r2 release candidate. Amethyst
was read only on this computer; no firmware, instrument or settings write was
performed. The uploaded private r3 draft remains unchanged.

## Findings

| Area | Evidence | Release assessment |
|---|---|---|
| Installation on the other PC | 24 seconds; both stages complete, updater935 admission and final FM-1_734 identity verified; exact734-r2 package hash | Pass for this FMER-to-FMER reinstall. This session did not start from stock firmware. |
| Complete backup | 76.6 seconds; validated checksum,128 instruments and one populated project | Pass |
| Complete restore | 941.7 seconds, including pre-transfer backup;128 instrument writes and one project write verified | Pass, but slow. Preserve progress and power throughout. |
| Saved data after returning Amethyst | All128 sound projections, project, working state, MIDI and FX default match the returned backup | Pass under documented normalization below |
| PC audition | Ten note/chord/arp/sequence renders; positive output, no clipped/sanitized samples, rejected events or remaining voices | Pass for host preview, not hardware audio capture |
| Editor saving after bank reset | Six saves sent revision0 after the bank reached revision2 | Companion blocker found and corrected in r5 |
| Firmware diagnostics | No recorded overruns, MIDI overflows, rejected messages, DSP initialization failure, LCD timeouts or retained crashes | No new firmware blocker found within available counters |

The supplied folder contains959 files and includes October17 history. Old stage1
timeouts, memory-layout rejections and the733.2 startup exception are not new
failures from this session. The latest launcher stderr is empty. All three recent
device jobs completed; six rejected editor saves are the new application issue.
The session occurred October20 at9:46-10:15pm EDT; logs use October21 UTC.

## Save correction

The embedded editor retained its own PC-bank snapshot while the outer bank
manager reset defaults twice. The server correctly refused stale writes rather
than overwriting newer data. Repeating Save reused revision0 and could not recover.

Save now fetches the current bank revision while retaining working edits. Changes
to other slots are preserved. If the destination itself changed, a dialog names
the current sound and asks before replacing it. Cancel preserves both saved data
and the working draft. A concurrent change after that review still fails the
server revision check: no automatic write retry occurs. The user can press Save
again to review the latest destination. Returning to PC sound banks refreshes its
view after editor saves. Backend conflict protection remains unchanged.

The new actual-browser regression first reproduced the exact revision0/current2
failure, then passed reset/save, unrelated changes, cancellation, explicit
replacement, a deliberately injected save-time race, retry and outer-view refresh.
No MIDI access is permitted in these tests. Help explains the corrected workflow.

## Device comparison and limits

The connected endpoint matched Amethyst's previously observed USB location and
the owner's identification. Port location is not a permanent hardware identity.
Both endpoints were enumerated; only Amethyst's explicitly selected pair opened.
All handles closed successfully. The read-only backup also checks that no save
generation or working-state edit changed during capture.

Restored records have new source-generation metadata. All128 instrument records
also changed control158 from1 to0: the existing instrument-only projection clears
project recording mode. No other instrument field differs. The saved project and
working state differ only in source generation. Musical sound projection, MIDI
settings and FX default compare equal; this is not a claim of raw byte equality.

Maximum recorded render time was1816us; minimum observed half period2839us, with
zero overruns/load sheds. These retained maxima do not establish a new worst-case
audio stress qualification.78 voice steals can occur within the four-voice budget
and are not crash counts. There is no new acoustic, continuous USB-audio, radio,
battery-calibration or optical-display acceptance in this review.

Full restore remains intentionally conservative: the journal shows per-slot
backup, staged-state preservation and readback verification. Optimizing its roughly
16-minute duration is a later pass, not grounds to remove preservation checks.
The returned startup logs identify the firmware exactly but do not retain enough
application metadata to distinguish every734 Companion revision.

## Release decision

Use r5 instead of r4 for the next Companion test. No new firmware change is
justified by this evidence. The save regression needs a brief owner acceptance
check on the other computer before public release. Then refresh the private draft
with the approved Companion and matching source/checksums; it still holds r3.

Community FM6 capture remains a protocol-tested preview, alternate flash layouts
remain unsupported, and Bluetooth/macOS/Linux remain deferred. None is silently
promoted to supported status by this successful FMER reinstall. Publication is
still reserved for the owner.

Raw logs/readback: artifacts/companion-qa-20261021. Sanitized evidence:
evidence/companion-qa-20261021.json. Returned source logs remain untouched in
the owner's supplied evidence directory and are excluded from public artifacts.
