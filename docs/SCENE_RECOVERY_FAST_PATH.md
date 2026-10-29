# Fast scene recovery: minimum evidence and reusable acceptance

Status: implementation requirements, based on a private Lost in Time experiment.
This proposal adds no core opcodes, proof status enums or scene format. It builds
on [shared IL](INTERACTION_IL.md), [source/block qualification](UDC_TESTING.md),
the [progressive scene workflow](SCENE_STREAMING_WORKFLOW.md), and the Z consumer
in [PR #18](https://github.com/seeker-cyber-maker/fDisBull/pull/18).

## Problem and desired result

The investigator can recover a scene correctly, but currently spends substantial
work writing an adapter, collecting readiness captures, materializing receipts
and replaying a route before offering the next useful interaction. Those tasks
qualify a native harness. They should not all be repeated to accept a new
code-derived scene or retained effect under an already qualified source model.

The desired unit is a **claim about one scene action under an explicit state
domain**, with a compact dependency receipt. Accept the supported subset early;
retain the unresolved frontier. Expand verification only when a new semantic
primitive, external effect or claimed boundary requires it.

Z is the public scene/command projection. UDL maps source behavior into shared
semantics; UIL is the resulting behavior representation. The practical discovery
order can be Z outline -> source obligations/UDL -> executable UIL. This does not
reverse the semantic authority: an outline, description or successful parser
dispatch is not proof of a game rule. In v1, changing `udl` to `uil` only changes
role metadata; measure actual source lowering separately from that copy.

## Minimum code-acceptance gate

For a conditional code claim, require the following evidence and stop when it is
sufficient. This is a proposed gate, not a claim that today's validator performs
these checks automatically.

1. **Source identity and entry binding.** Bind the exact resource/member and byte
   extent, decoder/profile, dispatch entry, semantic variable names and types.
   Hash resources once at intake; reuse immutable identities. A source digest
   establishes identity, not correctness of names or semantics.
2. **Complete slice for the claimed result.** Account for relevant guards,
   branches, reads, writes, aliases and ordered events. Every source operation in
   the slice must map to an operation, a qualified helper summary, or an explicit
   obligation. Do not silently omit unsupported operations or paths.
3. **Closed dependency boundary or narrowed claim.** Resolve calls that can
   affect the claimed result or its control flow. An opaque call need not block
   every claim: for example, a later unconditional write can establish a retained
   output *if the call returns normally to the expected continuation*. State
   that completion assumption and prove that the overwrite reaches and determines
   the value at the declared boundary. Do not infer that the call has no effects,
   terminates, preserves other variables, or is safe to erase from a full model.
4. **Nonvacuous guard and effect agreement.** Establish a satisfiable entry
   witness and compare the source model with the lowered model over the stated
   domain. Prefer finite branch partitions or a bounded solver obligation to
   many equivalent gameplay examples. A sample of examples alone is not an
   all-input proof; both models using one faulty decoder is not independent
   decoder validation. Numeric widths, signedness, wraparound and effect order
   belong in the obligation.
5. **Explicit claim ceiling.** Record what was accepted, assumptions, supported
   state domain, excluded effects, unknown dependencies and evidence identities.
   Source labels and descriptions need their own resource/binding evidence;
   author-supplied prose remains a paraphrase. No native screenshot is required
   for a purely conditional code claim whose source semantics are already bound.

A closed selected branch may be accepted while other branches remain unknown.
The model must reject or delegate those other branches, not supply a plausible
default. A retained-output projection must not be labeled a complete handler.

## Keep separate claim dimensions

| Claim | Least evidence that can establish it | Extra work only when claimed |
|---|---|---|
| Conditional code behavior | Source-bound entry/slice, semantic dependencies, nonvacuous guard and effect agreement | Native evidence for an unqualified source/VM mapping |
| Reachable in ordinary play | A source reachability argument with valid initialization/invariants, or an ordinary-input witness | A complete route only if the claim covers that route |
| Current native target ready | Fresh frame/context, registered geometry, input/presentation state and relevant conditions | A screenshot for an unknown presentation or first calibration |
| Native effect committed | Bounded input-to-result witness at the declared commit boundary | Later UI/persistence boundaries only if included in the result |
| Persistence | Declared save boundary and reopen comparison | No reopen for a pure text/flag lowering change |

Do not collapse these into one `scene_is_true` bit. A code-accepted scene may
still have unknown player reachability or unqualified click presentation. A
previously qualified contract can remain valid while a live observation becomes
stale; invalidate those separately.

## Reuse model

Qualification should be reusable at three granularities:

- Decoder/opcode semantics: byte layout, operand widths, signedness, aliasing and
  control effects for a pinned processor profile.
- Shared helper summaries: preconditions, read/write sets, ordered events,
  completion behavior and unsupported effects.
- Scene/action claims: entry guards and the relevant slice using those summaries.

The dependency key must bind resource/source identity, decoder and mapper
versions, source semantic model, candidate UIL semantic digest, typed interface
and defaults, normalization/checker policy, bindings, claimed outputs/events, assumptions/domain,
helper certificates, solver policy/version when used, and the observation
boundary. A matching source hash alone is not a cache key. Changed facts
invalidate their dependent claims; a new mouse/frame observation does not force
an unrelated arithmetic or opcode proof to run again.

The optional verifier remains local and bounded. Unsupported, unavailable,
unknown, counterexample and unsatisfiable/vacuous conditions must remain visible.
Caching an unknown result must never turn it into acceptance. Reusing an accepted
receipt requires verified identity and dependencies, not a caller's Boolean.
The current `proofs.py` returns a solver result record, not an independently
checkable proof object. A cache hit must say **reused qualification**, identify
the receipt and trust policy, and not imply a fresh solver run. This proposal
does not weaken `compile_dos`'s existing unconditional qualification default;
an explicit compatible acceptance-cache seam is required before reuse there.

## Concrete friction-removal requirements

| Priority | Current friction | Required seam | Smallest useful acceptance |
|---|---|---|---|
| P0 | Gob resources require a separate extractor, textual decoder and handwritten bounded AST parser | Processor/resource adapter yielding typed operations, exact spans, dispatch edges and unsupported nodes | Recover two bounded handlers and one unsupported opcode without losing the unknown frontier |
| P0 | Branch/helper scope is reconstructed by hand for every action | Backward effect slice plus helper read/write/control summaries and a source-coverage receipt | An unresolved helper blocks a complete handler claim but permits a justified narrower terminal-output claim |
| P0 | Source/UIL validation checks shape or small register blocks, not a scene dependency closure | Claim-scoped acceptance service over existing IL and source adapters | Detect changed guard, wrong numeric width, omitted relevant write and vacuous domain; no emulator needed for qualified pure semantics |
| P0 | Already qualified semantics are repeatedly revalidated | Content-addressed receipt lookup with dependency invalidation | Unchanged action reuses acceptance; changed resource, helper summary, binding or output domain invalidates it |
| P1 | Discovered source facts are manually copied into a player adapter | Generate the existing PR #18 Z envelope from accepted programs plus public scene metadata | Exactly one context, common typed declarations/defaults, unambiguous `(verb,item)` bindings and explicit partial coverage |
| P1 | Whole-game projections exceed the Z candidate's 32-program bound | A bounded provider/scene-streaming seam with declared cross-scene state and ownership | Load the next scene without dropping its shared state, changing semantics or raising the package bound silently |
| P1 | Native readiness and state effects get coupled into one postcondition | Separate requested/displayed/registered/ready/committed boundaries using existing scene predicates | A changed script name with stale geometry cannot accept a destination click; a committed effect survives later UI incompleteness |
| P1 | Reopening native checkpoints is tied to mutable mount bytes and paths | Explicit checkpoint resource closure and restore/remap protocol with diagnostics | Detect catalog-file mismatch before restore; restore a private snapshot without changing unrelated resources |
| P1 | Successful probes emit large repeated predicates and screenshots | Compact receipts by default; artifact references and timing counters; expand on first qualification/failure | A batch scene recovery reports counts, frontier, timings and evidence IDs without dumping game text or binary bytes |

These are requirements for the existing seams, not a request to add a competing
Z language or replace the native debugger. The native provider and the pure IL
provider should consume the same accepted public action identity while retaining
their distinct execution and persistence contracts.

## C-like views versus ASM

Use the highest-level *source-faithful* representation available. For an
interpreted game, direct guest-bytecode recovery avoids analyzing the host
interpreter for every scene. C-like pseudocode helps inspection when it preserves
guard structure, typed operations, spans and unresolved calls. Consult ASM for
unresolved lowering, pointer/alias, ABI, width, flags or native-dispatch facts.

The current `udl_blocks.asm_to_c` is a restricted rendering of the same supported
ASM decoder. It is not a general decompiler or an independent oracle. The
included [authored microbenchmark](../examples/recovery/benchmark_lift_paths.py)
separates already-available C parsing from the full ASM -> C -> IL route. Its
results cannot establish human/agent comprehension speed or whole-game recovery
speed. [Measured results and limitations](LOST_IN_TIME_FAST_RECOVERY.md).

## Verification budget and stopping rule

At intake, qualify a new decoder/semantic primitive and record the assumptions.
For each subsequent action, perform only source binding, relevant dependency
closure, the guard/effect obligation and output-format validation. For a scene
family's first native binding, add the minimal dispatch/result/presentation
witness. Reuse it where its domain applies. Do not repeat a full walkthrough,
save/reopen, pixel sweep or unchanged arithmetic proof for each new description.

Stop when the declared claim is supported or an unresolved dependency prevents
it. Return the useful accepted subset and the next blocking question. Measure
time to first useful Z action, actual source lowering, acceptance, native binding,
context transitions, cache reuse and unknown frontier separately. Machine-only
rebuild times must not be advertised as cold analyst recovery times.
