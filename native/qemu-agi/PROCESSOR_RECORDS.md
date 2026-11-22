# Native AGI processor records

The AGI CPU owns instruction decoding and execution. Disassembly, scene
construction and a future UIL emitter consume its instruction facts. Structural
inspection describes all documented fixed AGI 2.917 actions 0 through 173 and
predicates 0 through 18. The three legacy experimental profiles retain their
smaller execution admission. The explicit `agi-2917-runtime-1` profile uses the
same canonical parser for its resource-backed engine. Adding a descriptor does
not change any profile's execution admission.

The same bounded native decoder supplies TCG lowering and the explicit stopped
disassembly query. The existing DISASM channel remains a journal of retired
instructions. Static records can describe a pending or unexecuted instruction
without changing that journal or implying execution.

## Stopped batch interface

Use standard QMP QOM operations on the selected CPU:

| Property | Contract |
| --- | --- |
| `agi-decode-logic` | Selected immutable LOGIC ID. Runtime packages admit present IDs in `0..255`; legacy raw-code profiles admit only zero. Selecting a LOGIC resets `agi-decode-pc` to zero. |
| `agi-decode-pc` | Host-only starting byte PC, in `0..code_size`; default zero. A caller selects the boundary. |
| `agi-decode-limit` | Host-only maximum instruction records, `1..64`; default 64. |
| `agi-decode-json` | Read one bounded linear decode page from immutable loaded code. |

All operations require the CPU to be stopped. The selectors live outside
architectural state. Selecting or reading a page does not alter guest PC,
retirement, pending effects, run timing/counters, observation generations,
epochs or retained events. Repeated reads are deterministic. Static decoding is
performed on request; no static JSON is produced on the execution path.

The current page schema is `fdisbull-agi-native-instructions-2`:

```json
{
  "schema": "fdisbull-agi-native-instructions-2",
  "decoder": {
    "identity": "fdisbull.qemu.agi",
    "version": "2",
    "address_unit": "byte",
    "encoding": "agi-2.917",
    "decode_policy": "structural-1"
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
window includes every decoded row in its contiguous extent. For legacy raw-code
profiles, source has exactly the identity used by native state/events,
including `catalog_sha256` in binding profiles and `logic_id: 0`.

Runtime decode pages identify the **selected** immutable LOGIC, which can
differ from the currently executing LOGIC:

```json
{
  "sha256": "<selected LOGIC code SHA-256>",
  "size": 42,
  "logic_id": 7,
  "profile": "agi-2917-runtime-1",
  "package_sha256": "<exact UTF-8 package JSON byte SHA-256>"
}
```

Runtime state/event envelopes instead use `source.sha256` for package identity
and `source.logic_id`/`source.logic_sha256` for the current execution LOGIC.
Consumers must compare those explicit identities; the two envelope shapes are
not interchangeable. Runtime records require schema 2. Identical code bytes
in different LOGIC IDs or packages remain distinct address spaces.

`stop` is `end`, `limit` or `decode_fault`. A fault includes
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
| `operation` | Semantic operation name, such as `object.position`, `resource.load_view` or `string.assign`. Current fixed action descriptors are all named; archived catalog records may still say `unmodeled`. This is not a UIL block. |
| `operands` | Ordered typed symbolic inputs and destinations. |
| `conditions` | Ordered IF tokens; empty for other commands. |
| `successors` | Possible static edges; never a replacement for an observed `next_pc`. |
| `effect_class` | `scalar`, `flag`, `control`, `resource`, `actor`, `host` or `unknown`. Declares possible effects, not committed changes. |
| `execution_support` | `native`, `pending_host` or `unsupported_profile`. A supported encoding can still fail runtime preconditions. |

Operands use `role`, `kind`, `width`, `access` and exactly one of `index` or
`value`. Kinds include `variable`, `flag`, `actor`, `view`, `loop`, `cel`,
`picture`, `logic`, `room`, `sound`, `message`, `inventory_object`, `word`,
`string`, `controller`, `u8`, `u16` and `s16`. Variables and flags use `index`;
literal actor/resource/ordinal and immediate operands use `value`. Schema-2
`string` and `controller` operands also use `value` for their encoded 8-bit
slot identity, retaining their native read/write/reference access. They are
not resolved text or a historical controller state. Archived schema 1 retains
its original operand kinds. `width` is the logical value width (1 for
flags, 8 or 16 bits). `access` is `read`, `write`, `read_write` or `reference`.
Variable resource/ordinal operands retain kind `variable`, their variable
index and semantic role (`picture`, `logic`, `view`, `loop`, `cel`, etc.); a final snapshot must not
replace them with alleged historical constants.

IF tokens use `kind` of `predicate`, `or_begin`, `or_end` or `not`, with their
raw byte `pc`. Predicate tokens additionally carry `opcode`, `mnemonic` and
typed `operands`. Conditions preserve order and grouping. `said` exposes its
encoded `word_count` followed by that many ordered 16-bit `word` references;
structural counts from 0 through 255 are described without evaluating the
stateful predicate. Successors use `kind`, signed integer `pc` and
boolean `in_range`. Ordinary kinds are `fallthrough`, `branch`, `true` and
`false`. `assumed_return` is a call's possible local continuation if its callee
returns. `assumed_fallthrough` retains a conservative encoded continuation
without asserting that a control command's eventual outcome reaches it. External
LOGIC targets are typed references, not byte addresses in the current source.
Room changes have no local successor. Out-of-range encoded targets remain
visible facts.

The decoder preserves unsigned IF displacement, signed GOTO displacement,
empty IF admission and empty OR rejection. Structural inspection admits up to
1,024 encoded bytes and 64 predicates, at most 256 condition tokens, seven
action operands and 1,024 aggregate condition operands per instruction.
Its catalog describes the fixed action encodings from 0 through 173 and
predicates 0 through 18. In legacy profiles, `trace.on` remains a named
contextual-layout boundary. The explicitly selected runtime profile adopts
the nominal AGI 2.917 zero-operand form, consuming exactly its opcode byte.
Unknown commands, malformed encodings and structural limits retain explicit
fault boundaries.

The three legacy execution profiles still admit only the existing 29-command
union, predicates 1 through 7, eight predicates per IF and the prior 64-byte
bound. An invalid IF false
target faults only if that edge is taken. Disabled commands retain their
unsupported-opcode precedence, including before operand truncation or actor
validation. Structurally known unsupported predicates still produce the
existing condition fault during execution. The two policies share the parser;
static recognition is not executable support or full interpreter compatibility.

The runtime profile uses the broader canonical framing bounds and its own
execution support resolver. `native` and `pending_host` records describe that
resolver's contract; they do not establish a successful execution, accepted
resource, completed host service or whole-game compatibility. A typed `call`
retains its LOGIC reference and assumed local return; the host adapter does not
invent a callee byte address from the encoded resource ID.

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
opcode table. It accepts archived schema-1 pages and current schema-2 pages,
and rejects mixed decoder identities within one processor artifact. It adapts
the records to the existing processor protocol:

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

For a `QemuAGIRuntime` owner, use its captured package bytes and explicit
per-LOGIC source:

```python
logic_id = 7
code = vm.logic_code(logic_id)
page = vm.decode(logic_id, pc=0, limit=64)

# The existing batch reader and Processor adapter work without a new decoder.
pages = read_decode_pages(
    vm, code, source=vm.logic_source(logic_id),
    start_pc=0, max_instructions=256, page_limit=64)
processor = NativeAGIProcessor(code, pages)
instruction = decode_instruction(
    processor, code, Location(processor.info.address_space, 0))
```

`vm.decode` selects `agi-decode-logic`, `agi-decode-pc` and `agi-decode-limit`,
then delegates validation and complete state/event neutrality checks to the
same batch reader. It accepts present resources even when execution has not
loaded them. Its private immutable code capture is authoritative; mutating the
public package metadata cannot substitute code. The runtime QMP client limits
retained event batches to 4,096 so neutrality checks fit its 32 MiB transport
bound; larger retained batches are refused before event serialization.

The scene-specific consumers below retain their separate pilot capture
contracts. Runtime page acceptance by the common Processor adapter does not
also qualify runtime event envelopes for those scene planners.

`processor_scene.py` joins those records to a complete native capture. Its first
consumer admits a verified straight-line observed prefix and derives the bound
actor inventory, VIEW/loop/cel selection, source mappings and stopped endpoint.
Branches and loops are handled separately by the
[static scene-discovery consumer](SCENE_DISCOVERY.md). A complete static listing
still does not prove reachability or an observed scene.
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
condition and control-flow behavior. It adds nine native children; the
existing behavior batch adds eight. The discovery test adds one stopped child
for its packed structural and graph cases. Complete PQ1/KQ1 LOGIC metadata
reads are a separate two-child batch with no guest execution.

```sh
FDISBULL_QEMU_AGI_PROCESSOR=/private/qemu-system-agi \
FDISBULL_QEMU_AGI_INTENT=/private/qemu-system-agi \
FDISBULL_QEMU_AGI_EXPECTED_SHA256=EXACT_SHA256 \
  python -m pytest -q tests/test_qemu_agi_processor.py \
  tests/test_qemu_agi_behavior_batch.py tests/test_qemu_agi_discovery.py
```

The runtime processor suite uses two authored native children. One package
holds all 174 action encodings and all 19 predicate encodings across multiple
LOGIC IDs, including IDs containing identical bytes. A separate program
exercises strings, key/controller binding, a cross-LOGIC call and a pending
print while verifying inspection neutrality:

```sh
FDISBULL_QEMU_AGI=/private/qemu-system-agi \
FDISBULL_QEMU_AGI_EXPECTED_SHA256=EXACT_SHA256 \
  python -m pytest -q tests/test_qemu_agi_runtime_processor.py
```

These bounded checks qualify descriptor/consumer contracts and the authored
execution paths. They do not establish whole-game compatibility or performance
measurements.
