# Stopped SCUMM disassembly and scene packets

`processor_scene.py` turns native stopped facts into one source-bound packet.
It uses only Python's standard library, accepts caller-owned captures, and
neither launches nor resumes an emulator. The native CPU remains the decoder
and execution authority. The consumer validates identities, encoded extents,
counter accounting and witness consistency; it does not implement another
SCUMM interpreter.

The first packet schema is
`fdisbull-scumm-processor-scene-packet-1`. Its snapshot is current **as of its
recorded checkpoint**, including when observation is disabled or records have
been dropped. Its history is only the supplied retained native records.
`qualification.history_complete` is always `false` in this stateless version.

## Inputs and ownership

The caller supplies exact immutable kernel bytes and these native JSON values:

| Input | Schema | Requirement |
| --- | --- | --- |
| `scene` | `fdisbull-scumm-scene-1` | Required stopped actor/resource/control snapshot; newer captures also include authored verb slots |
| `events` | `fdisbull-scumm-events-2` | Optional retained DISASM and SCENE records from the same checkpoint |
| `decode_pages` | `fdisbull-scumm-early-decode-1` | Optional consecutive static pages with the additive source, extent and stop fields |

These schemas bind version, kernel size and SHA-256, runtime profile, manifest
SHA-256, source-receipt SHA-256 and selected script ID. Joining captures only by
PC or resource ID is insufficient. A hash records byte identity; the consumer
does not independently authenticate the original publisher or re-admit resource
payloads from the bank.

One caller must own and serialize VM access. Capture `scumm-scene-json`, then
`scumm-events-json` and any desired decode pages, then `scumm-scene-json` again.
Require the complete scene objects to be equal before calling the consumer.
The event epoch, control generation and observation accounting must also match
that scene. A matching bracket detects changes but is not a live ownership
lock. Static decode selectors do not move the guest PC or change observation
controls.

```python
from processor_scene import build_scene_packet, SceneInputError

# code is the exact immutable -kernel input. The caller has already acquired
# a coherent stopped scene/events/scene bracket using its own QMP controller.
packet = build_scene_packet(
    code=code,
    scene=scene,
    events=events,
    decode_pages=pages,
)
```

`build_scene_packet` is keyword-only and raises `SceneInputError` for malformed
or contradictory captures. It does not modify inputs and returns detached
output objects. Omitting `events` returns a useful snapshot with no alleged
changes; omitting static pages leaves static coverage unqualified.

## Facts in the packet

| Field | Meaning |
| --- | --- |
| `source` | Exact code/profile/catalog identity |
| `checkpoint` | Trace epoch, control generation, retirement, PC, guest status/fault and block reason |
| `observation` | Mask, capacity, retained count, eligible sequence, per-channel eligible/stored/dropped counts and observer calls |
| `actors` | All 32 supported actor states, including placement, room, metadata, indexed palette and raw name span |
| `verbs` | All 100 authored verb slots when supplied by the native snapshot; absent in older captures |
| `resources` | Declared slot counts and explicit available/resident/locked entries |
| `control` | Supported UI/cutscene state, global talk color and selected control-related variables |
| `disassembly.static_pages` | Canonical native static records and explicit listing boundaries |
| `disassembly.retirements` | Retained instructions that actually retired, with historical resolved operands and actual successors |
| `committed_changes` | Retained actor, global-color, resource, control and verb deltas |
| `evidence` | SHA-256 of code and deterministic JSON input representations |
| `qualification` | Explicit snapshot, history and presentation scope |

The actors' `bound` field means their placement was established in the bounded
model. It is not a visibility flag. Palette entries are indexed byte values or
`null` for unknown entries; they do not establish RGB colors or a frame.

Actor names retain a code-relative `pc`, `size` and lowercase hex `bytes`.
The bytes exclude the terminating NUL and are not assumed to be UTF-8.
`{pc: 0, size: 0, bytes: ""}` means no assigned name. An assigned empty name
has a nonzero `pc` and zero size, so the two facts remain distinct. The consumer
checks the supplied bytes and terminator against the immutable kernel.

Verb names have the same source-span representation, with an escape-aware
extent check. Commands after `ff` may include two argument bytes containing
zero. The consumer preserves those encoded bytes without rendering or
substituting variables. It distinguishes absent names after deletion from
assigned empty names, and validates the complete 100-slot inventory when it
is present. An older snapshot remains readable without inventing that inventory;
`qualification.verb_state` records whether the facts were supplied.

Resource availability, logical residency and locking are independent. A declared
slot can be locked without available bytes. Untouched unavailable slots are
implicit in the declared counts. The selected active script must retain its
available, resident code binding. Resource deltas may change residency/locking;
their availability, size and byte identity must remain consistent with the
immutable bank. A costume reference does not establish decoded costume pixels.

The control snapshot includes variables 21, 26, 27, 28, 29 and 38. Cursor and
cutscene records retain their before/after values, but ordinary scalar
instructions can also write these variables. The consumer therefore does not
assert that successive control deltas form their entire history.
`ui_revision` records UI invalidation, not rendered frames or draw calls.
Verb events contain `before_verb`, `after_verb`, `before_ui_revision` and
`after_ui_revision`. An accepted verb operation produces one SCENE record,
even if only the invalidation revision changes. It does not also produce a
second control record. The consumer checks the selected slot, encoded names
and revision increment, without claiming that retained verb rows form a
complete history across disabled or dropped observations.

## DISASM, SCENE and loss

| Mask | Retained evidence when capacity permits |
| ---: | --- |
| `0` | No new observations; current snapshots remain available |
| `1` | DISASM instruction retirements |
| `2` | SCENE committed supported changes |
| `3` | Both, DISASM before SCENE for the same retirement |

The common journal drops new records when full. Every eligible event advances
the global sequence and its channel's eligible count, including dropped events.
Capacity zero is valid and reports all eligible events as dropped.

**Retained sequence numbers need not form a contiguous prefix.** If capacity
fills, records are dropped, and the caller later increases capacity without
clearing, later records can be retained after a sequence gap. The consumer
requires increasing sequences, correct per-channel accounting and gaps bounded
by the reported loss. Per-channel eligibility cannot exceed observer calls,
and observer calls cannot exceed retired instructions. It never repairs a gap or interprets missing observations
as evidence that no effect occurred.

Mask changes preserve retained observations; their control generations remain
attached to each record. Observation clear and restart produce new trace
epochs. The stateless consumer refuses to join event and scene envelopes from
different epochs or current generations. It preserves older record generations
within an otherwise matching journal, without claiming uninterrupted coverage
across them. Disabled intervals, late capture and dropped records do not prevent
use of the current snapshot.

## Static facts, live facts and unsupported boundaries

A successful static row includes exact bytes, encoded operands, fallthrough,
branch target and payload extent. A failed row retains the native fault and
partial descriptor, omits complete instruction bytes, and does not advance the
successful listing cursor. A complete linear listing is not proof that every
instruction was reachable or executed.

Live records preserve resolved values captured during execution. They are not
reconstructed from the final variables. `decoded.next` is the encoded
fallthrough; the top-level `next` is the observed actual successor.
`branch_taken` is a native boolean only for branch instructions. An untaken
conditional may encode an out-of-range target; the consumer only requires a
taken target to be in range. If a static row is supplied for a live PC, their
canonical descriptors and exact bytes must agree.

Faulted or blocked instructions do not become retirements or committed changes.
The endpoint preserves their native status and reason. Recognizing a static
room, walk, print or scheduler instruction does not imply its effect executed.

The packet explicitly leaves these facts unqualified:

- Complete history, including the entire history of the selected control variables.
- Actor visibility or draw order.
- Room background decoding, room transitions and room rendering.
- Costume decoding or animation composition.
- Verb text rendering, mouseover and hit testing.
- Completed screen presentation.

These limits preserve the current native subset. A consumer may build a later
presentation layer using additional explicit resources and policy, but this
packet supplies no invented room pixels, visibility, movement or scheduler state.

## Offline command and verification

The CLI accepts saved captures and writes a new output file, refusing to
overwrite an existing one:

```sh
python3 native/qemu-scumm/processor_scene.py \
  --code /private/script.bin \
  --scene /private/scene.json \
  --events /private/events.json \
  --decode-pages /private/decode-pages.json \
  --output /private/scene-packet.json
```

Both `--events` and `--decode-pages` are optional. `--decode-pages` is a JSON
array of consecutive native pages. Packets can retain original instruction and
name bytes, so use the same private handling as the supplied source captures.

The authored standard-library tests require no emulator or original game data:

```sh
python3 native/qemu-scumm/test_processor_scene.py -v
```

Their 20 test groups cover all masks, zero/full capacity, growth after dropped
records, identity/epoch/counter rejection, palettes and raw names, runtime
resource bindings, scalar writes between control events, exact bytes and
successors, static fault boundaries, blocked room intent, detached outputs and
CLI overwrite refusal. Verb-specific checks include the complete inventory,
escaped and empty names, invalidation-only changes, detached output,
malformed/tampered event rejection and compatibility with older captures.

`test_observation_native.py --case native_scene_consumer` additionally captures
an authored native program through QMP and passes the coherent snapshot,
journal and decode page into this consumer. It verifies eight retirements,
seven committed changes, palette and non-ASCII name bytes, resource residency,
cursor state and unchanged inputs. The snapshot and these retained facts pass;
full-game execution, presentation and history remain unqualified.

`test_verbs_native.py` also passes native verb snapshots and their journal
through this consumer. A packet can then bind the independent, read-only
[room navigation](NAVIGATION.md) planner; neither consumer executes movement.
