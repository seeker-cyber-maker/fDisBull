# Native AGI processor records

The AGI CPU owns instruction decoding and execution. Disassembly, scene
construction and a future UIL emitter consume its instruction facts. This
increment establishes that shared decode seam for the instructions already
modeled by the three experimental native profiles; it does not implement UIL,
additional guest commands or native draw completion.

The same bounded native decoder supplies TCG lowering and the explicit stopped
disassembly query. The existing DISASM channel remains a journal of retired
instructions. Static records can describe a pending or unexecuted instruction
without changing that journal or implying execution.

## Stopped batch interface

Use standard QMP QOM operations on the selected CPU:

| Property | Contract |
| --- | --- |
| `agi-decode-pc` | Host-only starting byte PC, in `0..code_size`; default zero. A caller selects the boundary. |
| `agi-decode-limit` | Host-only maximum instruction records, `1..64`; default 64. |
| `agi-decode-json` | Read one bounded linear decode page from immutable loaded code. |

All operations require the CPU to be stopped. The selectors live outside
architectural state. Selecting or reading a page does not alter guest PC,
retirement, pending effects, run timing/counters, observation generations,
epochs or retained events. Repeated reads are deterministic. Static decoding is
performed on request; no static JSON is produced on the execution path.

The page schema is `fdisbull-agi-native-instructions-1`:

```json
{
  "schema": "fdisbull-agi-native-instructions-1",
  "decoder": {
    "identity": "fdisbull.qemu.agi",
    "version": "1",
    "address_unit": "byte"
  },
  "source": {
    "sha256": "<exact loaded raw-code SHA-256>",
    "size": 4,
    "logic_id": 0,
    "profile": "agi-2917-scalar-position-pilot-1"
  },
  "evidence": "static_decode",
  "traversal": "linear",
  "start_pc": 0,
  "limit": 64,
  "next_pc": 4,
  "stop": "end",
  "instructions": [],
  "error": null
}
```

The example omits instruction rows for brevity; an actual nonempty successful
window includes every decoded row in its contiguous extent. Source has exactly
the identity used by the native state/events, including `catalog_sha256` in
binding profiles. `stop` is `end`, `limit` or `decode_fault`. A fault includes
`pc`, `opcode`, the numeric `code` and native fault `name`; its instruction has
no invented extent or successor and is not appended as a successful row.
`next_pc` is the end of the last decoded row, or the requested start if none.

A page follows encoded lengths even after return or draw. This is a linear
listing, not a reachability proof. A window beginning at an arbitrary caller
PC does not establish that PC as a reachable instruction boundary. Reaching
the byte extent does not establish a complete executable game or CFG.

## Instruction facts

Each successful row has these fields:

| Field | Meaning |
| --- | --- |
| `pc`, `opcode`, `size`, `bytes` | Raw code-relative identity and exact complete encoded bytes. |
| `mnemonic` | AGI command/predicate spelling. |
| `operation` | Semantic operation name; reuse existing names such as `object.position`, `object.set_view`, `resource.load_view` and `object.draw`. This is not a UIL block. |
| `operands` | Ordered typed symbolic inputs and destinations. |
| `conditions` | Ordered IF tokens; empty for other commands. |
| `successors` | Possible static edges; never a replacement for an observed `next_pc`. |
| `effect_class` | `scalar`, `flag`, `control`, `resource`, `actor` or `host`. Declares possible effects, not committed changes. |
| `execution_support` | `native`, `pending_host` or `unsupported_profile`. A supported encoding can still fail runtime preconditions. |

Operands use `role`, `kind`, `width`, `access` and exactly one of `index` or
`value`. Kinds are `variable`, `flag`, `actor`, `view`, `loop`, `cel`, `u8`,
`u16` and `s16`. Variables and flags use `index`; literal actor/resource/ordinal
and immediate operands use `value`. `width` is the logical value width (1 for
flags, 8 or 16 bits). `access` is `read`, `write`, `read_write` or `reference`.
Variable resource/ordinal operands retain kind `variable`, their variable
index and semantic role (`view`, `loop`, `cel`); a final snapshot must not
replace them with alleged historical constants.

IF tokens use `kind` of `predicate`, `or_begin`, `or_end` or `not`, with their
raw byte `pc`. Predicate tokens additionally carry `opcode`, `mnemonic` and
typed `operands`. Conditions preserve order and grouping. Successors use
`kind` (`fallthrough`, `branch`, `true`, `false`), signed integer `pc` and
boolean `in_range`. Out-of-range encoded targets remain visible facts.

The decoder preserves the current native rules: unsigned IF displacement,
signed GOTO displacement, eight predicates and the existing encoded-byte bound,
empty IF admission and empty OR rejection. An invalid IF false target faults
only if that edge is taken. Disabled-profile commands retain their existing
unsupported-opcode precedence during execution. Structural decoding can still
describe a known command from another native profile. Unknown commands and
malformed encodings remain explicit boundaries.

The operation names retain AGI semantics: `scalar.increment` and
`scalar.decrement` saturate at the unsigned-byte limits, while `scalar.add` and
`scalar.subtract` wrap to eight bits. A later UIL emitter must preserve these
differences instead of treating every scalar operation as ordinary integer
arithmetic.

## Scene construction and future UIL

Join static records to native retirement/scene records using the complete
source identity and PC. Native events supply actual control flow, captured
resolved values and committed before/after state. The authoritative pending
descriptor supplies an unretired host request. Keep all three evidence classes
distinct, with journal ordering and loss information intact.

A scene-input planner can derive touched actors, VIEW references, current
bound cels and an actual stopped endpoint from these records and snapshots.
Preview layer order, missing actor flags/priority bands, background choice and
original room-entry assumptions remain explicit policy where the CPU evidence
does not establish them. An authored return produces a bound-layer inventory;
a pending draw additionally identifies the requested actor. Neither implies
native composition or screen presentation.

The host processor adapter reuses the existing `ProcessorInfo`, `Location`,
`DecodedInstruction` and `Successor` seam without parsing AGI opcodes again.
Preserve raw-PC identity and authored/original source mappings separately.
Future UIL emission can consume the native decoded record and existing
continuation/effect vocabulary. No new intermediate instruction language,
TCG-to-UIL conversion or one-trace-to-whole-program claim is introduced here.

## Host consumer

`processor_harness.py` validates page identity and bounds without maintaining an
opcode table. It adapts the records to the existing processor protocol:

```python
from fdisbull.processor import Location, decode_instruction
from processor_harness import NativeAGIProcessor, read_decode_pages

# vm is the existing stopped QMP owner; code is its exact immutable raw input.
pages = read_decode_pages(vm, code, max_instructions=256, page_limit=64)
processor = NativeAGIProcessor(code, pages)
instruction = decode_instruction(
    processor, code, Location(processor.info.address_space, 0))
```

`read_decode_pages` compares the complete native state and retained events
before and after its bounded batch. It never resumes the CPU. Static page
limits or decode faults remain visible to the caller.

`processor_scene.py` joins those records to a complete native capture. Its first
consumer admits a verified straight-line observed prefix and derives the bound
actor inventory, VIEW/loop/cel selection, source mappings and stopped endpoint.
Branches and loops are represented by the processor records but require a later
scene analysis. A complete static listing still does not prove reachability.
Incomplete journals, conflicting identities or disconnected transitions are
rejected. A conflicting legacy actor/VIEW/endpoint label is reported and does
not determine the derived plan.

`processor_scene_trial.py` can query one stopped CPU per detached packet and
produce a portable scene plan, then preview it through the existing Sarien
kernel. The metadata binary and the binary that produced the saved observations
are recorded separately. This workflow does not re-execute the saved fragment
or its containing game. With the source tree on the Python import path:

```sh
python native/qemu-agi/processor_scene_trial.py \
  --binary /private/qemu-system-agi \
  --expected-binary-sha256 EXACT_SHA256 \
  --batch /private/two-packet-policies.json \
  --scene-library /private/libagi-scene.so \
  --expected-library-sha256 EXACT_LIBRARY_SHA256 \
  --output /private/new-processor-scene-batch
```

The batch JSON is an array of one or two objects with `id`, `packet_directory`,
`bands` (168 priority-band values), `actor_policy` (all 16 actor IDs mapped to
explicit `flags` and `priority`) and `draw_order`. The background remains the
packet's explicit choice. Output includes instruction pages, the derived scene
plan, query-neutrality evidence, preview metadata, indexed visual/priority
planes and `scene.png`. Bound actor inventory does not establish that every
actor was drawn in the original game.

## Batched verification

The processor and existing behavior tests use authored bytecode and explicit
native binaries. The processor batch packs static descriptor/error cases into
one input, reuses a child across observation modes and tests coherent scalar,
condition and control-flow behavior. It adds seven native children; the
existing behavior batch adds eight. Detached PQ1/KQ1 metadata reads are a
separate two-child batch with no guest execution.

```sh
FDISBULL_QEMU_AGI_PROCESSOR=/private/qemu-system-agi \
FDISBULL_QEMU_AGI_INTENT=/private/qemu-system-agi \
FDISBULL_QEMU_AGI_EXPECTED_SHA256=EXACT_SHA256 \
  python -m pytest -q tests/test_qemu_agi_processor.py \
  tests/test_qemu_agi_behavior_batch.py
```

These bounded checks qualify the described increment. They do not establish
full opcode coverage, whole-game compatibility or performance measurements.
