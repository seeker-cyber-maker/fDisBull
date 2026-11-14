# Evidence-bound system installation

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

Activation re-verifies the staged prefix, records the exact previous selector,
switches it atomically and checks the selected executable and installed package
identity. It invokes the existing `check_local_install.py` with the required
version and full source commit. A failed activation restores the prior selector
and installation record; the prior prefix and running private sessions remain
in place. Rollback restores the recorded selector and retains both prefixes.
Unknown external changes require reconciliation rather than an overwrite.

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
