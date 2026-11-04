# fDisBull agent quickstart

Use this page to find the right fDisBull interface for a task. Replace every
example path with a path selected by the user. The Python distribution does not
include a native emulator, game files, saved states or project databases.

Do not upload original or modified game binaries/assets, story files, saves,
emulator states or raw game-containing databases/archives. New FDBs store
external payload references with exact size/SHA-256 and loader provenance;
the private object store is never a publication artifact. See
[external targets](EXTERNAL_TARGETS.md) for explicit divergent-source approval,
separate analysis, legacy migration and remaining export limits. Semantic
UIL/game representations are permitted pending sanitation, without embedded
original files. Hash equality is byte identity, not publisher authenticity.

When operating in containerized or agent environments where the working directory
or `$HOME` resides inside a Git checkout (e.g. `/workspace/.git`), fDisBull's
private storage guards deliberately reject creating object stores or databases
there to prevent accidental repository pollution or leakage of binary assets.
Configure private external stores outside Git ancestry before running an import
or analysis:
```sh
export FDISBULL_TARGET_STORE=/tmp/fdisbull-targets
export FDISBULL_OUTPUT_ARTIFACT_DIR=/tmp/fdisbull-artifacts
```
Place all `.fdb` analysis databases in `/tmp/` or another private directory
outside Git.

For recovery, translation or a backing swap, retrieve
`agent-skill --reference references/reconstruction.md`. It provides a first-use
recipe, a runnable counterexample exercise and separate original/UIL/target
acceptance gates. It requires no earlier conversation or project history.

For array/loop state and browser graphics/input, see
[bounded-memory browser reconstruction](UDC_MEMORY_BROWSER.md). Its strict
memory UIL and selected per-function Wasm/WebGPU backings are separate from the
scalar food profile. The Snake study checks original instructions, real input,
complete rasters and guarded state commits; finite comparisons are scoped in
its receipt.

For a native macOS ARM64 window over the same memory UIL, see
[native memory reconstruction](UDC_MEMORY_MACOS.md). The native compiler and
AppKit adapters have separate execution and input/view qualification gates;
source selection target metadata remains provenance.

For Windows x86/Win64 and Linux x86-64/X11 shells over that same memory UIL, see
[native desktop reconstruction](UDC_MEMORY_DESKTOP.md). Source emission,
compilation, immutable artifact admission and native input/view qualification
are separate gates; Wine execution does not qualify Microsoft Windows itself.

### Original Windows debugging and dot-mode

For original **Win32 PE32**, **Win64 PE32+** and **Win16 NE**, read the
[Windows runtime and scene guide](WINDOWS_ORIGINAL_RUNTIME_BRIDGE.md).
`wine-qemu` selects the actual PE process width; `wine-ne` binds original NE
segments to observed live selectors. Both share Windows keyboard, native frame
probes and named scenes. They require a matching prepared offline guest.
`--dot-mode` returns an owned read-only spectator URL, without host input hooks
or forwarding. Frames refresh at stops/slices. Generated UDC shells and original
debugger qualification remain separate.

For a finite Windows input-route fuzz campaign, use `fdisbull fuzz` with a
private `fdisbull-native-fuzz-1` configuration. It plans explicit keyboard,
click, or named scene-action mutations and runs each case in a fresh owned
Win16/Win32/Win64 Wine guest with no host input window. See the
[bounded route fuzzing contract](WINDOWS_ORIGINAL_RUNTIME_BRIDGE.md#bounded-route-fuzzing-core)
and its one-shot command, private-output rules, and native qualification limit.

The **local Mac is a first-class host**: native Mach-O/ARM64 analysis, `macos-observe`, LLDB and native UDC do not depend on a Windows guest or a remote Linux runner. For original PE32 execution, the Mac can drive an isolated x86-64 QEMU/Linux/Wine guest; Linux CI is optional. Read-only setup probes (never execution proof):

```sh
python scripts/windows_runtime_preflight.py --mode macos-native --strict
python scripts/windows_runtime_preflight.py --mode compilers --target pe32 --strict
python scripts/windows_runtime_preflight.py --mode qemu-host --kernel /private/kernel --initramfs /private/wine.cpio.gz --strict
```

The `macos-native` check reports local Clang/LLDB/xcrun tool presence only. A
successful `qemu-host` check establishes guest prerequisites; it does not qualify
Wine startup, debugging or a particular game. Inspect the Windows guide and
exact-head MR receipts for native results and unsupported advanced operations.

For a genuine Win16 NE shell, see [segmented memory reconstruction](UDC_MEMORY_WIN16.md).
It retains the same logical u32 arena, cuts and selectable RNG regions through
paged storage, C89 blocks, native far-buffer file transfer and streamed GDI/RGBA.
Use its explicit emit/compile/seal route and qualify source, artifact, native
boundary and original/composed behavior separately. A supported Wine 11 route
does not establish original Windows 3.x or whole-game compatibility.

## Discover commands and bundled skills

For a DOS program that enters protected/v86 mode, read
[protected-mode input, explicit RAM and native checkpoints](DOS_PROTECTED_RUNTIME.md).
Keep guarded live RAM edits separate from edited-checkpoint interventions;
queue acceptance alone does not prove game input consumption.

For repository CI and dual-mirror updates (Local Git + GitLab), first read
[CI coordination](CI_COORDINATION.md). GitHub (`origin`) is permanently retired;
keep local Git and GitLab (`brewster-jennings-group/fdisbull`) synchronized,
and use `scripts/ci_status.py --host gitlab.com --repo brewster-jennings-group/fdisbull`
in cache-only mode by default.

```text
fdisbull --version
fdisbull capabilities
fdisbull macos-snapshot com.example.authorized-app
fdisbull methods
fdisbull agent-skill --list
fdisbull agent-skill --index
fdisbull agent-skill --reference SKILL.md
fdisbull agent-skill --skill write-gamefaqs-guide --index
fdisbull agent-skill --skill write-gamefaqs-guide --reference SKILL.md
```

`capabilities` reports the imported copy's bounded analysis, debugger, C and
UIL support, provider hashes and dependency detection without launching tools
or targets. It is unreleased in this source. Read [capabilities](CAPABILITIES.md)
before treating dependency presence as working support. `doctor` is a separate
explicit runtime acceptance test. `methods` prints the JSON method names and
their parameter summaries; some language operations are CLI-only and appear
in the capability report with `cli:` interface names.

On macOS 14+, `macos-snapshot` observes running-app, accessibility and display
state without input or permission prompts. `macos-session` records a private
capture journal; `--live` explicitly enables declared menu/preference actions.
Select a display and CoreGraphics global logical rectangle from the snapshot,
including negative origins. Read [reversible native capture](MACOS_REVERSIBLE_CAPTURE.md)
before a live operation or `macos-session-recover`. Never reopen an unrelated
app or treat failed capture as permission to repeat an uncertain action.
`agent-skill --list` returns the small skill catalogue. Use `--skill` to select
one, then `--index` to list its references and their purposes without fetching
their text. Choose a reference and retrieve it with `--reference`.
Omitting `--skill` preserves the `fdisbull-investigate` selection and its
existing response format. `--list` cannot be combined with `--skill`, `--index`
or `--reference`; `--index` and `--reference` are mutually exclusive.

`agent-skill` returns the selected packaged instructions and references as JSON.
It reads no project and does not register or install a skill into an agent's
own discovery directory. Fetch a single resource when needed:

```text
fdisbull agent-skill --reference references/analysis-approach.md
fdisbull agent-skill --reference references/workflows.md
fdisbull agent-skill --reference references/scenes.md
fdisbull agent-skill --reference references/runtime-navigation.md
fdisbull agent-skill --reference references/udl-uil-udc.md
fdisbull agent-skill --reference references/common-uil.md
fdisbull agent-skill --reference references/recovery-research.md
fdisbull agent-skill --reference references/semantic-contracts.md
fdisbull agent-skill --reference references/scene-recovery.md
fdisbull agent-skill --reference references/formats-and-media.md
fdisbull agent-skill --skill write-gamefaqs-guide --reference references/evidence-and-provenance.md
fdisbull agent-skill --skill write-gamefaqs-guide --reference references/routes-and-discoveries.md
fdisbull agent-skill --skill write-gamefaqs-guide --reference references/formats-and-engine-reuse.md
```

With a source checkout, the bundled files are under
`src/fdisbull/skills/fdisbull-investigate/` and
`src/fdisbull/skills/write-gamefaqs-guide/`. The same projectless JSON method
accepts `{"method":"agent-skill","params":{"list":true}}` or
`{"method":"agent-skill","params":{"skill":"write-gamefaqs-guide","reference":"SKILL.md"}}`.
Skill names and reference paths are restricted to the published catalogue and
the selected skill's index.

The current JSON protocol has a
one-shot `request` command and a retained `serve`/`debug` session; a one-shot
request cannot keep a live emulator attached.

The full skill may exceed the inline response budget and return an output
artifact reference. Prefer the index and one selected guide for routine work;
use the output retrieval commands below when a complete export is needed.
The analysis-approach guide helps choose what to investigate next, including
actor, item, interaction and text-projection dependencies.
For the preserved Genesis-to-NES research and its native ARM64 successor, see
[the handoff](GENESIS_NES_RESEARCH_HANDOFF.md) and
[native Shadowrun output](SHADOWRUN_MACOS_ARM64.md). Select
`shadowrun-ai-build --target macos-arm64` for the same bounded model on a Mac.
For the separately recovered SNES opening-scene movement study, see
[SNES native transfer](SHADOWRUN_SNES_MACOS.md). Its `shadowrun-snes-build`
command uses the exact caller-owned SNES ROM, WRAM and save-RAM capture; it is
a prepared source-specific profile, not a whole-ROM conversion command.
The semantic-contract guide connects intent, effects, time and projection loss;
the scene-recovery guide starts UIL extraction from required scene elements and
bounded source dependencies. The formats/media guide covers input mapping and
qualified media reduction.

Use `write-gamefaqs-guide` to turn established investigation results into a
human-readable review, route or mechanics reference. Cover recovered unused code,
bugs, cheats, easter eggs, event probabilities, alternate paths, speedrun rules
and completion goals. Include recovered file/media specifications and qualified
engine/interpreter reuse across related games. It preserves release boundaries,
attributes external sources, and separates supported knowledge from unknowns.
Its templates and research guidance do not implement a game-guide
generator, play through a game, or submit anything to GameFAQs. Return to the
investigation skill for unresolved behavior that materially affects the review.

The installed-package gate supports the same selection. Its default remains
the investigation skill:

```text
python scripts/check_agent_skill.py --python /path/to/installed/python --skill write-gamefaqs-guide --output /private/guide-skill-receipt.json
```

For multi-agent benchmarking, lead-dossier preparation, and zero-context worker
verification under the Elephant-Goldfish Method (EGM), see
[cold-agent skill evaluation and the Elephant-Goldfish Method](COLD_AGENT_EGM_BENCHMARK.md).

## Reuse media readers

Run `fdisbull media-modules` to discover shipped parser APIs, dependencies and
limits. `media-inspect` inventories classic MZ header/module/opaque-tail ranges
or a selected AGI v2 resource; `media-extract` copies one member to a new private
directory outside Git. Both return source/member hashes without inline target
bytes and never execute inputs. Existing `gog-list/gog-unpack` and AGI picture
APIs remain available through the catalog. Read the packaged specification with
`fdisbull agent-skill --reference references/media-modules.md` before recovering
missing tooling or extending an adapter. This does not unpack compressed DOS
executables or establish the purpose of their trailing bytes.

For a closed native AVI recording, `fdisbull capture-audit CAPTURE.avi --output
/private/run/audit --every 4 --html` hashes every decoded frame and exports a
sample with original timestamps for slower review. Its output parent must be
private and outside Git. Check the audit receipt before analyzing pixels; video
timestamps do not supply guest ticks or input alignment. The
[capture-audit guide](TAS_CAPTURE_AUDIT.md) covers the Python/JSON interfaces,
budgets and failed-run diagnostics.

## Choose a route

### Intake a collection or a single addition

Use [collection intake](TARGET_COLLECTION_INTAKE.md) for the common per-artifact
workflow, source/member identities, unsupported formats and version decisions.
Inventory the batch before choosing programs, preserve learner/oracle separation,
and compare extracted hashes with the current private roster. An exact repeat
adds provenance rather than another program copy. A different release gets its
own original artifact before any snippet/layer relationship is proposed.

Identification, extraction, image loading, bounded analysis and native execution
are separate observations. Use a qualified archive/filesystem reader outside the
tool where needed; inspect the installed commands before assuming support.
Unknown formats remain catalogued inputs with an explicit capability gap.
The bundled `references/formats-and-media.md` carries the portable summary.

### Compose a new program from recovered or authored blocks

Use [the common indexed UIL contract](COMMON_UIL_CONTRACT.md) for the additive
`uil-*` methods. UIL references typed zero-based variable/constant slots;
presentation binds values/resources and orchestration selects exact catalog
implementations through owned call shims. The initial single-instruction
fallback admits decoded register MOV/INC/ADD/ADC, not arbitrary native execution.
Recoverable groups retain their children; a group label alone grants no semantic
or execution authority. [Conformance](COMMON_UIL_CONFORMANCE.md) demonstrates
mixed-source reconstruction, food arithmetic and Snake memory-model migration.
Run generated code and qualify original/source correspondence separately.

For [native common UIL](COMMON_UIL_NATIVE.md), `uil-link` resolves exact module
versions/types/ABI and nested providers before `uil-compile` builds a selected
macOS ARM64, Linux x86-64 or Win64 realization. `uil-components` describes finite
cascaded choices. Use `--source-only` for another prepared environment, then
`uil-build` or `uil-seal`; media services remain planned effects. Register-copy
pruning retains source children, logical slots and step charges.

### Inspect an executable without running it

When source is available, use the separate [source catalog](SOURCE_CONCEPT_SEARCH.md)
and `source-*` JSON methods to retain revisions and search across editions.
The bundled `references/source-and-concepts.md` gives the portable workflow.
Source names, spelling occurrences and similarity do not automatically become
native symbols, resolved variables or equivalent code.

```text
fdisbull identify /path/to/program
fdisbull rom-inspect /path/to/console-cartridge-or-sega-data-track
fdisbull disc-inspect /path/to/disc.cue
fdisbull inspect /path/to/program
fdisbull import /path/to/program /path/to/analysis.fdb
fdisbull analyze /path/to/analysis.fdb --max-instructions 10000
fdisbull analysis-status /path/to/analysis.fdb
fdisbull functions /path/to/analysis.fdb
fdisbull disasm /path/to/analysis.fdb --address 0x1000 --lines 40
```

For DOS COM files, select `--image com` explicitly when importing. A suffix
alone does not establish the file format. Analysis limits may leave work
pending; inspect status and do not call a budget stop complete. `render` exports
from saved project state without operating a GUI.

For a macOS ARM64 executable, select the `arm64` Mach-O slice explicitly and
keep the FDB and original file private. The 0.29.0 candidate includes exact ARM64
`code-backings`, source-bound `ghidra-arm64` instruction/C diagnostics and a
one-stop `macos-observe` LLDB launch. Read
[macOS ARM64 analysis](MACOS_ARM64_ANALYSIS.md) for commands, source hashes,
static/runtime address separation and the still-unimplemented app-level UIL
export.

Miles AIL 2 driver libraries (often `.ADV`) are recognized by validated bytes
and expose named exports and a bounded descriptor candidate. They import
automatically or with `--image ail`; addresses remain module-relative and no
runtime driver is installed. Use `dos-services --vector 0x66 --ax 0x688` to
describe a DIGPAK call, or `--ax 0x702` for MIDPAK. Stored DOS disassembly uses
the same names when AX is known, retaining unverified-handler and unknown-outcome
qualifications. See [DOS audio drivers](DOS_AUDIO_DRIVERS.md).

### Observe a real DOS target

```text
fdisbull debug /path/to/analysis.fdb \
  --executable /path/to/compatible-dosbox-x \
  --game-dir /path/to/game \
  --backend dosbox
```

The backend must be separately prepared and compatible with the requested
features. The debugger binds the executable and mapped version to the project;
use the original files and version the user selected. Drive ordinary guest
input, then verify that the target consumed it and produced the claimed state
change. `--dot-mode` only requests a compatible watch window; headless remains
the default. See `docs/DOSBOX_DEBUGGER.md` for detailed launch and command usage.

For PE or machine-level work, use the backend, kernel and runtime inputs
documented for that interface. Do not assume DOS options or address mappings
carry over.

### Inspect scenes or qualify movement

Use a scene revision for screenshot context, object recognition, readiness and
guarded clicks. Use a spatial-map revision for game-unit coverage, actor
footprints, obstacles, hazards, portals and interaction zones. Native movement
still uses the original guest input. A candidate route is not proof that the
engine follows it. Read `docs/SCENE_NAVIGATION.md` and
`docs/SPATIAL_MAPS.md`, then load the matching `scenes.md` or
`runtime-navigation.md` skill reference.

### Use a text interface

For a local authored slice, install or run the independent player from a source
checkout:

```text
python -m pip install ./player
python -m fdisbull_player --package /path/to/slice.json
python -m fdisbull_player --package /path/to/slice.json --live \
  --save-dir /path/to/private-checkpoints
```

This player evaluates a declared JSON slice; it is not a native-game emulator
or a recovered interpreter. `--live` checkpoints turns, but successful
checkpointing does not establish that a package models an original game.
Read `docs/TEXT_PLAYER.md` and `docs/PLAYER_LIVE.md`.

For a qualified debugger-backed projection, start the local host:

```text
fdisbull text-host /path/to/private-host-config.json \
  --spatial-mode physical
```

Connect `fdisbull-player --connect HOST:PORT` to the host endpoint it reports.
The backend must be supplied in the private configuration along with the
project, game directory, projection and qualified runtime witnesses. The
line-oriented loopback protocol has no authentication or encryption; use it
only in a trusted local environment. Select `physical`, `assisted` or `story`
explicitly. `--fair-play` locks the host to physical movement and is a voluntary
policy, not an anti-tamper boundary. See `docs/TEXT_PROJECTION.md` and
`docs/SPATIAL_MAPS.md`.

### Test shared interaction scenes with Z

Install the core tool and the separate player from the integration candidate.
From a checkout, the authored key-and-gate example runs as follows:

```sh
PYTHONPATH=src:player python -m fdisbull_player \
  --backend-command "python -m fdisbull.il_scenes examples/z/key-and-gate.json" \
  --backend-timeout 3
```

Try `look`, `take key`, `use key on gate`, `n` and `look`. With installed
packages, give the service a private scene document you supply; the example
directory is checkout-only. The player can be installed without the core;
the selected scene service needs its own matching core environment. Commands
are passed without a shell. Public observations stay partial and omit private
programs and evidence. Use `--quiet` for bounded external-driver runs with
full results kept in the private transcript. See [Z scenes](Z_SCENES.md).

### Play the original-backed DinoPark provider

With the core and player installed in the same selected Python environment:

```sh
fdisbull-player \
  --backend-command "python -m fdisbull.dinopark_z --game-dir /private/game --backend /private/backend/dosbox-x --work-dir /private/new-z-run" \
  --backend-timeout 60
```

The work directory must be new, outside Git and separate from the qualified
original. Try `look`, `go bank`, `repay loan`, `borrow loan` and `go office`.
The provider first emits and verifies the original game through the v0.23 UDC;
the native engine supplies effects. Its private receipts distinguish action
completion from shutdown and interrupted/unknown outcomes. Use native `save
park` for durable park persistence; live engine checkpoints have a separate
ownership and resource-identity contract. Keep game files and evidence private.
See [DinoPark Z](DINOPARK_Z.md) for the tested opening route, native requirements,
partial coverage and remaining untested cases.

For ordered scene commands, the separate player's `--batch-plan` and
`--batch-journal` flags retain progress before dispatch. Use a qualified
session-bound provider and the JSON operations in [batch recovery](Z_BATCH_RECOVERY.md).
Resuming a partial action requires both the plan and provider to authorize the
continuation. A successful acknowledgement is not proof that the original
intent completed: current partial steps remain paused. Never replay the
original action to repair missing evidence.

### Preserve Zork IR or recover a qualified action

```text
fdisbull zork-uil /private/ZORK1.DAT --output /private/zork.ir.json.gz
fdisbull zork-intents /private/ZORK1.DAT --ir /private/zork.ir.json.gz \
  --output /private/zork.intents.json.gz
fdisbull-player --intents /private/zork.intents.json.gz \
  --checkpoint /private/zork.progress.json
```

The executable Word16 format retains interpreter operations; its legacy `uil`
name does not make it recovered game intent. The qualified intent producer
binds one edition's source operations to semantic rules and keeps everything
unhandled as explicit IR. Generated packages and checkpoints retain story
data, so they must remain private. See [Zork IR](ZORK_UIL.md) and
[intent recovery](ZORK_INTENTS.md). On a fault, inspect completed effects and
interrupted-effect uncertainty; the CLI preserves the prior successful
checkpoint. A transcript-write failure is a separate delivery failure.

### Recover named Zork scenes and direct rules

```text
fdisbull zork-scenes /private/ZORK1.DAT \
  --intents /private/zork.intents.json.gz \
  --output /private/zork.scenes.json.gz \
  --uil /private/zork.scene-rules.json \
  --dispatch /private/zork.rule-links.json \
  --udl /private/zork.scene-definitions.json.gz
fdisbull-player --scenes /private/zork.scenes.json.gz \
  --checkpoint /private/zork.scene-progress.json
```

This retains the supplied intent/IR package and adds executable, address-free
scene rules plus direct named-handler links. Conditions and doors are read live;
the source's packed target values are resolved during production. The compatibility
adapter skips admitted selector operations and on-foot relocation instructions.
Changed or unqualified source dependencies use an explicit residual path.
The scene checkpoint binds the full new package. See [the scene contract](ZORK_SCENES.md)
for actual effect boundaries, unresolved handler bodies and source-qualified scope.

### Inspect interpreted game data

For a checksum-qualified raw Z-machine v3 story, including the supplied Zork I
edition, use the source-bound processor without a native project or emulator:

```text
fdisbull story-info /path/to/ZORK1.DAT
fdisbull zmachine-disasm /path/to/ZORK1.DAT --max-instructions 40
fdisbull zmachine-analyze /path/to/ZORK1.DAT --max-instructions 10000
```

The first query lists a source-order instruction slice; the second follows
candidate direct control-flow edges from the initial PC. Use `--address` for a
different listing start or repeat `--entry` for explicit graph roots. Read the
returned `complete_scope`, unresolved transfers, issues and budget frontier.
Even a drained static worklist does not establish runtime reachability or game
intent. Story offsets never become native interpreter addresses or `.fdb`
instruction rows. See [Z-machine processor](ZMACHINE_PROCESSOR.md) for the Python
interface and the distinction from executable IR and game-intent UIL.

For one AGI 2.917 logic resource in an uncompressed version-2 LOGDIR/VOL set:

```text
fdisbull agi-logic /path/to/LOGDIR /path/to/VOL-directory 1 \
  --profile 2.917 --max-instructions 1000
```

This is a bounded, read-only partial decoder. It does not show that the game
loaded or executed those bytes. To claim runtime behavior, qualify the resource
mapping and trace interpreter fetch, branch conditions and effects. See
`docs/AGI_LOGIC.md` and the interpreter section of `methodology.md`.

For direct guest inputs, `fdisbull decoder-modules` lists the explicitly
registered AGI and Z-machine front ends. `module-analyze` reads their source
instructions without a native project; `module-lift` provides the first narrow
AGI state projection into shared UDL/UIL. See [decoder modules](DECODER_MODULES.md)
for commands, source identities, required state witnesses and unsupported cases.
Choose the actual guest language before spending effort on the interpreter's
ASM; qualify runtime effects separately.

For an original-game route and reusable scene example, see the
[KQ1 bridge-corner investigation](AGI_BRIDGE_CLIP.md). Its fresh-game collector,
source-linked predicate observation and separate scene exporter have distinct
checks. The companion collision scanner proposes bounded static candidates;
it does not certify safe movement or glitches.
The [mushroom-island follow-up](AGI_MUSHROOM_CROSSING.md) combines a qualified
crossing with a normal parser command and separate native score/inventory
observations, then exports the observed route to the shared Z player.
The [leprechaun-cave follow-up](AGI_LEPRECHAUN_ROUTE.md) adds preparation,
range-sensitive parser input, the original shield writes and handler return,
and the game's shrink/regrowth sequence. Its exporter requires complete
observations and exposes the carried inventory in the separate player.
The [gnome/key and chest segment](AGI_GNOME_GIANT_ROUTE.md) adds a reusable
native-checkpoint continuation, an explicit origin receipt and eight guarded
text actions. Keep the prepared checkpoint, full single-session observations,
source-bound writes/returns and player verification as separate gates. A
scratch variable can be stale: the chest example observes the original
distance operation inside the command before continuing its effects.
The [dragon and mirror route](AGI_DRAGON_MIRROR_ROUTE.md) qualifies eight
fresh-game actions through a safe surface return. It adds source-bound water
consumption and mirror pickup, pretyped input with guarded movement, and a
coast-tolerant exit corridor. End short handler traces before blocking dialogue
and observe later score effects separately. A physical priority-plane flag is
not a story-state label: the underwater example binds actual PIC52 baseline
classes, swimming state and carried water. Its separate Z scene checks all
44 modeled native fields plus phase; original-game timing remains outside it.
The [boundary follow-up](AGI_BOUNDARY_EXCEPTIONS.md) derives thin complement
bands from paired AGI position predicates. Keep source candidates, picture
clearance and native reachability separate. Independent checkpoint forks
confirm the dragon rule at rows 166/167; other points remain unqualified.
For off-screen objects and scrolling margins, use the
[coordinate-domain audit](SCENE_COORDINATE_DOMAINS.md). Store its descriptor
with the scene/map, then call `debug-scene-domain-audit` or
`debug-spatial-domain-audit`. Expected mechanisms retain layout notices and
never grant movement or teleport authority.
The [bottom-row bridge follow-up](AGI_BRIDGE_BOTTOM.md) shows a complete bounded
source-candidate → ordinary-input witness → standalone scene workflow, including
expected border/room-initialization stages and the one-row-higher control.
Use the [shared controller and receipt helpers](BOUNDED_NATIVE_SCENES.md) when
authoring another native investigation. Keep the source-specific state/stop
policy in the adapter; routine saved scripts continue to use their existing API.
For video-led route research, the [Robb TAS reconstruction](research/kq1-robb-9.89/ROUTE.md)
keeps visible key highlights, inferred directions and unknown dispatch separate.
Qualify those proposed actions in the original game before using them as evidence.

### Compare console instruction proposals

Use `rom-inspect` / `disc-inspect` for container facts first. When a payload's
load mapping has independent evidence, `rom-disasm` can decode a bounded SH-2
range with Capstone, Ghidra or saturn-recomp. Supply the address mapping file
offset zero; keep extracted files and returned instruction bytes private.
`--mode word-scan` tests aligned words independently, including data hypotheses.
Neither mode discovers executable code or updates a native project. See
[ROM-to-ASM](ROM_ASM.md) for external engine setup, the shared output contract,
the Civilization Saturn comparison and the known Capstone CPU-profile issue.

### Generate a bounded native console cartridge

`console-udc-targets` lists the common NES/Genesis UIL profile. Compile an
authored script with `console-udc script.uil.json --target nes --output
/private/new-cartridge --display-variable '$x'`; change only `--target genesis`
for a Genesis cartridge. Outputs must be new directories outside Git.
Both modules emit native CPU and console startup code. See
[console UDC](CONSOLE_UDC.md) for the supported arithmetic/condition subset,
workload limits and real emulator results, including a bounded Genesis ROM →
UIL → NES test. This does not automatically recover a commercial game's UIL.

For the reviewed full Miniplanets profile, `rom-game-lift ORIGINAL_ROM --output
/private/new-uil` exports procedural game/audio UIL. `console-udc
/private/new-uil/program.uil.json --target nes --region ORIGINAL_ROM
--cc65-root /private/tools/cc65 --output /private/new-game` compiles the same
rules into a banked NES cartridge. See the [full-game contract and measured
qualification](MINIPLANETS_FULL_GAME.md); original data remains external and
this source-bound profile is separate from arbitrary ROM decompilation.
For a locked game/audio/presentation/PSG export with repeatable native builds,
use `genesis-replay-export ORIGINAL_ROM --target nes --cc65-root TOOLS --output
/private/new-bundle`. Select `--target genesis --m68k-root TOOLS` to compile
the full procedural game back to Genesis. `genesis-replay-source` reports
whether an intake has a reviewed semantic profile; parsing alone is insufficient.
See [Genesis UIL replay](GENESIS_UIL_REPLAY.md) for build/replay commands,
tool trust and the target-specific validation limits.

For a post-compilation two-game NES cartridge, discover
`nes-multicart-profiles` and inspect candidates with
`nes-multicart-inspect CARTRIDGE`. Use `nes-multicart-build GAME1 GAME2
--authored-compatible --output /private/new-multicart` only for authored
NROM games satisfying the declared mapper restrictions. The flag asserts
behavioral compatibility that a header cannot establish. The
[multicart contract and native checks](NES_MULTICART.md) describe the menu,
bank switching, input handoff and tested emulator reset behavior.

For a complete resource census and scene-element outline of a qualified DOS
AGI 2.917 resource directory:

```text
fdisbull agi-scenes /private/game --profile 2.917 --stage outline
fdisbull agi-scenes /private/game --profile 2.917 --stage resolve
```

The second stage adds conservative local value resolution. Use `--include-ir`
and `--include-text` for private source investigation. It retains every LOGIC
as low-level IR or an opaque source obligation; it is not an executable game
model. Read [AGI scene census](AGI_SCENE_CENSUS.md) and the bundled
`references/agi-scenes.md` before interpreting its coverage counts.

For the separately qualified KQ1 initial-audience bow:

```text
fdisbull kq1-bow-intents /private/kq1 --output /private/bow.package.json.gz
fdisbull kq1-bow-evaluate /private/bow.package.json.gz --state-file /private/before-bow.json
```

The second command executes named UIL rules and bound engine requests against
a declared state. It does not operate a guest or supply animation timing.
Follow [the interaction contract](KQ1_BOW_INTENT.md) for state qualification,
completion events and explicit modal acknowledgements, and read
[verification](VERIFICATION-KQ1-BOW-2026-10-30.md) for the distinction between
source comparisons and selected native observations. Unknown contexts return
`unrecovered`; the complete census remains low-level IR.

### Compare a source block with shared semantics

For the supported 0.23 DOS profile, read `udl-uil-udc.md` before using
`udl-lift-asm`, `udl-lift-c`, `udl-verify` or the `udc-*` commands. UDC currently
retains original x86-16 MZ/COM version-1 bytes; it does not generate general DOS
code or recover a whole game. A Z3 result covers only the explicit modeled
register boundary and assumptions. Read `docs/UDC_DOS.md`,
`docs/UDC_TESTING.md` and `docs/BOUNDED_PROOFS.md` for the supported schema and
limits.

## Keep results within their evidence

For one pure selected byte/word block, `build-web-block` emits guarded Wasm or
WGSL under the same module UIL. Read [Web UDC profiles](UDC_WEB.md) for target
names, host ABI and original-backed CivD qualification. Browser/GPU availability
and application state commits need separate checks.

`build-web-shell` adds an explicit typed record arena and orchestration plan over
two interchangeable selected blocks. Read [the browser shell](UDC_BROWSER_SHELL.md)
before binding async results to application state; computation readiness is not
a commit, and cancellation does not release a submitted GPU job early.

Static decode, authored scene geometry, diagnostic state edits, text
projections, bounded proofs and live ordinary input are different evidence
surfaces. Report which one supports each conclusion, with source/version and
context. Keep missing or unsupported behavior unknown. Keep game assets,
checkpoints and byte-retaining project databases private; export only the
requested authored scripts, selected evidence and receipts.

Before promising a capability mentioned in a proposal, check the
[PR requirements backlog](PR_BACKLOG.md) and the final source. Incorporated
documentation, authored tests and fresh native acceptance have different scope.

## Research a progression or recovery task

For a game recovery or normal-progress request, qualify the supplied edition and
search for prior source, interpreter and reverse-engineering work before choosing
probes. Use manuals and walkthroughs to draft a source-attributed milestone
checklist, with missing or version-specific steps marked unknown. Treat its scene
compositions as hypotheses until bounded native observations establish them.
The bundled `references/recovery-research.md` describes the progression from
source bytes to supported UDL/UIL and the scope of a bounded proof.

## Retrieve a large response

The core defaults to a 64 KiB inline response. When a reply contains an
`fdisbull-output-ref-1` marker with `status: artifact_required`, the wire payload
is incomplete and the original JSON is stored privately. Read its execution
summary separately: the operation can have completed or remain unknown.

```text
fdisbull output-info ARTIFACT
fdisbull output-select ARTIFACT /result/state --max-bytes 8192
fdisbull output-read ARTIFACT --offset 0 --length 4096
fdisbull output-export ARTIFACT /private/new-response.json
```

`output-select` returns a value only when it fits in full; `output-read` returns
a bounded base64-encoded byte range. The pointer for a raw `il-run` response is
`/state`, whereas a wrapped `request` response uses `/result/state`. Export
requires a new private path outside Git. Retrieving an artifact never reruns the
operation or advances the guest; the archived response is not a fresh runtime
observation. `output_unavailable` means full output could not be retained (for example,
storage or serialization failed), and no artifact exists;
it does not imply rollback or permission to retry. Output references are
distinct from project debugger artifact IDs. The default store is the user data
`fdisbull/output-artifacts` directory; `FDISBULL_OUTPUT_ARTIFACT_DIR` selects a
private location outside Git. Artifacts are not automatically deleted.
