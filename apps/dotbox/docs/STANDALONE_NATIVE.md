# Standalone DOSBox-X source and build

DotBox includes the source patches, recipe, hashes and license notices needed to
prepare its ownership-enabled DOSBox-X. No fDisBull checkout or Python package
is needed. Preparation requires Python 3.12 or later, Git, and either network
access to the pinned public DOSBox-X commit or a local Git repository containing
that commit. Preparation does not compile or install a binary.

From the DotBox source root, choose a new source directory outside the checkout:

```sh
python scripts/prepare_native.py /path/to/new/dotbox-dosbox-x
```

This fetches only the pinned commit into temporary storage, exports that
immutable commit, applies the included stable native patch followed by DotBox's
cooperative-input patch, verifies all 38 changed/new result files, and publishes
the prepared directory after every check passes. Existing output is verified
and reused; conflicting content is refused. A failed attempt removes only its
own temporary preparation directory. The output's `.dotbox-source.json` records
the recipe, upstream and patch identities, and explicitly records that no
native build was performed.

For offline preparation, use a local upstream Git object store:

```sh
python scripts/prepare_native.py /path/to/new/dotbox-dosbox-x \
  --upstream /path/to/dosbox-x-git-repository
python scripts/prepare_native.py /path/to/new/dotbox-dosbox-x --check
```

The local repository may have active changes. Preparation reads the exact
pinned Git commit and does not read, reset or alter its working tree. The check
command verifies the recipe inputs, the preparation receipt and every native
file changed by either patch. It does not validate unmodified upstream files,
build products, host libraries or a binary's behavior.

## Source identity

[`native/build-recipe.json`](../native/build-recipe.json) is the DotBox recipe.
It retains the complete base patch to preserve its independently recorded
identity rather than reconstructing a reduced patch with different provenance.
Only the native patch, its manifest and GPL text are copied from fDisBull;
fDisBull's application, disassembler, package, other emulator profiles and game
data are not native preparation dependencies.

| Input | Pin |
| --- | --- |
| DOSBox-X commit | `029bd65c5dcc7cdc7f2e14e35278620d9707d969` |
| DOSBox-X tree | `68005f10ab25418b40621875ad8e7a4bd867335c` |
| Base patch origin | fDisBull `ce91c303f2fccd1db9b1e3917ecc8c98473bfdb9`, `experimental/dosbox-x` |
| Base patch SHA-256 | `bc0ca8c93deaf6cb96eea91e39176b2713ab333e29bfefcf730e1a1d3c75eb2f` |
| Cooperative-input/restore patch SHA-256 | Current `overlay_sha256` in [`native/manifest.json`](../native/manifest.json), also pinned in the build recipe |
| Native ownership protocol | `dotbox-input-control-1` |
| Native restore admission fence | `dotbox-restore-control-1`; control fencing only, not a complete rewind capability |

The [`native/manifest.json`](../native/manifest.json) binds the current ownership
and restore-fence overlay. The historical `fdisbull_*` field names identify the
overlay's base provenance; they are not runtime imports or checkout selectors.
The original base manifest is retained verbatim. Its historical verification
fields are not claims about a newly prepared or built DotBox delivery.

## Build

For an Apple Silicon Mac, the [local build-and-test helper](LOCAL_MACOS_BUILD.md)
sets up a private build, uses the bundled pinned SDL2 and runs the strict native
fixture gate. It requires a full DotBox source checkout, including tests;
`dotbox kit-export` alone is not that checkout. A fresh Mac Studio build passed
the complete eight-fixture gate on 17 November 2026; see the qualification scope
below. The helper passes the SDK selected by `xcrun` as `SDKROOT` to its child
build processes so direct Command Line Tools compiler invocations can find the
system libraries.

For a manual build, install the host's normal DOSBox-X development prerequisites:
a C/C++14 toolchain, autoconf, automake, pkg-config, SDL2 development files, ncurses,
libpng/zlib and Zstandard development files. Upstream configure may detect
additional optional system libraries. NASM and Python Pillow are needed only
for upstream assembly-fixture acceptance, not to prepare this source.

In the prepared directory, run the commands retained in the recipe:

```sh
./autogen.sh
./configure --enable-sdl2 --enable-debug=heavy --enable-dosbox_agent \
  --enable-agent-zstd --disable-avcodec --disable-libslirp --disable-libfluidsynth
make -j2
```

The resulting executable is `src/dosbox-x`. SDL2, heavy debugging and the native
agent must be enabled; a stock DOSBox-X executable lacks DotBox's protocol.
The flags preserve the already exercised native configuration. Build memory
and prerequisites are host-dependent; follow the host's heavy-job policy when
applicable. Preparation and ordinary metadata tests do not start a heavy build.

Keep build output outside Git. Before distributing a binary, retain its hash,
host/architecture, toolchain/configuration and linked-library identities, the
full corresponding prepared source, and required notices. See
[`native/dosbox-x/NOTICES.md`](../native/dosbox-x/NOTICES.md) and
[`native/dosbox-x/COPYING`](../native/dosbox-x/COPYING).

## Qualification boundaries

Source preparation checks all 38 final result hashes against the exact pinned
base; those source checks do not compile a complete emulator. Compiled standalone
policy tests cover generation admission, unchanged owner and invalidation before
cleanup/failure. These remain evidence of the policy and source preparation,
not binary reproducibility.

Separately, a fresh Mac Studio developer build passed the full native gate on
Darwin 27.2.0 arm64 with Python 3.12.16: four headless and four visible fixtures,
pytest exit zero, no skips/failures/errors and an unchanged executable SHA-256.
The installed offline-kit doctor also passed. The
[sanitized native-build receipt](https://github.com/seeker-cyber-maker/DotBox/blob/codex/local-macos-build-20261117/docs/evidence/local-macos-native-2026-11-17.json)
binds that run to its measured checkout plus the one-line SDK environment fix.
It does not qualify other hosts, a signed application, a portable offline release
or original-Dot desktop integration. Earlier local arm64 executables remain
historical evidence and were not substituted for this fresh build.

For each intended host, build and identify a fresh executable, then run the
DotBox native protocol and full-service acceptance tests from a source checkout:

```sh
python scripts/test_native.py \
  --executable /absolute/path/to/src/dosbox-x \
  --report-dir /absolute/path/to/new/native-report
```

This requires exactly eight executed native fixtures, no skips and an unchanged
executable hash. Ordinary pytest may skip these fixtures when
`DOTBOX_DOSBOX_EXECUTABLE` is absent; its exit status alone is not native
acceptance. The helper's `--mode headless` runs four fixtures and explicitly
leaves the visible portion unqualified. Native acceptance must
exercise actual startup, screenshot/state access, agent-to-host ownership,
return to agent, held-input cleanup, rejection of stale input, continued play
and process cleanup. Dot's supported takeover event source and visible
keyboard/mouse behavior must be checked on Dot's actual desktop separately.
Source tests, an executable's existence and prior fDisBull qualification do not
establish that desktop result. Packaging, binary distribution and runtime
activation are separate delivery checks.

The restore fence intentionally changes raw `state.load`: clients must supply
an observed `expected_generation`, and old requests must never be retried with
a newly fetched value. An optional native test checks refusal and failed-load
generation invalidation when a matching executable is supplied. Complete
memory-only recovery additionally needs neutral captured/restored input, a
qualified DOS file/device boundary, post-failure closure, new provider context
and fresh rendered observations. No player rewind API is exposed by this cut.
