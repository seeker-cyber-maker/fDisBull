# Civ city screen: original-runtime observation

Status: **display-level runtime evidence from a real DOS install; one route, one
edition, no state-field binding yet.**

Method: `fdisbull-investigate` — authentic bounded keyboard input through the
DOSBox agent, display and action evidence kept separate, no direct state edits,
no pixel authority over the program's own dispatch.

## Identity

| Item | Value |
|---|---|
| Runtime edition | Civilization DOS **474.03** English install (`runtime/47403`) |
| `CIV.EXE` SHA-256 | `31e35b01f4d00df81685dfcb81e6de196a3876bd2afff6e39cbbfd964f5852ad` |
| Static-trace edition | `CIV.EXE` `22de2748…`, unpacked root `aa63aa39…` (**474.05**) |
| Edition relation | Explicit difference, not an equivalence claim |
| Client | branch source `1ed842a`, fDisBull 0.26.0 on `PYTHONPATH` |
| Interpreter | `/Users/Shared/fDisBull/releases/0.27.0-90e748c/venv/bin/python` (3.13.17) |
| Backend | DOSBox-X headless agent, SHA-256 `bcf318de…`, video mode 5 (320x200) |
| Run | `62abe65c7361483ba0385b82e42c6acf` |

Receipt and frames: `docs/evidence/civ-city-runtime/`.

## Route

Cold boot, keyboard only, no mouse (the game's own "keyboard only" mode):

```text
1                 VGA (256 colour)
1                 no sound
2                 keyboard only
<Enter>           difficulty: Chieftain (default selection)
<Enter>           competition: 7 civilizations
<Enter>           tribe: Roman
<Enter>           leader name: Caesar
                  intro animation is fixed at 3463 ticks (~58 s); see below
b                 settler order opens "Your first task" note
<Enter> b         dismiss note, order again
<Enter>           city name: Rome
<Enter>           dismiss production note -> city screen
```

The intro cannot be skipped; budget roughly two minutes of guest time per cold
boot. The city screen appears only after the production note is dismissed.

## Intro timing (reversed from the code)

The cold-boot delay is not a guess; it is fixed by `INTRO.C` (`game_startup`,
lines 131-256) and the sound driver, and it was re-measured here:

- two 320-step scene loops, step *i* waiting for `sound_quiet_ticks() >= i*21/4`
  and then `>= (i+320)*21/4`, each breaking on `kbhit()`;
- after them, if no key was consumed, `while (sound_quiet_ticks() < 3463);`;
- `quiet_ticks` is incremented in `ASOUND.ASM` `music_tick` ("the 60 Hz step"),
  so the self-running intro is `3463 / 60 ≈ 57.7 s` of guest time;
- keys queued during the intro do not skip it reliably: `kbhit()` must see them,
  while the final `switch (key_cmd())` maps only `N/L/E/C`; observed space and
  Esc presses left the animation running.

Observed confirmation: this run reached the difficulty menu after about 58 s of
guest time (47.9 s of earlier slices + 7.1 s of key slices + the first seconds of
a 30 s slice), matching the code-derived value.

Consequence for harnesses: wait ~65 s of guest time once for the intro, then
drive the menus; do not burn attempts on key-skip timing.

## Captures

All frames are 320x200 mode 5, captured from the visible framebuffer and stored
in the run's artifact table before export.

| Frame | Key | Changed pixels vs baseline | Ratio | Bounding box |
|---|---|---|---|---|
| `city-04-screen.png` | — | baseline | — | — |
| `city-05-happy.png` | `h` | 876 | 1.37 % | `(96,65)-(222,146)` |
| `city-06-map.png` | `m` | 9,449 | 14.76 % | `(96,65)-(221,192)` |
| `city-07-view.png` | `v` | 63,973 | 99.96 % | full frame |
| `city-08-back.png` | dismiss | 5 | 0.008 % | `(96,65)-(222,146)` |
| `city-09-units.png` | `a` | 256 | 0.40 % | `(100,65)-(183,131)` |

## What the frames establish

- The city screen presents the groups the partial fixture inventories: title
  (`ROME (POP:1)`), `CITY RESOURCES`, the 21-tile map panel, `FOOD STORAGE`,
  the `INFO` / `HAPPY` / `MAP` / `VIEW` tabs, `CHANGE` / `BUY`, `RENAME` /
  `EXIT`, and the production panel.
- `h` and `m` change only the tab content area, consistent with view modes `1`
  and `2` recovered from the static dispatch (`0A99:76DA`, `0A99:76ED`).
- `v` replaces the whole frame with the animated city view, consistent with the
  `int 3F` overlay entry `0x0013` recovered at `0A99:7700`/`7756`.
- Dismissing the overlay returns to a frame that differs from the baseline by
  5 pixels, so the overlay exit restores the INFO presentation.
- `a` with an empty city produced no unit-cursor panel; only the INFO content
  icon redraw changed. The unit-list handler was **not** exercised.
- `c` opens the production chooser only when the city screen is settled. Earlier
  attempts failed while the founding note or banner was up. With the screen
  active, `c` displayed `What shall we build in Rome?` with Settlers (40
  turns) … Hanging Gardens (300 turns); `down` + `Enter` moved the highlight
  to Militia and accepted it.
- Production is now bound to the city record: with `DS=0x32A4`, the record at
  `DS:0x70EC` read `production=0` after the first item and `production=1`
  after the Militia selection. This matches `find_slot` returning
  `cand[show_menu(...) + 1]`.
- The `A` auto-build toggle and the `a` unit-list cursor still lack a runtime
  exercise; the scene models them from the source and dispatch only.

## Debugger scene overlay

The city screen is also a `fdisbull-scene-1` overlay bound to the debugger's own
captures. The definition builder is `examples/civ/civ_city_overlay.py`; the
scene lives in the private run project, not in Git.

- Revision `731dea45…`: city-screen match (three stable pixels across INFO,
  HAPPY and MAP), `tab-happy`, `tab-map`, `change`; overlay exported with
  numbered markers.
- Revision `3529f038…` (child): adds `tab-city-view`.
- Revision `97950c30…` (child): `change` outcome re-measured from the live
  chooser frame and both live frames attached as evidence; reference replaced by
  the live city frame.
- Revision `c961e693…` (child): `change` outcome accepts two of three popup
  border pixels because the chooser list length varies with available items.
- Revision `a2785955…` (child): object ids renamed to the Z scene catalog
  (`tab-happiness`, `production-change`, …); the builder now refuses any
  overlay object whose id is absent from `examples/civ/civ_city_scene.json`.
- Revision `902d1329…` (child): adds `exit` (escape), whose outcome is the
  city match failing. Run `c778c405…` reported `matched`, but its frame
  (`f2d40dea…`) is the **blank transition frame**, so that predicate never
  proved the destination.
- Revision `3e9e4034…` (child): `exit` outcome requires both the city match
  failing and the map panel's cyan resource bar. Run `4f362301…` matched with
  the map view drawn (artifact `88d50321…`, no message box).

Live verification (run `a2420e60…`, 474.03 install, keyboard-only):

| Operation | Result |
|---|---|
| `assert_current()` on the city screen | `matched` |
| `act('tab-happiness')` | `matched`; the HAPPY content pixel changed as recorded |
| `act('tab-map')` | `matched`; the MAP content pixel changed as recorded |
| `act('production-change')` | `matched`; pressing `c` opened the production chooser |
| `act('exit')` | `matched`; escape left the city screen and the map panel was drawn (run `4f362301…`, artifact `88d50321…`) |

A first `exit` predicate that only required the city match to fail reported
`matched` on the blank transition frame (`c778c405…`, artifact `f2d40dea…`).
The destination marker fixed it: a screen transition needs a positive sample of
the destination, not just the absence of the source.

An earlier run on the pre-rename ids (`1dfc9a55…`) matched the same operations, so the rename is behaviour-neutral. The two failed attempts (`bcea8bf2…`, `b51825af…`) are kept: the scene asserted
and both tab acts passed, but `change` timed out because its outcome pixel had
been authored from an older chooser frame whose list was shorter. That is the
normal authoring loop: the live frame corrects the recorded predicate.

The overlay names controls with the Z scene's ids and validates them against
`examples/civ/civ_city_scene.json`, so the IL scene and the debugger overlay
project one control catalog; `catalog_ids()` is the check.

Adding elements uses append-only child revisions: `debug_save_scene(name,
definition, parent=current_revision)` keeps object identity by name, binds
per-object evidence to run artifacts, and retains the older revisions for
review (`debug_scene_info`, `debug_scene_overlay`, `debug_scene_observations`).
The whole object list is resent in each revision, and the scene's `match` must
hold before an action, so controls that only exist inside a popup belong to a
handler or a separate scene. Debug scenes and Z IL scenes are separate formats;
there is no automatic sync between them.

## Z route (no debugger)

The same recovered transitions are executable as a shared-IL scene, so scene work
does not need the DOS UI:

```bash
PYTHONPATH=src:player python -m fdisbull_player \
  --backend-command "python -m fdisbull.il_scenes examples/civ/civ_city_scene.json"
```

`activate change` opens the `production-chooser` context (Settlers/Militia), the
matching `build` action commits `$production` 0/1 and closes the chooser,
`open units` enters the `unit-list` context, and `next`/`previous`/`select`/
`exit` reproduce the recovered cursor bounds and `[0x70DC]` store as
`$city_cursor`. The scene is partial and marks the unit list as source-modelled,
not runtime-exercised.

## Limits

- Runtime edition 474.03, static trace 474.05; cross-edition equivalence is not
  established and the edition conflict row stays open.
- Display deltas are measured against one baseline frame. Animation and palette
  timing are not excluded; the 5-pixel return delta is within that noise.
- Guest state was read only for `townbuf[0].production`; the tab and overlay
  claims remain display-level and are not treated as semantic state.
- One route is not a deterministic replay or general readiness claim.
- The private game copy, project database and screenshots outside
  `docs/evidence/civ-city-runtime/` are not part of this repository.

## Next probes

1. Produce a unit (Militia selected; end turns) and exercise `a` with a
   non-empty unit list.
2. Read `shield_box` and `status` before and after the buy and sell paths.
3. Re-run the same route on the 474.05 executable over a complete data set to
   close the edition gap.
