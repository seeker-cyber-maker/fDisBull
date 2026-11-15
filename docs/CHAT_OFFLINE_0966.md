# Offline agent kit: 0966c331 / 0.34.1

This Linux x86-64 kit pins the application to
`0966c331f653952b638e42bb1bc5a9afff6ada33`. Its packaging harness has a separate
identity recorded in the delivery receipt. Packaging changes do not change that
application wheel or transfer earlier CI results to the harness.

The selected execution components are the retained DOSBox layers backend and
QEMU 9.2.4, with compact DOS/Wine and separate full-Windows runtime inputs.
This is not the native QEMU DOS migration or a CHIP-8/AGI/Gob runtime delivery.
Portable Python and dependencies are included: do not run pip, download packages
or compile native components. Consult the exact archive's delivery receipt for
its acceptance result; assembly alone does not qualify a kit.

## Extract once

Check the archive SHA-256 against the delivery receipt. Use a new destination,
preserve executable permissions, and keep the extracted kit immutable. For a
Python-only extractor, this bounded example rejects links and unsafe paths:

```python
from pathlib import Path, PurePosixPath
import shutil, stat, zipfile

archive = Path("/absolute/fdisbull-chat-offline.zip")
destination = Path("/absolute/new-kit-parent")
destination.mkdir()  # Refuses to overwrite an existing extraction.
seen, total = set(), 0
with zipfile.ZipFile(archive) as zipped:
    for member in zipped.infolist():
        parts = member.filename.rstrip("/").split("/")
        kind = stat.S_IFMT(member.external_attr >> 16)
        if (parts[0] != "fdisbull-chat-offline" or "\\" in member.filename
            or any(p in ("", ".", "..") for p in parts)
            or PurePosixPath(member.filename).is_absolute()
            or member.filename in seen or kind not in (0, stat.S_IFREG, stat.S_IFDIR)):
            raise ValueError("Unsafe or duplicate archive member")
        seen.add(member.filename); total += member.file_size
        if total > 4 * 1024**3: raise ValueError("Extraction exceeds kit budget")
        target = destination.joinpath(*parts)
        if member.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipped.open(member) as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        target.chmod((member.external_attr >> 16) & 0o777 or 0o644)
```

If a different trusted extractor dropped executable bits, restore these before
using the entry points:

```sh
cd /absolute/new-kit-parent/fdisbull-chat-offline
chmod +x bin/* python/bin/python3.13 lib/ld-linux-x86-64.so.2 \
  native/dosbox-x native/qemu/bin/qemu-system-x86_64
./bin/fdisbull --help
./bin/fdisbull agent-skill --reference SKILL.md
./bin/player --help
```

## Prepare private runtime caches

All cache paths must be absolute and outside the kit. Preparation uses only
bundled inputs and returns the resulting paths as JSON:

```sh
./bin/prepare-runtimes --cache /absolute/private/compact-cache
./bin/prepare-runtimes --windows --cache /absolute/private/windows-cache
```

Keep enough writable space for reconstructed images, private analysis and saved
states; the full Windows base expands to several GiB. Compact PE64 uses 4096 MiB
of guest RAM. Full Windows uses 8192 MiB, plus host/QEMU memory headroom. Run one
guest at a time. Full Windows includes Wine64/PE32 dependencies; the declared
native acceptance is a bounded authored PE64 workflow. It does not establish
PE32, Win16, Microsoft Windows or whole-game compatibility.

## Open a private target

Use the bundled interpreter for Python examples. Keep your own games, assets,
FDBs, object stores, screenshots and Anchor Stones outside the immutable kit and
outside Git. Set private storage paths before creating a project:

```sh
export FDISBULL_TARGET_STORE=/absolute/private/objects
export FDISBULL_OUTPUT_ARTIFACT_DIR=/absolute/private/artifacts
./bin/python /absolute/private/investigate.py
```

For a DOS target, `investigate.py` can use the normal public API:

```python
from pathlib import Path
from fdisbull.project import Project

kit = Path("/absolute/new-kit-parent/fdisbull-chat-offline")
work = Path("/absolute/private/dos-analysis")
game = Path("/absolute/private/dos-game")  # Your target and required assets.
work.mkdir(parents=True, exist_ok=True)
with Project.create(work / "target.fdb", game / "PROGRAM.EXE") as project:
    with project.debugger(kit / "bin/dosbox", game) as debug:
        print(debug.registers())
```

For a PE target using the included full-Windows image:

```python
from pathlib import Path
from fdisbull.project import Project

kit = Path("/absolute/new-kit-parent/fdisbull-chat-offline")
work = Path("/absolute/private/pe-analysis")
game = Path("/absolute/private/pe-game")
work.mkdir(parents=True, exist_ok=True)
with Project.create(work / "target.fdb", game / "PROGRAM.EXE") as project:
    with project.debugger(kit / "bin/qemu", game,
            kernel=kit / "runtime/kernel",
            initramfs=Path("/absolute/private/windows-cache/wine.cpio.gz"),
            memory_mib=8192, boot_timeout_ms=600000) as debug:
        print(debug.registers())
```

Use `compact-cache/wine.cpio.gz` and `memory_mib=4096` for the compact PE64
profile. Guest startup checks the protocol and complete runtime resource map
against the bundled application. Preserve an identity mismatch as a failure;
do not replace files or fetch another backend to bypass it.
