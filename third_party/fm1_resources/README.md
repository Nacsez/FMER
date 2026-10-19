# Public FM-1 configuration resources

`parameters.json` is an editable hexadecimal representation of two unmodified
data blocks extracted from M-VAVE's public Original V15 resource at commit
`b178ac43c25f010c60a878056fb5331fe693fd62`. It contains 383 bytes of configuration
and 2,873 bytes of EQ data. The original package SHA256, offsets and block hashes
are recorded in that file. Neither application code, boot code, instruments nor
the opaque device trailer is included.

The publisher grants Apache-2.0 for this resource in `UPSTREAM-NOTICES.md`, under
“Boot/update resources and recovery firmware”. The complete notice and Apache
license are retained. Configuration-resource attribution also identifies the
official JieLi SDK. Other components described in the complete publisher notice
are not thereby incorporated into FMER; no proprietary engine is linked.

FMER changes the representation to JSON and relocates these data blocks into its
existing supported layout. The two decoded blocks themselves are unchanged and
match the qualified units' existing configuration. This does not authorize a
layout migration: the installer still requires the existing layout/calibration
fingerprint and preserves each device's final sector.

`tools/build_public_image.py` generates all directory metadata and padding from
format constants. No private ROM is needed. The opaque last 32 bytes are FF in
the distributed package and are never written; the device retains its own.
