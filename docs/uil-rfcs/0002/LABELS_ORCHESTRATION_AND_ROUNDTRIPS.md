# Labels, interchangeable components, UDC orchestration and round trips

**REVISION IN PROGRESS. Discussion draft, 30 October 2026.**

This extends [RFC 0002](../0002-executable-rosetta-contracts.md) and the
[agent-first topology](AGENT_FIRST_TOPOLOGY.md). It records TiGa's clarification:
UIL describes meaning through symbolic identities, while the UDC chooses how to
realize memory, control flow and executable packaging. It adopts no new core
schema, opcode, backend or production optimization.

## 1. Decision

Use symbolic labels in UIL, not native addresses as ordinary variable/function
identities. Let interchangeable analysis providers establish source-backed UDL
bindings. Let interchangeable UDC implementations and an explicit orchestration
plan realize the blueprint. Preserve enough information to recover that blueprint
and, where requested, reconstruct its original executable backings.

The freedom belongs to implementation; the obligations belong to behavior:

- Executable UDL retains working backings and their entry/exit requirements.
- UIL owns logical values, state identity, relationships and observable effects.
- UDC definitions select or generate implementations of those contracts.
- UDC orchestration owns layout, connections and realization-only machinery.
- A build capsule binds the input blueprint, selected modules, transformations,
  output artifacts and the retained information needed by a round-trip profile.

There is no requirement to implement a semantic function using CALL/RET, a
variable using a stack slot, or a collection using contiguous memory. There is
also no permission to drop state, identities or effects that callers can observe.

## 2. Labels refer to logical identities

A human/agent sees `park.cash`, `region.timesShownID`, or `apply_adjustment`.
An exact reference resolves to a namespaced logical identity, independent of
spelling and physical placement. Maintain these distinct records:

| Record | Purpose |
| --- | --- |
| Stable node/entity ID | Identity across edits and renames; not an address |
| Qualified label and aliases | Readable names, scoped lookup, rename history |
| Contract revision | Immutable meaning, domain, state/effect and dependency specification |
| Backing/binding revision | Executable implementation, source correspondence and admitted entry context |
| Target realization | Chosen allocation, emitted symbol, handle/index and runtime representation |

Illustrative notation, not a new v1 format:

```
read(field = @region.timesShownID)
invoke(operation = @present_identification, receiver = @actor)
```

The resolver binds references once to stable IDs. A display rename must not
silently retarget them. Two scopes can contain a label `count` without denoting
one cell. Ambiguous, absent and incompatible-revision references are explicit
errors. Decompiler-generated variable names are evidence aliases, not authority.
Do not collapse distinct references because names, offsets or sampled values
match. A reloaded resource at the same address can be a different entity.

Separate immutable values, mutable cells/entities, references and storage
bindings. Domain, arithmetic, units, shape, lifetime and alias relationships are
semantic when observable. Layout, register allocation and calling convention are
usually realization choices. Endianness belongs to an encoding boundary unless
byte order itself is part of the declared operation. Observable address
arithmetic, pointer equality, volatile/device access and self-inspection cannot
be erased by giving their operands friendlier labels.

Names without addresses are an established implementation option: MLIR uses
scoped symbolic references [S1]. This proposal does not require MLIR's type,
serialization or symbol-table design.

## 3. Deduplicate implementations, not accidentally distinct state

"Similar" is a candidate-generation result. A deduplication decision must name
what is being shared and the domain/observation contract under which it is valid.

| Candidate | Potentially valid sharing | Conditions that can prevent it |
| --- | --- | --- |
| Immutable value/constant | One canonical value or storage backing | Observed identity/address distinction, external ABI or encoding |
| Pure function/composite | One qualified implementation, several logical aliases | Different domains, arithmetic, exits, exceptions or observed function identity |
| Stateful function | Shared code with separate per-instance state | Different closures, global dependencies, receiver identity or invocation state |
| Mutable variables | Proven aliases can have one cell; disjoint lifetimes may reuse physical storage | Equal current values/types/names do not establish shared identity |
| Repeated read/computation | Reuse an earlier result under proven invariance | Intervening writes, aliasing, volatility, callbacks, time or randomness |
| Duplicate recovered symbols | Shared semantic definition while preserving origins | Evidence that original roles or meanings actually differ |

The compiler can share physical code while retaining distinct logical operation
IDs, and can coalesce storage while retaining distinct semantic variables. These
are different transformations. Reverse maps must retain the multiplicity and
original provenance even when output contains only one implementation.

Suggested admission process:

1. Generate candidates using structural keys, normalized expressions, compatible
   contracts or embeddings. Record the generating method, never call similarity
   equivalence.
2. Compare types/domains, captured environment, state/read/write/alias sets,
   ordered effects, exits and identity observations. Match implementations in
   context, not isolated byte strings with unresolved relocations.
3. Establish the required correspondence with the existing qualification policy.
   Include discriminating cases, symbolic obligations where supported and
   original execution when needed. Finite examples alone are not universal proof.
4. Preserve aliases/source bindings and record the actual sharing transformation.
   Recheck affected dependents and compare the chosen observation boundary.
5. Measure total cost, including adapters, dispatch and reconstruction metadata.
   A smaller code body is not automatically faster or cheaper overall.

LLVM's distinction between address-significant and `unnamed_addr` functions and
constants provides a relevant precedent: equal contents need not imply that
identity can be merged [S2]. We can apply the principle without adopting LLVM.

## 4. Drop-in replacement is a versioned component contract

Make the pipeline selectable by capability: loader, decoder, dataflow provider,
C-view/decompiler, block mapper, verifier, compiler definition, orchestrator,
linker/packager and target runtime. A configured C-view provider could be
Ghidra, IDA/Hex-Rays, Binary Ninja, a restricted local renderer, or an explicit
manual-agent workflow. Some programs need no C stage at all.

Each interchangeable component declares:

- accepted inputs and exact identities, supported ISA/VM/format and capabilities;
- output schema and semantics, address spaces, fact modality and unresolved scope;
- dependencies, versions, license/runtime prerequisites and cost information;
- deterministic behavior or recorded nondeterminism; cancellation and failure
  semantics; execution authority and permissible external effects.

The receiver validates this handshake before accepting output. A compatible
interface is necessary but does not guarantee identical conclusions or complete
coverage. Keep raw provider evidence, source mappings and conflicts. Pin settings
and stage revisions; replacing one component invalidates dependent results whose
assumptions changed, not every unrelated fact in the project.

An agent-assisted provider is a valid candidate route, not a correctness escape
hatch. Mark its hypotheses, record tools/prompts/artifacts sufficient for the
chosen provenance policy, and require the same downstream acceptance criteria.
Unsupported required work is refused or delegated explicitly; there is no silent
fallback to a weaker provider. No provider may execute an analysis target merely
because its adapter accepts a file. Native execution authority remains separate.

"Drop-in" therefore means contract-compatible and testable, not unconditionally
substitutable regardless of architecture, license, supported semantics or state.
No Ghidra/IDA/Binary Ninja adapter or provider tournament is implemented here.

## 5. UDC orchestration is a first-class realization layer

A UDC has two cooperating parts: per-operation implementations/lowerings, and a
program-level realization/orchestration plan. The plan may combine retained ASM,
generated C/Rust, JavaScript modules and runtime services.

```
UIL blueprint + executable UDL support
          |
UDC definition selection
          |
UDC orchestration / realization plan
  - logical-to-physical state mapping
  - entry/exit, calling and continuation adapters
  - value conversions, ownership and lifetime management
  - relocations, code/data layout, trampolines and dispatch
  - runtime startup, service imports and error translation
  - resource packaging, target scaffold and linker
          |
Output artifact set + build/round-trip capsule
```

The plan contains generated fix-ups that need not appear as user-authored UIL
operations. It must nevertheless justify their relationship to the blueprint.
A fix-up can marshal an argument or implement a continuation; it cannot invent
a new observable purchase, write or callback and dismiss it as glue.

Let concrete state be `c`, abstract UIL state be `s`, and `pi(c)=s` be the declared
state projection. A realization-only step may change private implementation
state while leaving `pi(c)` and the observable event trace unchanged. An operation
implementation must simulate the corresponding UIL transition and preserve its
postcondition/frame conditions. This is a proposed proof obligation, not a
completed solver. Prevent infinite internal stuttering where UIL promises
progress; account for timing/resource constraints when the contract includes
them. Allocation failure, exceptions and interruption are not invisible simply
because the program-level plan introduced them.

Keep both an exact ABI-level view for adapters and the higher-level observations
used by the UIL contract. Qualification records the chosen boundary and excluded
effects. Hash and test orchestration code, state maps and generated fix-ups just
as other implementations are hashed and tested. Their cost counts toward target
selection. A wider scalar carrier is allowed if conversions preserve the domain;
sharing a raw pointer between incompatible heaps is not.

### Stackless and global-arena targets

A UDC can lower calls into jumps, a trampoline, continuation-passing or an explicit
state machine. It must retain return destinations and live activation state.
Recursion, reentrant callbacks, concurrent invocations, suspension and error
unwinding may require distinct frames or equivalent state even with no machine
call stack. Stackless does not mean stateless. Coroutine lowering offers a
practical precedent for explicit state/frame transformations [S3].

Likewise, variables can be stored in a global arena with zero-based indices.
Per-invocation state may need keys such as `(instance, activation, field)`.
Replacing every local with one global slot per function corrupts reentrant or
recursive executions. Scope and identity remain logical even if every storage
cell lives in one physical allocation. Permit specialization for a proven
non-reentrant domain; do not make it a universal default.

### A 64-bit label/handle is not a 64-bit native DOS address

An original 16-bit DOS program may be recompiled for a flat 64-bit host with
qualified service adapters. That is a new target, not a claim of original DOS
binary compatibility. A DOS-targeted implementation may instead represent a
logical handle/index in several words and translate it to admitted segmented,
windowed or otherwise supported storage.

The execution mode constrains effective-address encodings. Keeping a number in
64 bits does not make that number directly dereferenceable by ordinary real-mode
instructions. NASM documents distinct 16/32/64-bit modes and address-size rules
[S4]. A switch of execution environment, VM or bridge must be declared and
qualified; container names such as ELF, PE or DOS do not supply a missing mode.

For source segmented memory, preserve observable aliases: `1000:0010` and
`1001:0000` denote the same linear location under ordinary segment*16+offset
translation. Assigning unrelated logical cells to both loses behavior. This
example is an alias constraint, not a universal live-memory resolver.

## 6. Reversibility is an explicit output profile

The output plus its UDC definition is useful evidence, but generally does not
uniquely determine the input UIL. Optimization, inlining, deduplication, constant
folding, dead-code elimination and discarded names can be many-to-one. Two
blueprints can legitimately generate the same bytes. No inverse procedure can
choose the original without retained information or an explicitly coarser notion
of identity.

Define separate requested profiles:

| Round trip | Required result | Retained support |
| --- | --- | --- |
| Semantic recovery | A UIL program with equivalent declared behavior | Source/model evidence, selected definitions and state/effect mapping |
| Exact blueprint recovery | The same canonical UIL program/revision | Input blueprint, or proven lossless encoding plus all inverse residuals |
| Exact original code-image recovery | Original bytes in a declared artifact range | Original backings, opaque bytes, layout/resources/fixups and exact profile |
| Original ASM source-text recovery | Original text, labels, comments and formatting | The source text itself or a proven lossless source representation |

A sufficient first implementation is a content-addressed build capsule containing
or referencing the exact input UIL, contract/definition revisions, selected UDC
modules, orchestration plan, source/backing inventory, transformations and source
maps, target/toolchain profile, and hashes of every output. An optimized future
capsule can be smaller only if its restoration property is established.

Validate output hashes before trusting the capsule as a description of those
bytes. A stale, missing, incompatible or tampered capsule cannot restore certainty.
Integrity is not semantic correctness; acceptance still needs correspondence
checks. Treat imports as untrusted data, not permission to run compiler modules.

A capsule may include licensed original backings privately or reference a
separately retained store. It must not publish proprietary bytes merely to make
reversal convenient. Missing required content means reconstruction is unavailable,
not that an approximate replacement counts as exact.

Recovering the old blueprint can select its original-backed UDC and reemit the
original code image. After a meaningful UIL edit, reemitting the old bytes would
not implement the edited blueprint. Keep old and new revisions separately.
Identical disassembly text, exact code bytes and equivalent behavior are separate
claims; normalized ASM is not automatically the original source listing.

## 7. Proposed acceptance cases

The following are prospective production gates, independent of R01-R18 and
Q01-Q12. The small [authored witness checks](check_component_witnesses.py) exercise
selected counterexamples only, not production provider/dedup/orchestration APIs.

| ID | Case | Required behavior |
| --- | --- | --- |
| D01 | Rename a label; two scopes both contain `count` | References keep stable IDs; ambiguity rejects instead of retargeting. |
| D02 | Two mutable u8 cells both initially zero | Mutating one must not mutate the other without an established alias. |
| D03 | Identical constants with observed identity | Preserve identity distinctions or reject storage merging. |
| D04 | Equivalent pure implementations, wrapping versus saturation control | Admit only the declared operation/domain; boundary counterexample rejects the wrong candidate. |
| D05 | Identical code with different captured state | Share code only with distinct environments or a proved equivalent mapping. |
| D06 | Common expression separated by a write | Preserve read timing; reject a cached/recomputed value with changed meaning. |
| D07 | Replace the decompiler with another supported provider | Compatible input/output contract, identities, evidence and unknowns survive; changed findings requalify. |
| D08 | Agent workflow supplies an attractive unverified explanation | Preserve it as a hypothesis; no automatic acceptance or hidden fallback. |
| D09 | Global-arena implementation reentered by a callback | Activation state is isolated; naive shared slot fails. |
| D10 | Calls lowered to a trampoline/state machine | Return continuations, live values, exits and progress satisfy the contract. |
| D11 | Orchestration adds an observable event | Reject unless explicitly part of the behavior/profile; not invisible glue. |
| D12 | 64-bit handle on a DOS target | Translate under a supported profile or refuse; do not emit unsupported direct addressing. |
| D13 | Distinct segment:offset pairs alias one source location | Preserve that relationship through target-state mapping. |
| D14 | Two UIL programs compile to the same optimized output | Output alone makes exact inverse ambiguous; capsule recovers the selected original. |
| D15 | Corrupted output or capsule | Detect the identity mismatch; refuse claimed exact recovery. |
| D16 | Deduplicated code has multiple source origins | Reverse provenance retains all original logical identities and multiplicity. |
| D17 | Patched backing with unchanged caller bytes | Reuse code where valid, invalidate obsolete dependent behavioral claims. |
| D18 | Edited UIL compiled through stale original-only definitions | Reject unsupported edits or use a qualified updated implementation. |
| D19 | Missing resource/backing for exact reconstruction | Report missing closure; do not synthesize it and label the result byte-exact. |
| D20 | New value/function/control concept | Version semantics and negotiate support; no reinterpretation of an existing opcode. |

## 8. Illustration status and compatibility

The two generated concept images selected by the user are retained in the
separate full-resolution asset delivery. [Illustration notes](ILLUSTRATION_NOTES.md)
record their identities and publication status. They are explanatory artwork,
not APIs, proof receipts or capability matrices. The first image's PR number 30
is an illustration error: the discussion is PR 29. The conceptual text here takes
precedence over illustrative `verified: true`, fixed endian/storage fields or
particular function syntax in the images.

No existing v1 schema is modified. A companion definition/capsule mechanism needs
its own reviewed capability contract; it cannot hide executable authority in
`evidence`. Preserve the existing fDisBull/downstream ownership boundary.

## Primary references and scope

- S1: [MLIR symbols and symbol tables](https://mlir.llvm.org/docs/SymbolsAndSymbolTables/), especially scoped symbolic references.
- S2: [LLVM language reference](https://llvm.org/docs/LangRef.html), `unnamed_addr` for functions/constants and address significance.
- S3: [LLVM coroutines](https://llvm.org/docs/Coroutines.html), explicit coroutine frames and split control flow.
- S4: [NASM target processor mode](https://www.nasm.us/doc/nasm08.html#section-8.1), 16/32/64-bit instruction/address-size rules.

References checked 30 October 2026. These precedents justify constraints, not
adoption of a specific framework. The inverse-ambiguity claim follows directly
from two distinct inputs having the same output; it is not a measured decompiler
limitation. This revision implements no new fDisBull runtime or native backend.
