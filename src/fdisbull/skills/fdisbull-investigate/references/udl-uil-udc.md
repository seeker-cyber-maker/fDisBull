# Source-backed semantics: UDL, UIL and UDC

The `build-web-block` JSON method emits one canonical, pure selected UIL
invocation for `wasm32-scalar-1` or `webgpu-wgsl-scalar-1`. Inspect the actual
tool's `methods` first. Selection target metadata alone does not add a backend.
The build guards byte/word types and contract/layer domains, qualifies the
selected model and refuses extra effects/adapters. Its status is build-only;
run the emitted artifact and independently qualify original → UIL → output.
The JavaScript host returns pure values and never commits a delayed result to
application state. Services, revision checks and a complete shell remain a
separate composition gate. See repository `docs/UDC_WEB.md` for the finite
original-backed food study and its reproducible private recipe.

`build-web-shell` combines two such persisted selections with a separate typed
host plan. It requires identical module/contract identities and equal effective
admission domains. The shell owns record arenas and activation snapshots;
providers own compute resources. Stage a real result, then validate session,
entity generation, record revision, view/binding/operation/provider epochs before
an output-only commit. Readiness does not commit state. Cancelled GPU jobs keep
their device lease until settlement; replacement work queues, without fallback
or replay. Borrowed devices remain caller-owned. See `docs/UDC_BROWSER_SHELL.md`
for the fixed snapshot/invoke/guarded-commit profile, disposal cutoff and source
qualification; this does not imply general native-shell or whole-game support.

For first use and source-to-model acceptance, follow the
[repeatable reconstruction recipe](reconstruction.md).


Read this reference only when the task is to relate source operations to a
shared interaction representation or test a bounded source block. It is not a
general compiler manual.

## Contents

- [Keep the terms separate](#keep-the-terms-separate)
- [Preserve the accepted compiler priority](#preserve-the-accepted-compiler-priority)
- [Current DOS block boundary](#current-023-dos-block-boundary)
- [Persistent snippets and selectable block layers](#persistent-snippets-and-selectable-block-layers)
- [Zork IR and recovered intents](#zork-ir-and-recovered-intents)
- [Read a proof narrowly](#read-a-proof-narrowly)
- [Bytecode inspection and runtime qualification](#do-not-conflate-bytecode-inspection-with-runtime-qualification)

## Keep the terms separate

- **UDL** is the source-to-shared-IL mapping role.
- **UIL** is the candidate shared-IL program.
- **UDC** is a target compiler definition that reads UIL and binds its declared
  behavior to an implementation. The original DOS profile can select retained
  block backings. The selectable-layer prototype adds immutable contracts,
  isolated CPU providers and separately admitted native output profiles.

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
shared decoder lineage. General generated DOS lowering, richer process/object models,
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

## Persistent snippets and selectable block layers

The block-layer prototype persists source captures, authored cross-project
relations, typed contracts, UDL implementations and explicit selections.
`capture-snippet` accepts ordered `{address,size}` spans from an immutable mapped
version or `{file,offset,size}` spans from retained files. `file:"source"`
means the original source in version 1. Endpoint identities retain source,
byte-version, architecture/view, context and span hashes. NE indices remain
logical segment identities; a DOS CS context is separate from a physical address.

Read `snippet-info` and record lists with compact defaults. `full:true` returns
metadata documents; native payloads require the explicit `include_bytes:true`
request. Projects, byte-bearing exports, compiler capsules and original game
files remain outside Git. Copied metadata endpoints are external declarations,
not silently locally verified source. A relation needs its admitted domain,
evidence, assurance and unknowns; graph connectivity does not establish
equivalence or grant execution authority.

Use `store-block-contract`, `store-udl-layer` and `select-udl-layers` to register
supported profiles and pin exact contract/layer IDs. Python execution helpers
are in `fdisbull.udc_layers`: `register_contract`, `register_layer`,
`select_layers`, `run_layer` and `run_selection`. Persistence's `store_*` methods
validate structure and references; the execution helpers also admit behavioral
and backend profiles. A candidate's stored assurance is an authored declaration.

Keep exact behavior separate from deliberate variation. A shared-IL behavior
contract fixes its declared results and event plans. A bounded RNG policy may
explicitly permit different seed algorithms/sequences, but matching a u16 range
does not prove fairness, period, determinism or original sequence compatibility.
ADD and ADC are interchangeable for a sum only when their carry dependency is
discharged or included in the contract. An invocation that happens to match is
finite evidence. Unobserved flags do not become proved equivalent.

`fdisbull-module-uil-1` adds contract-bound `invoke` and unsigned `remainder`
through `run-module-uil` / `fdisbull.udc_blueprint.execute_module_uil`. It is a
separate profile; `fdisbull-il-1` primitives are unchanged. It validates exact
selected contracts and typed ports in untaken branches, bounds execution, and
retains modeled refusal state. It does not undo an effect in an external process.

The native x86-16 provider executes selected bytes in an isolated CPU through
explicit register/memory/segment/scratch adapters; it requires the optional
`udc` dependency. This is not a running DOS or Win16 process. Recovered source
data/pointer/caller assumptions still need evidence. Pure scalar Z3 admission
qualifies supplied IL completion/output models only; unknown, unsupported or
counterexample results do not become native equivalence.

`compile-udc-splice` emits a new hash-bound COM artifact through an explicit
placement/data recipe. Keep reusable math separate from target offsets,
seed loads/stores, ABI adapters and continuations. The first profile is limited
to a 65280-byte COM image and is not a general DOS linker. `build-udc-shell`
emits a new PE64 shell from supported selected UIL and notification modules.
The first selected PE bridge admits canonical port maps and rejects nonempty
extra contract/layer domains until native guards exist. Its notification service
is ui.notify, not a file/media service. Generated bytes, imported PE structure,
native execution and visible provider effects are distinct evidence gates.

Logical services such as future read_file ports can connect DOS or Windows
source provenance through explicit handle/buffer/status adapters. Current notify
providers do not implement that service. This is not an automatic BIOS sweep.
Different providers may have separate state arenas if their ports and adapters
declare authority, transfer and failure semantics. Never retry another provider
after unknown or partial effects as though no action occurred.

Source-checkout `docs/UDL_BLOCK_LAYERS.md` supplies concrete API examples,
formats, policy distinctions, first-profile limits and verification boundaries.

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

## Linux and generated C realization

`build-udc-shell` additionally accepts `target:"linux-x64"`, explicit
`service_adapters`, optional Linux `capture_state` and `c_compiler`. The default
remains Windows PE64. The Linux output uses the shared private math ABI inside a
static ELF64 shell; its public System V entry and Linux services are adapters.
A notification needs the explicit linux-stdout/no-acknowledgment profile. A UI
provider change is not automatically effect-equivalent.

`implementation.backend:"c-uil"` realizes supported pure word-scalar UIL as
generator-owned freestanding C through an explicit Clang executable. It retains
source, compiler, object and native text identities. This is not a general C
parser or an independent source oracle. Native object relocations, unsupported
effects/types and unimplemented contract profiles refuse. Model qualification,
source preservation, compiler output and native execution remain separate.
Capture descriptor3 observations only in the explicit analysis profile, validate
complete frames and bind the executable/process identity before making claims.
Source-checkout docs/UDC_LINUX_AND_C.md records the actual pilot and limits.
