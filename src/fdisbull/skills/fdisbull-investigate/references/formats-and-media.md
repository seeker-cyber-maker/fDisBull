# File formats, containers and media

Use this reference to qualify an input, diagnose a loading boundary, compare
editions or reduce media under an authorized task. These are investigation
procedures, not a promise that the installed tool supports every format.

Discover `media-modules` before building another reader. For missing-tool recovery,
shipped APIs and reusable format contracts, read [media-modules.md](media-modules.md).

## Contents

- [Keep each layer's identity](#keep-each-layers-identity)
- [Establish a bounded format contract](#establish-a-bounded-format-contract)
- [Investigate Mach-O ARM64](#investigate-mach-o-arm64)
- [Intake a batch or a later addition](#intake-a-batch-or-a-later-addition)
- [Reversible macOS UI observations](#reversible-macos-ui-observations)
- [Win16 NE, DOS/4GW LE, DOS audio drivers and Cortex-M flash](#win16-ne-dos4gw-le-dos-audio-drivers-and-cortex-m-flash)
- [Console ROMs, optical discs and mode-explicit decoders](#console-roms-optical-discs-and-mode-explicit-decoders)
- [Compare releases at the right boundary](#compare-releases-at-the-right-boundary)
- [Finalized AVI capture audits](#finalized-avi-capture-audits)
- [Reduce media through a valid consumer contract](#reduce-media-through-a-valid-consumer-contract)

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

When AGI or Z-machine guest instructions are present, prefer their explicit
source decoder module to treating the interpreter's native ASM as the story.
`decoder-modules` lists built-in capabilities; `module-analyze` is projectless.
An AGI LOGDIR/VOL container is validated structurally under a selected profile,
not an extension or automatic interpreter-version guess. Module snapshots and
resource-local locations have separate identities; retain both when linking
facts. Do not flatten a guest offset into the DOS interpreter's address space.

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

## Investigate Mach-O ARM64

Start with `identify` and `inspect --slice-arch arm64`; import the exact thin or
universal source into a private FDB with `--slice-arch arm64`. Run bounded
recursive `analyze`, then inspect `analysis-status`, stored disassembly and
candidate functions. `code-backings` can preserve the complete selected
4-byte native instructions and original-container offsets for a specific
entry. Fresh imports add candidate seeds from `LC_FUNCTION_STARTS` and unwind
offsets only when they resolve to aligned, file-backed executable code;
preexisting FDBs retain their earlier seeds. Keep the source hash, slice hash,
byte version, preferred address and runtime slide distinct. Reopen the FDB and validate source backings before
using them as evidence. An entry fixed point does not imply app-wide code
coverage, especially across Swift dynamic dispatch.

Where the installed methods include `ghidra-arm64`, use it for a source-bound
cross-check of caller-selected instructions. Its optional C listing is a
separate diagnostic, not a UIL lift. `macos-observe` explicitly launches an
exact source-bound executable to one LLDB breakpoint; do not treat that
single observation as a persistent debugger session or app behavior parity.
In a source checkout, `docs/MACOS_ARM64_ANALYSIS.md` has command examples and
the remaining SwiftUI-to-UIL requirements.

Run one bounded initial analysis, inspect pending work and follow the next
relevant frontier. Report instructions, candidate functions and cross-references
with the selected image, seeds, budget and tool revision. These counts do not
measure reachable coverage, semantic recovery or comparative speed. Do not
repeat an identical exhausted pass without a new seed, mapping or question.
Use [methodology.md](methodology.md) for native-to-resource or interpreter links.

## Intake a batch or a later addition

Use the same per-artifact checks for a collection and one additional game.
Inventory the outer sources first, then retain every archive/filesystem/codec
edge to the selected program. Record source and output hashes, reader/options,
roles, attributed edition/language labels, capability observations and unknowns.
Keep learner inputs separate from source/test oracles; record later oracle use.
An exact existing payload adds a provenance alias and a receipt rather than
another binary or an invented version.

Stage each candidate in a new private directory, verify its complete intended
output set, and register only accepted payloads. Unsupported or partially read
members keep explicit status without hiding useful intake of other members.
One writer maintains the shared selected-program roster/archive and verifies
earlier entries plus new member hashes. Keep source media and original bytes;
program-only deliveries exclude movies, full installers, oracles and databases.
Nonstandard guest programs need reviewed explicit selection, not suffix guessing.

Keep received, catalogued, extracted, mapped, analyzed, runtime-observed and
contract-qualified as separate observations. A recognized unsupported format
is still a catalogued input. Identify the missing seam: archive/filesystem,
codec, container loader, ISA/mode/endian processor, guest language or consumer.
Reuse the existing ISA decoder when only the container changes. Do not force an
unknown format through raw x86 or call a decompressed file a qualified process.
Implement/qualify missing readers with bounded structures and authored valid,
truncated and unsupported examples before promoting their support status.

Preserve an independently supplied revision as a new original artifact/project.
`Project.patch` makes a child mapped-byte version; it does not import/remap an
arbitrary new release. NE/LE memory patches do not reconstruct their containers.
A selectable UDL layer is another concept: it realizes a fixed logical contract.
Source-backed claims retain exact captures; domain/adapter requirements depend
on the backend. Authored UIL/C/service profiles can omit native snippets.
Keep unresolved notes in supported evidence fields or a relation's `unknowns`,
not an invented layer field. Registration/selection is not proof. Admit a replacement only
to the appropriate qualification scope. A bug fix changing admitted outputs/effects needs a revised
contract/UIL or explicitly chosen policy; do not relabel it as exact equivalence.

For major rewrites or new ISAs, keep separate projects and link only supported
small counterparts. Similarity is a triage lead, not admission. Shared resource
payloads do not establish code equivalence. Candidate links are authored claims;
they do not inherit proof transitively. See `udl-uil-udc.md` for
the actual supported backends and the source/model/native qualification edges.
The source checkout's `docs/TARGET_COLLECTION_INTAKE.md` gives the full workflow
and decision tables; no universal batch-intake command is implied here.

## Reversible macOS UI observations

When the installed catalog includes `macos-snapshot`, inspect the running app,
permissions, displays and target accessibility state before choosing an action.
`macos-session` without `live` observes/captures only. Explicit `live` and a
selected status index permit a bounded menu action and declared preference
changes; the session never launches or quits the app. Keep one controller.
Choose the display ID and CoreGraphics global logical rectangle from the
snapshot, including negative origins. PNG pixels and image-local coordinates
are different spaces. Preserve display identity, scale, AX and PNG receipts.

Inspect delivery and observed effects separately: an AX error can follow a
successful menu opening. Do not replay an uncertain input. Read cleanup and
the durable journal; use `macos-session-recover` explicitly after interruption.
Conflicts, stale process identity or unknown menu state remain unresolved.
Exact key absence restores by deletion; CFPreferences domain coverage does not
establish sandbox or cached-UI equivalence. Keep private captures/journals out
of publication. Compare original and replica labels/geometry/effects with
declared metric drift, preserving binary facts versus source assistance and
observations. In source, see `docs/MACOS_REVERSIBLE_CAPTURE.md` and the bounded
`docs/CPUINFO_REPLICATION_COMPARISON.md` experiment.

## Win16 NE, DOS/4GW LE, DOS audio drivers and Cortex-M flash

Supported Windows16 NE images can be imported directly with automatic selection
or `--image ne`. Use explicit logical addresses such as `ne:4:0x547c`; a segment
index is neither a live selector nor a DOS paragraph. Source bytes and raw
operands stay intact while validated fixups supply symbolic logical targets.
Keep declared zero fill, initialized file data and runtime-initialized state
separate. Query stored native facts/CFGs; selector-aware advanced IR and native
Win16 execution remain unsupported. In a source checkout, `docs/NE_LOADING.md`
details the bounded profile and `docs/COLONIZATION_FOOD_EQUIVALENCIES.md` records
a paired source-model comparison with explicit ABI limits. Persistent snippet
links and selectable UDL backings have a bounded prototype described in
[udl-uil-udc.md](udl-uil-udc.md); storing a candidate relationship does not qualify
a backing or expand the native acceptance profile.

For 32-bit DOS/4GW linear executables (`--image le` or automatic selection),
keep the outer DOS stub distinct from mapped LE objects, page tables, entry
context and validated 16/32-bit fixup records (`docs/dos4gw-le.md`). Do not
flatten uninitialized BSS pages into file offsets or equate static object bases
with live DOS extender selectors until runtime placement is observed.

Miles AIL 2 `.ADV` audio drivers dispatch by function number rather than standard
MZ/LE entry headers; import them with `--image ail` so handler seeds and driver
descriptor metadata remain explicit. Use `dos-services` to inventory INT 21h,
10h, 16h and 33h calls alongside INT 66h DIGPAK/MIDPAK vectors, keeping
unresolved register selectors unknown (`docs/DOS_AUDIO_DRIVERS.md`).

Static Armv7-M Cortex-M flash images decode Thumb/Thumb-2 code from an explicit
flash base and vector table (initial SP plus odd Thumb handler entries and
literal pools). Keep memory-mapped peripheral reads/writes, NVIC priorities and
interrupt timing unresolved without hardware or trace evidence (`docs/CORTEX_M.md`).

## Console ROMs, optical discs and mode-explicit decoders

Use projectless `rom-inspect` for NES (iNES/NES 2.0), Genesis/Mega Drive, SNES
(LoROM/HiROM scoring), Game Boy, GBA and N64 headers, and `disc-inspect` for
CUE/BIN or ISO 9660 images (including Sega Saturn system IDs and directory
extents). Container headers, checksums and mapper IDs describe packaging only;
an advertised multicart title count does not establish distinct playable games
(`docs/NES_MULTICART.md`).

For Sega Saturn Hitachi SH-2 binaries, `rom-disasm` compares independent
disassemblers at an explicit mapped base so decoder disagreements remain visible
(`docs/ROM_ASM.md`). For SNES 65C816 code, `fdisbull.snes_decode` requires
explicit `m` and `x` processor-status flag widths because immediate operand byte
lengths change with accumulator/index mode; keep LoROM bank-`80` mirrors and
WRAM (`7E`/`7F`) boundaries explicit (`docs/SHADOWRUN_SNES_MACOS.md`).

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

## Finalized AVI capture audits

Inspect a useful frame first when gathering a visual lead. For recording
integrity, completeness or timing claims, run projectless
`capture-audit` (`ffprobe`/`ffmpeg`) against finalized AVI segments into a new
private output directory (`docs/TAS_CAPTURE_AUDIT.md`). It hashes input files
and decoded RGBA frames, flags stream parameter drift, duplicate/dropped frames
and segment joins, and optionally samples PNG frames or an HTML contact sheet
(`--every`, `--html`). Keep video frame indices and container timestamps separate
from guest CPU ticks, deterministic input logs and unverified RAM state.

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
