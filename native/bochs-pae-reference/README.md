# Optional Bochs PAE reference

This private, opt-in reference uses Bochs 3.1's independent x86 full-machine
emulation and debugger. The only source change is [the debugger bridge](save-bridge.patch),
which calls Bochs's own `SIM->save_state` at the debugger stop. CPU, MMU and
restore implementations are upstream. The paired test runs both PAE page sizes
on FreeDOS and compares the stopped instructions before and after restore.
Keep guest disks, checkpoints and Bochs build products outside Git.

## Build

Use the [Bochs 3.1 source archive](https://downloads.sourceforge.net/project/bochs/bochs/3.1/bochs-3.1.tar.gz)
with SHA-256 `14aaf78dbe1337987923fffc4e7a962ae56abcf9a87474ace39e593f9f84ee84`.
Verify that digest before extracting. In the extracted `bochs` directory,
apply this repository's patch with `patch -p1` and build to a private prefix.

```sh
./configure --prefix="$BOCHS_PREFIX" --enable-debugger --enable-x86-64 \
  --with-nogui --disable-debugger-gui
make -j4
make install
```

Set `BOCHS_PREFIX` to an absolute path. On the tested macOS arm64 host, the
executable SHA-256 was
`06a966b0eb29f20540b8e17956d426a222f3ff15e64dfdb5554e61ab841c0641`.
The toolchain and build paths affect this digest. The installed `share/bochs/BIOS-bochs-latest`
SHA-256 was `530378cb25899f1063fb304d039edb33ea1c20ec784e65fed456233c07d9bf9a`
and `VGABIOS-lgpl-latest.bin` was
`157ee2e631c429114e48a8051c029ee79f1dc5adae59dd18178a6c6673c7cf37`.
The extracted upstream archive patched with this delta was byte-compared against
the built `bx_debug/dbg_main.cc`. The patch SHA-256 is
`5b2f68bf3e3605d11ece1809ffed4fb28cbe5cb2ae241730cdb2794610864e3e`.

## Run the paired comparison

Use the existing QEMU-DOS native test profile with `FDISBULL_QEMU_DOS`,
`FDISBULL_QEMU_IMG`, `FDISBULL_QEMU_DOS_FIRMWARE`, `FDISBULL_QEMU_DOS_MCOPY`,
`NASM` and the FreeDOS floppy at `FDISBULL_QEMU_DOS_BOOT_IMAGE`. From the
fDisBull repository, select the reference explicitly.

```sh
export FDISBULL_BOCHS="$BOCHS_PREFIX/bin/bochs"
python -m pytest -q tests/test_qemu_le_pae_bochs_parity_native.py
```

The helper locates the matching firmware under `$BOCHS_PREFIX/share/bochs`.
Use `FDISBULL_BOCHS_SHARE` for another matching firmware directory. Each test
stages the LE carrier on a private copy of the FreeDOS floppy and keeps its
checkpoint and traces in its own test directory. See the
[local results](../../docs/DOS_QEMU_HANDOFF.md#independent-pae-reference-for-protected-le-tracking-2026-11-24).

## Native checkpoint commands

Start with `bochs -q -debugger -f /absolute/path/to/bochsrc` to stop at
startup. At a debugger stop, save to an existing empty private directory.

```text
restore "__save_state__" "/absolute/path/to/state-directory"
```

The bridge reports `native save state PATH: OK` or `FAILED`. Exit the producer,
then start a separate process with `bochs -q -debugger -r /absolute/path/to/state-directory`.
Keep the matching disk image available to the receiver because the snapshot
references its configured floppy. Bochs documents the debugger and the native
startup restore option in its [debugger manual](https://bochs.sourceforge.io/doc/docbook/user/internal-debugger.html)
and [save and restore guide](https://bochs.sourceforge.io/doc/docbook/user/using-save-restore.html).
