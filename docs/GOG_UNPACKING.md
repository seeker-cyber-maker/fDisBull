# Unpack a GOG DOS installer without Wine

`gog-list` and `gog-unpack` read a local GOG offline installer using the host's
native [innoextract](https://constexpr.org/innoextract/). They do not execute
the Windows installer or its extracted programs. Listing and static analysis
need neither Wine nor the optional Windows debugger backend.

Install the external reader separately:

```bash
# macOS
brew install innoextract
# Debian / Ubuntu
sudo apt install innoextract
```

These commands cover Inno Setup installers supported by the installed reader.
They are not a universal GOG archive reader: an unsupported installer, encrypted
payload, missing multipart file or newer Inno Setup revision produces an error.
There is no fallback that runs the installer. The native reader's version and
diagnostics are retained or reported.

## List before extracting

Keep the downloaded installer and its adjacent `.bin` parts together. Choose a
private output directory **outside the fDisBull checkout** for licensed files:

```bash
fdisbull gog-list "/private/downloads/setup_owned_game.exe"
fdisbull gog-list "/private/downloads/setup_owned_game.exe" --include "GAME/"
fdisbull gog-unpack "/private/downloads/setup_owned_game.exe" "/private/targets/new-game" --include "GAME/"
```

`--include` is repeatable and uses **innoextract's path-filter rules**, on both
the inventory and extraction. It is not a shell glob. A bare filename can match
several directories; inspect the filtered list first. Include the game's data,
launch scripts and configuration when preparing a playable target. Extracting
only an executable is useful for static analysis but may not produce a runnable
game. Omit `--include` to extract the whole installer payload.

An existing output path is refused, including an empty directory or symlink.
The command reserves a new directory, stages extraction inside it, checks that
the regular files match the inventory, then moves them into place. Large disc
images are moved within the same filesystem rather than copied again. A failed
attempt removes only its newly created directory; it never replaces an earlier
target. Installer member paths with traversal, absolute paths or ambiguous
case collisions are refused.

The output contains `gog-unpack-manifest.json` with the extractor version,
selected paths, file sizes and SHA-256 hashes. The installer and adjacent files
matching its basename plus `-*.bin` are hashed before and after the operation.
The adjacent-part list records provenance candidates, not individually traced
file consumption. Input changes, unexpected output files, links and incomplete
extractions are errors. Source installers remain unchanged.

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
same keyword arguments. `timeout` is an integer from 1 to 3600 seconds for
each extractor process, defaulting to 300.
