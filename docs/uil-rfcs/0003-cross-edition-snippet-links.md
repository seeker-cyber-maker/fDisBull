# RFC 0003: Cross-edition snippet relationships and selectable UDL backings

- Status: **bounded prototype implemented; broader orchestration remains proposed**
- Extends: [Executable Rosetta contracts](0002-executable-rosetta-contracts.md)
- Case study: [Colonization food counterparts](../COLONIZATION_FOOD_EQUIVALENCIES.md)
- Compatibility: existing UIL syntax and meaning remain unchanged

The first implementation is documented in [selectable block layers](../UDL_BLOCK_LAYERS.md)
and the [pilot report](../UDL_LAYER_PILOT.md). Those documents define the actual
schemas, supported execution profiles and qualification limits. The conceptual
requirements below also retain work beyond that first profile.

## Motivation and decision

The DOS and Windows editions of Colonization contain related operations with
different source spans, data bindings and pointer conventions. Repeating an
analysis from scratch loses useful correspondences. Copying a function name or
prototype transfers too much confidence. Retain the relation itself, its domain,
evidence and unresolved differences in the project database.

One UIL operation should admit several versioned UDL implementations. A compiler
can select an eligible original backing as a pass-through or an independently
implemented backing, with explicit adapters at its boundaries. Keeping the UIL
contract fixed permits synthetic output assembled from DOS, Windows and authored
implementations. Such output has its own identity and lineage; exact original
reconstruction remains a separate build profile.

This specializes RFC 0002's multiple-implementation principle into persistent
snippet relationships and explicit compiler selection. UDC names the compiler
and selection path, including the "IDC" selector mentioned in the request.
It introduces no new v1 role, opcode or implicit execution authority.

## What existing evidence supports

RFC 0002 records real native/JavaScript/native handoffs and original-backed and
JavaScript compiler experiments. RFC 0001 also provides redistributable Python,
JavaScript, Rust and unchanged-IL implementations of one synthetic contract.
The latter was rerun for this continuation: 20 backing/case comparisons and five
malformed-input refusals passed, including rejection of a wrong event order.
These experiments establish useful composition mechanisms within their tested
interfaces. They do not establish Colonization snippet interchangeability or a
performance advantage for either edition.

The Colonization case study supplies concrete source-bound correspondence
candidates. Their domains, data state and helper dependencies determine which
local claims can be admitted. A larger function may contain an equivalent
kernel while its surrounding effects remain unresolved.

## Persist identities, relations and their qualification separately

These concepts guide the implementation and its remaining extensions. The names
below are illustrative; use the linked implementation contract for the actual
schema and JSON interchange formats.

| Concept | Minimum retained information |
| --- | --- |
| Snippet revision | Source-file hash, immutable byte-version hash, image view and architecture, decode context, ordered half-open source spans, span hashes and authored boundaries |
| Logical location | NE module and segment index/offset or DOS physical address plus CS context; never treat an NE index as a live selector or DOS paragraph |
| Contract revision | Stable operation identity, UIL revision/digest, typed domain, guards, outputs, state relation, initialization/resource phase, frame conditions and observation profile |
| Correspondence edge | Source and target snippet revisions, relation kind, direction, admitted domain, adapter references, evidence, unresolved differences and author |
| Qualification revision | Method, decoder/model lineage, exact tested inputs or quantified assumptions, counterexamples, unknowns and dependencies |
| UDL implementation | Contract reference, executable closure, source binding, ABI/runtime requirements, resources, dependencies and qualification refs |
| Selection revision | Target profile, requested implementation/layer, explicit tie-breaking, eligible alternatives, rejection reasons and cost evidence |
| Build receipt | UIL and selected implementation digests, adapters, retained resources, tool/runtime identities, emitted artifact hashes and reconstruction/synthetic profile |

Cross-project identities must remain meaningful after copying a database or
moving a file. Local row IDs and host paths can locate retained evidence, but
are not global source identities. An instruction address alone is insufficient.
One-to-many and many-to-one edges must be possible: compilers split, inline,
combine and reorder snippets. Function ownership can remain a candidate.

Use relation kinds that preserve what was established: exact bytes, same data
layout, candidate correspondence, equivalent under a stated contract, refinement
and counterexample. Evidence strength is a separate field: static interpretation,
finite model comparison, bounded proof and original-runtime observation are not
interchangeable. Equivalence in one output projection does not imply full ABI
or effect equivalence. Transitivity requires compatible domains and adapters;
it must not be inferred merely from graph connectivity.

Keep rejected and superseded relations inspectable. A changed source, contract,
helper, alias rule, binding or adapter invalidates the dependent qualification
without deleting earlier revisions. Unchanged bytes do not preserve a claim
whose external dependencies changed.

## UDL block layers with a fixed UIL contract

At a given logical operation, layers contain alternative implementations of
one contract revision. The selected layer provides its backing and qualified
boundary adapters. The UIL node and composition stay the same when meaning
stays the same. A behavior change requires a new contract revision.

Selection should be explicit and reproducible:

1. Choose an exact reconstruction or synthetic build profile and target runtime.
2. Resolve requested implementation IDs against immutable source/contract revisions.
3. Check the input domain, pointer/width rules, aliases, ownership, clobbers,
   entry/exit context, helper/resource closure and ordered effects.
4. Admit only implementations with sufficient qualification for that target.
5. Check output-to-next-input compatibility and adapters between adjacent blocks.
6. Apply the declared selection policy and retain both the choice and rejections.
7. Emit a new artifact/package and lineage manifest; qualify its observable behavior.

An explicit choice should fail with a reason when ineligible. It should not
silently select another implementation or broaden the contract. An automatic
policy can rank eligible alternatives deterministically after qualification.
Unrecovered behavior can retain an admitted original backing and its dependencies.

These alternatives are not the currently implemented native instruction-fetch
[code layers](../CODE_LAYERS.md). Selecting a semantic backing and patching guest
instruction fetch are separate operations with different lifetime and resource
requirements. Neither operation rolls back effects already produced.

## Pass-through and cross-platform adapters

A pass-through preserves an admitted implementation. It does not grant permission
to paste its machine bytes into an incompatible program. The Windows NE backing
requires the appropriate segment environment, far pointers, imports and calling
convention. A DOS backing has different state and runtime dependencies.

A synthetic build can realize a chosen backing through a compatible executor,
a supported lowering, or a compiled module with a qualified adapter. Each route
must declare its capabilities and resulting artifact boundary. Near-to-far
pointer conversion needs a real state binding; it is not integer widening.
The adapter must account for signedness, wrapping, registers/flags, stack and
callee cleanup, ownership, callbacks and all caller-visible effects.

Composition can mix languages and abstraction levels. It requires one declared
state authority or an explicit transfer protocol. A block cannot leave a stale
cached copy for the next language to consume. Ordered writes, failure/refusal,
partial completion, time, randomness and persistence belong to the contract
when observable. A failed block after mutation cannot transparently retry a
different backing as though no effects occurred.

Current DOS UDC capture remains limited to its documented MZ/COM source and
straight-line register semantic profile. This proposal does not make it capture
NE functions, lift branching memory code, orchestrate arbitrary native binaries
or select cross-edition replacements today.

## Compare efficiency after eligibility

The Windows and DOS implementations can be measured after their semantic and
adapter contracts agree. Instruction count alone is not performance evidence.
Include marshaling, runtime transitions, helper calls and resource costs, and
record workload, toolchain, target, clock policy and repeatability. A different
runtime or unmeasured candidate must not receive a fictitious zero cost.

Keep the original-backed baseline available. Faster output that changes the
admitted behavior fails qualification. Synthetic output may deliberately have
a different file hash and implementation mix while preserving the chosen UIL
contract; its receipt must say exactly which claim was checked.

## Small implementation sequence and acceptance gates

1. Add immutable snippet references and authored correspondence edges with
   revision, provenance, dependency and counterexample queries. Demonstrate
   reopen, cross-project identity and byte-version isolation.
2. Add one contract with two candidate UDL backings. Verify a bounded kernel,
   refusing unknown dependencies and preserving its explicit observation boundary.
3. Add explicit selection and adapters for one supported target. An ineligible
   choice, changed contract or stale helper must fail before normal execution.
4. Qualify a synthetic composition with two neighboring blocks. Compare outputs,
   ordered effects, refusal and partial-effect cases against a reference. Change
   a UIL operand and require a changed supported output or a clear refusal.
5. Add measured selection only after the above. Retain exact reconstruction as
   an independently tested profile, with its own file identity requirements.

The first Colonization candidate should be the smallest closed food-staging
kernel supported by both source slices, with helper/resource effects outside
that boundary. Enlarging it to the full production routine requires qualifying
those dependencies and a Windows runtime witness at the declared boundary.
