# System installation

## Current observation (2026-11-14)

Both `/Users/tiga/.local/bin/fdisbull` and `/usr/local/bin/fdisbull` route
through `/Users/Shared/fDisBull/current`. The selector currently points to
`releases/0.34.1-3aaac41`; its receipt records version `0.34.1`, source
`3aaac41b1f73220568fc07b9d53f5ccd4307a242` and status `local_candidate`.
This differs from immutable tag `v0.34.1` at
`011f1b8cb281edda208026aee9cdb238b800b2d7`. A version string alone does not
establish installed release identity. `check_local_install.py` correctly requires
`active_verified`; this current candidate does not meet that gate.

The intended next release is 0.35.0; source integration and exact-package install
acceptance remain open. Follow the [release process](RELEASE_PROCESS.md) and
[current release status](RELEASE_STATUS.md). No installation is performed by
updating these records.

## Installation protocol

`scripts/install_system.py` stages a fresh application prefix and switches the
existing shared selector only after validating its inputs and the candidate.
The current 0.35.0 installation is authorized after the complete release checks
pass. Older no-install instructions are historical; authorization does not turn
missing native evidence into a passed check.

The input manifest uses schema `fdisbull-system-install-input-1`. It records the
full source commit and version, the four CI release artifacts, independently
identified dependency wheels, Mac backends, runtime resources, and CI, published
release, public download and Mac native receipts. Each input reference contains
an absolute `path`, `size` and `sha256`. The script validates the closed manifest
fields before creating a prefix. It never takes a project database or emulator
state as an installation resource.

```sh
python scripts/install_system.py --base /Users/Shared/fDisBull stage --manifest /absolute/private/install-inputs.json
python scripts/install_system.py --base /Users/Shared/fDisBull verify --prefix /Users/Shared/fDisBull/releases/VERSION-SOURCEPREFIX
python scripts/install_system.py --base /Users/Shared/fDisBull activate --prefix /Users/Shared/fDisBull/releases/VERSION-SOURCEPREFIX
python scripts/install_system.py --base /Users/Shared/fDisBull reconcile --prefix /Users/Shared/fDisBull/releases/VERSION-SOURCEPREFIX
python scripts/install_system.py --base /Users/Shared/fDisBull rollback --prefix /Users/Shared/fDisBull/releases/VERSION-SOURCEPREFIX
```

Staging installs the identified wheels in a fresh virtual environment using only
the supplied dependency wheels. It copies the identified source tools, backends
and runtime resources, inventories their bytes, and runs the installed CLI
through an authored executable import, bounded analysis and project reopen.
That probe's temporary database and evidence live outside the release prefix.
A staged prefix is a candidate; staging does not replace `current`.

Mac native evidence uses schema `fdisbull-macos-native-qualification-1` and binds
the same version/source, backend bytes and every runtime resource. Successful
command records include nonzero native case counts, profiles, argument vectors,
return codes and byte-bound stdout/stderr logs. Required profiles cover stable
and layered DOSBox, the QEMU machine, Wine PE64/PE32 and Win16. Backend build
receipts bind the upstream source, applied patch where relevant, binary and
successful build commands. Linux CI and an old binary's hash do not establish
these host-specific facts. The installer consumes real receipts; it does not
manufacture native qualification.

Activation re-verifies the staged prefix and writes an immutable attempt
directory containing the exact previous selector and original staged receipt.
It records `activating`, switches the selector atomically, and checks the selected
executable and installed package identity. It invokes `check_local_install.py`
with the required version and full source commit. The internal precheck reports
`prechecked`, never active success. Only after
the live checks and their hash-bound completion proof are durable does the
installer write `active_verified`, then verify the public result. A failed
activation restores the prior selector and installation record; the prior
prefix and running private sessions remain in place. Rollback restores the recorded selector and retains both prefixes.
An abrupt process loss leaves `activating` or `rolling_back`, and public checks
reject that incomplete state. Explicit `reconcile` observes the current selector
and compensates only an owned effect; it does not replay the activation forward.
It refuses an unrelated selector change. A subsequent explicit activation uses a
new attempt directory, preserving every previous intent, completion and rollback
record. Repeating a completed activation verifies its existing result; repeating
rollback on an inactive candidate reports `already_inactive` without mutation.

An installer dependency may instead be built locally from an official PyPI
source distribution when no suitable official Darwin arm64 wheel exists. Its
manifest entry is `{"wheel": REF, "source_build": REF}`. Every `REF` is an
absolute file path, size and SHA-256 using the input reference format above.
The `fdisbull-source-built-wheel-1` document has exactly these fields:
`schema`, `name`, `version`, `platform` (`darwin`), `architecture` (`arm64`),
`wheel` (`name`, `size`, `sha256`), `sdist` (REF), `pypi_identity` (REF),
`build_commands`, `validation_commands`, and `toolchain` (a nonempty mapping
of names to REFs). Each command records exactly `argv`, `returncode`, `stdout`
and `stderr`; it must succeed and both logs must be hash-bound REFs. Wheel
metadata, filename and macOS arm64 tags must agree with the receipt.

The independent `fdisbull-source-sdist-pypi-identity-1` document supplies
`name`, `version` and a `files` array. Its unique source-file entry contains
`filename`, `metadata_match`, `yanked`, `packagetype`, `pypi_file_url`,
`pypi_release_api`, `pypi_sha256` and `pypi_size`. It must describe a
non-yanked official source distribution with the exact retained bytes. This
does not describe the locally built wheel as an official PyPI wheel. Staging
retains the original build and identity records, source archive, command logs,
toolchain evidence and a path index under `share/dependency-proofs`; the payload
inventory covers those files. Native application qualification remains separate.
These are operator-generated execution records. The installer checks their
identities and completeness; it does not prove that arbitrary recorded commands
ran. Produce them from the actual isolated build and independent wheel checks.
Simulated fixture records qualify the protocol only, never a dependency build.

The copied `share/verify-system.py` is version-neutral. It checks the file
inventory, CI artifact identities, native and delivery evidence, installed wheel
members and import locations. Its `active_default` field is true only when this
prefix is selected. The existing checker calls it with `verify`; the installer
can also supply explicit prefix and manifest arguments for a disposable test.

The regression tests exercise disposable prefixes and simulated protocol
records. They qualify installer behavior, not a real 0.35.0 installation. A new
release still requires actual Linux qualification, disconnected-kit acceptance,
publication/download readback, fresh Mac native results and live activation
readback before completion can be claimed.

The [0.31.1 installation snapshot](SYSTEM_INSTALLATION-0.31.1-HISTORY.md) is
preserved byte-for-byte for historical reference. Its active-selector statements
and qualification results describe that older installation, not today's prefix.

The finite subprocess runner terminates its exact owned process group on timeout
or output failure even if the original launcher has exited while a descendant
holds an output pipe. This cleanup does not inspect or stop unrelated apps.
