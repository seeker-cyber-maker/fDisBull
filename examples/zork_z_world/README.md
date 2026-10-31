# Z: a Zork-like world language

This example lifts the initial Zork I world from the MIT-licensed ZIL source
into **Z**, a small S-expression language for Zork-like maps. Z records rooms,
typed exits and initial object placement; it does not execute ZIL, run a
Z-machine, or claim story equivalence.

The generated structural map is:

| Item | Count |
| --- | ---: |
| Rooms | 110 |
| Objects | 140 (including pseudo/meta objects) |
| Exit clauses | 352 |
| Plain passages | 277 |
| Conditional passages | 31 |
| Blocked exits | 37 |
| Routine-computed exits | 7 |
| Rooms reachable through static exits | 105 / 110 |
| One-way static exits | 22 |

`RIVER-1` through `RIVER-5` have no static incoming room exit. They are entered
through the game's river function and river tables, so the compiler reports them
as unreachable rather than inventing edges. The 22 one-way exits are retained as
one-way; they are not symmetry errors.

## Files

- `zlang.py` — Z reader, validator, graph compiler and renderers.
- `build_zork_world.py` — ZIL room/object lifter and CLI.
- `generated/zork1-zil.z` — the structural world map in Z.
- `generated/zork1-zil.json` — compiled graph (nodes, exits, objects, stats,
  diagnostics).
- `generated/zork1-zil.txt` — distance levels, full exit index and diagnostics.
- `generated/zork1-zil.svg` — Graphviz view; dashed edges are conditional,
  diamonds are `PER` routines.

## Run

The lifter reads a checkout of
[`historicalsource/zork1`](https://github.com/historicalsource/zork1) at
`97b7b3d68c075dd9af7da499c3e9690ada3471fd`:

```sh
python build_zork_world.py \
  --source-root /path/to/zork1-open-source \
  --out-dir generated
```

Use `--with-text` to retain room descriptions, blocked prose, object names and
synonyms in Z. The checked-in structural map intentionally omits all story prose.
Use `--no-svg` when Graphviz is unavailable.

Tests:

```sh
python -m pytest tests -q
```

The real-source test skips when the ZIL checkout is absent. It pins the source
commit and the observed census; it does not require a retail story image.

## The language

```lisp
(z-world "sample"
  (source "https://example.invalid/zil" "commit" "MIT")
  (entry A)
  (directions NORTH SOUTH EAST WEST)
  (room A
    (flags RLANDBIT)
    (NORTH (to B))
    (EAST (blocked))
    (SOUTH (to C (if WON-FLAG) (else (blocked)))))
  (room B
    (SOUTH (to A)))
  (room C
    (EAST (per ROUTINE)))
  (object BOX
    (in A)
    (flags CONTBIT)))
```

An exit is one of:

- `(to ROOM)`
- `(to ROOM (if FLAG...) (else (blocked)))`
- `(blocked)` or `(blocked "message")`
- `(per ROUTINE)`
- `(unknown)`

Directions are declared by the document, not hard-coded. A target must be a
declared room; an object location may be a room, object or the pseudo locations
`LOCAL-GLOBALS`/`GLOBAL-OBJECTS`. The compiler never guesses a target for a
`PER` exit, and it leaves a dynamic entry unknown.

## Provenance and limits

- Source: `historicalsource/zork1`, MIT license, commit
  `97b7b3d68c075dd9af7da499c3e9690ada3471fd`. This is the release-119 ZIL
  source, not the retail GOG release-88 story. The map is not asserted to be
  byte- or behaviour-identical to the retail image.
- Z describes initial structure. It does not model parser grammar, mutable
  object state, timers, scoring, the thief, save/restore or condition evaluation.
- `PER` exits and river/water transitions remain opaque; their runtime targets
  are not inferred from table data.
- The SVG layout is a graph drawing, not canonical game geometry. Room adjacency
  is the claim; pixel position is not.
- The structural map contains derived identifiers, flags and exit structure, no
  story prose or story bytes.
