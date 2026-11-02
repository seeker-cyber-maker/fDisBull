# Source-backed semantics: UDL, UIL and UDC

Read this reference only when the task is to relate source operations to a
shared interaction representation or test a bounded source block. It is not a
general compiler manual.

## Contents

- [Bounded-memory web and macOS shells](#bounded-memory-web-and-macos-shells)
- [Keep the terms separate](#keep-the-terms-separate)
- [Preserve the accepted compiler priority](#preserve-the-accepted-compiler-priority)
- [Original-backed DOS block boundary](#original-backed-dos-block-boundary)
- [Overlapping instruction backings](#overlapping-instruction-backings)
- [Persistent snippets and selectable block layers](#persistent-snippets-and-selectable-block-layers)
- [Zork IR and recovered intents](#zork-ir-and-recovered-intents)
- [Qualified Zork scene rules](#qualified-zork-scene-rules)
- [Multi-scale Z worlds and larger scenes](#multi-scale-z-worlds-and-larger-scenes)
- [Native console UDC, replay and synthesis profiles](#native-console-udc-replay-and-synthesis-profiles)
- [Read a proof narrowly](#read-a-proof-narrowly)
- [Bytecode inspection and runtime qualification](#do-not-conflate-bytecode-inspection-with-runtime-qualification)
- [Linux and generated C realization](#linux-and-generated-c-realization)
- [Windows x86/x64 and Linux bounded-memory desktop realization](#windows-x86x64-and-linux-bounded-memory-desktop-realization)
- [Win16 segmented memory shell](#win16-segmented-memory-shell)
- [Direct guest-language front ends](#direct-guest-language-front-ends)

## Bounded-memory web and macOS shells

The separate `fdisbull-memory-uil-1` profile admits fixed unsigned word arenas,
indexed loads/stores and bounded loops. `store-memory-block-contract`,
`store-memory-udl-layer` and `select-memory-udl-layers` retain exact program,
function, source and target identities in the existing immutable database.
`build-memory-web-block` emits Wasm/WGSL and `build-memory-web-shell` combines
per-function selections with an explicit canvas/input orchestration plan.
These methods do not make scalar contracts accept arrays or arbitrary services.
Qualify original -> memory UIL -> emitted execution separately, then compare
ordered inputs, carried state and complete frames through the shell. Preserve
source-assisted versus blind recovery, diagnostic RAM interventions, cursor/font
projection and clock-adapter limits. See `docs/UDC_MEMORY_BROWSER.md` in a source
checkout for the bounded contract, ownership rules and Snake reproduction.

An inline region does not dynamically consult another function's selected
backing. For that experiment, `build-memory-web-shell` accepts a separately
hash-bound `fdisbull-memory-cuts-1` document. It requires exact contiguous
callee-body equality after removing only IDs/evidence, no loop ancestor or
local live-ins, and separately bounded continuation phases. Preserve the
canonical UIL hash. Qualify the derivation, source budget and memory domain,
then check actual nested invocation receipts under independent bindings and
compare carried original state/frames. Output equality by itself does not show
that routing occurred. Unsupported cuts must refuse rather than guess a stack
or silently reuse the inline implementation.

For named one-store subregions, use the separate memory-region contract/layer
methods and `build-memory-web-shell`'s `regions` parameter. Preserve the canonical
UIL and distinguish its digest from the derived execution view and each actual
implementation digest. Exact defaults must match the source expression.
Intentional behavior variants require explicit policy opt-in and their own
assurance; keeping the source document unchanged does not establish semantic
equivalence. Test both current-seed/state preservation at selection and the
subsequent actual invocation, capture algorithm and backend choices together,
and qualify original fidelity separately from the desired changed behavior.
The current region profile permits one pure store expression, literal reads,
one guarded output word and one source charge. It is not arbitrary code splicing.

`build-memory-macos-shell` retargets the same bounded-memory source selections,
cuts and regions to native ARM64 blocks and AppKit adapters. Preserve old layer
target metadata as source provenance and inspect the new native realization
hashes. Native compilation is build-only; qualify the actual dylib/application
against original state and complete raster data. This shell has one synchronous
main-thread owner, guarded staging and terminal close. Snapshot final quit state
before teardown. AppKit responder tests with constructed `NSEvent` objects and
offscreen `drawRect` establish a different edge from physical hardware/window
hit-testing. See source-checkout `docs/UDC_MEMORY_MACOS.md` for the exact ABI,
ownership, diagnostic modes and private Snake reproduction.

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

## Keep the terms separate

The additive `fdisbull-common-uil-1` profile uses indexed typed variables,
constants, functions and imports. `uil-catalog` groups exact normalized models
from admitted scalar/memory, restricted C/Python and decoded register instruction
inputs. `uil-run` evaluates owned frames; `uil-compile` emits standalone
Python/JavaScript and records actual selected shims. Presentation binds values
and resources; orchestration selects implementations. `uil-fold`/`uil-expand`
retain exact lower-level children; labels never substitute for matching model
content. Source correspondence and native/host qualification remain separate.
See source-checkout `docs/COMMON_UIL_CONTRACT.md` and the conformance study for
schemas, public examples, original-kernel evidence and explicit limits. This
profile does not rename or widen the legacy formats below.
Read [common-uil.md](common-uil.md) for a complete installed-package example.

- **UDL** is the source-to-shared-IL mapping role.
- **UIL** is the candidate shared-IL program.
- **UDC** is a target compiler definition that reads UIL and binds its declared
  behavior to an implementation. The original DOS profile can select retained
  block backings. The selectable-layer prototype adds immutable contracts,
  isolated CPU providers and separately admitted native output profiles.
- **Recovery harness:** an executable interface that observes and operates a
  backing, manages experiment boundaries and checkpoints, and records evidence.
  Its named observations, actions, guards and bindings form an architectural
  precursor to explicit UIL contracts, continuing as a test platform as
  backings are replaced.
- **Z:** an optional scene, object, relation, action and observation interface
  for an agent-facing world. The world owns authoritative state and behavior; a
  scene is a bounded observer view at a declared execution boundary. Z can
  operate a source-backed harness during recovery, expose recovered UIL through
  a selected realization, or supply authored behavior that lowers into UIL.

The recovery direction is supported by a feedback loop through the harness:
`waexecution` records qualified physical execution facts and restore coverage;
`waorchestration` uses those facts to connect logical objects, typed values,
dependencies and behavioral boundaries. Z names the observations and actions
used to investigate and test those boundaries. A checkpoint supplies both the
starting witness for an experiment and the state relation for comparing an
original-backed operation with a candidate. In a source checkout,
`docs/UDL_UIL_UDC_CONSOLIDATED.md` consolidates all schemas and profiles.

A register name does not define a permanent logical variable. Bind physical
definition/use occurrences or valid location intervals to logical values, slots
or object views. Preserve widths, overlapping views, aliases, lifetime, control
dependencies and relevant flags/faults. Internal value versions support
analysis without changing the mutable UIL slot grammar. Unobserved temporaries
may disappear from the portable contract; physical live-outs required by a
retained continuation remain an adapter obligation.

A qualified pass-through backing can retain opaque internal registers and
storage. Values and effects that cross its boundary still require an explicit
relation, which may initially be a coarse retained machine-context dependency.
Pass-through postpones internal abstraction; it does not remove entry,
continuation, runtime, state-ownership or effect obligations.

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

## Original-backed DOS block boundary

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

## Overlapping instruction backings

For the baseline direct UDL-to-UDC route, prefer `udc-native-capture`,
`udc-native-info` and default `udc-native-compile`. This immutable definition
keeps native backings and a logical multi-instruction block plan without
requiring UIL. Original-layout pass-through reproduces the entire retained
version-1 file byte-for-byte, preserving shared bytes and original offsets.
Incomplete analysis does not prevent exact byte retention; graph confidence
is reported separately and becomes unknown when stored facts cannot be verified.

`code-blocks` groups unique contiguous fallthroughs, splitting at admitted
entries, branch targets, joins, outside incoming edges and explicit captured
instruction IDs. The plan is unplaced and source layout is unchanged. One
intent can span several such blocks; grouping does not automatically recover
intent. Keep behavior identity, native backing, source offsets and final
placement separate.

Choose `udc-native-compile --mode relayout` only for an explicitly admitted
placement experiment. `--block-order FILE` places logical groups; `--order FILE`
is the separate instruction-order seam. They cannot be combined. Output entry
maps, source occurrences and fixups replace source-offset arithmetic. Arbitrary
implementation replacement and complete DOS executable generation remain
future compiler work. Source-checkout `docs/NATIVE_UDL_UDC.md` documents the
pass-through, splitting and layer-by-layer testing contract.

Use `code-backings PROJECT --entry ADDRESS` (repeat entries as needed), or
`Project.code_backings(entries)`, to capture exact stored x86 16/32-bit
instruction interpretations. A byte may be an immediate on one entry path
and an opcode on another. Each backing owns its complete local encoding;
physical-byte coverage counts the shared source once. Stored incoming paths,
byte roles, explicit continuations and source/backing revisions remain visible.
Explicit code/code ranges may overlap; data/code conflicts remain refused.

`code-layout` / `Project.code_layout` captures fresh and emits a bounded raw
layout with remapped direct near branches and explicit fallthrough jumps.
Require the complete captured graph and all five explicit caller assertions:
`no_code_reads`, `no_code_writes`, `no_computed_entries`,
`address_identity_unobserved` and `timing_unobserved`. These are domain claims,
not facts established by setting them to true. Indirect/far transfers, calls,
mixed contexts and unsupported relocation/alias requirements remain refused.
The output is `structural_only`, with source occurrences, glue and fixups;
it is not a regenerated MZ/LE file, semantic UIL or general equivalence proof.

The Python helpers `materialize_code_backing` and `validate_source` live in
`fdisbull.code_backings`; standalone `compile_code_backings` lives in
`fdisbull.code_layout`. Validation against a newer patch version rejects a stale
capsule; explicitly selecting its retained parent still works. The source
validator re-queries the requested stored graph; a public digest alone does
not authenticate caller-supplied evidence. Preserve incomplete captures as
incomplete and qualify native behavior separately. Source-checkout
`docs/CODE_BACKINGS.md` gives the schema, CLI examples and bounds. Keep private
byte-retaining capsules and emitted code outside Git. No physical-overlap
operation was added to UIL; unsupported effects remain native residuals.

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

### Multi-scale Z worlds and larger scenes

A scene can expose a room, tactical district, settlement, continent, resource
network or off-map destination. Overlapping views preserve entity identity and
share authoritative state. Geometry, topology, containment, ownership,
dependencies and view membership remain distinct. Changing observation scale
does not authorize changing simulation scope. Current, remembered and unknown
fields govern public query membership and counts. Continuations bind observer,
view and execution epoch; restored values do not revive old tokens. UIL slot IDs
remain scoped to operations and invocation bindings, while world entities bind
through object/field identities and recovered lifetime relations.

Rewind selects both a return boundary and an explicit restoration policy.
Preserve the existing TAS option for gameplay rewind with continued random
progression, used to retry room entries with random events or locations. Exact
repetition requires matched RNG and other nondeterministic inputs; exploratory
retries use a deliberately different random context. Record the selected policy
and actual context in the branch evidence. Pointwise original/replacement
comparisons must use matched or explicitly related random contexts.

## Native console UDC, replay and synthesis profiles

`console-udc-targets` lists a shared unsigned eight/16-bit UIL subset for NES
and Genesis. `console-udc` accepts `path`, `target`, `output` and optional
`display_variable`; output must be a new private directory outside Git. Both
targets generate native instructions, console startup and a controller loop.
Compilation validates structure and bounds and reports `executed: false`.
Runtime qualification remains a separate receipt. The source-checkout
`docs/CONSOLE_UDC.md` records real emulator checks and an actual bounded Genesis
machine-code → UIL → NES route with explicit RAM bindings. That initial lifter
accepts a straight-line generated function pattern, not arbitrary game code.

The separate `fdisbull.udl_genesis.lift_native` profile accepts a bounded native
RAM function with explicit source range, RAM bindings and address-register
assumptions. It handles selected byte/word arithmetic, tests and forward branches;
unknown effects fail closed. Source-checkout `docs/GENESIS_ROM_TO_NES.md` records
a real Miniplanets function tested against controlled execution of the original
ROM and native NES output. This is a RAM-state projection, not a whole-game port
or evidence that ordinary gameplay naturally reached the function.

`fdisbull.udl_miniplanets.lift_level` specializes the exact official REV04 ROM's
first level into standard UIL with immutable tables, plus separate NES scene
metadata. Pass both to `write_console_rom`, or replay saved inputs with
`console-udc --target nes --scene scene.json`. This is reviewed source-bound
recovery, not generic 68000 decompilation. Source-checkout
`docs/MINIPLANETS_NES_LEVEL.md` records playable controls, original CPU checks and
aligned natural Genesis/NES replays, plus rendering/reset and score/time exclusions.

For repeatable procedural game, display-planner and PSG audio synthesis across
targets, inspect `genesis-replay-profiles`, `genesis-replay-source`,
`genesis-replay-inspect`, `genesis-replay-export` and `genesis-replay-build`, or
`rom-game-lift` for the reviewed full-game Miniplanets profile. Builds emit into
a new private directory for banked NES (`--cc65-root`) or native Genesis
(`--m68k-root`). `genesis-replay-source` checks whether a supplied ROM matches a
reviewed semantic profile; it does not perform generic 68000 decompilation
(`docs/MINIPLANETS_FULL_GAME.md`, `docs/GENESIS_UIL_REPLAY.md`).

For NES multicart packaging, use `nes-multicart-profiles`,
`nes-multicart-inspect` and `nes-multicart-build --authored-compatible`. Menu
and bank-switching synthesis requires explicit caller compatibility assertions
that iNES/NES 2.0 headers alone cannot prove, and advertised multicart counts
remain marketing labels rather than distinct-game counts (`docs/NES_MULTICART.md`).

For bounded Genesis and SNES Shadowrun profiles, inspect `shadowrun-opening-*`,
`shadowrun-systems`, `shadowrun-system-*`, `shadowrun-play-build`,
`shadowrun-ai-profiles`, `shadowrun-ai-build`, `shadowrun-city-export`,
`shadowrun-z` and `shadowrun-snes-build`. Each command operates on a declared
prepared state or bounded subsystem (movement, combat, Karma, Matrix, cyberdeck,
contacts or city/text projection) rather than recovering the full commercial
game. Native `macos-arm64` compilation is the active desktop realization for
combined Shadowrun slices, while NES outputs remain bounded research profiles
(`docs/SHADOWRUN_MACOS_ARM64.md`, `docs/SHADOWRUN_SNES_MACOS.md`,
`docs/GENESIS_NES_RESEARCH_HANDOFF.md`).

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
Source-checkout `docs/UDC_LINUX_AND_C.md` records the actual pilot and limits.

## Windows x86/x64 and Linux bounded-memory desktop realization

The same memory UIL, cuts and selectable region contracts can emit native
Win32/GDI and Linux x86-64/X11 shells with `emit-memory-desktop-shell` or
`build-memory-desktop-shell`. Source-only emission, native compilation, immutable
format/architecture/hash admission and runtime qualification are separate gates.
Stored Wasm/WebGPU selections remain source provenance; generated native
realizations record their actual targets and source identities.

The shell owns palette presentation, physical keys, pointer capture/coordinates,
selectors and monotonic clock. Native integer pixels use the same deterministic
center sampling for drawing and picking. Refused-call observation reads the
actual live core; final closed observations use a labelled owned snapshot.
Qualify full state, frame bytes and native surfaces on the same original inputs,
including wrong-adapter/refusal counterexamples. Programmatic window messages or
X server queue events do not establish physical hardware/global hit-testing.
`windows-x86` admits I386/PE32 and uses i686 MinGW; `windows-x64` retains
AMD64/PE32+ and its x64 compiler. Both use Win32 services with different pointer
ABIs. Windows execution under Wine does not qualify Microsoft Windows OS execution.
Source-checkout `docs/UDC_MEMORY_DESKTOP.md` documents APIs, recipes and limits.

## Win16 segmented memory shell

The same canonical memory UIL, cuts and selectable region contracts can emit
genuine Windows NE artifacts through `emit-memory-win16-shell` or
`build-memory-win16-shell`. The Python module is
`fdisbull.udc_memory_win16_shell`; separate compile/seal methods admit a real
Open Watcom build. Confirm all method names in the selected runtime before use.
This target uses generated C89 blocks and the Win16 ABI, not an x64 executable
with a different label.

Logical indices and arithmetic remain u32. A 70,000-word arena occupies nine
pages of at most 32 KiB, retaining all 280,000 logical bytes. Far-pointer offsets
and native 16-bit `size_t` never replace logical indexing. The cooperative owner
stages pages, captures region choices and checks budgets/guards/footprints
before committing declared ranges. Selector changes do not reseed or rewrite
state; an alternative RNG is an explicitly different variant.

The native host uses `_lread`/`_lwrite` for far-buffer streams and streams RGBA
and GDI strips within segment bounds. Actual buffered-stdio corruption in the
qualified compiler/runtime combination required this adapter; successful byte
counts did not prove correct contents. Check complete bytes on both file and
graphics seams. Chrome is CP1252, callbacks are far Pascal instance thunks,
pointer carriers are signed16 and fractional clock division is retained.

Source recipes, compiler/NE admission, native API observations and original
DOS/UIL/composed comparisons remain separate. Authored NE/GDI/input checks in
Wine 11 new WoW64 do not qualify original Windows 3.x, physical hardware or
whole-game behavior. Source-checkout `docs/UDC_MEMORY_WIN16.md` documents the
Python/JSON APIs, SDK recipe, storage and current limits.

## Direct guest-language front ends

Use a recognized guest language as input, keeping interpreter and story separate.
`decoder-modules` lists explicit trusted module identities and capabilities;
`module-analyze` opens AGI v2 logic or a qualified raw Z-machine v3 story without
native ASM or a project database. `module-lift` admits bounded acyclic scalar
AGI components: comparisons/isset with AND/OR/NOT, branches, direct logic calls
and scalar assignments/arithmetic/flags. Supply exactly all reachable read/write
`$agi_vN` u8 and `$agi_fN` bool initial values and an explicit code-relative
`callee_entries` witness for each captured call target. Cached scan-start need
not be zero. Never select a target from initial values for an unsupported
`call.v`, or prune an unsupported branch because the witness avoids it.

Use `entry_offset`, root `stop_offsets` and cross-resource `stop_points` to
declare a smaller observation component. A stop inside a callee ends the entire
component with its caller suspended; it cannot stand in for a returning callee.
The v2 projection retains exits, suspended frames and source-entry mappings for
IL `visited` IDs. Qualification is nominal state/control projection, not actual
interpreter execution. Cycles, recursion, parser/I/O operations and exhausted
budgets refuse qualification. Keep full-call, bounded call-entry and original
runtime evidence separate.

For many shared branches or repeated callees, use `control_flow="compact"`
(`--control-flow compact`). The v3 AGI projection uses `fdisbull-il-2`, with
one continuation per source location and explicit transfer/call/return/stop.
The original tree form stays the default. Map continuation IDs in `visited`
through `block_sources`; use `control_trace` for modeled runtime frames rather
than attaching one invented frame to a shared source node. Whole-graph
validation covers inactive branches, all targets and globally unique IDs.
State and event refusal remains atomic under execution or call-depth budgets.

Use `allow_opaque=True` (`--allow-opaque`) only for a declared structural
question. It retains known action encodings as explicit opaque operations and
marks the result `control_flow_only`. Such a graph refuses execution before
any events, even when the initial witness avoids the action. Unknown widths
and unsupported conditions still refuse construction. All typed initial values
remain caller-supplied; synthetic inspection values are not runtime evidence.
The KQ1 logic-103 comparison covers its selected CFG and structural branch-choice
paths, not state/effect parity or a working AGI game. Keep generated source-byte
graphs private; export only authored tests and sanitized counts/digests.
V1-only scene and source-block/UDC proof consumers explicitly reject v2 graphs;
do not flatten or omit continuations to get a misleading acceptance result.

For the bounded object/resource profile, select
`effect_profile="agi-2.917"` (`--effect-profile agi-2.917`) with compact control
flow. It lowers the declared 22 KQ1 action encodings to typed effect ports and
uses `object_resource_projection`, not a native-execution qualification.
Supply explicit object snapshots and captured VIEW geometry/messages. The
`agi_resources` helpers validate uncompressed DOS v2 resources; the declared
2.917 profile is an assumption requiring separate interpreter qualification.
`object_state()` creates a nominal model fixture, not a captured game object.

Drawing/erasing/messages yield a bound request and private JSON checkpoint.
Check proposed model values, then resume only with a matching explicit host
result. Readback without a result must preserve request identity and visits.
Do not infer collision safety, a displayed frame, dismissed dialogue, arrival,
or an elapsed guest tick from a planned operation. Motion ports configure
controllers; they do not advance them. Timers, renderer/collision work and
independent scheduler changes need another qualified host or observation.

The evaluator dispatches no GUI/native command. Its checksum and a supplied
`completed` result are not authoritative native completion evidence. Keep
caller claims distinct from provider receipts. If a later model failure reports
`recovery_required`, preserve prior `host_completions`, reconcile the host, and
resume the existing qualified route rather than assuming rollback or replaying
the original action. `state`/`effect_context` remain the model transaction's
baseline until completion; proposed fields are intermediate observations.
The 472-case KQ corpus uses synthetic snapshots and supplied host outcomes;
full model branch/site coverage is not proof of native reachability or parity.
Keep source-retaining graphs, contexts, messages and checkpoints private.

The separate Python `AGIDOSMonitor` / `AGIDOSHostAdapter` can now qualify one
original DOS KQ1 leaf invocation against its lifted graph. Bind the unpacked
interpreter, selected resource, initial fetch, current logic record and call
frame before advancing. Native source fetches include conditions and jumps;
handler completions must be observed, and return needs its actual stack
witness. Capture-key mismatches, foreign breakpoints/watchpoints, hooks, missing
frames, timeouts and unknown transport outcomes are incomplete or differences,
never equality. Readback cannot retry an operation. Keep prior native
completions even when the model or a later capture fails; reconcile or explicitly
restore before a new trial. The adapter's verified result covers the declared
final scalar/object projection with named exclusions, not every transient value
or whole-game parity. A returned print handler is not visual text recognition.
`examples/agi/verify_host.py` labels its synthetic caller/state interventions;
do not report them as ordinary gameplay or natural reachability. The standalone
model evaluator remains native-free.

For branch closure, use `aggregate_native_coverage` with complete source-bound
host receipts and keep expected, observed and missing source/effect/branch
sets. Counts must use completed native steps and distinguish actual branch
destinations; same-target outcomes stay unknown. Reject partial, duplicate or
foreign-source records. The aggregator validates caller records, not their
authenticity or whole-game equivalence. Prefer guided model cases to select
cheap discriminating native probes, then independently run each original path.

An explicit `dialogue_key="enter"` or `"escape"` host policy now qualifies an
untimed native message wait before sending one physical key. It binds RAM text
to source, checks the original wait/stack/window and idle keyboard, requires a
fresh stored preview after measured guest progress, and verifies window closure,
settled input and original return. Missing capture, foreign stop or lost input
response must preserve the attempted phase and cannot trigger a replay. Default
blocking behavior still stops incomplete. Source-linked diagnostic Z builders
can reuse checked messages and observed state changes with a separate player;
keep original text/generated content private and label authored commands,
projection loss, in-memory checkpoint limits and natural-route coverage.

Bind source occurrence using the snapshot key plus the module's resource-local
location. File offsets and guest offsets are different coordinates. Unknown
instructions, unsupported control flow, malformed source or budget stops refuse semantic
qualification. Prefer a cheap supported direct lift over recovering the same
guest operation from interpreter ASM, but retain ASM for unknown languages and
engine effects. A missing capability requires another scoped module or probe,
not an inferred implementation. Persistence, scene/Z recovery, runtime effects
and UDC emission still require independent tests.
