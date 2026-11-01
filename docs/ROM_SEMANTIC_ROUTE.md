# ROM → ASM → C → UIL: what is currently qualified

This route is **not qualified for Civilization Saturn as a whole**. A narrowly
authored arithmetic slice passes through actual Ghidra C and saturn-recomp C++
to accepted UIL, under explicit unsigned types and register bindings. Untyped
pseudocode and a tested second decompiler configuration fail qualification.
Instruction agreement and a successful text conversion do not preserve every
CPU effect or recover a game's domain meaning.

## Concrete experiment

The authored eight-byte SH-2 function is:

```asm
mov r4,r0
add #1,r0
rts
nop
```

The same bytes and mapping at `0x06010000` pass all three ROM-to-ASM modules.
The arithmetic observation boundary is output `r0`, with incoming `r4` bound
to an unsigned 32-bit value. Return control, PC/PR, other registers,
instrumentation, flags, memory, timing and game behavior are excluded.
The original byte pattern is recognized independently by an intentionally
small manual-encoding reader; it is not derived from either C output.

Ghidra's function prototype is explicitly supplied as unsigned input in
`r4:4` and unsigned return in `r0:4`. The permanent generator logs both storage
bindings. Its actual decompiled output is:

```c
uint authored(uint value) {
    return value + 1;
}
```

Here `uint` is explicitly assumed and compiled as `uint32_t`; the binding is
supplied by the experiment and is not recovered from Civilization.

The pinned saturn-recomp generator produces a C++ wrapper whose arithmetic is:

```cpp
c.r[0] = c.r[4];
c.r[0] += 1;
```

Its real runtime header declares `uint32_t r[16]`. The checker verifies the
pinned clean source/header, recognizes the complete emitted wrapper and declares
its return and instrumentation effects outside the register-result contract.
Saturn is a **static translator**, not an independent high-level C decompiler.

`rom_semantics.py` accepts only these exact unsigned function/wrapper shapes,
with a small nonnegative immediate. It refuses additional effects, signed or
unbound C, arbitrary expressions, pointers and unsupported control flow. C
keywords/reserved identifiers are refused. Lift documents retain source text
or bytes and hashes; comparison rebuilds them and refuses altered source,
metadata or UIL. This is a bounded source reader, not a general C/C++ parser.

The resulting executable `fdisbull-il-1` UIL is typed `u32`: copy `$r4` to
`$r0`, then add the constant. The checker validates and executes this document.
Z3 compares arithmetic models reconstructed from the validated source lifts
for **all 32-bit input values**. The result is `equivalent_under_assumptions`
for the declared arithmetic boundary. The accepted UIL shape is validated and
checked against a rebuilt lift separately; the solver does not independently
translate the UIL runtime's execution semantics.

An otherwise supported C `+2` mutant yields a solver counterexample, rather
than being accepted because it resembles the expected source. Compiling the
actual emitted C and C++ with explicit type/context harnesses also gives:

| Input r4 | Native C, native C++ and UIL result r0 |
| --- | --- |
| `0` | `1` |
| `0x7fffffff` | `0x80000000` |
| `0xffffffff` | `0` |

These three executions check the compiled edge cases. The all-input result
compares parsed models, not native machine execution or compiler correctness
for all inputs. The solver does not independently establish that the chosen
abstraction faithfully models every part of SH-2, C++ or UIL.

## Actual refusals

An earlier authored block consumed incoming `r0` without a supplied ABI.
Ghidra emitted a function with an unbound `in_r0` local and signed addition.
As standalone C this is not a defined, all-input representation of a 32-bit
register increment. The narrow lifter refuses it. This is evidence that raw
pseudocode requires register/type context, not evidence that Ghidra cannot
describe such an input under an appropriate calling convention.

Reko 0.12.5 lists a SuperH backend. Testing the same ABI-consistent eight-byte
sample with `--arch superH --arch-option Endianness=be`, explicit base and entry
logged an internal stack-pointer/platform error and produced an empty function,
despite process exit zero. That output is **unqualified**, not another passing
C route. An omitted-endianness attempt failed similarly. Other configurations
or versions remain untested; no general absence-of-support claim is made.
The receipt records both DLL identities and the observed error.

| Engine/output | Result in this experiment |
| --- | --- |
| Untyped Ghidra pseudocode | Refused: incoming register and defined unsigned semantics are missing |
| Typed Ghidra C with supplied ABI | Parsed register-result model and UIL agree under assumptions; native edge checks pass |
| saturn-recomp C++ | Same bounded result, with real unsigned register type and wrapper effects explicitly excluded |
| Reko SuperH configuration tested | Refused: internal error and empty output, even with exit status zero |

## Why this does not establish a general route

Equivalence composes only when every stage has the same declared observation
boundary and compatible assumptions. A register-result proof cannot be carried
over to a stage that silently excludes flags, indirect writes, memory layout,
exceptions or timing. Console memory-mapped I/O, endian-sensitive accesses,
bank state, overlays and SH-2 delay slots require explicit models. Inferred C
types can introduce signed overflow, pointer aliasing or missing volatile
effects; inferred calling conventions can discard observable register changes.

The Civilization intake currently supplies a first-read transfer mapping, not
an established application entry or complete executable code/data map. No real
Civilization function has been qualified through this C/UIL experiment. This
is a useful positive control and a set of failure gates, not game recovery.

The generated UIL still describes register arithmetic. It does not establish
that the value means a score, a resource, a rule or a player action. Recovering
those meanings needs separate evidence and domain contracts.

The design recommendation from these checks is to preserve bytes and typed
instruction/IR effects as the semantic authority, with C as an inspectable
intermediate view. C → UIL is usable for explicitly supported, defined subsets
when each edge is checked. A generic C decompiler output should not be treated
as a lossless interchange format. A broader typed-IR → UIL path remains work
to qualify; this PR does not implement it.

## Reproduction and evidence

The [permanent generation recipe](../scripts/rom_semantic_route/README.md) uses
the committed Ghidra Java script, authored bytes and pinned Saturn generator.
`scripts/check_rom_semantic_route.py` checks the three assembly outputs, parses
the actual generated C/C++, validates UIL, runs proofs and compiles the native
edge harnesses. Original games are never executed. The generator was rerun
from the committed Java source and the ABI log checked before collecting the
final receipt.

The [sanitized receipt](evidence/rom-asm-2026-10-30/semantic-route.json) retains
authored outputs, source hashes, supplied bindings, proof scopes, compiler
identities, edge results, generator-log hashes and negative findings. It is a
receipt of these observed runs, not cryptographic proof of generator execution.
Full native logs and generated files stay in the private experiment directory.
