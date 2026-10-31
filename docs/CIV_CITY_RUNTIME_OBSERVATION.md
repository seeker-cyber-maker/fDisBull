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
                  intro animation runs ~2 min; space and Esc do not skip it
b                 settler order opens "Your first task" note
<Enter> b         dismiss note, order again
<Enter>           city name: Rome
<Enter>           dismiss production note -> city screen
```

The intro cannot be skipped; budget roughly two minutes of guest time per cold
boot. The city screen appears only after the production note is dismissed.

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
- `c` did not open a visible production chooser in three attempts in
  keyboard-only mode. The static call site (runtime `0x22009` → `1ADE:0421`)
  remains the only authority for that branch.

## Limits

- Runtime edition 474.03, static trace 474.05; cross-edition equivalence is not
  established and the edition conflict row stays open.
- Display deltas are measured against one baseline frame. Animation and palette
  timing are not excluded; the 5-pixel return delta is within that noise.
- No guest state field was read in this pass, so these are display observations
  only; the display is not treated as the program's semantic state.
- One route is not a deterministic replay or general readiness claim.
- The private game copy, project database and screenshots outside
  `docs/evidence/civ-city-runtime/` are not part of this repository.

## Next probes

1. Produce a unit (production chooser or turn advance) and exercise `a` with a
   non-empty unit list.
2. Retry `c` with the mouse enabled to test whether the chooser is
   mouse-dependent.
3. Read the city record fields (`shield_box`, `status`, `production`) at a
   breakpoint so display changes are bound to state, not pixels alone.
