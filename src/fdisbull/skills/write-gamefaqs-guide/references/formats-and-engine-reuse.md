# File specifications, media and shared engines

Use this reference when writing the technical part of a reversing-first guide.
Explain what was recovered well enough for another reader to inspect the data,
understand a limitation or reuse a qualified result. A file inventory or a codec
name alone is not a format specification. A partial specification is useful when
its supported fields and unknown regions are explicit.

## Contents

- [Identify the actual layers](#identify-the-actual-layers)
- [Write an implementable partial specification](#write-an-implementable-partial-specification)
- [Specify media and its consumer](#specify-media-and-its-consumer)
- [Describe an interpreter or framework](#describe-an-interpreter-or-framework)
- [Transfer findings between games](#transfer-findings-between-games)
- [External examples and experiment boundaries](#external-examples-and-experiment-boundaries)

## Identify the actual layers

Keep the target's original files, external reimplementations and investigative
tools separate. Give each relevant layer its own identity and evidence:

| Layer | What to identify |
| --- | --- |
| Distribution | Installer/archive/disc layout and extracted member identities. |
| Native executable | Image format, ISA/mode, loader/packer/extender and loaded mapping. |
| Game runtime | Shared engine/framework routines, native game-specific logic and platform drivers. |
| Interpreted content | Script/bytecode dialect, interpreter revision, dispatch and native service boundary. |
| Resources | Indices, volumes, object tables, text, images, music, video and save data. |
| Playback | The actual decoder/player instance, completion signals and calls into game state. |

An executable may combine native routines with interpreted game scripts. A DOS
extender identifies an execution/loading layer, not a game scripting language.
Machine-code disassembly does not establish that the original source was
handwritten assembly. An engine label inferred from signatures remains a lead
until the relevant structure or behavior is connected to the selected input.

Say whether interpreter code is linked into the game executable, supplied in a
separate executable/module, or only present in the external tool used to inspect
it. Support in an external reimplementation does not establish that its code is
inside the original. Do not present an external decoder's feature list as
capabilities recovered in the original.

## Write an implementable partial specification

Give the format/profile name, inspected releases, input identities, naming and
lookup rules, and the evidence behind the profile. Use a field table rather than
burying byte layout in prose:

| Offset or location | Width/count | Representation | Meaning and constraints | Evidence/status |
| --- | --- | --- | --- | --- |
| Exact expression and its base | Bytes/bits or derived size | Endianness, signedness, encoding, units | Interpretation, flags and valid relationships | Claim ID/locator; recovered, external or unresolved |

Populate this with actual known fields; do not invent a generic header to fill
the template. Cover relevant structures and their relationships:

- Signature, version/variant discrimination, header size, alignment and padding.
- Directory/index entries, resource IDs, volumes, aliases, missing-entry markers,
  offset bases, counts, lengths and whether sizes include headers or terminators.
- Nested chunks, ordering, dependencies and references outside the current file.
- Compression/encryption boundaries and transform order, decoded size, bit order,
  dictionary/state reset rules and checksums when established. Naming an
  algorithm does not establish its variant or parameters.
- Payload grammar and semantics: opcode/operand lengths, text encoding, image
  planes, sound events or save-state fields, as far as recovered.
- Range/overflow constraints, truncated input, unsupported variants and malformed
  records. Describe original-reader tolerance separately from a new parser's
  intended rejection policy.
- Unknown/reserved bytes, unresolved flags and unmapped tails. Preserve them;
  failure to interpret a region is not evidence that it is padding or unused.

Trace the file offset through extraction, decompression and runtime mapping when
an address is part of a claim. Keep raw and transformed offsets distinguishable.
Give a small authored example or sanitized field walk-through when it clarifies
the rules. Identify which bytes and relationships it exercises; an authored
fixture is not an original-game witness. State reader/tool revisions and whether
checks covered structural parsing, decoding, original loading or actual use.

Do not claim a round-trip writer or modification is valid merely because a
reader can parse the unchanged file. In-place replacements may also affect an
outer archive's lengths/index, signatures, lookup order or disk-placement rules.
Report unresolved writer obligations without withholding the useful read spec.

## Specify media and its consumer

Separate container structure, codec/event representation and the original
playback contract. Record the media's role: visual sequence, speech, music,
animation, palette/control data or a mixed stream. Explain any gameplay use of
frame boundaries, cues, subtitles, completion flags or duration.

| Concern | Details to preserve when known |
| --- | --- |
| Container | Header/chunk grammar, stream IDs, indices, counts, sizes, seek points and terminators. |
| Image/video | Dimensions, pixel/palette representation, keyframes, delta dependencies, frame disposal and initialization. |
| Audio/music | PCM sample format or event/synthesis model, channels, rates, block alignment, instruments/banks and stream interleaving. |
| Time | Timestamp/tick basis, variable durations, pause/speed effects and audio/video clock relationships. |
| Playback | Start state, looping/restart, EOF/error/cancel handling, waiting/polling and the event that unblocks progression. |
| Dependencies | Previous frames, shared palettes, external banks, script references and archive lookup/index updates. |
| Validation | Parser/decoder result, native-consumer evidence, retained effects and remaining unknowns. |

A MIDI-like event stream, sampled audio and animation frames need different
descriptions; do not call every media unit a frame. State the time basis before
converting frame/event counts into duration. A valid independently decoded file
may still fail the game's seek, synchronization or completion requirements.

For an authorized size-reduction appendix, document exactly what was retained
or removed and the measured byte savings. Keep originals and an identified
derivative. Structural acceptance and native playback/progression are separate
results. Arbitrary byte cuts, a renamed unrelated codec or an empty file do not
establish either result. No executable patch is implied by a media-only task.

Preserve unknown music duration and loop behavior. A very short or one-frame
music replacement could repeatedly finish and restart in a looping player,
possibly increasing CPU load; this is a risk unless observed in the selected
consumer. Locate the actual music instance's completion/restart/wait paths
before advising that shortening it is safe. A generic audio function is not that
identification. A duration-preserving low-data representation is an option only
after format and consumer qualification. If those obligations remain unresolved,
retain the original music and publish the partial specification and next test.

## Describe an interpreter or framework

Explain the division of responsibility in plain language, then give the evidence
needed to reproduce the identification. Useful findings include resource-load
call sites, dispatch tables, instruction fetch, operand decoding, branches,
script state, native callbacks and scheduler/save boundaries. Name unknown
indirect dispatch or native services explicitly.

Document the supported bytecode dialect and opcode coverage, argument encodings,
variable/flag/object models, call/return behavior, text/parser vocabulary and
relevant timing/RNG services. Keep discovered structures separate from analyst
names. A strings-only engine guess or several plausible opcode decodes is not
complete interpreter recovery. Conversely, publish a well-supported partial VM
model without requiring recovery of every renderer or driver first.

Separate data-defined game rules from native engine behavior and release-specific
patches. Explain where an apparent bug lives: game script, interpreter handler,
resource table, platform backend or external reimplementation. If evidence does
not locate it, say so. An engine fix can remove an exploit without changing game
resources; an identical interpreter can execute different scripts and routes.

## Transfer findings between games

Use a transfer matrix with one row per supported relation, not a claim that an
entire series is equivalent. Identify source and destination editions/platforms,
the reusable layer, correspondence evidence, differences, and the smallest
remaining qualification. Reuse a qualified decoder or semantic rule where it
applies; revisit only the affected boundary when a version differs.

Resource-format compatibility does not establish save compatibility, equal
routes, shared variable meanings, equal probabilities or transfer of an exploit.
Distinguish exact reuse, reuse with an identified adapter/variant, a hypothesis
to test and known incompatibility. Cite the original source once and retain its
lineage when several game guides use it. External implementations can suggest
discriminating checks, but their bug fixes and compatibility workarounds need
their own qualification against original behavior.

## External examples and experiment boundaries

This reference contains general authoring methodology. Concrete external
layout and related-game examples are in
[Engine source examples](engine-source-examples.md). **Before opening that
reference, check the investigation's information policy.** In a files-only pass,
use the supplied original evidence and leave external game facts unread until
a separately authorized comparison phase. Attribution after reading cannot
undo exposure during a restricted pass. The examples are optional; a useful
partial specification or transfer table does not require consulting them.
