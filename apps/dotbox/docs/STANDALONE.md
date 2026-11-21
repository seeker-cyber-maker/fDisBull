# Standalone engine cut

The [verification report](evidence/standalone-engine-2026-11-16.json) records the
clean installation and bounded native checks.

DotBox owns its Python runtime and SQLite control store. No fDisBull package or
source checkout is required. Python 3.12+, Pillow and pinned iced-x86 1.22.0 are the declared Python
requirements; a compatible native DOSBox-X executable and its platform libraries
are required to run a guest. See [native preparation](STANDALONE_NATIVE.md).
For a developer build on the Mac Studio, see the
[local macOS build and test procedure](LOCAL_MACOS_BUILD.md).
The separate [cloud Linux test record](https://github.com/seeker-cyber-maker/DotBox/blob/codex/local-macos-build-20261117/docs/LOCAL_LINUX_TEST.md)
records a fresh Linux native build, eight executed fixtures and one successful
Police Quest controls route. It used checkout source and an existing Python
environment; it is not a fresh installed-wheel or portable-release acceptance.

The current wheel includes [the learning kit](LEARNING_KIT.md): bounded offline
inspection, a saved learning focus, play instructions and native source/build
resources. `dotbox doctor` checks that kit; `dotbox guide` starts its instructions.
Use `dotbox kit-export --directory NEW_DIRECTORY` to materialize native source
resources and helpers. Exporting source does not prepare a native executable.

## Install

```sh
python3 -m venv /private/dotbox/venv
/private/dotbox/venv/bin/python -m pip install /path/to/dotbox.whl
/private/dotbox/venv/bin/dotbox --help
```

A clean installation must use an ordinary wheel, with no source-tree PYTHONPATH,
editable install or fDisBull environment. Verification records distinguish Python
installation, native execution and actual Codex cloud integration.

## Display size and coordinates

Choose presentation size when starting a visible session with
`dotbox serve --window-scale 3` or `--window-scale 4`, alongside the usual
session, project, game and executable arguments. The optional integer scale
accepts 2 through 5 and selects DOSBox-X's existing `normalNx` software scaler.
Omitting it preserves the previous launch configuration. The Python equivalent
is `NativeSession(..., window=True, window_scale=4)`; the backend configuration
key is `window_scale`. Headless sessions reject an explicit window scale.

For a 320 by 200 mode using ordinary double-width/double-height rendering, the
presentation sizes are:

| Scale | Displayed game pixels |
| --- | --- |
| 2 | 640 by 400 |
| 3 | 960 by 600 |
| 4 | 1280 by 800 |
| 5 | 1600 by 1000 |

Choose a size that fits the available desktop. This is a fixed integer scaler,
not automatic fitting; other DOS video modes and aspect settings can produce
different display dimensions. A surface-rendered window can grow while its
game image remains centered at the previous size, so maximizing the window
alone does not establish that the game image grew.

Keep game/world coordinates, physics, map data and control algorithms independent
of this setting. Native screenshots retain the guest framebuffer dimensions;
saved native mouse controls use that same guest pixel grid. A desktop or browser
input adapter must map its pointer through the current rendered game rectangle,
excluding borders and letterboxing. It must not store desktop pixels as game
coordinates. A renderer reset can invalidate frame/mode identities: acquire a
fresh observation, preserving the existing world model and controller.

## Use the Codex desktop harness

By default, the service starts the original game with native host input enabled.
Both Dot and the user use the outer harness's ordinary keyboard/mouse path;
Codex's existing Take over / Return control flow decides who can send that input.
DotBox neither replaces those buttons nor needs to guess their owner from pixels.
Frame observation and control authoring remain available. Direct agent RPC input,
play and pause are refused in this mode, so they cannot bypass the outer capture
boundary. The service reports `owner: harness`; platform owner stays `unknown`
unless the optional [ownership bridge](OWNERSHIP_BRIDGE.md) is explicitly bound
and receives fresh viewer evidence. Existing-viewer keyboard/mouse operation is
verified separately from native DotBox cloud installation. The bridge's actual
viewer-to-local-receiver path is verified. Later [connector verification](
evidence/ownership-connector-live-2026-11-16.json) establishes read-only status
delivery to the original Dot context; executing desktop input through the same
turn receipt remains unqualified. The preserved [transport investigation](SCREEN_TRANSPORT.md)
records earlier internal signals without claiming a supported Dot-facing API.

## Explicit native handoff diagnostics

For the explicit native RPC diagnostic path, start one service with your own
game directory and native executable:

```sh
dotbox serve --directory /private/dotbox/session \
  --project /private/dotbox/controls.db --program /private/game/PLAY.COM \
  --game-dir /private/game --executable /path/to/dosbox-x --manual-control
```

The `--manual-control` flag explicitly selects the local handoff test path. The
Codex/WebRTC harness owns its own Take over / Return control UI; this flag does
not subscribe to those events or change WebRTC input capture.

Read a lease, transfer to the human, then return it to the agent:

```sh
dotbox status --session /private/dotbox/session/session.json > /private/dotbox/status.json
dotbox control human --session /private/dotbox/session/session.json --lease /private/dotbox/status.json
dotbox status --session /private/dotbox/session/session.json > /private/dotbox/human.json
dotbox control agent --session /private/dotbox/session/session.json --lease /private/dotbox/human.json --resume
```

Native transfer releases tracked inputs and advances ownership generation.
Older agent leases are rejected; agent keyboard/mouse input is refused while
the human owns the guest. Unknown platform ownership remains unknown. Automatic
platform synchronization remains an external acceptance gate until a supported
provider is available and tested. Do not infer it from focus, pixels or silence.

## Storage and scope

New projects use a DotBox-only SQLite schema, executable SHA-256 binding and
immutable control revisions. Existing fDisBull FDBs are refused before mutation;
retain them as originals and author/import reviewed control definitions into a
new DotBox store. This cut does not silently migrate analysis databases or
claim the old mapped-version identity for a new independent store.

The proven keyboard/mouse formats and absolute guest-frame `(x,y)` convention
remain. An accepted input is not a verified game transition. Original saves,
frames, project stores and session credentials stay private.

The package includes an offline AGI V2/2.917 census and state-bound cardinal
route proposals. Read `dotbox guide --topic agi` and `--topic navigation` for
scope and examples. Live engine-state capture, movement execution, fenced
rewind, additional engines, audio and original-Dot game qualification remain
separate integration work.
The previous local Dune reports describe the dependent prototype and are not
standalone qualification evidence.
