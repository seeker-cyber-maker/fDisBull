# Resource-bound AGI design packet

This packet lets a reader build a diagnostic background-plus-sprite preview
from real resource pixels and native position observations. Its qualification is
`source_bound_design_preview_with_native_position_fragments`. The containing
room has not been executed. Keep that distinction in every output claim.

## Evidence and choices

- `logic` and `sites` identify the original LOGIC resource and exact instruction
  boundaries. All `payload_offset` values include the two-byte code-length
  prefix; `code_pc = payload_offset - 2`. These are static sites, not proof that
  their branches executed together.
- `design.picture` supplies an explicit designer value for the variable used by
  the selected `draw.pic` instruction. No reaching value or current room is
  inferred. The original picture resource identity is retained.
- `design.cel` supplies the selected original VIEW, loop and cel. The view ID
  comes from the selected `set.view` site. Loop/cel are explicit designer pose
  choices. They are not an observed animation state.
- `fragments.original` and `fragments.edited` are stopped native QEMU captures.
  Each executes a four-byte literal `position` instruction and an authored
  return, once, in a fresh zero-initialized pilot. The original instruction is
  copied exactly from its source site. The edited instruction uses the detached
  literal-position planner. Actual containing-room behavior remains unknown.
- `fragment_mapping` maps only fragment PCs 0..3 to the original instruction.
  PC 4 is an authored return and has no original source address. Native logic ID
  zero is the pilot's identifier; use `actual_logic` for the resource number.
- `source_edit_proposal` addresses the original resource while recording that
  no original file was written and full-LOGIC replay has not been qualified.

Each fragment contains `captured_scene.view.actors`. Select the actor whose
`id` equals `design.actor`, and use its `x`/`y` for that preview. Other zeroed
pilot actors are not observations of other characters in the original game.
The scene's `source`, `session_id`, `checkpoint`, `guest` and `coverage` bind
each observation to its own native child and stopped interval.

Original resource payloads are withheld. Their identities and the source-site
association are collector attestations, so a helper cannot independently rehash
those full resources. It can verify every supplied asset file, compare repeated
identity fields, and recover/check each five-byte native fragment from its
complete DISASM records. Keep those levels of verification distinct.

DISASM is mask bit 1 and SCENE bit 2; these runs select both (3). `retire`
records describe completed instructions, while `position` records describe
effective changes. Both records for one instruction share its retirement
ordinal. A zero-effect assignment can have a retire record and no position
record. Do not double-count the pair. The stopped counters expose loss.

## Assets and exact preview recipe

Verify the SHA-256 and length in `assets` before using each sibling file:

| File | Layout |
| --- | --- |
| `background.idx` | 160 × 168 row-major EGA color indices, one byte per pixel |
| `priority.idx` | Same geometry; decoded original priority/control values |
| `cel.idx` | `design.cel.width` × `design.cel.height` row-major color indices |

Every index is in 0..15. `render_contract.palette_rgb` is the complete diagnostic
RGB palette. Cel pixels already have their effective loop mirroring applied;
do not mirror them again. `transparent_color` identifies transparent cel pixels,
including omitted row tails.

For each fragment, copy the background indices. Place the cel's left edge at
actor x. AGI-style coordinates use the lower-left baseline, so the first cel row
is `top = y - height + 1`. X increases rightward and Y downward. Clip pixels to
the 160 × 168 canvas. Replace a background pixel only when the cel index differs
from `transparent_color`. Convert every resulting index using the supplied
palette. Save the logical 160 × 168 RGB image without resampling or annotations.
An additional display-sized copy may double X with nearest-neighbor scaling.

This recipe deliberately renders one diagnostic unoccluded layer. It does not
use the priority plane to establish game occlusion, draw order, collision or
current visibility. Preserve those unknowns; the source picture and cel bytes
do not supply a stopped full-engine scene state.

## Independent reconstruction task

Use only this guide, `packet.json`, and the three listed indexed assets. Do not
read the collector, product implementation, original game files, private oracle
or another helper's output. Save an independent reader, `original.png`,
`edited.png`, a JSON result and short friction notes. The JSON should report:

- Case ID and actor ID; original and edited observed positions.
- Picture/view/loop/cel identities, dimensions, transparency and mirroring.
- Logical output dimensions and SHA-256 of each raw RGB image buffer.
- Original source payload offset/code PC and the fragment/source mapping.
- `containing_logic_executed: false`, `game_visibility_known: false`,
  `engine_frame_equivalence: false`, and any additional unknowns.
- Whether all supplied identities and native observations were consistent.

Record questions or assumptions, implementation passes and reader executions.
Do not turn a successful diagnostic composition into a claim about a complete
room, successful gameplay, or an original-engine screenshot.
