# Public repository transition

The owner supplied `https://github.com/Nacsez/FMER.git` on 19 October 2026 and
authorized a **private** upload plus a **draft** release. Public visibility and
release publication remain withheld. The local checkout in `FMER GitHub/` is the
remote's source mirror; the original development repository retains private
history separately. Do not push its historical branches or tags to GitHub.

Keep the existing development workspace and its local history intact. It contains
historical references, evidence and material that should not become public.
Adding a remote to this repository and pushing its history is **not** the release
procedure. `.gitignore` does not remove previously tracked material or history.

## Prepared source export

Run `python tools/prepare_public_source.py --out "FMER Public Source 734"` with a
new output directory. The tool reuses the Companion corresponding-source allowlist,
adds public README/AGENTS and issue metadata, then writes a file-hash manifest and
ZIP. It never initializes git or contacts a remote. Its output is for review until
the distribution gates in RELEASE_READINESS.md are resolved.

Included: implementation, portable core, target adapter/loader, host UI, build and
test tools, original default recipes, offline Help and its editable figure sources,
release documentation, notices and the incorporated Felucca platform subset with
its pinned metadata. Compiler/normal headers are separate build prerequisites; the selected runtime
sources and public configuration-data recipe are now included.

Excluded: `.git` history, research corpus, private logs and AppData, device dumps,
saved user libraries, personal recordings, build directories, ZIPs, executables,
stock firmware executables, private banks and firmware release binaries.
The explicitly licensed public OEM V15 voice data and its notices are included;
see COMPANION_R4.md for provenance and conversion limits. The prepared source manifest
records exactly what is present. Dependency evidence is an explicit small list;
there is no general export of `evidence/`.

The public ignore rules keep the incorporated Felucca source trackable. Its
attributes preserve source bytes across checkout, because generated Help and
dependency records hash their inputs. The private workspace's broad acquisition
ignore and evidence export-ignore rules must not be copied into the public tree.

The allowlisted Felucca subset lives under `third_party/acquired/...` because the
builder's pinned-path verifier expects that layout. This is the sole acquisition
subtree exported. Do not copy the rest of `third_party/acquired` to make a build
work; supply the compiler and headers through documented command-line paths.

## Before updating the private draft

1. Rebuild host tests from the extracted source and check target link from the
   same tree with separately acquired, pinned toolchain inputs.
2. Retain the approved splash source/notice and retain the734-r2 source-runtime and public-resource notices.
3. Review the source manifest and archive contents for private data.
4. Match firmware, Companion source, runtime notices and release hashes.
5. Record a local annotated milestone tag without changing wire/build identity.

## Once publication is authorized

1. Regenerate the reviewed source tree from the approved local milestone.
2. Initialize a **new** repository in that export, commit the reviewed content,
   and set its remote to the owner-supplied URL. Do not inherit private history.
3. Configure the feedback destination in documentation and Companion only when
   the actual public URL exists. Test the resulting links.
4. Publish the source commit plus the exact qualified firmware and portable ZIP
   as release assets, with SHA-256 checksums, limitations and source correspondence.
5. Verify a download/extract/launch/install/help/feedback roundtrip on a second PC.

For this private staging step, carry out the source push and upload assets with
the release's `draft` flag true. Verify repository visibility, release state,
local/remote commit equality and each uploaded asset hash after transfer. The
maintainer owns the final Publish action. Never enable automated publication.

## Keeping release files current

`tools/stage_github_release.py` creates a fresh local asset set. It verifies that
the standalone firmware exactly matches the firmware inside Companion and its
catalog, checks the portable manifest, and requires passing deployment evidence
for that exact Companion ZIP. It packages original media and corresponding source,
then generates checksums and a release manifest. It performs no network writes.

Attach only that verified set to the matching draft. Recheck the remote hashes
and remove obsolete draft assets when deliberately superseded. Once a release
has been published, preserve its tag and bytes; create a new build/package tag
for a later stable set. Updating a draft is not authority to publish it or mark
an untested development build as stable. Keep the700-series firmware identity.

Public tests use the same 700-series build system. The repository can describe
the project as pre-1.0; no beta branch or alternate firmware identity is needed.
A future 0.7xx.xx naming scheme is a separate versioning decision. Do not retag
the same name onto changed binaries: package hashes distinguish documentation
refreshes that retain firmware 734.

The owner maintains direction and release authority. Issues accept feedback on
Companion, installation, firmware navigation, sounds, effects, arp, sequencer,
voice modes, MIDI and other observations. Categories are optional. Outside PRs
require prior approval, without limiting the legal rights granted by GPLv3.

Bluetooth is the first feature investigation after release and primary feedback.
Its transport scaffolding is not a released radio implementation. Reopen it with
full runtime linking, memory reuse, loaded audio/latency, recovery and three-unit
group evidence before advertising wireless capability.
