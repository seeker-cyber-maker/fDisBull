# Experimental native VIEW binding profile

`agi-2917-view-binding-pilot-1` executes a bounded resource-dependent actor
binding slice. It records which VIEW, loop and cel a successful instruction
selected, the selected geometry, and the resulting actor coordinates. A host
can use those facts to choose the matching decoded cel without manually
assigning its pose. This profile does not establish that the actor was drawn
or visible, and does not execute a complete room or game engine.

## Selection and compatibility

Select the profile explicitly at machine startup:

```text
-M agi-test,view-catalog=/absolute/path/views.fdbagiv1
```

The machine reads one bounded regular file before execution and retains an
immutable parsed catalog. Changing that file later cannot change the admitted
metadata. The `view-catalog` machine property rejects writes after initialization;
restart clears executed loads and actor state while preserving the catalog.
There is no runtime catalog or actor-state injection operation.

| Startup selection | Profile | State schema | Events schema |
| --- | --- | --- | --- |
| No catalog property | `agi-2917-scalar-position-pilot-1` | `fdisbull-agi-native-state-1` | `fdisbull-agi-native-events-1` |
| Explicit accepted catalog | `agi-2917-view-binding-pilot-1` | `fdisbull-agi-binding-state-1` | `fdisbull-agi-binding-events-1` |

The scalar profile keeps its admitted instructions, guest JSON and event JSON.
Its SCENE position records still have kind `position` and four coordinate
fields. The binding profile uses distinct schema/profile identifiers and rich
actor records; a consumer must opt into it. It must not silently reinterpret
these records as a complete scene or feed them through the scalar schema.

## Immutable catalog format

All counts are unsigned. Only `view_count` is little-endian multi-byte data;
the resource digests are 32 raw bytes, not text. No alignment or padding is used.

| Field | Width | Admission |
| --- | --- | --- |
| Magic | 8 bytes | ASCII `FDBAGIV1` |
| Initial horizon | 1 byte | 0..167, explicitly supplied by the caller |
| Reserved | 1 byte | Zero |
| VIEW count | 2 bytes | 1..256 |
| Each VIEW's resource ID | 1 byte | Strictly increasing, no duplicates |
| Each VIEW's loop count | 1 byte | 1..255 |
| Each VIEW's resource SHA-256 | 32 bytes | Every byte sequence is admitted |
| Each loop's cel count | 1 byte | 0..255 |
| Each cel reference's width, height | 2 bytes | Width 1..160; height 1..168 |

Each VIEW header is immediately followed by its loops, and each loop count is
immediately followed by its cel dimension pairs. Counts are ordinal: mirrored
or aliased cel references still occupy their declared loop/cel positions.
The catalog contains metadata rather than image pixels or original resource
payloads. Aggregate limits are 65,536 file bytes, 1,024 loops, 4,096 cel
references, and 1,024 cel references per VIEW. Truncation, extra trailing bytes,
bad ordering, bad dimensions or exceeded budgets fail startup with
`AGI_VIEW_CATALOG`. Empty unselected loops are allowed; selecting one faults.

The native loader binds the SHA-256 of the exact admitted catalog bytes. A
resource digest records an identity claim; the native CPU cannot verify a
payload that it has not received. The host must validate resource bytes and
geometry before creating the catalog, then validate the same identities when
decoding the selected cel. Matching hashes do not establish publisher
authenticity, rights, or original-interpreter parity.

Catalog availability and executed `load.view` membership are separate.
Catalog entries begin unloaded, including VIEW 0. An explicit load instruction
must succeed before a binding instruction can use the entry.

## Reset state and admitted execution

There are 16 actor slots and 256 byte-valued variables/flags, as in the scalar
pilot. Reset clears all variables, flags, loads and actor fields. Actors begin
unbound with zero coordinates and zero view/loop/cel/dimensions; booleans are
false, motion/cycle are `normal`, and direction is zero. Horizon comes only
from the immutable catalog. This is an explicit experimental seed, not a claim
that an arbitrary original LOGIC segment begins with those values.

The existing scalar, flag, pure conditional, branch, return and position
instructions remain admitted. The following are the only additional commands:

| Opcodes | Command | Committed effect |
| --- | --- | --- |
| 30 / 31 | `load.view` / `load.view.v` | Require a catalog entry; mark its resource ID loaded. A duplicate load is a successful no-op. |
| 33 | `animate.obj` | On the first call set animated/update/cycling, clear ignore_horizon/update_pos, and reset motion/cycle/direction. An already animated actor is unchanged. |
| 41 / 42 | `set.view` / `set.view.v` | Require an available loaded VIEW; bind it, set view_replaced, preserve a valid loop/cel or reset that ordinal to zero, then apply geometry. |
| 43 / 44 | `set.loop` / `set.loop.v` | Require a bound loaded VIEW and an in-range nonempty requested loop; preserve a valid cel or reset it to zero, then apply geometry. |
| 47 / 48 | `set.cel` / `set.cel.v` | Require a bound loaded VIEW and an in-range requested cel, then apply geometry. |

`animate.obj` retains coordinates, binding, geometry and the separate
`view_replaced` field. Setting loop or cel retains `view_replaced`. Explicit
out-of-range loop/cel operands fault instead of invoking game-specific
workarounds or guessing a clamped selection. All failure checks occur on a
private candidate before committing architectural state.

Geometry selection uses these ordered rules:

1. Assign the selected cel's width and height.
2. If `x + width > 160`, set `x = 160 - width` and `update_pos = true`.
3. If `y + 1 < height`, set `y = height - 1` and `update_pos = true`. Only
   within this top-edge repair, if `y <= horizon` and ignore_horizon is false,
   set `y = horizon + 1`.

There is no independent horizon clamp and no bottom-edge clamp in this
selected rule. A valid top edge stays unchanged even if the baseline is at or
above the horizon. Existing update_pos remains set unless first animation
clears it. Geometry changes leave `prev_x` and `prev_y` unchanged.

Position 37/38 retains the scalar pilot's behavior: assign requested x/y and
the same values to prev_x/prev_y without clipping. `get.posn` 39 reads the
current coordinates, including changes caused by a prior binding command;
its established x-then-y assignment order remains when destination variables
alias. No ignore/observe-horizon command is admitted, so ignore_horizon stays
false in this slice.

The animation and resource-selection structure is supported by the pinned
ScummVM implementations of
[`cmdAnimateObj` and command operand handling](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_cmd.cpp)
and [`setView`, `setLoop`, `setCel`](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/view.cpp).
The horizon rule intentionally preserves this repository's separately
qualified nominal DOS 2.917 rule in
[`agi_effects.py`](https://github.com/seeker-cyber-maker/fDisBull/blob/92f4295398ba87109adcc147c4379c429d871fe2/src/fdisbull/agi_effects.py) and
[`test_agi_effects.py`](https://github.com/seeker-cyber-maker/fDisBull/blob/92f4295398ba87109adcc147c4379c429d871fe2/tests/test_agi_effects.py), rather than ScummVM's
independent horizon repair. This profile does not claim equivalence for
ScummVM workarounds, malformed original inputs, or a full original engine.

## State and observation records

Binding `source` contains the existing raw-code `sha256`, `size`, `logic_id: 0`
and the new `profile`, plus `catalog_sha256`. The raw-code identity includes
any explicitly authored prelude; its offsets and logic ID do not silently
become original resource addresses. Both state and event documents carry
that source object.

State additionally exposes a top-level `catalog` object with exactly:

```text
sha256, size, view_count, loop_count, cel_count, horizon
```

`guest` retains pc, variables, flags, actors, status, fault and retired. It adds
`horizon` and the sorted `loaded_views` array. Each actor contains these fields:

```text
id, x, y, prev_x, prev_y,
view_bound, view, loop, cel, width, height,
animated, update, cycling, ignore_horizon, update_pos, view_replaced,
motion, cycle, direction
```

The seven boolean fields are JSON booleans; motion/cycle are the string
`normal`; other fields are integer values. An unbound zero view ID is distinct
from bound VIEW 0. The complete actor shape includes supported flags that can
affect later admitted commands even when they do not immediately move an actor.

Observation controls retain the existing DISASM bit 1 and SCENE bit 2, finite
capacity, clear/restart epochs, control generations and per-channel drop
counters. Common event fields remain seq, kind, control_generation, pc,
opcode, bytes, next_pc and retired. Binding records add:

| Kind | Additional fields |
| --- | --- |
| `retire` | `resolved_value` for 30/31/41/42/43/44/47/48; `resolved_position: {x,y}` for 37/38 |
| `actor` | Actor ID plus complete `before`/`after` actor objects, omitting only `id` |
| `view_load` | Resource ID in `view`, with boolean `before` and `after` |

Resolved operands are copied into the event at retirement, including with
DISASM alone. Later variable overwrites cannot change historic operands.
SCENE records describe actual supported state changes; repeated loads,
repeated animation and otherwise identical bindings have no SCENE record.
New-profile position changes use `actor`, not the old `position` record.
When both channels are enabled, DISASM precedes the corresponding SCENE event.

Mask 0 TCG contains no `agi_observe` diagnostic helper and no diagnostic
before-state capture. Binding instructions still require `agi_binding`, their
semantic helper; this is not an observation helper. Observation helper_calls
counts only `agi_observe`. Selected profile and observation mask both
participate in the TB identity. Event storage is still bounded and reserved;
the no-observer claim is not a claim of zero memory or total runtime cost.

## Fault and reconstruction boundaries

Existing faults 1..7 are unchanged. Additional instruction faults are:

| Code | Name | Cause |
| --- | --- | --- |
| 8 | `missing_view` | Requested VIEW absent from the catalog |
| 9 | `view_not_loaded` | Binding requires a VIEW without an executed load |
| 10 | `view_unbound` | Loop/cel requested before an actor is bound |
| 11 | `invalid_loop` | Explicit loop operand outside the bound VIEW |
| 12 | `invalid_cel` | Explicit cel operand outside the selected loop |
| 13 | `empty_view_loop` | Binding would select a loop with no cels |

A fault sets the stopped fault state at the failing PC. It does not retire
the failed command, change variables/flags/actors/loads, or add observation
events. Invalid actors and truncated encodings use the existing faults.

Discard/unanimate, draw/erase, priority, collision, motion/cycle advancement,
picture operations, horizon commands and renderer state remain unsupported.
Reaching such an opcode is a boundary; its operand is not a committed effect.
Animated, bound and dimensioned does not mean drawn, unobscured or visible.
Pictures, priority maps, overlay order and presentation require separately
identified evidence and cannot be recovered from this actor-binding snapshot.
The scene designer may combine this bounded result with explicit external
inputs while preserving that distinction.

Independent acceptance should cover literal synthetic geometry, reset and
load preconditions, index fallback versus explicit index faults, conditional
top-edge/horizon behavior, atomic rejection, first/repeated animation,
historical resolved operands, malformed catalogs, dropped observations,
restart and immutable catalog identity. Compare complete guest states under
all four masks and inspect finite mask-0/mask-3 TCG logs. Original-game slice
trials establish only their admitted prefix and declared seed; they do not
qualify whole-room execution or held-out games.
