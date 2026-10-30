# Original-backed DOS UDC

The 0.23 target reconstructs original DOS files from immutable
block backings. UDL mappings and UIL keep the same `fdisbull-il-1` primitives.
The compiler consumes UIL and uses the corresponding UDL/native backing as its
first executable definition. It does not regenerate arbitrary DOS code.

The separate [entry-qualified code backing engine](CODE_BACKINGS.md) captures
overlapping stored instruction interpretations and emits a bounded raw x86
layout with explicit continuations. Its structural-only output is not this
compiler's byte-identical file reconstruction or a regenerated MZ/LE container.
The [native UDL pass-through definition](NATIVE_UDL_UDC.md) also offers a
version-pinned exact-source baseline without requiring any UIL lift; its
logical block split leaves original physical storage unchanged.

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
block using the built-in renderer. `lift_c_block` parses its restricted
unsigned-16 assignment/add/subtract statements into UIL. `verify_block` can
then compare that UIL with the original ASM model, and UDC can select the
original native backing. The built-in view shares the ASM decoder.

An installed Ghidra can be selected explicitly with
`asm_to_c(lift, engine='ghidra', analyze_headless='/path/to/analyzeHeadless',
java_home='/path/to/jdk')`. This optional path starts a bounded headless
project with a synthetic DOS MZ header, the exact block bytes and a recorded
`RET` terminator. It obtains
Ghidra instruction facts and a decompiler C listing, then returns normalized
`text` in the same restricted C grammar. The normalized statements are derived
from Ghidra's decoded instruction facts, not parsed from its decompiler C.
The native `ghidra_c` listing and diagnostics are separate evidence; arbitrary
Ghidra C is not accepted by `lift_c_block`. A failed or unavailable Ghidra run
does not fall back to the built-in renderer. The caller must pin the tool path,
Java runtime and input hash when comparing results.

For an admitted block, use the selected view in the existing proof path:

```python
view = asm_to_c(lift, engine='ghidra',
                analyze_headless='/path/to/analyzeHeadless',
                java_home='/path/to/jdk')
candidate = lift_c_block(view['text'], lift['bindings'],
                         inputs=lift['inputs'], outputs=lift['outputs'])
proof = verify_block(lift, candidate['uil'])
```

Only an established `equivalent_under_assumptions` result qualifies the
candidate for this bounded interface.

Both views retain the same register-only contract. Flags, memory, control
flow, ABI, timing, signed undefined behavior, pointer aliasing and general
function recovery remain outside it. Neither renderer is independent source
evidence or a native parity check. The C profile declares uint16_t operands
and an int width of at least 32 bits. `udl-lift-asm`, `udl-lift-c` and
`udl-verify` expose the original bounded readers through the CLI; `udl-verify`
prints a compact verdict, while `--output FILE` retains complete proof
specifications.

Run the checkout-only [engine comparison](../examples/recovery/benchmark_asm_c_engines.py)
on authored blocks with an explicit Ghidra path. It records the C outputs,
qualification result and per-call wall times. A fresh Ghidra process is timed
against an in-process built-in call; the observed request latency ratio is
useful for that deployment choice, not a pure algorithm speed ratio. The
benchmark does not measure game reconstruction quality or analyst time.
Ghidra's real-mode decompiler may fail on an admitted block; such runs are
reported as unknown comparisons rather than replaced with built-in output.
The [measured methodology and result](GHIDRA_ASM_C_COMPARISON.md) document the
current local comparison.

See [the layer-by-layer protocol](UDC_TESTING.md) and
[0.23 verification](VERIFICATION-0.23.md) for the observed scope.
