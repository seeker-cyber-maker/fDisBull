# File formats, containers and media

## DOS executable triage: bytes, loader, runtime and game engine

Read this before proposing a replacement DOS stub or diagnosing a missing extender.
Identify the **exact bytes** first: installer/container, extracted original file,
static loaded image, or runtime dump. Record size/SHA-256 and the first bytes from
the actual file. A compact output-artifact receipt is not the inspection result:
use `output-info`, `output-read` or `output-select` when the tool returns an artifact.
Do not interpret truncated console output as a missing MZ header.

Keep four identities separate: file container (MZ/LE/etc.), CPU execution mode,
runtime services (DOS/extender/overlay manager), and game engine (MADS/Kyra/AGI/etc.).
A common engine label does not imply common native code or script syscall tables.

| Evidence | Interpretation and next check |
| --- | --- |
| Headerless small file | Possible COM, raw code or data; not automatically COM. COM has no magic and uses a PSP-relative entry at 0100h. Use explicit `--image com` only after identifying its role. |
| `MZ` at file offset 0 | Validate DOS header size, page count, relocations and entry before selecting a loader. MZ alone does not distinguish real-mode code from a protected-mode stub or a Windows executable. |
| `ZM` at offset 0 | Historical reversed DOS signature, not proof of corruption. Recognition and loader support are separate; this canonical MZ loader does not admit it. Preserve source and report that boundary rather than silently rewriting bytes. |
| Valid secondary `NE` | Segmented New Executable, commonly Windows/OS/2. Check its target-OS field and segment/entry tables, not just the letters or extension. |
| Valid secondary `LE`/`LX` | Linear executable, potentially DOS-extender/OS/2/VxD code. Validate the object/page/fixup tables and executable context. The format alone does not establish DOS/4GW or DPMI compatibility. |
| Valid `PE\0\0` | Validate COFF/optional header and sections. The MZ front may be a DOS stub while the main program targets Windows. GOG installers are not the DOS game inside them. |
| Appended MZ bytes | Preserve them. They may be overlays, resources, a packed image, another executable or padding; the tail is not all proven code and is not safely discardable. |
| `.BAT` / configuration | The launch contract: command order, arguments, current directory, environment and disc mounts. Read it before launching an arbitrarily chosen EXE. |
| `.OVL`, `.DRV`, `.COM`, `.DAT`, extensionless | Filenames are hints, not formats. A sound driver can be MZ; a DAT can be bytecode, a resource archive or a CD image; an extensionless program can still be an MZ. |
| DOS device-driver header | A SYS driver has a device chain, attributes and strategy/interrupt offsets, not necessarily an EXE header. OMF OBJ/LIB records are linker inputs, not runnable COM files. |

### MZ arithmetic and the 0x3c trap

Read little-endian fields: `e_cblp` at 02h, `e_cp` at 04h, `e_crlc` at 06h,
`e_cparhdr` at 08h, `e_ss:e_sp` at 0Eh:10h, `e_ip:e_cs` at 14h:16h and
`e_lfarlc` at 18h. The declared extent **includes the header**:

```text
header_bytes = e_cparhdr * 16
declared_bytes = e_cp * 512                         when e_cblp == 0
               = (e_cp - 1) * 512 + e_cblp         otherwise
resident_file_bytes = [header_bytes, declared_bytes)
appended_bytes = [declared_bytes, actual_file_size)
relocation_site = header_bytes + segment * 16 + offset
```

Validate `e_cp > 0`, legal last-page byte count, the entire relocation table within
the header, each relocated word within the loaded module and the file extent. DOS
relocation adds the chosen load segment to each specified word; file offsets are
not runtime physical addresses. Entry CS is load-relative. A runtime real-mode
address is `segment*16+offset`, subject to A20/wrap and the tool's supported bounds.
A loaded-module dump may correctly have no MZ header: DOS loaded the module, not
the file header. 386 registers or size-override prefixes alone do not establish
protected mode. The header's `e_ovno` word is not a universal overlay directory.
CS:IP, PSP, file offset, load-relative address and protected-mode selector are not
interchangeable. A protected-mode selector is not multiplied by 16 like real mode.

**Do not unconditionally read 0x3c as `e_lfanew`.** Old MZ headers can begin their
relocation table at 1Ch or 1Eh; relocation data can occupy 3Ch. Check the canonical
secondary-header detector's structural prerequisites, then validate the pointed
header. Random `LE`/`LX` strings anywhere in code do not identify that file format.
A valid modern DOS stub can have zero relocations; that is not proof of COM or a
particular packer. Do not “repair” a declared image size to swallow an unexplained tail.

### Overlay managers are not DOS extenders

An overlay manager loads banks into reusable address ranges under a resident
program. An extender supplies protected-mode execution/services. Executable
compression is a third mechanism. These can coexist; identify each independently.
RTLink signatures plus a validated bank directory support overlay analysis, not
adding DOS4GW. Likewise a DOS4GW string is a clue, not a proven missing dependency.
Require launch documentation, an actual loader error or verified code/container
structure before changing runtime prerequisites. Never fabricate or prepend a
stub, rename arbitrary files to DOS4GW, or patch original headers to make a
hypothesis pass. A stub cannot infer an unknown payload's ABI.

For supported embedded RTLink v2, the shipped Python reader needs no external
`rtlink_decode` executable. Discover `fdisbull-dos methods`, then use:

```sh
fdisbull-dos rtlink-inspect /private/DRAGON/SPHERE.EXE
fdisbull-dos rtlink-disasm /private/DRAGON/SPHERE.EXE --overlay 16 --offset 0xce --count 32
fdisbull-dos rtlink-export /private/DRAGON/SPHERE.EXE /private/new-analysis-view
```

The same entrypoint is `python -m fdisbull.dos_tools`. Inspection records table IDs,
original ranges/hashes, relocation sites, and guarded thunk candidates. Export
creates `analysis-flat.bin` plus `rtlink-map.json`, **not a runnable EXE**. It does
not apply relocations or resolve every cross-bank reference. Alignment zeros are
labeled synthetic; absent final-paragraph bytes remain explicitly unbacked. Unknown
external OVL/RTLINKST layouts refuse. Never claim full upstream RTLink-tool parity.

Key an overlay observation by source hash, bank ID, generation and observed load
binding, not just a reused CS:IP. Static descriptor load paragraphs are not proof
of a currently loaded bank. Breakpoint the resident loader or qualified thunk,
observe the read/relocation, then bind the runtime bytes. A flattened analysis
address must never be sent directly to the live debugger as a guest address.

### Reproduce the launch contract before diagnosing a format failure

The standard tool's DOS session launch initially passed an empty command tail.
The additive `fdisbull-dos debug` route exposes explicit arguments/CD configuration
while retaining the ordinary debugger JSON operations, evidence store and owned
process cleanup. It does not alter flags of `fdisbull debug` on older installations.

```sh
fdisbull import /private/DRAGON/MAINMENU.EXE /private/mainmenu.fdb
fdisbull-dos debug /private/mainmenu.fdb --executable /private/backend/dosbox \
  --game-dir /private/DRAGON --argument=-p --cd-image /private/GAME.INS
```

`--argument` is repeatable; use `--argument=-p` for a switch. This profile supports
bounded unquoted ASCII tokens, not arbitrary shell syntax/quoting. C: is the
explicit game directory. D: is an explicitly selected, read-only .cue/.ins/.iso.
There is no guessed CD search or shell-command passthrough. The supplied .INS is a
CUE alias; one- or two-digit TRACK/INDEX numbers are accepted through the same
validator. `fdisbull disc-inspect GAME.INS` reads the referenced data tracks directly.

Retain neighboring drivers/resources and verify CD paths and ISO contents. An IDX
can be an index into a HAG archive on the CD, not missing code. Host working
directory, guest current directory, C: root and D: media are different concepts.
The controlled backend starts without user autoexec; custom BAT/environment setup
must be explicitly qualified separately. A startup mount request is recorded as
intent, not automatically certified successful: verify guest filesystem access or
an actual game observation. Preserve owned source files; run games in private
copies because they can write configuration and saves.

For a held frame after changing memory, distinguish backing state, cached/derived
state and the next presented frame. A native save/load can rebuild state through
the game's own path, but a screenshot immediately after restore may still be
unavailable. Use explicit bounded frame readiness, not repeated blind input.
A successful menu boot proves that path only, not all overlays or a full playthrough.

References: Ralf Brown's DOS EXE header table
(https://www.delorie.com/djgpp/doc/rbinter/it/94/15.html), Microsoft's PE/COFF
specification (https://learn.microsoft.com/en-us/windows/win32/debug/pe-format),
and the ScummVM developer's RTLink research tool
(https://github.com/dreammaster/tools/tree/rtlink_decode/rtlink_decode).
Implementation and source-provenance details are in the repository document
`docs/DOS_FORMATS_AND_RTLINK.md`; this installed reference is self-contained.


Use this reference to qualify an input, diagnose a loading boundary, compare
editions or reduce media under an authorized task. These are investigation
procedures, not a promise that the installed tool supports every format.

Discover `media-modules` before building another reader. For missing-tool recovery,
shipped APIs and reusable format contracts, read [media-modules.md](media-modules.md).

## Contents

- [DOS executable triage](#dos-executable-triage-bytes-loader-runtime-and-game-engine)

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

Before inspecting individual pixels or citing a recorded run, run projectless
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
