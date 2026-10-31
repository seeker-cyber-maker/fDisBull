# Z world language and the Zork I map

Date: 31 October 2026. The source is the MIT-licensed
[`historicalsource/zork1`](https://github.com/historicalsource/zork1) checkout at
commit `97b7b3d68c075dd9af7da499c3e9690ada3471fd`. No retail story image, story
bytes or game prose is included in the generated structural artifact.

## Why another IR

The earlier Zork work had a raw Z-machine object projection and a two-room
semantic slice. Neither is a complete map. Z is a deliberately small,
Zork-like language for the missing middle: rooms and their exits as authored,
source-addressable data, with explicit blocked, conditional and routine exits.
It is closer to ZIL than to a generic graph schema, but it is not ZIL and does
not execute.

## Language shape

A document is `(z-world NAME MEMBER...)`. Members are `source`, `source-file`,
`entry`, `directions`, `room` and `object`. A room has optional `desc` and
`flags`, plus one form per direction. An exit form is `to`, `blocked`, `per` or
`unknown`; `to` may carry `(if ...)` and `(else (blocked))`.

The reader is strict about structure and case, and the writer emits a canonical
form: sorted rooms/objects, declared direction order, sorted flags. A parsed
document is therefore stable under `parse → write → parse → write`.

Validation separates hard errors from retained unknowns:

| Code | Severity | Meaning |
| --- | --- | --- |
| `unknown-entry` | error | entry is not a room |
| `unknown-direction` | error | exit direction not declared |
| `duplicate-direction` | error | two exits share a direction |
| `unknown-target` | error | passage target is not a room |
| `missing-target` / `missing-condition` / `missing-routine` | error | malformed clause |
| `unresolved-location` | warning | object location is not room/object/pseudo |
| `unreachable-room` | warning | no static path from the entry |

## Zork I census

Lifting all `ROOM` and `OBJECT` forms from the ZIL tree yields 110 rooms, 140
objects and 352 exit clauses. The exit split is 277 plain passages, 31
conditional passages, 37 blocked exits, 7 `PER` exits and no unknown clauses.

The static graph reaches 105 rooms. `RIVER-1` through `RIVER-5` have no incoming
room-exit edge; `1actions.zil` supplies their entry/flow through `RIVER-FUNCTION`
and the river speed/next tables. Z keeps that as an unresolved dynamic boundary
instead of adding an edge from the table without a runtime observation. Seven
exits are `PER`: four `MAZE-DIODES`, plus `GRATING-EXIT`, `TRAP-DOOR-EXIT` and
`UP-CHIMNEY-FUNCTION`; their destinations are decided at runtime.

The map has 22 one-way static exits. Many are genuine one-way passages (for
example trap doors, slides and the river); the compiler does not "fix" them by
symmetry. It reports the count, while the `.txt` index keeps direction and
condition on every clause.

## Verification

- `python -m pytest tests -q` — 5 tests: round trip, graph census, validation,
  the ZIL inline-comment quirk, real-source census and Graphviz rendering.
- The real-source test pins commit and counts, checks every passage target
  resolves to a room, checks West of House's exits and the mailbox location, and
  requires the five river rooms to be the only unreachable ones.
- `generated/zork1-zil.json` is the compiled graph;
  `generated/zork1-zil.svg` is a Graphviz rendering with dashed conditional edges and diamond routine nodes.

## Limits

Z is not a Z-machine IR and not a playable world. It does not evaluate the
`IF` conditions, expand `PER` routines, model object state or parser actions, or
claim that the retail release-88 story has the same room set. The SVG is a
force-layout drawing over the graph; positions are not game geometry. Descriptions
and blocked messages are omitted from the checked-in map; `--with-text` retains
them only when the caller deliberately handles that text.
