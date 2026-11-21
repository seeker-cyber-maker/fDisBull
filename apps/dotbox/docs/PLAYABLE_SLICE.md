> Historical dependent-prototype instructions. For the current standalone cut,
> use [STANDALONE.md](STANDALONE.md); no fDisBull environment is required.

# First playable development slice

This slice owns one visible original DOSBox-X game across client connections.
It reuses an installed fDisBull core and adds explicit native input ownership.
It has been exercised locally on macOS with an authored DOS graphics fixture.
Dot-cloud installation, audio, background learning and automatic synchronization
with the desktop's built-in takeover control remain separate acceptance work.

## Prepare the runtime

Use an existing compatible fDisBull Python environment. Build DOSBox-X with the
pinned fDisBull stable agent patch and [DotBox ownership overlay](../native/README.md).
A stock or spectator-only backend is refused rather than presented as cooperative.
No full game conversion or QEMU runtime is required.

For checkout development, point Python at this source and the prepared core:

```sh
export PYTHONPATH=/path/to/DotBox/src:/path/to/fDisBull/src
```

Use that environment's Python in the commands below. Do not download a package
merely because its registry name matches a dependency; use the established core
and its reviewed dependencies/offline package.

To prepare the authored fixture in a private runtime directory:

```sh
mkdir -p /private/work/dotbox-game
python /path/to/DotBox/examples/input_playground.py /private/work/dotbox-game/PLAY.COM
```

It draws a square moved by arrow keys or WASD. Escape exits. The generator refuses
to overwrite an existing output. It contains no commercial game code or assets.

## Own a persistent session

Run the owner process in one terminal or retained foreground tool session:

```sh
python -m dotbox serve \
  --directory /private/work/dotbox-session \
  --project /private/work/play.fdb \
  --program /private/work/dotbox-game/PLAY.COM --image com \
  --game-dir /private/work/dotbox-game \
  --executable /path/to/dotbox-compatible/dosbox-x \
  --manual-control
```

The session directory is created with permissions 0700; a pre-existing directory
must already be private and owned by the current user. Its private `session.json`
points at a loopback endpoint and a separate credential file. Never share those
runtime files or put credentials in command arguments/remote URLs.

The game initially starts paused with ownership unclaimed by DotBox. The
`--manual-control` flag explicitly enables development handoff commands. It does
not read or control the desktop's Take over / Return control state. Without it,
the current slice refuses control selection because no platform provider is attached.

In a second terminal/tool call, observe the session and choose an owner:

```sh
python -m dotbox status --session /private/work/dotbox-session/session.json > /private/work/status.json
python -m dotbox control human --resume \
  --session /private/work/dotbox-session/session.json \
  --lease /private/work/status.json > /private/work/human.json
```

Human keyboard/mouse now follows the normal native DOSBox path. Coordinate the
desktop takeover separately during this manual test. Agent injection is rejected
while the native owner is human. `--resume` only resumes a known startup/explicit
pause boundary; it leaves breakpoint, exit and unknown stops visible.

Return to agent input with the latest observed lease:

```sh
python -m dotbox control agent \
  --session /private/work/dotbox-session/session.json \
  --lease /private/work/human.json > /private/work/agent.json
python -m dotbox key left \
  --session /private/work/dotbox-session/session.json \
  --lease /private/work/agent.json
```

An ownership transfer clears pending/held input and advances a generation. An
old lease or an instance from a restarted service is refused. Receipts describe
accepted/queued input; observe the next completed frame to establish its game effect.
If a request loses its response, inspect the current state rather than replay it.

Capture the original game's latest completed frame without advancing it:

```sh
python -m dotbox frame --session /private/work/dotbox-session/session.json \
  --output /private/work/frame.png
```

The output must be new. A first frame may be unavailable immediately after
startup; the service remains usable and a later read can observe a completed frame.
The optional click command requires a mode/frame ID from an observation.

Clients can disconnect between commands. The owner process and game remain
alive. Explicit `pause`, `play` and `close` commands require a lease. Close it
when finished:

```sh
python -m dotbox status --session /private/work/dotbox-session/session.json > /private/work/final.json
python -m dotbox close --session /private/work/dotbox-session/session.json --lease /private/work/final.json
```

The owner reaps its emulator and removes discovery/credential files. Stopping
the owner process also ends the game; this slice does not yet restore a game
after owner/computer termination. Persistent checkpoint selection is later work.

## Development checks

The ordinary tests need pytest and the prepared fDisBull core on Python's path.
Set optional native inputs to include the real compiled/source checks:

```sh
DOTBOX_DOSBOX_EXECUTABLE=/path/to/dotbox-compatible/dosbox-x \
DOTBOX_DOSBOX_BASE_SOURCE=/path/to/pinned/pre-overlay-base \
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -rs -p no:cacheprovider
```

The source-application check needs only the pinned base files named in the overlay
manifest. Socket tests use synthetic game boundaries; native protocol and visible
host-keyboard acceptance are distinct evidence. A successful local run does not
qualify Dot's actual computer or the private viewer control-channel integration.
