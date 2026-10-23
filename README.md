# fDisBull

An agent-first disassembler with a persistent SQLite analysis database, explicit evidence, bounded analysis, and headless SVG/PNG exports.

Current completed version: **0.8.2**. Requires Python **3.12 or later**.

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

The unfinished DOSBox-X headless debugger checkpoint is preserved separately on `experimental/dosbox-headless`. Its launcher and runtime acceptance remain incomplete; it is not shipped in 0.8.2.

## Limits and licensing

Static analysis does not establish runtime execution. A drained queue does not establish complete code coverage. Authored labels and links record interpretations, and unresolved segment/pointer state stays explicit. Native macOS host verification remains pending; parsing Mac binaries on Linux is a separate check.

No first-party distribution license has been selected. Public visibility does not grant an open-source license. See [THIRD_PARTY.md](docs/THIRD_PARTY.md) for dependency provenance. The separate DOSBox-X checkpoint retains its upstream GPL notices.
