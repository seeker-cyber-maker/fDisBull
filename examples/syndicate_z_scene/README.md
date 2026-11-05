# Syndicate mission 1: original-backed spatial Z scene

This repository import contains the cumulative F002 tactical/history source and
the separate [D007 data-only restoration study](../../research/syndicate-rewind/2026-11-02/README.md).
The study has no native guest adapter. Current source-free verification and
historical original-game observations are separate qualifications.

The historical door/vehicle follow-up used fDisBull and fDisBull Player **0.29.0**. Earlier scene evidence used **0.26.0**. It is not a
replacement game, a complete mission solver, or a production plugin installation.
Original assets, native snapshots, screenshots of the
game, memory images and FDBs are excluded.

## Durable history and recorded damage

[HISTORY.md](HISTORY.md) describes the append-only semantic journal, bounded
summaries, notice queries and passive Player endpoint. Recorded damage attribution
is an opt-in observation view; it does not install an always-on live monitor.
The [integration contract](../../docs/WORLD_HISTORY_DAMAGE_CONTRACT.md) describes
the remaining watch ownership, live-action and perception requirements.

Historical findings and full handoff evidence remain in the original reports:

- [Doors and vehicles](https://chatgpt.com/library?file_id=libfile_c143c9db8ea08191ab6c2c5defc04630&account_id=personal).
- [Bounded original walking](https://chatgpt.com/library?file_id=libfile_586e2ac154f881918aa903ddd94ee97c&account_id=personal).
- [Damage attribution](https://chatgpt.com/library?file_id=libfile_d0a3b03d35a081918f473f5af63f0edb&account_id=personal).
- [World history and damage](https://chatgpt.com/library?file_id=libfile_07414ad9ef808191842d0650969bb02b&account_id=personal).

## Current: original walking (D004, 1 November 2026)

Read [NAVIGATION.md](NAVIGATION.md) for the opt-in `walk route to car` profile.
It uses the shared exact-coordinate plan and original order production with
bounded progress observation, no actor-position writes and no action replay.
Conditional gates are still refused. A partially completed long route stopped
on a health change; short car-approach walks succeeded for two tested team slots.
Neither outcome is a whole-map clearance or hazard-safety certificate.

## Door and vehicle follow-up (D003 history, 1 November 2026)

Read [DOORS_AND_VEHICLES.md](DOORS_AND_VEHICLES.md) first for the current native
interaction profile. Door states remain one door identity across opening/closing.
Vehicle occupancy is resolved through its separate predecessor/next chain.
Opt-in `board car`, `exit car` and `leave car` requests use original game code
after declared diagnostic input preparations. D003 did not expose walking as a general Z command. D004 adds the bounded
opt-in profile above and a second corridor witness, not unrestricted navigation.

## ASCII and precision follow-up (historical 31 October stage)

Read [ASCII_PRECISION_AND_ROUTING.md](ASCII_PRECISION_AND_ROUTING.md) for exact
coordinates, candidate approaches, bounded progress checks and the GitLab audit.
The full F002 handoff's `scene/public/mission-ascii.txt` and
`scene/public/team-subtile-ascii.txt` are the recorded agent views. Those semantic
exports and original graphical documentation are not copied into this source import.
Try `examine map`, `examine route to car`, and `examine path to mission target`.
This follow-up did not run a native guest or implement walking.

## Open the map and inspect the recorded scene

Use the semantic map and snapshot from the
[complete F002 handoff](https://chatgpt.com/library?file_id=libfile_b995297031a48191b85edf8470091000&account_id=personal).
Its `scene/public/mission-map.html` is self-contained. The JSON files are semantic
derivatives, not original tile art or binaries. Earlier semantic map exports are
already accounted for in Library intake MR !42; this import does not duplicate them.

With fDisBull Player installed, run from this example directory using explicit
paths to the handoff's semantic files:

```sh
python -m fdisbull_player --backend-command "python tools/z_provider.py --snapshot /private/F002/scene/public/mission-1-observation.json --map-model /private/F002/scene/public/map-model.json"
```

Try `look`, `examine team`, `examine civilians`, `examine police`,
`examine nearest car`, `examine car gate`, `examine mission target`,
`examine objectives`, and `inventory`. This recorded snapshot is read-only.
Teleport commands are deliberately unavailable without a live original game.

## Connect the live adapter

Live use requires the selected original MAIN and its resources, an installed
compatible fDisBull/DOSBox backend, and an owned paused mission session.
Do not reuse a numerical load address or a checkpoint from another generation.

The controller source is supplied as a portable, argument-driven form of the
single-owner controller used in the investigation:

```sh
python tools/session_controller.py --root /absolute/new-private-session \
  --game-dir /absolute/SYNDICAT --dosbox /absolute/path/to/dosbox
```

This starts the original MZ bootstrap. Reaching mission 1 is a separate setup
step: the earlier run used keyboard input and two guarded diagnostic menu-click
latches because the high-level mouse API refused the protected-mode boundary.
The delivered controller is not an automatic UI-route player. The setup ledger
and distinction from ordinary mouse input are in the historical reports linked above.

Once MAIN is paused in mission 1, nominate its **observed** code-object base and
verify it. The value below is an example from this run, not a universal address:

```sh
python tools/bind_scene.py --controller-root /absolute/new-private-session \
  --main /absolute/SYNDICAT/MAIN.EXE --code-base 0x1c4030 \
  --output /absolute/new-private-session/scene-binding.json
```

The binder derives all four runtime object bases from code-side fixups, compares
the executable object with its qualified mutable data exceptions, checks the
mission's spatial lists, and writes a private session-bound configuration. It
refuses a wrong source, inconsistent mapping, unexpected mutation or changed
observation revision. It does not silently search/fix another binary.

The live scene also needs the privately decoded `MAP01.DAT` and `COL01.DAT`:

```sh
python -m fdisbull_player --backend-command "python tools/z_provider.py --live-config /absolute/new-private-session/scene-binding.json --decoded-data /absolute/decoded/SYNDICAT/DATA"
```

Live-only commands are `focus team agent 2`, `advance world`, and `teleport`
followed by one of: `car approach`, `mission target approach`, `guard approach`,
`door approach`, `roof probe`, or `start position`. Focus changes the observer,
not the original UI selection. An explicitly enabled vehicle action separately
prepares native selection and records it as assistance. Teleport updates the recorded agent's spatial
membership and coordinates, then lets original updates settle owned items.

Only the observed on-foot team raw-state profile is admitted. A rider, pending
movement target, unsupported state, bad graph, stale context or unqualified
terrain waypoint is refused. An uncertain partial write holds the provider;
it is not retried. Explicitly inspect/restore the owned native checkpoint.

The controller accepts newline-delimited JSON over its local UNIX socket.
`{"op":"close"}` closes the owned debugger and emulator. Original input files
and every output containing bytes must remain outside Git. Checkpoint operations
are not exposed as replay-safe Z `--live` certificates; use ordinary player mode.
The native low-level `state.save/load` path was separately tested in the same
session, including register and full GAME-memory equality.

## Reproduce source-free checks

```sh
python -m unittest discover -s tests -v
```

The cumulative F002 source has 240 authored tests. The Player projection checks
require the genuine `fdisbull_player` package; the model operations use the Python
standard library. D003 and D004 historically reported 103 and 140 cases respectively.
They do not reproduce the separately recorded original-DOSBox acceptance.

To regenerate the terrain viewer from your private decoded resources:

```sh
python tools/build_map.py /absolute/decoded/SYNDICAT/DATA \
  public/mission-1-observation.json /absolute/new-map-output
python tools/render_static_map.py /absolute/new-map-output
```

The SVG renderer uses only the standard library; the optional PNG was rendered
with CairoSVG. The HTML has no external dependencies. Current live process
state is not included in this delivery, and the investigation's guest is closed.
