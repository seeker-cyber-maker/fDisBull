# Deterministic execution and discoverable UIL guidance

## Status and relationship to existing contracts

This is **proposed architecture and acceptance guidance** distilled from four
authored chapters of `UDL_UIL_UDC_Reference_v0.10.zip`. It adds no runtime,
callable operation, parser field, status enum, or profile version. The source
baseline is fDisBull main
`f861d17ed4837f753e000f53cc777a7d906fde82` (the 0.30.0 release line after the
reviewed 0.30.0 development merges); the provenance section identifies the
reference edition and exact chapter bytes.

Use the [common indexed contract](COMMON_UIL_CONTRACT.md),
[native realization contract](COMMON_UIL_NATIVE.md),
[agent quickstart](AGENT_QUICKSTART.md), and
[UIL export boundary](UIL_BOUNDARY.md) for their implemented or explicitly
proposed scopes. This supplement accompanies the canonical architecture in
[Draft MR !45][mr45], inspected at [its pinned document][canonical45].
Delegation and review policy remain in [Draft MR !47][mr47] and its
[pinned methodology guide][methodology47]. Neither draft is treated as merged.

The current common closure retains these distinct identities:

| Document | Existing format |
| --- | --- |
| Program | `fdisbull-common-uil-1` |
| Presentation | `fdisbull-uil-presentation-1` |
| Orchestration | `fdisbull-uil-orchestration-1` |
| Semantic catalog | `fdisbull-uil-catalog-1` |

The separate native link record uses `fdisbull-uil-native-link-1`, with
`fdisbull-udc-link-lock-1` for its resolved dependency graph. These identities
are defined by the pinned [common parser][common-source],
[catalog][catalog-source], and [native linker][link-source]. Scalar, memory,
adventure, console, and reference-study formats retain their own contracts.
An architecture description does not make a study format a production profile.
The checklists below belong in design and qualification records until a named
extension implements them; they are not extra keys to insert into current
strict documents.

## 1. Retain rules that supported operations can execute

Once inputs, contracts, policy, selected implementations, and required
environment are explicit, a supported operation should apply retained rules
without asking an agent to invent missing semantics during each invocation.
Agents investigate gaps and propose mappings, adapters, contracts, or changes.
An accepted proposal becomes a versioned artifact qualified for its stated
domain. Later runs consume that artifact rather than asking the model to
reconstruct its earlier answer. Repetition alone does not establish correctness.

Declare each reproducibility promise separately:

| Promise | What must remain fixed or explicitly related |
| --- | --- |
| Plan | Inputs, catalog snapshot, policies, relevant tool context, candidate order and tie-breaks |
| Artifact | Specified outputs, source and build inputs, toolchain, options, dependencies and environment |
| Replay | Qualified initial state, external inputs, random context and observation relation |
| Decision | Evidence or measurement set, admission rules and preference policy |

Canonicalization must preserve statement, effect, and other semantic sequence
order. Keep stable semantic/artifact identities separate from timestamps and
session metadata. Freshness epochs still invalidate stale actions even when
restored values repeat. Performance measurements remain observations: applying
a fixed policy to the same report can reproduce a decision; running another
benchmark produces new evidence. A deadline also need not explore the same
candidate set as a fixed work budget.

A missing fact or capability should stop the affected route with a bounded
diagnostic: name the boundary, missing dependency, known evidence, unresolved
assumptions, dependent work, qualified alternatives, and smallest useful next
check. Independent authorized work can continue. Keep invalid input,
unsupported capability, unresolved semantics, candidate rejection, inconclusive
verification, and tool failure conceptually distinct. A solver timeout is not a
counterexample, and a pipeline error is not an operation's modeled `refused`
outcome. These are diagnostic requirements, not newly accepted status values.

Replay also records its restoration policy. Exact comparison needs matched or
explicitly related random and external context; an exploratory retry may retain
declared current RNG/timing state. Restoring slots cannot undo an already
committed external effect. Preserve qualified original-backed execution while
unresolved behavior is investigated.

## 2. Derive guidance from real operations and current state

Build guidance from the operation definitions, validators, capabilities and
state used by execution. The existing [quickstart][quickstart-source] documents
these discovery entry points:

```sh
fdisbull --version
fdisbull capabilities
fdisbull methods
fdisbull agent-skill --index
fdisbull agent-skill --reference references/reconstruction.md
```

This is a source-verified command list, not a new execution receipt. The pinned
[capability implementation][capabilities-source] reports dependency detection
with `runtime_validation: not_run`; detection is not backend qualification.
The [dispatcher][cli-source] registers method names and parameter summaries;
its existence does not establish a standardized structured guidance envelope
for every operation.

A recommendation should identify the actual callable and schema, bind known
arguments exactly, expose missing arguments with types and units, and state
its purpose, preconditions, effects, bounds, expected result and recovery route.
Qualify it by relevant source, target, profile, observer, session and revision.
A partially specified route is not an executable invocation. Check identities
and current work before recommending another import, launch or build; recheck
applicability when executing. Support, usefulness for a goal and authorization
are separate predicates. Existing policy governs authorization; guidance adds
no routine approval gate.

**Ready to submit describes public request validity, not a successful outcome.**
Published readiness, available actions, ranking and explanations may depend
only on information admitted for the observer. If public rules permit an
attempt, hidden gameplay conditions affecting its outcome must not silently
suppress or downgrade it. Execution resolves those conditions and exposes the
permitted outcome. Hidden-state differences alone must not change otherwise
equivalent player-facing guidance. An investigator's richer view requires its
own explicit observation role.

Passive discovery must not launch execution, advance time, build an artifact or
run a benchmark. Expose an active readiness probe separately with its effects.
Keep descriptive actions distinct from executable actions, and state the actual
time unit and restoration coverage for advance or rewind. A frame, next-fetch
interval, instruction interval and game tick are not interchangeable.

Results should distinguish completion, pending work, refusal, and uncertain
effects using the existing interface's outcomes. Retrieve retained output using
the existing `output-info`, `output-select`, `output-read` or `output-export`
routes documented in the [quickstart][quickstart-source]; an incomplete wire
response is not evidence that the original operation did not run. Reconcile
unknown completion before repeating effects. Refresh stale context after
rewind or concurrent changes, and distinguish durable artifacts from
session-owned handles in a handoff.

## 3. Preserve meaning through the selected compiler and runtime

The [current native route][native-source] already has bounded component
selection, compiler recipes, separate build/seal receipts and a typed native
computation boundary. The broader toolchain chapter proposes how additional
adapters should preserve these responsibilities:

| Responsibility | Required boundary |
| --- | --- |
| Orchestration | Select qualified bodies/providers and bind logical state and services |
| Semantic lowering | Preserve the selected UIL profile in generated source or compiler IR |
| Compiler and linker | Respect target configuration, ABI constraints, symbols, relocations and layout |
| Startup and runtime | Establish entry state, ownership, required services, effects and continuation |

A logical slot is not a permanent register or memory address. A temporary may
be optimized away; persistent, shared, aliased, address-taken or observed state
needs its promised storage and materialization. Specify how required state is
available at invocation, observation and checkpoint boundaries.

Lowering preserves widths, signedness, wrapping, conversions, faults/refusal,
evaluation order, aliases, lifetime and effect commit boundaries. For example,
the current common contract eagerly evaluates both `select` arms and refuses
on defined invalid operations. A conditional translation that skips a required
failure changes that contract. Planned effects and `pending_host` do not imply
committed physical I/O. A wrapper must retain that distinction.

Record target ISA, OS/runtime, object format, ABI/memory model, entry and exit
relations, imports, libraries, tool versions/options, generated inputs and
artifact identities. Compatible native objects can share a link; an interpreted
provider or retained guest block needs a declared invocation and state bridge.
An extracted executable slice does not acquire missing relocation or
continuation facts merely because a linker is available.

The reference recommends evaluating LLVM/Clang and a target linker for modern
adapters and a separate Open Watcom adapter for legacy x86. This is a proposed
extension choice, not a replacement for existing recipes or qualification of a
generic cross-target backend. A successful build establishes acceptance by the
toolchain; source correspondence and behavior require separate evidence.

## 4. Make the realization recipe and its bindings explicit

A realization recipe should identify the UIL behavior/profile; selected
bodies, providers, bridges and scaffold; ordered construction stages; each
stage's inputs and outputs; and resulting artifacts and qualification evidence.
The catalog describes candidates, orchestration admits and connects them, and
execution materializes the plan. These are planning obligations rather than a
fifth common input document or a new recipe grammar.

Keep five binding categories separate:

| Binding | Meaning |
| --- | --- |
| Build configuration | Choice fixed for the generated artifact, such as a formatter policy |
| Relocation/layout | Target location or symbol resolved during construction or loading |
| Invocation input | Typed value supplied for one call |
| Persistent state | Object identity, field, ownership and lifetime across calls |
| Continuation | Control and runtime/machine state required after the call |

For an authored HUD example, a formatting policy can be fixed at build time,
the formatter's symbol relocated, a current health value supplied at invocation,
the entity field retained as persistent state, and a display result or guest
return bound to a continuation. This describes a design example; it asserts no
recovered health field. Slot indices, native addresses, configuration keys and
world entity IDs remain different identities.

Artifact form determines admission obligations. Source/IR needs lowering and
toolchain facts; a relocatable object needs ABI, symbol and relocation facts;
a raw body needs every fixup and entry/exit dependency; a runtime provider
needs protocol, lifecycle, scheduling and ownership facts. A serialized byte
literal retains the represented artifact's execution requirements. Putting
machine bytes in C or Python syntax is not semantic translation.

Qualify the composed boundary, including adapters, runtime calls and scaffold.
Compare required private state and effects as well as public observations.
Preserve three distinct identities: the reusable template, the bound target
realization, and qualification/measurement under a stated domain/environment.
Each identity covers the inputs affecting that result. A cache hit or matching
descriptor does not transfer evidence to a changed binding, wrapper or target.
Measure the composed operation when making cost choices, including conversions,
calls, copying and allocation.

## 5. Acceptance for a future implementation

Adopt one bounded route at a time. Its checks should demonstrate repeatable
planning under declared inputs; the particular artifact or replay guarantee
offered; preserved failures/effects; actionable unresolved diagnostics; and
invalidation of dependent results when relevant inputs change. Keep current
schemas strict and use the [UIL RFC process](UIL_RFC_PROCESS.md) for a required
language extension.

Test interface contracts separately from agent usability. Check that advertised
calls exist, arguments and preconditions agree with execution, hidden outcome
state cannot leak through guidance, passive discovery has no execution effects,
and uncertain completion is reconciled. A separate fresh-agent trial should
cover a useful task, an ordinary error, an unavailable capability, stale context,
existing-work reuse and honest completion within declared bounds. Retain the
actual visible transcript and assistance. A documentation review or a written
test plan does not complete that trial. Apply !47's bounded context and evidence
policy rather than creating an additional universal review gate.

This supplement performs documentation intake only. It supplies no new runtime
qualification, original-game execution, compiler integration, or fresh-agent
trial. Existing implementations and historical receipts retain their original
scope.

## Provenance and pinned evidence

The source was a privately supplied `UDL_UIL_UDC_Reference_v0.10.zip`,
**version 8**. The four chapters were read in full. Their SHA-256 identities
below pin this intake; the original private library link is intentionally not
reproduced, so a later revision must be checked separately.

| Chapter | Source sections used | SHA-256 |
| --- | --- | --- |
| `DETERMINISTIC_PIPELINE.md` | 1–8: retained rules, reproducibility, diagnostics, external context and acceptance | `fed75f5baf88a016d1ccbb0dc2ebd14ffb921787cf3f6228177599757adfbd0b` |
| `AGENT_GUIDANCE.md` | 3–11: discoverability, observer-valid readiness, recovery and fresh-agent acceptance | `49869f7e517a6fccbbe45014d0563625c82fce681933ec6290a55f842d4482f2` |
| `EXECUTION_TOOLCHAINS.md` | 1–8: toolchain roles, slots, lowering, bridges and realization evidence | `82970e9ff16fcb8a8586734ba9590656e200b079e1d7af7b0f73890c3d64e490` |
| `METASPLOIT_COMPOSITION.md` | 2–8: recipes, artifact forms, five bindings, wrappers and cache identities | `c882c67afedef22713e4e71cddf8056e6f620417b93a94314fc50d9154568758` |

The fourth chapter's transferable architecture is summarized here; this change
imports no third-party framework, payload or historical report. Current-source
claims above were checked against the pinned repository files. The reference's
proposals and outside-tool recommendations are attributed design input, not
newly executed integrations.

[mr45]: https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/45
[canonical45]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/9e5788f/docs/UDL_UIL_UDC_CONSOLIDATED.md
[mr47]: https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/47
[methodology47]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/22903caf22cb380be0fef6e1ae2481c9722e0424/src/fdisbull/skills/fdisbull-investigate/references/methodology.md
[common-source]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f861d17ed4837f753e000f53cc777a7d906fde82/src/fdisbull/common_uil.py
[catalog-source]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f861d17ed4837f753e000f53cc777a7d906fde82/src/fdisbull/uil_catalog.py
[link-source]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f861d17ed4837f753e000f53cc777a7d906fde82/src/fdisbull/uil_link.py
[quickstart-source]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f861d17ed4837f753e000f53cc777a7d906fde82/docs/AGENT_QUICKSTART.md
[capabilities-source]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f861d17ed4837f753e000f53cc777a7d906fde82/src/fdisbull/capabilities.py
[cli-source]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f861d17ed4837f753e000f53cc777a7d906fde82/src/fdisbull/cli.py
[native-source]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f861d17ed4837f753e000f53cc777a7d906fde82/docs/COMMON_UIL_NATIVE.md
