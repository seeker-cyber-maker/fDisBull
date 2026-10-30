# Z-machine processor module

`ZMachineV3Processor` exposes Zork's source bytecode through fDisBull's existing
[processor interface](PROCESSOR_MODULES.md). It decodes instructions, preserves
their original facts, describes variable references, and supplies explicit
control-flow successors. Bounded linear and recursive queries make those facts
available through the CLI and JSON protocol.

This module is a static source inspector. The [executable IR](ZORK_UIL.md) and
the separate [game-intent UIL with UDL definitions](ZORK_INTENTS.md) remain
unchanged. Processor facts can supply evidence for further recovery; they do
not themselves recover puzzles, parser intent, turns, or named game actions.
See the [verification report](VERIFICATION-ZMACHINE-PROCESSOR-2026-10-29.md) for
the tested source identities, comparisons, and remaining limitations.

## Inspect an owned story

For the qualified Zork I release 88 story, inspect the opening-handler entry:

```sh
fdisbull zmachine-disasm /private/ZORK1.DAT \
  --address 0x8089 --max-instructions 20

fdisbull zmachine-analyze /private/ZORK1.DAT \
  --entry 0x8089 --max-instructions 1000
```

`zmachine-disasm` reads a source-order slice. It retains both alternatives of a
conditional branch and the destination of a call, but continues its listing at
the next encoded instruction. It stops at an unconditional jump, return, halt,
restart, restore, decode error, or budget boundary. This prevents a listing
from silently treating the data following a terminal instruction as code.

`zmachine-analyze` follows candidate static successors from its selected roots,
including both conditional alternatives and direct routine entries. It also
follows call continuations under the explicit assumption that a callee returns.
It deduplicates attempted starts and reports unresolved transfers, decode
errors, conflicting spans, and pending work. It does not sweep every byte or
infer dynamic call targets from initial global values.

Omitting `--address` or all `--entry` arguments selects the original initial PC.
Repeat `--entry` to supply multiple roots. Explicit roots name **instruction
entries**, not routine headers; for example, `0x8089` is the instruction entry
corresponding to the separately identified mailbox routine header `0x8084`.
These numeric examples apply only to the cited release; use qualified offsets
for another story.

The default instruction budgets are 40 for a linear slice and 10,000 for
recursive analysis. Both accept integer budgets from 1 through 100,000. A
recursive request accepts at most 256 supplied roots, then deduplicates them.
Both queries also bound aggregate admitted instruction spans to 8 MiB. A budget
is an analysis limit, not an execution-step count or a coverage claim.

Output can contain original source bytes and encoded story text. Keep captures
and byte-retaining reports in private locations outside Git. Large replies may
use the core output-artifact protocol; the
[agent quickstart](AGENT_QUICKSTART.md#retrieve-a-large-response) explains how
to retrieve the existing response without rerunning analysis.

## Python processor API

```python
from fdisbull.processor import Location, decode_instruction
from fdisbull.zmachine_processor import ZMachineV3Processor

processor = ZMachineV3Processor.from_file("/private/ZORK1.DAT")
location = Location(processor.info.address_space, 0x8089)

instruction = decode_instruction(processor, processor.program, location)
if instruction is not None:
    print(instruction.facts["mnemonic"], instruction.facts["op_str"])
    for edge in instruction.successors:
        print(edge.kind, edge.target, edge.evidence)
```

The constructor also accepts immutable `bytes` directly:
`ZMachineV3Processor(story_bytes)`. `from_file` reads the file once with a size
bound, qualifies those bytes, and retains that same snapshot. Replacing the
original path later does not alter an existing processor. Pass its own
`processor.program` object back to the dispatcher; a different object is
rejected even if it was obtained from the same path.

The descriptor identifies `fdisbull.zmachine.v3`, adapter contract version `1`,
byte address units, and the capabilities `decode` and `static_successors`.
`state_schema` is `None` because the processor does not model live machine
state. Its address space has this form:

```text
zmachine.v3.sha256:<full-original-file-SHA-256>
```

The digest includes any trailing file padding. Two files with identical
declared images but different padding have distinct source identities. All
locations and resolved successors belong to that source space. Their offsets
are story-byte coordinates, never DOS interpreter addresses or native project
addresses. `story_info` returns an independent metadata dictionary; editing it
does not change source qualification or decoding.

Higher-level query functions are available separately:

```python
from fdisbull.zmachine_analysis import analyze_story, disassemble_story

listing = disassemble_story("/private/ZORK1.DAT", address=0x8089,
                            max_instructions=20)
analysis = analyze_story("/private/ZORK1.DAT", entry_points=[0x8089],
                         max_instructions=1000)
```

The analysis layer owns traversal and dispatches decoding through the same
processor seam. It creates no project database and persists no analysis queue.

## Standalone JSON methods

The methods work without a project and remain standalone inside a retained
session that has a default native project:

```json
{"id":"opening-listing","method":"zmachine-disasm","params":{"path":"/private/ZORK1.DAT","address":"0x8089","max_instructions":20}}
```

```json
{"id":"opening-graph","method":"zmachine-analyze","params":{"path":"/private/ZORK1.DAT","entry_points":["0x8089"],"max_instructions":1000}}
```

`address` and entries may be integers or numeric strings such as `"0x8089"`.
The CLI `--entry` option maps to the JSON `entry_points` array. A successful
protocol response wraps the analysis in `result`; `ok: true` means that the
query returned successfully, not that its graph is complete. Check the inner
`status`, `complete`, `complete_scope`, `issues`, and unresolved-transfer fields.
Malformed requests and unsupported source files return ordinary protocol errors.

## Instruction facts and successors

Every instruction preserves the existing raw decoder fields: `offset`, `op`,
`operands`, `end`, `bytes`, and any `store`, `branch`, or `text_offset` field.
Operand kinds and their encoded values are retained exactly. Added fields
include:

| Field | Meaning |
|---|---|
| `mnemonic`, `size`, `flow` | Normalized name, full encoded span, and control-flow classification. |
| `op_str` | Readable operands, store destination, branch polarity, and inline text span where applicable. |
| `operand_details` | Literal versus variable-number role, statically named variables, and unresolved runtime references. |
| `operand_evaluation` | `left_to_right`, preserving the source operand evaluation order. |
| `store_variable` | Stack, local, or global destination of an encoded store byte. |
| `call` | Packed address, routine header, entry, local count, initial locals, and qualification status. |
| `jump` | Signed displacement and calculated target for an immediate unconditional jump. |
| `return_value` | Literal return value when available, otherwise `null`. |

Variable zero denotes the evaluation stack; variables 1 through 15 denote
routine locals; variables 16 through 255 denote globals. Global annotations
include their table offsets, but no current global value is inferred. A local
reference records `exists_in_current_frame: null` because a standalone decoder
does not know the caller's frame.

The distinction between value reads and indirect variable references matters.
An ordinary operand reading `sp` pops its value. An immediate indirect
reference to variable zero reads or updates the top item in place. If the
variable-number operand itself is encoded as a variable, its value is read
first, then that runtime result selects the referenced variable. The module
records that reference as unresolved instead of substituting an initial value.
See the standard's [operand rules](https://inform-fiction.org/zmachine/standards/z1point1/sect04.html)
and [stack and indirect-reference rules](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html).

Each successor has `kind`, `target`, and `evidence`. A resolved `target` is a
`Location`; an unavailable destination is `None` in Python and `null` in JSON.
This is a candidate source destination, not proof of an executed instruction.

| Source operation | Successor contract |
|---|---|
| Conditional branch | Preserve polarity, target alternative, and encoded fallthrough. Offsets 0 and 1 become caller-dependent returns. |
| Direct call | Multiply the packed address by two, validate the local-count/default-value header, and target the first instruction after it. Retain an assumed return continuation. |
| Call to packed address zero | No callee edge; local continuation records the immediate false return. |
| Variable call or jump | Keep the transfer unresolved; no initial-value propagation. |
| Immediate jump | Use `instruction.end + signed16(operand) - 2`; no local fallthrough. |
| Routine return, including `print_ret` | Retain a return edge with an unknown caller continuation; no local fallthrough. |
| `quit` | Halt with no successor. |
| `restart` | Transfer to the original initial PC with an explicit state-reset explanation. |
| `restore` | Successful restoration has an unknown saved continuation. Only failure follows the false outcome of the local encoded branch. |

Packed calls name headers, not instruction entries. A header count from 0
through 15 is followed by that many two-byte initial local values, so the entry
is `header + 1 + 2 * local_count`. Call facts distinguish `routine_candidate`,
`null_routine`, `unresolved_variable`, and `invalid_routine_header`. Invalid
headers and out-of-image destinations retain evidence with unresolved edges.
The module does not establish routine ownership or validate all instructions
inside a candidate callee.

The restore exception prevents a misleading local control-flow graph: a
successful restore resumes the saved game elsewhere, while a failed restore
obeys the false result and the encoded branch polarity. `save` retains both
local outcomes. These rules follow the standard's
[opcode definitions](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html).

## Interpret traversal status

Both query results use format `fdisbull-zmachine-analysis-1` and explicitly
state `representation: source_instruction_facts`,
`runtime_reachability_proven: false`, and `game_intent_recovered: false`.

| Mode and status | Interpretation |
|---|---|
| Linear: `control_flow_boundary` | The listing reached an unconditional transfer or termination. |
| Linear: `end_of_story` | The listing reached the declared image end. An out-of-image continuation can still make the result incomplete. |
| Linear: `decode_error` | The requested next start could not be decoded under this profile. |
| Either: `instruction_budget` | The instruction-attempt budget was exhausted. The result is incomplete. |
| Either: `byte_budget` | The aggregate admitted-span bound stopped the query. The result is incomplete. |
| Recursive: `static_worklist_drained` | The selected static queue drained without reported issues or unresolved transfers other than caller-dependent returns. |
| Recursive: `partial` | The queue drained, but decode errors, overlaps, or unresolved transfers remain. |

Linear results have `complete_scope: requested_linear_slice_only` and expose
`next_offset` where applicable. Recursive results have
`complete_scope: requested_static_worklist_excluding_caller_dependent_returns`.
They expose `worklist_drained`, pending `frontier` entries with their origins,
`return_sites`, and `routine_candidates`. Caller-dependent returns remain in
the instruction edges and return-site list; they are explicitly excluded from
the static completion scope rather than guessed.

Recursive traversal reports overlapping instruction spans and overlaps between
candidate instructions and known candidate routine headers. It retains the
conflicting interpretations as evidence. A drained queue with such an issue is
not complete. Call-derived routine records remain classified as candidates,
with their supporting call sites; they are not promoted to verified functions.

Even a complete static worklist says nothing about untaken runtime paths,
current RAM, dynamically selected callees, feasible conditions, or whole-game
coverage. The byte budgets and candidate roots define the query's scope.

## The mailbox example and the three layers

For Zork I release 88, the earlier source-backed recovery independently
identified mailbox-opening routine header `0x8084`, two zero-initialized locals,
and instruction entry `0x8089`. That instruction entry is a valid explicit root
for inspection when used with that source identity; the header is a separate
source structure.

The original dispatcher calls through the evaluation stack at `0x586d`, stores
its result in local variable 4, and resumes at `0x5871`. There is no literal
packed-address call to this mailbox routine in the preserved mapping. The new
processor therefore leaves this callee unresolved. Knowledge from a qualified
runtime binding is separate evidence; it is not silently supplied to static
decoding.

Inside the opening handler, the direct call at `0x80ee` has packed address
`0x472c`. The processor identifies routine header `0x8e58`, six default locals,
and instruction entry `0x8e65`, with continuation `0x80f4`. That is a concrete
source call fact. Interpreting its role in listing the container's contents
requires the separate source-backed recovery described in
[ZORK_INTENTS.md](ZORK_INTENTS.md).

The resulting separation is:

| Layer | Responsibility |
|---|---|
| Z-machine processor | Original instruction encoding, operand references, and static control-flow facts. |
| Preserved executable IR | Ordered low-level semantics that retain the original game's behavior for the standalone consumer. |
| Game-intent UIL and source UDL | Named recovered interaction rules and their guarded relationship to original operations, with explicit residual IR. |

Adding this processor changes the first layer's inspection interface. It does
not rename low-level operations into game intent or expand the existing bounded
intent-recovery claim.

## Supported input and explicit limits

Input must be a raw version-3 story with the supported declared-length,
checksum, memory-layout, and table bounds. Recognition uses content rather than
the filename. Other Z-machine versions, container extraction, and early v3
stories without the supported header fields are outside this profile. The
bounded input reader accepts at most 512 KiB including padding; the declared
v3 image is constrained by the format's length field and 128 KiB limit.

Decoding is confined to offsets from 64 up to the declared image end. A direct
decode request in the header fails; a request at or beyond declared EOF returns
`None`, including offsets in padding. Truncated instructions, unsupported
opcodes, illegal operand counts, and constant indirect variable numbers outside
the byte range raise errors. Static queries retain decode failures as issues
and continue other queued alternatives when possible.

The high-memory mark is metadata, not an unconditional code floor: historical
stories can contain routines below that mark. See the standard's
[memory map and packed-address rules](https://inform-fiction.org/zmachine/standards/z1point1/sect01.html)
and [routine layout](https://inform-fiction.org/zmachine/standards/z1point1/sect05.html).

No VM execution, debugger state, image rendering, arbitrary guest-project
persistence, or native `.fdb` import is provided by this module. No plugin
discovery or automatic code loading is added; processor objects are supplied
explicitly to the trusted in-process interface. Platform and behavioral
verification remain scoped to the accompanying evidence.
