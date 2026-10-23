# Agent protocol

## Project debugger (0.10.0)

The same foreground `serve` process owns `debug-launch`, `debug-status`, `debug-registers`, `debug-breakpoint`, `debug-delete-breakpoint`, `debug-click`, `debug-run`, `debug-screenshot`, `debug-trace`, and `debug-stop`. Live requests carry the `run` ID returned by launch. `debug-run` accepts `guest_ms`, `fast_forward`, and an independent host `timeout_ms`; its `outcome` distinguishes a breakpoint, reached guest time, and timeout. Images/traces are retained in the `.fdb` and attached to the immutable launch version. `debug-runs`, `debug-artifacts`, and `debug-export` also work offline after restart. Full parameters, address verification rules, Python API, and examples are in [DOSBOX_DEBUGGER.md](DOSBOX_DEBUGGER.md).

`analysis-status` takes `project` and optional `version`. It returns current `stable`, pending code/data/seeds/segment scans, phase state, DOS seed-state counts and issue count without advancing analysis. `status` and disassembly snapshots embed the same summary; new image exports show it. A fixed point does not prove coverage. See [QUERYING.md](QUERYING.md).

`calls` takes `project`, optional `version`, `limit`, `offset`, and `kind` (`all`, `function`, `library`, `unresolved`). It groups stored call targets with shared names, module/import aliases where known, exact incoming call sites, evidence and current analysis state. Target groups paginate; each includes total call-site count and at most 100 sites with an explicit truncation flag. Use `xrefs` on the target for further references. DOS target CS contexts remain distinct. Declared import slots and proven stub aliases identify library requests across PE, ELF and Mach-O; `import_call` xrefs do not resolve the external provider. Compiled-in DOS helper names are not inferred. Unresolved indirect calls are kept separately. This is a static index, not a runtime call trace or a complete call graph.

`fdisbull serve --project FILE.fdb` reads UTF-8 JSON lines and writes one response per line. `fdisbull request '{...}'` performs one request. This is a local protocol, not MCP or JSON-RPC; there is no network server.

Request: `{"id":"caller-chosen","method":"status","params":{}}`.
Response: `{"id":"caller-chosen","ok":true,"result":{...}}` or `{"id":"caller-chosen","ok":false,"error":{"type":"ValueError","message":"..."}}`.

Include `project` in params when there is no session default, or to override it. `identify`, `inspect`, `decoder-check`, `managed` with a `path`, and `help` need no project. Paths are local to the process. Addresses accept integers or integer strings; use `0x...` strings to preserve 64-bit precision. Public address fields are hexadecimal strings; file offsets, sizes, counts and version IDs are integers. Non-finite JSON numbers are rejected.

| Method | Required params beyond project | Optional params |
| --- | --- | --- |
| identify | path; no project needed | |
| inspect | path; no project needed | slice_arch (`x86`, `x86_64`, `arm64`), image (`auto`, `pe`, `mz`) |
| import | path | arch, bits, base, entry, module, load_segment (MZ; default `0x1000`), slice_arch, image |
| analyze-module | path, project (new target) | export (name, integer ordinal or `#ordinal`), entry, max_instructions, slice_arch, image |
| managed | path **or** project | token (MethodDef), max_instructions (with token), version (project only) |
| decoder-check | data (hex bytes), bits; no project needed | address, arch (`x86`), scan_offsets, max_candidates |
| info | | version |
| header | | version |
| sections / imports / exports / strings / libraries / relocations | | version, limit (1–10,000), offset |
| linkage | | version |
| refresh-metadata | | version |
| status | | version |
| analyze | | version, start, max_instructions (1–1,000,000; default 10,000); MZ: cs, ds, es, ss |
| refresh-facts | | version |
| refresh-dos-state | MZ project | version, max_instructions (10,000) |
| memory-accesses | address | size (1–1 MiB), access, include_unresolved, version, limit, offset |
| cfg | address (exact instruction start) | version, cs, max_instructions, highlights |
| render-cfg | address, output (`.svg`) | same as cfg |
| functions | | version, limit, offset |
| locate | address | version, cs (MZ) |
| function-patterns | | version, limit, offset, scan_unexplored |
| items / queue | | version, limit, offset |
| disasm | | version, address, lines (1–500); MZ: cs |
| xrefs | address | version, direction (`to`/`from`), limit; MZ: cs |
| rename | address, name | version, author |
| comment | address, text | version, author |
| represent | address, representation | size, author, version, max_instructions, defer |
| recover-imports | module_exports **or** export_map | candidate_slots, version, max_slots (default 4096), gap_limit (default 10) |
| patch | address, data (hex bytes) | version (parent), label, origin |
| versions | | |
| issues | | version, limit |
| render | output | version, address, lines (1–200), format (`png`/`svg`); MZ: cs |
| segments | MZ project | version |
| code-regions | MZ project | version |
| help | no project needed | |

`limit` defaults to 200 for paginated lists. Information lists return `items`, `total`, `offset`, `has_more` and warnings. `items` and `queue` return arrays. `info` returns header/counts/warnings. `header.valid` means recognized header extents fit the file, not that the program can execute. A disk `file_offset` is never presented as a virtual address. Unknown import bindings and unmapped string addresses are null.

## External files and authored file references (0.8.2)

All methods here take `project` and optional `version` (default: latest).
Attached identity is version + file name + byte offset, independent of native
addresses and executable container offsets. File offsets in JSON are
nonnegative integers. No attachment becomes an executable mapping or analysis
seed.

| CLI / JSON method | Python `Project` method | Required params beyond project | Optional params |
| --- | --- | --- | --- |
| `attach-file` | `attach_file` | `path` | `name` (source basename), `kind` (`data`), `author` (`agent`) |
| `files` | `external_files` | — | `limit` (200; 1–10,000), `offset` (row pagination) |
| `file-bytes` | `file_bytes` | `name` | `offset` (0), `size` (64; 0–65,536) |
| `apply-file-type` | `apply_file_type` | `file`, `type_name` | `offset` (0), `name`, `author` |
| `file-data` | `typed_file` | `file` | `offset` (exact binding start; 0), `max_items` (256; 1–4096) |
| `file-reference` | `file_reference` | `address`, `file`, `evidence` | `offset` (0), `width` (1), `count` (1), `stride` (width), `access` (`unknown`), `cs`, `author` |
| `file-xrefs` | `file_xrefs` | `file` | `offset` (0), `size` (1), `limit` (200), `page_offset` (0), `include_stale` (true) |

CLI `file-reference PROJECT ADDRESS FILE OFFSET` and
`file-xrefs PROJECT FILE OFFSET` require the file offset positionally. Their
JSON/Python methods default it to zero. CLI `file-xrefs --page-offset N`
paginates reference records; it does not move the queried file interval.
`--active-only` sets `include_stale: false` and excludes both stale and
awaiting-decode records.

`attach-file` retains full bytes, SHA-256, basename, kind and author in SQLite.
It accepts a regular file, up to 64 MiB per file and 64 MiB aggregate per
version. Names are 1–256 characters without path separators or control
characters; blank names, `.` and `..` are rejected. `kind` is an identifier
used as descriptive metadata. The same name/hash is idempotent; a different
hash under that name is rejected. The original path is not needed afterward.
Child native byte versions inherit attachments, file bindings and authored
references while retaining the parent's state.

`files` returns metadata-only `items`, `total`, `total_bytes`, `limit`,
`offset` and `truncated`; it does not return file blobs. `file-bytes` returns
bounded `bytes` (hex), printable `ascii`, `file_size`, `requested_size`, actual
`size`, `sha256`, `eof`, `complete` and `truncated`. A read may clip at EOF;
an offset past EOF is rejected. `complete` means the response contains the
entire file from offset zero, not merely the requested range.

`apply-file-type` uses the shared explicit `define-type` registry. Its binding
must fit the attachment and may not overlap another binding in that file.
`typed_file` returns a compact layout, binding, scalar/pointer leaf `items`, SHA-256,
`byte_order: "little"`, and truncation/budget status. Leaves carry `file`,
`file_offset`, structural field `path`, current canonical `name`, type, original bytes and interpreted value.
Pointers remain encoded values; no native or file target is inferred. Type
revisions revalidate dependent file binding extents and overlaps atomically.
`file-data` reports `layout_expanded: false`; struct layout fields identify
their immediate type names and sizes, and array elements identify name/kind/size
without recursively embedding definitions. `apply-file-type` also returns a
compact layout. The shared `types` method remains the registry query.

`file-reference` requires an exact stored source instruction, including DOS
CS identity where applicable, and nonblank evidence of at most 4096
characters. It describes `count` intervals
`[offset + i*stride, offset + i*stride + width)`. Count is 1–4096; width and
stride are 1–1 MiB; the whole set must fit the attachment. `access` is an
authored classification (`read`, `write`, `read_write`, `address`, `unknown`),
not a decoded operation or observed I/O result. Source bytes, file hash,
context, author and evidence remain attached to the claim.

`file-xrefs` requires the complete query interval to fit retained file bytes;
it does not clip. It matches exact strided intervals, excluding gaps, and
returns `total` reference records, `page_offset` and `has_more`. Each match
has inclusive `matched_elements.first/last` indices. `locations` previews
only the first 16 declared elements, which may differ from the query's
matching elements. Current file-field names resolve in references,
disassembly and CFG/render output without changing raw instruction operands.
Disassembly/CFG instruction records preview at most eight `file_references`,
each with at most four `locations`, and include `file_reference_summary`
(`total`, `returned`, `truncated`). Display text uses at most three labels
plus an additional-reference count. Use paginated `file-xrefs` for the full
reference list and its 16-element previews.

References report `active`, `stale` and `state`: `active` requires matching
current source bytes and an exact stored instruction; `awaiting_decode`
means matching bytes without that stored decode; `stale_bytes` means bytes
changed. All report `runtime_observed: false`. These are authored file links,
separate from native xrefs, recovered I/O, heap bindings or control-flow
edges. A current annotation still needs independent evidence for its meaning.

```json
{"id":60,"method":"attach-file","params":{"project":"analysis.fdb","path":"resource.dat","name":"resource.dat","kind":"resource","author":"analyst"}}
{"id":61,"method":"files","params":{"project":"analysis.fdb","limit":20,"offset":0}}
{"id":62,"method":"file-bytes","params":{"project":"analysis.fdb","name":"resource.dat","offset":0,"size":8}}
{"id":63,"method":"apply-file-type","params":{"project":"analysis.fdb","file":"resource.dat","type_name":"Record","offset":0,"name":"record"}}
{"id":64,"method":"file-data","params":{"project":"analysis.fdb","file":"resource.dat","offset":0,"max_items":16}}
{"id":65,"method":"file-reference","params":{"project":"analysis.fdb","address":"0x1000","file":"resource.dat","offset":0,"width":4,"access":"read","evidence":"Analyst hypothesis; loaded buffer identity still requires verification."}}
{"id":66,"method":"file-xrefs","params":{"project":"analysis.fdb","file":"resource.dat","offset":0,"size":8,"limit":20,"page_offset":0,"include_stale":false}}
```

See [EXTERNAL_FILES.md](EXTERNAL_FILES.md) for a runnable typed-data example.

## Bidirectional field labels (0.8.2)

The three label-resolution methods share labels across explicit file/memory
correspondences. All accept `project` and optional `version` (latest by default). An endpoint is
exactly one of `{"file":"save.dat","offset":3872}` or
`{"address":"0x471a6"}`. File offsets accept nonnegative integers or integer
strings; native addresses also accept DOS `segment:offset` syntax for MZ.
The entire linked interval must fit an attachment or one native mapped region.

| CLI / JSON method | Python `Project` method | Required params beyond project | Optional params |
| --- | --- | --- | --- |
| `link-labels` | `link_labels` | `left`, `right`, `evidence` | `size` (1), `name`, `author` (`agent`) |
| `rename-file` | `rename_file` | `file`, `offset`, `name` | `author` (`agent`) |
| `label-info` | `label_info` | `endpoint` | — |

CLI syntax is `link-labels PROJECT LEFT_JSON RIGHT_JSON --size N --evidence TEXT
[--name LABEL]`, `rename-file PROJECT FILE OFFSET NAME`, and `label-info PROJECT
ENDPOINT_JSON`. Pass each endpoint as one quoted JSON argument. The existing
`rename PROJECT ADDRESS NAME` command renames a native endpoint and its linked
file fields. To rename a field from a code view, select the reference's native
target address or file offset; renaming the source instruction remains a
separate operation.

`link-labels` declares a one-to-one byte-offset mapping over `size` bytes. It
supports file-to-file, file-to-memory and memory-to-memory links. Links compose
transitively; a link over an eight-byte counter block also connects its interior
fields at offsets `+2`, `+4` and `+6`. DOS native endpoints use physical address
identity, while instruction-reference source CS contexts remain separate.
Renaming an instance field does not rewrite its type definition or rename
unlinked instances of that type.

Explicit names take precedence over structural names. If no explicit shared
name exists, the current type path supplies the display name, so later type
field revisions remain visible. A link between conflicting explicit names is
rejected atomically. `name` selects a shared name for the linked starting field;
conflicts at other interior fields must be resolved separately. Duplicate active
mappings in either direction are idempotent; supplying `name` can still rename
the starting field. Recreating a removed mapping makes a new link ID. Contradictory shifted offset cycles are rejected.

All three methods return the queried `version`, normalized `endpoint`, current
`name`, `explicit`, `label_author`, `label_anchor`, corresponding `members`, and `links` with
IDs, endpoint ranges, size, evidence and author. `runtime_observed` is always
false. `label_anchor` identifies the stored shared-name marker, or is null when
there is none; it is not the historical endpoint at which the name was chosen.
Typed file and native leaf values retain structural `path` and expose the
current canonical `name`; the shared name also resolves in operand references,
file references, native xrefs, disassembly and CFG/image output. Raw numeric
operands and bytes are preserved. Queries resolve names dynamically rather than
rewriting decoded or cached semantic facts.

These are authored field correspondences. They do not establish equal values,
live pointer/register state, runtime file loading, native xrefs or execution.
Existing `file-reference` remains an instruction-to-file relationship and never
equates that instruction's identity with the field it accesses. A stale source
instruction reference stays stale even when its field still has a shared label.
A byte patch copies label interpretations into the child; child renames leave
parent labels intact. Inherited interpretations still require evidence review
after changes to relevant loader behavior.

Limits are 1 byte–1 MiB per range, 4096 retained link records per version
(including removed history), 256 corresponding locations
per resolved component, and 100,000 location visits per link-validation pass.
Validation also bounds native annotation inspection at 10,000 rows. Endpoint,
cycle, conflict or budget failures roll back the link operation. Labels contain
1–256 characters without control characters; evidence contains 1–4096 nonblank
characters.

```json
{"id":70,"method":"link-labels","params":{"project":"dinopark.fdb","left":{"file":"DINOSG.000","offset":3872},"right":{"address":"4020:6fa6"},"size":8,"evidence":"Analyst-declared save-to-memory mapping; attach the independent loader/runtime evidence."}}
{"id":71,"method":"rename-file","params":{"project":"dinopark.fdb","file":"DINOSG.000","offset":3872,"name":"food_count","author":"analyst"}}
{"id":72,"method":"rename","params":{"project":"dinopark.fdb","address":"4020:6fa8","name":"restroom_count","author":"analyst"}}
{"id":73,"method":"label-info","params":{"project":"dinopark.fdb","endpoint":{"file":"DINOSG.000","offset":3874}}}
```

The example uses the user-reported DinoPark mapping at load segment `0x1000`;
recording it is not independent verification of that mapping or field meaning.

## Inspect and remove label links (0.8.2)

| CLI / JSON method | Python `Project` method | Required params beyond project | Optional params |
| --- | --- | --- | --- |
| `label-links` | `label_links` | — | `version`, `include_removed` (false), `limit` (200; 1–10,000), `offset` (0) |
| `unlink-labels` | `unlink_labels` | `link_id`, `reason` | `version`, `author` (`agent`) |

CLI syntax is `label-links PROJECT [--include-removed] [--limit N] [--offset N]`
and `unlink-labels PROJECT LINK_ID --reason TEXT [--author NAME]`. Both accept
`--version`. `LINK_ID` is the actual numeric inventory ID, not an endpoint or
an index in the displayed page. Inspect the inventory before choosing a wrong
link; IDs must not be guessed or assumed to start at `1` for the relationship
being corrected.

`label-links` returns `version`, `items`, `total`, `limit`, `offset`, `has_more`
and `include_removed`. Each item retains `id`, `left`, `right`, `size`, original
`evidence` and `author`, `active`, and `removal`. `removal` is null for an active
link or an object containing the removal `reason`, `author` and `created`
timestamp. Default inventory results contain active links; `include_removed`
also exposes retained inactive records. Pagination applies to the selected
inventory, not to file-byte intervals.

`unlink-labels` deactivates the whole selected range edge in the chosen version.
It retains that edge and its original evidence, and records the removal reason,
author and timestamp. Removed edges no longer participate in label resolution,
active duplicate detection or link validation. IDs are never reused: relinking
the same endpoints creates a new ID, while all historical records still count
toward the 4096-record per-version quota. An unknown link ID raises an error.
Retrying an already removed ID returns `removed: false` and preserves the first
removal record. The reason must be a nonblank string of 1–4096 characters;
`link_id` must be a positive integer.

The removal receipt contains:

| Field | Meaning |
| --- | --- |
| `version` | Version whose active correspondence graph was changed. |
| `removed` | True only when this call first removed the edge. |
| `link` | The retained link, with `active: false` and removal metadata. |
| `left.before` / `left.after` | `label-info` for the left starting endpoint before and after this call. |
| `right.before` / `right.after` | Equivalent before/after information for the right starting endpoint. |
| `still_connected` | An alternate active path still connects the two starting endpoints after removal. |
| `connectivity_scope` | `"starting_endpoints"`; connectivity does not describe every interior byte of the range. |

Removing one edge may leave an alternate path. Use its ID and evidence to
identify any additional mistaken edges; removal does not automatically delete
other paths. To inspect an interior field of a removed block, query that field
with `label-info` separately. A child byte version inherits the current removal
history; further child removals do not affect the parent.

This is a graph correction, not a rename undo. Existing 0.8.1 shared-name records
have a storage anchor without recorded rename origin. Removing a link leaves
that name at its existing anchor; detached components recompute labels from
their own remaining shared names, authored native annotations and structural
types. The old shared name is not copied into every detached endpoint. Inspect
the receipt's actual names and `label_anchor`, then explicitly rename a detached
field if needed.
Unlinking deletes no attachments, type definitions/bindings, source
`file-reference` annotations, authored native annotations, bytes or analysis
facts.

```json
{"id":74,"method":"label-links","params":{"project":"dinopark.fdb","include_removed":true,"limit":200,"offset":0}}
```

After choosing a specific wrong ID from that result, submit `unlink-labels`
with `link_id`, a concrete `reason`, and the intended `version`. The verified
native endpoint `4020:6fa6` is `0x471a6`; a mistaken correspondence must be
removed before a corrected link can safely propagate names to that endpoint.

## Refresh legacy DOS pointer state (0.8)

`refresh-dos-state` maps to Python
`Project.refresh_dos_state(version=None, max_instructions=10000)`. It is the
explicit migration for MZ analyses created before DOS pointer revision 2.
The earlier shallow `LES`/`LDS` rule could infer current pointers from immutable
initial descriptor bytes despite possible writes. Both zero and nonzero
snapshot pointer propagation are withdrawn; resource buffer/heap locations
remain unresolved without independent evidence.

An affected project with stored instructions reports `facts_stale: true`
in `analysis-status` (also `status.analysis`) and `stable: false`. CFG,
memory-access, call/call-effect, native-xref and function-analysis queries, ordinary `analyze`, and
`refresh-facts` require this refresh instead of returning the old facts.
Raw `disasm` keeps stored instruction bytes and authored file links available
with `stored_facts_stale: true` while hiding obsolete native references. Opening a project or making a
read-only query never silently rebuilds its analysis.

The refresh resets native/derived facts and resumes native analysis under
current rules within the instruction budget; derived jobs are requeued for
`auto-analyze`. It preserves source/mapped bytes, version identities,
authored names/comments/types, attachments and file-reference evidence.
Explicit seed addresses are retained for revalidation, while inherited
register assumptions are discarded. Continue with bounded `analyze` calls
until native work stabilizes, then `auto-analyze` for derived work; a budget
stop is not a fixed point. This DOS migration does not affect ELF, PE or
Mach-O projects and is distinct from `refresh-metadata` or `refresh-facts`.

The receipt includes `version`, `previous_dos_pointer_revision`,
`dos_pointer_revision`, `restored_user_roots`, the native `analysis` receipt,
live `status`/`advanced` queues and retained `sha256`/`source_sha256` values.
Native stability in the nested receipt does not clear pending derived work.

```json
{"id":67,"method":"refresh-dos-state","params":{"project":"dinopark.fdb","max_instructions":10000}}
```

## Native image selection and linkage (0.7)

`inspect` inventories an unselected universal Mach-O container. `import` and
`analyze-module` require an explicit `slice_arch` for FAT input; `x86` selects
32-bit x86, `x86_64` selects 64-bit x86 and `arm64` selects ARM64. A selector on
a thin file must match. Missing or subtype-ambiguous matches are errors; the
host architecture is never a selection rule. `arch` remains the separate raw
mode override and cannot be combined with a container selector.

`image: "auto"` is the default. A PE-bearing MZ file selects PE; `image: "pe"`
requires that native view. `image: "mz"` explicitly selects its declared DOS
load image, subject to the complete ordinary MZ extent, relocation and entry
checks. Inspection includes `image_views` with availability and validation
errors. PE and DOS views belong to separate projects/decode contexts. The
loader does not guess a DOS stub length from `e_lfanew`.

```json
{"id":50,"method":"inspect","params":{"path":"UniversalBinary","slice_arch":"arm64"}}
{"id":51,"method":"import","params":{"path":"UniversalBinary","project":"mac.fdb","slice_arch":"x86_64"}}
{"id":52,"method":"analyze-module","params":{"path":"universal.dylib","project":"module.fdb","slice_arch":"arm64"}}
{"id":53,"method":"import","params":{"path":"program.exe","project":"dos-view.fdb","image":"mz","load_segment":4096}}
{"id":54,"method":"inspect","params":{"path":"program.exe","image":"pe"}}
```

Projects retain the complete original container, including unselected slices.
Selected-slice metadata distinguishes container and slice hashes; public file
offsets and patch translations refer to the original container. Virtual
addresses remain the selected image's preferred static VAs. No ELF runtime
relocation, Mach-O slide, dyld resolution or native execution occurs.

`libraries` lists declared dependency names/ordinals; `relocations` retains
format-specific symbol, type, slot, addend and source evidence. `linkage`
returns format-specific records: an ELF object includes `needed`, interpreter,
RPATH/RUNPATH and native-validated PLT stubs; Mach-O supplies dyld/indirect-symbol
linkage records. Consumers should not assume identical `linkage` shapes.
Python callers use `Project.information(topic="libraries", ...)`, with
`"relocations"` or `"linkage"` for the other information operations.

ELF imports distinguish relocation-backed GOT slots from unresolved symbols,
COPY storage and TLS metadata. A slot's `address` is not the provider function
address. `required_module`/`module` is assigned only with a consistent symbol
version requirement; `module_candidates` remains non-binding otherwise.
Versioned aliases retain their version/hidden flag. Dynamic export types keep
functions, objects, IFUNC resolvers, TLS and absolute values distinct.

Mach-O imports retain load-command ordinals/scopes, weak/lazy/chained binding
provenance and exact indirect-symbol stub aliases. Unsupported or truncated
binding cases remain warned/unresolved. Lazy and chained pointer bytes are not
runtime code addresses; reexports and data/thread-local/absolute exports retain
their distinct kinds. No dependency or resolver is loaded.

`refresh-metadata` reparses retained ELF/Mach-O/PE file bytes, rebuilds the
metadata symbol/stub index and invalidates dependent derived jobs. It returns
counts, metadata revision, warnings and `invalidated_tasks`. Mappings, byte
versions and authored names/comments remain intact; missing original bytes
require a new import. Resume with `auto-analyze`. This operation differs from
`refresh-facts`, which backfills facts for already stored instructions.

```json
{"id":55,"method":"libraries","params":{"project":"mac.fdb"}}
{"id":56,"method":"relocations","params":{"project":"mac.fdb","limit":50}}
{"id":57,"method":"linkage","params":{"project":"mac.fdb"}}
{"id":58,"method":"refresh-metadata","params":{"project":"mac.fdb"}}
```

See [PLATFORMS.md](PLATFORMS.md) for practical commands and platform limits.

## Analysis and shared presentation

One selected image/architecture/bitness belongs to each project, even when the retained source container contains other images. Non-DOS projects use a flat little-endian decode context. MZ instruction facts add the actual CS (`x86:16:little:cs=38ff`); names/comments/representations remain shared by physical address within their byte version. `version` defaults to the newest ID.

`analyze` prioritizes recursive entry traversal, mapped data investigations, then deferred symbol/export seeds. It reports `decoded`, `attempted`, `data_processed`, `new_facts`, `pending_code`, `pending_data`, `pending`, `entry_complete`, `passes`, `stable` and `budget_exhausted`. The budget counts work attempts across code and data. `pending` can include an unscheduled later seed phase. Resume while unstable; an empty implemented work queue does not establish complete disassembly.

`queue` combines code and data tasks with reasons, states and details. `items` exposes investigated data values, evidence sources and shared presentations. Uncorroborated pointer values remain candidates; actual indirect control-flow evidence can promote their targets. Function records remain candidate entries, not proven boundaries.

`disasm` returns stored rows, original numeric `operands`, structured `references` and address-resolved `display_operands`. Each reference carries operand index, role, target, width, shared name and representation. Changing a target name changes callers' subsequent query/render output. `render` uses that same stored snapshot, does not trigger analysis, and rejects overwriting an active database or its sidecars.

`represent` defines one mapped range as `code`, `byte`, `word`, `dword`, `qword`, `pointer`, `ascii`, `utf-16le` or `unexplored`. `size` is bytes, 1–4096; strings require it explicitly, UTF-16 requires an even size, and numeric types require their natural width. `code` and `unexplored` default to one byte. Distinct explicit definitions may not overlap. The operation retracts affected dependency-indexed routine slices, falling back to a full reset if instruction coverage is incomplete, and reanalyzes within `max_instructions`; `defer: true` instead returns `analysis: null` and leaves work queued. Names/comments and byte identity survive. Explicit unexplored ranges block automatic code/data work; change the same definition to `code` before analyzing them. Check the nested receipt when analysis runs.

## Byte spans and function evidence

```json
{"id":20,"method":"locate","params":{"project":"dinopark.fdb","address":"38ff:5401"}}
{"id":21,"method":"function-patterns","params":{"project":"dinopark.fdb","scan_unexplored":true,"limit":30}}
{"id":22,"method":"represent","params":{"project":"sample.fdb","address":"0x401000","representation":"unexplored","size":32,"defer":true}}
```

`locate` returns mapping/classification, the actual byte, shared presentation, all containing instruction/data/definition spans, CS context and overlap indicators. A span's `position` is `begin`, `part`, `end` or `single`; `byte_offset` is relative to its start. Its `end` is inclusive and `end_exclusive` is the address after it. A single-byte span is `single`. This query reads stored ownership and never decodes new instructions. An explicit MZ CS filters instruction interpretations while physical data definitions stay shared.

`function-patterns` returns paginated `items`, `total`, `offset`, `has_more`, `scan` and warnings. Evidence contains `kind` (`prologue`, `epilogue`, `return`, `tail_jump`), pattern, candidate status, qualification, instruction bytes, context and source. A known candidate entry is reported separately from a pattern match. Returns can be shared/interior exits; jumps can be dispatches or internal branches. Neither proves a full function boundary.

`scan_unexplored` adds bounded native pattern proposals from unclassified executable-mapping bytes, excluding stored instructions/data and explicit definitions. It reports scan limits/partial coverage; raw DOS contexts remain candidates. It does not modify facts or queue work. Select an appropriate representation and call `analyze` when promoting a proposal for investigation.

## Explicit module analysis

`analyze-module` creates a new project using module mode and one analysis budget. Choose `export` or `entry`, never both. A name or ordinal must resolve uniquely to executable local bytes; forwarded exports are rejected. An explicit entry is a preferred virtual address, not a disk offset/RVA. With no root selection, available entry/export seeds remain eligible. The result includes selected export, analysis roots, receipt, status and scope; resume with ordinary `analyze` on that project. Selected roots persist through resets. Imported dependencies are not loaded or resolved, and no initializer executes.

```json
{"id":30,"method":"analyze-module","params":{"path":"library.dll","project":"library.fdb","export":"#7","max_instructions":10000}}
```

## Managed assembly and decoder proposals

`managed` inspects a local assembly (`path`) or retained source bytes of a project/version (`project`). With no token, it returns recognition status, CLR/metadata summaries and bounded method records. With a nonzero MethodDef token (`0x06xxxxxx`), it decodes that method's real CIL. Install `fdisbull[managed]` for dnfile 0.18.0/dncil 1.0.2; dependency-free recognition remains available and reports missing optional dependencies explicitly. The CIL instruction budget is 1–100,000, default 10,000.

```json
{"id":31,"method":"managed","params":{"path":"assembly.dll"}}
{"id":32,"method":"managed","params":{"path":"assembly.dll","token":"0x06000001","max_instructions":1000}}
{"id":33,"method":"managed","params":{"project":"assembly.fdb","token":"0x06000001","version":1}}
{"id":34,"method":"decoder-check","params":{"data":"0f0dc0","bits":64,"scan_offsets":true}}
```

CIL addresses combine a method token and method-local `IL_` offset; RVA/file offsets are separate fields. Token references retain names or unresolved identities; branch targets report whether they lie in the body and at known instruction starts. `complete` describes linear method decoding, not type/stack verification, EH recovery or source reconstruction. Invalid and budget-limited bodies remain explicit. Native/runtime/abstract/PInvoke methods without a CIL body are rejected for CIL decoding. CLR recognition guards pure-IL/invalid payloads from accidental native entry analysis; mixed native/managed and precompiled/NativeAOT cases keep their qualifications. This does not establish actual Godot ALD assembly coverage.

`decoder-check` accepts immutable input represented by 1–4096 hex-decoded bytes and x86 mode 16/32/64. The CLI defaults to 64 bits. It compares one start or starts 0–14, limited by `max_candidates` (1–16) and available bytes. Results include exact bytes, mode/address, engine versions/options, per-engine validity/length/text and separate comparison categories. Formatting/alias differences are not semantic disagreements. No byte execution, CPU observation, fact insertion or authoritative decoder selection occurs. ARM64 is rejected because two independent backends are not present. See [DECODER_RESEARCH.md](DECODER_RESEARCH.md) for the research boundary and [WINE_DEBUGGER.md](WINE_DEBUGGER.md) for the separate proposed execution backend.

## Classic DOS MZ

Automatic import recognizes classic MZ; do not pass `arch` to obtain segmented loading. `load_segment` selects the relocated image base and defaults to `0x1000`. The loader applies segment-word relocations, maps the module excluding its header/overlay, and adds deterministic zero-filled paragraph padding/minimum allocation. It records initial CS:IP and SS:SP. No PSP bytes, maximum-allocation heap, A20 wrap or DOS service execution are fabricated.

MZ addresses accept ordinary linear values or hexadecimal `CS:IP`, for example `38ff:53fd`. Plain `0x3e3ed` plus `cs: 14591` selects the same decode context. CLI register options use integer notation, for example `--cs 0x38ff --ds 0x4020`; JSON register overrides can be integers. Segment overrides apply only to MZ analysis; `cs` also selects MZ disassembly/xref/render views. Conflicting `cs` and `CS:IP` are rejected.

```json
{"id":10,"method":"analyze","params":{"project":"dinopark.fdb","start":"38ff:53fd","ds":16416,"max_instructions":10000}}
{"id":11,"method":"disasm","params":{"project":"dinopark.fdb","address":"38ff:53fd","lines":35}}
{"id":12,"method":"segments","params":{"project":"dinopark.fdb"}}
{"id":13,"method":"code-regions","params":{"project":"dinopark.fdb"}}
```

The DS value above is DinoPark-specific at load segment `0x1000`. Initial recursive traversal precedes deferred relocation-backed far-call candidates. Observed data segments can contribute relocated callback-pointer candidates; paired literal far-pointer stores can add further candidates. Relocations alone do not prove code. Reports retain seed provenance and unresolved state.

MZ `analyze` additionally reports `pending_seeds`, `pending_segment_scans` and `assumptions`. A newly corroborated indirect-call CS can invalidate prior data-pointer scans; rescans consume work budget and count as pending work. A budget stop is never called stable. The calling convention preserves DS/SS/BP/SP on call fallthrough while general registers/ES become unknown; deferred seeds may assume startup DS or a unique observed data segment. Unknown indirect targets, dynamic pointer writes and runtime-dependent state remain partial even after implemented queues drain.

`segments` returns selectors, CS contexts, inferred base/end, roles, sources and instruction counts. `bounds_inferred: true` distinguishes these candidates from format-defined sections. `code-regions` returns contiguous decoded runs per CS, with exclusive ends and `classification: decoded instruction run`; it does not imply the gaps or the entire segment are code. Both commands require an MZ project. The JSON method name is literally `code-regions`.

MZ disassembly includes physical `address`, `cs`, `ip`, `segmented_address`, context, alternative stored contexts, register assumptions and warnings. Without explicit CS, a deterministic stored context may be selected; a nearest-row view warns if the requested physical address is not stored. Explicit `CS:IP`/`cs` requires an exact stored instruction start; otherwise it returns an empty warned view without decoding new bytes. Xrefs retain source and target CS when known. Physical aliases share labels and explicit representations, not instruction-context identity.

The MZ project `header` supplies DOS fixed fields, relocation count, selected load segment and initial CS:IP. Standalone identification is byte-based; a successful header parse is not execution evidence. `sections` reports the unclassified DOS load-module mapping; use `segments`/`code-regions` for inferred roles versus actual decoded runs.

## Offline CHimpREC-style recovery

`export_map` is a local JSON file containing an export list, at most 16 MiB. `module_exports` accepts the same list directly:

```json
{"id":7,"method":"recover-imports","params":{"project":"capture.fdb","module_exports":[{"address":"0x7ffb12341000","module":"KERNEL32.dll","name":"Sleep","ordinal":null}],"candidate_slots":["0x140003000"],"max_slots":100,"gap_limit":10}}
```

Each export supplies its captured/runtime target `address`, nonempty `module`, optional `name`, `ordinal` and `forwarder`. Hexadecimal address strings are accepted. Candidate slots are addresses **of cells**, not their values. Recovery requires 32/64-bit pointer widths. Without explicit slots, the project runs its recursive analyzer and uses decoded pointer-width memory references as candidates. A budget stop leaves this discovery explicitly partial. The standalone Python helper additionally provides heuristic x86 FF15/25 pattern discovery; the project command uses recursive code evidence.

Results include `source` with pinned CHimpREC provenance, `entries`, contiguous module `groups`, `warnings`, `candidates_examined` and `budget_exhausted`. Entries retain all matching export alternatives, ordinal-only identities, ambiguous aliases, padding and unresolved targets. `max_slots` bounds unique cell reads; `gap_limit` bounds consecutive unresolved nonzero cells during range expansion. Resolved identities are persisted as shared slot labels. `imports.recovery` exposes the latest receipt. No live attachment, module discovery, forwarder traversal or executable rebuilding occurs.

## Persistence and limits

New projects retain source bytes and inspection metadata. Schema 1–7 databases migrate in place to schema 8 with original versions/annotations retained. Schema 8 adds per-version label-link removal history. Schema-1 work is reopened so reanalysis backfills reference facts. `refresh-metadata` can rebuild supported container metadata when original bytes are retained; projects lacking those bytes require a new import. Migration does not fabricate missing source bytes. Existing byte analysis remains available without the original path.

Patches create child versions. Inherited annotations and definitions need semantic review. Source-file SHA-256 and mapped-snapshot SHA-256 identify different byte arrangements. File-backed metadata can refresh after a patch with a known disk counterpart; warnings disclose inherited metadata when no such mapping is known. MZ patches act on relocated memory bytes. Child file bytes undo every relocation in reverse loader order (including duplicate/overlapping records) before preserving the file-backed module. Allocation-only edits remain memory-only with an explicit warning; parent bytes/metadata remain intact.

Limits: 64 MiB input and mapped bytes; patch 1 byte–1 MiB within one region; annotation 1–4096 characters; name at most 256 characters without controls; JSON line at most 1 MiB. Oversized requests close the stream; ordinary malformed requests return errors and the session continues. Inspection caps lists/text and marks truncated strings. SVG escapes text, and image bounds reject excessive views. Imported files are never executed.

## Memory effects and selected CFGs

```json
{"id":40,"method":"refresh-facts","params":{"project":"dinopark.fdb"}}
{"id":41,"method":"memory-accesses","params":{"project":"dinopark.fdb","address":"4020:6f90","size":2,"access":"write","limit":200}}
{"id":42,"method":"cfg","params":{"project":"dinopark.fdb","address":"38ff:2b66","highlights":[{"address":"38ff:2be6","label":"staff-condition candidate"},{"address":"38ff:3168","label":"booking site"}]}}
{"id":43,"method":"render-cfg","params":{"project":"dinopark.fdb","address":"38ff:2b66","output":"routine.svg","highlights":["38ff:2be6","38ff:2fd6","38ff:3168"]}}
```

`memory-accesses` considers all stored source contexts. Its data query selector is not a source-CS filter. Access filters are `all`, `read`, `write`, `read_write`, `conditional_write`, `address_only`; `write` includes read/modify/write and conditional writes. Byte intervals have exclusive ends and include writes beginning before the requested range. `items` separates `match: overlap` under known static state from `unresolved_candidate` with unknown registers/segments, repetition or width. Facts retain native decoder, expression, width, segment, assumptions and unresolved reasons. `address_matches`, `unresolved_candidates`, `total`, `has_more`, `analysis` and `budget_exhausted` qualify the result. Unknowns are never replaced with zero. Known flat native segmentation is an explicit assumption; FS/GS need a base. Conditional/repeated/vector effects may require runtime state. No query proves all writers or runtime execution.

`refresh-facts` backfills missing fallthrough and access facts atomically from stored bytes and state. It changes derived indexes only. Fresh analysis keeps access facts current; older projects without a current index revision use read-only decode fallback until refreshed. Representation resets retract derived indexes. Patches keep the parent's facts isolated.

`cfg` requires an exact stored entry and traverses independently of candidate function labels. Calls remain separate from intraprocedural edges and continuation assumes return. The output includes exact instruction nodes/edges, basic blocks, call sites, exits, gaps, unresolved transfers, budget frontier, current analysis and highlighted-site shortest paths with edge evidence. DOS physical entries with multiple CS interpretations require explicit CS. Up to 100 highlights accept addresses or `{address, cs?, label?}`. Reconstructed old continuations have separate provenance. `graph_closed` describes stored static topology under assumptions; it does not prove path feasibility, execution or function ownership. `render-cfg` exports this snapshot with selectable SVG text and protects database/sidecar paths.


## Shared analysis and interpretation (0.6)

All methods below take `project` and optional `version`. Hyphens name public CLI/JSON methods; Python method names use underscores. JSON bodies are structured objects; CLI definition/contract/signature files contain those objects, never arbitrary SQL or executable code.

| Method | Required | Optional |
| --- | --- | --- |
| `auto-analyze` | — | `start`, `cs`, `ds`, `es`, `ss`, `abi`, `max_instructions` (10,000), `max_functions` (200), `max_steps` (100,000), `max_entries` (256), `max_rounds` (8) |
| `advanced-status` | — | — |
| `function-analysis` | `address` | `cs` |
| `function-membership` | — | `max_instructions` (100,000), `max_work` (1,000,000) |
| `define-type` | `name`, `definition` | `author` |
| `apply-type` | `address`, `type_name` | `name`, `author` |
| `types` | — | — |
| `typed-data` | `address` | `max_items` (256) |
| `set-summary` | `address`, `name` | `cs`, `prototype`, `summary`, `abi`, `author` |
| `summaries` | — | — |
| `add-signature` | `signature` | — |
| `signatures` | — | — |
| `call-effects` | — | `address`, `size` (1), `access` (`all`, `read`, `write`), `include_unresolved` (true), `limit` (200), `offset` (0) |

`auto-analyze` runs bounded native discovery and persistent function jobs until both queues stabilize or limits stop work. `max_functions` limits job executions across rounds, not unique entries. Other budgets apply per job or native pass. Repeating resumes pending/partial work; increasing a per-job limit invalidates cached jobs for requalification. An entry with no stored instruction cannot produce a derived result. Enabling this pipeline retires shallow snapshot-pointer promotions and requires reaching-state and write-history evidence for new indirect transfers. Retained decoded code from earlier heuristic seeds remains evidence of that earlier discovery, not proven reachability.

`function-analysis` reports `state`, `generation`, `reason`, `stale` and a nullable result. A result contains CFG coverage, dataflow diagnostics, frame slots/candidate arguments, indirect proposals/admissions, signature matches, qualified summary and call effects. Stale evidence is inspectable but `call-effects` excludes it. Basic `analysis-status.stable` still concerns native queues; `advanced` and `overall_stable` show the additional pipeline state.

`function-membership` computes shared candidate membership over stored edges. It excludes callee edges, retains assumed call-return continuations and returns noncontiguous runs, shared blocks, alternate entries, tail-jump candidates, missing destinations and truncation. Candidate prologues and names do not override graph evidence.

Types are explicit layouts: scalar (`size`, `signed`), pointer (`size`, `target`, `address_space`), array (`element`, `count`), struct (`size`, `fields` containing `name`, `offset`, `type`). Builtins are `u8/u16/u32/u64/i8/i16/i32/i64`. Pointer spaces are `flat`, `near` with optional `segment`, and four-byte `far16`. Structures reject overlapping fields and by-value cycles; pointer recursion is allowed. `typed-data` interprets immutable little-endian bytes and never dereferences a process. Field names resolve dynamically through shared physical identity.

`set-summary` is an explicit user-confirmed assertion. Known identities include `memcpy`, `memmove`, `memset`, `read`, `write`, `fread`, `fwrite`; custom contracts require an explicit prototype/effects object. `add-signature` requires architecture, bitness, exact body bytes and provenance; byte wildcards require declared relocation ranges. The catalog matches a complete supplied contiguous body, not an arbitrary prefix. Matches and user assertions remain qualified static evidence. ABI profiles describe integer argument locations; floating/vector/variadic source signatures are not inferred.

`call-effects` records call-site xrefs with width/range expressions, callee identity, argument values, ABI and provenance. Import-derived records include `summary_source`, `binding_evidence` and the condition that the declared binding still resolves to the named contract. `binding_unchanged_under_static_state` in that evidence is `true` when the modeled state permits reading the unchanged slot, `false` when a modeled may-write/taint prevents that proof, and `null` when proof is unavailable. It never identifies an observed runtime provider. A concrete buffer range can therefore remain a conditional contract effect even when binding proof is false or unknown; `resolved` describes its buffer address/size, not runtime callee identity. I/O lengths are upper bounds; unknown pointers remain possible effects. An unresolved record is not proof of overlap with the queried field. For instruction-level writers, combine with `memory-accesses`. DOS near offsets are not physical intervals without an established segment-aware contract.

Mach-O ARM64 defaults to `aarch64_darwin` (alias `darwin_arm64`), which describes
integer register arguments only. Darwin packed stack arguments and variadic
placement need typed signatures and remain uninferred; floating/vector rules
and authenticated-pointer behavior are not fully modeled. ELF ARM64 uses the
separate `aarch64_aapcs64` profile. These defaults are analysis assumptions.
Native macOS Apple Silicon debugger acceptance is documented in [DOSBOX_DEBUGGER.md](DOSBOX_DEBUGGER.md); complete native-host coverage remains bounded by the documented Linux ELF fixture limitations.

```json
{"id":40,"method":"define-type","params":{"project":"analysis.fdb","name":"Pair","definition":{"kind":"struct","size":4,"fields":[{"name":"count","offset":0,"type":"u16"},{"name":"flags","offset":2,"type":"u16"}]}}}
{"id":41,"method":"apply-type","params":{"project":"analysis.fdb","address":"0x2000","type_name":"Pair","name":"record"}}
{"id":42,"method":"auto-analyze","params":{"project":"analysis.fdb","abi":"x86_64_sysv","max_functions":50}}
```

See [ADVANCED_ANALYSIS.md](ADVANCED_ANALYSIS.md) for the decoder-neutral expressions, solver contracts and current CPU coverage.
