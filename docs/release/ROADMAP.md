# From public testing to 1.0

Status checked 21 October 2026: the owner published `build-734-r5` at
18:19:44 UTC. Firmware is 734-r2; Companion is 734 r5. GitHub had no issues at
the time of this check. That is an intake baseline, not evidence of no bugs.
The GitHub release is published without its prerelease flag; the product remains
pre-1.0 under the owner's existing numbered-build policy.

## Work order

| Lane | Immediate work | Completion evidence |
|---|---|---|
| Public feedback | Use the three issue forms and [triage process](BETA_FEEDBACK.md); group duplicates and record positive coverage | Reproduction, affected build and a traceable disposition for each report |
| Reliability | Prioritize installation, saved data, sound continuity, transport and mode regressions | Regression plus appropriate packaged/physical checks and owner or reporter retest |
| Companion | Add exact package revision to diagnostics; finish separate-PC reset/edit/save acceptance | Export distinguishes candidates; conflicting saves preserve data and drafts |
| Qualification | Expand loaded audio, USB-audio endurance, MIDI topology, power and recovery coverage | Repeated, measured runs with exact setup and no unexplained regressions |
| Bluetooth | Resolve complete radio runtime and reusable memory in isolated research | [Gate-by-gate radio evidence](BLUETOOTH_PLAN.md), then candidate inclusion review |
| Release | Update Help and change notes with each accepted candidate | Verified source/assets, offline package, preserved data and explicit owner signoff |

The current [backlog](beta-backlog.json) contains known engineering/acceptance
items, not fabricated public reports. Add issue URLs when real reports arrive.
Keep stable fixes and Bluetooth work separate. Use an isolated research branch
or worktree based on the published source when changing runtime/interrupts;
merge only after its gates pass. Do not reduce voices, FX, sample rate or interface
responsiveness to make a radio feature fit unnoticed.

## Candidate for the complete release

These are proposed exit criteria for the owner to review, not a claim that they
have all passed or a guaranteed ship date:

- No unresolved P0/P1 defects in supported workflows. Repeated P2 failures have
  a fix or an explicit owner-accepted limitation and workaround.
- All current automated regressions pass with skips explained. Installation,
  recovery and save-format changes have preservation/failure-path evidence.
- The exact portable package passes extraction, launch, offline operation,
  upgrade/library preservation and shutdown checks on clean Windows 10 and 11
  x64 environments. Existing development-PC checks are not clean-VM evidence.
- FM/VA, 1V/4V/4T, arp recording, Song, mixer, saves and supported wired MIDI
  have a repeatable physical acceptance matrix. A new mode must not reduce an
  existing mode's keyboard or sequencer behavior.
- Sustained loaded playback, USB audio and paired MIDI run for a proposed two
  hours per relevant setup without unexplained dropouts, stuck notes, resets or
  corrupt saves. Record CPU/queue/stack peaks; zero crashes alone is insufficient.
- Audio reserve is measured against the existing 2,176 microsecond target per
  128-frame block at 44.1 kHz; any miss requires explanation and an explicit
  engineering decision, not silently changing the threshold.
- All known critical candidate fixes have a follow-up test; the owner completes
  a sustained musical workflow on the exact candidate. Keep a suggested minimum
  one-week candidate observation window; elapsed time or an empty tracker alone
  does not establish readiness.
- Help, MIDI tables, compatibility claims, licenses, source rebuild and package
  hashes match the candidate. Installation compatibility remains a tested matrix,
  never "every firmware" by implication.

Bluetooth is the first feature investigation and a desired inclusion. It is not
yet a promised 1.0 capability. If the runtime, licensing, budget or physical
quality gates fail, bring that evidence to the owner for a scope/date decision.
Do not hold reliability fixes hostage to the radio investigation or label an
unfinished backend supported. Group support requires three physical instruments;
a working two-unit link is a separate, narrower milestone.

After each candidate, summarize newly reported problems, reproduced problems,
verified fixes, untested workflows and outstanding blockers. Report devices and
setups actually tested rather than a success percentage with an unknown denominator.
