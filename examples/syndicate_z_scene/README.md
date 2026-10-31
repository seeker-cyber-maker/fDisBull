# Syndicate spatial Z research example

This example contains authored tooling/tests and sanitized receipts, not original
game assets, runtime snapshots or a prepackaged playable game. It was exercised
with fDisBull and fDisBull Player 0.26.0. See the companion
`docs/SYNDICATE_SPATIAL_Z_SCENE_2026-10-31.md` for results and remaining obligations.
Current-main compatibility is not asserted while GitHub is inaccessible.

From this example directory:

```sh
python -m unittest discover -s tests -v
```

Tests use an authored synthetic GAME-shaped fixture in memory and require the
installed `fdisbull_player` for the public projection checks. They require no
original file or native runtime. The separately reported native results are
not reproduced by these tests.

For a private, source-qualified observation JSON, use the unmodified player:

```sh
python -m fdisbull_player --backend-command "python tools/z_provider.py --snapshot /absolute/private-observation.json"
```

Snapshot mode is read-only. `Mission(raw_game_bytes).summary()` constructs such
an observation from a coherent private GAME snapshot. Do not substitute an
initial file for current runtime state. Live mode requires an owned paused
mission-1 DOSBox session, a verified object mapping, and the matching privately
decoded MAP01/COL01 resources. The controller and binder show that explicit
research path. They are not a new core API or automatic mission loader.

Native bindings must be regenerated after process/load changes. Diagnostic
teleporting is limited to the observed on-foot team state and named waypoints.
A held/partial result is not replayed; an operator must inspect or explicitly
restore the matching native checkpoint. Automatic Z live checkpoint certificates
are unsupported. Decoded terrain gives conditional paths, not actual collision,
visibility, boarding, stair or door-transition proofs.

To render an independently supplied semantic snapshot and matching private
resources, use `tools/build_map.py` then `tools/render_static_map.py`. Their output
is a semantic derivative; publish it only after a separate content review.
All original files, checkpoint bytes, database payloads and raw controller logs
must remain outside Git and tool distributions.


## ASCII/precision follow-up (local only)

`tools/agent_map.py` adds a standard-library ASCII projection over caller-supplied
semantic terrain and snapshots, candidate approach routes and a decision-only
progress watchdog. `z_provider.py` uses the view and suppresses duplicate exact
teleports. It does not dispatch walking or execute generated routes.
The added36 authored tests run without original files; player integration tests
require the existing `fdisbull_player`. See `ASCII_PRECISION_AND_ROUTING.md` for
the separate local data delivery and exact evidence limits.
