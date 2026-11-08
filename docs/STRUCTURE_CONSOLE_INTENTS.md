# Shared console and intent discovery

Status: source-only candidate extension, 2026-11-08. This extends the supplied
structural/menu discovery contribution, not the installed or released tool.
The package version is retained; `discovery_revision: 2` and the implementation
hashes identify this reader. It is read-only analysis, not a game runner.

## Agent entry point

```sh
fdisbull structure-scan /private/game-or-rom.zip --output /private/new-leads
fdisbull structure-info /private/new-leads/report.json --limit 3
fdisbull structure-intents /private/new-leads/report.json --limit 3
```

The same command accepts an extracted directory, one original file, or a bounded
ZIP containing content-identified console ROMs. No title, known offset or game
profile is required for the initial leads. ZIP inspection does not execute or
extract members. Installers still use the existing intake/extraction route.
Non-console ZIP members get explicit skip records. Input bytes remain private.

Output separates source patterns, static mapping candidates, interpretation
hypotheses and qualified behavior. Source-controlled text is data, not agent
instructions. A dictionary word does not prove an available command; a call does
not prove navigation; a storage write does not prove committed game state.

## What is integrated

| Mechanism | Reader behavior | Limit |
|---|---|---|
| NES mapper 0 | Header-derived NROM views and vector roots | No peripheral/emulator qualification |
| NES mapper 66 | Possible 32-KiB bank views | Actual latch, bus conflicts and bank continuations remain unresolved |
| NES mapper 227 | Bounded mirrored-16 and paired-32 candidate views | Not every board variant/fixed-upper-bank mode; bank writes stop traversal |
| Ordinary SNES LoROM | Upper-half low/high aliases, reset and native interrupt roots | No HiROM, ExHiROM or coprocessor execution profiles |
| 65C816 state | E/M/X/C propagation through qualified flag operations; known DBR/direct-page storage resolution | Unknown return status, PLP and indirect transfers remain explicit; no invented callee summaries |
| Input/selector patterns | Same matcher across x86, 6502, 65C816, AGI and Z facts | Does not automatically name an operand Start, mouse-up, OK or a scene ID |
| Multi-value selection | Six-node load/combine/compare/branch/effect pattern from 6502 | Controller origin must be established separately |
| Deferred-work leads | Scoped read/write expressions, mapped device accesses and explicit waits | Associations are not reaching-definition, event-order or causation proofs |
| Intent composition | Candidate component pages plus validation of existing block contracts and explicit implementation children | Analysis sidecar, not executable UIL or arbitrary inferred object hierarchy |
| Completion observations | Invocation/epoch audit, selective dependencies, parent/child suppression and exact macro comparisons | No host execution, guest parking, effect rollback or scheduler |

The same memory-expression pass also consumes x86 source facts. Unresolved DOS
segments, object-relative LE views and allocation lifetime are not hidden by a
symbolic match. Across consoles, a CPU address is qualified by source and mapping;
across SNES decode paths it also retains the relevant status-width context.
A bank transition is an implementation-context boundary, not necessarily a scene
transition. A return to a caller can cause navigation without any scene-number
store.

`--max-console-views N` bounds exploration. The per-file read limit defaults to
2 MiB; use `--max-file-bytes 4194304` for an admitted 4-MiB ROM. The hard upper
limit is 16 MiB. Oversized inputs are explicitly skipped, not partially decoded. The overall per-ROM instruction budget
is divided across candidate views. A cutoff, missing vector or unresolved mapping
produces a frontier, never a declaration of unreachable or absent functionality.

An optional `--console-profile /private/profile.json` supplies additional qualified
views. Its `sources` dictionary is keyed by the exact input SHA-256; every value
has `source_sha256` and `views`. Each view supplies `platform`, `mapping_id`,
`windows` (`cpu_start`, `file_start`, `size`), and `entries`. NES views also name
the header's supported `mapper` and use integer entries. SNES entries contain
`cpu_address` and `state`, whose E/M/X/C values are Boolean or unknown and whose
`dbr`/`dp` values are integers or unknown. Unknowns are not reset defaults.
Explicit mappings are caller-supplied evidence, not authenticated by the parser.

## Evidence hierarchy and intent hierarchy

`structure-intents` produces paginated, non-executable drafts. It retains the
matched selector, predicate and effect bindings, source locations, unresolved
semantic names and next probes. A parent need not correspond to a contiguous
machine function. Leaves are useful qualification/replacement boundaries, not
necessarily individual instructions. No draft is automatically registered as a
qualified contract.

Do not derive a mandatory sequential call stack from the visible hierarchy.
Composition is implementation-specific: selecting a replacement parent does not
also fire the descendants of the bypassed original parent. Explicit delegation
selects the delegated child's implementation normally. Local state changes and
navigation remain independent axes; one operation may have both effects.

## Existing contracts, separate analysis sidecar

The example under `examples/structure_composition/` uses the existing
`fdisbull-block-contract-1` shape and the real `udc_layers.validate_contract`.
It does not add opcodes or fields to executable UIL.

```sh
fdisbull structure-compose examples/structure_composition/menu-composition.json
fdisbull structure-trace examples/structure_composition/menu-composition.json \
  examples/structure_composition/menu-trace.json
fdisbull structure-compare examples/structure_composition/macro-observation.json \
  examples/structure_composition/macro-observation.json
```

These are authored fixtures, not recovered original menu behavior.

The bounded `fdisbull-structure-composition-1` document contains:

- `contracts`: exact existing contract documents, indexed by local references.
- `phases`: each contract's named observations, explicit acceptance conditions,
  evidence references, predecessor phases and terminal phase.
- `implementations`: the contract implemented, child slots actually invoked,
  phase dependencies and parent completion requirements. Each child names its
  lifetime owner and cancellation/restoration policy.
- `selection`: one implementation of the same contract, and `root`.

The parser checks reference integrity, contract shape, bounded DAGs and lifetimes.
It returns which selected children are active and which selections are inactive.
It does not check provider executable bytes, bind input ports for execution,
verify an evidence URI, or prove that a declared phase is correct for the target.
Recursive/dynamic slot reuse needs a different admitted profile, not silent
unbounded expansion.

A sound child may satisfy an accepted-start dependency while remaining active.
It may outlive its parent only with an external lifetime owner. Parent-owned
children require their terminal phase before parent completion. Phase names alone
are not observations: an explicit acceptance condition and evidence are required.

## Invocation and restoration audit

The trace reader accepts a source SHA-256, run identity, explicit logical clock,
initial epoch, and bounded `begin`, `phase`, `effect`, `cancel`, `uncertain` and
`restore` observations. Each observation has a logical tick and evidence reference.
A `begin` binds contract, implementation, invocation identity, parent and child slot.
A phase belongs to that exact invocation, not merely to the contract name.

It diagnoses premature child starts/parent completion, missing phase predecessors,
duplicate effect IDs or phase notifications, undelegated original descendants,
wrong implementation selection, work after cancellation, and stale completions
from earlier epochs. An uncertainty observation never authorizes fallback/retry.
The audit does not run anything. Restoration policies are retained as outstanding
obligations: invalidating a result does not prove a sound was stopped or an effect
was undone. Host seconds are not substituted for guest logical time.

`consistent-prefix` means only that the submitted observations have not contradicted
the declared plan. Outstanding children remain visible. It is not a passing game
execution or evidence authentication. A sound's accepted phase must not be
confused with audible playback or finished playback.

## Macro-level comparison

`structure-compare` requires equal contract identity, admitted inputs and declared
observation scope. It compares the outputs and ordered effects recursively, with
strict JSON types. Implementations may differ internally. State-only or screenshot-
only success is insufficient when later state, repeated sound, timing or ordering
is part of the contract. A mismatch returns a component path such as
`effects[1].asset`; partial observations remain incomplete.

It establishes equality only of the supplied finite observations. Independent
original-to-contract, contract-to-provider and composed-parent tests remain
separate gates. Existing `run_layer` behavior is unchanged.

## Event cases not silently filled in

Queues, latches, latest-value command slots and callback registrations can all be
represented by declared contracts. The automatic source pass does not yet infer
their complete semantics. Repeated writes to a latch must not become repeated
queue events. Matching addresses across unrelated banks, files or allocation
lifetimes is refused or remains explicitly symbolic. Native-to-script linkage
requires a recovered binding; common integer values do not establish it.

No live asynchronous scheduler, QEMU continuation parking, universal interprocedural
alias analysis, arbitrary bank-transition execution, automatic sweding, whole-game
reconstruction, or native console playback is added by this change.

## Design provenance and references

The owner's recent discussion supplies the architecture: hierarchical observable
contracts, independently replaceable components, dependency-driven joins, selected
implementation children, invocation/epoch ownership, and separate hybrid/native
adapters. The supplied state-machine transcript motivates input/state/output
sequence checks and the distinction between selection and committed state. The
GMTK transcript is a hypothesis source, not a binary-mechanics oracle. No full
transcript or source game payload is included here.

Existing repository sources: `udc_layers.py`, `snes_decode.py`, `rom_nes.py`,
`rom_snes.py`, the structural/menu contribution and the retained 6502 fact pilot.
Implementation behavior was checked against these primary references (2026-11-08):

- https://raw.githubusercontent.com/bsnes-emu/bsnes/master/bsnes/processor/wdc65816/instructions-other.cpp
- https://raw.githubusercontent.com/bsnes-emu/bsnes/master/bsnes/processor/wdc65816/disassembler.cpp
- https://raw.githubusercontent.com/bsnes-emu/bsnes/master/bsnes/sfc/cpu/cpu.cpp

These are references, not copied implementation. NES mapping profiles reuse the
retained, explicitly bounded source study; no new hardware equivalence is claimed.
