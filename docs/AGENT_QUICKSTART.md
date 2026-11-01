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

## Discover commands and bundled skills

For repository CI, first read [CI coordination](CI_COORDINATION.md). One named
owner refreshes a shared, dated status receipt at most every five minutes;
other agents read the receipt instead of polling GitHub separately. The finite
`scripts/ci_status.py` helper defaults to cache-only operation.

```text
fdisbull --version
fdisbull capabilities
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
fdisbull agent-skill --reference references/workflows.md
fdisbull agent-skill --reference references/scenes.md
fdisbull agent-skill --reference references/runtime-navigation.md
fdisbull agent-skill --reference references/udl-uil-udc.md
fdisbull agent-skill --reference references/common-uil.md
fdisbull agent-skill --reference references/recovery-research.md
fdisbull agent-skill --reference references/semantic-contracts.md
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
The semantic-contract guide connects intent, effects, time and projection loss;
the formats/media guide covers input mapping and qualified media reduction.

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

```text
fdisbull identify /path/to/program
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

### Compare a source block with shared semantics

For the supported 0.23 DOS profile, read `udl-uil-udc.md` before using
`udl-lift-asm`, `udl-lift-c`, `udl-verify` or the `udc-*` commands. UDC currently
retains original x86-16 MZ/COM version-1 bytes; it does not generate general DOS
code or recover a whole game. A Z3 result covers only the explicit modeled
register boundary and assumptions. Read `docs/UDC_DOS.md`,
`docs/UDC_TESTING.md` and `docs/BOUNDED_PROOFS.md` for the supported schema and
limits.

## Keep results within their evidence

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
