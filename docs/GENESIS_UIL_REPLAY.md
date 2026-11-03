# Repeatable Genesis source → UIL → native console builds

The [Genesis performance follow-up](GENESIS_PERFORMANCE.md) supersedes the
first Genesis output and its speed measurements below. It keeps the same
procedural UIL and original-backed accuracy contract, with a faster renderer
and a verified native state-copy helper. The first-output hashes remain
historical evidence.

The Genesis UDC facade now exports an identity-bound replay bundle and compiles
the reviewed full Miniplanets procedural game to either NES or a new Genesis
cartridge. Game rules are emitted from the same typed UIL tree on both targets.
The NES build reproduces the previously qualified moving-gameplay ROM exactly.
The new Genesis build passed the same 4,822 original-backed controlled cases.

This is a reviewed source-bound specialization of Miniplanets REMIX REV04.
A different Genesis ROM can be parsed and inspected, but needs its own recovered
rules, resource interpretation and hardware adapters before it can use this
route. The registry reports an unsupported semantic profile for an unknown ROM.
There is no automatic whole-ROM recovery or whole-game equivalence theorem.

## The representation

The bundle contains five separately hash-bound documents:

| Document | Executable meaning | Native boundary |
| --- | --- | --- |
| game | Typed procedural GameIL, 79 mutable fields, rules for all 55 stages | Generated C compiled to 6502 or 68000 |
| audio | Parsed typed music/effect events and original logical sound state | NES arrangement or retained Genesis Sona device driver |
| presentation | Typed planner, dirty-span certificates, sparse clear, pending-buffer ownership and weighted upload chunks | Registered NES C/6502 specialization |
| psg | Typed period/phase mapping and volume/owner/pan selection | Registered NES C/6502 specialization |
| scene | Projection and resource bindings with exact source identity | Target display adapter and privately derived assets |

The new public [presentation UIL](../src/fdisbull/data/miniplanets_presentation.uil.json)
and [PSG UIL](../src/fdisbull/data/miniplanets_psg.uil.json) are actual validated
syntax trees. Their authored
[presentation](../src/fdisbull/game_sources/miniplanets_presentation_uil.c) and
[PSG](../src/fdisbull/game_sources/miniplanets_psg_uil.c) units contain no original
ROM payload. The loaders regenerate the typed trees, require equality with the
packaged artifacts, and bind source bytes read once to their hashes.

For example, the presentation module can be executed independently:

    from fdisbull.presentation_il import lift_presentation, presentation_machine

    document = lift_presentation()
    machine = presentation_machine(document)
    overlay = machine.call("presentation_classify", 0, 0, 0)

Its named operations classify overlays, clear only certified terrain
intersections, invalidate a terrain miss, prepare uploads and acknowledge
completion. The planner retains the 46 + 8 × bytes cost model and 1,218-cycle
chunk budget used by the qualified NES specialization. This logical budget is
not a new proof of PPU or DMC timing. Geometry and gain tables are constants;
the low-level diagnostic state setter is not an authorization to mutate them.

These planner and PSG documents specify the NES adaptations. The Genesis target
captures them for comparison and reproducibility, but uses its own VDP adapter
and original hardware sound driver. The complete console devices are not
modeled by those two UIL documents.

## Registered compiler modules

The permanent entry point is the [Genesis UDC facade](../src/fdisbull/udc_genesis.py):
translation_profiles, inspect_translation_source, write_translation,
inspect_translation_bundle and replay_translation. The bounded scalar compiler
keeps its existing contract. The common console-udc command also accepts the
full procedural GameIL document with either target.

The [replay module](../src/fdisbull/genesis_replay.py) binds the exact source
ROM, canonical documents, reviewed baseline/efficient procedure selections,
implementation sources, target recipe, compiler/runtime inputs and expected
native output. Mixed selections use known equivalent procedure bodies; they do
not introduce a general plug-in interpreter.

The [Genesis full-game backend](../src/fdisbull/udc_genesis_game.py) emits the
procedural UIL as C and compiles it with m68k-elf GCC using the base 68000,
16-bit int / 32-bit long model. New game code starts at cartridge address
0x80000. Startup, controller polling, state publication and VDP rendering are
authored adapters. Physical C maps to the normalized Select bit.

The original cartridge prefix from 0x200 through 0x7ffff is retained at its
original addresses so that the original Sona 68000 API, Z80 driver, streams,
instruments and PCM references remain valid. Unused original game code remains
in that prefix, and a separate immutable source copy supplies GameIL ROM reads.
The manifest identifies the allowed Sona entry points and does not mark all
retained-code execution qualified. This is a full native game-rule compilation
with a retained device intrinsic, not a rewrite of the Sona driver into UIL.
The output is a 2 MiB cartridge with an authored header, vectors and checksum.

## Export and repeat

Install the optional console dependencies. Prepare tools outside the checkout;
the commands do not install compilers or download games. All output directories
must be new and outside Git. The exact REV04 ROM is 524,288 bytes with SHA-256
e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7.

    fdisbull genesis-replay-profiles
    fdisbull genesis-replay-source /private/intake/miniplanets.bin

    fdisbull genesis-replay-export /private/intake/miniplanets.bin --target nes \
      --cc65-root /private/tools/cc65 --output /private/run/nes-bundle
    fdisbull genesis-replay-inspect /private/run/nes-bundle
    fdisbull genesis-replay-build /private/run/nes-bundle --target nes \
      --rom /private/intake/miniplanets.bin --cc65-root /private/tools/cc65 \
      --output /private/run/nes-repeat

    fdisbull genesis-replay-export /private/intake/miniplanets.bin --target genesis \
      --m68k-root /private/tools/m68k --output /private/run/genesis-bundle
    fdisbull genesis-replay-build /private/run/genesis-bundle --target genesis \
      --rom /private/intake/miniplanets.bin --m68k-root /private/tools/m68k \
      --output /private/run/genesis-repeat

Export defaults to the efficient reviewed game variant. Use variant baseline,
or a procedures JSON object such as {"run_objects":"baseline"}, to select
reviewed alternatives. The recipe is locked to one target; create a bundle for
each target rather than changing its target field.

For an existing game UIL export, the direct compiler route is:

    fdisbull console-udc /private/run/game/program.uil.json --target genesis \
      --region /private/intake/miniplanets.bin --m68k-root /private/tools/m68k \
      --output /private/run/genesis-direct

The tested cc65 revision is 52727a5b407bfeac0dfac1fdd84be8cd2af4f814 with
wrapped-call bank support. Its captured inputs include nes.lib and
asminc/longbranch.mac. The tested Genesis compiler is GCC 16.2.0 with binutils
2.47, prepared privately from verified Homebrew bottles. Its approximately
66 MB closure contains compiler executables, cc1/collect2, target tools,
liblto_plugin, GCC runtime files and linker scripts.

GCC helper/library lookup is forced into the explicit trusted toolchain.
Compiler search and dynamic-loader override environment variables are removed.
The tested macOS arm64 toolchain still relies on five external Homebrew dylibs,
whose absolute paths and hashes are bound, plus the system runtime. Unresolved
relative or loader-token dylib references are refused. This receipt establishes
same-host replay under those dependencies; it does not establish cross-host
compiler portability.

## Trust, identity and failure behavior

Captured Python and compiler files are inert evidence. Replay uses the matching
installed implementation, reconstructs all five documents from the exact
original source and reviewed recipe, and compares their bytes. It captures
tools from the caller's explicit trusted root and executes that new snapshot.
It never imports Python or executes a compiler taken from an untrusted bundle.

The lock binds every payload file, tool, runtime and native ROM. Replay rejects
changed source, changed implementations, rehashed semantic forgeries, altered
runtime libraries/macros, unknown recipes, unsafe payload paths, symlinks and
resource-budget violations. Inputs are rechecked before publishing the new
output directory. Inspection checks retained payload identity without executing
anything and labels historical qualification claims unverified. It also leaves
lock-selected external host dependency paths unopened and unverified; replay
derives those dependencies from the trusted compiler before comparing them.

Bundles contain original-derived assets, ROMs, build intermediates and tools.
They are private experiment outputs and must stay out of source repositories,
tool ZIPs and wheels. Public packages contain authored sources, semantic
reference artifacts and sanitized evidence.

## Validation and measured limits

The [sanitized replay receipt](evidence/miniplanets-full-game-2026-10-31/genesis-replay.json)
and [Genesis presentation receipt](evidence/miniplanets-full-game-2026-10-31/genesis-presentation.json)
record inputs, hashes, checks and limits.

| Edge | Observed result | Limit |
| --- | --- | --- |
| Presentation UIL → NES specialization | 480 sequential planner cases and 32 native clear cases agree | Logical module; existing hardware timing evidence remains separate |
| PSG UIL → C/6502 specialization | 128 cases agree across UIL, C and native assembly | Period/phase and volume mapping, not all FM/PCM/APU behavior |
| Game UIL → new Genesis CPU | All 4,822 original-backed controlled cases pass | All 79 fields, returns, HV consumption and sound-event observations; bounded inputs |
| Ordinary new Genesis execution → UIL | 676 completed snapshots and independent controller mappings in 1,000 core frames pass | Same observed device inputs; no HV reads occurred in that ordinary run |
| Adapted Genesis staging/VDP | 470 gameplay presentation batches match host reference; native writes originate in the new present routine | Stage 0, no mace actors; adapted graphics, no original pixel parity |
| Native Sona adapter | Init/BGM/SFX/stop/status register sentinels pass; nonzero PCM and busy/status flags observed | Retained original driver; not a waveform equivalence proof |
| Locked native replay | NES and Genesis reproduce their respective expected ROM bytes | Compiler/runtime/implementation identity conditions apply |

The Genesis display probe measured 470 complete 296-word upload batches in
940 core frames at 59.922743 Hz, or approximately 29.96 batches/s for its bounded
gameplay scenario. This is a first native Genesis backend, not a 60 fps result.
It is a different workload and adapter from the NES moving-player benchmark.
Read-only observation preserved system RAM, watched RAM traces, PCM and final
frames; serialized states differed in 165 bytes, while independent unhooked
controls differed in 110 bytes. The cause remains unknown.
Full serialized-state neutrality and bus-level VBlank safety remain
unproved.

The NES output SHA-256 is
1cf6e29d02c991af6bc9a8ced6668adb2a91a81b6c2318770d27379afb751db0.
The Genesis output SHA-256 is
7c6a55fb7f5b55449cd009b6824d4d010abe8a814b972b35fec59f999660464f.
The unchanged NES bytes retain the earlier bounded accuracy/timing evidence;
this turn does not add a new 60 Hz claim.

Original-backed component witnesses are hash-bound to their complete original
contracts and input captures. The native checker compares architectural bytes
using the pinned core's absolute-address xor-1 RAM mapping, preserves gaps
between linked globals, and joins completed state publications by logical epoch
with an independent controller timeline. Startup must finish before seeded
component cases begin; a first attempt seeded too early and was retained as a
harness failure, then corrected without changing the ROM.

Independent review added regression checks for oversized host-file reads,
dynamic-loader environment injection and unresolved dylib references; all were
fixed before packaging. Natural completion of every stage, original graphical
and waveform parity, arbitrary-ROM translation and physical hardware execution
remain open. The full macOS suite also has known Linux/ELF and case-sensitive
filesystem failures; package/affected checks and that full-suite result are
reported separately.
