# Companion r11: returned installation review

Reviewed October24,2026; timestamps below are UTC on October25. This report
summarizes the owner's seventh returned AppData capture without distributing
private logs, device backups, paths or instrument data.

| Evidence | Result |
|---|---|
| Browser startup | Opening01:07:34; ready01:07:44; no new script errors |
| Launcher stderr | Empty |
| HTTP requests in this session | 725 successful responses; one favicon404 |
| Initial device probe | Completed |
| Installation01:09:07–01:29:02 | Completed; firmware735 installed |
| Instrument deployment | All128 slots completed; Bank A Rhythm, Bank B Atmosphere |
| Working-state restoration | Complete-state verification succeeded |
| Probe01:40:39–01:40:47 | No FM-1 input/output port enumerated; readable connection error |

The later probe saw only the Windows software-synth output and no input ports.
This establishes that the FM-1 MIDI port was unavailable at that moment, not why
it disappeared. It is not a flashing timeout or a missing instrument library.
The old startup-error.log describes an October17 release and is not evidence of
a new startup failure.

Exact Companion ZIP SHA256:
`5612135af27f94f2fafa9b589f3deb3e5ed07e4cd072c8240be58b03c3be1be3`.
Installed735-r9 FWSC SHA256:
`6911c2b8753c6b1f98f9d48c21f943a4c40497bf2bd481886975de246916e1e5`.

Conclusion: the supplied evidence supports successful initialization and a full
installation on the second computer. It does not qualify other starting firmware
layouts or prove every sound/project workflow. The exact tested ZIP is retained
for the draft release rather than rebuilt after this test.
