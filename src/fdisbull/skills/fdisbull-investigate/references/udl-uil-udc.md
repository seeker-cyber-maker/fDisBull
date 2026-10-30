# Source-backed semantics: UDL, UIL and UDC

Read this reference only when the task is to relate source operations to a
shared interaction representation or test a bounded source block. It is not a
general compiler manual.

## Contents

- [Keep the terms separate](#keep-the-terms-separate)
- [Preserve the accepted compiler priority](#preserve-the-accepted-compiler-priority)
- [Current DOS block boundary](#current-023-dos-block-boundary)
- [Zork IR and recovered intents](#zork-ir-and-recovered-intents)
- [Qualified Zork scene rules](#qualified-zork-scene-rules)
- [Read a proof narrowly](#read-a-proof-narrowly)
- [Bytecode inspection and runtime qualification](#do-not-conflate-bytecode-inspection-with-runtime-qualification)

## Keep the terms separate

- **UDL** is the source-to-shared-IL mapping role.
- **UIL** is the candidate shared-IL program.
- **UDC** is a target compiler definition that reads UIL and binds its declared
  behavior to an implementation. The currently qualified fDisBull target checks
  a candidate and can select retained original DOS block backings.

For v1 `fdisbull-il-1`, UDL and UIL are role metadata over the same primitive
nodes and evaluator; changing role does not perform a translation. The separate
interaction evaluator validates an authored program and may return
`pending_host` for graphic, sound or input effects. It does not perform those
side effects or establish correspondence with a game's behavior. See
source-checkout `docs/INTERACTION_IL.md` for the complete schema and limits.

## Preserve the accepted compiler priority

Start with the supported original-backed DOS path: capture unchanged native
blocks and source identities, retain opaque dependencies and explicit resources,
then qualify bounded ASM-to-UIL mappings at the declared source/effect boundary
before selecting a backing on a semantic-equivalence claim. An unmapped
byte-preserving baseline remains `original_bytes_only`; unsupported edits
remain refused.

The supported reduced-C route retains its derivation from the ASM lift and its
shared decoder lineage. Generated DOS lowering, richer process/object models,
automatic cross-language propagation and compiler learning remain future work.
Separately authored Rust/JavaScript/Python examples are conformance seeds, not
existing general translators or the first implementation target.

Qualification precedes optimization: compare candidates with compatible
semantic, input-domain, capability and assurance contracts, then measure cost
on comparable inputs and conditions. Retain unsupported effects and the
original-backed fallback; an unmeasured candidate is not free.

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

A qualified block can explain part of an operation without establishing its
complete intent. Use [semantic-contracts.md](semantic-contracts.md) to retain
guards, intermediate effects, interface/event evidence, time and persistence.
For a source claim, inspect the relevant control, read/write and helper
dependencies under a satisfiable domain. Unresolved relevant helpers block a
complete-handler claim; an independently supported narrower output claim may
still be useful. Label manually authored models as such and keep unsupported
operations explicit. This reasoning does not expand the installed lift profile.

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

## Zork IR and recovered intents

The supported v3 story converter preserves an executable word16 representation
for an independent player. Its legacy `zork-uil` command names that low-level IR;
successful play alone does not establish recovered game intent. For the qualified
Zork I R88 edition, `zork-intents` exports a separate address-free mailbox and
action-counter definition with source-linked UDL bindings. Parser, scheduler,
unsupported interactions and unresolved effects remain explicit IR.

```text
fdisbull zork-uil STORY --output PRIVATE-IR.json.gz --mapping PRIVATE-MAPPING.json.gz
fdisbull zork-intents STORY --ir PRIVATE-IR.json.gz --output PRIVATE-INTENTS.json.gz
fdisbull-player --intents PRIVATE-INTENTS.json.gz --checkpoint PRIVATE-CHECKPOINT.json
```

Use new output paths outside Git: these packages retain story data and checkpoints
retain game state. Compare complete source-bound observations and ordered effects,
and establish that the intended primitives actually ran instead of counting a
fallback-only route as semantic recovery. Source-checkout `docs/ZORK_UIL.md` and
`docs/ZORK_INTENTS.md` describe the edition, format and verification bounds.

Intent execution can fault after partial effects. Its recovery segment lists
completed effect calls and marks an interrupted effect unknown; it performs no
automatic rollback or fallback after mutation. A preflight fault has a separate
receipt. Retrieve the receipt before another action. The CLI keeps the last
successful checkpoint on failure; explicitly resume from that checkpoint rather
than treating a faulted runtime as a fresh attempt. Native host-file effects and
an independent player's checkpoint have different persistence boundaries.

### Qualified Zork scene rules

For the exact qualified Zork I R88 source, `zork-scenes` adds named scenes,
directional rules, live conditions and doors, ordered refusal effects and resolved
dispatch links. Its UIL uses semantic identities; original object numbers,
packed addresses and operation witnesses remain in the UDL correspondence.

```text
fdisbull zork-scenes STORY --intents PRIVATE-INTENTS.json.gz \
  --output PRIVATE-SCENES.json.gz --uil PRIVATE-SCENE-RULES.json \
  --dispatch PRIVATE-DISPATCH.json --udl PRIVATE-SCENE-UDL.json.gz
fdisbull-player --scenes PRIVATE-SCENES.json.gz --checkpoint PRIVATE-SCENE-CHECKPOINT.json
```

The current producer retains and validates the existing intent/IR package.
Scene selection, admitted on-foot relocation and residual arrival behavior have
separate effect boundaries. A resolved callback identity does not recover its
body; parser behavior, condition setters and unresolved handlers remain explicit
IR. Source-checkout `docs/ZORK_SCENES.md` specifies the supported package and
execution contract. Read [scene-recovery.md](scene-recovery.md) for the procedure
that starts from required scene elements; its proposed analysis steps do not add
a general slicing pass or change the installed exporter's prerequisites.

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
receipts live in source-checkout `docs/UDC_DOS.md`, `docs/UDC_TESTING.md`,
`docs/BOUNDED_PROOFS.md` and `docs/VERIFICATION-0.23.md`.

## Do not conflate bytecode inspection with runtime qualification

The `agi-logic` command is a bounded read-only decoder for one AGI 2.917 LOGIC
resource in a version-2 LOGDIR/VOL set. It helps locate candidate tests and
actions; it does not prove that a resource was loaded or executed. For a runtime
claim, qualify the file-to-memory or interpreter-fetch link and trace the
relevant branch and effect. A byte sequence that resembles a proximity guard is
not enough to authorize a semantic mapping or guard waiver. See the interpreter
and cross-file sections in [methodology.md](methodology.md) and the AGI source
documentation `docs/AGI_LOGIC.md`.
