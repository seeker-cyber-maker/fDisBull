# Testing each abstraction layer

The objective is to author UIL while retaining a checkable path to original
code. A passing final run cannot replace acceptance at each intervening layer.
Every comparison declares source/definition identities, input domain, observed
outputs, exclusions and the actual stopping boundary.

| Edge | Acceptance | Current evidence |
| --- | --- | --- |
| Original artifact to project/backings | Full-file hash, explicit resource inventory, complete nonoverlapping layout, immutable byte version. | MZ DinoPark, COM Zork and authored LLVM-assembled COM; definitions survive database reopen. |
| ASM to UDL mapping | Exact source span, native decoder facts, explicit live register interface; unsupported operations refuse. | Small MOV/ADD/SUB/INC/DEC profile; Capstone disagreement, truncated instructions and missing inputs are negative cases. |
| UDL to UIL | Same primitive nodes and bindings, role metadata only; retained source correspondence. | Exported roles and execution checks; no separate language is invented for the direction. |
| Source model to candidate UIL | Independently built transitions, satisfiable declared domain, equal declared outputs, preserved counterexamples and unavailable/unknown results. | Z3 bit-vector comparisons, wrapping cases, wrong candidate, changed-default and expression-budget refusals. |
| ASM to C view to UIL | Record how C was obtained; parse under explicit C numeric assumptions; compare with original ASM model. | Supported statement reduction and separate C reader; the view shares the ASM decoder. |
| UIL through UDL-backed UDC to DOS files | Every mapped candidate qualifies; no unsupported edit is silently dropped; emitted blocks/resources match their expected identities. | Stored original backings, checksummed compilation manifest, corruption/missing-block and no-clobber tests. |
| Emitted files to native behavior | Fresh original and emitted runs under matched observation boundaries; capture actual input, registers/state, stops and stored frames. | Authored keypress game, bounded Zork mailbox route, DinoPark office/bank/return route. |

The native acceptance example is checkout-only, at `examples/udc/README.md`.
It uses actual LLVM assembly,
DOSBox, key input, breakpoints, traces and stored-state screenshots. The tool
archives deliberately exclude `examples/`; obtain that directory from a source
checkout. The separate PR17 authored examples under `docs/uil-rfcs/0001/` and
the exact sanitized UDC receipts are explicitly included in source archives.

## Authored block game

The original COM is assembled from `synthetic_game.asm`, with object relocation
checks before extracting its code. Its qualified effect is AX + 200 - 1.
The native route enters with AX=10 and observes AX=209 and a stored u16 value
of 209 after a keypress. The game also produces actual completion text.

Three fresh native runs use the original assembly, ASM-derived UIL selected
through its original UDL backing, and ASM-derived C then C-derived UIL through
that same backing. The emitted native bytes are identical in all three cases.
Z3 checks the modeled register boundary for every u16 input, rather than only
the observed input 10. Changing the UIL increment to 201 produces a
counterexample and no compiler output.

Five further native probes on each file use paused AX and instruction-pointer
edits from a post-completion checkpoint. Inputs 0, 1, 65336, 65337 and 65535
produce 199, 200, 65535, 0 and 198, respectively. Actual AX, the stored u16
and the UIL result agree. These are assisted CPU/model probes, recorded
separately from the ordinary keypress route.

The native runs check concrete source-model boundaries. The solver checks the
modeled relation over its declared domain. Neither result alone proves the
source model's full fidelity to every CPU or caller observation.

## Extending coverage

New rules should first add negative cases and an independent observation or
model. Memory rules need aliasing and address-space contracts; branches need
guard and path coverage; calls need frame, clobber and continuation contracts.
Flags, clocks, external effects and partial failure require explicit semantics.
Do not widen the current register-only claim by attaching extra evidence.

C may make structured control flow and human naming easier to express. This
first straight-line example does not establish a general C-versus-ASM winner.
A fuller C route must also qualify its decompilation step, types and numeric
behavior. Keep assembly-backed implementations available while that coverage
is developed.

Qualification and optimization are separate. A missing measurement is not a
zero cost, and an equal final balance does not establish effect-order parity.
The current target learns no lowering rules and chooses no measured fastest
implementation. Follow-up work can replace individual original backings with
qualified DOS emission while keeping the shared UIL contract.
