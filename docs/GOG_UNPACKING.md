# Unpack GOG deliveries without running their installers

fDisBull keeps two GOG delivery paths separate because humanity did not settle
on one wrapper format and then stop inventing more.

| Delivery | Operation | Execution boundary |
| --- | --- | --- |
| Inno Setup offline installer | `gog-list`, `gog-unpack` | Built-in native reader; installer and extracted programs are not executed. |
| GOG Galaxy UPX wrapper | `gog-galaxy-rebuild` | Rebuilds a caller-captured mapped PE image; fDisBull does not download, launch or attach to Galaxy. |

## Inno Setup offline installers

`gog-list` and `gog-unpack` read a local GOG offline installer using fDisBull's
**built-in** Inno Setup reader. No external `innoextract`, Wine, subprocess or
optional Windows debugger backend is needed. They do not execute the Windows
installer or its extracted programs.

The supported profiles are **Inno Setup 5.5.7 Unicode and 5.6.2 Unicode**,
including the observed GOG Galaxy multipart payloads. The reader validates the loader table, LZMA1 metadata
blocks, file-location table, stored/LZMA2 data chunks, Inno 5.3.9+ x86 CALL/JMP
filter, per-chunk SHA-1, GOG zlib part sizes and final MD5. Other Inno versions,
external source slices, encrypted payloads, unknown compression and malformed
checksums are refused rather than guessed. This is not a universal GOG archive
reader or an installer runner.

### Profile identity and delivery checks

The 5.5.7 header predates the two environment/association strings introduced in
5.6.1. Its layout is selected explicitly, not guessed by retrying a failed parse.
The manifest reports the actual accepted profile. Compressed payloads require
the declared LZMA2 method; unknown profiles/compressors refuse without trying an
external program. This extension does not admit all versions between the two
named profiles or add external installer-slice support.

A package version alone is insufficient: the earlier 0.32.0 candidate at
`c80bff0` still used the external adapter. Native extraction was introduced by
!80 and incorporated into !95. Build the native-containing source, rather than
repacking that earlier wheel or installing an executable as a workaround.

Before delivering a native-capable package, run the narrow source-identity check
alongside the normal distribution/privacy checks:

```bash
python scripts/check_native_gog_distribution.py \
  dist/fdisbull-0.32.0-py3-none-any.whl \
  dist/fdisbull-0.32.0.tar.gz dist/fdisbull-0.32.0-tool.zip
python scripts/check_native_gog_distribution.py /private/new-offline-kit.zip
```

This check reads archive contents without importing them. It requires both
native modules, the adapter import, the two declared profiles, and identical
module bytes across supplied application artifacts. It also rejects direct
subprocess imports. It is a separate explicit check, not a replacement for
`check_dist.py`, a comprehensive code-security audit, or runtime qualification.
Follow it with extraction from an isolated installed wheel with an empty PATH
and process launches forbidden. Unknown input must fail, not fall back.

The authored tests in `tests/test_native_inno_profiles.py` exercise real CRC-
framed metadata, stored/LZMA2 payloads and GOG zlib reconstruction for both
profiles without game data. Corrupt hashes, unknown versions/compressors and
unsafe destinations must refuse. These fixture tests are distinct from
acceptance against privately supplied original installers.

### List before extracting

Keep the downloaded installer and its adjacent `.bin` parts together. Choose a
private output directory **outside the fDisBull checkout** for licensed files:

```bash
fdisbull gog-list "/private/downloads/setup_owned_game.exe"
fdisbull gog-list "/private/downloads/setup_owned_game.exe" --include "GAME/"
fdisbull gog-unpack "/private/downloads/setup_owned_game.exe" "/private/targets/new-game" --include "GAME/"
```

`--include` is repeatable and applies to both the inventory and extraction.
Matching is case-insensitive: an exact member path, a directory prefix such as
`GAME/`, or an `fnmatch` pattern such as `*.EXE`. It is not a shell glob and a
bare filename does not match a member in another directory. Inspect the filtered
list first. Include the game's data, launch scripts and configuration when
preparing a playable target. Extracting only an executable is useful for static
analysis but may not produce a runnable game. Omit `--include` to extract the
whole installer payload.

An existing output path is refused, including an empty directory or symlink.
The command reserves a new directory, stages extraction inside it, checks that
the regular files match the inventory, then moves them into place. Large disc
images are moved within the same filesystem rather than copied again. A failed
attempt removes only its newly created directory; it never replaces an earlier
target. Installer member paths with traversal, absolute paths or ambiguous case
collisions are refused.

The output contains `gog-unpack-manifest.json` with the native reader profile,
source SHA-256, selected paths, file sizes and SHA-256 hashes. The installer and
adjacent files matching its basename plus `-*.bin` are hashed before and after
the operation. The adjacent-part list records provenance candidates, not
individually traced file consumption; both supported profiles require embedded
slices. Input changes, unexpected output files, links and incomplete extractions
are errors. Source installers remain unchanged.

## Galaxy UPX wrappers

A Galaxy wrapper is not the corresponding offline installer and does not
necessarily contain the game payload. The inspected profile is a PE32 wrapper
whose packed entry is in `UPX1`, with the application restored into `UPX0` before
an observed transfer to its OEP.

`gog-galaxy-rebuild` accepts four already captured inputs:

1. the unchanged owned wrapper;
2. its mapped module image after unpacking;
3. a `fdisbull-chimprec-capture-1` process/thread/OEP receipt;
4. the loaded-module export map used to resolve runtime IAT pointers.

It validates the wrapper shape and source identity, recovers or verifies IAT
slots, applies explicit invalid-thunk decisions, and uses the CHimpREC PE writer
to produce a fixed-base unsigned analysis reconstruction. It does **not** attach
to a process, bypass anti-debugging, download a product or claim genuine Windows
DLL addresses merely because the caller supplied nonzero tokens.

See [CHimpREC captured-image recovery](CHIMPREC.md) for the capture schema,
rebuild behavior, command example and limitations.

## Find the program to analyze

The Inno manifest marks `.exe`, `.com` and files beginning with `MZ` or `ZM` as
**executable candidates**. A DOS sound driver can have a different extension;
a Windows setup helper can also be an executable candidate. These flags do not
identify the main game, establish a DOS COM profile or prove that a file runs.
Read included launch configuration and batch files before selecting a target:

```bash
fdisbull inspect "/private/targets/new-game/GAME/MAIN.EXE"
fdisbull import "/private/targets/new-game/GAME/MAIN.EXE" "/private/analysis/game.fdb"
fdisbull analyze "/private/analysis/game.fdb" --max-instructions 10000
fdisbull analysis-status "/private/analysis/game.fdb"
```

Use an explicit `--image com` only after qualifying a COM input. An MZ stub can
lead to an LE protected-mode program, and an MZ DOS game can contain appended
overlays. Successful extraction or PE reconstruction does not establish loader
support, game execution or complete analysis. Disc ripping, audio conversion and
movie framing remain separate format-specific operations.

## Agent protocol

The Inno methods work without a project:

```json
{"method":"gog-list","params":{"path":"/private/downloads/setup_owned_game.exe","include":["GAME/"]}}
{"method":"gog-unpack","params":{"path":"/private/downloads/setup_owned_game.exe","output":"/private/targets/new-game","include":["GAME/"],"timeout":300}}
```

The Galaxy coordinator is also projectless through its module CLI:

```bash
python -m fdisbull.gog_galaxy_cli \
  /private/wrapper.exe /private/mapped.bin \
  /private/capture.json /private/exports.json \
  /private/rebuilt-wrapper --candidate-slot 0x00473000
```

Python callers can use `fdisbull.gog_unpack.list_gog/unpack_gog` and
`fdisbull.gog_galaxy.rebuild_galaxy_capture/rebuild_galaxy_files`. The Inno
`timeout` is an integer from 1 to 3600 seconds for native parsing, source hashing
and extraction, defaulting to 300. Adjacent-part receipt hashing happens outside
that deadline. Native format details and evidence are in
`docs/NATIVE_INNO_562.md`.
