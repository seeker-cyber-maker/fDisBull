# CHIP-8 CPU-only QEMU profile

This profile connects a newly compiled QEMU TCG CPU/machine to fDisBull's
persistent source analysis and debugger. It is a bounded architecture experiment.
It does not change the DOS backend selector: DOSBox-X remains the default and
retained fallback. The dated [handoff](DOS_QEMU_HANDOFF.md) records actual local
build/test results and remaining gates.

## Reuse of the earlier architecture and sweding work

The classic opcode patterns and declared quirks come from the existing
[CHIP-8 pilot](../examples/chip8_pilot/README.md). The production static decoder
is compared with its classic classifier over all 65,536 words. That agreement
does not provide an independent historical execution oracle.

The earlier [Python UDC proof of concept](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/3e437a9e9ca313a2a24d18ef928a40fc5084b5f7/examples/chip8_pilot/PYTHON_UDC_POC.md)
remains on `agent/chip8-python-udc-poc-20261103`. Its hash-pinned opcode catalog,
manually sweded templates and trace-specialized outputs are useful conversion
work. Its generated Python still falls back to the authored interpreter, and
its intent records are candidate UDL/UIL rather than admitted common UIL. That
branch is preserved separately; it is not silently merged or relabelled as a
finished native conversion.

The new seam is source ROM → ordinary persistent FDB facts → a real QEMU
CHIP-8 CPU → fDisBull register/RAM/control/checkpoint operations. The
[G0–G8 end-to-end plan](milestones/2026-11-03-chip8-package-end-to-end-acceptance.md)
still governs qualification of source semantics, common UIL, registered UDC
providers, standalone emitted executables and reuse on held-out programs.
Building this debugger seam does not close those later conversion gates.

## Explicit source admission

For this source candidate, run the CLI from the checkout with
`PYTHONPATH=src python -m fdisbull` in place of `fdisbull` below. A shared
installation has its own payload and is not activated by these source tests.

```sh
fdisbull import /private/probe.ch8 /private/probe.fdb --arch chip8
# Equivalent explicit profile:
fdisbull import /private/other.ch8 /private/other.fdb \
  --profile chip8-classic-pilot-default-v1
```

The source is a caller-owned raw ROM of 2..3,584 bytes, mapped at `0x200` in
4 KiB of RAM. Source bytes and hash remain immutable in the original version.
No filename or host CPU inference selects the architecture. An odd-length data
tail is allowed; instruction starts must be even and contain a complete
big-endian 16-bit word. The persistent decode context is `chip8:16:big`.
An explicit base/entry override must still be `0x200`.

The static decoder recognizes the 34 non-legacy classic families. SYS calls,
SCHIP/XO extensions, invalid and truncated words remain undecoded. Skips retain
the taken `PC+4` and fallthrough `PC+2` edges when those destinations are in
range; an out-of-RAM taken target stays unresolved. Calls/returns remain distinct;
the V0-indexed jump stays indirect. I-based memory access facts keep their
address unknown unless the caller supplies an established I value. No address
is silently wrapped or invented from a missing register.

## Native CPU contract

The executable is a separately built `qemu-system-chip8` from the authored
[QEMU patch](../native/qemu-chip8/README.md), with machine `chip8-test` and
profile `chip8-classic-pilot-default-v1`. The CPU subset identity is
`fdisbull-chip8-cpu-smoke-1`. A raw ROM loads through `-kernel` at `0x200`.
There is no DOS image, PC firmware, guest OS or hidden interpreter process.

The first target uses one instruction per TCG block and a bounded native C
execution helper. It tests QEMU CPU/debugger integration; it is not an optimized
per-operation TCG backend or a newly qualified common-UIL representation.

Implemented words are `00EE`, `1nnn`, `2nnn`, `3xkk`, `4xkk`, `5xy0`, `6xkk`,
`7xkk`, `8xy0/1/2/3/4/5/6/7/E`, `9xy0`, `Annn`, `Fx55` and `Fx65`.
The declared pilot-default quirks use Vy for shifts, clear VF after logic,
and increment I after register transfers. Operands are read before writes,
including VF aliases. V0–VF are 8-bit; I, PC and return-stack entries are
stored as 16-bit values; SP has a maximum of 16. A valid final-byte transfer
can leave I at `0x1000`; a later out-of-range transfer faults rather than
wrapping. PC may advance beyond RAM and then fault on the next fetch.

Unknown/unsupported words, out-of-range fetch/transfer, stack under/overflow
and odd fetch addresses produce an inspectable sticky fault. Faulting
operations do not commit partial CPU/RAM updates. This aligned-fetch and
atomic-fault policy is an explicit implementation limit: the earlier authored
Python pilot permits odd fetches and can advance PC before some traps.
Successful-case comparisons with that pilot do not erase those differences.
Faults survive debugger edits, further resume and checkpoint restore; reset or
a fresh launch clears them. Editing PC is not implicit permission to clear a
recorded native fault.

`query-chip8-fault` binds the profile/subset and exposes fault code, source PC
and word. The debugger checks that identity and the complete GDB register XML;
it reads the CHIP-8 PC directly. A native fault takes precedence over a
breakpoint at the same PC. A timeout remains a timeout, without another guest
continue. Its late stopped-state inspection is a separate operation.

## Launch and inspect through fDisBull

```sh
fdisbull debug /private/probe.fdb \
  --backend qemu-chip8 --game-dir /private \
  --executable /external/build/qemu-system-chip8 \
  --qemu-checkpoint-tool /path/to/qemu-img
```

The same route is available through `debug-launch` and
`Project.debugger(..., backend="qemu-chip8")`. Select it explicitly. DOS/PC
clock, firmware, directory and device options refuse on this profile.
Original, unpatched CHIP-8 projects are admitted for execution; source patches
remain separate static versions and do not silently replace the running ROM.

For the authored ROM `6001 7002 A300 F055 1208`:

```python
with project.debugger(qemu, rom_directory, backend="qemu-chip8",
                      qemu_checkpoint_tool=qemu_img) as debug:
    point = debug.breakpoint(0x208)
    result = debug.run(timeout_ms=5000)
    assert result["outcome"] == "breakpoint"
    assert debug.registers()["registers"]["v0"] == "0x3"
    assert debug.memory(0x300, length=1)["hex"] == "03"
    debug.delete_breakpoint(point["breakpoint_id"])
    saved = debug.save_state()
    debug.write_memory(0x300, "7f", expected_hex="03")
    debug.load_state(saved["artifact"])
    assert debug.memory(0x300, length=1)["hex"] == "03"
```

Guarded register/RAM edits validate all guards before dispatch and read back
their effects. An uncertain mutation closes the owner rather than allowing
unobserved guest state or hidden breakpoints to remain live. Debug runs and
execution events are persisted in the FDB; an ended run is not a live session.

## Checkpoints and capabilities

The machine has no guest storage. With an explicit `qemu-img`, a private,
guest-unattached qcow2 node holds QEMU's full native snapshot. The snapshot
binds the exact source version/hash, CPU profile/subset, QEMU binary/version,
machine/RAM configuration and checkpoint-tool hash. CPU registers, stack,
fault state and all 4 KiB RAM are checked after load in a fresh QEMU process
before replacing the previous owner. Restore across QEMU binaries or CPU
profiles is refused. Host files are not restored.

Remove execution breakpoints before saving or loading this first checkpoint
profile. A reopened FDB can restore its artifact after explicitly launching
the same ROM and native runtime. A checkpoint is not permission to guess a
different source, dialect, device state or engine binary.

The new profile supports stopped inspection, bounded run/step, execution
breakpoints, guarded edits and native checkpoints. Display, keypad, timer,
audio/RNG, watchpoints, code/RAM layers, hooks, histories, selected undo and
comparative trials are not implemented for CHIP-8 and do not borrow DOS
semantics. Their existing DOS implementations remain retained and are tested
separately. IRQ/PIC and QEMM/DESQview task semantics remain DOS-profile work.

## Local checks

```sh
FDISBULL_CHIP8_QEMU=/external/build/qemu-system-chip8 \
FDISBULL_CHIP8_QEMU_IMG=/path/to/qemu-img \
FDISBULL_REQUIRE_CHIP8=1 \
python -m pytest -q tests/test_chip8.py tests/test_chip8_project.py \
  tests/test_qemu_chip8.py tests/test_qemu_chip8_native.py \
  tests/test_chip8_qemu_semantics_native.py
```

Tests use authored microprograms and independent expected states. The static
classifier comparison is labelled separately from executed native cases.
Native tests require the actual binary when `FDISBULL_REQUIRE_CHIP8=1`; an
optional skipped run is not acceptance evidence. No CI or default switch is
part of this slice.
