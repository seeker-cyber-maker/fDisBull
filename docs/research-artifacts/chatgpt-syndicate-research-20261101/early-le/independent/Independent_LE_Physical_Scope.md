# Independent physical scope of Syndicate MAIN.EXE

## Result

All **518,713 bytes** are assigned exactly once in a 19-interval physical ledger. The enumerated data ends exactly at EOF. No unexplained nonzero physical region remains. This is a structural accounting result; it does not establish the semantics or reachability of all mixed code and data.

The independent script reads raw MZ/LE structures and imports no fDisBull code. It did not reuse the prior independent reader or inspect the production LE parser. Original input identity was already checked by the coordinator; this pass did not repeat that whole-file hash.

## Physical byte ledger

Every range is half-open: the end offset belongs to the following range. Offsets are hexadecimal file coordinates.

| Start | End | Bytes | Structural ownership |
| ---: | ---: | ---: | --- |
| 0x0 | 0x1C | 28 | MZ fixed DOS fields |
| 0x1C | 0x40 | 36 | MZ extension/reserved fields and LE pointer |
| 0x40 | 0x58 | 24 | MZ segment relocation records |
| 0x58 | 0x60 | 8 | MZ paragraph padding |
| 0x60 | 0x28B2 | 10,322 | DOS bootstrap code and data; mixed contents |
| 0x28B2 | 0x28B8 | 6 | Zero-filled MZ-to-LE gap |
| 0x28B8 | 0x297C | 196 | LE fixed header, including 20 reserved bytes |
| 0x297C | 0x29DC | 96 | Four LE object records |
| 0x29DC | 0x2B80 | 420 | LE object page map |
| 0x2B80 | 0x2B88 | 8 | Resident name and zero terminator |
| 0x2B88 | 0x2B89 | 1 | Empty entry-table terminator |
| 0x2B89 | 0x2D31 | 424 | Fixup page offsets and final sentinel |
| 0x2D31 | 0x15A71 | 77,120 | Internal offset32 fixup records |
| 0x15A71 | 0x15A72 | 1 | Empty import-procedure table zero sentinel |
| 0x15A72 | 0x15C00 | 398 | Unassigned inter-section gap |
| 0x15C00 | 0x559F4 | 261,620 | Object 1 file-backed payload |
| 0x559F4 | 0x55C00 | 524 | Object 1 final-page slack |
| 0x55C00 | 0x62C00 | 53,248 | Object 2 file-backed payload |
| 0x62C00 | 0x7EA39 | 114,233 | Object 4 file-backed payload |

The 398-byte inter-section gap, six bytes between the MZ extent and LE header, eight bytes of MZ header padding, and 524 bytes after object 1's virtual end are all zero. The 524-byte physical slack is outside the exact declared object extent, but may still be copied or accessed in a rounded native allocation. No native behavior or deletion safety is established. Deletion or compaction would still require updating affected offsets and qualifying the original loader. No such modification was made.

## Declared aggregates are not disjoint sections

The loader aggregate starts at file 0x297C and declares 78,070 bytes, ending at 0x15A72. The fixup aggregate starts at 0x2B89 and declares 77,545 bytes, ending at the same point. Thus this file's loader aggregate includes its fixup aggregate. Adding both header sizes as independent physical sections would double-count bytes.

Current Open Watcom loadflat.c assigns loader_size before writing fixup tables. That current writer therefore supplies a different convention from this old target. The target's explicit values are preserved as overlapping descriptive aggregates; the byte partition instead uses concrete records and tables. No corruption diagnosis follows from this difference alone.

## MZ bootstrap and LE metadata

- The DOS header is 96 bytes. Its six segment-relocation records occupy 24 bytes at 0x40. Each relocation source falls within the declared load image.
- The declared MZ load image is 10,322 bytes. CS:IP is 0000:0210, corresponding to file offset 0x270. It remains a mixed native-code/data region in this structural pass.
- The MZ extent ends at 0x28B2, followed by six zero bytes before LE at 0x28B8.
- The LE fixed header is 196 bytes; its final 20 reserved/VxD-extension bytes are all zero. The OS-type field is 1 and CPU type is 2; this does not make the DOS bootstrap an OS/2 process.
- The resident-name table contains main with ordinal 0 and a zero terminator. The entry bundle table is empty, represented by a one-byte zero terminator.
- Resource count, module-directive count, import-module count, nonresident-name size, debug length and per-page checksum pointer are zero. No active payload from those features is hidden outside the ledger.
- The import-module table is empty. Its pointer equals the import-procedure pointer, whose reserved zero offset is represented by one zero byte at 0x15A71.
- All 105 logical page records use flags 0 and physical page number equal to logical number. The final physical page holds 3,641 bytes and ends at EOF.
- No iterated page, compressed page, nonresident-name payload, debug payload, active resource table or additional appended container is established by this executable.

IBM Revision 11 resolved the historical debug-offset erratum: debug offsets are file-relative. This sample has debug_off and debug_len both zero, so it does not exercise that parser path. The iterated-data pointer is likewise zero.

## Object and virtual-memory scope

| Object | Preferred range | Flags | Virtual bytes | File-backed bytes | Zero fill |
| --- | --- | --- | ---: | ---: | ---: |
| 1 | 0x10000..0x4FDF4 | readable, executable, preload, default32 | 261,620 | 261,620 | 0 |
| 2 | 0x50000..0x63E60 | readable, writable, preload, default32 | 81,504 | 53,248 | 28,256 |
| 3 | 0x70000..0x70C00 | readable, writable, preload, default32 | 3,072 | 0 | 3,072 |
| 4 | 0x80000..0x9C632 | readable, writable, preload, default32 | 116,274 | 114,233 | 2,041 |

Object 1 is the only declared executable object. Objects 2–4 are declared writable data; object 3 has no physical pages. The stack and autodata object ordinals both select object 2. Initial ESP is 81,504, its virtual size, so the declared initial stack top is the end address 0x63E60.

The complete virtual image contains 462,470 owned bytes, made from 429,101 source-backed bytes plus 33,369 zero-filled bytes. These counts exclude the physical page slack. They also exclude 112,556 bytes of gaps between preferred object ranges. Preferred bases are static loader declarations, not observed runtime selectors or allocations.

## Complete fixup record accounting

- The fixup page table has 106 little-endian 32-bit offsets: one per logical page plus its terminal sentinel.
- Its final value is 77,120, exactly the bytes consumed by 10,060 parsed records. Per-page boundaries are monotonic and every record ends within its page's metadata slice.
- All source types are offset32 (0x07). Target flag 0 occurs 6,710 times; target flag 0x10 occurs 3,350 times. Target object ordinals use one byte. Record widths are seven or nine bytes, respectively.
- Signed source offsets range from -3 to 4,095. Five cross-page writes are represented twice. They agree, so 10,060 records correspond to 10,055 unique four-byte writes.
- No distinct four-byte writes overlap. All source writes lie within their declared objects. All target offsets lie within or exactly at the end of their target objects.
- Three records target object 4's end address, 0x9C632. These are preserved as one-past pointers; they are not evidence of a missing fifth object or missing physical data.

| Source object | Target object | Record count, including duplicate records |
| --- | --- | ---: |
| 1 | 1 | 1,854 |
| 1 | 2 | 6,532 |
| 1 | 3 | 14 |
| 1 | 4 | 809 |
| 2 | 1 | 13 |
| 2 | 2 | 838 |

Objects 3 and 4 contain no relocation source writes. Object 4 is referenced by 809 records from object 1. Its payload is still semantically unclassified data in this pass; lack of relocations does not prove a particular resource format.

Object 2 contains 13 data-to-code relocation records, pointing to nine distinct object-1 addresses. These are useful candidate seeds or cross-checks for the separate instruction analysis, with no claim that all are called at runtime:

| Pointer source | Code target |
| --- | --- |
| 0x5BFFC | 0x3D640 |
| 0x5BFF8 | 0x3D640 |
| 0x5BFF4 | 0x3D640 |
| 0x5C32E | 0x3F974 |
| 0x5C334 | 0x3F37C |
| 0x5C33A | 0x406F9 |
| 0x5C346 | 0x4073E |
| 0x5C2E4 | 0x3F89D |
| 0x5C2EC | 0x404EF |
| 0x5C2E8 | 0x404EF |
| 0x5C340 | 0x40E6C |
| 0x5C328 | 0x40C18 |
| 0x5C324 | 0x40C18 |

## Independent mapped-image comparison support

The JSON report contains a SHA-256 for each object before and after applying the unique relocation writes. These hashes bind the independent mapped-byte result and can be compared with fDisBull's retained object regions. Computing them is distinct from repeating the original-file identity check. No comparison result is asserted by this report; the coordinator owns that check.

## Remaining questions

- Semantic partition and reachability inside the declared native-code/data regions, including the bootstrap's extender dispatch.
- Meaning of the writable data objects, tables and any native-to-resource interpreter behavior.
- Original runtime placement, selector mapping and observed fixup application.
- Original loader tolerance for compaction or removal of zero-filled physical bytes.
- Generic LE features absent from this file: resources, nonempty export entries, imported modules/procedures, iterated/compressed pages, VxD extensions and active debug/nonresident-name payloads.

No game execution, runtime mapping, runnable rewrite, generic-format acceptance or whole-game semantic recovery was performed.

## Evidence files

- scope_le.py — independent parser and partition validator.
- le-physical-scope.json — all header fields, objects, 105 pages, 19 physical intervals, fixup counts and object hashes.
- independent-fixup-records.json — all 10,060 decoded metadata records with physical, object and preferred virtual coordinates.
- le-header-fields.csv — fixed-header field offsets and exact values.

## Primary sources

- [LE/LX header, page and fixup definitions](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/watcom/h/exeflat.h).
- [Writer, page layout and declared aggregate sizes](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/wl/c/loadflat.c).
- [Fixup record reader](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/exedump/c/wdfix.c).
