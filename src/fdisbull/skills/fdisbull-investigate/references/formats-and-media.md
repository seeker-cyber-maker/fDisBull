# File formats, containers and media

Use this reference to qualify an input, diagnose a loading boundary, compare
editions or reduce media under an authorized task. These are investigation
procedures, not a promise that the installed tool supports every format.

## Contents

- [Keep each layer's identity](#keep-each-layers-identity)
- [Establish a bounded format contract](#establish-a-bounded-format-contract)
- [Compare releases](#compare-releases-at-the-right-boundary)
- [Reduce media](#reduce-media-through-a-valid-consumer-contract)

## Keep each layer's identity

Record the supplied container and relevant members: names, sizes, hashes,
edition/language, reader version, extraction options and transformations.
For multipart installers, retain the identity of every participating part.
Prefer a qualified reader that lists and extracts data without executing an
installer. Use a new private destination, check the actual extracted inventory
and keep originals intact. Discover optional extraction commands in the installed
version before using them; successful extraction does not establish game or
executable-loader support.

Distinguish container format, executable image, instruction set and mode,
packer/extender, runtime address space, and any interpreted guest language.
A DOS stub may lead to a different protected-mode image; a file suffix may name
a driver or resource rather than its executable format. A compression or
relocation problem belongs to loading/mapping, not automatically to instruction
decoding. Reuse the existing ISA processor when only the container changes.

Keep a mapping record for file offsets, loaded object/section addresses,
zero-filled ranges, relocated bytes and runtime selectors or generations.
Do not disassemble a wrapper as though it were the main image. Keep alternate
views explicit. Static preferred addresses are not observed runtime placement.
Preserve unmapped tails: an appended range may hold overlays, debug records,
resources or another format. Strings and plausible opcodes are leads; trace the
loader or interpreter before calling a range executable.

## Establish a bounded format contract

Start with the smallest representative structure that explains the target:
header and version, table bases, counts, sizes, byte order, alignment, entry
point and relocation semantics. Check every derived range against the actual
container and the declared image. Distinguish file-relative, header-relative,
page-relative, object-relative and signed offsets; do not infer a base from a
single convenient example.

When implementing or qualifying a reader, exercise authored normal, truncated
and unsupported variants. Bound counts and allocation sizes. Refuse unsupported
page encodings, fixup kinds or inconsistent duplicates explicitly. Compare
mapped bytes with a separately derived reader or qualified original loader where
possible; preserve shared parser/specification dependencies in the comparison.
Report static mapping qualification separately from native execution; a
loader-only task need not launch a game.
Record raw records and unique applied writes separately when a boundary-spanning
fixup can appear more than once.

Run one bounded initial analysis, inspect pending work and follow the next
relevant frontier. Report instructions, candidate functions and cross-references
with the selected image, seeds, budget and tool revision. These counts do not
measure reachable coverage, semantic recovery or comparative speed. Do not
repeat an identical exhausted pass without a new seed, mapping or question.
Use [methodology.md](methodology.md) for native-to-resource or interpreter links.

## Compare releases at the right boundary

Match the actual editions and resources before treating files as counterparts.
Retain the exact byte diff, then compare mapped instructions, control/data flow
and the relevant behavior. Explain normalizations such as relocation or layout
changes and retain what they hide. A semantic match at one register boundary
does not establish matching text, assets, timing, save formats or all paths.

If a supplied patch is part of the question, inspect its source/target identity
checks and operations as evidence. Verify reconstructed outputs against its
declared destinations when possible. A patcher's intent is not by itself proof
of the affected game's behavior; unsupported operations remain unresolved.

## Reduce media through a valid consumer contract

Inventory media by role before shrinking it: cutscene, voice, music, animation,
palette/control data, or a mixed stream. Follow references from scripts and
containers so an apparently visual asset is not silently discarding logic,
subtitles, synchronization events or a required completion signal.

Use a disposable derivative and change one qualified resource at a time.
Understand the actual format before truncating: header lengths, frame/chunk
counts, table offsets, keyframe and palette dependencies, stream terminators,
audio alignment and any surrounding archive index. Keep filename/lookup
identity where the consumer requires it. Produce the smallest valid retained
sequence only when its dependency and end-of-stream rules are known; arbitrary
byte cuts, zero-byte placeholders or a renamed unrelated codec are not evidence
of valid media.

Validate both levels separately: a structural parser/decoder accepts the
derivative, and the original consumer reaches the intended post-playback state
through ordinary input without losing required effects. Compare an unchanged
control and retain enough state, output and timing evidence to diagnose a
failure. When execution is unavailable, report structural validity only.

Preserve audio duration and loop behavior by default. A one-frame or very short
music stream may immediately finish and be reopened repeatedly by a looping
player, potentially increasing CPU load. Treat that as a risk to investigate,
not an observed failure without evidence. Smaller files and successful decoding
do not establish safe playback. Duration-preserving low-data audio is an option
only for a qualified format and consumer.

If shortening music is necessary, locate the selected player's completion,
restart, polling and wait paths. Use bounded, comparable playback trials to
observe loop counts, guest/wall time and host CPU where available. CPU differences
need matched instrumentation and meaningful intervals. Keep original audio when
the player contract cannot be established; finding a generic sound routine is
not identification of the music instance. Media-only work does not imply
permission to patch the game's executable.

Keep a compact derivative manifest with source/output identities, changed
ranges or members, byte savings, preserved/removed content, validation evidence
and unresolved consumer behavior. Preserve the original for reversal. A useful
size reduction is a measured result under this contract, not a substitute for it.
