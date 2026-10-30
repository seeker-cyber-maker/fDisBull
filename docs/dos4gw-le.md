# DOS/4GW LE static analysis

**Development candidate — unreleased.** Use a source checkout or wheel that
contains this module. This guide does not announce a published release or a
qualified native DOS/4GW execution backend.

The LE loader lets fDisBull analyze the protected-mode image in a supported
DOS/4GW-style executable. It maps the LE objects and their internal fixups,
then uses the existing **x86-32 `NativeProcessor`** for instruction decoding
and the existing project analyzer for traversal and persistent evidence.
There is no new instruction set, game-script interpreter or plugin registry.

For measured target results, format evidence and follow-up acceptance criteria,
see the [DOS format findings](DOS_FORMAT_FINDINGS_2026-10-29.md).

## Select the image

A file may contain both a 16-bit DOS MZ bootstrap and a 32-bit LE program.
These are separate image views with different entry points and address models.

| Selection | Behavior |
| --- | --- |
| Default / `--image auto` | A recognized LE input selects the supported LE loader. An unsupported LE profile fails explicitly; it is not silently analyzed as the preceding DOS bootstrap. |
| `--image le` | Requires an LE image, either bare or referenced by an independent MZ secondary-header field. It applies the same complete loading checks as automatic selection. |
| `--image mz` | Selects the declared 16-bit DOS load image of an MZ container, subject to the existing MZ validation. It does not load the LE program. |

Keep the two views in separate projects. For inputs with LE fixups, use the
container loader: `--arch` selects raw bytes and bypasses this mapping.
`--bits`, `--base`, a nondefault `--load-segment` and `--slice-arch` do not
describe this executable LE profile and are rejected by LE import. `--module`
does not enable DLL or missing-entry support for this profile.

## Run a bounded first pass

Replace the example paths with the chosen input and new private project paths.
Original game files and byte-retaining project databases belong outside the
source checkout and tool packages.

```sh
fdisbull identify /path/to/program.exe
fdisbull --output-artifact-dir "$HOME/fdisbull-private/output-artifacts" inspect /path/to/program.exe --image le
fdisbull import /path/to/program.exe /path/to/program-le.fdb --image le
fdisbull analyze /path/to/program-le.fdb --max-instructions 5000
fdisbull analysis-status /path/to/program-le.fdb
fdisbull functions /path/to/program-le.fdb --limit 20
fdisbull disasm /path/to/program-le.fdb --lines 20
```

Omitting `--image le` on import selects the same supported LE image
automatically. To inspect only a valid preceding DOS bootstrap instead:

```sh
fdisbull inspect /path/to/program.exe --image mz
fdisbull import /path/to/program.exe /path/to/program-dos-stub.fdb --image mz
```

One bounded analysis call may leave pending work and unresolved indirect
transfers. Function entries are candidates. Neither a drained queue nor a
large instruction count establishes full-game coverage or runtime behavior.
These commands do not execute the input program.

## Understand addresses and fixups

The loader maps each object's declared preferred base and virtual size. The
declared entry is the selected start object's base plus its EIP offset.
An explicit `--entry` must name a file-backed byte in an executable mapped
object. The result is a flat x86-32 address; it is not a real-mode `CS:IP`
pair or an observed protected-mode selector.

For supported internal offset32 fixups, the loader writes the target object's
preferred base plus its target offset into a separate mapped image. Target
offset fields may be 16 or 32 bits; object ordinals may be 8 or 16 bits.
Signed source offsets handle words spanning page boundaries, and identical
duplicate records on adjoining pages retain separate evidence while applying
one unique write. Conflicting overlapping writes are rejected.

The exact source container remains retained. Source-file offsets, mapped
addresses and mapped-snapshot hashes describe different representations.
Each fixup records its original mapped value, relocated value, metadata-record
offset and source-file fragments. The original mapped value may include
declared zero fill. A word spanning noncontiguous physical pages or BSS does
not claim a single contiguous source-file offset.

Standalone `inspect` shows a bounded preview of at most 10,000 fixup records,
with the total count and an explicit warning when that preview is capped.
That preview can still exceed the core inline reply budget. The global
`--output-artifact-dir` option in the example above permits a large reply to
be retained as an artifact and returns a compact receipt. Choose a private
directory outside Git; inspect the referenced artifact only when its detail
is needed. The option precedes the subcommand.

Imported projects retain every supported fixup and expose the complete list
through the existing paginated query:

```sh
fdisbull relocations /path/to/program-le.fdb --limit 50 --offset 0
fdisbull relocations /path/to/program-le.fdb --limit 50 --offset 50
```

Continue increasing the offset by the page size as needed. The per-request
limit remains bounded; a standalone preview cap does not truncate the project's
retained relocation evidence. Prefer these paginated project queries for
routine detail. Sections expose virtual size, permissions and
source fragments; contiguous file coordinates remain unknown when backing is
fragmented.

## Supported profile and explicit refusals

The current loader supports little-endian, level-zero LE executables with an
i386/486 CPU declaration, 4096-byte pages and 32-bit objects. It handles
enumerated physical pages, explicit zero-fill pages, BSS and the internal
offset32 fixups described above.

It refuses LX, imported modules, selector and far-pointer fixups,
self-relative fixups, fixup lists/chains/addends, 16-bit or unsupported object
semantics, iterated/invalid/compressed pages, DLLs/drivers and other page sizes.
An unsupported encoding is a limit of this module, not proof that the input is
an invalid executable.

Source and total mapped bytes are limited to 64 MiB; additional limits are
4,096 objects, 16,384 logical pages and 100,000 fixup records. Bounds and
overlaps are checked before an image is accepted.

This module does not recover RTLink or other dynamic overlays from classic
MZ files. An appended MZ tail may contain overlay data, debug information or
other content; its presence alone does not establish a loadable overlay.

## Versioned memory experiments

The existing `patch` command can create a child version of the mapped LE
memory image. The parent stays intact, and the child retains the original
source container and inherited file metadata with an explicit warning.

This is **memory-only patching**. No inverse fixup processing or runnable LE
executable rewrite is implemented. Retained relocation metadata describes the
original loading transformation; it does not prove that patched memory can be
written back to the file at the same offset. `refresh-metadata` is currently
unsupported for LE. Reopening a project preserves its stored evidence; it does
not refresh a native player or launch a DOS process.

Runtime selectors, actual DOS/4GW placement, interrupts, device state and
gameplay execution need separate investigation and qualification. See the
[processor seam](PROCESSOR_MODULES.md) and [DOS debugger guide](DOSBOX_DEBUGGER.md)
for their distinct responsibilities.

## Encoding references

The format definitions and page layout were checked against Open Watcom
commit `5474be3542af05eee71be05fafc31bbe11f1415b`:

- [LE/LX header, object, page-map and fixup definitions](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/watcom/h/exeflat.h).
- [LE page-map and enumerated-data writer](https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/wl/c/loadflat.c).

These sources explain the encoding. The implemented subset and its explicit
refusals are defined by this module and the authored loader/workflow tests.
