# Bounded Sarien scene primitives

`sarien_scene.c` adapts two cohesive pieces of original Sarien: AGI 2.x
position resolution and the priority-aware single-pixel raster rule. It is a
separate, reentrant C99 module. It does not complete pending QEMU instructions,
import native state, manage sprites, execute motion ticks, or present pixels.

## Source and permission

Upstream repository: [cmatsuoka/sarien](https://github.com/cmatsuoka/sarien).
Exact commit: [`aaef5e667757385b5b3650cc1f7365908720f7e6`](https://github.com/cmatsuoka/sarien/commit/aaef5e667757385b5b3650cc1f7365908720f7e6).
Modified for fDisBull on 2026-11-21.

| Upstream file | Git blob SHA | Material adapted |
| --- | --- | --- |
| [src/checks.c](https://github.com/cmatsuoka/sarien/blob/aaef5e667757385b5b3650cc1f7365908720f7e6/src/checks.c) | `240f7b90336af79d6b4e00ce1df79c9cf7010c04` | `check_position`, `check_collision`, `check_priority`, `fix_position`; only the AGI 2.x positioning path. |
| [src/sprite.c](https://github.com/cmatsuoka/sarien/blob/aaef5e667757385b5b3650cc1f7365908720f7e6/src/sprite.c) | `3553a2145d8542297c89897660a79b3b01f6523f` | `blit_pixel` effective-priority comparison and control-line preservation. |
| [doc/COPYING](https://github.com/cmatsuoka/sarien/blob/aaef5e667757385b5b3650cc1f7365908720f7e6/doc/COPYING) | `a43ea2126fb6b114bff5f8e003ee118e045dacf1` | Supplied GNU GPL version 2, copied to `COPYING.sarien.txt`. |

The upstream files credit Stuart George and Claudio Matsuoka: 1999–2001 for
`checks.c`, and 1999–2003 for `sprite.c`. Their notices grant redistribution
and modification under the GNU General Public License without a version
number and refer to `docs/COPYING`; the actual repository path is
`doc/COPYING`. The original grant is retained in `sarien_scene.c`.

This adaptation elects **GPL version 2**, under the reviewed notice and the
version-selection terms of section 9 of the supplied license. The adaptation
is marked `GPL-2.0-only`; the original upstream grant is not rewritten.
Preserve attribution, the license text and the dated modification notice.
Distribution remains subject to the license's applicable source and notice
requirements. No GPLv3 ScummVM source is included in this adaptation.

## Stable ABI 1

`sarien_scene.h` declares fixed-width integer structures and these functions:

- `agi_scene_abi_version()` returns `1`.
- `agi_scene_place(...)` returns status `0` for success, `1` for exhausted
  budget, or `2` for invalid input.
- `agi_scene_blit(...)` returns `0` for success or `2` for invalid input.

The module includes only `<stdint.h>` and `<stddef.h>`, has no mutable global
state, and performs no allocation or I/O. Calls with disjoint outputs can run
independently. Callers must supply valid, accessible C objects. Output/input
overlap is rejected; blitting additionally rejects overlap between either
plane and the cel or the other plane.

## Placement semantics

The context supplies a complete 160×168 indexed priority/control plane,
168 explicit priority-band values, a horizon, one to sixteen actors and a
target ID. Actor flags are explicitly mapped in the header; they are not
Sarien's original packed flag values. IDs must be unique in 0–255. All
coordinates and previous coordinates must initially fit -32768–32767.
The target and animated-and-drawn peers require positive dimensions within
160×168. Each dimension of an inactive peer may be zero.

Placement preserves these selected upstream rules:

- Horizon adjustment occurs before the first candidate evaluation unless
  the target ignores the horizon. Position validity includes all canvas
  boundaries and the complete cel height.
- Collision considers animated-and-drawn peers, skips the same ID, and
  respects ignore-objects on either participant. Horizontal endpoint
  comparisons are inclusive, including `target.x + target.width == peer.x`.
  Same-baseline and strict previous/current baseline-crossing tests remain.
- Nonfixed priority is read from the supplied band at the candidate baseline.
  Priority 15 bypasses baseline controls and yields false ego-water and
  ego-trigger results. Controls 0, 1, 2 and 3 retain their blocking, conditional
  blocking, trigger and water behavior. Water/land restrictions use the full
  baseline result.
- The repair order is the upstream expanding west, south, east, north spiral.
  Each evaluated candidate consumes one attempt, including the initial
  candidate after horizon adjustment. Allowed budgets are 1–1,048,576.

All candidates are local copies. Successful output reports the resolved
pose, priority and attempts. Ego-trigger and ego-water values are meaningful
for target ID 0; zero values for another target do not request global ego
flag changes. Exhaustion reports the **original** x, y and priority,
attempts used, and uninterpreted zero ego flags. No actor or input plane is
modified. Ordinary invalid input writes status 2 and zero other fields;
null output, output/input overlap, or an unrepresentable actor byte span
returns 2 without writing output.

### Explicit priority bands

The kernel has no implicit default bands. If a host deliberately wants the
upstream initial band recipe, [src/agi.c `init_pri_table`](https://github.com/cmatsuoka/sarien/blob/aaef5e667757385b5b3650cc1f7365908720f7e6/src/agi.c#L28-L37)
(Git blob `79e770085354e9ff9e61a24152fe7101514a4cd3`) initializes twelve rows
for each `p` from 1 through 14, storing `max(4, p)`. Equivalently,
`bands[y] = max(4, y / 12 + 1)` with integer division for `0 <= y < 168`.
Rows 0–47 are priority 4, rows 48–59 are 5, and rows 156–167 are 14.
Using this recipe is an explicit host assumption, not recovered room state.

## Raster semantics

Blitting consumes an already decoded and oriented cel, explicit dimensions,
transparency, actor priority and lower-left baseline position. The complete
cel rectangle must fit the canvas. Both planes and the cel are checked in
full for indices 0–15 before any plane mutation. Invalid input leaves both
planes and the output structure unchanged.

For each nontransparent pixel, priority/control values below 3 cause a
downward scan in the same column for effective priority; reaching the bottom
without a normal value uses 4. A pixel passes when actor priority is at least
the effective priority. Passing pixels update visual color. Existing control
values below 3 are retained; water and other priorities are replaced by actor
priority. `written_pixels` counts admitted nontransparent pixels, including
ones whose visual color already matched. `hidden` is 1 exactly when no pixel
was admitted. These are bounded raster facts, not presentation or whole-scene
visibility claims.

## Deliberate adaptations and excluded behavior

- Explicit validated arguments replace Sarien's global `game` context.
- A finite attempt budget replaces the unbounded repair loop. Candidate
  arithmetic uses 32-bit values; the input bounds and maximum budget keep it
  within range. Rejected and exhausted searches do not leak partial state.
- Separate visual and priority arrays replace the original packed nibbles.
- A bounded row-major decoded-cel traversal replaces RLE and mirror handling;
  the upstream `blit_cel` decoder, clipping and high-resolution path are not
  imported. The caller must not mirror pre-oriented cel pixels again.
- Fully in-bounds blit admission is explicit; there is no clipping or position
  repair inside the blit function.
- No engine, allocation pool, linked list, sprite save/restore, draw/erase
  lifecycle, resource loader, display callback, presentation state, AGI 3.x
  workaround, or debug-control behavior is imported.

This source provenance does not establish original-interpreter parity.
Runtime and integration qualification belong to the host's independent
tests and receipts. The implementation author performed source inspection
only and did not compile, execute tests, or modify the QEMU overlay.
