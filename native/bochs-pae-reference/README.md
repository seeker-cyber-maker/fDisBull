# Optional Bochs PAE and PSE-36 reference

This private, opt-in reference uses Bochs 3.1's independent x86 full-machine
emulation and debugger. The only source change is [the debugger bridge](save-bridge.patch),
which calls Bochs's own `SIM->save_state` at the debugger stop. CPU, MMU and
restore implementations are upstream. The paired test runs 4 KiB and 2 MiB
PAE pages and a 4 MiB PSE-36 page on FreeDOS. It compares the stopped instructions before and after restore.
Keep guest disks, checkpoints and Bochs build products outside Git.

## Build

Use the [Bochs 3.1 source archive](https://downloads.sourceforge.net/project/bochs/bochs/3.1/bochs-3.1.tar.gz)
with SHA-256 `14aaf78dbe1337987923fffc4e7a962ae56abcf9a87474ace39e593f9f84ee84`.
Verify that digest before extracting. In the extracted `bochs` directory,
apply this repository's patch with `patch -p1` and build to a private prefix.

```sh
./configure --prefix="$BOCHS_PREFIX" --enable-debugger --enable-x86-64 \
  --enable-long-phy-address --enable-large-ramfile \
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

Four cases cover low and high backing for 4 KiB and 2 MiB PAE pages.
A fifth covers 4 MiB PSE-36 pages backed above 4 GiB. Use `-k pse36` to run
the PSE-36 comparison alone or `-k high` to run all three high-backed cases.
The tests select a 64 MiB QEMU PC with 32 MiB in each bank. To generate
that same profile for a caller-owned boot image, use

```sh
fdisbull dos-profile "$FDISBULL_QEMU_DOS_BOOT_IMAGE" --cpu max --memory-mib 64 --max-ram-below-4g-mib 32
```

The high cases request `memory: guest=4120, host=32, block_size=2048` in Bochs
(guest and host sizes in MiB, block size in KiB). Keep the sparse native
checkpoint on a filesystem that supports sparse files. In the saved Bochs
RAM file, physical addresses above 4 GiB use offsets reduced by the 1 GiB
PCI gap. The saved memory metadata identifies allocated blocks.

The guest writes executable bytes above 4 GiB and puts `UD2` at the
corresponding low 32-bit addresses. The test compares the stopped source
location, instruction bytes, page-table entries and selector state across the
two engines. It checks Bochs's native debugger translation and reads high and
low physical memory through the debuggers. Each receiving process restores
its engine's own snapshot. The [high-address results](../../docs/DOS_QEMU_HANDOFF.md#high-physical-backing-for-pae-le-tracking-2026-11-24)
include the tested PAE addresses and stop counts. The [PSE-36 results](../../docs/DOS_QEMU_HANDOFF.md#high-physical-backing-for-4-mib-pse-36-le-tracking-2026-11-24)
include both high addresses and the raw 32-bit page-directory entries.

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

## One-shot high-backed capture

With the native profile and `FDISBULL_BOCHS` configured as above, run the
paired test locally.

```sh
python -m pytest -q tests/test_qemu_dos_capture_code_pae_bochs_native.py
```

The test captures a 15-byte extent at the guest's remapped LE instruction
in 4 KiB PAE, 2 MiB PAE and 4 MiB PSE-36 fixtures. For each mapping Bochs
saves a native checkpoint and observes its first restored stop in a new
process. QEMU captures RAM and execute views on either side of its own cold
restore. The test reopens the project after each QEMU owner exits, exports
the captures, and compares their bytes, instruction, backing and page-table
entries with Bochs's debugger and saved state. The low 32-bit aliases contain
a distinct instruction. Keep the private guest images, project databases and
native checkpoints outside Git. See the [verified scope and overlay
limits](../../docs/DOS_QEMU_HANDOFF.md#one-shot-high-backed-le-capture-2026-11-24).

### Compare active execute overlays

Select the QEMU binary built with the [physical64 extension](../qemu-high-execute/README.md)
and the Bochs reference above. To run just the three active-overlay comparisons,
use the following command.

```sh
python -m pytest -q tests/test_qemu_dos_capture_code_pae_bochs_native.py -k high_execute_overlay
```

QEMU installs an execute layer at the instruction's high backing and a second
execute layer at its wrapped low alias. Each Bochs owner saves or observes its
untouched checkpoint before substituting the high byte in reference RAM and
stepping one instruction. The paired test compares the full original and
substituted windows, the stopped addresses, and the relative change in ESI.

### Compare writes to overlaid bytes on dirty pages

Select the [dirty-page QEMU candidate](../qemu-dirty-overlay/README.md) and the
same Bochs reference. Run the three high-memory cases locally with

```sh
python -m pytest -q tests/test_qemu_dirty_execute_overlay_pae_native.py
```

The guest writes to a sibling on the watched 4 KiB physical subpage, then
writes the overlaid byte. The next instruction writes a sentinel. Bochs
steps the original guest to supply the independent PC, page-table walk and
physical RAM values. QEMU runs through the two stores in a single debugger
call. Both engines repeat the sequence from their own native checkpoints in
fresh processes.

### Compare CMPXCHG outcomes on dirty pages

Select the [CMPXCHG candidate](../qemu-cmpxchg-overlay/README.md) and the same
Bochs reference. Run the six combinations locally with

```sh
python -m pytest -q tests/test_qemu_dirty_overlay_cmpxchg_pae_native.py
```

Each variant dirties the physical subpage via a sibling write and performs
three scalar compares with either all locked or all unlocked instructions.
The guest records the failed compare's accumulator, RAM byte and arithmetic
flags. QEMU runs past the failure and stops just after the changed-value
match. After rebinding to the new backing value, QEMU must also stop after a
same-value match. Bochs steps the same guest and supplies independent status
flags, bytes, addresses and post-instruction PCs. Both engines load their
own checkpoints in fresh processes before repeating the sequence.

### Compare CMPXCHG8B and split-store overlays

Select the [CMPXCHG8B candidate](../qemu-atomic-overlay-batch/README.md) and
the same Bochs reference, then run the local batch with

```sh
python -m pytest -q tests/test_qemu_dirty_overlay_atomic_batch_native.py
```

Each mode and prefix combination shares one guest program. A sibling write
dirties the watched subpage before the failed, changed-value and same-value
comparisons. After rebinding the execute layer, a separate DWORD write spans
two physical 4 KiB subpages and overlaps an override only on the second one.
Both engines repeat the sequence after cold restore. The test compares the
complete operands, accumulator pair, ZF, stopped PCs and untouched sentinel.

### Compare CMPXCHG16B page-fault retry and cross-page watchpoints

Select the [CMPXCHG16B candidate](../qemu-cmpxchg16b-fault-retry/README.md)
as `FDISBULL_QEMU_DOS` and the independent Bochs reference as
`FDISBULL_BOCHS`. With the existing FreeDOS, firmware and tool paths set,
run the local paired batch:

```sh
python -m pytest -q tests/test_qemu_cmpxchg16b_fault_retry_native.py tests/test_qemu_cross_page_watch_retry_native.py
```

The first authored MZ enters long mode and makes the aligned 16-byte
operand read-only before each comparison. Its guest fault handler records
error code, CR2, saved RIP, register values and old memory, then clears the
write restriction and retries. Bochs and QEMU independently save and
restore their own machine checkpoints before running both plain and LOCK
variants with low and high physical backing. The high case maps linear
`0x130000` to physical `0x100802000` and marks both low aliases
separately. Bochs uses sparse high RAM and checks its page translation;
QEMU binds an active execute layer through the linear address. The
receiving QEMU session starts in real mode. The receipt
records the exact QEMU and Bochs binary hashes, guest source hash, three
faults and the full observed outcomes.

The second case uses a high-backed PAE split DWORD store with an execute
layer on the first page and a GDB write watchpoint on the second. It checks
the committed word and untouched sentinel before and after restore.
Because x86 GDB watchpoints stop after access, this case alone does not
qualify stop-before-access retry ordering.
