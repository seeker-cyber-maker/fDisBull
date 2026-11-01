# AGI 2.917 logic inspection (partial)

`fdisbull agi-logic LOGDIR VOLUME_DIRECTORY LOGIC --profile 2.917` reads a
version-2 LOGDIR and uncompressed version-2 VOL resource and performs a bounded,
read-only traversal of one logic's bytecode. JSON-lines method `agi-logic` uses
`logdir`, `volume_dir`, `logic`, `profile`, and optional `max_instructions`.
No file is changed or added to a native project. Source hashes and volume offsets
identify the input; they do not prove a runtime load or host-to-guest mapping.

This is an intentionally partial static decoder, not an AGI interpreter or a
claim that a game is recovered. It recognizes return, signed goto, structured
condition lists (including variable-length `said`), and selected state, flag,
logic-load, direct/variable logic calls, print, and selected resource/object
action encodings. The latter have unmodeled effects. Calls retain a local
continuation and an unresolved cross-resource edge. Unsupported opcodes terminate that path without
inventing an instruction length. An out-of-range edge, malformed instruction,
overlap, or exhausted budget prevents `complete`; even `complete` means only
that the reachable paths of this bounded static subset were decoded, not that
runtime behavior or an entire game was verified. Logic calls, room changes,
messages, compression, v3 volumes, execution, and persistent guest analysis are
not implemented. Use explicitly qualified runtime evidence for actual behavior.

Encoding references: [ScummVM v2 resource loader](https://github.com/scummvm/scummvm/blob/master/engines/agi/loader_v2.cpp),
[ScummVM opcode setup](https://github.com/scummvm/scummvm/blob/master/engines/agi/opcodes.cpp),
and [AGI behavioral specification, logic bytecode](https://peterkelly.github.io/agi-re/spec/logic_bytecode.html).
The 2.917 profile is explicit and must be established independently for the
input. Tests use synthetic resources; no commercial game data is distributed.

The [direct decoder module](DECODER_MODULES.md) can capture explicit callees and
lift scalar conditions, acyclic branches and direct calls into shared UDL/UIL.
It requires cached scan-entry witnesses and complete coverage of the selected
source component. Explicit boundaries inside callees stop that component rather
than pretending the callee returned. Nominal scalar model verification and
original-interpreter execution remain separate evidence.

The opt-in compact lift retains one shared continuation per admitted source
location. `--allow-opaque` retains known action encodings in a control-flow-only
projection whose execution is refused. Unknown instruction widths are still
refused rather than guessed. See the decoder-module contract for API examples
and [the KQ1 structural verification](VERIFICATION-AGI-COMPACT-2026-10-31.md).
The separate [effect profile](AGI_EFFECTS.md) adds bounded object/resource model
operations and explicit host suspension; it does not turn static decoding into
original-engine execution.

## Whole-resource scene census

Use the separate [AGI scene census](AGI_SCENE_CENSUS.md) to inventory all present
LOGIC resources, message/vocabulary/inventory data, typed scene references and
unresolved dependencies before qualifying complete interactions. Its `outline`
stage collects source structure; `resolve` adds bounded local value analysis.
The existing `agi-logic` API and its partial-decoder contract remain unchanged.
The census retains structural low-level IR and accepts no executable UIL.
