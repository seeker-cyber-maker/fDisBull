# Shared static analysis

The advanced analysis layer consumes a context-aware instruction graph and
normalized instruction facts. The same passes operate on x86 and ARM64 data;
file formats supply mapped bytes and metadata rather than separate analysis
algorithms. These are bounded static analyses. They neither execute a binary
nor establish complete instruction semantics, source-language functions or
runtime behavior.

## Current support and extension boundary

| Layer | Current implementation | Extension point |
| --- | --- | --- |
| Native decoding and CPU-to-IR adapters | x86 in 16/32/64-bit modes; little-endian ARM64 in 64-bit mode | Add an adapter that emits the same instruction, expression and transfer records |
| Graph and data-flow passes | Context-aware node IDs, explicit edges, normalized expressions and supplied snapshot readers | Another ISA or container can reuse the passes after providing those facts |
| ABI descriptions | x86 near/far 16-bit cdecl; x86 32-bit cdecl/stdcall/fastcall/thiscall; x86-64 System V and Win64; AArch64 AAPCS64 and Darwin integer-register arguments | Supply an explicit compatible ABI profile |
| Typed data | Explicit little-endian scalar, pointer, array and structure layouts over mapped bytes | Define named layouts; this does not add a CPU decoder |

Supporting a decoding mode does not mean every instruction has a mathematical
IR transfer. Unsupported effects remain unresolved or clobber affected values.
There is no universal CPU, vendor, microcode, exception or timing model.
Managed CIL analysis remains a separate metadata/CIL facility.

## Common facts and evidence

An instruction node has an exact `id`, an address, context, size and flow kind.
Edges identify source and target IDs; context is part of identity, particularly
for DOS segment aliases. Do not merge nodes solely because their physical
addresses match. Call and fallthrough edges have different meanings.

`semantics.instruction_semantics(raw, address, arch, bits, cs=None)` produces
JSON-compatible transfers. Expressions include:

```json
{"op":"const","value":8192}
{"op":"reg","name":"rdx","symbol":"entry:rdx"}
{"op":"add","args":[{"op":"reg","name":"rbp"},{"op":"const","value":-8}]}
{"op":"load","address":{"op":"const","value":8192},"width":2,"signed":false}
```

Assignments and stored values read the instruction's pre-state, so exchanging
two registers does not become two sequential Python assignments. Assignment
widths are in bits; memory widths are in bytes. Frozen register symbols denote
earlier values and cannot be rebound to a later value of the same register.
DOS memory expressions retain segment and offset arithmetic, including
address-size masks. Unknown DS/ES values remain unknown.

Results retain evidence and assumptions. A candidate target or function is not
silently promoted to an observed fact. A budget stop retains a frontier or
partial status; convergence means only that the supplied abstract problem has
stopped changing. It does not imply that every code region or runtime target
has been found.

## Six passes

| Pass | Public API | Result and boundary |
| --- | --- | --- |
| Candidate function membership | `function_analysis.function_membership(nodes, edges, entries, max_work=1_000_000)` | Many-to-many instruction/block membership, contiguous runs, shared tails, overlapping entries, tail-call candidates and unresolved frontiers. Follows supplied intraprocedural edges; excludes call targets. Labels and other entries do not imply exclusive ownership. |
| Values and branch guards | `flowdata.analyze_flow(nodes, edges, entry_id, semantics_by_id, initial=None, read_memory=None, abi=None, max_steps=100000)` | Incoming/outgoing states, feasible edges and retained guard bounds. Joins discard conflicting values and guards that do not survive every incoming path. Unknown writes/calls invalidate affected knowledge. Loops converge conservatively or stop with an explicit budget result. |
| Frames and ABI observations | `frames.analyze_frame(snapshot, semantics_by_id, flow_result, abi=None)` | Logical entry-SP offsets, stack access widths, frame-pointer relations, pre-call argument-location candidates and return/cleanup observations. These are not recovered source variables or proven signatures. |
| Bounded indirect transfers | `indirect.recover_indirect(snapshot, semantics_by_id, flow_result, read_memory, is_executable, max_entries=256)` | Candidate targets from normalized indirect expressions, with table slots, widths, index/bound evidence, load values and rejection reasons. Expands finite state or guard-bounded indices; performs no unbounded pointer scan. Requires caller-owned native-decoder validation before admission. |
| Explicit structural types | `typesystem.type_layout(name, registry)` and the project's `define_type`, `apply_type`, `types`, `typed_data` methods | Validated layouts and versioned user interpretation of mapped bytes. Field/array names resolve from shared physical identity. This does not infer a structure from nearby accesses or prove its semantic role. |
| Library identities and call effects | `summaries.match_signatures`, `resolve_summary`, `instantiate_effects` | Qualified identities plus concrete, bounded or unresolved caller memory effects. Metadata, registered signatures and confirmed prototypes retain separate evidence. An arbitrary label supplies no contract. |

### Membership and frames

Membership is computed independently for each requested entry. Shared code can
belong to several candidate functions. An unconditional transfer to another
candidate entry can be reported as a tail-call candidate while reachability
continues; that heuristic does not settle ownership. Missing stored branches
and missing fallthroughs remain visible. The pass never decodes missing code.

Frames use the solver's pre-call states. `calls[].argument_values` is an ordered
expression list; `calls[].arguments` also records each candidate location,
index and value. Register and stack locations come from an explicitly chosen
ABI profile and observed stack cells. With no profile, compatible alternatives
remain available rather than silently selecting a calling convention.
`signature_known` stays false. Argument count, floating-point/vector arguments,
variadic classification and complete ABI compatibility are not inferred.
Mach-O ARM64 defaults to `aarch64_darwin`; its packed stack arguments and
variadic layout require type evidence and are not inferred using AAPCS64 offsets.

### Snapshot reads and indirect targets

`read_memory(address, width)` supplies immutable snapshot bytes. The flow
solver also tracks abstract stores and suppresses stale snapshot reads when
an intervening write may alias; an unknown call can taint that knowledge.
This is not a runtime memory oracle.

The indirect pass requires a stable, non-budget-stopped flow result and graph
before producing target candidates. Guard evidence is tied to the same frozen
index value used by the table expression. A guard on only one incoming path
cannot bound a merged dispatch. Unknown indices, incomplete data flow,
unmapped/truncated slots, zero/out-of-range targets and non-executable mappings
are reported explicitly. The table-evaluation budget is global across the
requested transfers. A mapped executable target still needs native decoding
and context validation by the coordinator.

A guard on an expanded memory-derived index can remain an unresolved proposal
even when its finite range is clear in the disassembly. For example, loading an
index from memory, subtracting a constant, checking a bound and then scaling it
can lose the register identity required by the current guard matcher. The pass
does not guess DS or enumerate the registers inside that earlier load. Recovering
such cases requires value identities that distinguish the guarded load from a
later reload after mutation; that extension is not implemented in this release.

### Library and memory contracts

`builtin_signatures()` supplies four **authored fixture** helper bodies:
byte-loop `memcpy` and `memset` for x86-64 System V and ARM64 AAPCS64. Their
real bytes are useful narrow examples, not universal compiler or vendor-library
fingerprints. Matching requires the complete supplied contiguous body, explicit
architecture/bits and equal byte length. The caller remains responsible for
supplying the whole function. Registered byte masks allow only whole-byte
wildcards, each covered by an explicitly declared relocation range.

`resolve_summary(name, source=...)` requires qualified evidence of kind
`import`, `export`, `exact_signature` or `user_confirmed`. A name alone returns
no summary. Known contracts cover `memset`, `memcpy`, `memmove`, `read`, `write`,
`fread` and `fwrite`. Metadata identity remains conditional on that symbol
actually implementing the named contract. A user-supplied prototype/effect
contract requires `user_confirmed` evidence; a prototype alone adds no inferred
memory effects. Arguments have explicit names, ordered indices, types and roles.

Platform adapters identify declared slots and code stubs; the shared linkage
pass joins these with normalized call expressions. It never reads an unresolved
GOT/dyld cell as an external function address. Call effects retain
`binding_evidence`, including whether the static state excludes an intervening
write to the slot. If that proof is false or unknown, the declared identity is
still useful for investigation, but its effects remain conditional on the
binding being unchanged. Competing unknown identities prevent contract selection.

`instantiate_effects(summary, arguments, state=None)` accepts named arguments,
positional expressions or a frame call record. It returns half-open byte ranges
where address and size are known, retains unresolved expressions otherwise,
and can use symbol-matched guard bounds for potential ranges. It never reads or
writes the indicated memory. For example, a 12-byte `memset` at `0x2000`
describes `[0x2000, 0x200c)` on normal completion. A `fread(ptr, 2, 6, stream)`
describes a possible write of **0..12 bytes**, not proof of a complete read.
`fwrite`/`write` read their caller buffers; they do not write those source bytes.

Negative or overflowing lengths and address-width overflow produce diagnostics
and no memory facts. Known overlapping `memcpy` ranges violate its non-overlap
contract; no defined copy effect is asserted. `memmove` allows overlap and
retains its snapshot-copy semantics. These memory summaries do not model every
register, flag, exception, stream-internal operation or system side effect.
Generic semantic copy/fill-loop recognition is not implemented: the current
automatic helper identification is exact registered byte matching.

### Structural data types

Types describe an interpretation of retained bytes. Built-in signed/unsigned
integers are available at 8, 16, 32 and 64 bits. User layouts can define scalar
storage, 2/4/8-byte pointers, arrays and structures with explicit offsets and
total size. Pointer spaces include flat addresses, near pointers with an
optional explicit segment, and four-byte DOS `far16` offset/segment pairs.
Unspecified near-pointer segments remain unresolved.

Validation rejects by-value recursion, out-of-range fields, overlapping fields,
overlapping bindings and bindings outside a single mapped region. Pointer
recursion is allowed. Field names propagate through shared labels and views;
the underlying binary bytes and raw operand evidence are retained. Defining a
type is an authored hypothesis, not a claim that the binary's original source
used that declaration.

## Runnable Python example

This example decodes a short x86-64 caller, derives its argument values through
the shared IR and frames, and applies a separately supplied import identity.
The bytes contain an illustrative call instruction; no target code is run.

```python
from fdisbull.decoder import decode
from fdisbull.semantics import instruction_semantics
from fdisbull.flowdata import analyze_flow
from fdisbull.frames import analyze_frame
from fdisbull.summaries import resolve_summary, instantiate_effects

# mov edi,0x2000; mov esi,0x1234; mov edx,8; call next; ret
data = bytes.fromhex("bf00200000be34120000ba08000000e800000000c3")
nodes, semantics, offset = [], {}, 0
while offset < len(data):
    row = decode(data[offset:], 0x1000 + offset, "x86", 64)
    row.update(id=f"caller:{row['address']:x}", context="x86:64:little")
    nodes.append(row)
    semantics[row["id"]] = instruction_semantics(
        bytes.fromhex(row["bytes"]), row["address"], "x86", 64)
    offset += row["size"]
edges = [dict(source=a["id"], target=b["id"], kind="fallthrough")
         for a, b in zip(nodes, nodes[1:])]
flow = analyze_flow(nodes, edges, nodes[0]["id"], semantics)
snapshot = dict(nodes=nodes, entry=nodes[0]["id"],
                context="x86:64:little", arch="x86", bits=64)
frames = analyze_frame(snapshot, semantics, flow, abi="x86_64_sysv")
summary = resolve_summary("memset", source={"kind": "import", "module": "example"})
result = instantiate_effects(summary, frames["calls"][0])
effect, = result["effects"]
assert (effect["address"], effect["size"], effect["fill_byte"]) == (0x2000, 8, 0x34)
assert not result["runtime_observed"]
```

## Coordinator integration

The project coordinator owns persistence, invalidation, queues, target admission
and repeated passes. The pure APIs above do not mutate a project or enqueue
code themselves. New evidence can require another graph/data-flow pass; a
pending queue or exhausted pass budget must not be reported as a stable project.
User names, representations, type definitions and summary revisions retain
their authored provenance rather than replacing the original bytes.

The coordinator's command surfaces are `auto-analyze`, `function-analysis`,
`function-membership`, `define-type`, `apply-type`, `types`, `typed-data`,
`set-summary`, `summaries`, `add-signature`, `signatures` and `call-effects`.
Exact command arguments and coordinator limits are defined by each command's
`--help` and the project API; these pure-pass interfaces do not promise an
unbounded whole-program analysis.

Related evidence and boundaries are documented in
[the architecture](ARCHITECTURE.md), [the API](API.md),
[decoder research](DECODER_RESEARCH.md) and
[the DinoPark field audit](DINOPARK_FIELD_AUDIT.md).
