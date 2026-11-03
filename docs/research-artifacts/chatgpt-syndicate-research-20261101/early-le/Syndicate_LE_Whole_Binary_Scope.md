# Syndicate LE: whole-binary scope and continuation pack

Date: 30 October 2026. Tool: installed fDisBull 0.26.0, isolated Python 3.13.5.

## Executive summary

**The selected 518,713-byte MAIN.EXE now has complete physical byte accounting.** Nineteen disjoint, contiguous ranges cover the whole file. There is no unexplained nonzero region outside the identified structures and payloads, and the last enumerated page ends exactly at EOF. The 398-byte inter-section zero gap is explicitly retained as structurally unassigned; alignment is a supported hypothesis, not a deletion rule.

The independent reconstruction agrees with the installed loader on all four preferred-address objects and every one of the 10,060 supported relocation records. The five duplicated cross-page records correspond to five already-counted writes, yielding 10,055 unique four-byte writes. The original retained project's bytes agree as well.

The previously unexamined DOS bootstrap has a traced startup role: it searches for an external DOS4G/W executable, forwards MAIN.EXE's pathname and the command tail, loads the external executable as an overlay, and transfers into its header-derived entry. The external loader's actual execution and subsequent LE consumption are not observed in this static pass.

**Instruction and semantic recovery remain partial.** Resuming the existing project increased stored instructions from 5,000 to 22,910. Its basic discovery queues drained. A separate bounded derived pass produced 368 done jobs and 16 partial jobs, admitted no new control edges, and withdrew seven legacy snapshot-only edges. All 60 stored indirect calls/jumps remain without stored resolved targets. These limits are retained rather than hidden by the successful container accounting.

## Target and provenance

| Item | Identity |
| --- | --- |
| Selected file | Syndicate main MAIN.EXE |
| Bytes | 518,713 |
| SHA-256 | bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078 |
| Recovered source | Version 1 binary_info.source_bytes from the archived Syndicate project |
| Prior pack | DOS_LE_Analysis_and_Knowledge_Pack.zip, 29 October 2026 |
| Current tool release | fDisBull 0.26.0 |
| Release source commit | 8ba24d62b5010d3a6a5d604524aad72e2e047b77 |
| Mapped version | Original, version 1; preserved source and mapped bytes |

The existing source-preserving database supplied the exact original executable, so the 60 MB installer did not need to be downloaded or executed. The restored source identity matched the previous experiment once; the original archived project was preserved and a separate working copy was continued. New object hashes measure independently reconstructed mapped images, not repeated checks of the original file.

External primary sources supplied format grammar. Game-specific extents, records and control-flow findings derive from this retained executable and its stored instruction evidence. The independent parser imports no fDisBull module and did not reuse the earlier independent reader. A separate reviewer checked the new partition and selected original-byte intervals.

This report concerns this MAIN.EXE edition. The expansion and launcher retain their earlier loading-survey status; this is not a fresh whole-file pass over those other executables.

## Architecture: complete physical file map

All intervals below are half-open: the end byte belongs to the following region.

| File start | End, exclusive | Bytes | Classification |
| --- | --- | --- | --- |
| 0x000000 | 0x00001C | 28 | MZ fixed DOS fields |
| 0x00001C | 0x000040 | 36 | MZ extension/reserved fields and LE pointer |
| 0x000040 | 0x000058 | 24 | MZ segment relocation records |
| 0x000058 | 0x000060 | 8 | MZ paragraph padding |
| 0x000060 | 0x0028B2 | 10,322 | DOS bootstrap code and data; mixed contents |
| 0x0028B2 | 0x0028B8 | 6 | Zero-filled MZ-to-LE gap |
| 0x0028B8 | 0x00297C | 196 | LE fixed header, including 20 reserved bytes |
| 0x00297C | 0x0029DC | 96 | Four LE object records |
| 0x0029DC | 0x002B80 | 420 | LE object page map |
| 0x002B80 | 0x002B88 | 8 | Resident name and zero terminator |
| 0x002B88 | 0x002B89 | 1 | Empty entry-table terminator |
| 0x002B89 | 0x002D31 | 424 | Fixup page offsets and final sentinel |
| 0x002D31 | 0x015A71 | 77,120 | Internal offset32 fixup records |
| 0x015A71 | 0x015A72 | 1 | Empty import-procedure table zero sentinel |
| 0x015A72 | 0x015C00 | 398 | Unassigned inter-section gap |
| 0x015C00 | 0x0559F4 | 261,620 | Object 1 file-backed payload |
| 0x0559F4 | 0x055C00 | 524 | Object 1 final-page slack |
| 0x055C00 | 0x062C00 | 53,248 | Object 2 file-backed payload |
| 0x062C00 | 0x07EA39 | 114,233 | Object 4 file-backed payload |

### What the previously hidden bytes are

The physical page payload is **429,625 bytes**: 104 full 4,096-byte pages and one final 3,641-byte page. Only **429,101 bytes** fall inside the exact declared object extents. The difference is the **524-byte all-zero suffix of object 1's final physical page**.

That suffix is outside object 1's exact virtual size. It could still be copied or accessible in a rounded native allocation; this static map does not establish original-loader accessibility or permission to remove it. Physical page slack is distinct from virtual BSS.

There are also **398 zero bytes** between the parsed metadata end, 0x15A72, and page storage at 0x15C00. The gap exactly reaches the next 512-byte boundary, supporting a sector-alignment explanation. Its producer intent and deletion safety remain untested. The six bytes between the MZ declared extent and the LE header, and the eight final MZ-header bytes, are also zero and remain explicitly accounted for.

No extra EOF suffix exists after object 4's final stored page. This closes a physical-tail question; it does not interpret all data inside the payload objects.

### LE header and optional structures

The LE header begins at file offset **0x28B8**. It declares little-endian byte/word order, level zero, CPU type 2 (386), 4,096-byte pages and four objects. Header table offsets must be interpreted with their documented bases; enumerated data is file-relative. All 48 grouped fixed-header fields, including the final 20 reserved bytes, are enumerated in the accompanying CSV. The 20 reserved bytes are all zero and receive no speculative VxD meaning.

The resident-name table contains **main, ordinal 0**, followed by its terminator. The entry table is a single zero-count terminator, so the source itself establishes that this sample has no exported entry bundles. Import-module count is zero, and the import-procedure table is a single zero sentinel. These claims come from parsing the bytes, not from the generic inspector's empty lists.

Resource and module-directive counts are zero. Nonresident-name and debug offset/size fields, iterated-data pointer and per-page checksum pointer are inactive. Empty resource/name positions can coincide; a nonzero pointer with a zero count must not fabricate a nonempty region. An empty LE resource index does not rule out application-managed assets inside ordinary objects or external files. Zero checksum fields are recorded as unsupplied checksums, not as successful checksum verification.

### Overlapping aggregate declarations

The declared loader aggregate is **[0x297C, 0x15A72)**, 78,070 bytes. The declared fixup aggregate is **[0x2B89, 0x15A72)**, 77,545 bytes. Thus this file's loader aggregate contains the fixup aggregate. Adding them as disjoint regions would double-count the fixups.

The 525-byte difference consists exactly of the object records, page map, resident-name table and entry-table terminator. The examined modern Open Watcom writer calculates loader size before fixups, so this file's inclusive convention is an observed producer/version question, not something established by that writer. Both declared ranges fit the source and are preserved without treating the overlap as corruption. The nonoverlapping leaf partition above remains the accounting authority.

## File-to-memory map

| Object | Preferred range, end exclusive | Permissions | Physical page bytes | Mapped source bytes | Virtual zero fill |
| --- | --- | --- | --- | --- | --- |
| 1 | 0x10000..0x4FDF4 | r-x | 262,144 | 261,620 | 0 |
| 2 | 0x50000..0x63E60 | rw- | 53,248 | 53,248 | 28,256 |
| 3 | 0x70000..0x70C00 | rw- | 0 | 0 | 3,072 |
| 4 | 0x80000..0x9C632 | rw- | 114,233 | 114,233 | 2,041 |

The LE objects total **462,470 virtual bytes**: 429,101 copied bytes plus **33,369 bytes of virtual zero fill**. Object 3 is entirely zero fill and consumes no physical payload pages. Object 2's declared initial stack address is its exclusive end, **0x63E60**. The main entry is object 1 base 0x10000 plus EIP 0x2D85C, yielding **0x3D85C**.

All 105 logical page entries are enumerated (flag zero) and map to the identically numbered physical page. There are no page aliases, unowned entries or holes in this observed page map. The physical source of page k is 0x15C00 + (k - 1) * 4096. The last-page length applies to the final physical page.

Object permissions describe the LE declarations: object 1 is executable and also contains embedded tables; objects 2, 3 and 4 are writable data regions. Their individual gameplay structures are not recovered by these permissions. Preferred addresses and virtual gaps are not observed DOS/4GW selectors, actual load positions, or the whole DOS-process memory map.

## Relocations: complete record accounting

The 106-entry fixup page table occupies 424 bytes. Its final sentinel bounds exactly **77,120 record bytes**, all of which were consumed. The remaining one-byte import-procedure sentinel brings the full fixup aggregate to 77,545 bytes.

- **10,060 encoded records** produce **10,055 unique four-byte writes**.
- All observed source kinds are offset32, source byte 0x07.
- Target flags 0x00 occur 6,710 times and use 16-bit target offsets.
- Target flags 0x10 occur 3,350 times and use 32-bit target offsets.
- Both target-offset encodings still produce a four-byte relocated value.
- Every observed object ordinal uses one byte.
- Signed page source offsets range from -3 to 4,095.
- Distinct write locations do not overlap; duplicate writes agree.

The five duplicated writes are at preferred addresses **0x10FFF, 0x20FFD, 0x36FFE, 0x41FFD and 0x4AFFF**. Each pair occurs in adjacent page lists; the second record uses a negative offset to refer back into the preceding page. For example, offsets 4095 and -1 both describe the write at 0x10FFF, whose relocated value is 0x5E555. Both records remain evidence, while the write is applied once.

Three records target object 4's exclusive end, **0x9C632**, from source addresses 0x16EF8, 0x24FC1 and 0x4F90A. These are one-past-object values, not evidence of a missing extra object byte. Entry points still require actual file-backed executable bytes; a valid end pointer does not qualify as an entry point.

The independent and fDisBull records were compared field by field for record location, page, source object/address/offset, target object/offset/flags and relocated value. There were **zero mismatches**. All four reconstructed relocated object hashes also match, and the preserved project's region bytes equal the current v0.26 loader's bytes. This verifies the selected static transformation; it does not qualify native loader execution.

## DOS bootstrap: the concrete handoff

The MZ header is 96 bytes and the file-backed load image is 10,322 bytes, ending at 0x28B2. Six segment relocations and the minimal-allocation arithmetic are accounted for separately from the LE image. The MZ minimum static allocation is 12,480 bytes; virtual allocation is not extra file storage.

The recovered entry path is:

1. C runtime startup reaches the launcher main routine at static **1000:0055**.
2. It searches for **dos4gw.exe**, then **dos4g.exe**, using file probes and the **DOS4GPATH** and **PATH** environment values. A later exec wrapper also provides a fallback path search.
3. It builds arguments containing the chosen loader pathname, the original program pathname and the raw PSP command tail. The DOS >=3 startup branch obtains the original pathname from the environment block.
4. The exec implementation reads the selected external file's MZ header and prepares a transfer area near the available-memory end.
5. At source **1000:1CD4**, it sets **AX=4B03h** and far-jumps into a copied thunk. That thunk starts with PUSH CS / POP DS / INT 21h, performing the DOS overlay load.
6. On success, the thunk installs the external MZ's header-derived SS:SP and transfers to its adjusted CS:IP with RETF at source **1000:1B29**.

The copied thunk's source-template addresses are recorded; its actual relocated runtime address is unobserved. The selected loader receives MAIN.EXE's pathname so it can handle the protected-mode payload. An empty LE import table therefore does not make this startup path self-contained.

The bootstrap also contains a generic COM alternative and diagnostic exits. The ordinary returned failure path requests exit code 1; the thunk's load-error path requests FFh. These are static requested codes, not observed guest-exit events.

This role was established with one 2,000-attempt MZ analysis (1,508 decoded instructions, 50 function candidates, 1,785 xrefs, 65 pending work items), followed by 572 explicitly selected decoder records across ten windows. The windows did not mutate the project worklist. The remaining bootstrap code is preserved as incomplete; the entry-to-external-loader handoff is the supported causal conclusion.

## Analysis coverage: what the byte map does and does not recover

The existing 5,000-instruction LE project was resumed rather than imported and analyzed from scratch. One 20,000-attempt continuation added **17,910 instructions**, processed 474 data investigations, and drained the current basic discovery queues in approximately **5.473 seconds**.

A separate derived pass processed **384 jobs** in approximately **287.383 seconds**. It produced **368 done and 16 partial jobs**, admitted **zero new edges**, and withdrew **seven legacy snapshot-only control edges**. The current function count is **384 candidates**: 383 direct-call candidates and the LE entry. The temporary pre-derived count was 387 because three weaker indirect-call candidates were subsequently withdrawn. Stored instruction bytes were retained.

All **60 indirect sites** remain without stored resolved control-target edges: 42 jumps and 18 calls. Return destinations are a separate caller-dependent question; the 476 stored return instructions are not counted among those 60 sites. Fifty-nine of the done derived results still contain graph unknowns. A done job means a fixed point of that implemented pass, not complete function recovery.

The project was reopened in a separate status command without reanalysis. The saved native queues remained drained, while overall stability remained false because the 16 partial derived jobs persist.

### Exact stored byte unions

These figures measure stored classifications, not ground-truth code/data identity or runtime coverage. Code and data observations can overlap.

| Object | Declared bytes | Instruction-byte union | Data-item union | Overlap | Neither tagged |
| --- | --- | --- | --- | --- | --- |
| object_1 | 261,620 | 71,411 | 98 | 20 | 190,131 |
| object_2 | 81,504 | 0 | 2,201 | 0 | 79,303 |
| object_3 | 3,072 | 0 | 4 | 0 | 3,068 |
| object_4 | 116,274 | 0 | 80 | 0 | 116,194 |

The 71,411 unique instruction bytes occupy about **27.30% of object 1's declared 261,620-byte extent**. That extent also contains embedded data, so this is not a percentage of all real instructions or game behavior recovered. Across all four objects, 388,696 bytes have neither an instruction nor a data-item tag. Their physical and virtual ownership is known even where their program meaning is not.

### A real overlapping instruction byte

At **0x3D1E9**, bytes A8 AA decode as **TEST AL,AAh**. A different direct branch enters **0x3D1EA**, where AA decodes as **STOSB**. The surrounding code tests bytes in AX around a word-copy loop: one path reaches the single-byte store, while the other consumes its opcode as the TEST immediate and reaches the common epilogue. The TEST also changes flags; no unqualified no-op equivalence is asserted.

Both starts have stored incoming control-flow evidence. Their shared byte explains why nominal instruction lengths sum to **71,412** while their union is **71,411**. Both interpretations are preserved. A byte-range ledger must use unions and must not confuse valid instruction overlap with conflicting relocation writes.

There are also 20 bytes carrying both instruction and data tags, including the three decoded callback targets below. These are overlapping observations, not an automatic command to delete one interpretation.

### Relocation-backed callback candidates

Object 2 contains 13 data-to-code fixup records targeting nine distinct addresses:

| Preferred target | Decoded instruction start | Current function candidate |
| --- | --- | --- |
| 0x3d640 | yes | no |
| 0x3f37c | no | no |
| 0x3f89d | no | no |
| 0x3f974 | no | no |
| 0x404ef | yes | no |
| 0x406f9 | no | no |
| 0x4073e | no | no |
| 0x40c18 | yes | no |
| 0x40e6c | no | no |

The six undecoded targets do not fall inside another stored instruction. A relocation establishes the initial pointer value; it does not establish which call consumes it or whether the writable slot stays unchanged. These addresses are concrete follow-up targets, retained without silently promoting them into observed functions.

## Implementation findings

The shipped loader's selected mapping is correct for this sample, but its whole-container inspection coverage is narrower than its successful load might suggest.

A fresh in-memory reproduction using a 4,500-byte authored fixture changed each of eight optional pointers/extents to 0xFFFFFFF0 (and supplied nonzero counts or lengths where applicable). Both load_le and inspect_binary accepted all variants without warnings:

| Unvalidated structure | Modified header location |
| --- | --- |
| Resident names | +0x58 |
| Entry table | +0x5C |
| Resource table with count 1 | +0x50 / +0x54 |
| Module-directive table with count 1 | +0x60 / +0x64 |
| Debug data with length 16 | +0x98 / +0x9C |
| Nonresident names with length 16 | +0x88 / +0x8C |
| Declared loader extent | +0x38 |
| Per-page checksums | +0x7C |

The independent reviewer ran the probe, and the integration owner reran the self-contained reproducer against the installed package. This is a verified inspection-coverage gap, not evidence that the supplied MAIN.EXE is malformed. This file's relevant empty tables and inactive features were checked independently.

Other implementation boundaries:

- The final 20 fixed-header bytes are retained but not named in the current loader metadata.
- Physical page suffixes outside an object's exact capacity are retained in the original source but omitted from mapped-byte accounting. Exposing physical_size, mapped_size and slack separately would make the 524-byte distinction visible.
- Standalone inspection previews 10,000 of this file's 10,060 relocations. Whole-record claims require the full loader metadata or complete project pagination.
- Generic exports=[] does not certify an empty LE entry table, because the inspector does not parse it. This pass independently established that this sample's entry table is empty.
- The supported reader remains a qualified LE subset. LX, active import handling, resource/directive semantics, additional fixup kinds and unsupported page encodings are not made complete by this one sample.

### Concrete implementation acceptance criteria

1. Add a physical interval ledger separate from object mapping. Every source byte must be a parsed structure, payload, explicit gap/slack or unresolved interval; aggregates must not be double-counted.
2. For optional tables, either parse and validate their active extents or report them as unvalidated/unsupported. Successful object mapping should not imply full-container validation.
3. Expose reserved-header coverage, physical page size, clipped object bytes, virtual zero fill and EOF remainder as distinct quantities.
4. Preserve record count versus unique-write count, duplicate provenance and one-past pointers. Keep unsupported relocation forms explicit.
5. Use union-based instruction coverage and retain branch-supported overlapping decodes. Keep inferred data tags distinct from exclusive ownership claims.
6. Report basic queue stability, derived job completeness and unresolved transfers separately. A single stable boolean must not stand in for whole-binary recovery.
7. Improve targeted switch-index recovery with partial-register semantics and memory-value identity across compare/reload sequences. Keep writable callback targets conditional on qualified write/alias evidence.

The independent scripts in this pack implement selected-profile investigation and coverage export. They are not installed production-loader changes and should not be promoted to generic LE conformance or adversarial-input qualification without the corresponding implementation and tests.

## Research references and decisions

The structural parser uses Open Watcom's definitions, page writer and fixup reader at commit **5474be3542af05eee71be05fafc31bbe11f1415b**:

- [exeflat.h](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/watcom/h/exeflat.h)
- [loadflat.c](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/wl/c/loadflat.c)
- [obj2supp.c](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/wl/c/obj2supp.c)
- [wdfix.c](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/exedump/c/wdfix.c)

The separate reference review also consulted a newer pinned Watcom revision and the DOS/32A consumer; their exact references and scope are in spec-references/LE_Format_References.md. A different implementation is corroboration for format mechanics, not proof of Syndicate's original runtime.

[IBM Revision 11, June 14, 2001](https://archive.org/stream/IBMOS2Warp4ToolkitDocuments2/32-bit%20Linear%20eXecutable%20Module%20Format%20%28LX%29%20Specification) explicitly corrects older documentation: the debug-data offset is **file-relative**. The 1992 header-relative wording is a historical erratum, not an established alternate dialect. Shared LX fields are used cautiously; LE-specific page layout and final-page semantics come from LE-capable definitions and producer code.

Decisions made during this pass:

- Restore prior source and analysis before gathering new evidence.
- Keep all original bytes, partial worklists, failed assumptions and derived limits.
- Keep physical bytes, preferred object memory, relocated values, instruction tags and runtime observations as separate identities.
- Use one independent structural reconstruction and one direct comparison across all supported records; avoid redundant original-file hashing or repeated initial analysis.
- Stop broad derived retries after the result identified specific blockers. The next useful work is local index/alias reasoning and consumer evidence.
- Leave zero gaps and slack intact; this investigation provides no media or executable-size transformation.

## Tasks completed, questions retained, and next work

Completed: exact input recovery; full physical partition; complete header/page/object/fixup census for the observed profile; independent mapped-byte and record comparison; bootstrap handoff tracing; continuation of the saved LE project; bounded derived analysis; optional-table gap reproduction; exact stored byte-union export; persistent projects and reproducible analysis scripts.

Remaining questions are concrete:

- Which original DOS4G/W executable is selected under the actual environment, and how does it place these objects and selectors?
- Does the native loader copy or expose physical page slack beyond an exact object extent?
- What historical producer convention explains this file's inclusive loader_size aggregate?
- Which indirect dispatch targets become provable after recovering the compared memory value through a partial-register reload?
- Which writable callback slots can be qualified against actual stores, stack separation or a native observation?
- What gameplay structures occupy the large data objects and the remaining unclassified executable-object ranges?

These are separate from the closed physical-accounting question. For code recovery, use the relocation-backed tables and callback inventory as the next discriminators. Increasing a broad instruction budget alone does not supply the missing value or alias evidence.

## Memory and resumption

The preferred LE entry is **0x3D85C**, not the MZ entry. MAIN.EXE's DOS bootstrap calls an external loader through an overlay thunk. The protected image has **4 objects / 105 enumerated pages / 10,060 records / 10,055 writes**. Physical file bytes total **518,713**; virtual object bytes total **462,470**; zero-filled virtual bytes total **33,369**. The physical-only object-1 suffix is **524 bytes**, and the zero gap before page data is **398 bytes**.

The current LE checkpoint contains **22,910 instructions and 384 candidate functions**. Basic queues are drained; **16 derived jobs and 60 indirect transfers remain unresolved**. Preserve both instruction interpretations at 0x3D1E9/0x3D1EA. The independent byte map and full fixup census have been compared with every mapped byte and every supported record.

Use the packaged README and coverage JSON to choose a specific remaining question. Extract byte-retaining projects and originals outside a source checkout. The tool's native DOS/4GW execution profile remains a separate qualification step; no game or installer was executed during this pass.


## Appendix: precise remaining indirect-transfer blockers

The complete local evidence is in [the indirect-scope diagnostic](loader-audit/indirect-scope-diagnostic.md) and its companion JSON. This was a consistent read-only capture with zero SQLite changes.

### Seventeen-entry switch table

The dispatch at **0x10779** belongs to candidate owner **0x105E0**. Its derived job is done and its flow solver stable after 491 steps. The rejection is **unbounded_or_nondominating_index**, not a budget stop. The nearby code compares a 16-bit memory value with 0x10, branches above the bound, reloads the stack-held offset, then performs XOR EAX,EAX followed by MOV AX from memory before the indexed jump.

The current guard implementation handles selected register comparisons but does not retain the compared memory-load identity here. The normalized MOV AX supplies no assignment and clobbers the EAX family, losing the relation to the preceding XOR. The CS override already carries the flat-native-segment assumption; it is not the reported obstacle.

LE fixups identify exactly **17 four-byte table entries at 0x10550..0x10590**, with 11 unique initial targets. Only the shared default target, 0x10D3D, is already a stored instruction. The other ten starts are 0x10781, 0x10790, 0x10855, 0x10889, 0x108B8, 0x10966, 0x109BF, 0x10A90, 0x10AC8 and 0x10B65.

The useful next proof is local: establish compare/reload identity and relevant write assumptions, retain the unsigned 0..16 fallthrough range, and model the partial-register merge. The stored engine has not already proved that range, and the target list was not silently admitted as reachable code.

### Writable callback defaults and stack aliases

The calls through **0x5BFF4, 0x5BFF8 and 0x5BFFC** have initial LE-loaded values **0x3D640**, a stored RET. Their local owner **0x3D641** is stable after 27 steps but reports **snapshot_memory_may_be_modified**. The rejection is about possible write history, not merely the writable object flag.

Inspection of source and normalized IR supplies a specific explanation: the prologue's stack store records a 32-bit-masked physical stack expression, while the read-qualification helper recognizes a plain symbolic-stack shape. The masked form remains a conservative possible alias. This explanation is derived from the implementation and IR; raw incoming solver states are not persisted. It is not proof that a callback slot was actually overwritten. Later unknown calls add further effects.

A larger owner, **0x274A0**, separately stops after 25,000 flow steps with six pending items and incomplete_dataflow. More budget could address that caller's unfinished computation, but cannot by itself establish the callback alias contract or repair the switch-index representation.

Any refinement should preserve actual absolute/unknown stores and qualify stack separation. The initial defaults alone do not justify restoring the seven withdrawn snapshot-only control edges.
