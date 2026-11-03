# Syndicate graphics contracts and missing-code continuation

Investigation date: 31 October 2026. This is a source-qualified research
handoff, not a production analyzer patch, general CPU sandbox or native game
acceptance. It continues the diagnostic study in PR #69 and the incorporated
[whole-binary LE report](LE_WHOLE_BINARY_SCOPE_2026-10-30.md).

The study used an isolated fDisBull **0.26.0**, Python 3.13.5, Capstone 5.0.9,
iced-x86 1.21.0 and Z3 5.3.2. Main was separately inspected at
`90e748c8bc6a4f068f9136f4d4ec989672421a03`; its newer storage/integration work
was not silently substituted for the research runtime. No shared installation,
release, game original or existing source layer was changed.

## Result and identities

| Measure | Retained baseline | Continued checkpoint |
| --- | ---: | ---: |
| Stored instruction candidates | 67,838 | **68,264** |
| Unique instruction-covered bytes | 227,447 | **229,190** |
| Candidate functions | 630 | **630** |
| Stored cross-references | 80,914 | **81,433** |

The instruction union is **87.60% of the 261,620-byte executable object**, not
87.60% of recovered game logic. This pass adds 426 instructions and 1,743 unique
bytes without creating functions merely because switch cases were seeded.
All earlier instruction rows are identical. All 68,264 encodings match mapped
source bytes and an independent decoder agrees on their recorded lengths.
The size sum is 229,191: the previously recovered TEST/STOSB shared byte remains
represented by both interpretations and counted once in physical coverage.
SQLite integrity is `ok`; the ordinary work queue has no pending entries.
Derived analysis, semantic coverage and actual runtime reachability are separate.

Selected MAIN.EXE: 518,713 bytes, SHA-256
`bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078`.
Mapped image digest:
`98454a7d9845d423ec63c6393c31a3b093deb27c390e400148017bc15a69d51b`.
Both remain unchanged. All nine selected original resource files also retain
their intake digests. This is not a new rehash of the prior 929-file collection.

## 1. Three remaining drawing dispatches now have explicit local domains

| Outer entry | Dispatch | Recovered operation under the admitted mode |
| --- | --- | --- |
| `0x41EEE` | `0x41FD2` | Horizontal line on the primary planar buffer |
| `0x423F8` | `0x4257D` | Filled rectangle on the primary buffer |
| `0x4276B` | `0x428F0` | Filled rectangle on the secondary buffer |

The diagnostic preparations use mode byte 2, origins zero, viewport 640 by 400,
valid disjoint image/stack memory, color 0..15, 80-byte row strides and four
32,000-byte color planes. These are supplied contexts, not observed DOS startup.
The rectangle callers normalize negative dimensions by moving the origin and
negating the extent, then clip. The line caller first increments its second
endpoint and conditionally swaps endpoints; preserve that exact order rather
than replacing it with an idealized symmetric inclusive-line rule.

After first-byte handling, the cross-byte path starts with
`r = right - ((left & 0xFFF8) + 8)`. For clipped `0 <= left < right <= 640`,
its initial remainder is nonnegative and at most 632. The loop consumes 16
pixels while `r > 16`. Its selected helpers preserve EDI, the remainder carrier.
Consequently the exit dispatch is in **0..16** under this local contract.
A signed upper-bound comparison alone does not supply that lower invariant.

Fresh evidence:

- **48 caller-level cases** all returned and matched an independently authored
  full-buffer pixel oracle plus surrounding guards. Cases include clipping,
  negative/empty/outside rectangles, reversed lines and both image buffers.
- **51 additional calls** exercise every one of the 17 slots at each of the
  three tables. Actual traced targets and complete framebuffer results match.
- All 51 table slots match retained LE relocations. Candidate-only traversal
  from their previously missing starts adds **195 instructions**.
- The local model checks 15 exact source operations and 32 helper paths for
  EDI preservation. Three Z3 obligations are unsatisfiable for a violating
  result; two negative controls are satisfiable when the lower invariant or
  callee preservation is omitted.
- Exhaustive enumeration covers **205,120 clipped endpoint pairs**, including
  202,880 cross-byte pairs, all 17 exit indices and at most 39 full-loop steps.

The proof concerns the stated local model and successful-access/callee
assumptions. The native observations concern the tested preparations. Neither
is promoted into a proof that all game callers establish the domain, that
runtime tables are immutable, or that a full-game rendering path was executed.

## 2. Sprite interpretation must follow exact effects, not convenient labels

The common planar sprite dispatcher is `0x4D94F`. Its low two variant bits and
rounded width select implementations. For the previously admitted width domain,
the index is `(variant & 3) * 8 + ceil(width/8) - 1`; the original byte arithmetic
and signed shift still matter outside that domain.

A fresh **64-case** matrix contains 48 authored ordinary-width cases, 12
unsupported-width controls, and four calls using original sprite 800 through
its original descriptor wrapper. All returned with source canaries intact.

| Variant | Actual result within the tested unclipped preparations |
| --- | --- |
| 0 | Normal image |
| 1 | Horizontal reversal |
| 2 | Vertical reversal **one destination row above** the conventional oracle |
| 3 | Destination pixel buffer unchanged |

For variant 2, source row `row` goes to `y + height - 2 - row`, rather than the
conventional `y + height - 1 - row`. All 13 relevant matrix cases match the
source-specific oracle and differ from the conventional one. Two subsequent
calls through the original element-to-sprite caller also preserve this offset:
that inspected caller slice does not insert a compensating Y adjustment.
Intended image anchoring and full-screen composition remain unobserved, so this
is not yet labelled an unintended game bug.

Variant 3 still executes setup and can change registers/flags; unchanged pixels
do not mean no effects whatsoever. Width classes 3, 5, 6 and 7 dispatch to RET
in the inspected table. Twelve authored width-24/40/48/56 controls, for variants
0..2, return without drawing. Do not generalize this into globally dead code.

### Resource backtracking narrows the live-looking cases

The actual HSPR-0 table has **1,802 entries**: 1,520 width-16, 160 width-32,
119 width-64 and three empty width-zero records. All 1,799 nonempty entries fit
implemented width classes. The unsupported authored widths are absent from this
selected table; that does not prove their absence from every possible source.

The **10,486 animation elements** have flags 0 in 7,252 cases, flags 1 in 3,232,
and flags 2 in exactly **two**, with no flags-3 element in this set. Both flags-2
elements use sprite 800. Following element chains, frame chains and animation
starts ties them to three frames reachable from **animation 390**.

A separate native update loop processes 256 records of 30 bytes. Its statically
inspected cases for states 10, 13 and 16 request animation 390; the common tail
loads its first frame from the animation-start table. Three actual tail-slice
checks demonstrate new selection, retaining an already selected animation,
and ignoring a zero request. Together with the two element-caller cases, all
**five caller-slice checks** reach their selected stopping boundaries and match
the declared outputs.

This establishes more than a filename guess: there are actual resource links,
source assignments and observed local consumers. It still does not identify a
player action that creates those state values, execute the entire effect loop,
or establish the intended screen appearance. Historic libsyndicate research
calls the corresponding 256-by-30-byte area SFX; that is an attributed semantic
lead rather than independent original-game runtime evidence.

## 3. Four additional dispatches emerged as the map expanded

The current 67,838-instruction baseline already contained 87 indirect jumps,
not the 83 counted at the older 62,837 checkpoint. Four newly visible sites
had not yet entered the earlier conditional-map inventory.

| Site | Local selector | Initial table slots |
| --- | --- | ---: |
| `0x25910` | Unsigned byte at most 44; reload and mask to eight bits | 45 |
| `0x3A607` | Byte decrement with wrap, unsigned result at most 18 | 19 |
| `0x24DEF` | Two masked flag bits, explicit upper clearing and shift | 4 |
| `0x15945` | Global byte at most 3, cleared full register before low-byte write | 4 |

**80 original-instruction cut probes** cover admitted indices and rejection
controls; all stop at the expected dispatch or reject boundary with the expected
index. All **72 pointer slots** agree with the initial relocated image.
Twenty distinct starts were genuinely absent before this pass. Traversal adds
**231 instructions**; already stored targets remain deduplicated.

These local observations do not certify every predecessor or mutable-table
value. The research deliberately adds no `resolved_indirect` control edges.
There remain **87 stored indirect jumps and 18 indirect calls**. A conditional
map count must not be confused with a production resolved-edge count.

### A classifier has an inherited-register result, not simply true/false

At entry `0x258F0`, a nonzero gate word returns zero. With the gate clear, eleven
admitted type values return one, thirty return zero, and **types 36, 40, 41 and
42 return incoming EAX unchanged**. Out-of-range type bytes also reach that
inherited-result return. This is actual source behavior, not a claim about the
author's intention or the source language's return-value rules.

**53 callee probes** check all 45 admitted type values, inherited/out-of-range
controls and the nonzero gate. They all match and preserve the tested EBX value.
Six further checks execute one original caller slice. It computes a record
offset using stride 92, calls the helper, and tests **AX**, not all of EAX.
Under otherwise matching diagnostic type-36 records, index zero retains type 36;
index one supplies offset 92 and the caller changes the type to 2. True/false
controls behave consistently. These are six selected-boundary observations,
not ordinary scenario activation or a demonstrated gameplay exploit.

A reconstructed Boolean helper would lose this caller-state dependency. Preserve
incoming register bits, result width and caller use until a stronger domain
proves the distinction irrelevant. A separately requested bug fix would need a
changed-behavior contract instead of an exact-fidelity claim.

## 4. Reproduction and failures retained

The previous private workspace was not live in this context. The exact executable,
retained baseline and source-free seed plans were recovered. A first short host
command ended during replay; a fresh process resumed the durable queue. The
67,838-row baseline was restored before new candidate work. This restoration is
not counted as fresh independent discovery. Nine selected assets were recovered
from exact matching installer streams and rechecked against their retained
size/hash identities, not by executing the installer.

Execution remains the earlier bounded Linux x86-32 compatibility harness: RX
original code, explicit writable data/scratch, supplied registers/stack, finite
budgets, forbidden environment operations, return/pre-jump stops and owned-child
cleanup. It is **not DOS/4GW, a device model, normal gameplay or a malicious-code
sandbox**. No sound driver was executed this time.

| Fresh planned matrix | Cases | Expected results matched |
| --- | ---: | ---: |
| Drawing callers | 48 | 48 |
| All three drawing-table slots | 51 | 51 |
| Sprite implementation/negative-width matrix | 64 | 64 source-specific results |
| Resource/animation caller slices | 5 | 5 |
| Four new selector cut matrices | 80 | 80 |
| Inherited return, callee and caller | 59 | 59 |
| Total planned case executions | **307** | **307** |

The 307 cases comprise 216 returns and 91 selected-boundary stops. A separate
RET calibration adds one execution. An authored harness defect accidentally
repeated the 64-case sprite matrix during import before detecting an occupied
receipt path. Those repeats returned, but their separate raw traces were not
saved; captured command output remains. The original receipt was not overwritten
and the intended caller batch had not started. Total actual executions therefore
include **372 calls**, not merely 307 successful planned cases.

The harness was corrected with a main guard and an output check before target
execution. A mocked-run preflight verifies import performs zero calls and an
occupied destination fails before dispatch. This was a research harness error,
not a fDisBull defect or game bug. It motivates the session requirements below.

A second research helper initially compared integer targets with canonical
hexadecimal-text FDB addresses, overlabelling offered seeds as new. The engine
correctly deduplicated them. The corrected ledger uses the immutable pre-pass
backup, records offered versus genuinely absent targets, and preserves the
original mistaken receipt. No source bytes or target behavior changed.

## Handoff

[Diagnostic tooling requirements](DIAGNOSTIC_TOOLING_REQUIREMENTS_2026-10-31.md)
turn the observed friction into scoped acceptance criteria: candidate admission,
loop/callee contracts, exact implementation observations, resource reverse links,
and preflighted persistent experiment records. Those are proposals, not claims
that this PR implements a runtime or passes production conformance.

Private receipt locators include `graphics-caller-summary.json`,
`all-draw-slots-summary.json`, `draw-loop-model.json`,
`sprite-contract-summary.json`, `sprite-resource-graph.json`,
`resource-callers-summary.json`, `new-dispatch-summary.json`,
`new-table-extension-corrected.json`, `inherited-return-summary.json`,
`harness-friction.json` and `final-analysis-v2.json`. Source-only reproduction
tools and selected sanitized receipts are delivered separately; no original
code bytes, framebuffer, asset payload, memory image or byte-retaining database
is added to Git.

The next material questions are the writers and legal domains of the SFX states,
the meaning and legitimate use of inherited-return types, the remaining large
unclassified executable-object gaps, and actual audio-module registration and
playback state. Static resource reachability is not player reachability.

References:

- [PR #69 methodology and motivating study](https://github.com/seeker-cyber-maker/fDisBull/pull/69), source `641b7e950e000422a9f740757471498f54fffeb2`.
- [Current main analysis entry and private queue](https://github.com/seeker-cyber-maker/fDisBull/blob/90e748c8bc6a4f068f9136f4d4ec989672421a03/src/fdisbull/analysis.py).
- [FreeSynd graphics notes](https://freesynd.sourceforge.io/ff.php.html) and [Paul Chavent's libsyndicate research](https://icculus.org/libsyndicate/libsyndicate.html): external terminology/format leads, not substitutes for the original-instruction observations.
