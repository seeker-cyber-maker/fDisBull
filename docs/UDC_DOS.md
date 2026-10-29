# Original-backed DOS UDC

The 0.23 target reconstructs original DOS files from immutable
block backings. UDL mappings and UIL keep the same `fdisbull-il-1` primitives.
The compiler consumes UIL and uses the corresponding UDL/native backing as its
first executable definition. It does not regenerate arbitrary DOS code.

The current profile accepts original static **version 1**, x86-16 MZ or COM.
MZ headers, relocations, data and opaque regions retain their original bytes
and layout. Explicit attached resources are captured with the executable.
Compilation can run after the original input files have been removed because
the private project stores the backing blocks. A caller's patch version does
not replace that original definition.

## Capture, inspect and compile

```python
from fdisbull.project import Project
from fdisbull.udc import capture_dos_definition, shared_programs, compile_dos
from fdisbull.udl_blocks import lift_asm_block, asm_to_c, lift_c_block, verify_block

with Project('/private/analysis.fdb') as project:
    # This exact source span must exist at the specified primary-file offset.
    lift = lift_asm_block(bytes.fromhex('05c80048'), {'ax': '$score'},
                          inputs=['ax'], outputs=['ax'])
    definition = capture_dos_definition(project, 'original-score',
        semantic_blocks=[{'id': 'score', 'offset': 16, 'lift': lift}])
    udl = shared_programs(project, definition['id'], role='udl')
    uil = shared_programs(project, definition['id'], role='uil')
    result = compile_dos(project, definition['id'], '/private/new-emitted-game',
                         programs=uil)
```

The offset in this example belongs to the authored verification game, not an
arbitrary executable. A different input must supply its actual byte-bound
mapping. The original and emitted files retain identical hashes.

Resources are explicit snapshots, for example
`project.attach_file(path, name='story')` followed by
`resources={'DATA/ZORK1.DAT': 'story'}` at capture. They are not discovered or
fetched implicitly. Saved states and project databases are refused as resource
inputs; an output alias does not bypass the source-filename and SQLite checks.

Equivalent CLI operations are `udc-capture`, `udc-info`, `udc-programs` and
`udc-compile`. `udc-capture --blocks FILE` takes the `semantic_blocks` list;
`--resources FILE` takes the output-path-to-attached-file map. `udc-programs`
requires an output file, and `udc-compile` writes its complete manifest next
to the emitted files. Default replies contain compact metadata and counts,
not game bytes or the entire block catalog. `udc-info --full` is explicit.

Output must be a new directory outside Git. It is exclusively reserved before
writing, has private permissions, and receives its completion manifest last.
An existing directory is never replaced. A failed build removes its own
partial directory. Artifact paths reject traversal, drive/stream names and
reserved manifest/device names. Definitions retain immutable parent revisions
and integrity hashes covering their source, block graph and authorship.

## Semantic coverage and Z3

Unmapped code and data are retained as original dependencies. A definition
with no recovered semantic blocks reports `original_bytes_only`; it does not
claim that its game was recovered into UIL.

The first semantic profile accepts only complete straight-line 16-bit register
blocks: immediate MOV, supported AX ADD/SUB, and register INC/DEC. Capstone
checks the instruction facts. Inputs, outputs and variable bindings are
explicit. Memory, pointers, control flow and observed flags are refused.

Source-byte transitions and candidate UIL transitions are modeled separately.
Z3 compares the declared register outputs for all admitted 16-bit inputs.
Proof receipts retain the actual bit-vector specifications and assumptions.
An incorrect block returns a counterexample; unavailable or unknown proof is
never equality. Modeling budgets bound expression expansion before JSON or
solver construction. A semantic build requires an established result even if
the candidate has not changed since capture.

A source span must lie inside the file-backed load module. MZ spans touched by
loader relocations are refused by the semantic profile: raw-file constants are
not silently treated as relocated runtime constants. Headers and overlays can
remain opaque preserved bytes.

A changed UIL block may select the original backing only if that same narrow
observation contract is proved equivalent. Unchanged variable defaults and
bindings are required. This does not prove timing, flags, memory, caller ABI,
intermediate writes or whole-program behavior. Native bytes remain unchanged;
new DOS lowering rules have not been implemented.

## C route

`asm_to_c(lift)` produces a bounded C-like statement view of the supported ASM
block. `lift_c_block` parses a restricted unsigned-16 assignment/add/subtract
statement sequence into the same UIL. `verify_block` can then compare that UIL
with the original ASM model, and UDC can select the original native backing.

The view shares the ASM decoder. It is an additional abstraction edge to test,
not independent source evidence or a general C/C++ decompiler. The C profile
declares uint16_t operands and an int width of at least 32 bits. Signed
undefined behavior, arbitrary expressions, aliasing and function recovery are
outside this reader. `udl-lift-asm`, `udl-lift-c` and `udl-verify` expose the
same bounded source, model and refusal behavior through the CLI. `udl-verify`
prints a compact verdict; `--output FILE` retains complete proof specifications.

See [the layer-by-layer protocol](UDC_TESTING.md) and
[0.23 verification](VERIFICATION-0.23.md) for the observed scope.
