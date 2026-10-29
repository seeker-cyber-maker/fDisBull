# fDisBull agent quickstart

Use this page to find the right fDisBull interface for a task. Replace every
example path with a path selected by the user. The Python distribution does not
include a native emulator, game files, saved states or project databases.

## Discover commands and the bundled skill

```text
fdisbull --version
fdisbull methods
fdisbull agent-skill --index
fdisbull agent-skill --reference SKILL.md
```

`methods` prints the JSON method names and their parameter summaries.
`agent-skill --index` lists each guide's purpose without transferring its text.
Choose the relevant guide, then use `--reference` to retrieve it.
`agent-skill` returns the packaged investigation instructions and references as
JSON; it reads no project and does not register or install a skill into an
agent's own discovery directory. Fetch a single resource when needed:

```text
fdisbull agent-skill --reference references/workflows.md
fdisbull agent-skill --reference references/scenes.md
fdisbull agent-skill --reference references/runtime-navigation.md
fdisbull agent-skill --reference references/udl-uil-udc.md
```

With a source checkout, the bundled files are under
`src/fdisbull/skills/fdisbull-investigate/`. The current JSON protocol has a
one-shot `request` command and a retained `serve`/`debug` session; a one-shot
request cannot keep a live emulator attached.

## Choose a route

### Inspect an executable without running it

```text
fdisbull identify /path/to/program
fdisbull inspect /path/to/program
fdisbull import /path/to/program /path/to/analysis.fdb
fdisbull analyze /path/to/analysis.fdb --max-instructions 10000
fdisbull analysis-status /path/to/analysis.fdb
fdisbull functions /path/to/analysis.fdb
fdisbull disasm /path/to/analysis.fdb --address 0x1000 --lines 40
```

For DOS COM files, select `--image com` explicitly when importing. A suffix
alone does not establish the file format. Analysis limits may leave work
pending; inspect status and do not call a budget stop complete. `render` exports
from saved project state without operating a GUI.

### Observe a real DOS target

```text
fdisbull debug /path/to/analysis.fdb \
  --executable /path/to/compatible-dosbox-x \
  --game-dir /path/to/game \
  --backend dosbox
```

The backend must be separately prepared and compatible with the requested
features. The debugger binds the executable and mapped version to the project;
use the original files and version the user selected. Drive ordinary guest
input, then verify that the target consumed it and produced the claimed state
change. `--dot-mode` only requests a compatible watch window; headless remains
the default. See `docs/DOSBOX_DEBUGGER.md` for detailed launch and command usage.

For PE or machine-level work, use the backend, kernel and runtime inputs
documented for that interface. Do not assume DOS options or address mappings
carry over.

### Inspect scenes or qualify movement

Use a scene revision for screenshot context, object recognition, readiness and
guarded clicks. Use a spatial-map revision for game-unit coverage, actor
footprints, obstacles, hazards, portals and interaction zones. Native movement
still uses the original guest input. A candidate route is not proof that the
engine follows it. Read `docs/SCENE_NAVIGATION.md` and
`docs/SPATIAL_MAPS.md`, then load the matching `scenes.md` or
`runtime-navigation.md` skill reference.

### Use a text interface

For a local authored slice, install or run the independent player from a source
checkout:

```text
python -m pip install ./player
python -m fdisbull_player --package /path/to/slice.json
python -m fdisbull_player --package /path/to/slice.json --live \
  --save-dir /path/to/private-checkpoints
```

This player evaluates a declared JSON slice; it is not a native-game emulator
or a recovered interpreter. `--live` checkpoints turns, but successful
checkpointing does not establish that a package models an original game.
Read `docs/TEXT_PLAYER.md` and `docs/PLAYER_LIVE.md`.

For a qualified debugger-backed projection, start the local host:

```text
fdisbull text-host /path/to/private-host-config.json \
  --spatial-mode physical
```

Connect `fdisbull-player --connect HOST:PORT` to the host endpoint it reports.
The backend must be supplied in the private configuration along with the
project, game directory, projection and qualified runtime witnesses. The
line-oriented loopback protocol has no authentication or encryption; use it
only in a trusted local environment. Select `physical`, `assisted` or `story`
explicitly. `--fair-play` locks the host to physical movement and is a voluntary
policy, not an anti-tamper boundary. See `docs/TEXT_PROJECTION.md` and
`docs/SPATIAL_MAPS.md`.

### Inspect interpreted game data

For one AGI 2.917 logic resource in an uncompressed version-2 LOGDIR/VOL set:

```text
fdisbull agi-logic /path/to/LOGDIR /path/to/VOL-directory 1 \
  --profile 2.917 --max-instructions 1000
```

This is a bounded, read-only partial decoder. It does not show that the game
loaded or executed those bytes. To claim runtime behavior, qualify the resource
mapping and trace interpreter fetch, branch conditions and effects. See
`docs/AGI_LOGIC.md` and the interpreter section of `methodology.md`.

### Compare a source block with shared semantics

For the supported 0.23 DOS profile, read `udl-uil-udc.md` before using
`udl-lift-asm`, `udl-lift-c`, `udl-verify` or the `udc-*` commands. UDC currently
retains original x86-16 MZ/COM version-1 bytes; it does not generate general DOS
code or recover a whole game. A Z3 result covers only the explicit modeled
register boundary and assumptions. Read `docs/UDC_DOS.md`,
`docs/UDC_TESTING.md` and `docs/BOUNDED_PROOFS.md` for the supported schema and
limits.

## Keep results within their evidence

Static decode, authored scene geometry, diagnostic state edits, text
projections, bounded proofs and live ordinary input are different evidence
surfaces. Report which one supports each conclusion, with source/version and
context. Keep missing or unsupported behavior unknown. Keep game assets,
checkpoints and byte-retaining project databases private; export only the
requested authored scripts, selected evidence and receipts.
