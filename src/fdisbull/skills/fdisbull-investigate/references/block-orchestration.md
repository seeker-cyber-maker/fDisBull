# Program-block orchestration across languages

Use this reference when composing program implementations from different source
languages or native backings. The question is whether their **program
interfaces and effects** compose; this is not a workflow for scheduling agents.

## Contents

- [Start with identities and evidence](#start-with-identities-and-evidence)
- [Qualify each boundary](#qualify-each-boundary)
- [Plan adapters before layout](#plan-adapters-before-layout)
- [Example: a native block and a C implementation](#example-a-native-block-and-a-c-implementation)
- [Place, fix and qualify the composition](#place-fix-and-qualify-the-composition)
- [Choose the next experiment](#choose-the-next-experiment)

## Start with identities and evidence

1. State one intended behavior and its inputs, outputs, preconditions, ordered
   effects, failure paths and observable boundary. Name the behavior separately
   from any source address or language.
2. Record each immutable source identity, source-byte version, decode context,
   and complete entry-qualified backing. Keep overlapping source occurrences
   distinct even when they share physical bytes.
3. Give every selected implementation its own revision and declared behavior
   contract. An implementation can be native code, generated code or a retained
   original backing; source language alone does not establish its machine ABI.
4. Record each adapter's revision and its admitted input/output contract. Bind
   stable entry and exit ports before selecting their physical locations. Layout
   identity changes when placement or fixups change, even if behavior identity
   is unchanged. An implementation change does not patch its source or sibling.
5. Preserve an exact original-layout pass-through baseline where available.
   Unsupported behavior stays an explicit residual or unknown; do not promote
   byte identity, a matching label, or a compiler claim into semantic proof.

## Qualify each boundary

Determine whether a component is an **inline instruction block** or a
**callable function**. An inline block inherits its surrounding machine state
and continues through explicit ports; it is not automatically safe to call.
A function has a verified call/return interface, including its own entry and
exit machinery. Never add a wrapper just because two source languages differ:
when the compiled interfaces already match, preserve the direct connection.

For each boundary record, at minimum:

- ISA, execution mode, endianness, required CPU features, address width and
  memory model; near versus far pointers and segment assumptions where relevant.
- Entry and exit ports, argument locations, return values, hidden arguments,
  aggregate/structure layout, pointer representation and ownership/lifetime.
- Stack entry and exit state, alignment, red zones or shadow space if applicable,
  register clobbers and callee/caller saves, and who cleans arguments.
- Live flags, including direction flag where string instructions depend on it;
  memory reads/writes, ordered external effects, and error or partial outcomes.
- Required runtime, initialization, helper routines, exception and unwind
  behavior, callbacks and other environment obligations when applicable.
- Integer promotion/overflow and boolean representation, evaluation/effect
  ordering, aliasing/lifetime rules, and floating-point or SIMD state when
  these affect the admitted behavior. Matching ABIs alone do not reconcile
  C undefined behavior with an ASM model's modular arithmetic.

Use compiler output, ABI specifications, native observations and existing source
contracts as evidence at their respective scopes. Do not infer a calling
convention from a language name or a function-like label. If architecture,
mode, state representation or effects do not match, qualify an explicit
transition, recompile/re-lower to a compatible target, use an appropriate
emulation boundary, or refuse that composition. Changing ISA labels or source
metadata does not translate code.

## Plan adapters before layout

First inventory what each side actually does. A compiler-generated C function may
already contain its required prologue and epilogue; do not add a second function
frame or duplicate its register saves. If interfaces match, no adapter is needed.
Otherwise specify only the missing transition and identify who owns each step:

1. Marshal arguments and hidden inputs, including width, signedness, layout and
   pointer/segment conversion. Establish runtime prerequisites.
2. Save required live registers and flags, establish stack alignment and any
   necessary frame, and perform a matched near/far call and return when the
   admitted boundary is callable. Respect caller versus callee cleanup.
3. Recover return values, restore stack and state, and preserve ordered effects,
   errors, cleanup and unwind obligations. State precisely which changes the
   adapter itself makes; even a stack cleanup instruction may change flags.
4. Describe error and interruption behavior as well as ordinary return. If the
   combined partial effects or unwind behavior cannot be represented and tested,
   keep that path unknown or refuse it rather than silently discarding it.

An adapter is itself an implementation with dependencies, source and revision
identity, ports, clobbers and qualification. Do not manufacture a language
transition for two inline blocks when no call is needed. Do not use offsets or
branch repair to paper over an incompatible ABI.

## Example: a native block and a C implementation

The following is an **illustrative contract**, not an existing fDisBull API or
a claim about a particular C compiler's default ABI.

- A 16-bit x86 caller reaches a callable boundary with a 16-bit value in AX.
  It expects the result in AX, BX preserved, a restored stack, and the incoming
  flags live after the boundary. The admitted domain excludes external effects.
- An independently compiled C candidate implements the same admitted behavior
  and uses the same 16-bit mode. Its declared ABI takes one 16-bit stack
  argument, returns in AX, preserves BX, uses a near return, and requires its
  caller to remove the argument. It requires DF clear on entry. Its generated
  function already owns its frame.
- The proposed adapter saves the live flags, clears DF, pushes AX as the
  argument, calls
  the candidate using a near call, removes the argument under that ABI, restores
  the saved flags and continues through the original logical exit. Verify stack
  addresses, alignment, saved registers and every exit in the actual target; do
  not add another prologue around the candidate's existing frame.

If a candidate is compiled to accept AX directly and meets the other stated
conditions, select the compatible interface without that argument adapter.
If flags are not preserved, an exception can bypass cleanup, or the function's
actual ABI is unknown, the boundary is not yet qualified. A different ISA
requires an actual transition or compatible re-lowering, not a new tag.

## Place, fix and qualify the composition

Build an explicit graph of implementations and adapters with stable ports.
Decide required transitions and their sizes before final placement. Inventory
code and data references, relocations, pointer tables and externally supplied
entries. After placement, resolve typed fixups to the selected ports, perform
branch relaxation as needed, and independently re-decode emitted transfers and
check ranges. Revisit sizing if relaxation changes it. A missing or ambiguous
reference remains unresolved; it is not an implicit fallthrough or permission
to assume an old source offset still identifies a new instruction.

Keep the exact retained-source baseline separate from a regenerated artifact.
Qualify each source-to-backing and implementation-to-behavior edge; then qualify
adapter boundaries, adjacent pairs and the composed program. Use authored
native executions at declared entries and compare state and ordered effects at
normal and error exits, including cleanup and observable partial effects. Test
relocation or block-order changes as metamorphic controls and include deliberately
broken argument, cleanup, port or state handling as negative controls.

A Z3 result applies only to the modeled inputs, outputs and assumptions. A
register-only projection excludes memory, flags, control flow, ABI, timing and
external effects unless a separate model and evidence cover them. Recheck proof
identity against the selected implementation and source revisions. Native test
results likewise cover only the exercised target and states; neither establishes
whole-program parity or unobserved reachability.

The current bounded DOS16/i386 profile places retained native blocks and selected
straight-line replacements with declared data and near-reference repairs. It
can emit COM or a resident MZ scaffold. It requires one CS context and refuses
calls and unsupported control transfers; it
does not generate the general language/ABI adapters described here. Check the
installed methods and backend before proposing a native run.

## Choose the next experiment

Prefer compatible target lowering or an already matching ABI, then the smallest
qualified adapter. Compare candidates on the same declared behavior and input
domain. Choose one unresolved boundary per experiment by expected decision
value, confidence and cost, including runtime setup and evidence handling.
Retain the baseline and previous revisions; stop and report unknown when the
required transition, native capability or decisive evidence is unavailable.
