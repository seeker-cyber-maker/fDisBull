# Native AGI actor execution

`overlay/target/agi/runtime_actor.c` and `runtime_actor.h` implement portable
native actor/world state and deterministic actor phases. The module is used
by the AGI CPU runtime; it does not depend on QEMU, a display, wall-clock
time, global state, or proprietary game assets. Modified for fDisBull on
2026-11-22.

## Immutable source and permission

The cohesive execution algorithms are adapted from
[cmatsuoka/sarien at aaef5e667757385b5b3650cc1f7365908720f7e6](https://github.com/cmatsuoka/sarien/tree/aaef5e667757385b5b3650cc1f7365908720f7e6).
The checkout and the following Git blob identities were verified locally.

| Donor path | Git blob | Adapted behavior |
| --- | --- | --- |
| `src/op_cmd.c` | `c106da38e26975a80965bd1a26a8f80952b29d89` | Actor actions 33–91 and 147/148, argument indirection, flags, motion and cycle setup, getters. |
| `src/view.c` | `bb9ed18abe83dee982c288dc18b0f65f0625ca4a` | View/loop/cel binding, loop choice from direction, cycle counters, forward/reverse and completion behavior. |
| `src/motion.c` | `4226474c8eef74cfe0b98206b7d0e2b1146c05c8` | Direction selection, move destination, follow/wander, strict block-rectangle crossing. |
| `src/checks.c` | `240f7b90336af79d6b4e00ce1df79c9cf7010c04` | Position validation, actor collision, priority/control evaluation, borders, expanding repair spiral. |
| `src/sprite.c` | `3553a2145d8542297c89897660a79b3b01f6523f` | Remembered pose/geometry and `DIDNT_MOVE` bookkeeping from `commit_sprites`; no renderer or allocation pool. |
| `src/cycle.c` | `6eaf1094a53c26d3c6aade2cf6b173c6507256a2` | Ego/v6 synchronization, separation of motion preparation and post-LOGIC actor updates; room-style actor timing defaults. |
| `src/agi.c` | `79e770085354e9ff9e61a24152fe7101514a4cd3` | Initial priority bands: `max(4, y / 12 + 1)`. |
| `doc/COPYING` | `a43ea2126fb6b114bff5f8e003ee118e045dacf1` | Existing retained `COPYING.sarien.txt`, GNU GPL version 2. |

The upstream files credit Stuart George and Claudio Matsuoka, 1999–2003
(some files end their range at 2001). Their unversioned GNU GPL grant and
reference to `docs/COPYING` are retained in the C file. The actual upstream
license path is `doc/COPYING`. As in the previously reviewed scene adapter,
this adaptation elects GPL version 2 under section 9 of that supplied
license and is marked `GPL-2.0-only`. Preserve the copyright, original grant,
dated modification notice, this provenance and `COPYING.sarien.txt` when
distributing this module. No ScummVM source is included.

## Ownership and interface

`AgiRuntimeWorld` contains 256 actors, explicit loaded-VIEW membership,
priority bands, horizon, block rectangle, player-control state, RNG state,
and an exact logical-tick counter. All architectural fields have fixed-width
integer types; no resource or callback pointers enter snapshots.

The parent owns resource loading/discard, LOGIC execution, variables and
flags, inventory, picture decoding, composition, host effects and input.
The actor module handles actions 33–91 and 147/148. Actions 30–32 and
92 onward (apart from 147/148) return `AGI_RA_UNHANDLED`, allowing the parent
to dispatch its own semantics. `force.update` (60) performs remembered-pose
bookkeeping for drawn actors; the parent must also emit the renderer refresh
effect even if actor bytes do not change. Draw/erase changes native drawn
membership; it does not claim that any host has presented pixels.

The immutable geometry callback supplies loop/cel counts and cel dimensions.
Its response must describe an existing VIEW even if a requested loop or cel
is out of range, with unavailable nested fields zero. Missing or unloaded
views, unbound actors, invalid selections, empty loops, and invalid
dimensions have distinct results. A view change may fall back to loop zero;
a view or loop change may fall back to cel zero. Explicit invalid loop/cel
commands fault rather than indexing outside a resource.

Draw, repaired positioning and active actor updates consume a supplied
complete 160×168 priority/control plane, with one value in 0–15 per pixel.
The plane is read-only and is never silently synthesized. Actor priority 15
bypasses baseline control rules. Controls 0, 1, 2 and 3 keep the donor's
unconditional obstruction, conditional obstruction, trigger, and water
semantics. Ego-water and ego-trigger are flags 0 and 3. The parent supplies
the background priority/control plane, not a plane destructively overwritten
by presentation of moving sprites.

## Interpreter phase ordering

An authentic interpreter cycle invokes:

1. `agi_runtime_actor_prepare`: synchronize ego direction/v6 according to
   player control, select motion for active actors whose step counter is
   one, and apply block-boundary crossing.
2. Parent LOGIC 0 execution, including its calls and asynchronous waits.
3. `agi_runtime_actor_finish`: apply LOGIC's v6 to ego, select directional
   loops, advance cycle counters, update positions and completion/border
   flags, commit remembered positions, and increment `world.ticks` once.

The parent owns its cycle-active guard and must not prepare twice or mix an
explicit world tick with a prepared unfinished interpreter cycle.
`agi_runtime_actor_tick(n)` composes prepare and finish exactly once per tick
without executing LOGIC. It accepts at most 4096 ticks per call and uses one
transaction for the entire batch. Each individual prepare or finish call
is also atomic. Preparation does not increment the tick counter.

## Preserved behavior and deliberate bounds

- Geometry binding preserves the existing native CPU's qualified nominal
  DOS 2.917 distinction: horizon repair is nested inside top-edge repair.
  A valid top edge with a baseline above the horizon remains unchanged by
  binding. General drawing/placement and motion enforce the horizon
  separately. Binding leaves remembered coordinates unchanged.
- Animated, updating and drawn membership jointly gate actor ticks. Cycle
  and step counters retain their distinct zero behavior: a zero cycle
  counter does not cycle, while a zero step counter admits position updates.
- Automatic loop choice uses the donor's 2/3-loop and 4-loop direction
  tables and the 2.917 step-counter gate. Fixed-loop prevents this selection.
  End/reverse-loop completion includes the initial `DONTUPDATE` skip;
  explicit `set.cel` cancels that skip.
- Motion keeps the donor's direction threshold, saved step restoration,
  flag completion, ego control ownership and border completion. Follow and
  wander retain byte-wrapping counters and the donor's obstacle recovery.
  A step size of zero moves no pixels; no synthetic progress is invented.
- Collision includes touching horizontal endpoints and strict crossings of
  current versus remembered baselines. Ignore-objects on either actor
  disables their collision. Repair retains west, south, east, north spiral
  order. The search is bounded by a square enclosing every possible picture
  position; impossible placement returns `AGI_RA_NO_POSITION` atomically.
- The callback RNG receives only a private transaction's RNG state and an
  exclusive upper bound. It must return a value in that range and must not
  mutate hidden host state. A missing callback, out-of-range result, or
  1024 unsuccessful rejection draws faults without committing RNG state.
- Public state must originate from initialization/commands or a validated
  snapshot. Byte-derived fields, 0–8 directions, 0–15 priorities, in-canvas
  positive bound geometry, and coordinate snapshots in −512…512 are
  checked before arithmetic/indexing. Geometry itself is limited to
  160×168. The coordinate envelope includes every command-generated pose.
- Variables, flags and world are writable disjoint accessible C objects;
  callbacks and their immutable inputs must remain valid through each
  call. Negative results leave world, variables and flags unchanged.

AGI 3.x version workarounds, mouse-specific motion, sprite rasterization and
host timing are outside this actor module. This provenance and synthetic
coverage establish the stated native semantics, not parity with every
historical interpreter or completion of the parent CPU's other subsystems.

## Verification

`tests/test_qemu_agi_runtime_actor.py` compiles the production C source as a
portable shared library with C11, `-Wall -Wextra -Werror`, and invokes it via
ctypes. All resources and planes are authored synthetic data. The initial
25 passing cases cover the assigned actor actions, binding faults and
fallback, horizon distinctions, water/land/trigger controls, object
collisions, every cycle mode, movement and completion, deterministic
follow/wander, all four borders, preparation/LOGIC/finish ordering, and
whole-batch rollback when a later tick fails. No QEMU build or private game
assets are needed for this module's test command:

```sh
python -m pytest -q tests/test_qemu_agi_runtime_actor.py
```
