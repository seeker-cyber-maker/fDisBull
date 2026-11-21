# Reversing machinery and faster harness construction

Audit date: 20 November 2026. This inventory covers the current Keen development
checkpoint, its installed Python runtime, the bundled native source, retained
native capability receipts, and relevant fDisBull source. It is an audit and a
small offline transfer demonstration. No production implementation, dependency
installation, native launch or new gameplay test was performed.

## Assessment

Selected fDisBull components should make harness construction easier and faster.
The strongest candidates are scalar memory narrowing, repeat/contrast execution
searches, native reader/writer and control-flow queries, and typed record layouts.
The immediate integration priority is a reusable owned capture/trial runner and
a portable private game-profile loader. Those provide a usable route from the
existing debugger to the analysis algorithms and preserve the resulting work.

DotBox already has instruction decoding, memory/register access, breakpoints,
traces and native checkpoints. Its ordinary service exposes only a small part
of those capabilities. Successful Dune and Keen experiments still require
target-specific adapters or private owner scripts. Adding a second decoder
would leave much of that assembly work in place.

A fresh offline demonstration provides one concrete result: fDisBull's unchanged
scalar-search kernel reduced **65,533 possible unaligned 32-bit positions to two
candidates** for a known score change of 100, in **38.509 ms** for that refinement.
The independently known score location survived. The other candidate remains
unexplained. This demonstrates useful candidate reduction, not a measured
end-to-end improvement in harness preparation time.

The [authored evidence receipt](evidence/reversing-inventory-2026-11-20.json)
pins the source, installed checks, demonstration, independent reviews and scope.

## Source and evidence boundary

| Material | Audited identity | Qualification |
| --- | --- | --- |
| DotBox current source | Primary `7d4573ea0e8b0ef72faf73f26ebf74d25bc0a144`; local `b494d4123a182d74b5440cd79eda8b79bb557a93`; shared tree `1433870a1fce7be20c387115f0a59f477bda56a0` | Development branch, not a release or main integration |
| Installed DotBox | `0.1.0.dev9`, Python `3.12.14`, iced-x86 `1.22.0`, Pillow `12.3.0` | Fresh doctor and source/module/resource comparison; no new native qualification |
| Native base | DOSBox-X `029bd65c5dcc7cdc7f2e14e35278620d9707d969`, fDisBull-derived agent base `ce91c303f2fccd1db9b1e3917ecc8c98473bfdb9`, plus DotBox overlays | Source present; selected prior native capability and gameplay evidence retained |
| fDisBull delivered-package reference | Linux 0.34.1 portal record identifies `ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd` | Main comparison source, fetched at the immutable commit; full package not installed for this audit |
| fDisBull GitLab release tag | `v0.34.1` at `011f1b8cb281edda208026aee9cdb238b800b2d7` | Distinct release metadata; not substituted for the portal package's source identity |
| fDisBull observed main | `829453ecae3fb0de236dbdd95be85a554efd1fb7` | Reviewed generic search/CFG/type/serializer files have unchanged blob identities relative to the package source |
| Newer QEMU work | `95580d960ad5acaf3f3bb42b8a8c68fa7d880f82` on `codex/qemu-parity-20261120` | Separate branch work, not attributed to the delivered package |

The DotBox primary main-to-Keen comparison was 62 commits ahead and zero behind.
The complete RTS/Keen tree comparison found no extra RTS file missing from this
Keen checkout. This inventory therefore includes the existing RTS action/world
modules, while preserving their provider and live-qualification limits.

## What DotBox includes

Availability and qualification are separate. An installed API can be exercised
offline; a native capability can be implemented and previously advertised
without every mode being freshly tested. A packaged experiment can be useful
while still requiring a caller's live ownership adapter.

| Capability | Included surface | What it currently does |
| --- | --- | --- |
| Executable/resource identity | `dotbox inspect identity`, `inspection.py` | Selected COM/MZ file layout, entry/relocation information and hashes of explicit resource files; no automatic complete-edition or overlay identity |
| Strings | `dotbox inspect strings` | Bounded ASCII extraction with locations, hashes and truncation; no string-to-code reference index |
| Byte/signature search | `dotbox inspect find` | Exact/masked overlapping byte matches in selected windows; no semantic instruction-pattern search |
| x86 disassembly | `dotbox inspect disassemble`, iced-x86 | Bounded 16/32-bit linear listing with invalid/truncated-instruction handling; no native reachability, function, CFG or definition/use recovery |
| Byte differences | `dotbox inspect diff` | Comparable-span before/after byte-run differences; no persistent typed candidate narrowing |
| Session and transport | `NativeSession`, `DOSBoxRPC`, operation budgets | Owned native process, session binding, request limits, deadlines and cleanup; a direct Python caller can reach native methods |
| Native register/memory access | Bundled DOSBox-X agent | Register read/edit and memory read/write in supported address spaces; not exposed as a general investigation operation in the normal service |
| Native execution control | Bundled agent, bounded wait helper | Step into/over, continue/pause/wait, bounded frame advancement and guest clocks; individual methods retain their negotiated limits |
| Breakpoints and watches | Bundled agent | Execution, memory-change and read/write access breakpoints; retained access-watch scope is normal CPU core, real-mode byte addresses |
| CPU traces | Bundled agent | Bounded trace support; retained selected-build capability reports a 10,000-event maximum; no normal DotBox trace-query workflow |
| Checkpoints | Native save/load and DotBox restore-generation fence | Machine-state primitives and research batch restore; no fully qualified ordinary player rewind operation |
| Images and pixel observation | Native screenshot/pixel probe, screenshot codecs | Original-frame capture and bounded pixel observations; useful recognition evidence, independent of world coordinates |
| Saved ordinary controls | `HarnessLibrary`, `ControlStore`, input macros | Immutable keyboard/mouse control definitions, source binding and declared admission; no arbitrary debugger-write/native-call route |
| Learning frontier | `LearningStore`, `dotbox learn` | One bounded foreground question, findings, evidence references and clock identity; not a structural analysis graph or automatic probe scheduler |
| Current facts and choices | `SceneStore`, scene projection, core oracle | Stores supplied current observations and derives qualified situations/choices; does not discover field semantics or capture the game |
| AGI resource analysis | `dotbox agi`, three small AGI modules | Supported uncompressed AGI V2/2.917 resource census, vocabulary/object metadata, conditions, write sites and resource references |
| AGI control/value analysis | AGI layout/scene analysis | Typed low-level IR, branch successors and bounded conservative value propagation; this is meaningful engine-specific analysis, not a general native equivalent |
| Geometry and action planning | Spatial map, navigation, RTS world/actions | Routes and admitted action proposals over supplied qualified state; no automatic native-layout discovery |
| Installed instructions and source preparation | Kit resources, doctor, native preparation recipe | Operational guides, exact native patches/manifests/notices and authored self-checks; native binary/platform qualification remains separate |

These findings are grounded in the [inspector][db-inspection], [service][db-service],
[native source recipe][db-native], [installed kit][db-kit], [AGI scope][db-agi] and
[resource manifest][db-resources].

### The public-interface gap

`PlayService` has read operations `status`, `frame`, `harness-list` and
`harness-info`; its mutation set covers ownership/control, play/pause, ordinary
inputs, closing, saving a harness and executing an admitted action. Coordination
and ownership bridge operations are separate. It has no generic capture,
register read, memory read/write, watch, trace, trace-search or rewind operation.
The optional MCP connector exposes ownership status, not the analyzer inventory.

The installed `NativeSession.call` can reach the native facilities. The missing
product layer is an owned, bounded and coherent investigation operation that
also handles stop identity, cleanup, budgets and evidence. Exposing raw RPCs
without those obligations would not provide the intended reusable workflow.

### Experiments already worth promoting

Four Dune components **are included in installed resources**:
`dune_probe_batch.py`, `dune_ui_reader.py`, `dune_progress.py` and `dune_map.py`.
They can be recovered with the kit, but are not ordinary `dotbox.*` runtime
modules or top-level analysis commands. They require a supplied session-bound,
generation-fenced adapter and a qualified target profile.

The Dune batch already performs comparable-baseline restore, probe cleanup and
re-arming, ordinary input, bounded capture, per-trial recording, final restore
and disk-canary checks. Its historical nine-trial dispatch measurement was
**3.233 seconds**, plus **0.418 seconds** for the prepared baseline. Full
observation took **18.080 seconds**. That historical run used its recorded
research runtime; it does not qualify a different binary or a new generic API.
The reusable lifecycle is a strong existing starting point. [Dune batch][db-batch]

The Keen loop, actor, world, waypoint and oracle adapter, plus browser preview,
exist in source but are outside the current installed resource catalog. Current
trials load frozen copies and private target bindings. The core oracle itself
is physically installed. These are packaging/integration gaps, distinct from
an absent algorithm. [Keen loop][db-loop]

## What is missing or incomplete

| Missing layer | Present foundation | Work still required |
| --- | --- | --- |
| General owned capture/trial API | Native debugger plus Dune lifecycle and Keen coherent loop | Profile-driven capture requests, exact stop ownership, comparable baselines, neutral input, one deadline, observer re-arming and retained failure outcomes |
| Portable game profile and observer loader | Hashed private layouts, hooks, code guards and control definitions | One manifest joining startup, source/layout assumptions, observers, static/dynamic reads, dependencies and qualification; fresh current-state admission on reuse |
| Scalar candidate narrowing | Existing byte/masked search and diff | Typed unknown/exact/range searches, successive predicates and retained candidate lineage |
| Execution-event comparison | CPU traces and game-specific analysis scripts | Common trace/event contract, repeated-action intersection, contrast/idle subtraction, witnesses and explicit coverage |
| Native relationship analysis | iced-x86 linear decode | Mapped instruction facts, xrefs, possible readers/writers, CFG/call edges, bounded value propagation and unresolved indirect-target frontiers |
| Reusable typed native readers | Hand-authored Dune and Keen observers; AGI reader | Struct/array/pointer schemas, validation, sparse-read dependency recording and mapping/lifetime invalidation |
| Persistent investigation index | Learning and observation stores | Source/context-bound hypotheses, layouts, code facts, trace references and dependency invalidation, separate from current gameplay facts |
| General phase/input calibration | Retained Keen phase/timing experiments | Reusable comparison of queued input, input consumption, simulation effect, collision/reaction and presentation clocks |
| Broader native/engine formats | Selected COM/MZ startup and AGI profile | Only the specific new loader/resource/save reader required by a target; no general SCI/SCUMM/Z-machine/LE live provider is installed |
| Qualified original-call/entry routes | Existing guidance and fDisBull precedents | Selected ABI, arguments, omitted setup, return/continuation and effect qualification for each supported operation |

There is no general native decompiler, symbolic executor, whole-program taint
engine, generic unpacker, complete function recognizer, analysis graph store,
transition-family dependency scheduler or UDL/UIL/UDC compilation pipeline in
the inspected DotBox runtime. Those absences have different priorities. Current
evidence favors capture, narrowing, binding and reuse before broader compilation.

## Which fDisBull tools would help

The following are implemented at the pinned package source, with source/CLI
routing inspected. Except for the scalar-search demonstration below, this
audit did not execute the fDisBull algorithms or install its full application.

| Existing fDisBull machinery | Concrete use in harness construction | Integration assessment |
| --- | --- | --- |
| `memory_search.py` and its runtime adapter | Find likely score, ammo, selected-object, timer or coordinate fields by exact/range/change/delta observations | Highest-value small kernel: standard library only; feed DotBox captures and retain all candidates |
| `execution_events.py`, `event_search.py` | Compare repeated button A with idle/button B; retain likely dispatch sites and site/register/value combinations | High value; pure event kernel plus a DotBox provenance/storage adapter; uses the decoder already available |
| `memory.py`, `facts.py`, `advanced.py` | Ask which decoded instructions may read/write a candidate field and what a call may affect | High value for turning an address into a rule; preserve unresolved addresses, segment assumptions and widths |
| `cfg.py`, `function_analysis.py`, `flowdata.py`, `indirect.py` | Follow branches, shared tails, callback tables, state-machine cases and bounded value propagation | Useful second layer; pure kernels need correctly normalized instruction/semantic facts and an index |
| `typesystem.py` | Define actor records, arrays, near/far pointer domains and fields once; decode later observations consistently | High reuse value; schemas do not discover meanings or prove live mappings |
| `debug_experiments.py` | Store repeatable scripts, checkpoint/observation definitions and bounded baseline/layer trials using the same stored script | Reuse its contracts while generalizing DotBox's already demonstrated batch; lifecycle work is larger than a kernel copy |
| `serializer_discovery.py`, `serializer_candidates.py` | Find candidate save/load data flows and serializers in supported linear32 code, with explicit ABI hypotheses | Target-dependent; valuable for DOS extenders/save structures, not a ready real-mode Keen invocation tool |
| `source_native.py` | Bind known source/listing/link-map information to emitted procedures and selected calls; bounded EXEPACK profile | Useful for source-available games; does not establish universal source/binary equivalence |
| `project.py`, `incremental.py`, `runtime_code.py` | Preserve analysis, interpretations and their invalidation across versions and contexts | Reuse selected record contracts and small stores; complete Project import is a broad architecture dependency |
| `proofs.py` and format/engine readers | Check explicit small finite-width rules, or replace native discovery with the correct resource parser | Add for a concrete target question; solver success concerns the supplied model, and recognition alone is not engine support |

Primary sources: [memory narrowing][fdb-search], [event search][fdb-events],
[memory effects][fdb-memory], [analysis API][fdb-api], [types][fdb-types],
[experiments][fdb-experiments], [serializers][fdb-serializers],
[source correspondence][fdb-source] and [format registry][fdb-formats].

### Important limits on reuse

The package's `debug-trace-until` path requires an owned stopped **unpaged
real-mode DOS** session. Its `native-capture-watch` helper watches **1–16
explicitly supplied E8 rel32 callsites** under a qualified flat32 selector.
Neither is an automatic survey of every function exit or all visible buttons.
A coordinator must supply candidates, perform comparable trials and preserve
first-hit/truncated/no-hit coverage. [Trace collector][fdb-trace], [call watch][fdb-watch]

Static memory-access facts are possible effects, not a list of every actual
runtime writer. Retrospective event subtraction narrows observed correlations,
not causation. CFG/flow kernels cannot become a native analyzer without a valid
fact-producing layer. These limits should remain in the DotBox interfaces.

## Offline transfer demonstration

The unchanged fDisBull scalar-search kernel was loaded directly from its pinned
source, using only the standard library. It read the retained initial/final
64 KiB data-segment snapshots from a completed original Keen collection run.
No guest ran, no live memory was read or written, and no package was installed.

The region and unsigned little-endian 32-bit interpretation came from prior
knowledge. The known score location was used only for independent validation,
never to seed or restrict the search. This is a warm transfer of a search tool
to real game data, not blind recovery of an unknown memory layout.

| Operation over the complete selected region | Result | One observed wall time |
| --- | ---: | ---: |
| Start unknown, 32-bit, stride one | 65,533 positions | 0.101 ms |
| Refine that initial search for any changed value | 274 candidates | 36.214 ms |
| Separately refine the initial search for delta +100 | 2 candidates | 38.509 ms |
| Independent search for initial value zero | 27,640 candidates | 22.402 ms |
| Refine the zero-valued set to final value 100 | 2 candidates | 16.312 ms |
| Existing DotBox byte diff on the same files | 104 changed bytes in 69 ranges | 4.848 ms |

The changed-value and delta searches are parallel branches of the original
unknown set, not an executed 65,533→274→2 chain. The two surviving candidates
include the independently validated score field; the other meaning is unknown.
Candidate narrowing still needs a writer/consumer query or another discriminating
observation to establish semantics.

Both a changed-context input and a corrupted snapshot payload were refused.
The result retains source/run/mapping identity, hashes, candidate lineage and
complete result sets. An independent reviewer checked script semantics and
recorded hashes without rerunning the trial.

The byte diff was faster in this run and performs a simpler operation. The useful
benefit here is reducing what the agent must investigate. One-shot local timings
do not estimate model latency, capture cost or total harness-development savings.

## Where preparation time actually went

Existing evidence separates fast mechanical experiments from assembling and
qualifying their inputs:

| Historical workflow | Recorded observation | Tooling implication |
| --- | --- | --- |
| Dune dispatch survey | Nine trials 3.233 s plus 0.418 s baseline; first native interaction to first completed batch 452.216 s | A batch can run quickly once target binding and the driver exist; prioritize preparing/reusing those inputs |
| Keen gameplay preparation | 797.421 s to useful play against a 600 s warm allowance | Retain the miss; includes setup/submission and correction work, not just reversing |
| Active Keen actor-model trace | 881.622 s within its 1,800 s declared research allowance | Source/model binding, original trace setup and analysis are distinct from live-loop evaluation cost |
| Live oracle integration | 450.314 s from its recorded warm start to first selected observed movement | Reusing known gameplay still requires owner/observer/policy/test assembly |
| Repeated Keen owner code | Three private owner scripts are about 31–33 KB; eight identical normalized top-level functions | Capture and evidence plumbing is being reconstructed across experiments; scenario-specific policy still differs |

These are differently scoped historical clocks. Earlier work lies outside some
clocks, and no per-tool time attribution or percentage saving is established.
[Dune preparation][db-batch], [gameplay][db-gameplay], [actor model][db-actor],
[oracle live test][db-oracle-live].

The latest Keen owner depends on a frozen bootstrap from the display study, the
original decoder bound to the exact executable and observed load layout, an
earlier opening plan, baseline benchmark,
code/terrain bindings and a frame-store helper. A private manifest and loader
could retain those relationships directly. Reusing a profile must still verify
the current source, mapping, phase and input owner; historical qualification
cannot become a current control token.

Relationship analysis would also address real mistakes. Keen's field called
`objectcount` was cumulative allocation count, so linked-list traversal supplied
the live census. Renderer stops could sample an intermediate clock state. Raw
vertical speed stayed nonzero after landing. An idle animation broke a test
that incorrectly froze the animation state. These examples require writer/
consumer, lifetime and phase evidence in addition to a numeric match.

Dune's sparse reader already records dependencies and reduced measured
conversation-entry RPCs from 227 to 56 and bytes per action from 1,572,879 to
117,315. A shared typed dependency reader could make that approach reusable in
other profiles. Those measured transport reductions are not measurements of
agent preparation-time savings. [Sparse reader qualification][db-sparse]

## Recommended implementation order

Priorities and relative effort below are engineering judgments from the observed
seams. They are not measured development-speed rankings or delivery estimates.

| Priority | Small deliverable | Expected benefit | Relative work and acceptance |
| --- | --- | --- | --- |
| P0 | Owned capture/trial operation, generalizing Dune's lifecycle | Removes repeated restore/arm/input/timeout/cleanup code and returns coherent evidence | Medium integration effort; reproduce the dispatch matrix and refusal cases with one owner, no replay after uncertain delivery and recordings outside rewind |
| P0 | Portable private profile/observer bundle with an installed loader | Removes recovery of dependencies across old work directories; enables warm reuse | Medium effort; fresh process loads a known profile and refuses changed source/mapping/phase while completing the same bounded action |
| P0 | Scalar memory narrowing over captured buffers | Quickly reduces candidate fields; demonstrated on retained game data | Small core, moderate integration; preserve complete candidates, scalar semantics, lineage and context refusal through the ordinary interface |
| P1 | Repeat/contrast trace queries and common trial records | Finds candidate dispatch/selectors and reuses evidence-analysis code | Small kernel plus capture/storage adapters; retain witnesses, comparability and no-hit/first-hit limits |
| P1 | Native read/write/xref index, then bounded CFG/flow | Connects candidate values to code and related controls | Medium-to-large fact/model integration; authored binaries plus a bounded actual target question, explicit unresolved paths and segment/mapping identities |
| P1 | Typed record/dependency reader and phase-calibration recipe | Reduces bespoke decoding and false assumptions about clocks, animation, pointers and stale fields | Medium effort; full/sparse observations match and source/pointer/epoch changes invalidate correctly |
| P2 | Small persistent investigation/dependency ledger | Avoids rediscovery and lets one schema/dispatcher finding unlock siblings | Medium effort; separate hypotheses from accepted facts and current observations, invalidate dependent results, avoid duplicate work |
| P2, target-driven | Additional engine/save/source readers and original-entry helpers | Removes a concrete parser, mapping or traversal obstacle | Variable effort; qualify one edition/profile/ABI and its actual continuation before reuse |

The first useful integrated workflow is: capture a comparable before-state,
perform one known ordinary action under bounded probes, capture the after-state,
narrow fields or code events, inspect the surviving writer/consumer candidates,
and save the accepted observer/action profile. Dot handles hypotheses and the
next discriminating question; deterministic tools handle the mechanical trial.

## Dependency and architecture choices

DotBox already pins iced-x86 1.22.0. The inspected fDisBull package pins iced-x86
1.21.0, Capstone 5.0.9, LIEF 1.0.0 and Pillow, with optional Z3, Unicorn,
managed-code, source and console tooling. Importing the entire package would
therefore introduce additional dependencies and a decoder-pin conflict.

The scalar-search core needs only the standard library. The event core uses
iced-x86, but its behavior should be tested against DotBox's selected version.
The pure graph/flow/indirect kernels require an appropriate normalized fact
producer. Current memory-effect and serializer modules also import Capstone;
either extract the required functionality with its reviewed dependencies or
adapt the required x86 facts to the existing decoder. Type, event and analysis
adapters currently depend on fDisBull's Project/SQL contracts.

Favor small owned modules and explicit evidence formats. A complete Project
import would couple DotBox to broader analysis, debug artifacts, source,
proof and UIL machinery. Retain source provenance and applicable notices when
actually extracting code; this audit publishes no fDisBull code port.

The newer QEMU branch has useful source/mapping/task-lifetime work and an explicit
[review of DotBox contracts][fdb-transfer]. It also preserves separate backend
qualification. Those designs may help future overlay/extender profiles; replacing
the emulator is not required for the first capture/search/profile improvements.

Full decompilation, general symbolic execution, broad fuzzing and the UDL/UIL/UDC
pipeline can wait for a question that benefits from them. Bounded parser/contract
tests and small model checks remain useful. Improving the recent oracle's GC
and RPC latency tails is a separate runtime optimization objective.

## Fresh verification and packaging finding

The installed doctor verified **81 resource hashes** and passed its authored
decoder, AGI, scene and navigation checks. All **40 physically installed runtime
Python files** match current source. Four focused offline suites passed:

```text
venv/bin/python -m pytest -q tests/test_inspection.py tests/test_agi.py \
  tests/test_learning.py tests/test_dune_probe_batch.py
133 passed in 0.73 seconds; exit 0
```

Doctor explicitly reports native qualification false because it does not launch
or test the native backend. This audit uses prior native receipts with their
original scope and does not promote advertisements into new live acceptance.

There is one concrete reproducibility issue: the existing installed distribution
RECORD lists 39 runtime modules; the recently installed, source-matching
`oracle.py` is absent from that older RECORD. It works in the current environment,
but reinstalling the old wheel would not reconstruct this complete runtime.
A rebuilt, qualified package and portable profile should precede a claim that
another Dot can reproduce this setup from one installation. No repair was made
under this audit request.

## How to verify that harness construction improves

Benchmark the preparation workflow separately from the game loop. Freeze the
source, game edition, starting state and initial knowledge in both arms. A test
using known Keen addresses is warm reuse; a cold-transfer question needs a
withheld answer or a different bounded target with comparable exposure.

Record five milestones: first useful ordinary input; first qualified coherent
observer; first admitted semantic action; saved reusable profile; and successful
profile reuse in a fresh owned process. Also count source searches, raw tool
requests, agent decisions, newly authored glue and failed qualification attempts.
Retain setup delays and failures rather than restarting the clock.

The correctness gate is the same observed control/effect, the same source and
state admission, and the same refusal of incompatible captures or stale actions.
The efficiency gate is less preparation/assembly work at those milestones.
Start with capture/profile/scalar search, measure that slice, then add event and
native relationship analysis against a concrete remaining bottleneck.

[db-inspection]: ../src/dotbox/inspection.py
[db-service]: ../src/dotbox/service.py
[db-native]: STANDALONE_NATIVE.md
[db-kit]: LEARNING_KIT.md
[db-agi]: ENGINE_AWARE_PREPARATION.md
[db-resources]: ../src/dotbox/resources_manifest.json
[db-batch]: DUNE_BATCH_PROBE.md
[db-loop]: ../scripts/experiments/keen_loop.py
[db-gameplay]: KEEN_GAMEPLAY.md
[db-actor]: KEEN_ACTOR_MODEL.md
[db-oracle-live]: ORACLE_REALTIME.md
[db-sparse]: DUNE_OPTIMIZATION.md
[fdb-search]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/memory_search.py
[fdb-events]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/execution_events.py
[fdb-memory]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/memory.py
[fdb-api]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/docs/API.md
[fdb-types]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/typesystem.py
[fdb-experiments]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/debug_experiments.py
[fdb-serializers]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/serializer_discovery.py
[fdb-source]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/source_native.py
[fdb-formats]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/format_registry.py
[fdb-trace]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/execution_trace.py
[fdb-watch]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/z_capture_watch.py
[fdb-transfer]: https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/95580d960ad5acaf3f3bb42b8a8c68fa7d880f82/docs/QEMU_DOTBOX_TRANSFER_REVIEW_20261120.md
