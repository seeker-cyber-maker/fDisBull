# Overlapping instructions: UDL closure, UIL meaning and UDC layout

Status: implementation contract, 2026-10-30. The bounded
[entry-qualified backing engine](CODE_BACKINGS.md) implements complete stored
encodings, explicit continuations and raw single-context x86 layouts. The
separate [native UDL-to-UDC bridge](NATIVE_UDL_UDC.md) persists logical block
plans and defaults to exact original-layout pass-through without inserting
duplicates. Relayout is explicit and independent of UIL behavior. The
acceptance cases below retain their broader requirements; this is not a
general overlap-aware executable compiler or original-game reconstruction.
This supplements the accepted [definitions](DEFINITIONS_AND_ROADMAP.md) and
[original-backed DOS compiler limits](UDC_DOS.md), rather than changing their
current capability claims. The motivating bounded evidence is in the
[LE whole-binary findings](LE_WHOLE_BINARY_SCOPE_2026-10-30.md).

## Required separation

| Representation | Responsibility |
| --- | --- |
| Original source | One immutable physical byte may participate in multiple instruction interpretations. Count it once in source coverage. |
| UDL executable blocks | Each independently materialized block must contain its complete instruction encoding, including its own copy of a byte shared in the original. Preserve source provenance, decode context, entries, exits and state/effect dependencies. |
| UIL | Keep recovered intention and behavior. Physical instruction overlap is an implementation detail, not an obligation of the semantic operation. |
| UDC and orchestration | Select implementations, place blocks, adapt interfaces, remap entries/continuations and repair control flow, references and relocations so the selected output preserves the admitted behavior. |

UDL may retain content-addressed source storage once internally, but independent
materialization must resolve a complete local encoding. A block cannot borrow
its last opcode/operand byte from whatever block happens to be emitted beside
it. This is logical/executable closure, not a requirement to duplicate immutable
storage globally or to duplicate all downstream callees inside each block.

## The motivating two-entry pattern

The LE study retained a TEST instruction whose immediate byte is also a STOSB
opcode on a separately targeted entry. Both decodes have incoming control-flow
evidence and the same next boundary. The following is a normalized instruction
illustration, not a shipped game code dump or a claim of recovered game intent:

```text
source entry A:       TEST AL, 0xAA   ; complete encoding A8 AA
source entry B=A+1:   STOSB           ; complete encoding    AA
source join J=A+2:    shared continuation
```

Entering A executes TEST, consumes both bytes and reaches J without a store.
Entering B executes STOSB and reaches J. Physical source extent: two bytes.
Sum of the two complete local encodings: three bytes. The same source AA byte
appears once as an immediate and once as an opcode in independent UDL backings.
Output control-transfer machinery can add further bytes. Do not promise an
exact output-size increment for a general transformation.

The direct UDL route must retain actual instruction behavior. TEST changes
flags even though AL is unchanged. STOSB performs its memory write and updates
the destination index according to DF and the selected address-size mode.
State includes the relevant segment/address environment, live flags, memory,
caller state and continuation. A plausible high-level label cannot erase them.
Intel's [TEST](https://read.seas.harvard.edu/~kohler/class/aosref/i386/TEST.htm)
and [STOS](https://read.seas.harvard.edu/~kohler/class/aosref/i386/STOS.htm)
80386 instruction references describe the architectural operations; they do not
prove target-level reachability or a game-specific purpose.

## UDL: independently enclosed executable backings

Materialize one complete instruction stream per admitted entry interpretation.
For the illustration, block A owns local bytes A8 AA; block B owns local byte AA.
Record their shared origin separately from their different executable roles.
At minimum, the backing/contract needs:

- Immutable source identity and byte version, ISA/mode/decode context, logical
  entry identity and local instruction boundaries.
- Source-to-local provenance for every copied span, allowing one source byte to
  map to more than one local occurrence with different roles.
- Entry ports and explicit exit/continuation identities, including formerly
  implicit fallthrough. J is a logical continuation, not a retained adjacency.
- Live-in/live-out state, clobbers, flag dependencies, ordered effects, memory
  assumptions and any still-unresolved dependency.
- Local relocation/reference sites and their target entry identities. Source
  addresses remain evidence and binding data, not the UIL operation's meaning.

"Self-enclosed" does not mean each block is a standalone process, has no inputs,
or can be moved without an adapter. It means its code is complete and its
external obligations are explicit. A copied instruction with a dangling hidden
fallthrough is not a qualified independently executable block.

Distinguish logical blocks with distinct entry semantics even when they share
source storage. A byte-only global replacement or a single source-offset-to-one-
output-offset map cannot represent this relation safely. Index mappings by
source context, entry interpretation, block revision and local occurrence.

A source-byte patch potentially invalidates both backings and their dependent
qualifications. An edit to only one independently selected backing is a new
implementation choice, not silently the same source patch. Keep original bytes,
source alias relationships and all previous revisions intact.

## UIL: overlap disappears from the semantic contract

UIL should not care whether the original implementation saved a byte through
instruction overlap. Once meaning is qualified, the overlap is automatically
abstracted away as part of the ordinary separation of intention from backing:
no special physical-overlap primitive, address or adjacency rule belongs in the
UIL merely because the original used one byte twice.

That does not make recognition of overlapping decodes an automatic proof of
higher-level intent. The two entry paths may implement different effects.
Recover those effects and conditions; only eliminate low-level flag or store
operations when their irrelevance at the chosen semantic boundary is established.
Unknown behavior remains an explicit residual backing, not invented intention.

When physical layout itself is observable, retain the required observation as a
semantic dependency or compatibility service. Examples include code-as-data
reads, address comparisons, checksums, self-modification and external entry
addresses. UIL can still be layout-independent while a selected UDC supplies
that compatibility; silently discarding an observed dependency is not abstraction.

## Direct UDL to UDC: orchestration must preserve the two paths

The direct reconstruction path must work without first recovering game-level
UIL. It can select the retained entry-qualified UDL implementations and compose
them under their lower-level contracts. It is not simple byte concatenation.

For example, concatenating A8 AA and AA as `A8 AA AA` makes the TEST path also
execute the separate STOSB. That introduces a memory write and index update
which the original A path skipped. It is wrong despite both instructions being
individually complete and decodable.

One valid candidate layout under an admitted state/effect profile is:

```text
new_A:
    TEST AL, 0xAA
    JMP new_J         ; skip the independently emitted store block
new_B:
    STOSB
    JMP new_J         ; optional if new_J is its actual next instruction
new_J:
    shared continuation
```

This is a proposed layout strategy, not an emitted or native-tested result.
The orchestration layer must do the following:

1. Resolve each original entry to the corresponding new logical entry. Redirect
   all qualified direct branches, calls, tables and pointer references, including
   the original branch into an operand byte. Do not preserve `new_A + 1` as B.
2. Turn every exit/fallthrough into an explicit continuation edge before physical
   placement. A must bypass B; both must reach the correct J exactly once.
3. Recompute branch displacements, widen encodings or insert qualified thunks
   where needed, then lay out again until all distances and fixups are valid.
   Rebuild affected container metadata when producing a runnable image.
4. Preserve relevant flags, registers, segments, memory effects, stack/caller
   state, ABI and ordered partial effects. Glue must not introduce a call frame,
   flag clobber or extra store unless an explicit adapter accounts for it.
5. Preserve mappings from source entries and byte occurrences to final output
   ranges in the build capsule. Distinguish source identity, semantic revision,
   backing revision and layout revision; changed placement is not automatically
   changed intention or proof of preserved behavior.
6. Compare behavior from every admitted entry and relevant state, including
   rejected/error paths. Individually valid blocks do not establish valid
   composition. Timing or address-observation fidelity needs its own contract.

Other strategies are allowed when qualified: duplicate a small successor tail,
preserve the original overlapping group in a constrained source-backed island,
or lower both paths to another target representation. Architecture/mode and
ABI constraints still apply; retained 32-bit instructions are not automatically
valid 64-bit code. Do not require the original overlap to remain physically
present in a regenerated program if a simpler nonoverlapping layout preserves
its behavior.

### Observable aliasing and unresolved entries

Duplicating immutable code is not always behaviorally neutral. A write to the
shared source byte could change both interpretations; two unrelated output
copies would not reproduce that relationship. Code-as-data reads and computed
interior addresses can also observe the old layout. Establish absence in the
admitted domain, explicitly maintain the alias/translation relationship, retain
a qualified original-layout island, or refuse that transformation as unresolved.
An unresolved computed target must not be silently redirected to a guessed entry.

Exact original-byte reconstruction is a different output mode. It requires the
retained original source/layout recipe and shared storage, and may legitimately
retain the physical overlap. De-overlapped semantic output may grow and is not
byte-identical. Existing `original_bytes_only` support is not an overlap-aware
relocating writer; this document does not promote it into one.

## Acceptance cases

These ten cases are implementation requirements, not a claim that production
UDL extraction, orchestration or native execution already passes them.

| ID | Case and required observation |
| --- | --- |
| OVL01 | Retain both entry-qualified decodes with evidence; coverage counts the shared byte once while local encoding sizes count each occurrence. Save/reopen keeps both. |
| OVL02 | Independently materialize A and B with their complete bytes and declared ports. Removing the sibling block's storage must not truncate the surviving encoding. |
| OVL03 | From A, preserve TEST effects and reach J with no STOSB write/index effect. Reject naive A8-AA-AA concatenation as a negative control. |
| OVL04 | From B, perform exactly one supported byte-store/index update and reach J; exercise relevant AL values, DF directions, address sizes and memory assumptions. |
| OVL05 | Remap direct, table and pointer entries to the right interpretation; no stale branch into the copied immediate. Unresolved computed entries remain unresolved. |
| OVL06 | Relocate blocks across short-branch limits, repair fixups and verify all continuations; include a live-flags consumer to detect clobbering glue. |
| OVL07 | Qualified semantic UIL has no physical-overlap requirement and yields the same admitted meaning through independent layouts/backings; unsupported semantics remain residual. |
| OVL08 | Shared-source mutation invalidates all dependent occurrences; a one-backing edit is distinct. Detect observable self-modification/code reads or preserve their explicit compatibility contract. |
| OVL09 | Distinguish exact-source pass-through from de-overlapped semantic output. Retain source/backing/layout provenance and reject unsupported ISA/ABI/container transformations. |
| OVL10 | Compare the composed output from both entries at the declared state/effect boundary, including failures and shared continuation. Synthetic checks and original-program runtime evidence remain separately reported. |

## Delivery and review boundary

The companion findings publish only metadata, numeric summaries and authored
requirements. The normalized example explains an instruction-set pattern; no
original game function, binary, asset, project or raw evidence payload is added.
Local documentation/arithmetic checks do not establish an overlap-aware compiler,
full LE conformance or whole-game recovery. Relevant seams include the source
backing and adapter work in PR #38 and orchestration in PR #42; this handoff
adds requirements without modifying those branches or adopting their pending APIs.
