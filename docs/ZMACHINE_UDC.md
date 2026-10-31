# Z-machine v3 source-backed experiments

This standalone Python scaffold captures a checksum-qualified v3 story snapshot
and emits either its byte-identical baseline or a narrowly admitted scalar
instruction experiment. It does not run a story or prove behavior. Story bytes,
definitions, emitted results and private evidence belong outside Git.

```python
from fdisbull.zmachine_udc import capture_zmachine_definition, compile_zmachine_definition

# Read a user-owned story into immutable bytes in a private workspace.
definition = capture_zmachine_definition(story_bytes, max_instructions=10000)
baseline = compile_zmachine_definition(definition)
experiment = compile_zmachine_definition(
    definition, mode='experiment', assumptions={'no_code_data_alias': True, 'scalar_values_not_addresses': True},
    edits=[{'offset': 900, 'expected_hex': '14010210',
            'replacement_hex': '14010310'}])
```

The offsets and bytes here are from an authored test fixture, not a game.
The methods return hex bytes and identities; they do not write files. Capture
binds the entire source including trailing padding, source SHA-256, v3 version,
bounded instruction catalog and definition digest. Every compilation rebuilds
and checks the catalog and source checksum. The digest detects accidental
corruption; it is not an authentication signature against a party replacing
and resealing the whole source.

The catalog follows only the initial PC's straight-line decoded fallthrough,
up to the budget or the first control transfer, decode error, known table or
high-memory boundary. A catalog entry is a candidate instruction, not proof
of reachability or ownership. Header, dynamic memory, dictionary, abbreviation
table and padding are excluded. Other data/code aliasing can be undiscovered:
experiments require the caller's explicit `no_code_data_alias` and
`scalar_values_not_addresses` assertions. The latter covers changed inputs and
their result; neither assertion is proved by capture.

Each experiment identifies a distinct catalog instruction and its exact expected
old bytes. The current whitelist permits only long-form 2OP `add`, `sub`, `mul`,
`div`, `mod`, `or`, and `and`, changing one or both small scalar constants while
preserving opcode, operand kinds, store target and size. Variable selectors,
control flow, addresses, calls, packed pointers and other encodings cannot be
changed. The compiler recomputes the declared-image checksum, requalifies the
output and decodes each edited instruction again. Other bytes, including file
padding, are preserved. The source definition remains unchanged.

The output reports `unverified_experiment`, `equivalence_proven: false` and
`native_execution: false`; no behavior, effect, game compatibility or proof is
inferred from matching instruction shapes. The baseline reports
`original_bytes_only`. Variable-length placement, general reference discovery,
call/routine relocation and Z3 equivalence are outside this profile.

## Projectless CLI and JSON

`zmachine-udc-capture /private/story` returns the private immutable definition.
`zmachine-udc-compile /private/definition.json` returns its exact baseline.
For an experiment, add `--mode experiment --edits /private/edits.json
--assumptions /private/assumptions.json`. JSON methods have the same names;
capture accepts `path` and optional `max_instructions`, while compile accepts
`definition` or `definition_file`, plus edit/mode/assumption parameters.
Input JSON files are bounded to 4 MiB. No project database is required.

Definitions and output bytes use the normal output limits and artifact handles.
Retrieve/export the complete definition into a private location when the reply
is artifact-backed; a compact handle is not the definition itself. These
commands write no executable or story file automatically.
An output artifact for a captured CLI/JSON reply retains its reply envelope;
the definition is its `result` member. Export the reply privately and extract
that member into the definition file. `output-select` with
`/result/source_sha256` can retrieve its identity without expanding story bytes.
