# UIL RFC 0005: Portable service contracts and alternative target realizations

- Status: draft
- Author or agent identity: ROM research lane `95b1b107135b`
- Date: 2026-11-03
- UIL core version: fDisBull 0.30.0 / `fdisbull-common-uil-1`
- Proposed extension identifier and version, if any: none; test the seams before changing a schema
- Supersedes: none
- Superseded by: none

## Semantic limitation

fDisBull already separates source evidence, shared behavior and target
realization, but the implementation remains uneven at the portability boundary:

- Common UIL can request ordered `text.show`, `image.show`, `sound.play`,
  `music.start` and `music.stop` effects.
- Presentation binds resources to those requests.
- The common runtime and generated probes return those effects as ordered plans
  with `pending_host` state.
- Current desktop and console shells do not expose a general physical
  service-provider interface that consumes those plans and returns
  identity-bound completion receipts.
- Current retained-code and selectable-layer routes do not expose a general
  same-ISA native-island connector that can place an original routine in a new
  executable, bind its ABI and globals, and call it from a standard scaffold.

As a result, fDisBull can describe much of the **thinking** independently of the
**doing**, but cannot yet select among several complete ways of doing the same
thing. The purpose of this RFC is to catalogue techniques used by established
reverse-engineering and cross-platform porting projects, map them to the current
tool, and recommend independent experiments. Overlap is intentional: several
UDC implementations may satisfy one UIL contract when each is independently
admitted and qualified.

## Design principle: UIL describes meaning; UDC supplies mechanism

A portable behavioral program should be able to say, in effect:

```text
when title_screen_enters:
    image.show(title_image)
    text.show(start_prompt)
    music.start(title_music, looping=true)

when fire_is_admitted:
    sound.play(shot_sound)
```

The program decides **what** happens, **when** it happens, and what state change
or ordering accompanies it. The target realization decides whether the request
is implemented by a native OS API, a console routine, an emulated source device,
a converted framebuffer, a compatibility shim, retained machine code, generated
target code, static recompilation, JIT translation or another admitted provider.

The current operation names correspond to colloquial calls such as
`display_text()`, `show_image()` and `play_sound()`. Renaming the verbs matters
less than defining their contracts. A service contract needs more than a
function name and matching integer widths. It needs declared:

- input meaning and resource identity;
- ordering relative to effects and state commits;
- lifetime and ownership;
- clock or timing domain when observable;
- completion and acknowledgement behavior;
- refusal, unknown and partial-effect behavior;
- whether repeated identical requests remain distinct events;
- retry and fallback policy;
- target capability requirements; and
- evidence identifying which provider actually ran.

This is the chip-package model: UIL exposes semantic pads; UDC selects and binds
implementations; generated adapters are the bonding wires; the target runtime is
the standard socket.

## Current fDisBull baseline

The following is implemented on `main` at the time of this RFC. “Implemented,”
“bounded” and “proposed” remain deliberately separate.

| Current component | Implemented scope | Portability gap |
| --- | --- | --- |
| [Common UIL contract](../COMMON_UIL_CONTRACT.md) | Indexed typed computation, resources, ordered planned text/image/sound/music effects, `pending_host`, immutable package identity and selected semantic implementations. | No general physical effect executor, callback receipt or partial-effect reconciliation provider. |
| [Common native realization](../COMMON_UIL_NATIVE.md) | macOS ARM64, Linux x86-64 and Win64 computation probes; deterministic component resolver; selectable C/assembly arithmetic leaves; versioned intrinsic requirements. | Service contracts are plans only. The documented image decode/blit component graph is metadata, not a working renderer. |
| [Common desktop shell](../COMMON_UIL_DESKTOP.md) | Effects-free indexed arena, keyboard, pointer, clock, palette and framebuffer adapters across AppKit, X11 and Win64/GDI. | No general text, image, audio, file or retained-native service provider. |
| [Console UDC](../CONSOLE_UDC.md) | Native NES and Genesis startup/controller loops; bounded u8/u16 logic; optional marker display; one narrow Genesis-byte-to-UIL route. | No general resources, effect requests, graphics primitives, audio service, mapper-neutral shell or cross-console native-island provider. |
| [Code backings and selectable layers](../CODE_BACKINGS.md) | Retained native bytes, overlapping interpretations, content-addressed contracts/layers, bounded x86-16 providers and structural relayout under explicit assertions. | No general cross-executable ABI rebinding, service interception or same-ISA transplant linker. |
| Verification machinery | Original/model/output separation, selected-provider counters, typed state comparison, bounded whole-frame checks, native image admission and negative controls. | No standard portability suite spanning alternate realizations of one service-rich UIL program. |

The project has the right separation and several relevant seams. It should
extend those seams rather than create one monolithic `port-game` operation.

## Precedent projects and reusable techniques

These projects are methodological references, not imported dependencies or
claims reproduced by fDisBull.

### Meynaf Atari ST to Amiga conversions

Community documentation of Philippe “Meynaf” Guichardon's conversions describes
a retained-code strategy: original Atari ST 68000 gameplay code is patched to
run on Amiga, source-machine memory and OS interactions are redirected, the ST
screen is converted to Amiga bitplanes, and source audio may be emulated.

Techniques:

- retain most same-ISA gameplay code;
- patch source-machine memory, OS and device interactions;
- translate a framebuffer at one narrow boundary;
- emulate a source audio chip instead of rewriting every call;
- run under the destination OS rather than taking over the machine;
- keep per-game compatibility profiles while interfaces are still incomplete;
- measure compatibility-bridge cost before replacing it.

References:

- [Meynaf port index](http://meynaf.free.fr/pr/index_en.html)
- [Super Sprint discussion](https://www.amigafrance.com/forums/topic/supersprint/)
- [Karateka conversion summary](https://www.amigafrance.com/forums/topic/karateka/)

### Where Time Stood Still ST to Amiga conversion

The conversion runs the ST program in Amiga memory and intercepts routines that
publish an ST image. Collision, clipping, object movement and gameplay remain in
the retained engine; a host routine converts the completed frame.

Techniques:

- execute a source binary as a same-ISA native island;
- intercept a few high-leverage publication routines;
- preserve the gameplay engine while replacing only hardware boundaries;
- use a compatibility provider as a bootstrapping path, not necessarily the
  final renderer.

Reference:

- [conversion description reproducing the developer's EAB explanation](https://www.indieretronews.com/2014/07/where-time-stood-still-new-amiga-game.html)

### OpenUA

[OpenUA](https://github.com/slaapliedje/OpenUA) decompiles a Macintosh 68k game
engine and serves Atari and Amiga targets through a compatibility layer and
hardware-abstraction layer. It combines C with retained 68k assembly, runtime
backend selection, deterministic resource extractors, chunky/planar conversion
and real-hardware checks.

Techniques:

- choose a same-ISA source edition to avoid needless instruction rewriting;
- decompile incrementally while retaining difficult routines in assembly;
- preserve historical API call sites behind a compatibility shim;
- provide a stable engine-facing HAL with several backends;
- select backends without changing game logic;
- use a canonical intermediate framebuffer, then replace it when measurements
  justify a native renderer;
- keep resource extraction/conversion separate from runtime behavior;
- test real hardware because emulators can agree on the same mistake;
- retain decision records and subsystem-specific limits.

References:

- [OpenUA README](https://github.com/slaapliedje/OpenUA)
- [OpenUA decisions](https://github.com/slaapliedje/OpenUA/blob/main/docs/decisions.md)

### Xevious 68K

[Xevious 68K](https://github.com/jotd666/xevious) reverse-engineers the original
arcade CPUs, transcodes the core to 68000 assembly, and isolates platform work
behind an operating-system-dependent layer used by Neo Geo and Amiga targets.

Techniques:

- transcode instructions to a shared target ISA when semantic lifting is not yet
  available or worthwhile;
- define a platform-independent core with explicit OSD calls;
- keep graphics, input, storage and sound in target adapters;
- preserve deterministic rules, including pseudo-random behavior;
- add a target by implementing the OSD interface rather than rewriting logic.

### atari_reverse

[atari_reverse](https://github.com/geogeo28/atari_reverse) disassembles shipped
GEMDOS programs, names functions, rewrites them as readable C or 68000 twins,
and differentially checks each recovered function against original machine
code. Verified cores are rebuilt into playable 68000 programs; later remaster
work is compared frame by frame.

Techniques:

- scaffold analysis from one executable;
- anchor naming on OS traps and hardware registers;
- verify functions independently before composition;
- use original machine code as the reimplementation oracle;
- distinguish exact reconstruction from later optimization/remastering;
- compare complete frames and performance after function-level equivalence;
- preserve packers and protected loaders as separate recovery problems;
- use real hardware as a stronger evidence grade than emulator agreement.

### Bloodwych-68k

[Bloodwych-68k](https://github.com/HoraceAndTheSpider/Bloodwych-68k) rebuilds
Amiga and Atari ST 68k source, preserves raw/relabelled/data-linked views,
externalizes data regions, identifies binary families by content, and provides
reversible extract/edit/patch tools.

Techniques:

- retain raw, relabelled and data-linked source views;
- externalize graphics and maps while keeping source references;
- describe regions and labels through editable metadata;
- recognize executable families by content rather than filenames;
- keep extraction, editing, validation and patching reversible;
- require relocation/layout support when edited data no longer fits a slot.

### NES to SNES porting template

The [NES-to-SNES template](https://github.com/rumbleminze/nes-to-snes-template)
retains and edits source PRG banks, converts CHR assets deterministically, adds
SNES support routines and sound emulation, and links the result with an explicit
ROM layout.

Techniques:

- preserve source bank relationships while target support is incomplete;
- replace hardware sequences with support-routine calls;
- keep game and target-service code in separate regions;
- generate graphics conversion rather than hand-editing assets;
- use an ordinary assembler/linker for placement and fixups;
- preserve an executable checkpoint while progressively replacing operations.

### upernes

[upernes](https://github.com/mandraga/upernes) disassembles NES code, rewrites
hardware reads/writes into 65C816 support calls, reorganizes memory, retains much
of the original 6502 code in emulation mode, converts tiles and links a SNES
image. Unknown indirect targets are reported at runtime and fed into the next
build.

Techniques:

- static rewriting of source-hardware accesses;
- retained execution through a compatible CPU mode;
- iterative discovery of indirect control flow;
- runtime fault screens that produce actionable build feedback;
- tiny hardware-focused ROMs for palette, scrolling, sprites, input, indirect
  jumps and interrupts;
- explicit code/data remapping and RAM placement for performance.

### Project Nested

[Project Nested](https://github.com/Myself086/Project-Nested) provides a NES
execution environment on SNES using dynamic recompilation, desktop preparation
and compatibility profiles.

Techniques:

- combine AOT preparation with JIT fallback for unknown destinations;
- retain observed entry points and feedback across runs;
- separate desktop preparation from target runtime execution;
- use per-game settings for unresolved hardware differences;
- treat execution coverage as feedback, not proof of absent behavior.

### EmuDevz

[EmuDevz](https://github.com/afska/emudevz) teaches console implementation by
replacing one CPU/PPU/APU/bus component at a time while supplied components and
cumulative tests keep the machine executable.

Techniques:

- replace one explicit component while retaining reference providers elsewhere;
- record which provider actually ran, including fallbacks;
- use the first divergence as the next investigation target;
- keep earlier tests active as capability grows;
- name provisional implementations and their limits;
- separate tutorial/reference equivalence, target-console equivalence and
  application equivalence.

### Elephant–Goldfish review

Google's [Elephant–Goldfish Model](https://github.com/google/elephant-goldfish-model)
is not a runtime, but it helps validate contract portability. A context-rich
author prepares a design/evidence packet and a fresh reader tests whether that
packet is comprehensible and implementable.

Techniques:

- require a fresh agent to paraphrase a contract before critiquing it;
- expose assumptions retained only in the lead agent's conversation;
- separate comprehension review from deterministic behavioral evidence;
- retain unresolved findings and incomplete review rather than treating silence
  as acceptance.

## Technique catalogue and current-tool mapping

The same UIL contract may legitimately have several realization strategies.
Preserve them as alternatives instead of choosing one universal mechanism too
early.

| Technique | Current fDisBull state | Recommended experiment or implementation |
| --- | --- | --- |
| Retained native-code island | Bounded retained x86 backings and structural layouts exist; no general same-ISA executable island. | Add a content-addressed island profile containing code identity, entry ABI, permitted memory/effects, relocations, preserved registers and continuation. |
| Same-ISA ABI rebinding | Typed common-UIL shims exist; arbitrary guest ABI rebinding does not. | Transplant one qualified Amiga Civilization 68000 routine into the bootable Atari build, generate stack/global wiring, redirect a natural call site and observe it. |
| OS/trap/import interception | Source traps can be annotated; no generic service-import conversion. | Map concrete traps/calls to versioned UIL services without embedding target API names. |
| Compatibility shim preserving call sites | No general foreign-API shim catalog. | Implement a small authored historical API subset twice, such as text drawing and file reads, behind one service contract. |
| Platform HAL / OSD | UDC targets and native component resolution form partial HALs. | Add exact effect-provider modules and selected provider IDs while keeping logic UIL unchanged. |
| Framebuffer bridge | Indexed desktop frames exist; no source-framebuffer converter provider. | Implement an ST planar or NES tile/frame source-surface provider and compare complete output and pacing. |
| Native renderer replacement | Desktop shells render indexed pixels but do not realize high-level image/text effects. | Implement a native text/image provider while retaining the framebuffer bridge as an alternative. |
| Runtime backend selection | Desktop variants select computation realizations; physical service selection is absent. | Select among exact providers from declared capabilities, record the selected provider, and prohibit implicit fallback after effects. |
| Static instruction transcode | Narrow x86 and Genesis lifters exist; no general transcode framework. | Keep transcode as an alternate UDC leaf for supported subsets with source instruction IDs and explicit hardware substitutions. |
| Readable source reimplementation | Restricted C/Python adapters and common C codegen exist; no arbitrary decompiler. | Import typed-C functions only after original-machine differential qualification. Compilation alone is not source proof. |
| Function differential qualification | Strong bounded original→UIL and UIL→target patterns already exist. | Standardize native-island receipts with domains, register/memory/effect projections and negative controls. |
| Complete-frame composed comparison | Used in bounded desktop and game studies. | Make complete frame/event/state comparison a promotion gate for visual provider substitution. |
| Deterministic asset conversion | Presentation carries resources; game-specific converters exist. | Add content-addressed transform records containing source/output hashes, dimensions, palette/encoding and rebuild receipts. |
| Ordered audio-event bridge | `sound.play` is planned; no register-event adapter or physical playback provider. | Capture repeated clocked writes, map them to a source-audio service, compare counts/order before samples, then qualify a player. |
| Input normalization | Desktop and console adapters use separate mappings. | Define press/release/hold semantics and clock phase; prove two targets consume the same normalized schedule. |
| File/resource abstraction | Resource URIs are inert; no generic file service. | Add read-only package operations with an explicit namespace, byte counts, errors and no ambient filesystem authority. |
| Memory/layout relocation | Code layout and native links are profile-specific. | Generalize placement receipts around sections, relocations, call-site redirects and source occurrences without hiding slot failures. |
| AOT plus JIT fallback | No target runtime translator. | Defer until service and island contracts exist; prototype on a redistributable fixture with unknown-target traps and coverage receipts. |
| Runtime feedback into next build | Harnesses retain observations, but feedback is not a standard build pipeline. | Record discovered entry points/unknown services as evidence-bound candidate inputs, never silently trusted coverage. |
| Progressive component replacement | Draft skill work and selectable arithmetic leaves exist. | Apply it to effect providers: reference provider → candidate provider → composed service-rich application with first-divergence reports. |
| Per-program compatibility profile | Several project-specific studies exist; no generic authority. | Store exact source, target, providers, assumptions, exceptions and evidence; keep selection explicit and non-authoritative until qualified. |
| Fresh-reader review | Cold-agent and handoff work exist separately. | Require comprehension/evidence review at reusable provider and native-island promotion boundaries. |
| Real-hardware validation | Most current console/desktop evidence uses emulators or host processes. | Add a higher evidence grade with exact hardware, build/media identity, input schedule and observed divergences. |
| Multiple alternate providers | Native arithmetic variants exist; physical service alternatives do not. | Let compatibility bridges, native backends, retained code, generated code and emulators coexist under one contract. |

## Proposed service layering

Do not collapse behavior, resources, target implementation and evidence into one
document. A portable service should have five separate layers:

1. **UIL operation** — semantic service, typed inputs, logical ordering and
   modeled state transition; no SDL, Intuition, GEM, Win32, PPU or APU names.
2. **Presentation resource** — concrete resource identity and data/locator,
   including encoding, dimensions or sample metadata required for admission.
3. **UDC provider contract** — target, service version, accepted profiles,
   timing, ownership, completion and failure behavior.
4. **Generated connector** — logical ports/resources mapped to provider ABI,
   memory layout and target representation.
5. **Execution receipt** — provider actually entered, ordered requests,
   completion/partial status and observations used for qualification.

The existing `pending_host` result is a useful staging boundary. A provider
should consume that plan and return a separate completion receipt. It must not
commit model state before the configured boundary and must not retry another
provider after an unknown or partial physical effect.

### Compare event semantics before visual or audio similarity

Two providers are not equivalent merely because the final screen or register
snapshot looks similar. Compare, in order:

1. completion and event counts;
2. event identities and ordered arguments;
3. required clock/timing relations;
4. state ownership and commit behavior;
5. complete rendered/audio output at the declared boundary.

Repeated equal writes or requests remain distinct when the device treats the
write as an action. A final register value cannot replace an event trace.

## Alternate realization strategies under one contract

| Strategy | Best use | Main risk | Required evidence |
| --- | --- | --- | --- |
| Full UIL code generation | Recovered target-independent logic | Unsupported semantics hidden as defaults | Independent original→UIL and UIL→target checks |
| Retained native island | Same-ISA or qualified routine | Hidden ABI/global/device dependencies | Entry/exit state, allowlisted memory/effects and natural call-site execution |
| Compatibility shim | Historical API-heavy engine | Shim alters behavior | API/event trace plus composed application checks |
| Source-framebuffer bridge | Rapid visual bootstrapping | Performance/timing cost and hidden renderer semantics | Complete source buffer, converted frame and pacing checks |
| Native target renderer | Performance and integration | Reimplementation divergence | Same service/event contract plus complete-frame comparison |
| Static transcode/recompile | Compatible ISA subset and known control flow | Unknown indirect control or hardware assumptions | Complete coverage/refusal and source-linked tests |
| AOT/JIT execution provider | Large dynamic source program | Coverage mistaken for completeness | Unknown-target traps, feedback identity and fallback receipts |
| Full source-machine emulator | Broad compatibility oracle or fallback | Expensive and not semantic recovery | Declared hardware profile and independent application scenarios |
| Readable source reimplementation | Maintainability and optimization | Source model may be wrong | Function differential proof, then composed frame/effect tests |

A slower or less elegant provider can still be valuable as a qualified baseline.
Prefer an explicit slow implementation over a silent guessed one.

## Recommended implementation and test order

### P0-A: service-provider execution seam

Implement a provider interface that consumes the current ordered effect plan and
returns an identity-bound receipt. Start with:

- a deterministic reference provider that records requests without physical I/O;
- one actual desktop provider for text, image and sound;
- explicit `completed`, `refused`, `partial_effect` and `unknown` outcomes;
- no automatic fallback after provider entry; and
- provider and resource hashes in the realization closure.

This turns current service verbs from plans into a portable execution boundary.

### P0-B: service-rich held-out fixture

Create a redistributable “portable kiosk” fixture with one title image, two text
messages, one short sound, input, and a small state machine deciding which
services fire. Include two identical sound requests that must remain two events
and one deliberately wrong provider/resource binding.

Run unchanged UIL through at least two provider stacks. Compare ordered requests,
state, complete frames and audio counts/samples at declared clocks. The wrong
binding must fail the intended-output comparison even when structurally valid.

### P0-C: same-ISA Civilization native-island transplant

Use the bootable Atari ST Civilization baseline as the first held-out connector
test:

1. choose one previously qualified Amiga 68000 routine;
2. place it in a new Atari executable region instead of assuming the original
   slot is large enough;
3. generate its stack/global/relocation adapter;
4. redirect one Atari call site;
5. boot the modified executable in an independent emulator;
6. demonstrate ordinary execution reaches the transplant;
7. compare result, preserved registers, relevant memory and visible outcome;
8. repeat with a wrong global binding as a negative control.

Start with `WhichYear` or `OnMap`; then test `FameLevel`, whose repeated-versus-
single difficulty read needs an explicit stable-input lifetime contract. This
qualifies the native-island connector, not a whole-game port.

### P0-D: ordered audio bridge

Implement one source-device bridge preserving repeated writes and clock order,
such as YM2149 or an authored PSG fixture. Compare write counts, register/value
pairs, clocks, generated target events, sample counts before values, and final
audio through a separately qualified player.

### P0-E: two visual providers for one contract

Implement both a source-framebuffer conversion provider and a native target
renderer for one fixture. The former proves rapid compatibility; the latter
tests replacement with a target-native implementation. Both satisfy the same
UIL-visible display contract. Keep both after the native provider passes.

### P1: resource, input, file and structure connectors

Add deterministic resource transforms, normalized input events, read-only
packaged-file services and typed structure adapters. Keep ambient filesystem
access outside the service. Test path errors, partial reads, encoding,
press/release/hold semantics, field offsets, aliasing, lifetime and deliberately
wrong field bindings.

### P2: static transcode, AOT/JIT and hardware qualification

After service and native-island contracts stabilize, add static transcode and
hybrid AOT/JIT providers as alternatives. Unknown indirect targets and
unsupported effects must trap with actionable evidence. Promote providers
through emulator diversity and then real hardware, preserving exact build,
hardware, media, input and observation identities.

## Conformance requirements for every provider

A reusable provider or native-island adapter should not be promoted without:

- exact source, semantic contract, target, provider and generator identities;
- positive cases covering every admitted branch/service;
- unchanged-state and no-effect cases;
- at least one deliberately wrong binding or implementation;
- completion/event counts before output values;
- provider-entry evidence, not merely matching final output;
- declared clock and observation boundary;
- refusal for unsupported profiles and resource kinds;
- no implicit retry after unknown/partial effects;
- independent original→UIL and UIL→provider comparisons where an original is
  involved;
- composed application checks; and
- fresh-reader review for reusable cross-project contracts.

## Proposed module impact

These are recommended work areas, not changes implemented by this RFC.

| Module or area | Recommended responsibility |
| --- | --- |
| `common_uil.py` | Retain target-independent service operations and fail-closed signatures; avoid target API names. |
| `uil_runtime.py` | Expose provider execution/receipt after `pending_host`, preserving proposed versus committed state. |
| `uil_link.py` and native resolver | Select exact service providers and nested requirements without “latest” or implicit fallback. |
| `uil_native_codegen.py` | Emit provider dispatch adapters and identity-bound receipt plumbing, not hard-coded SDL/GEM/Win32 policy. |
| `uil_desktop.py` | Supply the first physical text/image/sound providers and lifecycle integration. |
| `console_udc.py` and target backends | Adopt the same service contracts when implementations exist; retain narrower refusal meanwhile. |
| `udc_layers.py` and code-backing modules | Add native-island contracts, placement/relocation recipes and generated ABI connectors. |
| Resource tooling | Add deterministic transform identities and receipts independent of runtime providers. |
| Verification tools | Compare ordered effects, state, complete frame/audio and actual provider identities across alternatives. |

## Security boundary

A provider must not turn a resource URI or source import into ambient code,
filesystem, network or native-library execution.

- Resources remain inert until an explicitly selected provider admits them.
- File access uses an explicit package namespace and declared modes.
- Native islands bind retained code identity, entries, memory/effect authority
  and placement recipes.
- A provider cannot silently load another provider after refusal or partial
  effect.
- Initial adapters carry typed values and bounded buffers, not arbitrary native
  pointers.
- Private game bytes, disks, states and native captures remain outside Git.

## Conformance fixtures

Recommended redistributable fixtures:

1. **Portable kiosk:** state-driven text/image/sound with two provider stacks and
   a wrong-binding negative control.
2. **Same-ISA scalar island:** authored 68000 routine with two ABI layouts,
   exhaustive small-domain comparison and wrong-global binding.
3. **Source-frame visual bridge:** authored planar/indexed source surface with
   conversion and native-render providers.
4. **Ordered PSG events:** repeated equal writes, frame-relative clocks and a
   lost-write mutation.
5. **Read-only package service:** deterministic reads, partial reads, missing
   resources and forbidden ambient paths.

The commercial Civilization transplant remains a private held-out application
of the authored native-island contract.

## Alternatives

### One universal translator

A universal translator forces every source/target pair through one mechanism and
makes partial support look complete. The precedent projects show that retained
code, shims, native renderers, recompilation and emulation are useful at
different stages. fDisBull should standardize contracts and evidence, not one
mechanism.

### One full source-machine emulator per target

An emulator is a useful compatibility provider and oracle, but it does not
recover semantic intent or produce editable visual blocks. It should remain one
possible UDC provider, not the definition of UIL.

### Rewrite every game manually

This works, but repeats service and ABI knowledge in per-game glue. Provider and
connector layers should turn that glue into reusable modules.

### Put target APIs directly in UIL

Embedding GEM, Intuition, SDL, Win32, PPU or APU calls in UIL collapses the
thinking/doing separation. Target APIs belong in providers and generated
connectors. UIL retains the semantic action and observable contract.

## Implementation experience

This RFC is informed by current common-UIL planned effects and component
selection, current effects-free desktop and bounded console UDCs, retained-code
and selectable-layer prototypes, the private Civilization 68000 die comparison
and boot validation, prior NES/SNES scaffold experiments, and the external
projects above.

No physical service provider, general transplant linker, modified Civilization
executable, JIT runtime or new UIL schema is implemented by this RFC. The first
implementation should be the provider seam and authored kiosk fixture, followed
by the private Civilization transplant.

## Disposition

Review questions:

1. Is the five-layer service split sufficient to preserve current package,
   orchestration and native-link identities?
2. Should provider completion be a new receipt or an extension of existing
   host-completion records?
3. Which host should provide the second implementation after the deterministic
   reference provider?
4. Can native islands reuse existing layer/selection identities without granting
   arbitrary native-memory authority?
5. Which requirements belong in common service contracts and which remain
   provider-specific qualification metadata?

Acceptance would authorize bounded implementation experiments, not claim general
game portability or automatically enable a provider.
