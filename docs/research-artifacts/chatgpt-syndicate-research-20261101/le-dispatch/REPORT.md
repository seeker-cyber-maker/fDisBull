# Syndicate LE: conditional dispatch and code-discovery continuation

**Investigation date:** October 30, 2026, America/Toronto. Final audit captured
at 2026-10-31 01:17 UTC. This continues the retained 22,910-instruction checkpoint,
not a new import or an original-game execution.

## Executive result

Stored instruction discovery increased from **22,910 to 62,837**. The union of
instruction-covered bytes increased from **71,411 to 209,709**, or **80.16% of
object 1's 261,620-byte declared extent**. This is a denominator of executable
object storage, not a claim that 80.16% of game logic is understood or reachable.
The remaining extent includes undecoded code, data, padding and unresolved roles.

The main advance was to recover finite conditional dispatch maps, rather than
repeatedly increase a global analysis budget. There are **75 locally qualified
jump-table sites**: 71 unsigned-guard cases and four two-predicate cases. Their
initial tables contain **1,200 distinct pointer slots**, occupying **4,800 bytes**,
and point to **587 distinct initial targets**. Every slot agrees with the retained
LE relocation records. None of those table bytes overlaps the stored instruction
byte union.

| Measure | Before | After |
| --- | ---: | ---: |
| Stored instructions | 22,910 | 62,837 |
| Unique instruction bytes | 71,411 | 209,709 |
| Candidate functions | 384 | 609 |
| Stored cross-references | 27,027 | 75,275 |

Function counts are hypotheses, not original source function boundaries. Of the
609 entries, 591 came from direct calls, one from the LE entry, and 17 from
explicit seeds. Twelve of those explicit seeds are switch case labels created
by the public analysis API during the initial experiments; five are runtime
initializer/finalizer targets. Later case discovery used the private queue seam
without creating a function merely because a case label was seeded.

The eight retained replay stages contain **540 seed entries**. Following them
from a separate baseline copy and resuming after a host time limit reproduced
all **62,837 instruction rows** exactly in address, context, bytes, size, mnemonic,
operands, flow and target. This verifies replay of the researched candidate set,
not independent rediscovery or a new runtime oracle.

## 1. The first blocked switch was a value-tracking problem

The original stalled dispatch is at preferred image address `0x10779`, using a
17-entry table at `0x10550`. Its local path compares a 16-bit memory value with
16, escapes when unsigned-above, reloads the same field through another register,
clears EAX and writes AX before indexing the table.

A byte-array memory model preserves the equality of the two stack loads and the
selected record field. Partial-register writes preserve upper bits unless an
actual clear eliminates them. Under valid, stable flat memory and execution
through this slice, the dispatch index is therefore in **0..16**. The selected
slice contains no intervening write or call. Negative controls change the reload
address or omit the high-register clear; both admit out-of-range counterexamples.

The 17 table slots have 11 distinct initial targets. Ten target starts were
missing. Their bounded discovery added **320 instructions**. One recovered case
then exposed a nested dispatch at `0x10c91`, with another 17-slot table at
`0x10594`. It has three distinct targets; its two missing case starts added
**35 instructions**.

The same local issue recurred elsewhere. The narrow checker models byte, word
and dword aliases, full-register clearing, supported arithmetic and actual MOV
stores using byte-wise memory updates. It does not assume that a store cannot
alias a later reload. Adjacent unsigned CMP/JA guards, feasible guard domains,
aligned in-range offsets and nonwrapping table addresses are checked. Unsupported
operations, address-size overrides and nonflat segment dependencies are refused.
A solver timeout or an unknown result is not an acceptance.

**Qualification boundary:** these are statements about traversals through a
specified guard slice. They do not prove that every path into the dispatch
passes through that guard, that a player can reach it, or that table contents
remain unchanged at runtime. The compared table is the initial relocated image.
The research maps remain separate from production resolved-control edges.

## 2. Four graphics-oriented dispatches use predicate-built indices

Four additional sites at `0x4398c`, `0x4878e`, `0x488b7` and `0x4a3a1` form an
index from two comparisons. They begin with a zero offset and conditionally add
8 and 4, so the table byte offset is one of **0, 4, 8, 12**.

The source-binding check verifies the input masks, sum construction, comparison
operands, branch targets that skip each addition, all EAX writes, intervening
escape branches, and the final indirect jump. It is not just a proof of a
handwritten formula that resembles the code.

Two sites mask each input to one bit. In those local models, slot 2 cannot be
selected: a sum of two implies both bits are one, which also selects the second
predicate. The table still contains that slot. This establishes local
infeasibility from the modeled entry, **not globally unused code**; an alternate
entry or another caller could change the conclusion.

The fourteen newly seeded, locally feasible case entries exposed another
**6,270 instructions**. The surrounding routines manipulate buffer pointers,
coordinate-like values and pixel-related shifts. That supports a graphics-oriented
classification, not full recovery of rendering semantics.

## 3. A small runtime record structure is now visible

The first switch belongs to a routine at `0x105e0` that processes **eight records
of fourteen bytes** beginning at `0x9be3a`. The outer loop increments the byte
offset by 14 and the count to eight; a later scan covers exactly 112 bytes.

| Offset | Storage width | Current recovered interpretation |
| --- | ---: | --- |
| `+0` | 4 bytes | State/completion value. Exactly 1 satisfies the final scan. |
| `+4` | 2 bytes | Type selector, admitted as 0..16 on the recovered dispatch path. |
| `+6` | 2 bytes | Offset-like object reference; selected consumers add base `0x8810e`. |
| `+8` | 2 bytes | Coordinate-like argument; units and complete meaning unresolved. |
| `+10` | 2 bytes | Coordinate-like argument; units and complete meaning unresolved. |
| `+12` | 2 bytes | Further component requiring interpretation. |

This is a **partial runtime-memory layout**, not a recovered disk format. Its
base lies in the LE object's declared zero-filled area. A file loader or writer
still needs to connect these runtime records to serialized resources.

The structure behaves like a mission/objective evaluator: type cases inspect
objects and update completion-like state, and the final scan can enter a terminal
helper. That name remains an interpretation until presentation and normal-game
observations establish the player-facing role of every field and case.

## 4. Name-triggered behavior and an alternate completion condition

Newly decoded code compares two text fields of a selected **1,047-byte record**
against embedded trigger strings. The fields are at `+0x11` and `+0x23`. Their
player-facing labels and the normal input route have not been qualified here.
The comparison helper performs a NUL-terminated byte comparison, folding ASCII
A..Z to lowercase; it is not a Unicode or locale-aware comparison.

Two concrete conditional effects are recovered:

- **DO IT AGAIN:** matching either inspected field sets byte `0x60b48` to 1.
- **ROB A BANK:** matching either inspected field sets byte `0x60b43` to 1 and
  writes **100,000,000** into the selected record's first dword.

The bank-like trigger strongly suggests a money-related feature, but the
numeric store was not observed as an on-screen cash balance in this pass.
Neither finding is presented as a verified player activation recipe.

The final eight-record scan enters helper `0x10510` when every state equals 1
**or** when both byte globals `0x5e2b2` and `0x60b48` are nonzero. The helper
itself first checks existing terminal-state bits. Thus DO IT AGAIN is linked to
an alternate completion path, but its additional gate at `0x5e2b2`, earlier
routine guards and complete gameplay consequences remain unresolved. No missing
writer is interpreted as proof that the flag is constant.

No external cheat guide was used to obtain these trigger/effect links. They are
static source-derived findings, not a completed speedrun route, known legal
category shortcut, or native demonstration of a cheat.

## 5. Startup/finalization callbacks were recovered structurally

A separate pair of loops walks six-byte callback records:

| Table | Range, end exclusive | Records |
| --- | --- | ---: |
| Initialization | `0x5c32c` to `0x5c344` | 4 |
| Finalization | `0x5c344` to `0x5c34a` | 1 |

Each record contains a one-byte state/type marker, one-byte priority and relocated
four-byte callback at offset 2. The caller selects eligible priorities, calls the
pointer and marks the record as processed using value 2. Initialization chooses
the lowest priority, with the last encountered equal-priority record selected;
finalization chooses the highest. All five initial records have priority 32 and
state zero. Decoding their five targets added **302 instructions**.

These findings came from the original instructions and relocated data first.
A later comparison with Open Watcom's `initrtns.c`, pinned at
`e082e2445fc73d35f38367d0fddb8a35f94be42a`, corroborated the runtime-family pattern:
priority scans, indirect callback invocation and processed marker 2. It does
not identify an exact original compiler version or establish byte-for-byte
identity with that modern source.

Primary source:
https://github.com/open-watcom/open-watcom-v2/blob/e082e2445fc73d35f38367d0fddb8a35f94be42a/bld/clib/startup/c/initrtns.c

Do not confuse these tables with the three writable slots at `0x5bff4`,
`0x5bff8` and `0x5bffc`, whose initial value is a RET target. The latter are still
unqualified as runtime constants. The full relocation census exposes their
four direct call references, but does not exclude indirect writes or prior
call effects. The stack-alias concern is still visible rather than bypassed.

## 6. What remains open

Of the **83 stored indirect jumps**, 75 now have conditional local table maps.
The other eight are:

| Site(s) | Missing obligation |
| --- | --- |
| `0x25a67` | A stack store occurs between loading the compared byte and reloading it. Under unconstrained addresses it may alias that field. Establish disjointness rather than deleting the possible write from the model. |
| `0x3bb73` | Register-carried dynamic target. Recover its producer and admitted values. |
| `0x41fd2`, `0x4257d`, `0x428f0` | Signed loop/remainder bounds and relevant callee-preservation requirements, not merely a nearby upper-bound comparison. |
| `0x42b98`, `0x42d70` | Entry-register contracts from callers. The local entry is already the indirect dispatch. |
| `0x4d94f` | Width-dependent byte arithmetic, signed shift and decrement. Zero or other unqualified inputs can invalidate the tempting small-index assumption. |

There are also **18 indirect calls** without qualified production control
targets. Two have the recovered startup/finalization table interpretation; that
is still not a proof of immutable runtime target sets. Return destinations are
caller-dependent and are not included in these indirect-jump/call counts.

The ordinary instruction work queue is drained. The older derived-analysis
ledger is not: **351 done, 14 partial, 19 pending**, plus **225 newly discovered
function candidates not registered in that earlier derived pass**. Those old
results were not promoted to fresh whole-program proofs.

The project also retains **106 bytes with both code and data-item tags**. Tags
are not mutually exclusive ground truth. The 4,800 verified table bytes do not
intersect the instruction union. The earlier TEST/STOSB shared-byte case remains
intact, with two interpretations and one physical byte counted once.

## Verification and reproducibility

- Every baseline instruction encoding and size is preserved.
- All **62,837** stored instruction encodings agree with the mapped original
  image. A separate Capstone decode agrees on all recorded lengths. This is a
  byte/length cross-check, not independent proof of code reachability or effects.
- The source container and mapped-image identities are unchanged. SQLite
  integrity checks pass on the continuing and replay projects.
- All 71 guarded models were rerun with the final checker. Ten authored model
  checks passed, including negative cases for stale upper bits, changed reloads,
  potentially aliasing writes, impossible guards and address-size overrides.
- All four Boolean-dispatch bindings passed the stronger source-structure check.
- A separate source-free seed replay reached the same full instruction view.
  Its first invocation hit a host command time limit at 56,567 instructions with
  14 queued entries. A fresh process continued that stored queue, without new
  seed injection, and reached 62,837 identical rows. A clean uninterrupted replay
  is not claimed; the retained interruption is documented in the receipt.
- Fixture authoring encountered an incorrect escape displacement and a CALL
  opcode where the intended test was a JMP. Those authored fixtures were corrected
  before the final ten-check run; they were not classified as product defects.

The active analysis tool was the supplied **fDisBull 0.26.0** offline wheel,
Python 3.13.5, Capstone 5.0.9, iced-x86 1.21.0 and Z3 5.3.2. A fresh GitHub read
confirmed main `f94a5cd` separately. This work did not install main, alter the
production analyzer, add proved indirect edges, run the game, rebuild an LE,
or demonstrate overlap-to-UDC output in Syndicate.

The included tools and replay plan are research artifacts. They preserve the
difference between a conditional local bound, an initial table value, candidate
code discovery and actual runtime behavior. The seed replayer deliberately
requires fDisBull 0.26.0 and a new private destination. It uses a private queue
seam, not a promised stable public API.

## Implementation priorities

1. Preserve guard values through partial registers and reloads with explicit
   memory-alias facts. Do not infer non-aliasing merely because a store looks
   stack-related.
2. Add candidate-only table discovery distinct from proven control edges and
   distinct from function-entry creation. The current research workaround must
   not masquerade as integrated production analysis.
3. Model predecessor/caller and loop contracts for the remaining graphics
   dispatches, then qualify runtime table mutability and dynamic callbacks.
4. Keep source, candidate-decoding, dataflow, semantic and native coverage as
   separate ledgers. Preserve overlapping instructions and source-byte unions.
5. Connect the 14-byte runtime records and 1,047-byte profile records to actual
   resource-loading/writing paths before publishing them as disk specifications.

## Knowledge pack

**Architecture:** LE mapping and fixups -> stored x86 instructions -> conditional
local guard model -> initial table correspondence -> candidate queue -> expanded
stored decoding. Source-backed semantic observations remain separate.

**Decisions:** Preserve the baseline and original bytes; no blanket pointer
seeding; no fabricated resolved control edges; no original payload publication;
retain uncertain runtime mutability, aliases, entry paths and game meanings.

**Next:** The strongest remaining targets are the precise alias obligation at
`0x25a67`, caller/loop contracts for the graphics dispatches, and the additional
gate for the recovered name-triggered completion behavior.
