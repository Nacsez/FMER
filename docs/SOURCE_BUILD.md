# Rebuilding the supplied source

The portable companion includes `Corresponding Source.zip` alongside the
executable. Extract that archive into an empty working directory. Root LICENSE,
LICENSING.md and NOTICE describe the original FMER grant and dependency scope.
Build and test without connecting an instrument first.

## Host and companion

Use Python 3.13, CMake and the documented C++ build prerequisites in
DEPENDENCIES.md. From the extracted root:

```text
cmake -S . -B artifacts/build/host -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build artifacts/build/host --config Release
ctest --test-dir artifacts/build/host -C Release --output-on-failure
python tools/build_companion_help.py
```

CMake selects an available generator; use `-G` if your environment requires an
explicit installed generator. The full
workspace test command also checks the immutable research corpus, which is not
relicensed or copied into the companion source archive. Run the compiled tests
with `ctest --test-dir artifacts/build/host -C Release --output-on-failure`
when working with the reduced distributable source.

`python tools/dev.py test --config Release` is the full private-workspace audit;
it is not the reduced export's entrypoint. The public export deliberately omits
private corpus/evidence. Targeted portable Python checks can be run with unittest
discovery for `test_release_guide.py`; do not fabricate missing private inputs.

To reproduce the new documentation frames, build the CMake target
`fmer_feature_capture`, then run it with a `guide-` filename prefix inside an
existing output directory. Run `tools/build_release_media.py --captures <that
directory>` and `tools/build_companion_help.py`. PNG/PDF release exports additionally
use Playwright and a local Chromium browser via `tools/export_release_media.py`.
All image sources are local; no device access or hosted asset is needed.

The portable Windows build uses the pinned official Python embeddable runtime
and Windows .NET Framework compiler. `tools/build_companion_portable.py --out
<new-directory>` builds the launcher, copies the reviewed runtime and includes
defaults, help, firmware, source and notices. It does not download missing
prerequisites. `evidence/python-portable-runtime.json` identifies the runtime.
The companion uses a local browser interface; no hosted website is required.

## FM-1 target

`tools/build_fm1_candidate.py` compiles the target without touching hardware.
Its `--toolchain-root`, `--libcxx-root`, `--upstream-root` and `--out` options
select build inputs explicitly; use `--help` for exact invocation. The source
archive includes the selected Felucca platform sources at the path expected by
the builder, its LICENSE/README and the pinned Git tree metadata. Source
validation remains enabled. The builder stages and records FMER modifications
to control input, USB and MIDI UART code; it does not alter the acquired copy.

The required JieLi pi32v2 r3 toolchain and libc++ headers are pinned in
`evidence/target-toolchain.json`. The compiler and normal headers are separate
prerequisites with their own licenses; source-built runtime inputs are included; private acquisition directories and
device-specific dumps are not distributed. The firmware's original source,
generated header inputs, linker script and packaging/loader scripts are
included. Review `firmware/fm1/loader/PROVENANCE.json`, compatibility.h and write_policy.h before
building or modifying the updater.

The target build outputs an ELF and map, not automatically a qualified release.
Use the existing package/loader validation and preservation tests before any
write. Runtime memory-layout and calibration checks remain required. Changing
source does not justify bypassing those checks.

## Source runtime and public packaging (734-r2)

Target builds now default to `--runtime source`. The included Newlib/LLVM subset
is hash-checked and compiled locally; vendor libc/libm/compiler-rt archives are
not required or linked. `--runtime vendor-reference` is only an explicit private
comparison option. The additional llvm-ar tool pin is in tools/source_runtime.py.

Build the independent loader tests from firmware/fm1/loader/tests using CMake.
Then run `python tools/build_release_firmware.py --candidate <target-build>
--out <new-package-directory> --loader-test <fmer_portable_loader_test executable>
--stage-only --toolchain-root <pinned-compiler-directory>`. This creates an isolated package/catalog without replacing the
bundled release. It uses the public configuration/EQ JSON and generated format
metadata; no private ROM, vendor SDK payload or network download is needed.
Source and notices are under third_party/runtime and third_party/fm1_resources.
Keep stage-only packages separate until target and preservation tests pass.

See [the734-r2 review](release/RUNTIME_REVIEW_734.md) for exact hashes, memory,
numerical limits, target evidence and the external-compiler boundary.

## Earlier734-r1 source rehearsal

The following results describe the earlier vendor-runtime build, not734-r2.

The 734 extracted-source rehearsal configured and rebuilt the host executable
and codec tests in a fresh directory, rendered an audible chord, and passed
the seven DX7 adapter tests against that rebuilt executable. The final archive
also includes the loader's license and all offline-help figures. This was on
the development computer with its installed compiler; it was not a clean VM
or a bit-for-bit reproducibility test.

The19 October source-only export was separately configured and built for the
host and linked for FM-1 using the pinned compiler and libc++ headers supplied
outside the export. Its `.text`, `.ram_text` and `.data` loadable bytes exactly
match the qualified734 ELF. The whole ELF hash differs (non-loadable metadata);
no new firmware was packaged or installed from that reconstruction. This closes
the extracted-tree target-source gap, not clean-machine/VM qualification or
vendor-runtime terms. The initial sandbox compiler invocation was denied; the
reviewed compile-only retry succeeded. Results are in the release test record.

The earlier734-r1 licensing pass did not settle vendor-runtime terms.734-r2
addresses that issue with the source-built replacement described above.
Resolve all required corresponding-source and installation-information details
before a public binary release. Record exact compiler, source and output hashes
with the release. The owner licensed the original splash artwork and its editable
source under GPL-3.0-only on 19 October 2026. Both source packages include the
original `FMER SPLASH.png`, its generator and generated header. See
[the artwork source notice](release/ARTWORK.md) for the exact source hash and form.
