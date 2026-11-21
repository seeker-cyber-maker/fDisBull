# AGI observation reconstruction packet

This is a protocol reference for an independent reconstruction exercise. Treat
the supplied packet as the complete evidence available to you. Do not read the
original program, repository implementation, another helper's files, or the
coordinator's expected answers. Do not run a guest or contact an external system.

## Available evidence

Each case has a source identity, a host attachment ID, stopped checkpoint
metadata and the exact native event envelope. The collector attests that the
selected mask stayed enabled throughout this execution interval, with no clear
or restart during the interval. State and events were read from one unchanged
stopped checkpoint. No initial guest snapshot is supplied.

Some packets also include `captured_scene`, the existing scene consumer's
snapshot-backed result. Use it only when it is actually present. It can restore
current positions after a history gap, without recreating missing history.

The native profile is `agi-2917-scalar-position-pilot-1`. It has 16 actor slots,
256 byte variables and 256 flags. Do not infer an actor's current state from its
absence in an event stream. The profile name alone is not an initial-state
receipt. Actor slots and coordinate facts do not establish visible characters.

## Record interpretation

- The host mask uses `DISASM=1` and `SCENE=2`: values 0/1/2/3 select off,
  DISASM only, SCENE only, or both. A selected channel can legitimately have
  zero eligible records. Check its mask bit and the continuity attestation;
  positive record counts are not required to establish that it was enabled.
- `kind: retire` is the DISASM channel: a completed instruction's raw opcode,
  exact code-relative PC and byte span, actual successor and retirement ordinal.
  It does not contain a decoded mnemonic or an execution-before variable table.
- `kind: position` is SCENE: an effective position change, including actor ID,
  complete before/after position fields and the responsible source instruction.
  An assignment that changes none of those fields produces no SCENE record.
- With both channels enabled, a retirement record precedes the position record
  for the same instruction. They share one `retired` ordinal; do not count them
  as two executed instructions.
- `seq` is shared by both channels. Buffer storage retains a prefix and drops
  newly eligible records when full. A lost tail need not leave a visible gap
  among retained sequence numbers. Read total and per-channel counters.
- `epoch` separates observation clears/restarts. `control_generation` identifies
  control changes; final mask and epoch alone do not prove collection continuity.
- Positioning sets `x`, `y`, `prev_x` and `prev_y` to the assigned coordinates.
  `after.prev_x/prev_y` are not the prior position; use `before` for that.
- Variable position operands are variable IDs. A position witness's `after`
  fields give resolved values at that instruction, which may differ from later
  variable values. A last effective-change witness need not be the last executed
  position instruction.

The following opcode reference is sufficient to interpret these exercise
packets. All operands are byte values. Numeric opcode values are decimal.

| Opcode | Bytes | Meaning |
| --- | ---: | --- |
| 0 | 1 | Root return |
| 3 | 3 | `assignn(variable_id, literal_value)` |
| 37 | 4 | `position(actor_id, literal_x, literal_y)` |
| 38 | 4 | `position.v(actor_id, x_variable_id, y_variable_id)` |
| 39 | 4 | `get.posn(actor_id, x_variable_id, y_variable_id)` |

Other pilot instructions exist, but are not required by this packet's opcode
vocabulary. Bytecode addresses are relative to the raw LOGIC code, not a complete
resource container. Size and SHA-256 bind that entire raw source. Recovering all
source bytes requires coverage of every byte without contradictory spans, then
verification against the recorded size/hash. A dynamic trace does not generally
cover unexecuted branches.

## Deliverables

Write a small reusable Python reader `reconstruct.py`, its generated
`reconstruction.json`, and a concise `NOTES.md` in your assigned output directory.
Use standard-library code only. You may add a self-contained diagnostic SVG or
HTML plot, but a numerical position scaffold is sufficient. Never invent missing
resources, images, room dimensions, visibility, collision or drawing order.

Use this result shape (add evidence/notes fields as useful):

```json
{
  "schema": "agi-helper-reconstruction-1",
  "condition": "copied from packet",
  "cases": [{
    "id": "copied from case",
    "source_sha256": "copied source identity",
    "scene_history_complete": false,
    "actors": [{
      "id": 0, "x": 0, "y": 0,
      "final_verified": false,
      "last_effective_change_pc": null,
      "last_position_instruction_pc": null,
      "evidence": "explain which record or snapshot supports each claim"
    }],
    "unknown_actor_ids": [],
    "recovered_source_hex": null,
    "rebuild_program_hex": null,
    "can_render_original_scene": false,
    "unknown_scene_fields": [],
    "notes": []
  }]
}
```

An actor record may be a verified final position or an explicitly historical
last observation. Do not label a retained prefix as final state when later
unobserved changes remain possible. Use null for an unsupported last-assignment
claim. List actor IDs whose current position remains unknown.

If the evidence supports final placements, construct a new raw program of
literal `position` instructions followed by `return` that reproduces those
supported coordinates. This is a placement scaffold; it need not reproduce
variable state, bindings, history or other semantics. A code reconstruction is
a separate claim recorded in `recovered_source_hex`. Preserve uncertainty for
incomplete captures. The coordinator will validate and execute admitted programs.

In NOTES, list every input file read, any assumptions or questions, concrete
friction, whether one pass was enough, and the smallest additional information
needed for a faithful rendered scene. Keep conclusions specific to this trial.
