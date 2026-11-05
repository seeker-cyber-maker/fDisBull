# fDisBull 0.29.0: uploaded core packages installed

Date: 2026-11-01. This is a local sandbox intake, not a release or GitLab change.

## Answer

Both new archives contain installable **fDisBull 0.29.0 and its standalone player**.
Together with the dependency bundle supplied previously, they are sufficient for
an offline core/player installation. That installation is now working in an
isolated Linux x86-64 Python 3.13.5 virtual environment.

Neither archive contains a prebuilt native DOSBox debugger backend. The full
`fdisbull-0.29.0-linux-x86_64-offline.tar.gz` remains the simplest way to supply
that backend for live DOS-game execution. It is not needed to continue the
installed static-analysis, shared-IL, or local text-player work.

Ghidra is another separate dependency; its headless executable is not found here.
The installed Ghidra diagnostic entry point does not supply Ghidra itself or a
new general p-code-to-UIL implementation.

## What each upload contains

| Upload | Contents checked |
| --- | --- |
| `fdisbull-0.29.0.tar.gz` | Python source distribution; 712 files, core/player build metadata, source, skills, tests and documentation. |
| `fdisbull-0.29.0-tool.zip` | Tool-source bundle; 704 files, including the same core and player source. ZIP integrity check passed. |
| Earlier dependencies archive | Five pinned Linux-compatible wheels, install instructions and manifests. All nine internal checksum entries passed again. |

701 of the 704 common source-package/tool-ZIP files match byte for byte. The
three differences are documentation only: `docs/RELEASE-0.29.0.md`,
`docs/evidence/0.29.0-release/README.md`, and `docs/OFFLINE_KIT_0.20.md`.
The source distribution's eight extra files are packaging metadata.

The source-distribution and dependency-archive SHA-256 values match the publisher
values previously recorded in this conversation. The tool ZIP has valid CRCs and
its content was compared with the source distribution; its publisher checksum
was not independently fetched in this intake.

## Actual installation and checks

- Built core and player wheels locally from the source distribution using
  existing setuptools 82.0.1. These are local builds, not byte-identical claims
  about the publisher's wheel.
- Installed five dependency wheels and both application wheels into a fresh,
  isolated virtual environment, with `--no-index`; nothing was downloaded.
- `fdisbull --version`: **0.29.0**. Player distribution metadata: **0.29.0**.
- `pip check`: **no broken requirements**.
- All source files intended for the core/player packages match their installed
  copies: core 191 files, player
  9 files.
- **80 console-synthesis tests passed, zero skipped**, against installed modules,
  without the source-tree overlay. Host pytest was used only as a test runner;
  the checked application and core dependencies loaded from the isolated venv.
- Installed CLI imported and analyzed an authored three-instruction x86-16
  fragment, then read its MOV/ADD/RET disassembly in a separate invocation.
- Installed player API and CLI both executed an authored scene action and
  reported the expected success/state change. This is not a native game test.
- Decoder, ELF-parsing, PNG round-trip and Z3 smoke checks passed.
- The installed capability catalog and investigation skill were retrieved.

One initial probe tried `fdisbull-player --version`. This CLI has no supported
version flag and exited 2; the result is retained, not counted as a pass. The
package metadata, CLI help and functional player invocation were then checked.

No full suite, native DOS debugger, original console CPU, commercial game or
Ghidra invocation was run. No claim is made about those unavailable edges.

## Files in this handoff

`wheels/` contains the two locally built application wheels. The already supplied
50 MB dependency archive is not duplicated. `evidence/` contains checksums,
installation logs, test results, smoke results, discovered capabilities and the
exact input comparison. `intake_smoke.py` is the authored repeatable smoke test.
`run_installed_tests.py` records the local test-runner path used for this session;
on another machine install pytest normally instead of relying on that host path.

The installed sandbox command is:

```sh
original-linux-run --version
```

For another compatible **Linux x86-64 / Python 3.13** environment, extract the
previous dependency archive, then use its reviewed `install.sh` to create a new
venv. Install the two enclosed wheels offline:

```sh
/path/to/new-venv/bin/python -m pip install --no-index --no-deps wheels/*.whl
/path/to/new-venv/bin/python intake_smoke.py --output /new/private/smoke-output
```

The Linux dependency wheels are not a macOS installation kit. These instructions
do not install the missing native debugger or Ghidra.
