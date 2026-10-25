# Companion 735 r11: startup and returned-computer QA

## Evidence and confidence

The owner's October 24 AppData capture contains two server launches and two
partial browser loads. Both launcher stderr files are empty. Each browser loads
the HTML, CSS and loadout script; neither records a request for the unit-profile
script or main application script. There are no new device operations in these
attempts. The startup-error.log is from October 17 and describes an older733.2
instance; it does not establish the cause of this new failure.

This establishes incomplete browser initialization, not a firmware or missing
instrument-bank diagnosis. The old logs did not record browser exceptions,
browser version or failed resource requests. A browser extension or browser
specific behavior cannot be ruled out.

We reproduced a concrete server defect: an accepted TCP connection that sends
no request prevents the plain HTTPServer from delivering scripts to another
connection. A two-second request timed out with the old server. Browsers can
open such speculative connections. The revised server serves the request while
six idle connections remain open. This is a reproduced contributor consistent
with the logs, not proof of the exact remote-computer trigger.

An isolated copy of the returned banks opens successfully in Edge, and its
source files remain unchanged. No private AppData, sounds or diagnostic text is
included in the public source or portable archive.

## Changes

- Up to32 socket readers can accept/parse connections; application handlers
  remain serialized under one lock. Rendering and library mutations do not
  become parallel. Device jobs retain their independent single-operation guard.
- Closing refuses queued application requests and drains the current handler
  before releasing the per-user library lock. The existing transfer-safe Quit
  and last-tab shutdown policies remain in force.
- UI scripts defer in their dependency order. The embedded editor loads only
  when opened, avoiding an unnecessary second bank initialization at startup.
- An inline startup watchdog runs before external scripts. It shows loading,
  script-load failure, initialization failure and a30-second pending state.
  Recovery links work even if the main application script never runs. With
  JavaScript disabled, a static message explains the requirement.
- Startup diagnostics retain bounded browser/error events locally with source
  identity, a downloadable report and no automatic upload. Files rotate at
  approximately64KiB; exports contain at most40 recent events. Error text should
  be reviewed before sharing. No sound, project, MIDI or ROM content is read.
- Portable rehearsal now opens the actual extracted EXE's server in Edge and
  exercises navigation and blocked-script recovery. API-only package tests did
  not previously exercise this failure class.

## Verification and limits

Regressions cover idle sockets, serialized concurrent requests, rejection during
shutdown, journal bounds/restart, cross-origin rejection and simultaneous bank
saves (one succeeds; the stale revision receives409). Browser checks exercise
normal navigation, lazy editor initialization, blocked main script, failed bank
read and reload recovery. The broader product workflow and extracted package
are checked separately; receipts are in artifacts/companion-startup-735r11 and
the sanitized evidence/companion-startup-20261024.json.

The firmware remains the exact735-r9 image. Public734 artifacts remain unchanged.
This is local development only. No connected FM-1 was accessed. The owner's
second-computer retry is still needed to confirm resolution on that computer.
