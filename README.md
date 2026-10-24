# fDisBull

An agent-first disassembler with a persistent SQLite analysis database, explicit evidence, bounded analysis, and headless SVG/PNG exports.

> **This tool is not designed for malware analysis or security work.**
>
> Must bring your own weapons. I have only done this once before. Safety not guaranteed.
>
> *With a nod to the “Safety Not Guaranteed” newspaper ad.*

Requires Python **3.12 or later**.

## Release, branches, and native backend status

| Track | Source and availability | Verification |
| --- | --- | --- |
| **Current source: 0.12.0** | [Release notes](docs/RELEASE-0.12.0.md): PE64 Wine/QEMU debugging, guarded memory edits, traces, screenshots and clicks | [PE64 verification](docs/PE64_VERIFICATION.md) and required Linux package, DOS native and PE64 native CI gates |
| **Latest published package release: 0.11.0** | [GitHub release and packages](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.11.0), commit `a216747` | [Tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40014891689): 759 passed. [Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40014891475): 15 established-backend and 32 layers-backend tests passed, no native skips. |
| **Repository branch** | [main](https://github.com/seeker-cyber-maker/fDisBull/tree/main) is the only active branch | Release promotion requires both ordinary and native Linux CI. Use version tags for fixed source snapshots. The old experimental checkpoint is preserved under an archive tag. |

The Python packages do **not** include an emulator. Stable debugging needs the [0.10 backend patch](experimental/dosbox-x/README.md); execution layers need the separate [layers backend patch](experimental/dosbox-x/layers/README.md). Both pin an upstream source commit and require an explicit executable path. Coordinate grids work with either backend.

The [release-status record](docs/RELEASE_STATUS.md) distinguishes tagged source, published packages and historical candidate receipts. Ordinary Python CI may skip native tests; [required native acceptance](docs/DOSBOX_DEBUGGER.md#required-native-acceptance) builds or selects the real patched backend and runs the existing tests against it.

The user-designated [DeepSeek delivery](docs/DELIVERY-0.11.md) contains the published packages and the tested Mac ARM64 layers backend, with checksums and usage instructions. Original game files, saved states and local project databases are excluded.

## Install and use

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
fdisbull inspect /path/to/program
fdisbull import /path/to/program analysis.fdb
fdisbull analyze analysis.fdb --max-instructions 10000
fdisbull analysis-status analysis.fdb
fdisbull functions analysis.fdb
```

On Windows, activate `.venv\Scripts\Activate.ps1` in PowerShell. Install `.[managed]` for optional .NET metadata and CIL inspection.

## Capabilities

- x86 16/32/64 and ARM64 decoding; DOS MZ, PE, ELF, Mach-O, universal Mach-O slices, and explicit raw images.
- Persistent instructions, control flow, references, annotations, types, and immutable byte versions.
- Explicit PE versus DOS-stub selection and segment-aware DOS instruction identities.
- Bounded analysis with pending work and unresolved targets kept visible.
- Attached resource/save files with typed fields, evidenced code references, and bidirectional shared labels.
- Repairable label links with retained history.
- Disassembly and control-flow graph images generated from stored state.

See the [user guide](docs/USER_GUIDE.md), [API](docs/API.md), [architecture](docs/ARCHITECTURE.md), [platform support](docs/PLATFORMS.md), and [external-file workflow](docs/EXTERNAL_FILES.md).

## DOSBox debugging

Launch an original DOS MZ project with `fdisbull debug PROJECT --executable PATH_TO_PATCHED_DOSBOX --game-dir GAME_DIRECTORY`. The foreground JSON interface can set relocation-checked breakpoints from disassembly addresses, click in guest screenshots, run until a breakpoint with a host timeout, and fast-forward a requested number of guest milliseconds. Screenshots and traces are stored inside the project and remain exportable after restart. See [DOSBox debugger usage and acceptance](docs/DOSBOX_DEBUGGER.md).

The real DinoPark path was verified through this interface. A ten-second guest skip completed in about 0.45 host seconds on the tested Mac, with actual elapsed values recorded; this is not a speed guarantee. The separately built DOSBox backend is required and is not bundled with the Python tool.

## Tool packages and examples

The wheel, source distribution, and standalone tool ZIP contain the tool, tests, and relevant documentation. **DinoPark is a repository example and is excluded from tool release packages.**

The [DinoPark example](examples/dinopark/README.md) contains layouts, investigation notes, and selected renders. Original game executables, resources, saves, and databases retaining those bytes are local inputs. Authored C fixtures are under `examples/synthetic/`.

```bash
python -m pip install '.[test]' build
python -m pytest -q
python -m build
python scripts/check_dist.py
python scripts/build_release.py
```

`MANIFEST.in`, `.gitattributes`, and the standalone ZIP builder exclude repository examples and experimental work from distributable artifacts. Build output goes to `dist/`.

## History and experimental work

Eight saved releases were reconstructed as successive commits: **0.1.0, 0.2.0, 0.3.0, 0.4.0, 0.5.0, 0.8.0, 0.8.1, and 0.8.2**. These are imported release snapshots, not original development commits. Exact 0.6.0 and 0.7.0 source snapshots were unavailable; their later verification notes remain historical documentation. [Import provenance](history/README.md) records filtering and archive hashes.

The original unfinished DOSBox checkpoint is preserved at tag `archive/dosbox-headless-2026-10-23`; the former experimental and takeover branches have been removed. The continuation contains a complete backend patch and fixture/DinoPark runtime evidence under `experimental/dosbox-x`; the Python integration uses that separately built backend. Neither emulator nor original game assets are included in tool packages.

Version 0.12.0 integrates a [PE64 Wine/QEMU debugger](docs/WINE_DEBUGGER.md): disassembly breakpoints, guarded memory edits, bounded instruction traces, client-window screenshots, 8px grids and mouse clicks, persisted with the project. It requires a separately prepared offline Linux/Wine runtime and QEMU. The [earlier Wine/Linux experiment](experimental/wine/README.md) records why full x86-64 CPU emulation is used on this Mac: Apple container/Rosetta failed the debugger gate. The [installed-wheel acceptance](docs/PE64_VERIFICATION.md) verifies real input, memory edits, rearmed breakpoints, traces and offline exports in two fresh sessions. The published 0.11.0 packages predate this PE integration.

## Limits and licensing

Static analysis does not establish runtime execution. A drained queue does not establish complete code coverage. Authored labels and links record interpretations, and unresolved segment/pointer state stays explicit. Native macOS debugger acceptance passes; the full suite still has Linux ELF fixture failures on Apple's compiler/linker. Runtime integration launches original unpatched DOS MZ or x86-64 PE EXE versions; static child patches are never applied silently. PE support has its own runtime and acceptance gate; DOS states, layers and data watchpoints do not transfer to PE.

Runtime code snapshots can preserve and decode observed self-modified or layered bytes alongside earlier views. They do not automatically create a new static code interpretation, traverse its targets, or rebuild its xrefs. A mapped runtime address alone does not verify equality with static instructions. Headless execution is not security isolation, and restoring a machine checkpoint does not roll back mounted host files.

No first-party distribution license has been selected. Public visibility does not grant an open-source license. See [THIRD_PARTY.md](docs/THIRD_PARTY.md) for dependency provenance. The separate DOSBox-X checkpoint retains its upstream GPL notices.

The debugger also supports [native checkpoints, editable state forks, bounded menu scripts, and CPU data-access breakpoints](docs/DEBUGGER_SCRIPTS.md). See the [0.10.0 release notes](docs/RELEASE-0.10.0.md) and [parking-counter experiment](docs/PARKING_COMMIT.md). Explicit DOS analysis seeds are decoded first within the requested budget, so preparing one execution-breakpoint address is no longer blocked by an older analysis queue.

The 0.11.0 [code layers](docs/CODE_LAYERS.md) distinguish RAM-visible patches from instruction-fetch overlays, preserve observed self-modified code separately from static facts, and support guarded layer stacks, branch theories, and breakpoint-triggered virtual caves. They require the separate layers backend; the published 0.10.0 backend and packages remain unchanged. Zero additional guest RAM bytes does not imply zero host overhead or unchanged guest timing.

Screenshots also support an [optional native-coordinate grid](docs/DOSBOX_DEBUGGER.md#optional-screenshot-coordinate-grid-0110) for writing click scripts. Clean frames remain stored unchanged; annotated images retain the same dimensions and video-mode ID and can be regenerated from the project after restart without operating a GUI. `click-frame` captures, labels and queues a chosen click in one client action.
