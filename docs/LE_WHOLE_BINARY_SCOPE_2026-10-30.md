# LE whole-binary findings and implementation handoff

Investigation date: 2026-10-30. Evidence tool: fDisBull 0.26.0, source
`8ba24d62b5010d3a6a5d604524aad72e2e047b77`, isolated Python 3.13.5.
Publication base: `f783f2aa43bae779392fd3f6558c980c5e4884b5`.

This is a sanitized findings and requirements handoff following
[the initial DOS format study](DOS_FORMAT_FINDINGS_2026-10-29.md) and PR #25.
It does not implement a new loader, optimizer or executable writer. Historical
investigation results below were recovered from their retained reports and
receipts, not rerun or relabeled as tests of the publication base.

The instruction-overlap finding has a separate
[UDL / UIL / UDC reconstruction contract](UDL_OVERLAP_RECONSTRUCTION.md).
That contract is central: independently executable UDL blocks need complete
local encodings, UIL keeps recovered meaning rather than physical overlap,
and UDC orchestration must preserve both entry paths when laying out output.

## Evidence identity and limits

The selected Syndicate MAIN.EXE is 518,713 bytes, SHA-256
`bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078`.
It was recovered from version 1 of the preserved analysis project. Originals,
raw disassembly, databases, native states and the private evidence archive are
not part of this PR.

The retained archive is `Syndicate_LE_Whole_Binary_Scope_2026-10-30.zip`,
7,800,765 bytes, SHA-256
`059150e40157dda42fe0698ef1ab5fdbcc9907f98180cd1e223a06985542503d`.
These identities identify evidence; they do not supply missing executable data.
Its readable report and named receipts support the following bounded findings.
The expansion and launcher did not receive this whole-file pass. No original
DOS/4GW or game execution was performed for the recorded static investigation.

## Complete physical accounting, not complete code recovery

Nineteen contiguous, disjoint half-open ranges account for every physical byte.
The final page ends at EOF. There is no unexplained nonzero region outside the
identified structures and payloads; payload contents are not thereby understood.

| File start | End, exclusive | Bytes | Classification |
| --- | --- | ---: | --- |
| `0x000000` | `0x00001C` | 28 | MZ fixed fields |
| `0x00001C` | `0x000040` | 36 | MZ extension/reserved fields and LE pointer |
| `0x000040` | `0x000058` | 24 | Six MZ relocation records |
| `0x000058` | `0x000060` | 8 | Zero header padding |
| `0x000060` | `0x0028B2` | 10,322 | Mixed DOS bootstrap code/data |
| `0x0028B2` | `0x0028B8` | 6 | Zero gap before LE |
| `0x0028B8` | `0x00297C` | 196 | Full LE header, including reserved suffix |
| `0x00297C` | `0x0029DC` | 96 | Four object records |
| `0x0029DC` | `0x002B80` | 420 | 105 page-map entries |
| `0x002B80` | `0x002B88` | 8 | Resident name, ordinal and terminator |
| `0x002B88` | `0x002B89` | 1 | Empty entry-table terminator |
| `0x002B89` | `0x002D31` | 424 | 106 fixup-page offsets |
| `0x002D31` | `0x015A71` | 77,120 | Fixup-record stream |
| `0x015A71` | `0x015A72` | 1 | Empty import-procedure sentinel |
| `0x015A72` | `0x015C00` | 398 | Explicitly unassigned zero gap |
| `0x015C00` | `0x0559F4` | 261,620 | Object 1 payload |
| `0x0559F4` | `0x055C00` | 524 | Object 1 final physical-page slack |
| `0x055C00` | `0x062C00` | 53,248 | Object 2 payload |
| `0x062C00` | `0x07EA39` | 114,233 | Object 4 payload through EOF |

The 398-byte gap reaches the next 512-byte boundary, supporting an alignment
hypothesis, not deletion safety. The 524-byte suffix is outside object 1's exact
virtual size but inside its final physical page. Whether a native loader copies
or exposes it in a rounded allocation remains unknown. Neither region is BSS.

All 48 grouped fixed-header fields were inventoried. The final 20 reserved bytes
are zero; no VxD-specific meaning is assigned. The resident name is `main` with
ordinal zero. Independent parsing establishes an empty entry table and inactive
resources, directives, imports, nonresident names, debug data, iterated data and
page checksums for this sample. Generic `exports=[]` alone would not establish
that. Empty tables can share positions; zero checksum fields mean unsupplied
checksums, not successful checksum verification.

The declared loader aggregate is 78,070 bytes and contains the 77,545-byte fixup
aggregate. Their 525-byte difference is the objects, page map, resident names
and empty entry table. Keep both declarations but count disjoint leaf regions;
adding the aggregate sizes would double-count fixups. The historical producer's
inclusive convention remains unexplained, not established corruption.

## File-backed bytes, zero fill and relocation accounting

| Object | Declared virtual bytes | Mapped file bytes | Virtual zero fill | Physical page bytes |
| --- | ---: | ---: | ---: | ---: |
| 1, read/execute | 261,620 | 261,620 | 0 | 262,144 |
| 2, read/write | 81,504 | 53,248 | 28,256 | 53,248 |
| 3, read/write | 3,072 | 0 | 3,072 | 0 |
| 4, read/write | 116,274 | 114,233 | 2,041 | 114,233 |
| Total | 462,470 | 429,101 | 33,369 | 429,625 |

All 105 page entries are enumerated and map to identically numbered physical
pages. The last physical page is 3,641 bytes. No aliases, holes or unowned page
entries were found in this map. Preferred object addresses are not observed
runtime selectors or placements; object permissions do not classify all payload
bytes as code or data.

The independent parser matched every relocated byte of all four objects and
all 10,060 fixup records against the installed loader, with zero mismatches.
There are 10,055 unique four-byte writes: five cross-page writes have consistent
records on both adjoining pages, including signed negative source offsets.
Preserve both encoded records and apply each unique write once. This relocation
record overlap is distinct from the instruction overlap discussed below.

All observed fixups are internal offset32. Of the target fields, 6,710 use
16-bit offsets and 3,350 use 32-bit offsets. Three records resolve exactly to
object 4's exclusive end; boundary pointers are not missing data or automatic
code-entry seeds. Standalone inspection previews only 10,000 records, so full
record claims need complete loader metadata or project pagination.

## Bootstrap and discovery status

The statically traced MZ startup searches for external `dos4gw.exe` and
`dos4g.exe`, using `DOS4GPATH` and `PATH`. It prepares the original filename and
command tail, invokes DOS overlay loading with `AX=4B03h`, and transfers through
a header-derived stack/entry handoff. The actual selected extender and its
subsequent execution remain unobserved. The separate MZ project has 1,508 stored
instructions and 50 candidate functions; it is not complete bootstrap recovery.

| LE discovery measure | Recorded result |
| --- | ---: |
| Stored instructions | 22,910, increased from 5,000 |
| Candidate functions | 384, increased from 171 |
| Cross-references | 27,027 |
| Unique instruction-covered bytes | 71,411 |
| Sum of instruction sizes | 71,412 |
| Basic discovery work remaining | 0 |
| Derived jobs done / partial | 368 / 16 |
| Indirect calls/jumps without resolved control targets | 60 |
| New control edges admitted by the bounded derived pass | 0 |
| Legacy snapshot-only edges withdrawn | 7 |

The 71,411-byte union is 27.3% of object 1's extent, not 27.3% of known actual
code. A drained basic queue is not whole-binary semantic coverage or runtime
reachability. Preserve partial jobs, unresolved transfers and rejected targets.

### Instruction overlap must remain a valid interpretation

One byte is an immediate operand on a two-byte TEST path and the opcode of a
one-byte STOSB on a separate entry path. Both paths reach the same next boundary.
Incoming decoded control-flow edges support both interpretations. This is not
merely a decoder disagreement, although native execution of these paths was not
observed in this investigation. The private overlap receipt retains the source
addresses, bytes and incoming edges; the public companion uses symbolic entries.

Do not force one-instruction-per-byte ownership or discard the second entry.
Count physical byte coverage once while retaining both decoded instructions.
For independent UDL blocks, duplicate the shared byte into each complete local
encoding, retain common source provenance, and let UDC orchestration fix the
layout and control-flow consequences. UIL must not inherit a physical-overlap
requirement when the recovered meaning does not depend on that layout.

### Concrete remaining indirect-transfer blockers

**Switch:** a relocation-backed 17-entry table contains 11 distinct initial
targets; ten target starts are undecoded. Its owner finished without budget
exhaustion, but comparison of a 16-bit memory value followed by reload through
AX after clearing EAX loses the required value identity and partial-register
relationship. The refusal is an unbounded/nondominating index, not a CS-override
or budget problem. Qualify compare/reload identity, intervening writes and the
unsigned bound before admitting edges. Candidate decoding can be separate from
claiming proven dispatch reachability.

**Callbacks:** three writable slots initially target a decoded RET. A masked
symbolic stack-store expression is not recognized by the simpler stack-shape
alias exclusion, leaving conservative possible modification. This diagnosis
comes from inspected normalized IR and source, not a witnessed slot overwrite.
Retain possible absolute/unknown stores and qualify stack separation; initial
pointer values alone do not justify restoring the seven withdrawn edges.
A separate larger owner exhausted 25,000 flow steps with six pending items;
that budget issue must not be confused with the stable owners' precision gaps.

**Additional candidates:** nine distinct object-2-to-object-1 pointer targets
include six undecoded starts; none was a function-candidate entry after cleanup.
Record them as leads until use and write assumptions are qualified.

## Reproduced loader-validation gaps

Eight authored-fixture mutations were accepted by both loading and inspection
without a warning in 0.26.0: out-of-file resident names, entry table, resources,
directives, debug data, nonresident names, loader aggregate and page checksums.
The retained probe report records these actual historical results. This does
not make the selected game malformed and is not a new reproduction on main.

Successful object/fixup mapping therefore must not be advertised as complete
physical-container validation. Parse and validate active optional structures,
or explicitly report them as unsupported/unvalidated. Distinguish inactive
zero-count tables and legal coincident positions from invalid active extents.

## Implementation acceptance criteria

These are prospective requirements, not newly passing production tests.

| ID | Required result |
| --- | --- |
| LE01 | Physical interval ledger partitions the entire file into structures, payloads, gaps/slack and unresolved regions; nested aggregates are not summed twice. |
| LE02 | Active optional tables have checked bases, lengths, termination and overflow, or explicit unsupported/unvalidated status. Reproduce all eight negative fixtures and valid empty/coincident-table controls. |
| LE03 | Report physical page storage, clipped mapped bytes, virtual zero fill, reserved header coverage and EOF remainder separately. |
| LE04 | Preserve all fixup records, unique writes, cross-page duplicate provenance and legal boundary pointers; conflicting writes still reject. |
| LE05 | Preserve entry-qualified overlapping decodes and union-based coverage; persist/reopen both paths and their evidence. |
| LE06 | Separate basic queues, derived partial work, candidate entries and unresolved transfers; a stable flag alone cannot claim full recovery. |
| LE07 | Qualify the compare/reload partial-register switch and callback alias cases locally; keep counterexamples and candidate-versus-proven distinctions. |

For executable reconstruction also implement the ten OVL acceptance cases in
[the overlap contract](UDL_OVERLAP_RECONSTRUCTION.md#acceptance-cases).
Prefer these discriminating cases to repeatedly increasing a global budget.

## Evidence locators and references

The private archive members are durable locators for the study, not public
payloads: `independent/le-physical-scope.json`, `independent-comparison.json`,
`independent/stored-analysis-coverage.json`, `continuation/instruction-overlap.json`,
`loader-audit/bootstrap-findings.md`, `loader-audit/fixture-probe-results.json`,
and `loader-audit/indirect-scope-diagnostic.md` with its companion JSON.
No fresh game run, loader reconstruction or native output is claimed by this PR.

Primary format sources pinned by the original study:

- [Open Watcom LE/LX declarations](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/watcom/h/exeflat.h).
- [LE page writer](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/wl/c/loadflat.c).
- [Relocation emitter](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/wl/c/obj2supp.c) and [fixup reader](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/exedump/c/wdfix.c).
- [IBM Revision 11 specification](https://archive.org/stream/IBMOS2Warp4ToolkitDocuments2/32-bit%20Linear%20eXecutable%20Module%20Format%20%28LX%29%20Specification), whose debug-offset correction is retained by the study: file-relative, not the older header-relative wording. Shared LX rules do not replace LE page semantics.

Related implementation work: PR #38's source backings/adapters, #39's shell
milestone and #42's target orchestration. PR #41 describes adjacent static
analysis friction. None of those reports is substituted for this study's
qualification, and this handoff does not modify their branches or claim their
implementation supports overlap reconstruction.
