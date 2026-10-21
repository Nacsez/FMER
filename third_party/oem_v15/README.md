# OEM Patches — M-VAVE Original V15

128 packed FM voices extracted from the public M-VAVE recovery resource,
not from a private device dump. Original names, order and packed bytes are
retained in voices.json. The two bank copies in that resource are identical.

Source: sdk/firmware/FM-1_015.fwsc in m-vave/fm1_open at
b178ac43c25f010c60a878056fb5331fe693fd62. Package SHA-256:
db1642b2b6fa5c2cccb11ffd13878068bb28601678d3644049f99dc40e7edb8a.
Extracted bank SHA-256:
ecad0b8620f9d784d46c8da1e3c5de02c40214649ed8dec218026431046aad25.

M-VAVE licenses that specific recovery resource under Apache-2.0, as stated
in the accompanying complete UPSTREAM-NOTICES.md. Retain it and
LICENSE-APACHE-2.0.txt. Copyright (c) 2026 M-VAVE and applicable component
authors. Product names identify provenance, not endorsement.

Modification: extracted the voice data and omitted executable code, other
resources and device settings. FMER import normalizes eleven voices to standard
DX7 limits and records every change in the catalog Notes; voices.json preserves
the original values. Original OEM voices are not relicensed as FMER defaults.
Effects, projects and identical playback sound are not part of this conversion.

Reproduce with tools/extract_oem_v15.py using the exact publisher package.
That tool checks its hash, descriptor, decrypted resource CRC and duplicate
bank equality. No acquired code or firmware executes during extraction.
