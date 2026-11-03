# Observed KQ1 goat scene export

`examples/agi/build_goat_scene.py` builds a private, partial Z scene from the
owner's game and a separately prepared `fdisbull-agi-natural-encounter-1`
capture. It does not run the game or authenticate capture claims. The exporter
checks the AGI and declared logic resource hashes, frame file hashes and metadata,
explicit ordinary-input completion, and any source-message binding before
producing content. Missing or contradictory required evidence stops the export.
Original game files, message exports, raw captures and scene output stay private.
Selected native verification frames are retained with the sanitized receipt.

## Collect the original encounter

Run the checkout with the qualified DOSBox backend and the owner's unchanged
AGI 2.917 KQ1 edition:

```sh
PYTHONPATH=src:.:player python examples/agi/verify_goat.py \
  --source /private/kq1 --backend /private/dosbox-x \
  --output /private/new-goat-capture
```

The replay starts a new game, walks to the garden, takes a carrot, opens the
gate, enters the pen, approaches the roaming goat, shows the carrot and leads
it out to room 9. It uses ordinary keyboard input with physical policy locked.
There are no debugger memory/register writes, redirected calls, teleports or
checkpoint loads. A baseline is saved privately by the shared launch helper;
the replay never restores it. Route and native-observation budgets are bounded;
unexpected stops or blocked movement remain failures with partial evidence.

The script observes original print-handler entry and return using
`AGIDOSPrintObserver`, checking engine/resource identity, source argument,
native stack and original RAM message. An existing parser key release can
settle during a guarded frame interval. One dismissal key is sent only after
the original modal wait, a fresh frame and idle input are qualified. Unknown
run/input outcomes and partial completions remain recorded; readback cannot
replay a key. Message return and later state commitment have separate bounded
checks: the carrot/follower flags and score can change after the print returns.

The final logic-103 invocation is selected at its naturally reached first
fetch. The adapter compares its declared scalar/object projection against the
lifted source and requires the original stack-matched return. This is one
normal route, not the earlier synthetic branch sweep or whole-game parity.
The current replay does not qualify troll resolution, water refusal, every
roaming-goat timing or all navigation paths.

`capture.private.json` leaves `goat_visible` as null until a separate frame
review. Preserve that original file; put explicit visibility observations and
parent/frame hashes in a derived capture for export. A drawn flag and a stored
frame describe different observations: a completed frame may still show an
actor whose later RAM drawn flag has cleared. Never infer visibility from that
flag alone. Generated source text and native VIEW versions stay private.

## Native VIEW cache binding

Ordinary direction changes cause this interpreter to mirror shared VIEW cels
in place. Native write watches observed the header writer at `CS:57DC` and both
directions of the cache change. Re-encoded rows can consume reserved cel bytes
or leave unused tails. Raw source/runtime hashes remain different.

The adapter accepts only byte identity or a bounded shared-cel cache relation:
same directories, dimensions, transparency and effective pixels for every
loop alias, with mutations confined to that cel's structural allocation.
Descriptions and other structures remain protected. Mid-transformation
captures, changed pixels and malformed/overlapping structures refuse.
`view_bindings` records the relation and both hashes; `native_view_captures`
retains observed raw versions for private export. This is not a blanket skip of
resource validation or evidence of whole-program equivalence.

The sanitized [verification receipt](evidence/agi-natural-goat-2026-10-31/receipt.json)
records the normal route, source comparison and native writer evidence.
The follow-up uses the local Git review flow; GitHub Actions was disabled and
no Linux CI success is claimed. Installed 0.27.0 can consume the exported IL
scene, while the new native observer/cache binding belongs to this unshipped
stacked change. No installation update is required to play the export.

## Export and play

The capture supplies:

- `source.agi_sha256` and `source.resources`, mapping decimal logic IDs to
  source resource SHA-256 values. Logic 103 and each logic containing a recorded
  message must be declared.
- `runtime` with `policy: "physical"`, `fresh_game: true` and an empty
  `interventions` list. These are operator assertions, not independently
  authenticated guarantees.
- `observations`, keyed by ID. Each has `state` with byte integers `room` and
  `score` and booleans `carrot`, `following`, and `gate_open`; an explicit
  boolean `goat_visible` from inspection of the frame; and `frame` with a
  capture-directory-relative `path`, `sha256`, and `metadata` containing integer
  `frame_id`, `mode_id`, positive integer `width` and `height`, and `source`
  equal to `last_completed_guest_frame`.
  The exporter verifies bytes and metadata presence, not image interpretation.
- One `show-carrot` action, optionally followed by one `lead-to-water` or
  `wander-away`, or `leave-pen` action. Each has a nonempty `label` and `verb`, `before` and
  `after` observation IDs, `complete: true`, `messages_complete: true`, and
  nonempty `inputs`. Each input has `kind: "keyboard"`, nonempty `key`, and
  `delivered: true` and `complete: true`. The key is a physical-input record
  label, such as `type:show carrot` or `press:enter`; it does not assert that a
  whole text entry is one physical key. The second edge must reuse the first
  edge's after-observation ID as its before-observation ID.
- Each action's `messages` list, empty only when observation was complete and
  no message occurred. Every listed message needs integer `logic`,
  `source_offset` and `message_id`, `status: "completed"`, true
  `handler_return_observed`, `input_settled`, and `window_closed`, plus a
  frame in the same form. The exporter verifies the source `print` instruction
  and retrieves the message resource. It does not prove the screenshot's text;
  scene output labels the message as source text before runtime formatting.

For `leave-pen`, the before room must be 10 or 11; the after room must be
outside both, with carrot and following retained and score unchanged. Its action
also requires `native_invocation: {"path": "...", "sha256": "..."}` for a
private `fdisbull-agi-original-host-trial-1` receipt relative to the artifact
directory. The exporter checks the raw file hash, verified and complete status,
native execution, empty differences, logic 103 identity and a nonempty source
path ending in return with no call or call.v opcodes. The path and hash are
checked against the captured logic-103 print occurrences, including their exact
count and order. Missing or duplicate message observations refuse. These are
supplied evidence, not an authenticated chain; the invocation verifies only its
declared comparison and does not prove the entire route or omitted effects.

The first edge must start with a carried carrot, a visibly observed goat and no
following flag; it must end with following set and the score increased by five.
The player uses the authored command `use carrot on goat`, followed by `use
route` only when a contiguous second edge was supplied. These commands are
projection choices, not claims about original parser phrasing. In particular, a
recorded autonomous departure is not established as caused by the route command.
The scene reproduces selected witnessed state changes under phase and state
guards, not every consequence or every possible encounter. It has no autonomous
clock, native execution, or durable save. Its checkpoints are in memory.

```sh
PYTHONPATH=src:. python examples/agi/build_goat_scene.py \
  --source /private/kq1 --capture /private/capture/encounter.json \
  --artifacts /private/capture --output /private/new-goat-scene
PYTHONPATH=src:player python -m fdisbull_player --backend-command \
  "python -m fdisbull.il_scenes /private/new-goat-scene/scene.json"
```

`provenance.json` binds the canonical capture hash, source identities, frame
hashes, selected message offsets and generated scene hash. It is a derived
record, not an independent signature or verification that assertions about
physical play, input consumption, visibility or dialogue are true. The builder
validates capture at export time; an already exported scene does not revalidate
it on each turn. `python -m pytest -q tests/test_agi_goat_scene.py` exercises
synthetic data only and does not establish original-game behavior.
