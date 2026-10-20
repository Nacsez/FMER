# FMER public-source agent instructions

Read README.md, CONTRIBUTING.md, LICENSING.md, docs/SOURCE_BUILD.md,
docs/DESIGN.md and the relevant directory AGENTS.md before editing.

The owner directs the project. Public testers report issues and optional reviewed
diagnostic summaries; they should not create unsolicited pull requests. Code
contributions need explicit maintainer approval. Do not publish, push, upload
logs, or access/flash hardware unless the user authorizes that action.

Preserve attribution, per-file licenses and dependency pins. Original FMER code,
Companion and original defaults are GPL-3.0-only. Do not relicense vendor assets,
imported patches or artwork implicitly. Never commit device dumps, private musical
libraries, credentials, AppData or personal recordings.

Use CADER's palette and value model in docs/DESIGN.md. Prefer visual, musical
controls and exact values. Keep firmware screens and Companion documentation in
sync. Capture diagrams with the real renderer, not invented device screens.

Keep the musical core portable. No allocation, logging I/O, blocking locks,
filesystem or flash operations in audio processing. Use bounded queues and
explicit note ownership. Maintain diagnostic counters and format logs outside
the real-time path. Never present unsupported placeholder behavior as working.

Follow docs/SOURCE_BUILD.md for this reduced source tree. The historical private
workspace's research corpus, device evidence and toolchain acquisition are not
part of this snapshot. Some workspace-wide audit tests require that private
context; do not fabricate it or disable device compatibility checks to pass.
Run host CTest and the source-snapshot tests before hardware consideration.

Use isolated libraries in tests. Record exact build inputs, outcomes, failures
and skips. Host tests do not qualify audio, electrical behavior or a physical
transport. Unknown hardware layouts remain blocked. Protect the boot/identity/
calibration regions and saved musical data in every installer modification.

734-r2 target builds default to the included licensed source runtime. Keep its
per-file provenance and notices, and the public configuration-data provenance.
The compiler is external; do not link or distribute unreviewed vendor archives.
Do not promote vendor-reference builds or weaken installer preservation guards.
Read docs/release/RUNTIME_REVIEW_734.md.

Companion734 r3 accepts custom applications only with the exact reviewed935 updater and protected layout. Read docs/release/COMPANION_R3.md before changing admission. Preserve the distinction between transport compatibility and tested application behavior. Firmware734-r2 is the current release candidate; do not alter it for Companion-only work.
