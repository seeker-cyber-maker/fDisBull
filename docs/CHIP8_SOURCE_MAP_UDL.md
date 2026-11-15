# CHIP-8 original-source maps and typed UDL candidates

This is the bounded **G2 original-source mapping** step in the
[CHIP-8 G0–G8 plan](milestones/2026-11-03-chip8-package-end-to-end-acceptance.md).
Start with a verified [G0 intake](CHIP8_CONVERSION_INTAKE.md) and a compatible,
source-bound [G1 package closure](CHIP8_PACKAGE_CLOSURE.md). G2 walks the
original mapped ROM and stores source instruction facts with typed UDL
candidates. It does not execute the guest, prove those candidates against an
independent oracle, create executable common UIL, or complete G3–G8.

## Build and inspect

```python
from fdisbull.project import Project

with Project('/private/analysis.fdb') as project:
    mapping = project.chip8_source_map(
        closure_id,
        max_instructions=256,
        max_states=2048,
        max_call_depth=16,
        expected_intake_sha256=accepted_intake_sha256,
    )
    checked = project.chip8_source_map_info(
        mapping['mapping'], expected_intake_sha256=accepted_intake_sha256)
```

The bounded options are 1–1,792 unique decoded source instructions, 1–8,192 states and call depth
1–16. A request starts at original source PC `0x200` with an empty return
stack. It does not run `Project.analyze` or add instruction facts to that
analysis. The source map has format `fdisbull-chip8-source-map-1`, a
content-addressed `chip8-map:` ID, source and closure pins, producer hashes,
options, instructions, states, edges, frontiers, unclassified spans, coverage
and assumptions. The private canonical document is limited to 8 MiB.

The CLI uses the usual JSON protocol envelope (`ok` and `result`):

```sh
fdisbull chip8-source-map /private/analysis.fdb "$CLOSURE_ID" \
  --max-instructions 256 --max-states 2048 --max-call-depth 16 \
  --expected-intake-sha256 "$INTAKE_SHA256"
fdisbull chip8-source-map-info /private/analysis.fdb "$MAPPING_ID" \
  --expected-intake-sha256 "$INTAKE_SHA256"
```

The corresponding JSON methods are `chip8-source-map` with `project`, `closure`
and the same optional snake-case budget and pin fields, and
`chip8-source-map-info` with `project`, `mapping` and optional `version` and
`expected_intake_sha256`. Existing public address normalization applies: some
address/target fields in JSON and CLI replies appear as hexadecimal strings,
while Python records retain their native numeric values.

Replies default to a 65,536-byte output budget. For a larger bounded result,
choose a private artifact directory outside Git and a larger permitted reply
budget, for example:

```sh
fdisbull --max-output-bytes 1048576 --output-artifact-dir /private/fdb-output \
  chip8-source-map-info /private/analysis.fdb "$MAPPING_ID"
```

When an artifact directory is supplied, oversized responses can be inspected
and exported with the existing output-artifact tools. The output artifact is separate from the stored
source-map identity. Source-word maps, original ROMs, byte-bearing projects and
their private object stores stay outside Git and review uploads.

## Evidence and limits

Each classified instruction records its original PC, complete two-byte
big-endian word, file-relative span and SHA-256, decoded facts and a typed UDL
candidate. States include the PC and abstract return stack; edges retain their
kind, condition and assumption. A skip has both taken and fallthrough candidate
edges; odd or out-of-range successors remain explicit frontiers. These paths are conditional on the recorded assumptions,
not observations that the guest took them.

`coverage` reports classified and unclassified **source bytes**, worklist and
budget status. An unclassified span is unknown; it is not automatically data
or unreachable code. `budget_exhausted` and `worklist_exhausted` describe this
bounded traversal, not whole-program completeness or runtime coverage. The
frontier records unsupported or truncated instructions, odd or out-of-range
fetches, unresolved V0-indexed jumps and return/stack limits, symbolic I-based
memory and possible range faults, key waits, and other unfinished boundaries.
The whole 65,536-word classifier space is not claimed as source coverage.

A symbolic write through I may affect later source bytes. A successor after
such a write is conditional on both a nonfaulting write and subsequent fetches
still matching the original source words; it is not proof of self-modifying
execution. Active fetch or RAM overlays are not part of this original-source
view. For fault behavior, a fault of the **current** instruction is distinct
from an odd or out-of-range **next fetch** after current-instruction effects
have committed.

Typed descriptors retain candidate operands, may-read/write ports and effects,
including source-prestate operand capture and VF alias ordering; SP and the
16-slot stack; guarded I-relative RAM accesses; wait, framebuffer, timer and
RNG effects. Unknowns and environmental assumptions remain explicit. These are
`static-candidate` descriptions of the declared profile, not G3-qualified
semantics, independently verified G4 behavior, or executable common UIL.

An identical request may reuse its immutable map. Cold `chip8_source_map_info`
rechecks G0/G1 bindings, producer hashes, budget/options, source words and
spans, stored decoded fields and UDL candidates, and reconstructs the graph
from stored facts. It does not invoke the decoder or a live guest; reconstructing
the graph is still validation work. Missing or corrupt objects, stale producer
or source/closure bindings, and mismatched records refuse rather than silently
reusing them. DOSBox remains the default; this source-map step does not alter
DOS migration qualification or any native machine state.
