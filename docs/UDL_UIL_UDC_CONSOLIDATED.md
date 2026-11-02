# Consolidated UDL, UIL, and UDC Semantic Architecture and Format Reference

This reference consolidates the definitions, schemas, data profiles, and
verification boundaries of the **UDL → UIL → UDC** semantic pipeline across
fDisBull's supported environments, incorporating the recovery harness,
multi-scale Z-worlds, selectable block layers, and TAS rewind state policies.

---

## 1. Core Architecture and Pipeline Separation

fDisBull separates program analysis and semantic reconstruction into three
distinct architectural roles:

```text
+-------------------+      UDL       +-------------------+      UDC       +-------------------+
|  Original Binary  | -------------> |     Candidate     | -------------> | Target Realization|
|   or Guest VM     | Source Mapping | Shared-IL Program | Target Binding |   (Code / Shell)  |
| (DOS, PE, Mach-O, |                | (Common, Memory,  |                | (Native, Desktop, |
|  Cortex-M, AGI, Z)|                |  Zork, AGI, Z)    |                |  Web, Console)    |
+-------------------+                +-------------------+                +-------------------+
          ^                                    |                                    |
          |           Recovery Harness         |            Pointwise Proof         |
          +====================================+====================================+
               (Feedback, Checkpoints, Rewind, and Differential Qualification)
```

1. **UDL (Universal Decompilation Language / Source Mapping):**
   The mapping role between concrete source operations and shared semantics. It
   binds specific original addresses (e.g., segmented DOS `CS:IP`, logical Win16
   `ne:seg:offset`, 32-bit LE offsets, or 64-bit virtual addresses), registers,
   and file extents to logical variables, operations, and contracts. UDL
   preserves provenance, byte identity, and source evidence.
2. **UIL (Universal Intermediate Language / Behavioral IR):**
   The candidate shared behavioral representation. It declares typed variables,
   pure expressions, acyclic local control flow, guards, and planned effect
   requests. UIL contains no native instruction opcodes, concrete host memory
   addresses, target register allocations, or target calling conventions.
3. **UDC (Universal Decompilation Compiler / Realization):**
   Target compiler and realization definitions. A UDC reads UIL and binds its
   declared behavior to a target implementation—emitting standalone portable
   code (Python, JavaScript), linking native machine components (macOS ARM64,
   Linux x86-64, Windows x64), compiling segmented 16-bit binaries (Win16 NE),
   synthesizing console cartridges (NES, Genesis), or orchestrating
   desktop/browser window shells.

### The Recovery Harness and Feedback Loop

Recovery is rarely a one-shot forward translation. The **recovery harness** is an
executable interface that observes and operates a backing, manages experiment
boundaries and checkpoints, and records evidence:

- `waexecution` records qualified physical execution facts, access events, and
  restore coverage.
- `waorchestration` connects logical objects, typed values, dependencies, and
  behavioral boundaries.
- **Z** names the observations, objects, relations, and actions used to
  investigate and test those boundaries.
- A checkpoint supplies both the starting witness for an experiment and the
  state relation for comparing an original-backed operation with a candidate
  replacement.

---

## 2. The Seven Concrete Profiles and Data Formats

fDisBull defines seven concrete, content-addressed formats for representing and
evaluating programs at different abstraction layers:

| Profile / Format | Primary Schema / Identifier | Scope and Responsibilities |
| --- | --- | --- |
| **Common Indexed UIL** | `fdisbull-common-uil-1` | 4-document specification: indexed typed variables, functions, semantic catalogs, and copy-in/copy-out orchestration. |
| **Memory UIL & Shells** | `fdisbull-memory-uil-1` | Fixed unsigned word arenas, indexed load/store, callee cuts (`fdisbull-memory-cuts-1`), and single-store regions (`regions`). |
| **Selectable Block Layers** | `fdisbull-block-contract-1` | Content-addressed snippets, links, contracts, layers, selections; isolated x86-16 CPU blocks and COM splicing. |
| **Direct AGI v2** | `fdisbull-il-2` / `agi-2.917` | Sierra AGI v2 logic trees and compact continuations, typed effect ports, and live DOS host qualification. |
| **Direct Z-machine v3** | `zork-uil` / `zork-intents` | Word16 executable IR, source-linked mailbox game-intent rules, and 110-room / 352-exit address-free scene rules. |
| **Console Synthesis** | `console-udc` / `genesis-replay` | Shared unsigned 8/16-bit UIL for NES/Genesis; full-game procedural replay (*Miniplanets*); prepared-state slices (*Shadowrun*). |
| **Multi-Scale Z-Worlds** | `z-world-view-study-1` | Authoritative world state vs. bounded observer scene views; overlapping views, current/remembered/unknown knowledge. |

---

## 3. Format 1: Common Indexed UIL (`fdisbull-common-uil-1`)

The common indexed profile composes source-independent typed functions and
selected block definitions with separate orchestration and presentation.

### The Four Documents

1. **Program (`fdisbull-common-uil-1`):**
   - Declares typed variables (`variables`) and constants (`constants`) using
     zero-based indices (`u8`, `u16`, `u32`, `u64`, `i8`, `i16`, `i32`, `i64`,
     `bool`, `text`).
   - Defines local functions (`functions`) with inputs, outputs, `max_steps`, and
     ordered statement bodies (`body`).
   - Declares imported reusable semantic functions (`imports`) with typed ports
     and planned effect declarations.
   - Restricts local call graphs to acyclic invocations.
2. **Presentation (`fdisbull-uil-presentation-1`):**
   - Binds initial variable values and constant values using canonical decimal
     strings.
   - Binds static resources (text strings, sound data, images) by table index.
3. **Semantic Catalog:**
   - Grouped normalized UDL descriptors compiled via `uil-catalog`.
   - Preserves distinct implementation backings (e.g., portable-C, native-asm,
     decoded x86) under a content-addressed `semantic_id`.
4. **Orchestration (`fdisbull-uil-orchestration-1`):**
   - Maps each import index to an exact implementation ID in the catalog.
   - Declares frame ownership (`copy-in-copy-out`), max call depth, and execution
     epoch tickets.

### Native Linking and Component Selection

The `uil-link` and `uil-compile` methods target native platforms (`macos-arm64`,
`linux-x64`, `windows-x64`):
- Deterministic native lock binds ABI, numeric wrapping, effects, and exact
  intrinsic versions.
- Per-function and per-operation overrides allow selecting portable C or native
  assembly arithmetic per child operator:
  ```json
  {"components": {"add": "portable-c", "mul": "native-asm"}}
  ```
- Scalar value numbering removes redundant temporary physical copies in
  straight-line lowering while preserving logical charges.

### Native Desktop Shells (`uil-desktop*`)

`uil-desktop` builds native window applications (macOS AppKit, Linux X11,
Windows Win32/Win64) over a fixed u32 arena:
- Host plan binds indexed function triggers, input patches, output commit
  footprints, guard predicates, palette/frame geometry, and monotonic clock.
- One synchronous owner per transaction; refused calls preserve committed state
  without mutating application memory.

---

## 4. Format 2: Bounded-Memory UIL (`fdisbull-memory-uil-1`)

For programs with array indexing, pointer arithmetic, or fixed memory grids,
`fdisbull-memory-uil-1` models execution over an explicit unsigned word arena:

### Contiguous Callee Cuts (`fdisbull-memory-cuts-1`)

Allows replacing inlined functions without dynamic symbol resolution:
- Requires exact contiguous callee-body equality after stripping evidence IDs.
- Prohibits loop ancestors or local live-in variables crossing the cut boundary.
- Preserves the canonical UIL hash and validates derivation under independent
  bindings.

### Selectable Subregions (`regions`)

Allows modular variation of small, safety-critical memory modifications:
- Exactly one pure store expression, literal reads, one guarded output word,
  and one source charge.
- Distinguishes intentional behavior variants from exact source equivalence;
  variants require explicit caller policy opt-in.

### Multi-Target Desktop and Segmented Realizations

The same bounded-memory model compiles across five targets:
1. **Wasm/WebGPU:** Standalone browser canvas and compute shaders
   (`build-memory-web-shell`).
2. **macOS ARM64:** Native AppKit window with offscreen bitmap backing
   (`build-memory-macos-shell`).
3. **Windows x86/x64:** Win32/GDI desktop applications.
4. **Linux x86-64:** X11/Xlib desktop applications.
5. **Win16 Segmented NE:** Genuine 16-bit Windows executables
   (`build-memory-win16-shell`):
   - Logical 32-bit arena addresses mapped across 9 pages of at most 32 KiB.
   - Emits C89 code compiled with Open Watcom using `_lread`/`_lwrite` far
     buffers and far Pascal callback thunks.

---

## 5. Format 3: Selectable UDL Block Layers and Code Backings

The block-layer prototype manages source captures, cross-project relations, and
alternative native backings:

### Content-Addressed Records

- **Snippet (`fdisbull-snippet-1`):** Immutable source span `{address, size}`
  from a mapped version or `{file, offset, size}` from retained files.
- **Relation (`fdisbull-snippet-link-1`):** Relates source and target snippets
  with relation kind, admitted domain, evidence, and assurance level.
- **Contract (`fdisbull-block-contract-1`):** Typed logical ports and a fixed
  UIL behavior or admitted service.
- **Layer (`fdisbull-udl-layer-1`):** Binds a contract to an implementation
  descriptor, boundary adapter, and optional source snippet.
- **Selection (`fdisbull-udl-selection-1`):** Pins exact layer IDs to logical
  binding names.

### Overlapping Code Backings (`code-backings`, `code-layout`)

- Captures exact multi-entry x86 instruction interpretations where the same
  physical byte serves as an immediate in one path and an opcode in another.
- `code-layout` emits raw relocated code requiring five explicit assertions:
  `no_code_reads`, `no_code_writes`, `no_computed_entries`,
  `address_identity_unobserved`, and `timing_unobserved`.

---

## 6. Format 4: Direct Guest Interpreters (AGI & Z-Machine)

When analyzing interpreted adventure games, fDisBull bypasses host interpreter
x86 disassembly to analyze bytecode scripts directly:

### Sierra AGI v2 (2.917)

- `agi-logic` decodes raw LOGIC resources.
- `agi-scenes` performs two-stage projectless census (`outline` and `resolve`)
  across VOL/LOGDIR structures.
- `module-lift` extracts acyclic components into `fdisbull-il-2` with compact
  continuations, explicit call/return/stop nodes, and typed effect ports.
- `AGIDOSHostAdapter` qualifies lifted graphs by comparing leaf invocations
  against the live DOS interpreter.

### Z-Machine v3 (*Zork I*)

- `story-info` and `zmachine-disasm` decode raw v3 story files.
- `zork-uil` lowers complete v3 stories into word16 standalone executable IR.
- `zork-intents` exports source-linked mailbox and action-counter rules with
  fault receipts.
- `zork-scenes` recovers 110 named rooms and 352 exits with live guards, door
  conditions, and explicit residual IR.

---

## 7. Format 5: Console Synthesis and Replay

- **Shared Console UDC (`console-udc`):** Compiles unsigned 8/16-bit UIL into
  runnable NES 6502 (`.nes`) or Sega Genesis 68000 (`.bin`) ROMs with native
  startup, palette setup, and controller loops.
- **NES Multicarts (`nes-multicart-*`):** Synthesizes bank-switching menu ROMs
  for compatible NROM games under an explicit `--authored-compatible` assertion.
- ***Miniplanets* Procedural Replay (`rom-game-lift`, `genesis-replay-*`):**
  Lifts all 55 levels, display planners, and PSG audio into procedural UIL,
  compiling to banked NES cartridges or repeatable Genesis ROMs (~59.9 Hz).
- ***Shadowrun* Slices (`shadowrun-*`):** Prepared-state Genesis slices (motel
  opening, field combat, hostile AI arena) and SNES 65816 morgue-movement slices
  compiled to native macOS ARM64 desktop windows (with NES slices preserved as
  research).

---

## 8. Format 6: Multi-Scale Z-Worlds and Observer Scenes

### Worlds vs. Scenes

**A Z world owns authoritative identities, state, relationships, clocks, and
behavior. A Z scene is a bounded, observer-scoped view of that world at a
declared execution boundary.**

- A tactical room, city district, continental map, or off-map transit hub
  represent different observer views of the same underlying world.
- Overlapping views share authoritative entity identities without duplication.
- Restricting observation scale does not authorize skipping off-screen
  simulation.

### Knowledge Admission

Public observations strictly distinguish:
- **Current knowledge:** Observable facts verified at the current execution epoch.
- **Remembered knowledge:** Previously observed facts whose current validity is
  unconfirmed.
- **Unknown knowledge:** Facts outside observer visibility or unrecovered by the
  model.

Pagination uses opaque cursors bound to world, observer, view, and epoch;
restoring a checkpoint invalidates old cursors even if visible field values repeat.

---

## 9. TAS Rewind and State Preservation Policies

Rewind connects observed outcomes back to producing code and state. In fDisBull,
rewind selects both a **return boundary** and an explicit **restoration policy**:

1. **Deterministic Machine Parity (Default):**
   Restores both CPU registers and full writable RAM to the recorded historical
   checkpoint. Subsequent execution reproduces identical behavior.
2. **Selective State / RNG Continuation Policy:**
   Restores native machine execution context while preserving declared current
   memory ranges (such as live RNG state or frame counters):
   - Used for exploratory retries (e.g., retrying a room entry to observe
     alternative randomized events without restarting the entire session).
   - The resulting execution state is explicitly marked `partial_restored: true`
     and `resume_safe: false`.
   - Pointwise original vs. replacement equivalence tests must always use
     matched random contexts rather than mixed exploratory states.

---

## 10. Rich Text Formatting and Dynamic Display

For dynamic text and string templates, the study profile introduces two core
operations:

1. **`text.format`:**
   Evaluates ordered typed parts (literal text strings, variables, constants,
   and formatted decimals with minimum width and padding) into a bounded UTF-8
   text value (at most 4,096 bytes).
2. **`text.display`:**
   Stages an output event containing a text value into the invocation's event
   plan, returning `pending_host` without claiming physical window rendering.

Formatting policies remain distinct across engines (e.g., DinoPark `%02d`
zero-padded width vs. Ultima unsigned decimal width vs. AGI trailing-two-digit
modulo-100 formatting).

---

## Summary of Verification Gates

Before asserting semantic equivalence or code replacement:
1. Qualify **Original → UIL** under declared input domains and boundary assumptions.
2. Qualify **UIL → Target Output** independently on matching test cases.
3. Verify **Composed Realization** against original runtime traces and complete
   frame/memory receipts.
4. Keep unresolved effects, unobserved flags, and external host obligations
   explicit in the coverage ledger.
