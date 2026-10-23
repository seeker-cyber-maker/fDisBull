# fDisBull

An agent-first disassembler with a persistent SQLite analysis database, explicit evidence, bounded analysis, and headless SVG/PNG exports.

Current development version: **0.9.0**, including a project-backed DOSBox debugger. Published baseline: **0.8.2**. Requires Python **3.12 or later**.

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

The original unfinished DOSBox checkpoint remains on `experimental/dosbox-headless`. The local continuation contains a complete backend patch and fixture/DinoPark runtime evidence under `experimental/dosbox-x`; the 0.9.0 Python integration uses that separately built backend. Neither emulator nor original game assets are included in tool packages.

## Limits and licensing

Static analysis does not establish runtime execution. A drained queue does not establish complete code coverage. Authored labels and links record interpretations, and unresolved segment/pointer state stays explicit. Native macOS debugger acceptance passes; the full suite still has Linux ELF fixture failures on Apple's compiler/linker. The integration currently launches original unpatched DOS MZ versions; it does not silently apply static child patches to the game.

No first-party distribution license has been selected. Public visibility does not grant an open-source license. See [THIRD_PARTY.md](docs/THIRD_PARTY.md) for dependency provenance. The separate DOSBox-X checkpoint retains its upstream GPL notices.
