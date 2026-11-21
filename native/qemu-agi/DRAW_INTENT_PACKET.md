# Detached AGI cycle and draw-intent packet

This directory is a private `fdisbull-agi-draw-intent-packet-1` packet. Use only
its declared inputs to reconstruct the selected diagnostic layers and their
semantic report. The packet is sufficient for the bounded preview task; it
does not establish the original displayed room or complete game execution.

## Files and identities

Start with `packet.json`. Verify every file in `assets`, every document in
`documents`, and the catalog by their declared length and SHA-256. The packet
includes this README, `DRAW_INTENT_PROFILE.md` and `VIEW_BINDING_PROFILE.md`.
Those documents define the new execution contract and its base catalog/actor
semantics. `catalog.bin` uses FDBAGIV1; catalog ordinals and dimensions must
agree with native state and all candidate cel metadata.

Reconstruct raw fragment bytes from `entry.load_prologue_bytes`, the ordered
`sites[*].bytes`, and `entry.authored_return_bytes`. Check native source size
and SHA-256, the contiguous source mapping and copied-span digest. Authored
load and return bytes have no original source address. The containing original
room and its entry conditions were not executed.

## Execution facts

`native.snapshot` uses `fdisbull-agi-intent-state-1`. Select each actor's actual
VIEW/loop/cel and geometry from `guest.actors`; cel asset enumeration is a set
of candidates, not a hand-selected answer. `native.observations` supplies the
complete retirement and SCENE journal for this one run. Replay its load and
actor before/after transitions from `entry.initial_snapshot` and compare every
actor and loaded VIEW with the final native state.

Two endpoint kinds are possible:

| Endpoint | Meaning |
| --- | --- |
| `authored_return` | Every copied action retired, then the appended authored return retired. No later original source was run. `draw_request` and native pending_effect are null. |
| `pending_draw` | The final copied draw was reached but did not retire or mutate committed actor state. `draw_request.native_descriptor` is identical to native pending_effect. No later instruction ran. |

For a pending draw, compare `draw_request.committed_pose` with the complete
native actor, and match its source/site/actor/bytes to the final copied draw.
It has `committed=false`, `retired=false`, `completion_available=false`.
The `position_repair_completed`, `sprite_buffers_updated` and
`presentation_established` fields are false. They describe work not completed
by this fragment; they do not assert the visibility of a separately running
original game. The current coordinates are input to the deferred draw, not a
claimed repaired draw position.

Cycling is a committed control bit. `stop.cycling` can change it without moving
the actor or advancing its cel. Infer a reset-derived field only when the
initial snapshot and every transition support that conclusion. Explicit source
commands, reset retention and pending effects must stay distinct in the report.

## Diagnostic reconstruction

Use the selected cel's `asset` indexed-pixel file. Dimensions and transparency
come from that cel row. Pixels have already been oriented by the resource
decoder; do not mirror them again. `mirrored` documents effective orientation.
Use `render_contract.palette_rgb` to expand palette indices.

Each actor output is a transparent RGBA canvas of 160 by 168 pixels. Place its
cel at x and top row `y-height+1`, clip only to the canvas, and leave the declared
transparent index transparent. Save it as `actor-<id>.png`. Save `scene.png` as
RGB: expand `background.idx`, then composite selected layers in
`render_contract.draw_order`. That is a diagnostic order, not observed native
sprite order or priority occlusion. Do not use `priority.idx` to invent effects
that the packet does not claim to execute.

For a pending draw, this image previews the requested layer using its current
committed pose. For an authored-return endpoint, it previews selected bound
layers. Neither image establishes current visibility or presentation.

## Required reconstruction report

Write `reconstruction.json` with:

- `schema`: `agi-draw-intent-reconstruction-1`;
- `packet_id` and `endpoint_kind`;
- `actors`: selected IDs with view/loop/cel, width/height, x/y, prev_x/prev_y,
  animated, update and cycling, plus the output filename;
- `pending_draw`: null, or actor ID, original payload offset, fragment PC,
  committed=false, retired=false, completion_available=false;
- `visibility_established`: false and `presentation_established`: false;
- `scene_file`: `scene.png`, checks performed, and explicit remaining unknowns.

Also retain your standalone reconstruction program and a concise `REVIEW.md`.
Explain any missing data or document that prevented verification. A complete
diagnostic image is not evidence that pending position repair, collision,
priority, sprite composition or presentation took place.
