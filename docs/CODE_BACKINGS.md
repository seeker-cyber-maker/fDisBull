# Entry-qualified code backings and bounded layouts

This engine path preserves multiple instruction interpretations of a source
byte. It captures complete native encodings and can emit a separate bounded
layout. It does not infer game intent, extend the register-only UIL lift, or
write a regenerated MZ/LE executable. The existing [original DOS compiler](UDC_DOS.md)
continues to reconstruct the exact original file layout.

The [direct native UDL-to-UDC route](NATIVE_UDL_UDC.md) persists these backings
with a logical multi-instruction block plan. Its default pass-through keeps the
entire original file and offsets intact; relayout is a separate explicit mode.

## The shared-byte case

The authored sequence `74 01 A8 AA C3` admits two conditional paths. One enters
`A8 AA` (`TEST AL,0xAA`), the other enters its immediate byte `AA` (`STOSB`).
Both reach the same `RET`. These are separate instructions with separate entry
semantics, even though their source bytes overlap.

`Project.code_backings` gives each stored instruction its full local encoding.
The TEST backing contains both bytes without depending on the STOSB backing.
Its provenance identifies AA as an immediate; the other backing identifies the
same source address as part of its instruction encoding. Coverage counts the
source byte once and local occurrences separately. Including RET, the selected
slice has three physical bytes and four local encoding bytes.

`Project.code_blocks` groups explicit straight-line paths after merging all
requested roots, preserving joins, alternate entries and caller boundaries.
The groups are logical and unplaced: deriving them does not insert bytes or
change source offsets. Independent group encodings are available through
`fdisbull.code_blocks.materialize_code_block`.

Explicit code/code representation ranges can overlap. A collision involving a
data representation remains an error. Decoded alternatives, source patches,
prior versions and annotation authorship remain retained in the project.

## Capture and emit

The Python, JSON-line and CLI interfaces use the same project implementation.
They operate on exact **stored** instruction entries. Analyze the required
entries first; a capture never silently decodes missing instructions.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from fdisbull.project import Project
from fdisbull.code_backings import materialize_code_backing, validate_source
from fdisbull.code_layout import compile_code_backings

with TemporaryDirectory(prefix='fdisbull-authored-', dir='/tmp') as private:
    root = Path(private)
    source = root / 'OVERLAP.BIN'
    source.write_bytes(bytes.fromhex('7401a8aac3'))
    with Project.create(root / 'analysis.fdb', source,
                        arch='x86', bits=16, base=0x1000) as project:
        project.analyze()
        backings = project.code_backings([0x1002, 0x1003])
        assert backings['complete']
        assert validate_source(project, backings)['status'] == 'source_valid'
        assert materialize_code_backing(backings['blocks'][0]) == b'\xa8\xaa'
        assumptions = {
            'no_code_reads': True, 'no_code_writes': True,
            'no_computed_entries': True, 'address_identity_unobserved': True,
            'timing_unobserved': True,
        }
        output = compile_code_backings(backings, base=0x200,
                                       assumptions=assumptions)
        # Alternatively project.code_layout captures fresh and emits in one call.
        assert output['bytes'] == 'a8aae90400aae90000c3'
        assert output['qualification'] == 'structural_only'
```

Every assumption is an explicit caller assertion about the admitted domain;
the engine has not established it by examining a game. Do not set these values
merely to get a result. Unsupported or unknown domains can still be captured
as residual native backings without emitting a new layout.

For an existing private project containing that authored example:

```text
fdisbull code-backings /private/analysis.fdb --entry 0x1002 --entry 0x1003
fdisbull code-layout /private/analysis.fdb --entry 0x1002 --entry 0x1003 --base 0x200 --assumptions /private/assumptions.json
```

The matching JSON methods are `code-backings` and `code-layout`; both require
`project` and `entries`. Optional capture arguments are `version`, `cs` and
`max_instructions`. An entry can be an address or `{address, cs?}`. DOS accepts
CS:IP entries; supply a selector when a physical address has multiple contexts.
The capture budget is shared across roots and counts repeated CFG visits.
All requested entries remain recorded when that budget expires. Missing facts,
unresolved transfers and frontier entries produce `complete: false`.

The layout additionally accepts `order` (all backing IDs exactly once), `base`,
`assumptions` and `entry_references`. The CLI accepts the latter structured
arguments in bounded JSON files using `--order`, `--assumptions` and
`--entry-references`. Routine output uses the existing output-limit and artifact
handle policy. These replies can retain source bytes: keep private captures,
artifacts and analysis projects outside Git and deliveries.

## What the layout preserves and refuses

The supported profile is one x86 16- or 32-bit decode context. Ordinary
instructions keep their complete bytes. Supported same-width direct near
JMP/Jcc instructions are rebuilt as near branches, including short branches
that no longer reach. Every ordinary fallthrough and conditional false path
gets an explicit near JMP. This glue changes neither flags nor the stack.
TEST therefore bypasses the separately emitted STOSB; adjacency is never used
as an implicit continuation contract.

The near conditional form requires a 386 or newer CPU, including in 16-bit
mode. Source instruction extensions remain required too; CPU feature levels
are not inferred from the mode alone. This is not an 8086 lowering target.

The output records source/backing revisions, local occurrences, final entry
locations, rewritten branches and glue. `entry_references` explicitly names
pointer/table targets and widths; the result supplies their remapped
little-endian values. It does not discover all pointers or patch a surrounding
table/container. In 16-bit output, locations are **IP offsets**, not flat linear
far pointers. A surrounding image builder must handle segments and headers.

Unresolved or missing ports, indirect transfers, calls, far transfers,
unsupported branch forms, IP-relative memory, mixed contexts, conflicting
source occurrences and unsupported mode/container transformations are refused.
Known direct references into captured code are refused. Indirect accesses and
code outside the captured set still require the declared no-code-read/write
assumptions. No source checksum, code-address comparison or self-modifying
alias relationship is silently reconstructed by making two independent copies.

There are at most 4,096 blocks in a layout. Output must fit a nonwrapping
16/32-bit address interval and every emitted near displacement must fit its
signed width. The emitter rejects an out-of-range displacement rather than
inventing a thunk or an external entry. Capture can be broader than this
emission profile; a capture's completeness does not imply supported semantics.

## Identity and assurance boundaries

A backing revision binds complete local bytes, context, provenance and ports.
A source-byte patch creates a new immutable version and invalidates a capsule
when checked against that current version, including both shared occurrences.
The original capsule can still be checked against its retained original
version. Editing one independent backing is not a source patch: materialization
rejects a mismatched revision, and this API does not qualify arbitrary edits.

`validate_source` checks version/byte identity and re-queries the requested
project graph to detect a relabeled partial capture or altered ports. Its
`source_valid` receipt is not semantic equivalence or authenticated authorship.
Public JSON digests detect inconsistent content; callers can recompute them.
The standalone `compile_code_backings` accepts caller-authored capsules and
independently validates encodings and edges; it cannot authenticate their
historical analysis evidence. `Project.code_layout` and its CLI/JSON method
capture directly from the selected project version instead.

No physical-overlap primitive is added to UIL. TEST flags, STOSB memory effects
and unsupported behavior remain native residuals until a semantic contract is
separately qualified. The existing straight-line UIL lift continues to reject
observed flags, memory and unsupported instructions.

The authored tests distinguish structural checks, a bounded Z3 ISA model,
and real DOSBox execution. A proof under the authored model is not a proof of
decoder fidelity, exceptional paths, timing, an original game's reachability
or a general relocating compiler. See [the broader PR #45 contract](UDL_OVERLAP_RECONSTRUCTION.md)
for work beyond this bounded engine path.
