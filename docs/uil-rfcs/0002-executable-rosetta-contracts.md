# RFC 0002: Executable Rosetta contracts, patch propagation and polyglot UDC

- Status: **draft architectural principles; not an adopted runtime or format**
- Author: ChatGPT, formalizing TiGa's executable UDL, UIL blueprint and UDC requirements
- Date: 30 October 2026 (America/Montreal)
- Reviewed repository: `70eb4e38bf4bf8d47e52e38b8fab6a6cd718f15e`
- Core compatibility: existing `fdisbull-il-1`; no new opcode, role or schema identifier
- Extends: [RFC 0001](0001-shared-intents-and-compiler-definitions.md)
- Supersedes: none; existing execution, qualification and ownership boundaries remain

## 1. Decision and semantic limitation

Treat the system as an **executable Rosetta Stone**: a network of qualified
correspondences between values, operations, compositions and implementations.
`IV` and `4` can denote the same integer; native code, C, JavaScript or Rust can
implement the same operation. Spelling and implementation language are not its
meaning. Correspondence is established by a contract, not by matching names.

The missing architectural connection is not another decompilation stage. It is
retaining executable UDL backings, deriving an initial UDC from them, and updating
those correspondences incrementally when code or the editable blueprint changes.
The desired product is a manipulable program, not only a description of a binary.

The principles are:

1. Preserve working source implementations while recovering their meaning.
2. UDL and UIL share syntax; their direction and backing authority differ.
3. Make the contract the common identity, with versioned implementations on both sides.
4. Derive original-backed output from retained UDL implementations before demanding a rewrite.
5. Keep one editable hierarchical blueprint; text, diagrams and player views are projections.
6. Permit mixed abstraction levels and mixed implementation languages.
7. Qualify connections and composition, not just individual blocks.
8. Use patches as guarded implementation substitutions and dependency-local updates.
9. Preserve residual executable behavior rather than fabricate missing semantics.
10. Distinguish exact reconstruction, semantic equivalence, refinement and lossy presentation.
11. Promote recurring patterns into reusable composites only after checking their interfaces.
12. Reuse established evidence, while rechecking facts whose dependencies changed.

These principles do not require every language pair to have an independent
translator. A new backend can add implementations of common contracts. It still
has to support the required subset and adapters; there is no automatic universal
language coverage.

[Sweding](../SWEDING.md) names the realization freedom within these contracts:
reuse or create a backing with different machinery while preserving original
observable effects, action responses and timing. Missing a target-language
primitive does not alone require a UIL amendment. Explicitly justify and agree
comparison exclusions/tolerances; an underspecified contract cannot silently
weaken the original behavior. Bounded matching evidence leaves untested coverage
unknown. This guidance adds no runtime or schema.

## 2. Terminology and responsibility

| Term | Meaning in this proposal |
| --- | --- |
| UDL | User-Defined Language: shared block structure connected to retained executable source backings, their state/ABI adapters and source evidence. Not merely a decompiler description. |
| UIL | Universal Interaction Language: the common typed operation contracts and editable composition. A recovered program can contain semantic and explicitly residual blocks together. |
| UDC | User-Defined Compiler: definition selection, lowering, code retention/generation, linking and orchestration that realize the blueprint for a target profile. |
| Backing | An immutable executable implementation or executable closure with dependencies and a declared entry/exit context; not necessarily a standalone function. |
| Contract | The admitted behavior of an operation, including state, ordered effects and relevant environment assumptions. |
| Adapter | A versioned implementation of a connection between block representations or runtimes. Its conversions and effects are also qualified. |
| Blueprint | The shared program plus definition references, connections, unresolved frontier and bound evidence/backing inventory. Not only player-visible prose. |

Three identities remain distinct: stable logical operation/node identity,
immutable contract revision, and immutable backing/source-binding revision.
One contract can have several implementations. One implementation can support
multiple qualified views. Role labels and friendly names cannot establish these
relations; changing meaning creates a contract revision.

The existing [shared IL](../INTERACTION_IL.md) uses the same syntax and evaluator
for `udl` and `uil`; changing role is metadata. It does not execute native code
because a document says `udl`. Native execution requires an explicitly selected,
qualified companion backing and executor. **Do not introduce a `udc` role or
hide executable authority inside v1 evidence.**

The [DOS UDC](../UDC_DOS.md) already retains original blocks under its narrow
profile. This RFC does not widen that profile or change its qualification gates.
The [UIL ownership boundary](../UIL_BOUNDARY.md) also remains: general target
compilers, visual editors and downstream runtimes are separate products unless
adopted in another reviewed change.

## 3. Contracts on both sides of the blueprint

For an operation `b`, let `K` describe its input domain, types, state relation,
entry guards, reads/writes/aliases, exits, frame conditions and ordered events.
An observation profile `O` specifies relevant timing, randomness, exceptions,
partial completion, services and persistence. Include caller-visible registers
or flags when the source context can observe them. Exclusions must be explicit.

For related initial states and the same admitted input/environment, the intended
qualification is:

```text
observe_O(run(source_backing_b))
    = observe_O(run(UIL_definition_b))
    = observe_O(run(target_implementation_b))
```

The final states must also satisfy the declared state relation. This is an
obligation to establish within a domain, not a theorem implied by the diagram.
For deterministic blocks compare ordered traces and outcomes. For nondeterminism
specify the allowed trace sets and scheduler/RNG assumptions; trace inclusion is
refinement, not automatically equivalence. A bounded terminating test does not
establish behavior on divergence or outside the tested domain.

Local agreement composes only when output states satisfy the next block's entry
conditions, adapters preserve meaning, and ownership, aliasing, interference,
continuations and effect order are compatible. A hidden shared write or callback
can invalidate an otherwise plausible composition. Keep one authoritative state
owner or an explicit synchronized ownership/transfer protocol, not independent
simulations that happen to share labels.

An opaque backing can preserve behavior in its established original context
without having a recovered high-level meaning. Keep that preservation claim
separate from a claimed semantic implementation. Unsupported paths must remain
explicitly unsupported or use an admitted residual executor, never a successful
no-op. Unknown dependencies do not become pure because their names are missing.

## 4. Round trips and the initial UDC

Given original code `B`, source recovery returns shared structure `U` and retained
support `S`: backings, source maps, context adapters, layout and resource closure.
The initial UDC can be derived by retaining/selecting those same implementations:

```text
B --executable UDL mapping--> (U, S) --original-backed UDC--> B'
```

For the exact-reconstruction profile require `B' = B` over a declared artifact
boundary. The retained support carries details that the readable blueprint need
not expose. Without those bytes/layout/resources, exact reconstruction cannot be
assumed. Preserve license and redistribution constraints on retained content.

For a portable backend `C_t`, require `C_t(U)` to agree with `U` under its declared
contract. Output can be a program package containing several runtimes/modules,
not necessarily one file. Compilation must report unsupported operations before
a normal complete build is accepted. Explicit partial builds remain partial.

Exact reconstruction and semantic recovery are different checks. A compiler that
copies a subtraction block while labelling it addition can round-trip bytes and
still misdescribe the program. A compiler that ignores an edited UIL operand
also fails the contract. Require semantic sensitivity controls: a changed operand
must change supported generated behavior or be rejected for lacking a backing.
An unsupported edit may not silently select the closest-looking implementation.

For newly authored UIL, there may be no original UDL side. Its meaning comes from
explicit definitions and composition; supported UDCs implement it. Source
recovery and programming are two entry routes to the same blueprint.

## 5. Patch-first propagation

When an applicable patch is available, use its guarded transformation rather
than rediscovering correspondence through two whole-binary analyses. Preserve the
base identity, expected bytes/signature, ordered edits and resulting identity.
Distinguish installer operations, added assets, native instructions and VM
resources. A patch is authoritative about its specified transformation, not proof
that its comments or intended gameplay outcome are correct.

Let `P(B0) = B1` be the checked patch transformation. Let `U0/S0` and `U1/S1`
be the corresponding shared representations and executable backing inventories.
Original-backed profiles must satisfy:

```text
C0(U0, S0) = B0
C1(U1, S1) = B1 = P(B0)
```

These equations constrain the middle; they do not uniquely infer it. The
behavior-changing pre/post programs are not claimed equivalent to each other.
Each representation is checked against its own revision.

Initially, applying a patch can replace an affected executable UDL backing while
preserving its identity and connections when the interface remains compatible.
A narrowed or changed interface requires re-admission of connected blocks.
An already independent abstract implementation must be updated or invalidated;
swapping its old source backing does not magically update its generated code.
A still-opaque block can remain executable through an explicit revised backing
without waiting for complete high-level recovery.

Propagate invalidation from changed instructions through relevant control/data
flow, helpers, aliases, contracts, compiler selections and derived projections.
Unchanged bytes can be reused while an unchanged caller's transitive behavioral
claim needs rechecking. Separate semantic change from binding-only relocation.
Overlapping layers require declared ordering and conflicts must be detected.
Reanalysis stops at a justified dependency boundary, not necessarily at the last
written byte. Whole-binary matching remains useful when correspondence is absent.

Use two qualification routes where feasible: recover `U1` from the actual
patched source, and propagate the change through existing `U0/S0`. Compare their
supported meaning as well as exact patched bytes. Shared decoder assumptions
must be recorded rather than advertised as independent evidence.

Native instruction-fetch overlays and interpreted-resource overlays are not
interchangeable. A VM reads its bytecode as data. Resource layers require pinned
resource identity, a qualified current resolver and rebinding on reload/restore;
see [code layers](../CODE_LAYERS.md). Disabling a layer does not roll back state
changes caused while it was active; A/B execution needs compatible checkpoints.

### The two-handler to three-handler example

The authored fixture retains unrelated work before and after the decision:

```text
before += 7                 (u16 wrapping)
number = 3*x + 7             (u8 wrapping)
PRE:  number < 128 -> lower; otherwise -> higher_or_equal
POST: number < 128 -> lower; number == 128 -> equal; otherwise -> higher
Each handler writes its outcome and increments calls once.
after += 11                 (u16 wrapping)
```

The former higher-or-equal implementation remains valid for the higher branch.
Only the decision backing and a new equality backing change. The UIL delta is
that branch split; surrounding operations and existing handlers remain shared.
One generic JavaScript UDC can compile both revisions. An original-backed UDC
requires the revised decision/equality definitions and must reject unsupported
semantic edits instead of emitting a preselected reference answer.

## 6. Address abstraction and multiple levels

ASM, C-like code and Z are optional analysis/presentation levels, not a mandatory
ladder. Input can reach executable UDL from native code, guest bytecode or a
higher-level view. Different regions can remain at different abstraction levels.
Z is not the Z-machine and a public Zork-like observation is not the whole private
blueprint. Retain the private rules and bindings when producing public narration.

Abstract a register/address when its observable role is preserved by the
contract and backing. Keep aliases, object/storage identity, lifetimes, numeric
width, read timing, scopes and meaningful pointer arithmetic. A local variable
and an object property are not equivalent solely because they contain the same
integer. Unresolved pointer behavior stays residual or explicitly unsupported.

Progressively reduce definitions to a declared semantic primitive set, but retain
the hierarchy and opaque executable dependencies. There is no requirement to
flatten every program to bits or invoke a foreign runtime for each primitive.
Conversely, recovering a domain label is not permission to delete lower-level
behavior that the model has not accounted for.

A real-time game such as Doom is a prospective capability test, not an excluded
genre: contracts may need ticks, input ordering, fixed-width arithmetic, RNG,
collisions, resource services and rendering callbacks with logical effects.
A text view is optional; removing graphics must not remove simulation. Retained
original-backed execution and fully portable reconstruction are separate
milestones. No Doom support is demonstrated by this RFC.

## 7. Polyglot UDC and qualified connections

A UDC can select compiled C/ASM for one block, JavaScript for another, and Rust
or another implementation for a third. The definition's authoring language,
emitted language, target ISA and runtime are separate axes. Selection can operate
at composite granularity rather than one language for the entire program.

The common value contract need not impose identical internal layouts. For `u8`,
require the integer domain `0..255`, with distinct wrapping, checked or saturating
operations. A wider carrier is permitted if it preserves values exactly. The
experiment's JavaScript scalar carrier is a Number, not an eight-bit scalar;
its local vector uses Uint8Array. Validate inputs before coercion.

Every connection declares:

- value encoding, width/sign, range checks, endianness and numeric conversion;
- record/list layout, length, ownership, borrowing, mutation, lifetime and aliasing;
- calling convention, continuation, errors/traps, cancellation and partial effects;
- runtime/ABI/toolchain identities, synchronization and allowed services.

Copying a scalar, borrowing a buffer and sharing memory are different contracts.
A JavaScript object is not a C array or Rust Vec layout. Adapter qualification
must include malformed inputs and effects on both sides. Interoperability does
not follow merely from both languages having a similarly named type.

The prototype sequence is:

```text
C:  a = (3*x + 7) mod 256
JS: v = Uint8Array([a, k]); b = (v[0] + v[1]) mod 256
C:  result = b XOR 165
```

The common `u8` contract survives each boundary. The vector remains JS-private;
this example establishes no shared-buffer lifetime or Rust interoperability.
Node-API supplies the actual in-process C/JS bridge in the prototype [R3]. Other
ABI/FFI mechanisms are possible; the canonical ABI is a design precedent [R2],
not an adopted dependency.

Correctness eligibility precedes cost. Include transfers, allocations, runtime
startup, synchronization and adapter calls when choosing an implementation.
Measure cold and warm behavior separately and distinguish build/qualification
cost from execution cost. Batch or fuse compatible operations when beneficial.
No language is intrinsically the fastest, and many tiny valid crossings can be
slower than one larger implementation. No speedup is claimed here.

## 8. Visual programming and emergent composites

UIL is a canonical structured program that humans can edit visually and agents
can edit directly. Layout coordinates are presentation metadata, not control
flow. Typed sockets, sequencing/state connections, guards, effects and capability
requirements determine whether a composition is meaningful.

A visual block can expand into smaller blocks, select a qualified original
backing, or select a supported target implementation. Editing and serialization
must preserve stable node identities, definitions and ordered dependencies.
A UI cannot change the meaning of the same serialized blueprint silently.
The analogy is an executable construction kit: recover components from a program,
assemble or modify the blueprint, and compile through selected definitions.

Pattern recognition, repeated structure, dataflow cohesion and hierarchical
grouping can propose new functions/composites. Complexity alone is not proof of
a useful boundary. Establish live inputs/outputs, side effects, captured state,
exit conditions and environment assumptions; then check replacement equivalence.
New composites need not match the original programmer's function boundaries.

If a composite expands into already supported primitives, a UDC can compile the
expansion without a bespoke backend rule. A qualified optimized backing is an
alternative. Track the dependency graph so a primitive/contract change invalidates
affected composites. Hierarchical grouping is not runtime recursion; actual
recursive calls need explicit stack, termination/divergence and effect behavior.

Learning adds candidates, counterexamples and qualifications as immutable
revisions. It does not silently rewrite pinned programs or promote a discovered
pattern to verified meaning. This is a proposed capability, not a claim that
automatic function discovery has been implemented. Multi-level operations and
nested regions in MLIR provide a related design precedent [R1].

## 9. Evidence, loss accounting and orchestration

Use precise result categories, without adding new production status enums:

| Claim | Required distinction |
| --- | --- |
| Exact artifact reconstruction | Identity over the declared bytes/resources/layout; not automatically all process state. |
| Semantic equivalence | Matching admitted behavior under an explicit state/trace observation contract. |
| Refinement | One-way restriction of permitted behavior; do not label it symmetric equivalence. |
| Executable preservation | Retained original behavior in a qualified context, possibly still opaque. |
| Projection | A selected view that can omit private state; not a lossless simulation/save by default. |
| Candidate | Guide-derived or inferred behavior with unresolved correspondence; not an executable fact. |

A hash binds identity, not meaning. A successful parser, round trip, source-port
match or test against one's own draft does not independently prove semantics.
Finite tests cover their stated inputs. Bounded solver checks retain their
models, assumptions and unresolved results. Timing, RNG and external effects
cannot be excluded silently and then claimed preserved.

Maintain one revisioned evidence/dependency graph, not independently interpreted
worlds per exporter. Guides and rough code skeletons seed hypotheses/checklists;
ordinary play supplies observations and discriminating questions. Neither route
automatically establishes code-backed meaning. A conjecture simulator remains
separate from accepted recovered behavior. Preserve contradictory annotations
and refinements rather than first-description-wins merging.

Parallel workers may investigate independent mechanisms or representations, but
consume pinned evidence revisions and publish dependency deltas. One controller
owns mutation of a live guest; independent runs use explicit isolated state.
Measure discovery, waiting, propagation and rework, not just artifact export.
Reusing accepted contracts and refreshing a stale runtime observation are different
operations. HUD/agent snapshots remain selected observations, not full checkpoints.

## 10. Capability, compatibility and security boundary

This principles RFC reserves no extension ID and introduces no executable syntax.
All examples above are explanatory notation, not new valid v1 operations. Future
schemas must declare required capabilities; unsupported required operations,
adapters or runtime services must be rejected rather than approximated silently.
Partial/residual execution requires an explicit profile and honest coverage.

A companion definition/catalog can bind backings and adapters without changing
the strict shared-IL envelope. Both UDL and UDC use the same versioned semantics.
Keep v1 role metadata, arithmetic, pending-host behavior and evidence validation
unchanged. Definitions, receipts and outputs retain separate immutable identities.

Code-backed does not mean automatically authorized. Imported UIL is untrusted
data. Only explicitly registered and selected compiler definitions/executors may
load native code, run host-language modules or access declared services. Content
hashes do not grant permission. Preserve build/runtime capability separation,
resource bounds, source licenses and private game assets. A trusted in-process
C addon test is not a hostile-code sandbox qualification.

## 11. Conformance requirements and implementation experience

The [evidence companion](0002/README.md) records two authored prototypes and fresh
replays. They support bounded feasibility, not automatic recovery or a universal
compiler. The [literal vectors](0002/vectors.json) are design fixtures, not a new
UIL format. Their arithmetic can be checked independently; the following broader
acceptance cases remain requirements unless separately demonstrated.

| ID | Case | Required result |
| --- | --- | --- |
| R01 | IV and 4, or two integer encodings | Same admitted value with explicit codecs; no inference from names alone. |
| R02 | UDL/UIL role change | Shared meaning unchanged; native execution still requires backing authority. |
| R03 | Unchanged original-backed reconstruction | Exact declared image and resources; residual regions retained. |
| R04 | Two handlers become three | Patch, UDL revision, UIL delta and both UDC routes agree; unrelated blocks reusable. |
| R05 | UIL equality result changes 30 to 31 | Generative backend changes behavior; fixed-backings backend rejects absent implementation. |
| R06 | Reordered same instruction multiset | Dataflow/order analysis detects changed behavior; no equivalence from a bag of opcodes. |
| R07 | Layout-only address change | Binding updates without semantic edit only when correspondence is established. |
| R08 | Unknown alias/helper or storage-scope change | Preserve/residualize or reject; do not silently erase dependencies. |
| R09 | C to JS to C u8 path | Typed intermediate/final values agree; invalid inputs reject before coercion. |
| R10 | Shared/borrowed collection crosses runtimes | Ownership, bounds, lifetime and mutation protocol checked separately from scalar success. |
| R11 | Unchanged caller invokes patched callee | Retain caller bytes, invalidate affected transitive qualification. |
| R12 | Patched interpreter resource reloads | Re-resolve correct resource/epoch; reject stale address authority. |
| R13 | Collapse then expand a composite | Same admitted state/effect trace and dependencies; no label-only acceptance. |
| R14 | Visual edit and agent edit of same blueprint | Same canonical program; presentation layout alone has no semantic effect. |
| R15 | Return to baseline for A/B trial | Restore relevant state, not merely disable the patch layer. |
| R16 | Unsupported required primitive/backend | Explicit refusal or declared residual route; never success by ignoring it. |
| R17 | Timed or randomized workload with text view | Preserve declared ticks/input/RNG/effects; no automatic pause between agent turns. |
| R18 | Wrong adapter or stale backing definition | Reject or expose a counterexample even if component tests individually passed. |

Incremental delivery: preserve executable mappings and exact backings; pin
contracts and adapters; implement dependency-local patch propagation; add one
portable compiler and mixed-language connections; then add visual composition
and qualified abstraction discovery. Each increment has its own evidence and
independent consumer intake. Do not delay useful supported blocks until a whole
game, language or abstraction hierarchy is recovered.

## 12. Alternatives and disposition

A mandatory ASM-to-C-to-Z pipeline adds unnecessary gates and excludes workloads
that need time/process semantics. Two full independent binary analyses waste
known patch correspondence, but remain a valid fallback. Byte pass-through alone
preserves implementation without establishing meaning. High-level rewrites alone
lose the executable reference. One target language per UDC is simpler but should
be a supported deployment choice, not an architectural restriction.

The chosen design retains executable reference components, editable common
contracts and target-specific implementations together. It permits a semantic
primitive foundation and higher-level reusable structure without choosing one
privileged programming language as truth.

Disposition: **draft**. Review must settle concrete companion schemas, supported
contract/adapter profiles, composition checking and integration ownership before
runtime adoption. This PR formalizes the principles; it does not merge a compiler,
visual editor, automatic discovery system or new game support.

## References

- [R1: MLIR language reference](https://mlir.llvm.org/docs/LangRef/): mixed-level operations, nested regions and common representations; precedent only.
- [R2: Component Model canonical ABI](https://component-model.bytecodealliance.org/advanced/canonical-abi.html): explicit cross-language representation boundary; no requirement to adopt Wasm.
- [R3: Node-API, Node 22.16.0](https://nodejs.org/download/release/v22.16.0/docs/api/n-api.html): C API used by the authored in-process fixture.
- Related repository work: [minimum recovery and held-out experiments, PR 20](https://github.com/seeker-cyber-maker/fDisBull/pull/20), [HUD/context proposal, PR 22](https://github.com/seeker-cyber-maker/fDisBull/pull/22), [source-backed intent/residual distinction, PR 24](https://github.com/seeker-cyber-maker/fDisBull/pull/24).
