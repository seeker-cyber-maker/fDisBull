# External save and resource files

An attached file is an immutable byte snapshot stored in the analysis database.
It has a name, original filename, kind, SHA-256 and author. Use it for save
files, resource tables or other data you want to inspect alongside the program.
The original path is no longer needed after attachment.

Attached identity is **version + file name + byte offset**. An offset of
`0x20` in `resource.dat` is distinct from virtual address `0x20`, offset
`0x20` in another attachment, and the executable container's disk offset
`0x20`. Attaching a file does not map it into native memory, decode it or
alter the executable's byte hash.

## Attach and interpret bytes

This example creates a small x86 image and an independent two-record data
file. The program is only decoded; none of these commands executes it.

```bash
python - <<'PY'
import json
from pathlib import Path

Path('program.bin').write_bytes(bytes.fromhex('8b00c3') + bytes(29) + bytes(8))
Path('resource.dat').write_bytes(bytes.fromhex('0300020007000400'))
Path('record.json').write_text(json.dumps({
    'kind': 'struct', 'size': 4, 'fields': [
        {'name': 'count', 'offset': 0, 'type': 'u16'},
        {'name': 'flags', 'offset': 2, 'type': 'u16'}]}))
Path('records.json').write_text(json.dumps({
    'kind': 'array', 'element': 'Record', 'count': 2}))
PY
fdisbull import program.bin analysis.fdb --arch x86 --bits 64 --base 0x1000
fdisbull analyze analysis.fdb
fdisbull attach-file analysis.fdb resource.dat --name resource.dat --kind resource
fdisbull files analysis.fdb
fdisbull file-bytes analysis.fdb resource.dat --offset 0 --size 8
fdisbull define-type analysis.fdb Record record.json
fdisbull define-type analysis.fdb Records records.json
fdisbull apply-file-type analysis.fdb resource.dat Records --offset 0 --name records
fdisbull file-data analysis.fdb resource.dat --offset 0 --max-items 16
```

The byte query returns `0300020007000400` and a bounded printable-ASCII view.
The typed query reports `records[0].count = 3`, `records[0].flags = 2`,
`records[1].count = 7` and `records[1].flags = 4`, each with its file offset,
type and original bytes. These neutral names are authored interpretations.
The returned layout is compact: `file-data` reports `layout_expanded: false`
and immediate field/element type names and sizes instead of recursively
repeating the registry. Leaf values remain bounded by `--max-items`.

The existing `define-type` command supplies scalar, array, struct and pointer
layouts; builtins include `u8/u16/u32/u64` and signed `i8/i16/i32/i64`.
Interpretation is little-endian. A pointer layout exposes its encoded value;
it does not produce a native target or follow a process pointer. Type
bindings must fit retained file bytes and may not overlap. Redefining a type
revalidates its file bindings atomically, including nested layouts and sizes.
`file-data --offset` selects a binding's start, rather than scanning for a
type at an arbitrary offset.

## Record an evidenced code-to-file relationship

`file-reference` records an analyst's statement about a decoded instruction.
It requires an exact stored instruction identity, an attached file, a bounded
file interval and a nonempty explanation. In the example above, the load at
`0x1000` has an unknown buffer address. The following records an explicit
**hypothesis**, which still requires independent loader or runtime evidence:

```bash
fdisbull file-reference analysis.fdb 0x1000 resource.dat 0 \
  --width 4 --count 2 --stride 4 --access read \
  --evidence 'Hypothesis: this load accesses either retained record; buffer identity remains unproven.'
fdisbull file-xrefs analysis.fdb resource.dat 0 --size 8
fdisbull disasm analysis.fdb --address 0x1000 --lines 2
fdisbull render-cfg analysis.fdb 0x1000 resource-load.svg
```

`width` is bytes per element; `count` and `stride` describe the set
`[offset + i * stride, offset + i * stride + width)` for
`0 <= i < count`. The default count is one and the default stride is width.
A query only matches those element intervals: gaps between strided elements
are not references. Access is an authored classification: `read`, `write`,
`read_write`, `address` or `unknown`.

For DOS sources, use `CS:IP` or `--cs` to choose the stored decode context.
Each reference retains source instruction bytes, context, file hash, evidence
and author. Disassembly and CFG/render output resolve current file-field
labels when queried, so revising a type or binding name updates their display.
The original instruction operands remain available.
Disassembly and CFG JSON preview at most eight file references per instruction,
with up to four locations each; `file_reference_summary` reports total,
returned and truncation. Display text includes at most three labels plus an
additional-reference count. Use `file-xrefs` for paginated reference records.

References report `runtime_observed: false` and one of these states:

| State | Meaning |
| --- | --- |
| `active` | The source bytes and exact stored instruction still match. This says nothing about whether the instruction executed. |
| `awaiting_decode` | Source bytes match, but that exact instruction is not currently stored. |
| `stale_bytes` | Source bytes changed; the earlier relationship needs review. |

`file-xrefs` reports these annotations separately from native memory xrefs.
`--page-offset` paginates reference records, while the positional offset and
`--size` select file bytes. Its default includes all three states;
`--active-only` excludes stale and awaiting-decode rows. Pagination counts
reference records, not individual elements. `matched_elements.first/last`
are inclusive indices; the first-16 location preview need not include the
elements that matched the queried interval.

It does not prove that a resource was loaded, recover a file-position cursor,
associate a heap allocation with file bytes, or infer an economic/game rule
from nearby numeric values.

## Share labels between files and native fields

Use `link-labels` when evidence connects an attached-file interval to native
memory or to the same fields in another attached file. It records corresponding
byte offsets rather than copying display text. Once linked, a field name set
at either end resolves through the entire chain when queried.

The following continues the small example above. Its correspondence is an
explicit demonstration declaration: the example program does not establish
that `resource.dat` was actually loaded into the retained data bytes at `0x1020`.

```bash
fdisbull link-labels analysis.fdb '{"file":"resource.dat","offset":0}' '{"address":"0x1020"}' \
  --size 8 --evidence 'Demonstration correspondence only; no runtime loading is claimed.'
fdisbull rename-file analysis.fdb resource.dat 0 record_count
fdisbull label-info analysis.fdb '{"address":"0x1020"}'
fdisbull rename analysis.fdb 0x1020 selected_count
fdisbull label-info analysis.fdb '{"file":"resource.dat","offset":0}'
```

Both `label-info` queries return the name most recently set at either endpoint.
For real analysis, link the field's data address, not the address of the
instruction that accesses it. `file-reference` already attaches the current file
field name to that instruction's operand display. Renaming the instruction
itself must not rename the referenced field.

For DinoPark, this example declares the user-reported eight-byte save-to-memory
mapping. Run it on a working copy with `DINOSG.000` attached and, for native fact
queries, the older DOS analysis refreshed. At the default load segment
`0x1000`, `4020:6fa6` identifies physical address `0x471a6`.

```bash
fdisbull attach-file dinopark.fdb DINOSG.000 --kind save
fdisbull link-labels dinopark.fdb '{"file":"DINOSG.000","offset":3872}' '{"address":"4020:6fa6"}' \
  --size 8 --evidence 'User-reported save offset 3872 to DS:6FA6 mapping; retain the independent save-diff and loader/runtime evidence.'
fdisbull rename-file dinopark.fdb DINOSG.000 3872 food_count
fdisbull label-info dinopark.fdb '{"address":"4020:6fa6"}'
fdisbull rename dinopark.fdb '4020:6fa8' restroom_count
fdisbull label-info dinopark.fdb '{"file":"DINOSG.000","offset":3874}'
```

The eight-byte range maps interior fields one-to-one: save offset 3874 and
`4020:6fa8` share a label independently of offset 3872 and `4020:6fa6`. Link a
second save's corresponding block with another `link-labels` call to extend the
same identity chain. A copied backup buffer can also be linked when its field
correspondence is supported by evidence. Different values in different save
snapshots remain different immutable bytes; the shared label states which
field they represent.

`label-info` shows the normalized endpoint, current name, explicit-name flag,
label author, `label_anchor`, corresponding members and every traversed link
with evidence. The anchor identifies a stored shared-name marker, not the
historical endpoint where the analyst chose the name.
Endpoints are exactly `{"file":NAME,"offset":OFFSET}` or `{"address":ADDRESS}`.
The methods support every existing native adapter and container; they do not
route on PE or x86 instructions. DOS data aliases resolve physically, and
source instruction CS identities stay separate.

A shared instance name appears in typed leaf `name`, native/file references,
xrefs, disassembly and CFG/image exports. Leaf `path` still describes the
structural layout. Changing a type's field name updates the structural fallback
when no explicit shared label has been set. Renaming one linked instance does
not change the type definition or every unlinked instance using that type.

Linking distinct explicit names raises an error instead of choosing silently.
Use `--name LABEL` to choose the starting field's shared name; resolve any
conflicting interior-field names separately before linking a whole block.
Invalid extents, offset cycles and validation-budget failures roll back the
operation. Repeating an active range link is idempotent; a new link after
removal receives a new ID.

All links report `runtime_observed: false`. A label correspondence does not
prove a pointer value, actual loader activity, execution, equal bytes or a
native control/data xref. Names resolve at query time, with the original
operands and evidence retained. An unchanged source fingerprint does not prove
that a changed upstream loader still supports an authored correspondence.

## Correct a mistaken label link

List the correspondence edges before removing one:

```bash
fdisbull label-links dinopark.fdb --include-removed --limit 200 --offset 0
```

Match the wrong edge by its file/native endpoints, range and original evidence,
then use its actual numeric `id` with `unlink-labels`. Do not assume the wrong
relationship has ID `1`. In this syntax example, replace `LINK_ID` with that
reviewed ID:

```bash
fdisbull unlink-labels dinopark.fdb LINK_ID \
  --reason 'Incorrect save-to-memory correspondence; retain this correction and its evidence.'
fdisbull label-info dinopark.fdb '{"file":"DINOSG.000","offset":3872}'
fdisbull label-info dinopark.fdb '{"address":"0x471a6"}'
fdisbull label-links dinopark.fdb --include-removed
```

For the DinoPark mapping above, the verified native address is `0x471a6`
(`4020:6fa6` at the stated load segment). The correct native address does not
identify which inventory record was mistaken; inspect the actual edge before
choosing an ID.

The command removes that entire range edge from active label resolution while
keeping the original edge and evidence. The receipt includes the inactive link,
removal reason/author/time, `removed`, left/right `before` and `after`
`label-info`, and `still_connected` with `connectivity_scope: "starting_endpoints"`.
The latter is true if another path still connects the two starting endpoints;
it makes no connectivity claim for every interior byte. Inspect any remaining mistaken paths and
remove their specific IDs separately. For an interior field, use `label-info`
on that field's own offset/address to inspect the resulting name.

Unlinking is a graph correction, not a rename undo. A shared name written by
0.8.1 has a storage anchor but no retained rename origin. Removal leaves that
name at its existing anchor; each detached component resolves its own remaining
names, native annotations and types. It does not copy the old shared name into
every detached field. Check the before/after names and explicitly rename a
remaining incorrect label if necessary.

No attached snapshots, types, source `file-reference` annotations, native name
annotations, bytes or analysis facts are deleted. Those instruction-to-file
annotations remain separate claims; inspect them independently if their
evidence also became invalid. Removed edges are excluded from graph traversal,
validation and active duplicate matching. Repeating removal of the same ID is
idempotent (`removed: false`) and retains the first removal metadata. Unknown
IDs are errors. A later corrected link gets a new ID; removed IDs are never
reused.

Use `--version` to select the version being corrected. Child versions inherit
removal history, and a correction in the child leaves the parent graph intact.
`label-links` defaults to active records; `--include-removed` reveals the full
retained history, with `--limit`/`--offset` for pagination.

## Versions and bounds

Each attachment is immutable under its name in a byte version. Attaching the
same name and content again is idempotent; changed content requires another
name. `kind` is descriptive metadata, not a parser or an executable format.
Names are single identifiers rather than paths: empty names, separators,
control characters, `.` and `..` are rejected.

A native `patch` creates a child version that inherits attachments, file type
bindings, authored references, label links, removal history and shared names. Child annotation
changes do not modify the parent. References are checked against the child's current source bytes and
decode state; inherited data does not make a stale instruction relationship
current. Select earlier state with the usual `--version` argument.

Attachments are limited to 64 MiB per file and in aggregate per version. `files` paginates
metadata without returning blobs. `file-bytes` defaults to 64 bytes, allows
at most 65,536 bytes per request, and marks partial end-of-file reads. Typed
queries have an explicit `max_items` budget and truncation flag. References
allow at most 4,096 elements, with bounded widths/strides and no interval past
the attached file's end. Reference locations are previewed at most 16 at a
time in `file-xrefs`; `matched_elements` still identifies the matching index range.

## Older DOS projects

Before using the packaged historical DinoPark project or another older MZ
analysis for memory-access, CFG, native-xref, call or derived-function queries,
run the explicit pointer-state migration:

```bash
fdisbull refresh-dos-state examples/dinopark.fdb --max-instructions 10000
fdisbull analyze examples/dinopark.fdb --max-instructions 100000
```

Repeat `analyze` until native work is stable, then use `auto-analyze` for
derived results. `analysis-status` reports `facts_stale: true` for legacy
pointer facts until refreshed. An old shallow `LES`/`LDS` rule read initial descriptor bytes
as current pointers despite possible writes; those inferences could make a
heap/resource access appear to have a false exact memory address. Initial
zero or nonzero descriptors do not establish a runtime file-buffer binding.

`refresh-dos-state` resets native/derived facts and resumes bounded native
analysis, leaving derived jobs queued for `auto-analyze`. It preserves bytes, versions,
authored annotations/types, attached snapshots and authored file-reference
evidence. It retains explicit seed addresses while dropping inherited register
assumptions for revalidation. Raw disassembly remains available before refresh
with old native references hidden. File links remain authored claims and do
not become proven runtime mappings through migration. This repair is separate
from `refresh-facts` and does not affect ELF, PE or Mach-O projects.

Label links allow at most 4096 retained range records per version, including
removed history, each 1 byte–1 MiB; resolving one
field is bounded at 256 corresponding locations. Link validation is bounded at
100,000 location visits and 10,000 native annotations. A limit failure is an
error rather than a silently truncated identity chain.

See [API.md](API.md) for Python/JSON methods and pagination parameters.
