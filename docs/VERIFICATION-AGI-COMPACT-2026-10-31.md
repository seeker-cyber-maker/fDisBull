# Compact AGI control flow: verification

2026-10-31. Follow-up to PR #71, based on
`73256035840302017dcb475fc1fa0fc2a19a1799`. This is engine development, with
no tag, release or system installation change.

## Implemented contract

The opt-in `module-lift --control-flow compact` uses shared `fdisbull-il-2`
continuations and the AGI projection wrapper `fdisbull-agi-state-projection-3`.
UDL and UIL retain the same primitives and differ only by role. Each admitted
source location appears once; branch joins and repeated callee calls refer to
it rather than copying its body into each path. The default tree format stays
available. The AGI processor/module descriptor revision is 3.

Transfers model goto, condition, call, return and component stop with a bounded
runtime resume stack. A global stop in a callee preserves the suspended caller.
If all callee paths stop, no caller continuation is admitted; an unexpected
return through a null resume refuses. Both branch alternatives are compiled,
independent of initial-state witnesses. Source cycles, recursive/dynamic calls,
unknown instruction widths and unsupported predicates remain refused.

Whole-graph validation includes inactive and unreachable bodies, target
references, typed values and unique IDs. The 64 KiB document, 1,024-node and
32-level structural bounds remain. Execution counts continuation entries and
body operations against the step budget, and preserves atomic refusal and
pending host-plan semantics. Source-entry trace IDs and runtime control stacks
remain distinct. Existing scene and source-block/UDC proof consumers explicitly
reject v2 instead of ignoring its continuation table. Immutable IL storage
retains versioned documents and file-bound evidence checks across restart.

`--allow-opaque` is an explicit compact-only inspection option. Known action
encodings can be retained with source evidence as opaque blocks. Such a graph
is `control_flow_only`, and evaluation refuses before events or state changes,
even if the initial witness avoids those operations. No unknown effect is
converted into a no-op. The extra decoder facts cover the declared KQ1 action
set, not a complete AGI instruction table or engine implementation. Encodings
were checked against the pinned
[ScummVM v2 opcode table](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/opcodes.cpp).

## KQ1 logic 103

The private uncompressed v2 resource was read without running the original DOS
interpreter. The selected profile is an explicit 2.917 assumption. Entry zero
and artificial typed scalar inspection values are not observed runtime state.
The complete generated source-retaining graph remains outside the checkout.

An independent raw-byte traversal rebuilt source edges using the existing
profile-specific layout contract, without using the production compact
compiler/processor as the source-graph oracle. That shared width contract and
the production container loader are not independently proven by this check.
The raw reference uses unsigned IF and signed GOTO displacements; no high-bit
IF skip is present in this selected resource. Results:

| Check | Result |
| --- | --- |
| Unique source locations / compact continuations | 111 / 111 |
| Shared join targets | 12 |
| Source edges compared | 132; zero mismatches |
| Structural branch-choice paths | 922 source and 922 projection; zero sequence mismatches |
| Retained opaque action sites / distinct action opcodes | 56 / 22; zero source mapping mismatches |
| Compact IL JSON size | 56,714 bytes, below the unchanged 65,536-byte limit |
| Evaluation | Refused at opaque preflight; zero events and zero visited entries |
| Source integrity | LOGDIR and every inspected VOL hash unchanged |

The previous structural expansion estimate was 5,105 recursive source visits
for the same 111-node graph, with a longest path of 60 instructions. The new
representation stores shared continuations once. The 922 branch-choice paths
include structurally possible alternatives, not a claim that every sequence is
reachable under game state. This comparison establishes the selected source
control-flow structure, not scalar/effect parity, original-interpreter
execution, rendering, movement or a complete semantic lift of the routine.

The [sanitized receipt](evidence/agi-compact-2026-10-31/receipt.json) retains
counts, digests, implementation identities and scope. Original instruction
bytes, the generated graph and raw target traces are private. The public
`scripts/verify_agi_compact_graph.py` can repeat the leaf-graph check with an
explicit private source and projection. It is a structural verifier, not an
AGI interpreter or substitute for the debugger.

```text
python scripts/verify_agi_compact_graph.py \
  --logdir /private/game/LOGDIR --volume-dir /private/game --logic 103 \
  --profile 2.917 --projection /private/kq103-projection.json \
  --output /private/kq103-structural-receipt.json
```

The verifier preserves true/false edge identity and refuses altered evidence,
duplicate/moved opaque mappings, cycles, calls, path-budget exhaustion and
high-bit IF skips outside its current layout-check scope. Predicate equivalence
and scalar bodies are not checked by this structural script. Its receipt
contains counts and digests, with no original bytes, state or target paths.

## Authored executable checks

An authored 12-diamond graph represents 25 source instructions as 25
continuations and 12 joins. The old tree form refuses its expansion budget;
the compact form executes for all 256 byte selector values and matches an
independent expected final state. Additional tests compare source-entry traces
and state with the tree lifter for multiple callee returns, repeated calls to
one shared callee, and mixed stopping/returning callee branches. Tests cover
reused callees at deeper stack depths, unknown and truncated encodings,
inactive opaque operations, malformed unreachable graph entries, capability
preflight, loops/recursion budgets and refusal without partial effects.

A genuine optional Z3 check independently models the emitted acyclic shared
callee graph for all declared byte/Boolean inputs. Coverage is checked before
comparison; a differing output is UNSAT, and mutating a caller copy yields SAT.
The proof concerns only that authored graph and explicit nominal semantics,
not original KQ1 behavior or a general compiler-equivalence claim.

Fresh CPython 3.13.13/macOS ARM64 focused verification: **354 passed, 1 skipped**.
The skip requires a case-sensitive filesystem. This includes the new compact
compiler/evaluator/verifier/proof tests, existing AGI control/reference/layout,
decoder and processor tests, shared IL, CLI, scene, UDC/source-block, revision
storage, distribution and both bundled-skill checks. The receipt records the
same counts and implementation digests. Linux CI is separate evidence.

## CI and remaining gates

PR #71's exact head passed ordinary and complete native Linux CI, including
stable/layers DOSBox and installed-wheel DOS/boot/PE64 acceptance:
[ordinary](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41164350553),
[native](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41164350554).
The follow-up PR requires its own exact-head checks before integration.

A full semantic KQ1 routine still needs explicit object/resource, movement,
text and scheduler effects. Indexed variable banks, loops and other guest
predicates are separate qualifications. No game files, native states, project
databases or raw private deliveries are part of this change or tool packages.
