# Observed KQ1 troll-bridge scene export

The private goat scene exporter can retain a third contiguous observed action:
`show-carrot`, `leave-pen`, then `troll-bridge`. The same shared IL scene backend
and separate text player provide `use carrot on goat`, `use route`, and finally
`use bridge`. The third command reproduces the supplied bridge outcome under
phase and state guards. The export remains a partial authored projection, with
no native execution, autonomous clock, or durable save. Checkpoints are in
memory. Existing one-action and two-action scene output is unchanged.

The [ordinary goat capture contract](AGI_NATURAL_GOAT.md) still applies. The
extension adds an independently read carried-item observation, explicit bridge
state, three source-bound message observations, and a hash-bound native score
write receipt. The exporter checks consistency of supplied evidence; it does
not authenticate the operator, replay the original route, or prove whole-game
recovery. Original resources, messages, frames, traces, databases, native states,
and generated scenes stay outside Git.

## Collect and qualify the capture

The checkout includes the ordinary-input collector for the owner's unchanged,
qualified AGI 2.917 KQ1 edition and separately prepared backend:

```sh
PYTHONPATH=src:.:player python examples/agi/verify_troll.py \
  --source /private/kq1 --backend /private/dosbox-x \
  --output /private/new-troll-capture
```

The collector extends the fresh goat route from room 9 to the bridge. It uses
physical keyboard input and observes the original interpreter. A story flag
alone is insufficient to establish that the carrot is carried: the collector
binds item 3 in the original inventory table and reads its location value
`0xff` separately. The original game owns scripted actor positioning.

The route continues across the cleared bridge using ordinary arrows. The
six-pixel ego baseline fits near x35; x41 intersects the north rail. It stops
near y44 on the far bank without leaving room 25. The original room logic owns
its post-encounter collision policy. No debugger collision or coordinate edits
are used. The collector checks neutral input, room 25, the cleared-troll flag,
score 11, and the water flag after crossing.

Route execution has a 420,000 guest-millisecond and 360,000 wall-millisecond
ceiling. Native dialogue and trace work consume those same remaining limits.
An arrow intended to stop movement can be consumed by a real modal dialogue.
The controller rechecks direction and sends a fresh direction-selected key only
after it has observed a newly completed dialogue; four attempts bound this
case. Unknown delivery, incomplete dialogue, foreign stops and unexplained
failure to stop remain failures.

Raw capture visibility remains pending until separate inspection of stored
frames. Preserve `capture.private.json` and record explicit visibility in a
derived capture, retaining the parent and inspected-frame hashes. The exporter
requires boolean `goat_visible` on every used observation. The final bridge
observation additionally requires `goat_visible: false` and
`troll_visible: false`. A native actor's drawn flag is a different observation
and cannot supply either frame-visibility value. The exporter checks frame
bytes, hashes, and metadata; it does not interpret the pixels.

## Third-action contract

For a three-action capture, every used observation must include the original
five state fields plus boolean `carrot_carried`, `troll_removed`, and
`troll_paid`. Source identities must include logic 25, logic 103, and every
other logic containing a captured message. The third action must have
`id: "troll-bridge"`, and its `before` ID must equal the second action's
`after` ID. The second action must be `leave-pen` with its existing qualified
logic-103 invocation receipt.

The bridge action requires these observations:

| State field | Before bridge action | After bridge action |
| --- | --- | --- |
| `room` | 9 | 25 |
| `score` | 7 | 11, an increase of four |
| `carrot` | true | true |
| `carrot_carried` | true | true |
| `following` | true | false |
| `troll_removed` | false | true |
| `troll_paid` | false | false |

`gate_open` remains a required boolean state field. As with the prior actions,
the third action needs a nonempty label and verb, `complete: true`,
`messages_complete: true`, and completed, delivered keyboard input records.
Its logic-25 message observations must occur exactly once in this order:

| Logic | Source offset | Message ID |
| --- | --- | --- |
| 25 | `0x014c` | 1 |
| 25 | `0x016a` | 2 |
| 25 | `0x019f` | 30 |

Every message requires its completed original print-handler return, settled
input, closed window, source `print` instruction, and a hash-bound frame in the
existing capture format. Missing, duplicate, reordered, or extra logic-25
messages refuse export. Messages from another declared logic still need the
normal source and completed-frame binding. Generated dialogue is labeled as
source text before runtime formatting and remains private.

## Native score-write evidence

The third action supplies
`native_score_write: {"path": "troll-score-write.private.json", "sha256": "..."}`.
Paths are relative to the private artifact directory. The exporter loads the
raw JSON and checks its hash before checking these fields:

- `format: "fdisbull-agi-troll-score-write-1"`, `status: "verified"`,
  `complete: true`, and `native_execution: true`;
- `source_logic_sha256` equal to the declared logic-25 resource hash,
  `source_offset: 0x01b8`, `before_score: 7`, and `after_score: 11`, agreeing
  with the bridge observations;
- source bytes `05 03 04` at logic-25 offsets `0x01b8..0x01ba`, binding the
  score-variable addition to the supplied edition;
- `writer` with integer `source_offset: 0x72da`, `resume_offset: 0x72de`,
  `bx: 3`, and `al: 4`;
- `trace` with a nonempty relative `path`, SHA-256, and integer `count: 32`.
  The trace artifact must be present, nonempty, and match that hash.

The trace is retained continuation evidence. The exporter verifies its bytes
and the supplied count, without interpreting its events or upgrading fetched
instructions to completed execution. These JSON fields are supplied assertions,
not an authenticated chain of execution. A matching hash establishes byte
identity only.

The third provenance edge retains the score receipt hash, source logic hash and
offset, before/after scores, selected writer fields, and trace hash/count. It
omits private artifact paths and source message text. The scene also retains
the extra typed state and uses `carrot_carried` for its inventory condition.
At phase 3, the context is `Observed bridge cleared`, with score 11 and following
false. Repeated or stale commands do not replay the recorded action.

## Export, play, and portable checks

```sh
PYTHONPATH=src:. python examples/agi/build_goat_scene.py \
  --source /private/kq1 \
  --capture /private/new-troll-capture/qualified-capture.private.json \
  --artifacts /private/new-troll-capture --output /private/new-troll-scene
PYTHONPATH=src:player python -m fdisbull_player --backend-command \
  "python -m fdisbull.il_scenes /private/new-troll-scene/scene.json"
```

The output directory must be fresh, private, and outside the checkout, source,
and artifact trees. The exporter writes `scene.json` and `provenance.json`; the
latter binds the canonical supplied capture, source identities, frames,
message occurrences, score-write evidence, and generated scene hash.

`python -m pytest -q tests/test_agi_goat_scene.py` exercises authored portable
fixtures only. It covers the third player action, state and evidence refusal,
exact message occurrences, stale/repeated actions, in-memory checkpoint
restoration, and unchanged one-action/two-action export bytes. It supplies no
independent evidence of original-game reachability or a completed native run.

## Qualified local result

The [sanitized verification receipt](evidence/agi-troll-bridge-2026-10-31/receipt.json)
records two completed fresh-game encounters on local macOS ARM64. The final
run also crossed the bridge and stopped at (34,44) in room 25. Score changed
from 7 to 11 at the source-bound original write; the carrot stayed carried,
the troll-payment flag remained false, and the goat retired. The selected final
frames were inspected separately for actor absence. Source and private-copy
file manifests matched after teardown.

The exported three-action scene was exercised with installed 0.27.0, both
directly and through a separate content process. Its typed state matched the
observed final state, and stale/repeated actions and in-memory checkpoint
restoration were checked. This neither modifies that installation nor adds
durable checkpoint storage to the IL scene backend.

The receipt also preserves the earlier failed attempt: a completed bridge
dialogue consumed the movement-stop key, so the controller refused to claim
success. Local tests and native observations are separate from Linux CI.
No GitLab CI acceptance, integration merge, tag, release or installation update
is claimed by this follow-up.
