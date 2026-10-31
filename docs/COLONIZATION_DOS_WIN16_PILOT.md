# Colonization DOS / Windows 3.1 parallel pilot

This pilot asks which findings from two editions of the same game help the
other analysis project, and which must remain local. It used an owned DOS 3.0
build and the original Windows 3.1 build recovered from the same GOG CD image.
Game files, saves, snapshots, screenshots, raw signatures and byte-retaining
projects remain private. This document contains authored findings and limits.

The concrete result is **useful structural transfer with target-local checks**.
The companion [type catalog feature](TYPE_CATALOGS.md) moves definitions,
authorship and declared origin without moving bindings or native confidence.
Windows execution was not performed; this is the first paired Win16 static
pilot, with original-engine DOS observations alongside it.

## Inputs, isolation and method

| Input | SHA-256 |
| --- | --- |
| DOS VICEROY.EXE | `a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3` |
| Windows COLONIZE.EXE, original 1995 NE build | `ae7d9149f056766a534fe8f0006c9512aac1e1004e9776ab3cca818e4833b650` |

Separate agents owned separate private database/runtime directories. They
exchanged hypotheses, then checked their own original bytes. The DOS lane
pinned its existing 0.23.0 native stack; the Windows lane used installed 0.25.0
native x86-16 decoding and NE metadata. The coordinator used this PR checkout
for the transfer trial. No shared installation or original executable changed.

DOS observations used original guest input with the built-in cheat menu and
colony free-production cycle. This is explicitly assisted investigation. The
native process was closed and reaped, cheats were disabled and the clean native
save was preserved. A physical input policy alone does not mean fair play.

Windows code was extracted into source-bound raw segment projections. A second
fresh build reproduced accepted decoder rows and source identities. Logical NE
segment indices below are not real-mode CS values or allocated selectors.

## What the two lanes established

| Question | DOS evidence | Windows evidence | Transfer decision |
| --- | --- | --- | --- |
| Colony stock record | Native stock writes plus static stride 202, owner +0x1A, 16 words at +0x9A | Independent selector/stock-loop decode confirms those same offsets and bound | Share a partial record definition; leave other fields opaque |
| Net commodity change | A[i] - B[i], with conditional mapped adjustment | Same arithmetic idiom in NE4:47DD | Share a semantic hypothesis; validate native code and ABI separately |
| Optional adjustment output | Two-byte near pointer | Four-byte selector:offset far pointer, checked as dword and loaded with LES | Do not copy the DOS prototype unchanged |
| Current colony | Near global pointer | Far pointer through DGROUP | Keep globals and bindings local |
| Calendar | Resident year/season logic with threshold 1600; earlier narrow native year check | Independent NE2:2A10..2A94 update idiom, plus an unqualified announcement call | Share the rule hypothesis, not a whole-function/runtime equivalence claim |
| Resource mapping | Twenty signed bytes retained in original-engine RAM | Twenty initialized bytes match exactly; signed access decoded | Accept the comparison window; complete Windows array bound remains unknown |
| Terrain parameters | 377 numeric comparisons match 29 native records | Upstream terrain/worker writers not qualified in this lane | Send a search constraint, not an accepted Windows layout |

The Windows stock addition is at logical NE4:95F2, source file offset 0x10BF2;
the clamped store is NE4:961B / file 0x10C1B. Its selector computes a 202-byte
record stride. NE fixup chains resolve the calendar fields to logical data
segment 19 and the net-helper arrays to segment 20. Raw instruction operands
and original bytes remain intact. Live selector allocations remain unknown.

The two clean Windows projects retain 8,673 and 4,246 instruction
interpretations, with 81 and 47 function candidates. Empty implemented basic
queues for these projections do not establish complete NE analysis, complete
function ownership or execution. Speculative overlapping starts were preserved
in exploratory projects and excluded from accepted focused projects.

## A stronger DOS production result

A same-invocation native calculation set a center-food staging byte to 2,
conditionally added 2, cleared the first production-cache word and added the
staged 4 into it. Two native code windows matched original bytes after normal
DOS relocation. A separate completed free cycle changed food from 2 to 4 while
year 1494, season 0 and turn counter 2 remained unchanged.

The matching value 4 in a terrain text row was not this calculation's established
cause. The native branch and staging write provide the stronger evidence.
The cache calculation also runs during colony redisplay: a cache watchpoint
alone does not establish a stock commit or a world turn.

All 13 numeric terrain fields matched across 29 observed 16-byte records:
377 comparisons. Numeric fields occupy offsets 1..4 and 6..14; three bytes
remain unknown. Twenty-one source rows map to 29 native rows with an eight-row
repetition. This establishes data equality/order, not the parser/file-read
provenance edge or the meaning of the repeated group.

## Transfer trial through real project APIs

The coordinator independently rechecked the original Windows stock instructions
and the compared mapping bytes. A complete 202-byte colony record in a clean
DOS native save matched the captured DOS RAM record. Only the owner/stock fields
and stride have independent Windows code support; the whole record's field
meanings remain unqualified.

The trial then:

1. Cloned the source DOS and accepted Windows projects without modifying either.
2. Defined a signed 16-word stock layout, a partial 202-byte stock record and a
   20-byte signed comparison-window layout in the DOS project.
3. Exported/imported the three definitions using this PR's public Python API.
   Immediately afterward the receiving project had **zero imported bindings,
   zero attachments and unchanged instruction/annotation counts and bytes**.
4. Explicitly attached and typed the same preserved save in both projects at
   its locally checked file location. Typed field values agreed after reopening.
   This tests data interpretation, not Windows save loading or game execution.
5. Explicitly bound a Windows file comparison window. Twenty bytes agreed;
   the view's length does not prove a complete native Windows array bound.
6. Rejected a conflicting definition and retained source authorship/origin.
7. Imported a private DOS helper signature and compared it with the independently
   found Windows helper. There was **no exact native-body match**, despite the
   shared arithmetic. No Windows function identity was assigned from that match.

An origin is a declared lineage assertion, not authentication or transferred
verification. The new commands preserve that distinction and refuse fixed
pointer segments. Fields and addresses need a receiving-project acceptance
check. See [type catalogs](TYPE_CATALOGS.md) for the implemented contract.

## Frictions encountered and concrete resolutions

| Friction | Resolution in this PR or next bounded step |
| --- | --- |
| Types had no portable definition exchange, although exact function signatures already did | Implemented bounded `export-types` / `import-types`, preserved authors/origin, conflicts atomic, bindings excluded |
| A layout match tempted reuse of pointer widths and globals | Confirm target code first; fixed segments refused; local bindings and explicit near/far ABI review |
| 20 scratch resources were confused with 16 warehouse stocks | Keep distinct definitions and observed bounds; do not infer the Windows 20-entry bound from byte equality |
| Source CSV fields are not contiguous native records, and some rows repeat | Preserve row order, unknown holes and exact comparisons; trace parser/table-loading provenance separately |
| A matching number looked like a production cause | Prefer writer/staging/cache witnesses from one invocation; separate redisplay from committed stock effects |
| NE identification exposes only the small DOS stub as a standard loaded view | Next: a genuine NE static view with module/segment identity, file ranges and declared bounds; retain a clear runtime boundary |
| Fixup placeholders hide useful static calls and data identities | Next: attach bounded symbolic internal targets and import module/ordinal evidence while retaining raw operands and unknown live selectors |
| Sparse/interior address queries produced empty or later rows; speculative seeds overlapped | Check returned boundaries; keep accepted entry paths separate. A context-aware exact/neighbor query would make this easier |
| Installed tool versions differed from checkout documentation | Pin exact CLI/Python/backend per run and check actual capabilities; do not mix release claims |
| Native emulator states depended on changing host save files | Preserve native saves; qualify checkpoint resources/ownership separately from project persistence |
| API-valid Unicode catalogs exceeded the CLI's earlier ASCII-escaped byte count | Independent review reproduced it; file export now uses the same canonical UTF-8 encoder, including the exact 4 MiB boundary |
| Generic address formatting could rewrite numeric enum members in a metadata catalog | Preserve export catalog values exactly in the JSON protocol; a round-trip regression covers address-like member names |
| There is no live Win16 result | Prepare and qualify a compatible runtime separately; then test clean save load, one stock change and the calendar witness before expanding scope |

A later correspondence ledger could retain each candidate relation with source
and target identities, local evidence, accepted/rejected status and limits. This
PR implements the small definition-transfer seam, not automatic semantic
matching, label propagation, NE native loading or a Win16 debugger.

## Verification and remaining work

Authored fixture tests exercise two-project transfer, malformed/dependency and
conflict atomicity, fixed-pointer refusal, byte/binding exclusion, restart,
child-version isolation, stale-origin handling and CLI file protection. Unicode
and exact-size boundary reproductions are retained as regressions. Public test
fixtures contain no game code or data.

The next useful analysis question is the Windows upstream producer corresponding
to the DOS center-food staging/cache writer. Before a runtime parity claim, the
Windows lane also needs a compatible Win16 environment and actual effects. Save
compatibility remains a claim in the owned build's README until tested there;
cheat-enabled DOS saves are explicitly excluded by that build's documentation.

A successful partial type transfer is useful progress. It does not establish
whole-game recovery, cross-platform runtime parity or a complete colony schema.
