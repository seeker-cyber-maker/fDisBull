# Persist and use the next control

Use the installed DotBox build and a prepared compatible DOSBox-X. Read
`dotbox guide --topic runtime` (or `docs/STANDALONE.md`) for first launch. The owner service
survives short-lived clients; keep that service alive. Current explicit
development ownership is separate from the desktop's built-in takeover UI.

In default desktop mode, use the supported ordinary desktop keyboard/mouse
tools under the current outer input owner. Native `act`, key, type, click,
play and pause RPCs are refused. The store still retains useful recipes and
observations. A saved guest-frame coordinate is not automatically a host-window
coordinate; an outer executor must establish its own fresh mapping.

For the player's selected intent or delegated goal, use an applicable known
control immediately. Observe its result and save useful
metadata afterward. Do not construct a wrapper or replay the input to save it.

Observe status and an original frame through the supported CLI:

```sh
python -m dotbox status --session /private/work/session/session.json > /private/work/status.json
python -m dotbox frame --session /private/work/session/session.json --output /private/work/frame.png
```

For the explicit `--manual-control` native diagnostic path only, use an existing
fresh agent lease when the agent owns input; do not select agent
ownership while the human is playing. If a manual test needs an explicit handback,
coordinate it first and use the runtime's `control agent --resume` only at an
admitted startup/pause boundary. A stored recipe never establishes ownership.

Record a learned absolute mouse click as a small JSON vocabulary. Replace every
example coordinate and frame size with your observed original guest pixels:

```json
{
  "format": "dotbox-control-set-1",
  "name": "opening",
  "controls": {
    "open_panel": {
      "authority": "player-input",
      "steps": [{"op": "mouse.click", "x": 40, "y": 90,
                 "width": 320, "height": 200, "button": "left", "hold_ms": 80}]
    }
  }
}
```

`x,y` are absolute guest-frame coordinates, independent of host-window size.
They are not deltas. Frame width/height must match at execution. Do not persist
runtime frame/mode IDs: the server captures fresh ones for every use. One named
mouse action contains one click; compose larger routes through separately
observed actions. Keyboard-only sequences remain supported. Expected dimensions
protect coordinate space, not scene identity; check current applicability before
calling a scene-dependent action.

Save metadata without replaying the input:

```sh
python -m dotbox harness-save --definition /private/work/controls.json --session /private/work/session/session.json --lease /private/work/status.json > /private/work/saved.json
```

Use `harness-save --parent REVISION` for an incremental compatible revision.
`harness-list` and `harness-info REVISION` find previous revisions after reconnect
or project reopen; there is no automatic latest selection. A new owner needs a
new lease. Old keyboard `fdisbull-macro-set-1` vocabularies remain supported.

## Explicit native diagnostic execution

Only in a service started with `--manual-control`, an applicable subsequent
action may select the saved revision through `dotbox act`. Do not immediately
repeat an action already used to learn the recipe:

```sh
python -m dotbox act REVISION open_panel --session /private/work/session/session.json --lease /private/work/saved.json
```

On a running agent-owned diagnostic guest, a mouse `act` establishes a bounded pause,
captures fresh frame IDs, checks dimensions and ownership, sends the absolute
click, and issues continue. This all happens in one service request without
model reasoning while paused. Inspect the returned coordination markers and a
new completed frame; queued input and a continue acknowledgment do not prove
the intended game effect. A refusal or partial failure is not permission to retry
or resume blindly. Keep the actual stopped/unknown state visible and observe it
before choosing recovery. The primitive `click` interface remains available for
diagnosis with explicit frame/mode IDs.
