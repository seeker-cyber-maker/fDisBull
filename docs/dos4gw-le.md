# DOS/4GW LE static analysis

The mixed-mode extension is a local development candidate. Use a checkout or
wheel containing these changes; this guide does not announce a shared system
installation or a published release.

The LE loader maps supported protected-mode executable objects, retains the
complete original file and uses the native x86 decoder in each object's declared
16-bit or 32-bit mode. The ordinary project analyzer owns traversal, persisted
facts, candidate functions, xrefs, CFGs and byte versions. Runtime execution and
runtime selector binding are separate evidence paths.

## Select the image

| Selection | Behavior |
| --- | --- |
| Default / `--image auto` | Selects a validated direct LE, independent MZ/LE or declared MZ/BW/inner-MZ/LE application. Unsupported recognized profiles fail explicitly. |
| `--image le` | Selects the same LE application with complete mapping and supported-fixup checks. |
| `--image mz` | Selects the original outer DOS bootstrap as a separate real-mode image. |

For bound carriers the outer MZ's declared end must identify a complete BW
header. Its absolute `next_header_pos` must point forward to a validated inner
MZ whose independent `e_lfanew` identifies LE. This is bounded chain traversal,
not signature scanning or carving. The inner header must actually contain the
secondary-header field. Original-file positions, application-file positions,
object offsets and preferred address keys stay distinct in metadata.

Keep MZ and LE selections in separate projects. `--arch` bypasses container
loading and must not be used to force a mixed module through one raw decoder.
LE import rejects incompatible `--bits`, `--base`, `--load-segment`,
`--slice-arch` and library/module overrides.

```sh
fdisbull identify /private/original.exe
fdisbull import /private/original.exe /private/protected.fdb --image le
fdisbull analyze /private/protected.fdb --max-instructions 5000
fdisbull analysis-status /private/protected.fdb
fdisbull disasm /private/protected.fdb --address 0x60000 --lines 16
fdisbull cfg /private/protected.fdb 0x60000
```

The example address is a caller-selected preferred object address, not a
universal entry. Inspect the actual sections and loader metadata first. Original
programs, project databases and decoder objects belong in private paths outside
source Git and distribution inputs.

## Object modes and traversal

Each mapped object retains its preferred base, size, flags, file-backed extents
and declared decoder width. The project persists `decode_regions` in each byte
version. The project's default width describes its selected entry; the analysis
namespace remains stable while each instruction exposes its actual
`decoder_bits` and `decoder_context`. Disassembly, memory queries, CFG nodes,
function-boundary discovery and native backing blocks use the address's object
mode. Reopening a project and making a mapped-memory child version preserve
these declarations.

New mode-bearing LE projects use semantic project schema 10. Older fDisBull
readers reject that format instead of silently treating the bridge as 32-bit.
The new reader also accepts ordinary legacy schema-9 projects. Unguarded
schema-9 mode prototypes require explicit reimport; changing a format number
alone is not a general migration procedure.

A 16-bit object's near instruction pointer is object-relative. Only qualified
same-object targets are rebased into preferred address keys. Decoding and
fallthrough stop at object boundaries and at actual file-backed boundaries;
interior zero-fill pages and trailing BSS are not invented instruction bytes.
A near branch does not establish a switch of runtime code-selector mode.
Selectors and far transfers remain unresolved unless separately qualified.

A file-backed executable 16-bit object boundary receives a labeled candidate
seed. That allows inspection of a bridge or interrupt-style object without
asserting a call edge from the main entry or claiming a proven function root.
One bounded pass may leave pending work. An empty implemented queue is not
whole-program recovery or proof that every byte is reachable.

## Fixups and immutable source

For supported internal `offset32` fixups, the static analysis image receives the
target object's preferred base plus target offset. Original bytes, original
values, record positions, source fragments, target object/offset and resulting
static values are retained. Target offsets may use 16 or 32 bits, and object
ordinals may use 8 or 16 bits. Signed page-crossing source positions and identical
cross-page duplicate records are preserved; conflicting writes refuse.

Internal `offset16` records are parsed and retained **symbolically and
unapplied**. Their field bytes are unchanged, `applied` is false,
`relocated_value` is null and the record retains its target object, target offset,
preferred target address and explicit unresolved reason. Original-runtime
observations and another documented loader differ in this field's treatment;
the generic loader does not choose a runtime alias convention from the record
alone. A preferred base aligned to 64 KiB must not conceal that uncertainty.

An instruction intersecting such a field reports
`operand_status='symbolic_unapplied_fixup'` and retains its relocation evidence.
Control-flow closure and operand interpretation are separate: a closed CFG can
still have `interpretation_complete=false`. Segment-derived LE16 memory
expressions remain symbolic; they never inherit real-mode `selector * 16`
arithmetic. Native backing blocks keep their true width, but an unapplied
relocation makes the capture incomplete for executable reconstruction.
Fixed-width derived semantics and ABI `auto-analyze` explicitly refuse mixed
projects and any LE image with symbolic operand fixups; they do not publish 32-bit effects for 16-bit instructions.

All applied fixups identify the separate `static_analysis_image` and set
`runtime_applied=false`. The full original container remains `source_bytes`.
Static preferred addresses are neither observed native placements nor runtime
selectors. Native object placements can differ by object, so a single uniform
runtime relocation delta must not be assumed.

Standalone inspection limits its relocation preview to 10,000 records and
reports the total. Imported projects retain every supported record. Use bounded
pagination for complete inspection:

```sh
fdisbull relocations /private/protected.fdb --limit 50 --offset 0
fdisbull relocations /private/protected.fdb --limit 50 --offset 50
```

Large replies can use the global `--output-artifact-dir` option with a private
external directory. Fragmented mappings do not claim a single contiguous source
file offset.

## Supported profile and refusals

The profile supports little-endian, level-zero i386/486 LE executable modules,
4096-byte pages, 16-bit objects up to 64 KiB, 32-bit objects, enumerated pages,
zero-fill pages and BSS. Source and mapped bytes are bounded to 64 MiB, with
4,096 objects, 16,384 logical pages and 100,000 fixup records. Mappings, structural
extents and overlaps are checked before admission.

LX, external imports, selector/far-pointer fixups, self-relative fixups,
fixup lists/chains/addends, iterated/invalid/compressed pages, privileged or
resource object semantics, DLLs/drivers and other page sizes still refuse.
An unsupported profile is not proof that the original executable is invalid.
The separate `le-driver-inspect` / `le-driver-disasm` interfaces retain their
broader symbolic object-inventory contract, including driver/library variants.

## Versioned memory and native verification

`patch` creates a child mapped-memory version without modifying the original
container or parent. Mode declarations and source metadata are preserved with
the existing inherited-metadata warning. Original fixup evidence describes the
initial loading transformation, not an inverse executable writer.
`refresh-metadata` and runnable LE file rewriting remain unsupported.

Native qualification must bind the original executable, actual descriptor
bases/default widths, observed memory and each relocation target object. It
must distinguish mapped code from code actually reached. Mapping a 16-bit
interrupt-style object does not establish that the handler ran. The private
Doom pilot reached original title screens and checked sampled offset32 sites
against independently observed object bases; its offset16 convention remains
explicitly unresolved. No licensed target bytes are distributed by the tool.

See [DOS debugger boundaries](DOSBOX_DEBUGGER.md) for the original-runtime
backend and [the processor seam](PROCESSOR_MODULES.md) for native decoder facts.
A normal LE static project does not by itself provide a live runtime binding.

## Encoding references

The format definitions follow Open Watcom commit
`5474be3542af05eee71be05fafc31bbe11f1415b`:

- [LE/LX header, object, page and fixup definitions](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/watcom/h/exeflat.h).
- [DOS/16M BW header and absolute next-header field](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/watcom/h/exe16m.h).
- [LE page/data writer](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/wl/c/loadflat.c).

These references explain encodings. Authored tests and explicitly scoped native
receipts qualify the implemented subset; a specification alone does not prove
a particular original loader's runtime convention.
