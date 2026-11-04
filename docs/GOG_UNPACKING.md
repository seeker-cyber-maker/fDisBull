# Unpack a GOG DOS installer without Wine

`gog-list` and `gog-unpack` read a local GOG offline installer using fDisBull's
**built-in** Inno Setup reader. No external `innoextract`, Wine, subprocess or
optional Windows debugger backend is needed. They do not execute the Windows
installer or its extracted programs.

The supported profile is **Inno Setup 5.6.2 Unicode**, including GOG Galaxy
multipart payloads. The reader validates the loader table, LZMA1 metadata
blocks, file-location table, stored/LZMA2 data chunks, Inno 5.3.9+ x86 CALL/JMP
filter, per-chunk SHA-1, GOG zlib part sizes and final MD5. Other Inno versions,
external source slices, encrypted payloads, unknown compression and malformed
checksums are refused rather than guessed. This is not a universal GOG archive
reader or an installer runner.

## List before extracting

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
target. Installer member paths with traversal, absolute paths or ambiguous
case collisions are refused.

The output contains `gog-unpack-manifest.json` with the native reader profile,
source SHA-256, selected paths, file sizes and SHA-256 hashes. The installer and
adjacent files matching its basename plus `-*.bin` are hashed before and after
the operation. The adjacent-part list records provenance candidates, not
individually traced file consumption; the supported profile requires embedded
slices. Input changes, unexpected output files, links and incomplete extractions
are errors. Source installers remain unchanged.

## Find the program to analyze

The manifest marks `.exe`, `.com` and files beginning with `MZ` or `ZM` as
**executable candidates**. A DOS sound driver can have a different extension;
a Windows setup helper can also be an executable candidate. These flags do not
identify the main game, establish a DOS COM profile or prove that a file runs.
Read the included DOSBox launch configuration and batch files to distinguish
the game, intro and support programs, then inspect the selected input:

```bash
fdisbull inspect "/private/targets/new-game/GAME/MAIN.EXE"
fdisbull import "/private/targets/new-game/GAME/MAIN.EXE" "/private/analysis/game.fdb"
fdisbull analyze "/private/analysis/game.fdb" --max-instructions 10000
fdisbull analysis-status "/private/analysis/game.fdb"
```

Use an explicit `--image com` only after qualifying a COM input. An MZ stub can
lead to an LE protected-mode program, and an MZ DOS game can contain appended
overlays. Successful unpacking does not establish loader support or complete
analysis of those formats. Disc ripping, audio conversion and movie framing
are separate, format-specific operations; this command preserves their bytes.

## Agent protocol

Both methods work without a project, including in a server with a default
project. Responses use the ordinary bounded-output policy:

```json
{"method":"gog-list","params":{"path":"/private/downloads/setup_owned_game.exe","include":["GAME/"]}}
{"method":"gog-unpack","params":{"path":"/private/downloads/setup_owned_game.exe","output":"/private/targets/new-game","include":["GAME/"],"timeout":300}}
```

Python callers can use `fdisbull.gog_unpack.list_gog` and `unpack_gog` with the
same keyword arguments. `timeout` is an integer from 1 to 3600 seconds for the
native parsing, source hashing and extraction deadline, defaulting to 300.
Adjacent-part receipt hashing happens outside that deadline. Native format
details and qualification evidence are in `docs/NATIVE_INNO_562.md`.
