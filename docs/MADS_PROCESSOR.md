# MADS conversation processor

`fdisbull.mads.conversation` is a registered guest processor using the same
`DecoderRegistry`, `ProcessorInfo`, `Location`, `DecodedInstruction` and bounded
`module-analyze` traversal as AGI, Z-machine and Westwood EMC2. It decodes real
MADS conversation instructions. It is **not a standalone MADS game engine**.

## Layers and supported input

Keep these layers separate:

- Native DOS scene/game logic: the existing x86 decoder and separately identified
  RTLink overlays. A container or studio name does not turn native code into VM code.
- HAG (`MADSCONCAT 1.0`): indexed named resources, including the CNV/CND pairs.
- MADSPACK 2.0: a fixed directory of up to 16 stored or FAB-compressed sections.
- CNV: seven sections describing conversation nodes, dialog records, messages,
  text offsets/text data and an encoded command section.
- CND: initial/default conversation variables, entry flags and imported variable
  slots. Stored host workspace and pointer-looking words are not live pointers.

The initial corpus is the privately supplied Dragonsphere 1.01 CD. Other games,
localizations and engine revisions require their own intake. The profile name
`mads-cnv-v1` versions this decoder contract, not the complete original MADS engine.
The resource readers are reusable independently of the conversation processor.
Local `.IDX` files are not substitutes for the `.HAG` payloads on the CD.

## Use the existing module interface

Discover the installed implementation rather than assuming a version label:

```sh
fdisbull decoder-modules
fdisbull module-analyze fdisbull.mads.conversation /private/CONV001.CNV
fdisbull agent-skill --reference references/media-modules.md
```

The direct command analyzes dialog 0. Select other dialogs and archive members
through the existing projectless JSON interface; no generic CLI change is needed:

```json
{"method":"module-analyze","params":{"module":"fdisbull.mads.conversation","path":"/private/GLOBAL.HAG","member":"CONV001.CNV","function_index":3,"max_instructions":80}}
```

`member` can also be an integer HAG directory index in the JSON/Python API.
Duplicate case-insensitive names refuse name selection instead of silently
choosing a payload. The source archive identity and selected directory index
remain in the provenance. A standalone CNV also works without `member`.

Resource overviews and explicit selection are available through a module CLI:

```sh
python -m fdisbull.mads_processor inspect /private/GLOBAL.HAG --kind hag
python -m fdisbull.mads_processor inspect /private/GLOBAL.HAG --member CONV001.CNV
python -m fdisbull.mads_processor inspect /private/CONV001.CND --kind cnd
python -m fdisbull.mads_processor analyze /private/GLOBAL.HAG \
  --member CONV001.CNV --function-index 3 --max-instructions 80
```

`HagArchive.select()` returns the selected record and immutable payload bytes;
`MadsPack.read()` exposes immutable decoded sections. No source is executed,
modified or written by these readers. They do not install or launch ScummVM.

## Instruction facts and control flow

The decoder recognizes commands 0 through 9 and 255, their exact encoded spans,
conditional-expression records, flag-entry lists, weighted message references,
speech IDs, assignment destinations and GOTO offsets. All supported expression
operation IDs and signed 16-bit operands are retained. Variable access summaries
are encoded references, not observations of live host variables.

Every opened input is bound to the CNV hash, decompressed command bytes, selected
dialog, compression provenance and optional archive occurrence. Addresses are
**byte offsets within decompressed CNV section 6**, not physical compressed-file
positions, x86 CS:IP, overlay-relative offsets or live interpreter pointers.
The processor parses the selected declared dialog range and follows only known
instruction boundaries there. It does not scan arbitrary resources for opcodes.

GOTO exposes both the branch and fallthrough without evaluating its predicate.
A target in an operand or another dialog remains unresolved. NODE can finish the
current script or fall through. END/error are local terminal operations;
DIALOG_END retains an unresolved engine-control edge because its execution
semantics have not been qualified. Exhausted instruction budgets remain incomplete.
`complete` means the selected static edges were covered, not that a dialog is
reachable, a predicate is satisfiable, the game runs, or an engine is equivalent.

There is deliberately no condition evaluator, guest execution, native callback
binding, live debugging sidecar, save-state support or UIL lifter in this change.
In particular, do not infer arithmetic behavior from an upstream enum label.
The reviewed old reference has expression-name/implementation discrepancies
(including comparison and Boolean labels) and unfinished conversation methods.
It supplies format evidence, not an original-runtime behavioral oracle.

## Defensive parsing

Inputs are bounded regular files or immutable byte snapshots. HAG sources are
limited to 128 MiB, selected resources to 16 MiB, total expanded MADSPACK data to
32 MiB and command offsets to the 16-bit CNV space. Index extents, counts,
section lengths, backward references and final decoded lengths are checked.
Partially overlapping HAG ranges refuse; exact aliases retain separate identities.
Path-like/control-character names refuse. No automatic input-driven Python imports
or external executables are used.

FAB controls are consumed least-significant-bit first. On the last bit of a
control word the next word is prefetched before command payload bytes. Copies
may overlap previously produced output. The extended length is byte-sized in
this profile, including the reference's wrap at 255. Source tails remain explicit
metadata, not fabricated padding. Unknown codecs/opcodes/expressions refuse.

CND's first count fields and referenced sections are validated, while the rest of
its serialized runtime workspace stays opaque. Arbitrary words in that workspace
must not become allocations, host pointers or claimed live game state.

## Qualification and next gates

Authored tests use invented resources and explicit compressed token streams.
They cover every command encoding and supported expression ID, control-word
refills, overlapping copies, corruption, invalid targets, source drift, duplicate
names, bounded traversal, refusal to lift and the real projectless JSON/CLI.
A `python -S` test verifies that decoding needs no optional native decoder.

Private corpus checks are distinct: decode every CNV dialog; inspect each matching
CND; retain aggregate counts and source hashes outside Git. Do not commit original
assets, decoded text, command-byte listings or source-retaining analysis databases.
The generic analyzer's `facts.bytes` contains original-derived target bytes and
therefore belongs in private evidence, not public reports.

Before release, qualify the exact combined source and installed artifacts. A
native interpreter breakpoint/trace comparison is still required before assigning
runtime semantics or translating complete conversations into executable UIL.
Keep the existing release owner's doctor/build-identity priority and CI gates.

## Source references and licensing boundary

The source consulted is ScummVM **v2.8.1**, not a claim about its current release:

- `engines/mads/resources.cpp`, blob `f5debd0a6702c866adea761c4df790960f425d6d`:
  https://github.com/scummvm/scummvm/blob/v2.8.1/engines/mads/resources.cpp
- `engines/mads/compression.cpp`, blob `c78de8d7c5bdd1f4916d9f0b4b83bd11a2c970d6`:
  https://github.com/scummvm/scummvm/blob/v2.8.1/engines/mads/compression.cpp
- `engines/mads/conversations.cpp`, blob `21b98f45e3df76fc4dcffdcf866082f3d26e1cd4`:
  https://github.com/scummvm/scummvm/blob/v2.8.1/engines/mads/conversations.cpp
- `engines/mads/conversations.h`, blob `1adf75bd124e61a31c18d02678bc75feadabbf0a`:
  https://github.com/scummvm/scummvm/blob/v2.8.1/engines/mads/conversations.h

This is newly authored Python informed by that GPL-licensed source and original
resource measurements, **not a clean-room claim or licensing clearance**. Review
possible derivative obligations and repository license compatibility before public
integration/release. No upstream runtime or game assets are bundled.
