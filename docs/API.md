# Agent protocol

`fdisbull serve --project FILE.fdb` reads UTF-8 JSON lines and writes one response per line. `fdisbull request '{...}'` performs one request. This is a local protocol, not MCP or JSON-RPC; there is no network server.

Request: `{"id":"caller-chosen","method":"status","params":{}}`.
Response: `{"id":"caller-chosen","ok":true,"result":{...}}` or `{"id":"caller-chosen","ok":false,"error":{"type":"ValueError","message":"..."}}`.

Include `project` in params when there is no session default, or to override it. `identify`, `inspect` and `help` need no project and work in a bound stream too. Paths are local to the process. Addresses accept integers or integer strings; use `0x...` strings to preserve 64-bit precision. Public address fields are hexadecimal strings; file offsets, sizes, counts and version IDs are integers. Non-finite JSON numbers are rejected.

| Method | Required params beyond project | Optional params |
| --- | --- | --- |
| identify | path; no project needed | |
| inspect | path; no project needed | |
| import | path | arch, bits, base, entry, load_segment (MZ; default `0x1000`) |
| info | | version |
| header | | version |
| sections / imports / exports / strings | | version, limit (1–10,000), offset |
| status | | version |
| analyze | | version, start, max_instructions (1–1,000,000; default 10,000); MZ: cs, ds, es, ss |
| functions | | version, limit, offset |
| items / queue | | version, limit, offset |
| disasm | | version, address, lines (1–500); MZ: cs |
| xrefs | address | version, direction (`to`/`from`), limit; MZ: cs |
| rename | address, name | version, author |
| comment | address, text | version, author |
| represent | address, representation | size, author, version, max_instructions |
| recover-imports | module_exports **or** export_map | candidate_slots, version, max_slots (default 4096), gap_limit (default 10) |
| patch | address, data (hex bytes) | version (parent), label, origin |
| versions | | |
| issues | | version, limit |
| render | output | version, address, lines (1–200), format (`png`/`svg`); MZ: cs |
| segments | MZ project | version |
| code-regions | MZ project | version |
| help | no project needed | |

`limit` defaults to 200 for paginated lists. Information lists return `items`, `total`, `offset`, `has_more` and warnings. `items` and `queue` return arrays. `info` returns header/counts/warnings. `header.valid` means recognized header extents fit the file, not that the program can execute. A disk `file_offset` is never presented as a virtual address. Unknown import bindings and unmapped string addresses are null.

## Analysis and shared presentation

One binary/architecture/bitness belongs to each project. Non-DOS projects use a flat little-endian decode context. MZ instruction facts add the actual CS (`x86:16:little:cs=38ff`); names/comments/representations remain shared by physical address within their byte version. `version` defaults to the newest ID.

`analyze` prioritizes recursive entry traversal, mapped data investigations, then deferred symbol/export seeds. It reports `decoded`, `attempted`, `data_processed`, `new_facts`, `pending_code`, `pending_data`, `pending`, `entry_complete`, `passes`, `stable` and `budget_exhausted`. The budget counts work attempts across code and data. `pending` can include an unscheduled later seed phase. Resume while unstable; an empty implemented work queue does not establish complete disassembly.

`queue` combines code and data tasks with reasons, states and details. `items` exposes investigated data values, evidence sources and shared presentations. Uncorroborated pointer values remain candidates; actual indirect control-flow evidence can promote their targets. Function records remain candidate entries, not proven boundaries.

`disasm` returns stored rows, original numeric `operands`, structured `references` and address-resolved `display_operands`. Each reference carries operand index, role, target, width, shared name and representation. Changing a target name changes callers' subsequent query/render output. `render` uses that same stored snapshot, does not trigger analysis, and rejects overwriting an active database or its sidecars.

`represent` defines one mapped range as `code`, `byte`, `word`, `dword`, `qword`, `pointer`, `ascii` or `utf-16le`. `size` is bytes, 1–4096; strings require it explicitly, UTF-16 requires an even size, and numeric types require their natural width. `code` defaults to one byte. Distinct explicit definitions may not overlap. The operation resets derived code/data facts and automatically reanalyzes within `max_instructions`; names/comments survive. Check the nested analysis receipt for remaining work.

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

MZ `analyze` additionally reports `pending_seeds` and `assumptions`. A budget stop is never called stable. The calling convention preserves DS/SS/BP/SP on call fallthrough while general registers/ES become unknown; deferred seeds may assume startup DS or a unique observed data segment. Unknown indirect targets, dynamic pointer writes and runtime-dependent state remain partial even after implemented queues drain.

`segments` returns selectors, CS contexts, inferred base/end, roles, sources and instruction counts. `bounds_inferred: true` distinguishes these candidates from format-defined sections. `code-regions` returns contiguous decoded runs per CS, with exclusive ends and `classification: decoded instruction run`; it does not imply the gaps or the entire segment are code. Both commands require an MZ project. The JSON method name is literally `code-regions`.

MZ disassembly includes physical `address`, `cs`, `ip`, `segmented_address`, context, alternative stored contexts, register assumptions and warnings. Without explicit CS, a deterministic stored context may be selected; a nearest-row view warns if the requested physical address is not stored. Explicit `CS:IP`/`cs` selects an interpretation without decoding new bytes. Xrefs retain source and target CS when known. Physical aliases share labels and explicit representations, not instruction-context identity.

The MZ project `header` supplies DOS fixed fields, relocation count, selected load segment and initial CS:IP. Standalone identification is byte-based; a successful header parse is not execution evidence. `sections` reports the unclassified DOS load-module mapping; use `segments`/`code-regions` for inferred roles versus actual decoded runs.

## Offline CHimpREC-style recovery

`export_map` is a local JSON file containing an export list, at most 16 MiB. `module_exports` accepts the same list directly:

```json
{"id":7,"method":"recover-imports","params":{"project":"capture.fdb","module_exports":[{"address":"0x7ffb12341000","module":"KERNEL32.dll","name":"Sleep","ordinal":null}],"candidate_slots":["0x140003000"],"max_slots":100,"gap_limit":10}}
```

Each export supplies its captured/runtime target `address`, nonempty `module`, optional `name`, `ordinal` and `forwarder`. Hexadecimal address strings are accepted. Candidate slots are addresses **of cells**, not their values. Recovery requires 32/64-bit pointer widths. Without explicit slots, the project runs its recursive analyzer and uses decoded pointer-width memory references as candidates. A budget stop leaves this discovery explicitly partial. The standalone Python helper additionally provides heuristic x86 FF15/25 pattern discovery; the project command uses recursive code evidence.

Results include `source` with pinned CHimpREC provenance, `entries`, contiguous module `groups`, `warnings`, `candidates_examined` and `budget_exhausted`. Entries retain all matching export alternatives, ordinal-only identities, ambiguous aliases, padding and unresolved targets. `max_slots` bounds unique cell reads; `gap_limit` bounds consecutive unresolved nonzero cells during range expansion. Resolved identities are persisted as shared slot labels. `imports.recovery` exposes the latest receipt. No live attachment, module discovery, forwarder traversal or executable rebuilding occurs.

## Persistence and limits

New projects retain source bytes and inspection metadata. Schema 1/2 databases migrate in place to schema 3 with original versions/annotations retained. Schema-1 work is reopened so reanalysis backfills reference facts. Missing original file metadata is reported explicitly and requires a new import; migration does not fabricate source bytes. Existing byte analysis remains available without that file.

Patches create child versions. Inherited annotations and definitions need semantic review. Source-file SHA-256 and mapped-snapshot SHA-256 identify different byte arrangements. File-backed metadata can refresh after a patch with a known disk counterpart; warnings disclose inherited metadata when no such mapping is known. MZ patches act on relocated memory bytes. Child file bytes undo every relocation in reverse loader order (including duplicate/overlapping records) before preserving the file-backed module. Allocation-only edits remain memory-only with an explicit warning; parent bytes/metadata remain intact.

Limits: 64 MiB input and mapped bytes; patch 1 byte–1 MiB within one region; annotation 1–4096 characters; name at most 256 characters without controls; JSON line at most 1 MiB. Oversized requests close the stream; ordinary malformed requests return errors and the session continues. Inspection caps lists/text and marks truncated strings. SVG escapes text, and image bounds reject excessive views. Imported files are never executed.
