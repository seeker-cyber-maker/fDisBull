# First standard DOS UDC target: COM16/i386

This engine target generates a new headerless DOS COM program from retained
native blocks and explicitly selected straight-line replacements. It places
blocks independently and repairs admitted references. It is a bounded first
target, not a general DOS compiler or automatic UIL lowering.

The [native UDL-to-UDC pass-through](NATIVE_UDL_UDC.md) remains the byte-identical
baseline. Its default original-layout mode preserves the entire original file.
`udc-dos-compile` instead emits a new program and reports new placements.

## Admitted program and data

The source must be a complete, freshly validated version-1 native definition
from an x86-16 COM project with one CS context. Source byte/backing/plan
identities remain pinned. Multiple captured roots require an explicit boot
entry; known incoming control edges from outside the captured graph are
refused. Calls, far/indirect transfers, interrupts and unsupported modes need
future adapters.

The emitted program targets a 386 or newer CPU, starts at IP 0x100 with a
flag- and stack-neutral near jump, and uses CS=DS=ES=SS. Segment changes and
unsupported stack-pointer mutations are refused. The upper segment range
0xF000..0xFFFF is reserved for stack. Every output instruction/data range must
fit without overlap or wrapping, and near displacements must fit signed 16-bit
range. Near conditional forms require the declared 386 target.

Data is explicit: each `{id, ip, size}` selects retained bytes at the original
COM IP offset. File offset is **IP minus 0x100**. The definition checks those
bytes against the original file and mapped source version and rejects overlap
with any known instruction or explicit code definition, including outside the
selected CFG. Data stays at its fixed IP while code is placed in a separate
bank. Omitted source regions become declared zero padding in the new output;
this is not a claim that all original data has been recovered.

The caller must supply the five existing layout assertions:
`no_code_reads`, `no_code_writes`, `no_computed_entries`,
`address_identity_unobserved` and `timing_unobserved`. Register-addressed/string
memory additionally requires `register_memory_targets_fixed_data: true` and
actual declared data. These are domain obligations, not facts inferred by
setting booleans. Known absolute memory/address references must match native
fields and lie wholly within declared data; an unclassified known access is
refused. Unobserved or undiscovered references remain outside the qualified
domain.

## Stable ports and selected implementations

The UDL native definition retains original instruction interpretations and a
logical block plan. A source byte can still have several original roles.
Standard UDC placement binds each logical block entry to a new IP, so an entry
that originally began inside another instruction is never reconstructed as
`new_A + 1` by assumption.

A replacement is a separate immutable implementation revision, bound to the
compiler definition, logical block and expected source block revision. Its
complete local body can differ in length. The first profile accepts only
straight-line NEXT instructions in a replacement and requires one explicit
source successor port. The compiler adds a neutral near jump to that port.
Conditional or terminal blocks and unsupported internal control transfers
require later replacement interfaces.

Selection is explicit through `{block_id: implementation_id}`. Registering a
newer implementation never silently changes a compilation. Replacing one
overlapping interpretation does not modify a sibling backing or the retained
original file. The code bank, source/candidate occurrences and fixups describe
the selected implementation rather than pretending its bytes were the source.

## Typed reference repairs

The admitted reference forms are:

| Kind | Required site and behavior |
| --- | --- |
| Native direct JMP/Jcc | Resolve exact logical target ports, emit near forms, and re-decode final targets. Conditional false paths and terminal fallthroughs get explicit neutral jumps. |
| Fixed absolute memory/address | Validate decoded access/address size, segment, full extent and fixed-data ownership. Preserve the offset and record that decision. |
| `near-code-pointer` | A two-byte field in declared data with expected old bytes and a known block target. Write the newly placed near IP. This does not authorize indirect dispatch. |
| `code-immediate` / `data-immediate` | An explicitly declared native MOV reg16,imm16 field. Verify its exact location and original target value; do not guess that every constant is a pointer. |

Example table declaration:

```json
{"kind":"near-code-pointer","data":"fixed","offset":4,
 "target":"BLOCK_ID","expected_hex":"0c01"}
```

Original instruction-immediate records use `instruction`, `field_offset`,
`target`, optional data `addend` and `expected_hex`. Replacement records use a
body-relative `field_offset` instead of a source instruction ID. All sites are
checked against native field boundaries and reject duplicates, overlap,
out-of-range values or unsupported target interiors.

Stored operand evidence is also a requirement. If an already known MOV
immediate points to code, leaving its typed reference out is an error. Newly
discovered semantic reference facts invalidate an older capture; changing a
presentation label does not. Replacing a block with such an original pointer
site currently requires a future obligation-transfer interface and is refused
conservatively.

## Projection proof and experiments remain separate

`purpose='experiment'` admits a structurally valid candidate without claiming
the old behavior. This is useful for intentionally changing a rule.

`purpose='register-equivalence'` requests a genuine Z3 check using the supported
straight-line u16 ASM model. A projection names `bindings`, `inputs` and
`outputs`. The model compares declared register outputs and excludes flags,
memory, control flow, ABI, timing and partial effects. Source and candidate
immediate fixups are refused in this proof profile, since proving an old
pointer constant before rewriting it would not prove the emitted value.
Unknown, unavailable or counterexample results refuse that qualification.
The proof is rechecked on readback and compilation.

The generated artifact remains **`structural_only`**, even if a selected
register projection passes. Its `native_execution` field is false: compiling
does not run it. Native observations belong to a separate test receipt, and a
narrow register proof never establishes whole-program parity.

## Agent and Python workflow

Inspect the native plan first, then choose one small question, declare the
needed data and references, and compare the unchanged baseline before adding
one implementation. Keep original native UDC definitions as a fallback.

```python
with Project('/private/analysis.fdb') as project:
    native = project.udc_native_capture('source', ['1000:0100'], version=1)
    definition = project.udc_dos_define('com-experiment', native['id'],
        data=[{'id': 'fixed', 'ip': 0x180, 'size': 6}],
        references=[{'kind': 'near-code-pointer', 'data': 'fixed',
                     'offset': 4, 'target': STORE_BLOCK_ID, 'expected_hex': '0c01'}])
    candidate = project.udc_dos_implementation(definition['id'], COMPUTE_BLOCK_ID,
        'b81100b81100', EXPECTED_BLOCK_REVISION,
        purpose='register-equivalence',
        projection={'bindings': {'ax': '$result'}, 'inputs': [], 'outputs': ['ax']})
    generated = project.udc_dos_compile(definition['id'],
        implementations={COMPUTE_BLOCK_ID: candidate['id']}, assumptions=ASSUMPTIONS)
```

Those addresses, bytes and identifiers belong to the authored verification
fixture; supply actual bindings for a different source. The output contains
whole-file hex bytes, a payload hash, source/definition/implementation/layout
identities, port IPs, output ranges and fixup records. Saving bytes is an
explicit caller operation in a private workspace; these APIs do not write
host executables or launch a guest.

The JSON/CLI methods are `udc-dos-define`, `udc-dos-info`,
`udc-dos-implementation`, `udc-dos-implementation-info` and `udc-dos-compile`.
Structured CLI inputs use bounded JSON files through `--data`, `--references`,
`--projection`, `--implementations`, `--block-order` and `--assumptions`.
`--full` opts into private definition details; routine replies use the existing
output-limit/artifact-handle policy. Keep generated code, byte-retaining
artifacts, source programs, states and project databases out of Git.

## MZ output scaffold

Select `container='mz'` in Python or `--container mz` on `udc-dos-compile`
to place the same checked code/data layout in a new resident DOS MZ executable.
The default remains COM. The source definition still requires the COM16 source
profile above; this output adapter does not relink arbitrary original MZ games,
overlays, far calls, multiple segments or DOS extenders. Use the original-backed
native pass-through for a byte-identical baseline of an existing MZ game.

The new container has a 32-byte header, a single loader relocation, equal initial
CS/SS, SP=FFFEh and a 64 KiB allocation including the reserved stack. Startup at
IP 00F7h preserves AX, flags and SP while initializing DS and ES to the actual
loader-selected segment; execution continues through the existing 0100h entry
jump. Code/data ports and their near references retain their IP values. Emitted
file offsets change to **32 plus IP**, and the result separately records loader
relocations, the container and the underlying code-layout identity.

MZ wrapping adds no semantic equivalence claim. The generated result remains
`structural_only`, with `native_execution: false`. An authored native acceptance
test separately checks startup, the relocated segment word, registers, ready
loop branches, result memory and repaired pointer targets in DOSBox. It does
not establish reconstruction of an original MZ game's runtime.
