# DotBox @VERSION@ for Dot — Linux x86_64

This development bundle contains the standalone DotBox application, its small
shared core, four pinned runtime wheels, the compatible DOSBox-X executable and
its static library closure, required notices, and corresponding source archives.
It contains no game files or private saved sessions. Python is supplied by the
host: use **CPython 3.12 on Linux x86_64**.

## Install once

From this extracted bundle, first check its integrity:

```sh
python3.12 install.py --verify-only
```

Then install into a **new** private directory whose parent already exists:

```sh
python3.12 install.py --prefix /absolute/private/dotbox-dev10
```

Omitting `--prefix` creates `install/` inside this bundle. Existing installations
are refused, including partial failed installations; choose another new prefix.
Installation uses only the four hash-pinned wheels with `pip --no-index
--require-hashes`. It does not install fDisBull, fetch dependencies, use global
site-packages, compile an emulator, or alter an existing session. The required
free-space estimate comes from this payload; the builder's 40 GiB reserve is not
imposed on consumer installations.

Check the installed offline kit:

```sh
/absolute/private/dotbox-dev10/bin/dotbox doctor
/absolute/private/dotbox-dev10/bin/dotbox guide
```

The doctor should identify the installed layout and offline readiness. It does
not launch a game or qualify the current desktop's input, takeover or audio.
The installation receipt records exact source, manifest and native identities.

## Start an original game

Use your own game directory and a new private session/control-store location:

```sh
/absolute/private/dotbox-dev10/bin/dotbox serve \
  --directory /absolute/private/game-session \
  --project /absolute/private/game-controls.db \
  --program /absolute/private/game/PLAY.COM \
  --game-dir /absolute/private/game \
  --executable /absolute/private/dotbox-dev10/bin/dotbox-dosbox-x
```

Replace `PLAY.COM` with the original game executable. The explicit
`--executable` remains required. The DotBox launcher also exports
`DOTBOX_DOSBOX_EXECUTABLE` for compatible diagnostics; the environment variable
does not replace that CLI argument.

The native launcher runs the retained executable through its supplied Linux
loader and library directory. It makes no ELF changes and does not force a dummy
SDL driver. Default visible play and the outer desktop harness retain their
existing input behavior. A shell without a usable display cannot establish
visible play; headless diagnostic evidence is separate from actual Dot desktop
acceptance. `--manual-control` is a separate diagnostic mode, not a substitute
for the platform's Take over / Return control flow.

## Scope and recovery

DOSBox-X is the base gameplay runtime. A separately delivered AGI CPU companion
is optional analysis tooling; it is not a new `dotbox serve` backend.
Read `RELEASE_NOTES.md` and the accompanying qualification report for the tested
host and remaining limits. Packaging itself does not establish game completion,
visible takeover, audio, a stable release tag or hosted CI.

`manifest.json` and `SHA256SUMS` bind every immutable bundle payload file. Their
checks establish content consistency, not a publisher signature; retain the
delivery's independently recorded archive checksum. Keep the bundle immutable.
Place games, evidence and session data outside it. The installer copies the
runtime, notices and source archives into the chosen prefix, so moving this
download afterward does not break the launchers. Keep the installed prefix at
its chosen path because Python virtual environments are not relocatable.
