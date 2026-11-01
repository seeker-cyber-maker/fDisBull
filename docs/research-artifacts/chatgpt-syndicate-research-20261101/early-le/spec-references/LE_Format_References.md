# LE physical-scope reference

Research date: 2026-10-30. This is format guidance, not proof of the selected game's runtime behavior. No external document is reproduced here.

## Primary sources

- **Open Watcom structures:** [exeflat.h](https://github.com/open-watcom/open-watcom-v2/blob/bd0aebdf6a1bdb9ded59adfcd9e281582c218fa1/bld/watcom/h/exeflat.h).
- **Open Watcom producer:** [loadflat.c](https://github.com/open-watcom/open-watcom-v2/blob/bd0aebdf6a1bdb9ded59adfcd9e281582c218fa1/bld/wl/c/loadflat.c).
- **Relocation emission:** [obj2supp.c](https://github.com/open-watcom/open-watcom-v2/blob/bd0aebdf6a1bdb9ded59adfcd9e281582c218fa1/bld/wl/c/obj2supp.c).
- **MZ stub and name tables:** [loados2.c](https://github.com/open-watcom/open-watcom-v2/blob/bd0aebdf6a1bdb9ded59adfcd9e281582c218fa1/bld/wl/c/loados2.c).
- **IBM LX specification, Revision 11, 2001-06-14:** [archived original](https://archive.org/stream/IBMOS2Warp4ToolkitDocuments2/32-bit%20Linear%20eXecutable%20Module%20Format%20%28LX%29%20Specification).
- **Independent DOS consumer:** [DOS/32A loader.asm](https://github.com/amindlost/dos32a/blob/06d8e3a0b2397d872205d6c99a7de0d6b8628bcc/src/dos32a/loader.asm). This supports a practical subset; it is not a general specification or evidence of Syndicate's original extender.

## LE-specific facts versus shared LX concepts

Open Watcom's packed object record is 24 bytes. Its LE page entry is a big-endian 24-bit page number followed by a byte of flags. LX uses an eight-byte offset/size/flags entry instead. Header +0x2C means final physical page length in LE, but a page-offset shift in LX. Do not apply LX page decoding to LE.

The shared header structure is 196 bytes in Open Watcom, including 20 trailing reserved/VxD-extension bytes. For a DOS LE file, those bytes still need physical ownership even when zero; VxD-specific meaning requires the corresponding profile.

Open Watcom stores object virtual size independently from initialized size. Its LE writer fills intermediate page tails and uses the last-page field for the final physical page. It emits the full page size when that final page is full; a zero-means-full compatibility rule needs separate qualification.

## Offset and extent checklist

Let H be the absolute LE-header position. These are factual field locations from the packed structures. The current target uses only a subset.

| Region or field | Header location | Base and extent |
| --- | --- | --- |
| Objects | +0x40, count +0x44 | H-relative; 24 bytes each |
| Page map | +0x48 | H-relative; 4 bytes each for LE |
| Iterated storage | +0x4C | File-relative |
| Resources | +0x50, count +0x54 | H-relative; 14 bytes each |
| Resident names | +0x58 | H-relative; length/name/ordinal records |
| Entry bundles | +0x5C | H-relative; variable bundles |
| Directives | +0x60, count +0x64 | H-relative; 8 bytes each |
| Fixup page offsets | +0x68 | H-relative; 4 times page-count-plus-one |
| Fixup records | +0x6C | H-relative; final page-table sentinel bounds stream |
| Import modules | +0x70, count +0x74 | H-relative; length-prefixed names |
| Import procedures | +0x78 | H-relative; fixup-section end bounds stream |
| Page checksums | +0x7C | H-relative; 4 bytes per page, if present |
| Enumerated data | +0x80 | File-relative |
| Nonresident names | +0x88, size +0x8C | File-relative |
| Debug data | +0x98, size +0x9C | File-relative |

### IBM's debug-offset correction

Revision 11 explicitly corrects the earlier claim that debug offsets were header-relative: +0x98 is file-relative. This agrees with Open Watcom's producer. The old 1992 [EDM/2 reprint](https://www.edm2.com/index.php/LX_-_Linear_eXecutable_Module_Format_Description) contains the superseded wording. This is a documented historical erratum, not established evidence of two valid runtime dialects.

IBM's shared-table description also makes directive payload bases conditional: resident payloads use H, nonresident payloads use the file start. A fixup aggregate includes imports; it is larger than the record stream alone. Empty tables can have coincident positions. These shared concepts do not prove support for every LE extension.

## Cross-page fixups

Open Watcom's relocation emitter writes a second record when a relocation crosses a page boundary, subtracting the page size from its source offset. DOS/32A sign-extends that offset when consuming records. Thus a negative second-page offset can describe the same four-byte write as the preceding page's record.

Preserve both encoded records but count the semantic write once after checking equal source, width and target. Verify that each page consumes its precise fixup-record span and that the final sentinel is in bounds. Source lists are flagged in the source-type byte. Unsupported forms must remain explicit.

## Interpretation boundaries for the selected target

Maintain separate ledgers for physical bytes, object-backed bytes, virtual zero-fill and decoded instructions. A complete physical partition does not recover code semantics or runtime reachability. File bytes beyond an object's exact virtual size may still occupy its final physical page; that is distinct from allocation rounding or proven inaccessibility in the original loader.

The target declares a loader aggregate containing the fixup aggregate. Preserve the two declarations without summing them as disjoint regions. Open Watcom's examined writer sets its loader size before writing fixups, so the target declaration is not justified merely by citing that producer; its producer/version-specific rationale remains unresolved.

Zeros in an inter-section interval establish its contents. Alignment arithmetic can support a padding hypothesis but cannot prove deletion safety. An unclaimed tail must remain an exact interval until its role is established. Zero checksum fields do not establish successful checksum verification.
