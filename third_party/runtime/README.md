# FMER source-built runtime

This subset builds the C/math/compiler helpers required by FMER734
from publicly licensed source. It contains no extracted vendor binary archive.
The49 source units replace48 vendor objects: the vendor memcpy object also
provides memmove, which has a separate upstream source file.
734-r2 uses this source subset. The original734-r1 payload used vendor archives;
this review does not retroactively qualify those archives.

Newlib2.2.0: https://sourceware.org/pub/newlib/newlib-2.2.0.tar.gz
LLVM compiler-rt4.0.1: https://releases.llvm.org/4.0.1/compiler-rt-4.0.1.src.tar.xz

PROVENANCE.json records exact archive and file hashes, original paths, selected
compilation units and optimization flags. Upstream file bytes are unmodified.
No upstream configure/build/install scripts run. Archives were obtained over
HTTPS; the retained LLVM signature was not verified and is not called verified.

## Existing permissions

Newlib source keeps its per-file notices and complete COPYING.NEWLIB. The
selected math files primarily use Sun's permissive notice, float classification
uses Red Hat's explicit permissive notice, and files without an overriding
notice retain the collection's default notices. No Cygwin, Linux syscalls,
proprietary DSP, radio or operating-system implementation is selected.

Compiler-rt is dual MIT/UIUC. FMER selects its MIT option and retains the full
license, credits and individual headers. This component is not blanket
relicensed as GPL; the combined application remains GPL-3.0-only.

These existing licenses do not require a new permission request or per-release
approval. Source, notices and build instructions accompany distribution. No
M-VAVE proprietary SDK linking exception is relied upon.

## Build boundary

Run `python tools/build_fm1_candidate.py --runtime source --usb-product FMER
--out <new-directory>` with the pinned external compiler/headers available.
The command builds an offline candidate and does not open a device.734-r2 target
and package evidence is recorded in docs/release/RUNTIME_REVIEW_734.md.
The compiler itself remains a separately obtained prerequisite; FMER does not
redistribute its executables or claim an open-source pi32v2 compiler backend.

Forty reference objects match code/data, relocation contracts and exports; eight
differ. Exact results and whole-program differences are reported in the runtime
audit. Function names and unrelocated bytes alone do not establish
whole-firmware equivalence. Preserve the qualified734 package until audio,
timing, USB and storage regression gates are met for a replacement.
