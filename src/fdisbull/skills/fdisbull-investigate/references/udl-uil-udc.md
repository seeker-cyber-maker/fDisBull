# Source-backed semantics: UDL, UIL and UDC

Read this reference only when the task is to relate source operations to a
shared interaction representation or test a bounded source block. It is not a
general compiler manual.

## Keep the terms separate

- **UDL** is the source-to-shared-IL mapping role.
- **UIL** is the candidate shared-IL program.
- **UDC** is the DOS original-backed compiler definition that checks a UIL
  candidate and can select its retained original backing.

For v1 `fdisbull-il-1`, UDL and UIL are role metadata over the same primitive
nodes and evaluator; changing role does not perform a translation. The separate
interaction evaluator validates an authored program and may return
`pending_host` for graphic, sound or input effects. It does not perform those
side effects or establish correspondence with a game's behavior. See
`INTERACTION_IL.md` for the complete schema and limits.

## Current 0.23 DOS block boundary

UDC currently accepts original static x86-16 MZ or COM version 1. It rebuilds
the original files byte-for-byte from immutable project backings, including
opaque regions and explicitly attached resources. It does not generate DOS
machine code, relocate a new program or recover a whole game into UIL. A
definition with no qualified semantic blocks is an `original_bytes_only`
reconstruction.

The semantic ASM profile is a complete straight-line 16-bit register subset:
immediate MOV, supported AX ADD/SUB and register INC/DEC. Source spans must
match original file bytes and supported loader conditions; memory, pointers,
branches, flags and ABI effects are refused. These lifts retain the original
native bytes as the available implementation backing.

For an authored source block, the CLI paths are:

```text
fdisbull udl-lift-asm BLOCK --bindings BINDINGS.json --input ax --output-register ax --output LIFT.json
fdisbull udl-lift-c SOURCE.c --bindings BINDINGS.json --input ax --output-register ax --output LIFT.json
fdisbull udl-verify LIFT.json CANDIDATE-UIL.json --output PROOF.json
```

Every path, binding, register interface and source extent is caller-supplied.
Check the source offset against the exact original bytes before mapping a real
program. A small supported sequence in one file does not establish a function,
reachable path, calling convention or complete game rule.

Persisting and using an original-backed DOS definition is intentionally more
explicit:

```text
fdisbull udc-capture PROJECT.fdb NAME --blocks BLOCKS.json --resources RESOURCES.json
fdisbull udc-info PROJECT.fdb DEFINITION
fdisbull udc-programs PROJECT.fdb DEFINITION --role uil --output UIL.json
fdisbull udc-compile PROJECT.fdb DEFINITION NEW-OUTPUT --programs UIL.json
```

`BLOCKS.json` contains the `semantic_blocks` list. `RESOURCES.json` maps output
paths to files already attached to the project; inputs are not discovered from
arbitrary host paths. The output directory must be new and outside Git. Use the
default `udc-info` reply before requesting `--full`; game bytes and block
catalogs are not printed by default.

## Read a proof narrowly

`udl-verify` uses the optional Z3 dependency to compare a source block model with
a candidate UIL program over the declared register inputs and outputs. The
result `equivalent_under_assumptions` means only that those modeled outputs
match under the recorded assumptions. A `counterexample` is an input to
investigate against the original, not an observed original result;
`unavailable`, `unknown`, invalid input or unsupported semantics do not
establish equivalence. Check that assumptions are satisfiable, that the
modeled source span is correctly interpreted, and that the observed program
boundary matches the claim. A proof does not validate the source model against
all processor, memory, flag, timing, caller or external-effect behavior.

The bounded C-like route is a view from the supported ASM lift. It shares the
ASM decoder and uses a separate restricted statement reader; it is not a general
C/C++ decompiler or an independent source oracle. Retain the derivation and
numeric assumptions when comparing C and ASM models. More details and test
receipts live in the source documentation `UDC_DOS.md`, `UDC_TESTING.md`,
`BOUNDED_PROOFS.md` and `VERIFICATION-0.23.md`.

## Do not conflate bytecode inspection with runtime qualification

The `agi-logic` command is a bounded read-only decoder for one AGI 2.917 LOGIC
resource in a version-2 LOGDIR/VOL set. It helps locate candidate tests and
actions; it does not prove that a resource was loaded or executed. For a runtime
claim, qualify the file-to-memory or interpreter-fetch link and trace the
relevant branch and effect. A byte sequence that resembles a proximity guard is
not enough to authorize a semantic mapping or guard waiver. See the interpreter
and cross-file sections in [methodology.md](methodology.md) and the AGI source
documentation `AGI_LOGIC.md`.
