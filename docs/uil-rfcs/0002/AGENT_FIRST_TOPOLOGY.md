# Agent-first UIL: branching recovery routes and language-neutral meaning

**REVISION IN PROGRESS. Discussion draft, 30 October 2026.**

This companion extends [RFC 0002](../0002-executable-rosetta-contracts.md).
It publishes design questions for other investigators without fixing a new UIL
schema, changing production behavior, or declaring a winning analysis provider.
The [verification companion](RESEARCH_AND_VERIFICATION.md) covers dataflow,
execution history and hierarchical invariant learning. The [editable route
map](pipeline-map.mmd) is a conceptual topology, not measured performance.

## 1. The destination is meaning, not a compulsory pipeline

The reference route is source -> executable UDL -> shared UIL -> UDC -> target.
It is a useful "Sacred Timeline" for orientation, not the only permitted route.
C, ASM, guest bytecode, Z-like scenes, graphs and tensors are views or sources at
appropriate levels. None must become a compulsory intermediate representation
for every region of every program. In particular, Z is neither Z-machine nor a
requirement to turn a continuous simulation into a turn-based adventure.

The enduring object is a versioned behavioral blueprint plus retained support:
executable backings, source bindings, contracts, relationships and unresolved
questions. UDL and UIL share vocabulary; UDL retains executable source
implementations. UDC can initially reuse those implementations, later replace
individual ones, or combine several languages and runtimes. Adding an analysis
provider must not turn UDL back into disposable pseudocode.

There are two legitimate entry routes. Recovery starts from existing artifacts
and observations. Authored UIL starts from explicit behavior definitions without
an original executable. Guide-derived drafts can seed recovery, but their
claims remain hypotheses until qualified. An executable conjecture simulator
must not be confused with original-backed execution.

### Reading the map

The amber route is the architectural reference. Blue branches are optional
analysis routes; dashed connections indicate proposed adapters or qualified
handoffs, not installed integrations. A C-like view can rejoin through typed
facts or executable UDL. Direct guest-bytecode recovery can bypass native
interpreter decompilation. Dynamic observations feed the same evidence graph.

The convergence gate admits claims at their declared scope. It does not make
three agreeing tools a proof, and does not block an admitted opaque backing
merely because its high-level meaning is incomplete. Conflicts and unknowns
remain attached to the blueprint. The evidence graph joins information; it is
not a new mandatory executable language between UDL and UIL.

The proof path checks relationships beside the route. It does not insert a
mandatory whole-program solver run between every pair of blocks. Alternative
target routes can share a linker or runtime, but byte-identical reconstruction
and equivalent generated behavior are distinct destinations.

## 2. Compose analysis capabilities, not decompiler brands

The present `udl_blocks.py` path at fDisBull commit
`85503c0e895842424faa7db62f020b879d08568a` checks a small x86-16 straight-line
reader against Capstone and renders a restricted assignment/add/subtract view.
It is not a general Capstone-to-C decompiler. It has no modeled memory,
control flow, observed flags or ABI. Its adequacy for an earlier fixture does
not establish that it is the best general recovery path. [S1]

| Provider or route | Useful contribution | Integration boundary / question |
| --- | --- | --- |
| fDisBull + Capstone | Source bytes, instruction/operand facts, retained analysis and existing bounded lifts | Keep cheap supported work local; instruction facts alone do not supply a complete transition model. |
| Binary Ninja | LLIL/MLIL, SSA definitions and uses, possible-value constraints | Preserve IL level, SSA version, source location and before/after position. Possible values and reaching definitions answer different questions. [S2] |
| Ghidra | Raw p-code, analyzed high p-code, decompiler dataflow and slices | Retain the distinction between direct instruction translation and analysis-introduced nodes. A simple slice is not complete alias/call/control closure. [S3] |
| IDA with Hex-Rays | Microcode, use/definition sets, ctree and pseudocode | Keep may/must facts and microcode maturity. IDA disassembly alone is not a guarantee of an available licensed Hex-Rays backend. [S4] |
| Hopper | A further ASM/pseudocode/scriptable investigation route | Adapter capability and host/license availability need checking; pseudocode is not automatically compilable or equivalent. [S5] |
| Game processor or resource adapter | Direct VM operations, script dispatch, objects, resources | Often answers a game-rule question more directly than decompiling its native interpreter. Qualify the selected VM profile. |
| Native/runtime tracing | Concrete reads, writes, branch outcomes and loaded-resource identities | Witnesses concern recorded executions; do not silently turn them into all-path facts. |
| LLM or guide scaffold | Names, candidate structure, possible invariants and useful next questions | Retain origin and uncertainty; synthesis is not the acceptance authority. |

REA's official repository is `morluto/rea`. Its inspected README at
`8f920bb65b8d8ae669411501b0a3a59a62883ac3` describes providers including Hopper,
Ghidra and IDA (also Kuna). This demonstrates an agent-facing provider approach,
not verified semantic fusion of those engines or a benchmark ranking. [S6]

A proposed capability broker should ask for an operation such as decode, obtain
def-use facts, resolve a call, slice an effect, or render a C-like explanation.
Select a provider per question and supported target, not permanently per stage.
An example route is Ghidra p-code -> Binary Ninja range hypothesis -> native
witness -> shared binding -> executable UDL. This is a proposed exchange, not a
claim that their internal IRs are directly interchangeable today.

Each response needs source/resource and byte-view identity; address space;
provider/adapter version and analysis settings; semantic level; fact modality
(exact decoding, may, must, observed, inferred); dependencies; and unresolved
boundaries. Provider-generated names are aliases, not global identities.
Reconcile facts only after establishing what source operation/state they refer
to. Retain incompatible claims instead of taking a majority vote. Two tools
using the same decoder or copied annotations are not independent witnesses.

Choose providers by a measured workload objective: supported architecture/VM,
correctly recovered dependencies, unresolved frontier, machine and agent time,
context volume, correction work, licensing/deployment cost and reproducibility.
Cold project creation and warm queries must be measured separately. Query a
second provider when it can settle a disagreement or unlock work, not for every
instruction by default. No provider tournament was executed for this revision.

## 3. Separate meaning, encoding and placement

UIL should not require a variable to have an address, a stack slot, a C type
name or a preferred implementation language. A useful model distinguishes a
value, a stateful entity/cell, a reference to an entity, and a concrete storage
binding. These are conceptual distinctions, not proposed mandatory class names.

| Property | Semantic UIL responsibility | UDL binding / UDC realization |
| --- | --- | --- |
| Identity and relations | Stable logical identity; equality/aliasing where meaningful; producer/consumer links | Source locations, object resolvers, emitted symbols and concrete handles |
| Value domain | Bool, bounded/unbounded integer, bits, enum, reference, collection or extension-defined domain | Machine representation and carrier; a wider carrier may preserve a smaller domain |
| Width and sign | Specify when wrapping, bounds, bit tests or signed comparison are observable | Storage width, register width, sign-extension and boxing |
| Arithmetic | Overflow, saturation, rounding, exceptional results and units | Instructions, library operations and checked adapters |
| Shape and granularity | Collection dimensions/index domain, element type, units or resolution | Dense/sparse layout, packing, strides and allocation |
| Constancy | Immutable value versus read-only access versus state invariant | Const qualifier, readonly pages or optimization choice only when justified |
| State and effects | Reads/writes, ownership/alias relationships, ordering, lifetime and permitted failures | Memory ownership, borrowing, synchronization and calling convention |
| Encoding / endianness | Required when external bytes or bit ordering are part of the observable contract | Otherwise chosen at the source/target encoding boundary |
| Placement | No ordinary address required | Address allocation, alignment, stack/register assignment, segments and relocations |

An abstract integer has no byte endianness. A file field decoded as a
little-endian 16-bit value does. Similarly, numeric precision, collection element
size and atomicity are different meanings of "granularity" and should not be
collapsed into a single vague property. Size plus signedness cannot alone
capture ownership, units, overflow, equality of references or effect ordering.

For example, a state field can mean "an unsigned value in 0..255, updated with
modulo-256 addition" without requiring C `uint8_t`, Rust `u8`, JavaScript
`Number`, a CPU register, or a contiguous byte of storage. These are candidate
realizations. At a byte-oriented external interface, encoding becomes explicit.
Do not remove address arithmetic or self-inspection that is actually observable;
retain such behavior in an appropriate capability or source-backed residual.

WIT is a useful precedent for language-neutral component interfaces, including
records, variants and resources, but explicitly does not define behavior. UIL
must retain the behavioral part that an interface-only description lacks. [S7]

## 4. Functions are contracts and regions, not necessarily machine functions

Represent an operation by its identity, arguments/results, admitted state,
relations, ordered effects, exits, and optional hierarchical body. A backing is
separately bound to an entry/exit cut, executable dependencies and an adapter.
An inline native region may require live registers and a continuation; it need
not be given a fabricated RET to fit a function abstraction.

One operation may use multiple fragments; one fragment may implement several
qualified views. A pure composite, coroutine, state machine, process, dataflow
region or source-backed opaque operation should not be forced into a C ABI
function. Calls, callbacks, suspension, exceptions and recursion retain their
behavior even when the target implements them differently.

An agent can factor a repeated region into a candidate composite or expand one
into smaller operations. The graph records what changed and which observations
would distinguish a wrong abstraction. Existing executable backings can remain
in use while this interpretation develops. Pattern recognition proposes a
boundary; source/contract checks admit the replacement. Recovered function
boundaries and useful new abstraction boundaries need not be identical.

## 5. Graphs, vectors and tensors without a new implementation prison

An exact typed graph is a suitable reference description. Vectors/tensors may
encode its adjacency, batches, values or transition relations. Require a defined
mapping back to exact identities, labels and ordering where these matter. A
lossless sparse encoding is different from a learned embedding: embeddings can
retrieve candidates but similarity does not establish executable equivalence.

A loop can be described without a machine jump:

```
state_0 = initial_state
while guard(state_k):
    (state_next, ordered_events) = step(state_k, input_k)
    state_k = state_next
```

Equivalent views may include a scan, fold, tensor recurrence, relation or
structured region. The description still needs the initial state, iteration
relation, stopping/progress behavior, effects and exceptional outcomes.
The future UDC can implement it with jumps, vector instructions, GPU kernels,
actors or another qualified mechanism. A tensor container alone supplies none
of those semantics. Encoding an arbitrary loop as a huge transition tensor may
also be much less useful than keeping its compact generative description.

Vectorization is a target decision only when dependencies and the observation
contract permit it. Floating-point reassociation, loop-carried state, aliasing,
early exit, I/O and callback order cannot be silently discarded. Semantic
recurrence does not imply parallel execution. A nonterminating game loop needs
progress/event semantics, not a fabricated finite result.

Modern compiler work already offers reusable pieces: MLIR describes extensible
operations, nested regions and dataflow graphs, while its tensor and structured
control-flow dialects have different semantics. We can borrow these mechanisms
without declaring MLIR, LLVM, SSA or tensors the mandatory UIL serialization or
the ultimate semantic vocabulary. [S8]

## 6. UDC is a build and runtime orchestration plan

The UDC may select native/ASM for one operation, generated Rust/C for another,
and JavaScript for another. It may combine libraries and providers. Distinguish
the language used to implement the compiler definition, the emitted artifact,
and the runtime that executes it. They need not be the same.

Connections are part of the plan: value conversion, bounds, ownership, borrowing,
copying, async completion, exception/panic translation, state ownership and
resource access. Do not pass a Rust Vec layout as a JavaScript array layout.
Coalesce compatible regions and account for boundary overhead instead of making
a foreign-function call for each semantic primitive. Correctness determines
eligibility; measured end-to-end cost selects among eligible implementations.

### Target scaffolds: ELF, PE, DOS and beyond

A scaffold is a versioned target recipe, not a fixed empty executable into which
arbitrary bytes can safely be poured. It supplies entry/startup/exit behavior,
link rules, sections/segments, imports, relocations, runtime services, resource
packaging and ABI adapters. The UDC fills it with compatible objects, generated
code or retained closures, then the linker/packager finalizes the image. [S9]

Keep container, ISA, ABI, operating environment and services separate. An ELF
label does not make a Windows fragment run on Linux. A PE DOS stub does not make
the whole PE a DOS program. DOS COM, real-mode MZ and extender/LE profiles need
different loaders and memory rules. Host JavaScript does not become available
inside DOS unless the selected plan supplies an interpreter, a lowering or an
explicit bridge, with its consequences accounted for. An unsupported target may
retain an admitted native runtime or refuse that build, not invent one.

Scaffolds can emit a package with several runtimes, not only a monolithic file.
An exact-reconstruction profile must also retain original layout/opaque content;
a semantic-generation profile may have different bytes. Both need declared
artifact and observation boundaries. Conventional ABI/loader rules need not
shape the UIL core, but generated output must obey the rules of its chosen
execution environment. Novel targets can define different realization profiles.

## 7. Agent-first means inspectable choices, not weaker semantics

The agent should be able to query meaning, expand a composite, compare backing
options, propose a rewrite, inspect a counterexample and ask why a choice is
unsupported. Keep immutable revisions, small results with expandable evidence,
transactional graph edits, explicit dependency invalidation and reproducible
build selections. A graphical editor and an agent operate on the same semantic
program; presentation layout is not executable control flow.

Allow rich names and prose as helpful descriptions, but bind execution to
explicit definitions. The map analogy is useful: crayons, ink and an island can
realize the same specified shape. A contract must say which shape properties
matter; a rough map from memory is a candidate, not a unique specification.
Agents' recollection is not an evidence store. Persist identity and provenance.

The stable part should be the meaning of an adopted definition and the rules for
connecting/revising definitions, not a permanently frozen list of primitives.
New concepts can be registered under versioned definitions with domain, effects,
meaning, required capabilities and conformance examples. They can lower to known
operations, provide qualified backings, or remain explicit unknowns. Unknown
required behavior must not be executed as a successful no-op. Discovery and
hypothesis storage stay permissive; accepted execution remains precise.

This is semantic discipline without mandating the metaphorical ink. Do not
silently change the meaning of an old opcode to accommodate a new concept.
Do not silently import C undefined behavior or CPU layout into every abstract
value. Existing strict v1 documents and execution authority remain unchanged.

## 8. Open questions for the next discussion

1. Which minimal value/state/effect interfaces belong in the core, versus
   operation-definition libraries? No final schema is selected here.
2. How should exact graph identity survive equivalent reorderings, renaming and
   patch-local revisions while retaining meaningful event order?
3. What assurance is required to reuse a backing, a new lowering, or a cross-tool
   binding? Retained original behavior and recovered meaning remain distinct.
4. Which provider comparison uses equal cold knowledge and accepted scope?
   Suggested cases: aliasing, merged definitions, unknown calls, VM dispatch,
   looping state and a known patch, not only attractive C output.
5. Which minimal target scaffold should demonstrate mixed C/Rust/ASM first?
   Existing authored JS/C results are not new ELF/PE/DOS portability tests.
6. Which loop is genuinely suited to a tensor/scan view, and which observation
   contract permits changing its execution schedule?

A first pilot should compare capability routes on the same authored/held-out
slices and return qualified facts, explicit differences and costs. Keep one
mutating controller per live guest; schedule independent analysis questions
rather than one permanently idle agent for every representation.

## Sources and verification status

Primary documentation inspected on 30 October 2026. Tool versions and adapters
must be pinned when executing a trial; these links do not constitute a trial.

- S1: [fDisBull bounded reader](https://github.com/seeker-cyber-maker/fDisBull/blob/85503c0e895842424faa7db62f020b879d08568a/src/fdisbull/udl_blocks.py); [Capstone operand access](https://www.capstone-engine.org/op_access.html).
- S2: [Binary Ninja SSA API](https://dev-api.binary.ninja/binaryninja.mediumlevelil-module.html), development documentation, and [C++ MLIL API](https://api.binary.ninja/cpp/group__mediumlevelil.html). The stable Python page timed out during this review; availability was not tested in a licensed runtime.
- S3: [Ghidra p-code](https://ghidra.re/ghidra_docs/languages/html/pcoderef.html), [additional operations](https://ghidra.re/ghidra_docs/languages/html/additionalpcode.html), [slice API](https://ghidra.re/ghidra_docs/api/ghidra/app/decompiler/component/DecompilerUtils.html).
- S4: [Hex-Rays representations](https://python.docs.hex-rays.com/ida_hexrays/index.html), [may/must use/definition lists](https://python.docs.hex-rays.com/classida__hexrays_1_1mblock__t.html).
- S5: [Hopper FAQ](https://www.hopperapp.com/faq.html). No Hopper dataflow API parity claim is made.
- S6: [REA pinned README](https://github.com/morluto/rea/blob/8f920bb65b8d8ae669411501b0a3a59a62883ac3/README.md).
- S7: [WIT interfaces](https://component-model.bytecodealliance.org/design/wit.html).
- S8: [MLIR language reference](https://mlir.llvm.org/docs/LangRef/), [tensor](https://mlir.llvm.org/docs/Dialects/TensorOps/) and [structured control flow](https://mlir.llvm.org/docs/Dialects/SCFDialect/).
- S9: [Microsoft PE/COFF](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format), [ELF program loading](https://gabi.xinuos.com/elf/07-pheader.html), [existing DOS UDC profile](../../UDC_DOS.md).

This is a design/documentation increment. No provider tournament, new semantic
compiler, scaffold runtime, tensorized game, cross-tool exchange or game run was
executed. Earlier fixture receipts retain their original dates and scope. The
phrase "UCL" in the discussion did not resolve to a specific project during
reference lookup; no additional dependency or acronym definition is inferred.
