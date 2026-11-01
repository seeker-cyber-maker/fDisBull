# Syndicate: graphics caller contracts and missing-code continuation

**31 October 2026.** The analysis continues the privately retained 67,838-instruction checkpoint. No original game executable or asset was changed. The new findings, code-discovery plan, diagnostic tools and sanitized results are included in this bundle.

**GitHub delivery status:** the PR files and patch are prepared locally. This session's GitHub connector exposes read operations but no branch/commit/PR creation action, and no authenticated GitHub CLI is installed. No new PR was created. Existing PR #69 remains a separate earlier methodology delivery; it was not modified by this pass.

## Executive result

- **68,186** stored instruction candidates, **228,882** unique instruction bytes and **87.49%** of the executable object's extent. This is not semantic coverage or ordinary reachability.
- **262 original-instruction diagnostic calls passed:** 176 complete line/rectangle comparisons and 86 sprite/animation comparisons. Every owned child was reaped.
- The three formerly blocked graphics tails, plus a newly examined sibling, have a conditional **0..16** index contract established from caller setup and a decreasing loop.
- Vertical reflection preserves an actual one-row anchor shift through an original higher-level frame caller. It is not silently replaced with a conventional graphics flip.
- LX sound service getters require interrupt/environment semantics even when they appear to return metadata. Those drivers were not executed.
- A fresh replay reproduces **all 68,186 instruction rows**, and all **897 recovered selected asset paths** retain their prior identities.

## Exact implementation coordinates and provenance

These are preferred addresses in the exact selected MAIN image, not observed DOS/4GW load addresses or globally reusable labels.

| Role | Preferred address | Evidence boundary |
| --- | --- | --- |
| Horizontal span, first framebuffer | `0x41EEE` | 44 full-routine diagnostic cases |
| Horizontal span, second framebuffer | `0x42173` | 44 cases; newly seeded sibling; ordinary caller reachability remains unknown |
| Rectangle fill, first framebuffer | `0x423F8` | 44 full-routine cases |
| Rectangle fill, second framebuffer | `0x4276B` | 44 full-routine cases |
| Tail dispatches | `0x41FD2`, `0x42257`, `0x4257D`, `0x428F0` | Conditional caller/loop bounds, sampled before the instruction |
| Seventeen-slot tail tables | `0x41FD9`, `0x4225E`, `0x42584`, `0x428F7` | Initial relocated image and candidate-only discovery |
| Sprite wrapper, second buffer | `0x4CF23` | 80 individual sprite calls |
| Sprite dispatcher | `0x4D92B`, indirect branch `0x4D94F` | Selected mode and widths, not arbitrary sprite input |
| Higher animation caller | `0x1E050` | Six calls using original frame/element/sprite data; one shared five-element chain |

Framebuffer globals are `0x55368` and `0x55374`. Viewport origin and dimensions occupy four dwords starting at `0x55380`. The tested mode is byte `2` at `0x80105`; other modes are not inherited. Native line arguments are `(left, right, y, color)`; rectangle arguments are `(x, y, width, height, color)`.

Each plane occupies 32,000 bytes, with an 80-byte row stride. The drawing oracle changes individual bits in a nonuniform initial buffer rather than reusing the original mask tables. The 176 drawing checks compare both full 128,000-byte buffers and both sets of 32-byte guards. The 86 sprite checks compare the complete selected buffer; those are not additional two-buffer/canary tests.

The selected animation frames are 1767, 2306 and 2310. All select the same element chain `[4235,4236,4237,4238,4239]`; different next-frame links do not make them independent visuals. Elements 4238 and 4239 select sprite 800 through TAB byte displacement 4800. Its width/height are 16/8 and DAT offset 71412. The positions are (-53,22) and (-49,-34). A structural chain from start index 390 links the relevant frames; this does not establish a player-visible scenario. The selected frame sound field is zero, so the unchanged caller bypasses sound naturally rather than using a fabricated service response.

The original input is 518,713 bytes with SHA-256 `bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078`. The relocated mapped-image digest remains `98454a7d9845d423ec63c6393c31a3b093deb27c390e400148017bc15a69d51b`. Native execution was on Linux x86-64 in explicit x86-32 compatibility mode, not inside DOSBox. The research runtime remains fDisBull 0.26.0 even though current main was inspected at `90e748c8bc6a4f068f9136f4d4ec989672421a03`.

## Driver boundary

GAMEDG.DLL and GAMEFM.DLL each use preferred base `0x10000`, coinciding with MAIN's preferred code base. The privately reconstructed objects are 5,904 and 15,515 bytes, with 276 and 395 internal fixups and 19 and 38 services respectively. These are module-local identities, not simultaneously observed placements.

Service-100 candidates enter at object offsets `0xD97` and `0x2560`. The first interrupt-control instruction occurs at preferred `0x10D9B` / `0x12566`. The candidate descriptor pointers are preferred `0x100CB` / `0x10163`. CLI/STI and saved interrupt flags are a real environment obligation, even on this seemingly simple query. No driver code was executed, no CLI/STI was skipped, and no sound-completion claim was made.

## Complete handoff

The remainder is the implementation handoff prepared for the repository. Its acceptance cases are prospective product requirements, while the explicit authored arithmetic checks and private original-instruction observations above were executed.

## Results and claim boundaries

The exact owned Syndicate MAIN.EXE remains 518,713 bytes, SHA-256
`bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078`.
The original bytes, mapped images, resource payloads, raw CPU receipts and
byte-retaining databases remain private and are not included here.

| Result | Established scope |
| --- | --- |
| Three previously blocked graphics dispatches, plus a sibling routine | Caller setup, clipping and a decreasing remainder explain a 17-entry tail table in the admitted planar domain. |
| 176 original-code line/rectangle probes | All returned and matched an independently written, source-informed pixel oracle; both framebuffer identities, untouched buffer, guard bytes and preserved input registers were checked. |
| 86 sprite/animation probes | All returned with complete selected-framebuffer agreement: 64 authored sprite cases, 16 uses of one actual resource sprite, six original higher-caller invocations. |
| Six higher-caller invocations | Three frame IDs at two positions; the IDs share **one five-element render chain**, not three independent visuals. Original resources supplied pointers/content; the selected zero sound field avoided, rather than stubbed, the sound path. |
| Discovery continuation | 67,838 to **68,186** stored instructions, **228,882** unique instruction bytes, **630** function candidates and **81,351** xrefs. |
| Byte and replay audit | Every stored encoding matches the mapped original and an independent decoder's length. A fresh source-free seed replay from the 22,910-instruction checkpoint reproduces all 68,186 instruction rows. |
| Dynamic coverage | **2,525 distinct original instruction starts** across 262 diagnostic calls; all are present in stored analysis. This is not ordinary-game reachability or 2,525 independently qualified routines. |
| Driver boundary | Even apparently descriptive service getters in the two external LX drivers execute CLI/STI-related interrupt control. No driver execution or hardware result is claimed. |

The instruction-byte union is **87.49% of the executable object's 261,620-byte
extent**, not a percentage of recovered game meaning. The instruction-size sum
is 228,883: the previously supported TEST/STOSB shared byte is counted once in
physical coverage and twice in its complete encodings. All 22,910 original
baseline instruction rows were retained, and the previous 67,838 rows were
unchanged by candidate additions. There are still 88 stored indirect jumps and
18 indirect calls; this study did not manufacture resolved production edges.

Execution used an authored Linux x86-64 launcher and explicitly supplied
32-bit compatibility-mode state, with source code RX, bounded private buffers,
a return sentinel, finite instruction/time limits and child cleanup. All 262
owned children were reaped. This is **not a DOS/4GW process, device emulator,
security sandbox, full-game run or reconstructed executable**. The harness is
not a new production capability in this PR.

## 1. Caller and loop contracts, not another global budget

The relevant routines are clipped horizontal-span and rectangle fills over
four planar 640-by-400 buffers. A color helper handles full middle words; a
17-slot table handles the tail. Under the admitted coordinate and nonaliasing
state contract, the initial remainder is:

```text
r = right - ((left & 0xFFF8) + 8)
```

The domain is `0 <= left < right <= 640` in different aligned byte cells. The
middle loop subtracts 16 only while `r > 16`. Nonnegativity and decrease give
`0 <= r <= 16` at the dispatch, including index **16**. A signed upper-bound
check alone admits negative values. Dropping the earlier endpoint ordering
also admits a negative initial remainder. Both weakened models have retained
counterexamples.

Five Z3 checks covered initialization, loop preservation, exit bounds and those
two negative controls. A separate exhaustive enumeration covered **202,880**
admitted endpoint pairs, all 17 tail indices and at most 39 middle iterations.
Thirty-two source color-helper paths were checked for preservation of the
remainder register, with twelve decisive source-operation anchors checked.
These source checks and native cases support a **conditional local contract**;
the small solver model is not automatically a translation of every caller path.

The native matrix covers both buffer selectors, all 16 colors, every tail
index, translated viewports and representative clipped, empty, reversed or
negative inputs. The source's admission rules are retained, including increment
before horizontal endpoint swapping and signed rectangle normalization. Do not
replace those with a generic normalized rectangle API without comparison.

### Tool friction: candidate entry is not necessarily a function

At the reviewed main, [`AnalysisMixin.analyze(start=...)`](https://github.com/seeker-cyber-maker/fDisBull/blob/90e748c8bc6a4f068f9136f4d4ec989672421a03/src/fdisbull/analysis.py)
queues the start and inserts a `user seed` function candidate. The study instead
used the existing private `_queue_code` seam for switch labels and a
source-supported sibling entry. This added 348 instructions without increasing
the function-candidate count. It is a reproducible research workaround, not a
stable public API.

**Recommendation:** expose candidate-only seeding with explicit source/context,
reason, evidence and confidence/claim scope. Keep candidate decoding separate
from function inference, indirect-edge admission and runtime reachability.
Persist its frontier and allow bounded continuation without re-adding seeds.
A tool should not require an investigator to mislabel a switch case as a
function just to decode it.

**Recommendation:** let qualified caller ranges, memory identity/alias facts,
loop invariants and callee-preservation summaries feed a conditional dispatch
record. Keep assumptions and a bypass-path obligation. Unknown table mutation
or another entry must prevent global promotion, not erase the useful local map.

## 2. Asset domains improve diagnostic preparation

Each inspected HSPR table has 1,802 entries, of which 1,799 are nonempty. The
nonempty widths are 16, 32 and 64; the first narrower forced experiment was not
a representative HSPR input. That does not make the 8-pixel code path globally
unreachable. Table names, resource family and actual consuming routine matter.

Each edition's element flags have counts 7,252 / 3,232 / 2 for values 0 / 1 / 2;
none has literal 3. The two flag-2 records select the same sprite. Three frame
IDs lead to the same five-element chain containing those records. This is a
resource-reference path, not an identified player scenario or proof that no
caller can construct another flag value.

The source's transparency operation is `(destination & mask) | color`.
Inspected asset groups clear color bits underneath transparent pixels; the
oracle did not assume the operation would skip arbitrary malformed color data.

The tested vertical-reflection path uses:

```text
destination_y = supplied_y + height - 2 - source_row
```

That is one row above the conventional `height - 1 - source_row` anchor. The
higher original frame caller preserves this behavior. The comparison retained
it and a deliberately conventional-anchor mismatch; it did not silently repair
it to match a familiar graphics API. Intended artistic anchoring remains
unknown, so this is not a confirmed gameplay bug. Variant 3 wrote no pixels in
the tested width/mode domain; that is not a dead-code classification.

**Recommendation:** attach resource-domain facts to diagnostic recipes and
source consumers: observed widths/flags, bounds, transforms, encoding and
structural reference chains. Separate corpus absence, modeled infeasibility,
diagnostic execution and ordinary reachability. Preserve shared-chain identity
so six calls are not advertised as six independent content cases.

**Recommendation:** qualify a primitive's exact footprint and coordinate anchor
before naming it `flip_vertical` or replacing it with a standard library call.
Record anchor shifts, transparent suffixes, clipping, buffer selection and
caller-visible argument changes when they affect the chosen boundary.

## 3. Reusable routine probes need explicit execution and effect contracts

Useful evidence required a private launcher, ABI/buffer setup, instruction
single-stepping, selected pre-instruction register samples and complete
framebuffer comparisons. A screenshot alone would not distinguish a stray
plane write, corrupted neighbor buffer or a one-row anchor difference.

A future supported routine-probe profile should record:

- Exact source/module identity, byte version, ISA/mode/load context and the
  selected entry; no implicit reuse of preferred addresses as live selectors.
- Supplied arguments, registers, flags, stack/return state, globals, resource
  bindings and mapped memory permissions/extents. Caller state and fabricated
  diagnostic state are distinct preparation provenance.
- A finite instruction/time budget, a semantic or return stop, passive sampling
  boundaries, prohibited services and explicit fault/environment-stop outcomes.
- Expected write domains, nonselected-buffer/canary checks and relevant full
  output comparisons, plus successful owned-child cleanup independently of the
  target outcome. Return alone is not contract satisfaction.
- Immutable trial identity and output paths. Refuse overwriting an earlier raw
  receipt. Retain source bytes privately; export identities and scoped summaries.

The study's added sampling is **before instruction execution**, not proof that
the sampled instruction completed. A production integration should use a
qualified debugger/backend seam, not bypass its resource or execution authority.
A host compatibility profile may be useful for environment-independent routines
but must retain a different identity and claim ceiling from DOS execution.

## 4. External modules and environment-dependent instructions

Both examined sound drivers are LX and declare the same preferred base as the
main executable's code. Service pointers therefore require module identity and
an actual load instance; flattening them into MAIN's address space would create
false relationships. The private one-object mapping is not production LX support.

Even the service-100 descriptor-return candidates pass through CLI and related
interrupt-state handling. The ordinary host compatibility harness stops before
unsupported environment instructions; it cannot execute these getters faithfully
by treating CLI/STI as no-ops. No device or driver execution was attempted here.

**Recommendation:** qualify a module-aware driver path with object-relative
entry identities, relocations and load generations, and make the first missing
environment requirement explicit. A chosen virtualized-interrupt experiment can
be useful if declared as such, but cannot inherit original DOS/4GW fidelity.
Connect service ID, registered module/table, runtime pointer and active device
only when those edges have evidence. See the separately qualified
[DOS audio work in PR #41](https://github.com/seeker-cyber-maker/fDisBull/pull/41); a common service label does not make
these particular drivers or their completion returns already qualified.

## Prospective implementation acceptance

These are future product requirements, not a tally of passing product tests.

| ID | Priority | Required result |
| --- | --- | --- |
| DG01 | P0 | Public candidate-only seed preserves version/context/evidence, does not automatically create a function or a proved edge, and resumes after reopen with the same candidate inventory. |
| DG02 | P0 | Caller/loop proof retains the 0..16 inclusive domain, detects negative indices when lower-bound/order premises are removed, and preserves mutation/bypass/alias unknowns. |
| DG03 | P0 | A probe result separately records target outcome, output checks, observation phase and child cleanup. Success cannot be inferred solely from RET or process exit. |
| DG04 | P1 | Portable preparation capsules reject wrong source/module/mode or unsupported services, and retain negative/fault/budget results without silently expanding memory or synthesizing service success. |
| DG05 | P1 | Resource-derived preparation records corpus identity and consumer relationships; missing flags and repeated frame chains do not turn into dead-code or independent-case claims. |
| DG06 | P1 | Semantic graphics replacement preserves the established anchor/footprint, both buffer roles and admitted transparency behavior; a conventional-anchor negative control must fail. |
| DG07 | P1 | Driver targets with coincident preferred addresses remain distinct by module/load identity. Privileged/device requirements produce explicit stops until a selected backend contract supports them. |
| DG08 | P1 | Evidence output is append-only or versioned, with compact source-free summaries and explicit private payload references; replay neither overwrites earlier generations nor requires distributing game bytes. |

## Reproducible authored check

Run from the repository root:

```sh
python tools/check_contract_models.py --require-z3
```

The script requires no game input and checks only the declared arithmetic model.
Without `--require-z3`, an unavailable optional solver is reported as unavailable,
not passed. Its [receipt](evidence/public-model-checks.json)
binds the exact script digest. The private source-anchor/callee inspection and
262 original-instruction probes are separate evidence; the public checker does
not reproduce them or qualify the production analyzer.

## Verification and retained limitations

- The public checker enumerated all 202,880 pairs and passed its five expected
  solver outcomes, including both counterexamples, with Z3 5.3.2.
- All 262 native diagnostic cases met their declared comparisons and returned;
  source instruction bytes were unchanged and every owned child was reaped.
- The newly packaged seed plan replayed every stored instruction row exactly.
  Full original-file and mapped identities remained unchanged; all 897 restored
  selected resource paths matched their prior recorded identities. Their paths
  came from the retained manifest, not a newly recovered installer path table.
- Local source and documentation checks cover Python syntax, receipt digest,
  UTF-8/newlines, Markdown/link structure and exclusion of private payloads.
  No full repository suite, installed 0.27 native run or production compiler
  conformance is claimed for this documentation/model-fixture change.
- An optional Z3 dependency was missing on the first research proof invocation;
  the supplied offline wheel was then installed privately. Initial ad hoc asset
  queries also used the wrong decoder return shape and expansion filename suffix.
  These failed before native probes and were corrected as setup/query errors,
  not classified as target/tool bugs. No native matrix failure was hidden.

The prepared PR does not alter #69, the selected original game, current production
analysis rules, shared installations, release tags or other agents' branches.
Related #41 audio modules, #53 media adapters and #57 interpreter-assisted
recovery remain separate capabilities and evidence scopes.
