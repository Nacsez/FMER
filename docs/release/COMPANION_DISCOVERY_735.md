# Companion connection-discovery feedback — 24 October 2026

## Report and confidence

A tester using public734 reported wording similar to "trouble finding
instruments" while trying to install FMER. The owner confirmed that Companion
was run from its fully extracted folder. Exact text, starting firmware, Windows
port enumeration, failure stage and logs are unavailable. The cause is therefore
**unconfirmed**; do not label this a reproduced installer defect or a resolved
tester incident.

The examined local public archive is `FMER Companion 734 r5 Windows.zip`, SHA256
`6a6aaafd528f01d9b4b1d87f7650b8900a464e3c5fd3d44cc5cdf19e49d98204`.
The paraphrased phrase is not an exact message found in the reviewed paths.
The public and735-r9 versions share their endpoint-name matching rules and
generic connection-timeout explanation. There was no already-completed fix
that proves this report resolved. Keeping the extracted folder together rules
out relocation of the EXE alone, not every possible package/OS problem.

## Plausible cases

* Windows exposes no recognized FM-1 MIDI pair: disconnected unit, USB Master
  mode, a connection providing power but no MIDI, or another firmware's name.
* Only an input or output is visible, or both exist but firmware does not answer.
* Another program owns a MIDI port. MMRESULT7 already has dedicated guidance.
* The connection disappears during an updater/application transition.
* A stock-firmware bank operation is requested instead of installation. Stock
  does not expose FMER's musical backup protocol; that limitation already has
  its own explanation. None of these cases proves missing or corrupt patches.

## Implemented locally in Companion735/r10

Device discovery now records Windows input/output names and IDs plus matching
counts when the list changes, then records the final reason on timeout. Reasons
distinguish no ports, unrecognized names, an incomplete pair, unanswered identity
and a transitional identity. Identical polls do not flood the log. The exported
operation retains the last eight discovery events even after another progress
phase replaces the banner; full events remain in the local session journal.

Readable outcomes explicitly distinguish the physical FM-1 USB MIDI connection
from instrument presets. Guidance includes one connected unit, closing competing
apps, Check connection and FMER's PC/NORMAL USB mode. Updater and expected-app
timeouts instead retain uncertainty, ask to keep power connected and export the
stopped operation record. They never claim no earlier write occurred or prescribe
repeated resets. Raw details remain collapsed and Export operation record stays
visible. The offline troubleshooting article includes the same workflow.

No endpoint allowlist, identity/layout validation, retry deadline, write barrier,
firmware payload or automatic reset policy changed. Unknown MIDI names are
diagnosed, not automatically opened or force-flashed. This pass uses isolated
mock transport/browser tests; no connected instrument was accessed. The local
735/r10 package still contains the qualified735-r9 firmware. Public734 downloads
are not replaced or published by this work.

## Verification and follow-up

Regression cases exercise absent/unrecognized/one-sided ports with no MIDI
session opened, bounded identity retries and cleanup, unchanged-port log
suppression, readable transition outcomes, and durable bounded export history.
The real-browser fixture checks the connection title, preset distinction,
PC/NORMAL instructions, export button and collapsed technical details.
Receipts are retained in `artifacts/companion-discovery-735r10/`.

Without the tester's logs, success on that computer remains unverified. If the
tester encounters it again, the useful minimum is the exact message, starting
firmware, Companion revision and unit screen state. An operation export is
optional but much more diagnostic. Review device names before sharing privately;
do not request ROMs, personal patches or the entire AppData folder publicly.
