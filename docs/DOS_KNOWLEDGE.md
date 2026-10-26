# Standalone DOS analysis knowledge

These features work without IDA. Native decoding and retained bytes remain the
instruction authority; the additions supply explicit interpretations.

## Runtime identities

The bundled catalog adds **182 DOS16 signatures** from Microsoft's publicly
released `SLIBCE.LIB`, `MLIBCE.LIB` and `LLIBCE.LIB`, alongside the four authored
64-bit contract examples. String, memory and arithmetic helpers have separate
small/medium/large model variants. This is not 182 distinct function names.

Inputs are pinned to Microsoft MS-DOS commit
`2d04cacc5322951f187bb17e017c12920ac8ebe2`. The packaged catalog retains library
hashes, public symbols, modules and offsets. Its MIT licence is included in
`data/MICROSOFT-DOS-LICENSE.txt`. Reproduce it from those exact three libraries:

```sh
python scripts/build_dos_signatures.py /path/to/libraries /tmp/catalog.json
```

The OMF extractor admits only fixup-free, publicly named routines with closed,
contiguous, returning native control flow. Modules needing fixups, unsupported
records, bad checksums, iterated code data, calls or indirect transfers are
excluded with reasons. It is not an arbitrary OMF linker or FLIRT `.sig` reader.
Borland/Pascal compiler catalogs are not bundled yet.

`auto-analyze` qualifies complete stored function bodies. New analysis/catalog
revisions invalidate older derived results when that pass runs. Unique matches
supply names through shared identity; authored names/native symbols take
precedence and conflicting matches remain ambiguous. Patches invalidate matches
without altering parents. DOS signatures supply identities only, not automatic
segmented memory-effect contracts or proof of runtime execution.

- `capture-signature PROJECT ADDRESS NAME` captures a user-confirmed identity from a
  closed, contiguous stored function. MZ segment fixups are explicitly masked.
- `export-signatures PROJECT` returns registered identities as `fdisbull-signatures-1`.
- `import-signatures PROJECT CATALOG.json` validates the entire document before
  registration. Imports are versioned and invalidate derived results.
- `omf-catalog LIBRARY --abi x86_16_cdecl_near` extracts a caller-supplied OMF
  library without automatically registering it.

Equivalent Python methods are `capture_signature`, `export_signatures`,
`import_signatures`. Each capture retains authorship, context and source hashes.

## DOS/BIOS descriptions

`dos-services` exposes 37 authored service descriptions. Stored DOS disassembly
adds `interrupt_service`: selector evidence, known input values, documented
outputs and qualified buffer effects, separate from raw operands and user comments.
INT 21h/AH=3Fh, for example, writes into DS:DX with CX as a requested upper bound;
actual transfer/error status remain unknown until observed. Unknown selectors
stay unknown. This does not add optimistic register preservation to the solver.
Replaced interrupt handlers may behave differently.

Facts were checked against the [Microsoft MS-DOS Encyclopedia](https://www.pcjs.org/documents/books/mspl13/msdos/encyclopedia/section5/)
and [IBM PC Technical Reference](https://www.pcjs.org/documents/manuals/ibm/pc/techref/).
This is a documented subset, not full DOS/BIOS coverage.

## Rich types

| Kind | Definition fields |
|---|---|
| `enum` | `size`, `members` map; optional `signed`, `flags` |
| `union` | `size`, `fields` with `name`, `type`, offset zero |
| `bitfield` | `size`, `fields` with `name`, `lsb`, `width`, optional `signed` |
| `typedef` | `target` type name |
| `function` | `returns` type or null, named `arguments`, explicit `abi`, optional `variadic` |

Enums show symbols; flags retain unknown bits. Unions expose every interpretation
without guessing the active one. Bitfields retain storage bytes and extracted
values. Types work on mapped memory and attached immutable files, survive restart
and remain isolated by version. Function pointers expose declared prototypes;
function types have no data storage and cannot be bound directly to data.
Expanded layouts have a 65,536-node/member budget and a separate 4,096-instance
union budget. Existing 16 KB nested layouts remain supported; repeated overlapping
interpretations remain bounded. Oversized definitions fail before persistence. OMF extraction
also bounds module segment storage and reports excluded modules explicitly.

`set-function-type PROJECT ADDRESS TYPE` freezes an authored prototype into the
version's function summary. Reapply after editing its type definition. The new
`x86_16_pascal_near`/`x86_16_pascal_far` profiles require a prototype to assign
source argument indices. Declared DOS16 widths determine aligned stack locations,
Pascal source order and callee cleanup. Only an exact available stack cell supplies
a value; fragmented cells are not guessed. Other ABIs retain their existing
integer-register candidate model. No automatic source-type recovery is claimed.

## Remaining coverage

Dedicated COM/SYS loaders, compiler-managed overlay loading, further compiler
catalogs and broad debug-symbol import remain separate work. Toggleable execution
layers do not replace compiler overlay-file loading.
