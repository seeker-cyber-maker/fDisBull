# fDisBull 0.18.0 — shared Mac installation

Installed source: `416b64d9f4bfcf56e2876656d43f1d6a3d6cfdae`, tag `v0.18.0`.
The stable selector is `/Users/Shared/fDisBull/current`. Global commands are
in `/usr/local/bin`, also exposed through Homebrew's bin directory. The old
user-local 0.8.1 launcher now forwards to the shared installation.

## Commands

```bash
fdisbull --version
fdisbull --help
fdisbull agent-skill
fdisbull-runtime
fdisbull-python -c 'import fdisbull; print(fdisbull.__version__, fdisbull.__file__)'
```

`fdisbull-python` is the managed interpreter for Python API scripts. Existing
Conda and project environments were not modified. App launchers select the
qualified environment and do not inherit a project-specific PYTHONPATH.
`fdisbull-dosbox` selects the native Mac backend; `fdisbull-qemu` selects the
copied QEMU with its matching firmware. `fdisbull-runtime` returns version-bound
Python/JSON launch profiles for DOSBox, DOS-in-QEMU, Wine/QEMU and raw machines.

```python
import json, subprocess
from fdisbull.project import Project
runtime = json.loads(subprocess.check_output(["fdisbull-runtime"], text=True))
with Project("your-private-project.fdb") as project:
    with project.debugger(game_dir="/path/to/your/private/game",
                          **runtime["profiles"]["dos"]) as debug:
        print(debug.registers())
```

Keep game files, projects and saved states outside this installation. The
included boot filesystems are audited pristine OS/runtime inputs, not captured
sessions. Scene probing currently supports direct DOSBox; C/C++ decompilation
and source-view debugging are not implemented in 0.18. Mac backends use the
existing Homebrew shared libraries on this machine.

The source docs, two replay drivers, bundled skill and selected verification
receipts are under `share/`. Run the local payload verifier with:

```bash
fdisbull-python /Users/Shared/fDisBull/current/share/verify-system.py
```

The previous 0.8.1 launcher is preserved in
`/Users/Shared/fDisBull/backups/2026-10-27-before-0.18.0/`.
The shared `current` selector and recorded launcher backups make activation
reversible; the installer did not migrate or open existing project databases.
No new DeepSeek delivery folder or offline archive was created.

This tool is not currently suitable for malware analysis or security work.
Must bring your own weapons. I have only done this once before. Safety not guaranteed.
