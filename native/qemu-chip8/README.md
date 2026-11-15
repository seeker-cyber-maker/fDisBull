# Bounded CHIP-8 QEMU TCG target

This incremental QEMU 10.0.13 patch adds a real `chip8-softmmu` system target,
the `chip8-test` machine, a CHIP-8 CPU model, GDB register XML, and the
`query-chip8-fault` QMP command. The CPU is translated through QEMU TCG; the
initial implementation emits one helper-backed CHIP-8 instruction per
translated block so the host can inspect each instruction boundary.

## Profile and limits

The named profile is `chip8-classic-pilot-default-v1`, with instruction subset
`fdisbull-chip8-cpu-smoke-1`. The machine exposes exactly 4 KiB of RAM and loads
a raw ROM at address `0x200`. It has one CPU and no display, input, timers, or
sound devices.

The supported subset is `1nnn`, `2nnn`, `3xkk`, `4xkk`, `5xy0`, `6xkk`,
`7xkk`, `8xy0/1/2/3/4/5/6/7/E`, `9xy0`, `Annn`, `00EE`, `Fx55`, and `Fx65`.
The named profile uses the pilot's shift-from-`Vy` and logic-clears-`VF`
quirks; transfers increment `I`. Register-to-register operations that alias
`VF` use read-before-write behavior. Unsupported words, unsupported opcode
subforms, odd instruction addresses, and out-of-range fetches/transfers produce
a sticky inspectable CPU fault. Fault codes are 1 unsupported, 2 fetch outside
RAM, 3 data access outside RAM, 4 stack underflow, 5 stack overflow, and 6 odd
instruction address. Reset clears the fault; editing PC does not erase it.

This target deliberately requires word-aligned instruction addresses, whereas
the Python pilot can execute an odd fetch. The native target faults before
changing the faulting instruction's state. `I` and `PC` remain 16-bit so a
successful transfer may leave `I == 0x1000`, or a successful last-word
instruction may leave `PC == 0x1000`; a subsequent access then faults rather
than wrapping.

The GDB register file contains `V0` through `VF` (8 bits), `I` and `PC`
(16 bits), `SP` (8 bits, valid range 0 through 16), and 16 16-bit stack slots.
GDB values are little-endian. Stack reads at or above `SP` return zero; lowering
`SP` clears retired entries, and nonzero writes to inactive slots are left
unapplied.
VMState records CPU registers, stack, sticky fault, and the machine RAM. The
tested cold restore is for checkpoints made and loaded with this exact binary;
cross-binary migration is not qualified.

`query-chip8-fault` returns `profile`, `cpu-subset`, `faulted`, `fault-code`,
`fault-pc`, and `fault-opcode`. A QEMU GDB write to an invalid stack value may
receive the generic stub's `OK` reply, but the CPU callback leaves the invalid
value unapplied; callers must verify register readback.

## Build

The candidate was built from the pinned QEMU 10.0.13 source archive identified
in `source-manifest.json`, on macOS arm64 with TCG:

```sh
mkdir -p build-chip8 tmp-chip8
cd build-chip8
TMPDIR=../tmp-chip8 ../configure \
  --target-list=chip8-softmmu \
  --without-default-features --enable-system --enable-tcg --enable-pixman \
  --disable-user --disable-tools --disable-docs --disable-guest-agent \
  --disable-containers --disable-download --disable-install-blobs \
  --disable-debug-info --disable-qom-cast-debug --audio-drv-list= \
  --firmwarepath=../pc-bios --prefix="$PWD/install" \
  --ninja=/Users/tiga/miniconda/bin/ninja \
  --python=/Users/tiga/miniconda/bin/python3
TMPDIR=../tmp-chip8 /Users/tiga/miniconda/bin/ninja -j4 qemu-system-chip8
```

The tested binary SHA-256 is recorded in the manifest. This source patch is
incremental over unmodified QEMU 10.0.13; replay it with `patch -p1` at the
QEMU source root. The manifest points to a replay receipt that verifies each
patched file against the built candidate.

## Verification and claim ceiling

The frozen candidate passed 12 locally authored native cases with zero
failures, errors, or skips. They cover actual TCG execution, GDB register and
RAM access, calls/returns, pilot-specific arithmetic/shift behavior, bounded
memory transfers, explicit faults, breakpoints, QMP fault receipts, cold
checkpoint restore, and saved-project reopen. The recorded native receipt is
`R/chip8-native-03.log` with its paired XML/result evidence.

This is a bounded CPU/machine smoke target, not a complete CHIP-8 implementation
or evidence of DOS CPU portability. It does not model display, timers, sound,
keys, arbitrary ROM compatibility, or whole-game behavior. The real machine
uses a helper-heavy execution path, with one instruction per translated block;
performance and broader TCG optimizations are unmeasured. Only local macOS
build/native checks were run. Hosted CI, Linux, and cross-architecture builds
remain unverified.
