# Win16 NE static loading and analysis

fDisBull can select and load supported Windows 16-bit NE images directly from
an MZ-wrapped source file. It preserves the complete original container,
initialized segment bytes and raw operands. NE relocations remain symbolic;
this view does not allocate Windows selectors or execute Windows code.

## Select the actual image

```text
fdisbull inspect /private/COLONIZE.EXE
fdisbull import /private/COLONIZE.EXE /private/colonization-ne.fdb --image ne
fdisbull analyze /private/colonization-ne.fdb --max-instructions 1000
fdisbull analysis-status /private/colonization-ne.fdb
fdisbull analyze /private/colonization-ne.fdb --start ne:4:0x547c --max-instructions 5000
fdisbull disasm /private/colonization-ne.fdb --address ne:4:0x54b5 --lines 50
fdisbull render /private/colonization-ne.fdb /private/food.png --address ne:4:0x54b5
```

Use caller-owned paths and a new project. Automatic import selects a recognized
NE view as well; malformed or unsupported NE does not silently become a DOS
stub. `--image mz` remains the explicit, separately validated DOS view of the
same container. One image/context belongs to each project.

Static analysis starts with the declared entry point and follows native
instruction facts. Export/entry-table seeds and explicit question-driven seeds
supply later frontiers. Budgets can leave pending work. Inspect actual returned
instruction starts and the pending frontier; a stored nearest-row view or empty
implemented queue is not evidence of complete NE or game recovery.

## Logical addresses and preserved operands

The canonical spelling is `ne:20:0x0122`: decimal NE segment index 20 and an
explicit hexadecimal offset. Decimal or `0x` integer components are accepted;
ambiguous bare leading-zero offsets are rejected. Numeric queries can use the
packed database identity `(segment_index << 16) | offset`, here `0x140122`.
This is an identity key, not linear process memory.

`ne:4:0x547c` must not be interpreted as DOS paragraph arithmetic. Unprefixed
`segment:offset` and DOS `cs` overrides are refused in NE projects. The decode
context is `x86:16:little:ne`. The normal x86 native decoder supplies facts at
the segment-relative offset; near branches/fallthrough return to that same
logical segment, including a valid 16-bit IP wrap. They cannot fall into the
next packed segment slot.

Disassembly rows include `logical_location`, `target_logical_location` and
`ne_fixups`. A logical location carries segment index, offset, key and
`runtime_selector: null`. Raw instruction bytes and operand text remain intact.
A validated internal far-operand fixup can add a logical call/jump target;
unfixed selectors, imports and unsupported relationships stay unresolved.
No guessed selector value is written into the program.
Selector-only fixups retain the target segment and raw fields; unused target2
does not become a point offset. Additive source addends stay distinct from the
declared base target. Fixups touching opcode, prefix, ModRM/SIB or other
structural encoding bytes stop native successor inference rather than letting
unrelocated bytes drive a false CFG. Typed NE pointers likewise remain encoded
values with unknown targets until a runtime/state binding is qualified.

CFGs, call views, location queries and stored-state disassembly images preserve
the NE identity. Native memory access facts retain an unresolved selector
boundary rather than using a DOS real-mode base. A declared automatic-data or
stack segment does not observe current DS, SS or ES values in a live process.

## Mapping, metadata and bounds

Each segment retains its initialized file range and declared minimum allocation.
Declared heap/stack allocation is represented as deterministic zero fill within
the supported segment bound. Allocation-only bytes are not code seeds.
`locate` identifies `initialized_file_bytes` versus `allocation_zero_fill` and
returns a source-file offset only for initialized bytes. That is an import-phase
mapping, not a post-initialization memory observation.

NE metadata retains header fields, segments, fixed/movable entry records,
resident/nonresident names, exports, symbolic imports, resource file ranges and
relocation records with expanded source chains. Entry/export names use their
ordinal relationships. Imported procedures retain module plus name or ordinal;
no external address is allocated. Resources are inventoried without launching
a decoder or mapping them as executable segments.

Standalone inspection caps large lists. An imported project retains all NE
fixups and exposes them through the existing paginated query:

```python
with Project('/private/colonization-ne.fdb') as project:
    first_page = project.information('relocations', limit=100, offset=0)
    next_page = project.information('relocations', limit=100, offset=100)
```

Fixups preserve their raw record, source type/width, additive flag, source file
locations and bytes. Bounded internal targets receive logical segment/offset
identities; symbolic imports and OS floating-point fixups remain explicit.
The loader does not modify source bytes. Overlapping source sites, cyclic or
out-of-bounds chains and invalid ordinal/segment references are rejected.

The supported static profile is Windows NE with ordinary x86-16 segments and
supported byte/selector16/offset16/far16:16 relocation source encodings. It
refuses OS/2 targets, iterated or 32-bit segments, self-loading modules and
unsupported relocation encodings. Bounds include 64 MiB input/mapped storage,
64 KiB per segment, 4,096 segments, 65,536 fixup records and 262,144 expanded
source sites. Counts, strings, tables, allocations and source ranges are checked
before use. A recognized format outside this profile is not a loadable view.

## Versions and execution boundary

Patches create mapped-memory child versions. The original NE source container
and file metadata remain inherited, with a warning; this implementation does
not emit a rewritten NE executable or apply inverse fixups. A changed fixup
operand must not reuse a stale logical target qualification. Restart preserves
stored bytes, analysis, logical locations and authored presentation.

NE projects use native static traversal and stored CFG/disassembly views.
Project-native advanced IR/ABI analysis and signature capture are refused until
there is a qualified selector-aware model. Explicit mathematical-model proofs
and standalone bounded lifts retain their existing independent scope; they do
not establish native NE semantics. DOS/PE64 and raw-machine debug launch paths
refuse NE projects. A compatible Win16 runtime needs separate preparation and
qualification.

## Frictions encountered and resolved

| Friction | Resolution |
| --- | --- |
| Manual raw projections lost native segment identity and cross-segment calls | Direct NE image selection with logical segment keys and validated symbolic fixups |
| Unrelocated fixups could change opcode structure or only part of a far operand | Source-range/structural guards and complete operand qualification; unsupported combinations stay unresolved |
| Selector-only raw target2 looked like a meaningful point offset | Retain its raw value and target segment; leave offset/point identity unknown |
| Capped standalone export previews could hide data-export names | Project symbol indexing uses full retained NE tables; shared presentation survives preview limits, child versions and reopen |
| Generic address, pointer and memory paths assumed flat or real-mode semantics | Explicit NE parsing and unresolved selector/pointer facts; unsupported project-native advanced paths refuse |
| Initialized file data was compared with post-initialization DOS memory | Keep phase and state bindings with each cross-edition correspondence |

## Colonization qualification and next friction

The owned Colonization input has 33 declared segments. Its direct NE import
exposes the Windows food routine with original source mappings and symbolic
internal references. The [paired food study](COLONIZATION_FOOD_EQUIVALENCIES.md)
records the source spans, model comparison, ABI differences and unknown runtime
state. Licensed programs, databases and raw evidence remain outside Git.

This removes the manual raw-segment projection step. Remaining work includes
selector-aware dataflow, initialized-to-runtime resource bindings and qualified
Win16 execution. The proposed [snippet relationship ledger](uil-rfcs/0003-cross-edition-snippet-links.md)
would preserve cross-edition candidates and their domains without treating
static similarity as full native equivalence.

Format references: [Open Watcom NE structures](https://github.com/open-watcom/open-watcom-v2/blob/master/bld/watcom/h/exeos2.h)
and [Wine 10.0 NE segment loader](https://github.com/wine-mirror/wine/blob/wine-10.0/dlls/krnl386.exe16/ne_segment.c).
These informed the bounded static profile; fDisBull does not embed or invoke
Wine to load or analyze this image.
