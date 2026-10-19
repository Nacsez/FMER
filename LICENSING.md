# FMER licensing

Effective 18 October 2026, the project owner licenses original FMER firmware,
FMER Companion and original FMER default instruments under the **GNU General
Public License, version 3 only** (`GPL-3.0-only`). The full text is in [LICENSE](LICENSE).
This replaces the earlier deferred decision. It does not authorize a public
release or replace the distribution checks below.

## Scope

The grant covers original FMER software in `core/`, `firmware/fm1/`, `hal/`,
`ui/`, `host/`, `tools/`, `packaging/` and `tests/`, including its original help
prose, build scripts, original code-drawn interface graphics and generated
forms. Existing third-party notices and any more specific file license remain
effective. The combined FMER firmware is distributed under GPL-3.0-only;
individual Apache/MIT-licensed dependencies retain their own notices and terms.

All 64 original FMER default instruments, their editable recipes in
`core/factory_presets.cpp`, and exported FMER Default library/bank copies are
GPL-3.0-only. The recipes are the preferred source form; native/JSON exports
are editable representations. Changes to these instruments may be saved and
shared under the same license. Importing someone else's instrument does not
relicense it. User-authored patches and projects remain their authors' work.

Playing FMER, recording a performance or rendering audio does not by itself
require the resulting music to use GPL. The GPL does not claim independent
compositions or recordings merely because FMER produced their sound.

On 19 October 2026 the owner confirmed ownership of `FMER SPLASH.png` and
expressly included that artwork and its editable source under GPL-3.0-only.
The original PNG and its generator are included in the source packages; the
generated firmware splash and Help reproductions carry the same grant.
See [artwork provenance and source form](docs/release/ARTWORK.md).

The grant does **not** relicense the delivered research corpus, acquired
references, third-party fonts/artwork/samples/banks, M-VAVE firmware, device
dumps, private libraries or vendor SDK/toolchain binaries. These retain their
existing rights and provenance. An
official vendor asset with an explicit redistribution license may be included
only under its own terms, with its exact source, hash and notices recorded.
A private unit dump is not such a distributable asset.

The official M-VAVE `fm1_open` repository at commit
`b178ac43c25f010c60a878056fb5331fe693fd62` now explicitly licenses its
`sdk/firmware/FM-1_015.fwsc` resource under Apache-2.0 in THIRD_PARTY.md.
That specific public image has a different layout from the V15 application
already qualified on our units. It is not included or enabled for installation
in this build. A redistribution grant is separate from safe migration and
rollback qualification. The open V13 line also has distinct code/SDK terms and
storage layout; it is not relicensed by this FMER decision. See
[the pinned interoperability review](docs/research/2026-10-18-community-interoperability.md).

## Attribution and project direction

Keep existing copyright notices, license texts, provenance and modification
notices. [NOTICE](NOTICE) identifies the incorporated foundations;
[DEPENDENCIES.md](DEPENDENCIES.md) records versions and limitations.

The owner directs the official FMER project and releases. Public testing and
feedback are welcome. Code-contributor status is reserved: outside pull
requests require the maintainer's explicit prior permission. This is a
repository participation policy, not an additional restriction on the GPL.
Recipients retain their GPL rights to use, modify, fork and redistribute,
including commercial distribution. Do not imply that an unofficial build is
an official FMER release. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Distribution checklist

1. Ship GPLv3, the applicable dependency notices, and the corresponding source
   matching the exact firmware and companion binaries. Include build/install
   scripts, original default recipes and all required interface definitions.
2. Keep Felucca/SLOOP GPL notices and MSFA Apache-2.0 notices. The companion ZIP
   contains root licensing documents, `notices/` and `Corresponding Source.zip`.
   See [source/build guidance](docs/SOURCE_BUILD.md).
3. Verify that the source archive rebuilds from its documented prerequisites.
   A file named "Corresponding Source" is not, by itself, a compliance finding.
   Resolve required source and installation-information obligations before
   publishing binaries; do not substitute an untested download promise.
4. 734-r2 builds its selected runtime from licensed Newlib/LLVM source and includes
   source/notices. It links no vendor binary runtime archive. The compiler remains
   an external prerequisite and is not redistributed. Preserve this boundary;
   do not treat it as clearance for a different SDK or an older binary.
   The original FMER splash permission is recorded in the artwork source notice;
   it does not grant rights to unrelated third-party artwork.
   Stock resources require an explicit per-asset license and admission review.
5. Keep private device data, personal recordings, AppData and imported banks
   out of published artifacts. A beta does not waive license obligations.

GPL permits charging for copies; it does not impose a zero-price condition.
Private modifications need not be posted publicly merely because they exist.
Distribution of covered works carries the license's source and notice duties.
FMER is provided without warranty to the extent permitted by law; see LICENSE.

The identified linked-runtime gap is addressed by the source-built734-r2 route.
Configuration/EQ data are sourced from the explicitly Apache-licensed public
resource, with complete attribution and no private dump dependency. The original
stock application and opaque device trailer are not bundled. Read the
[options, exact boundaries and verification](docs/release/RUNTIME_REVIEW_734.md).
This does not change the separate requirement for owner-authorized publication.

Primary references: [GNU GPLv3](https://www.gnu.org/licenses/gpl-3.0.html),
[GNU license FAQ](https://www.gnu.org/licenses/gpl-faq.en.html), and
[Apache/GPL compatibility](https://www.apache.org/licenses/GPL-compatibility.html).
