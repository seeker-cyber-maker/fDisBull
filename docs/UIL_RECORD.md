# Indexed UIL records: strings, arrays and `print_text`

Status: **additive experimental record format**, implemented in
`src/fdisbull/uil_record.py` with tests in `tests/test_uil_record.py` and
`tests/test_civ_world_uil.py`. It does **not** change `fdisbull-il-1` or the
`fdisbull-il-scene-1` envelope.

The recovered Civ-style screen record needs two things the current IL blocks
lack:

1. **String state.** Leader and city names are text buffers, not integers.
2. **Indexed state.** The page-2 map is an 80x50 collection, and the other
   layers are indexed arrays. Repeating one scalar per cell is not a faithful
   representation.

The record also settles the reference rule: **all variable references are
zero-based slot indices**. Slot 0 is the first declaration. A name is optional
documentation; it is never the lookup key.

## 1. Document

```json
{
  "format": "fdisbull-uil-record-1",
  "role": "uil",
  "slots": [
    {"type": "u8", "initial": 0},
    {"type": "string", "initial": "Rome", "max_bytes": 16}
  ],
  "body": [
    {"id": "print-name", "op": "print_text", "slot": 1, "x": 8, "y": 4}
  ]
}
```

The top-level fields are `format`, `role`, `slots`, `body` and optional
`evidence`. `role` uses the existing `udl`/`uil` meaning; no new authority is
claimed by the string. A record is limited to 1 MiB, 4,096 slots and 65,536
blocks/conditions, depth 64.

## 2. Slots

Each slot is declared in order and addressed by its index. Runtime state is a
list in the same order; it is not a name-keyed dictionary.

| Type | Initial value | Operations |
|---|---|---|
| `bool` | boolean | `set`, `eq`, `bit_test` |
| `u8/u16/u32/u64`, `i8/i16/i32/i64` | in-range integer | `set`, `add`, `subtract`, `multiply`, `divide`, comparisons |
| `string` | string plus `max_bytes` | `set`, `eq`, `print_text` |
| `array` | `element` scalar type, `length`, initial list | `set_element`, `eq` is not a collection operation |

An array is fixed length and fixed element type. A string is bounded by
`max_bytes` in UTF-8. Neither is an unbounded host object. Arithmetic wraps at
the declared width; boolean and string arithmetic is invalid.

## 3. Value references

A literal is a JSON integer or boolean. A state reference is:

```json
{"slot": 23}
```

There is no `$name` lookup in this record. This is deliberate: a recovered
record can use its original numeric slot without inventing a symbol, and a
renamed slot cannot silently change a program's meaning.

`x` and `y` in `print_text` and `index` in `set_element` accept either a
literal integer or a numeric slot reference. A string slot is not a valid
coordinate or array index.

## 4. Operations

| Operation | Fields | Meaning |
|---|---|---|
| `set` | `slot`, `value` | Store a literal or another slot's value. |
| `add`, `subtract`, `multiply`, `divide` | `slot`, `value` | Integer arithmetic with width wrapping; division by zero refuses the whole action. |
| `if` | `condition`, `then`, `else` | Ordered branch. |
| `require` | `condition` | Refuse the whole action when false. |
| `set_element` | `slot`, `index`, `value` | Replace one cell of an array slot. |
| `print_text` | `slot`, `x`, `y`, optional `font`, `color` | Emit a declarative text event from a **string slot** at coordinates. |

Conditions are `eq`, `ge`, `bit_test`, `not` and `and`, using the same
references. `ge` is integer-only; `eq` requires compatible types.

### `print_text`

The canonical operation is:

```json
{"id": "print-row-23", "op": "print_text", "slot": 23, "x": 0, "y": 23}
```

If slot 23 contains `"hello"`, the evaluator returns:

```json
{"op": "print_text", "slot": 23, "text": "hello", "x": 0, "y": 23}
```

This is an **event**, not a host draw. The record does not claim a VGA render,
clipping, font metrics or palette. `font`/`color` are optional presentation
hints in the event. A later renderer can bind them to an extracted
`FONTS.CV` font or a scene palette.

## 5. Execution and failure

`execute_record()` validates the complete record first, including unselected
branches, then executes atomically:

- a failed `require`, out-of-range index, non-string `print_text` slot, bad
  assignment, division by zero or budget stop returns `status: "refused"`;
- refused execution returns no events and does not commit the work state;
- a completed execution returns the committed state, ordered text events and
  visited block IDs;
- events are ordered by execution; `print_text` does not perform I/O.

The record is not a replacement for the scene envelope. The scene envelope
still owns contexts, objects, visibility, action binding and the Z player. A
future bridge/compiler can lower record fields into IL programs or serve the
record through a renderer, but that bridge is not claimed here.

## 6. Civilization reduced world record

`examples/civ/civ_world_uil.py` turns one decoded `CIVILn.MAP` page-2 image
into a record:

- slots **0..49**: 50 map row strings, row-major;
- slots **50..56**: terrain, terrain colour, unit owner, unit present,
  improvements, known improvements and the original 80x50 minimap, each
  4,000 cells;
- slots **57..60**: viewport/selected x/y scalars;
- body: 50 `print_text` operations for rows 0..49.

Therefore `print_text(23, 0, 23)` prints map row 23. The uppercase glyph in a
row marks a unit present; that is the reduced Z convention, not an original
screen rule. The source layers and the extraction boundary are documented in
[CIV_MEDIA_FORMATS.md](CIV_MEDIA_FORMATS.md).

```sh
PYTHONPATH=src:. python3 -m examples.civ.civ_world_uil \
  --map /private/CIVIL0.MAP \
  --out /private/civ-world-record.json \
  --summary /private/civ-world-summary.json \
  --text /private/civ-world-map.txt
```

The record is intentionally not committed with game-derived rows. The builder
and format are committed; the private output is a caller's evidence.

## 7. Limits

- No text-entry/event operation yet. `set` can assign a string; the original
  edit-line still needs a separate input event and bounds policy.
- No variable-length arrays, nested arrays, string slicing, encoding
  conversion or collection iteration. The 80x50 map fits a fixed `i8/u8/u16`
  array; general collections do not.
- No host rendering, input dispatch, audio or save persistence.
- The record does not by itself prove the original screen. It represents the
  recovered state and a reduced text projection; runtime pixel claims remain
  separate.
