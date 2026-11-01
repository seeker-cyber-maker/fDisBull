# Conversion experiment boundaries

This is the authored original and its oracle. An exported source description,
an imported executable, or a renamed function is not a recovered UIL or an
executed UDC backing. Conversion remains a separate experiment.

## Slice to recover first

Recover a complete input -> one step -> draw interaction, then repeat it across
shells. Public LINK-map entries separate `SNAKE_STEP`, `RESET_GAME`,
`POLL_INPUT`, `POLL_MOUSE`, `RENDER_FRAME` and `MAIN_LOOP`. The public state is
initialized and present in the file-backed data segment. The source map and
raw raster witnesses belong to the oracle lane.

The game step takes no OS service and mutates an explicit state record. It
preserves general registers and DS/ES/SS, with a balanced near-call stack;
arithmetic flags are not a result contract. Its state domain requires unique,
adjacent occupied cells, length 1..600, directions 0..3 and a free food cell
while active. A future adapter must validate or establish those assumptions.

Shell responsibilities are explicit:

| Service | Original DOS implementation | Replacement boundary |
| --- | --- | --- |
| Keyboard | BIOS INT 16h events | Normalize to direction/pause/step/reset/quit actions |
| Pointer | INT 33h position/buttons, rising left edge | Normalize pixel coordinates and press edges |
| Clock | Low BIOS tick word, one step per four ticks while running | Supply monotonic tick events; no catch-up batch |
| Drawing | Indexed A000 framebuffer plus BIOS text | Fill rectangles, draw text, present a complete frame |
| Cursor | Mouse-driver hide/show around redraw | Host cursor ownership, excluded from core raster comparisons |
| Lifetime | VGA initialization; mode 3 before DOS exit | Create/destroy window or canvas and input subscriptions |

## Geometry and state

Framebuffer: 320x200 indexed pixels. Board: 30x20 cells, origin (8,24), pitch 8;
each cell is a 7x7 interior with one-pixel gutters. Index = y*30+x.
Border (6,22) spans 244x164. Palette indices: background 0, border 8, body 2,
head 10, food 12, controls 1, text 15. Font/cursor/palette/viewport differences
must be compared at a declared projection boundary; equal core state is not
automatically equal rendered pixels.

Mouse button rectangles use inclusive bounds:

| Action | x | y |
| --- | --- | --- |
| Up | 280..303 | 40..59 |
| Left | 256..279 | 64..83 |
| Right | 288..311 | 64..83 |
| Down | 280..303 | 88..107 |
| Pause | 256..311 | 120..139 |
| Step | 256..311 | 144..163 |
| Reset | 256..311 | 168..187 |

The original starts paused, permitting exactly controlled N/STEP input.
Queue at most one perpendicular direction change per game tick; reject direct
reversal and ignore additional queued turns. Ordinary automatic play remains
available. Reset repeats the fixed initial state and RNG seed.

## Acceptance of a converted variant

1. Bind original, model, selected layers, generated artifact and shell hashes.
2. Compare all 17 original-machine-code step cases before testing presentation.
3. Replay keyboard and pointer sequences against committed state and a saved
   raster, including direction admission, growth, collision, restart and exit.
4. Keep one owner of mutable game state. If computing a step asynchronously,
   snapshot inputs and reject stale results after edit/reset/close or layer swap.
   Do not release live GPU memory while physical work is pending.
5. Interchange backings within one carried-state sequence. Initialization from
   the expected answer before each call is not a carried-state test.
6. Separate logic parity, input dispatch, timing policy, drawing equivalence,
   resource cleanup and whole-game scope in the receipt.

Current scalar food backends do not by themselves supply a Snake converter for
array state, loops, rendering or input. This fixture makes those next gaps
small and observable; it does not declare them implemented.
