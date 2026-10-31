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
logic-load, and print actions. Unsupported opcodes terminate that path without
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

## Whole-resource scene census

Use the separate [AGI scene census](AGI_SCENE_CENSUS.md) to inventory all present
LOGIC resources, message/vocabulary/inventory data, typed scene references and
unresolved dependencies before qualifying complete interactions. Its `outline`
stage collects source structure; `resolve` adds bounded local value analysis.
The existing `agi-logic` API and its partial-decoder contract remain unchanged.
The census retains structural low-level IR and accepts no executable UIL.
