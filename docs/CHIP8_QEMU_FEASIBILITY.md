# CHIP-8 as a real QEMU CPU target: feasibility note

**Status:** source-grounded feasibility assessment only. No QEMU source was
changed or built for this note.
**Inspected QEMU source:** local QEMU `10.0.13` tree in the fDisBull native
runtime study area, at the time of this assessment. Absence statements below
refer only to that inspected tree and version.

## Recommendation

A CHIP-8 QEMU target is technically feasible and is a useful debugger
generalization experiment. It is a separate architecture port, however, rather
than a small reuse of the DOS debugger. The smallest credible first result is a
new TCG CPU target and minimal system machine that executes a short CHIP-8 test
program inside QEMU and exposes its architectural state through QEMU debugging
interfaces. A Python CHIP-8 interpreter hosted beside QEMU, or an interpreter
implemented as a QEMU device without a CHIP-8 CPU target, would not meet that
test.

Keep the first result deliberately narrow: test the real TCG CPU, register and
memory observation, stepping, breakpoints and saved-state restoration. Add
keypad, display and timers only after that CPU/debugger seam works. This tests
whether fDisBull can add a genuinely different QEMU architecture without
claiming a complete CHIP-8 environment or game port.

## What exists today

The CHIP-8 pilot is useful source material, but it is not a QEMU target or an
independent emulator oracle:

- [`examples/chip8_pilot/README.md`](../examples/chip8_pilot/README.md) describes
  an authored Python classic interpreter, two authored decoders and a small
  corpus pilot. It explicitly says the interpreter has not been historically
  qualified and leaves keyboard release, font variants, SCHIP/XO execution,
  vblank, audio and original timing unqualified.
- [`examples/chip8_pilot/RESULTS.md`](../examples/chip8_pilot/RESULTS.md)
  reports the bounded 2026-11-02 results: 196,608 word/profile decoder
  comparisons, six classic ROM runs, 26/34 observed classic non-legacy
  instruction families, and a total nine-ROM pinned corpus. The report
  distinguishes same-VM repeatability and synthetic gap probes from independent
  semantic qualification and natural corpus observation.
- [`docs/REUSABLE_ANALYSIS_PACKAGES_RFC_2026-11-03.md`](REUSABLE_ANALYSIS_PACKAGES_RFC_2026-11-03.md)
  makes CHIP-8 a virtual ISA with **no conventional OS**. CPU/ISA behavior is
  separate from the host environment's keypad, display, clock, RNG and timing
  policy. The RFC is a proposed package design, not a registered production
  closure.
- [`docs/milestones/2026-11-03-chip8-package-end-to-end-acceptance.md`](milestones/2026-11-03-chip8-package-end-to-end-acceptance.md)
  remains a proposed G0–G8 gate plan. Open gates include independent
  interpreter/spec qualification, accepted semantic contracts, the ordinary
  source→UDL→UIL→UDC execution path, held-out package reuse and a verified
  delivered artifact. The QEMU smoke proposed below would not close those gates.
- [`docs/examples/chip8-package-closure.example.json`](examples/chip8-package-closure.example.json)
  labels itself illustrative-only, not registered and not executable.

## QEMU source findings

In the inspected QEMU `10.0.13` checkout, there is no CHIP-8 directory in
`target/`, `hw/` or `configs/targets/`. This is a version-and-checkout finding,
not a statement about every QEMU fork or later release.

The nearest small CPU-front-end example is RX:

- `target/rx/cpu.h`, `cpu.c`, `translate.c`, `insns.decode`, `gdbstub.c` and
  `disas.c` implement CPU state/QOM, translation, instruction decoding,
  registers and disassembly.
- `target/rx/meson.build` runs QEMU's `decodetree.process()` on
  `insns.decode` and adds the generated decoder and frontend sources to the
  architecture sourceset.
- `hw/rx/rx-gdbsim.c` and `hw/rx/meson.build` show the separate system-machine
  layer that creates the CPU, maps RAM, loads an image and sets the initial PC.
- AVR is another structural reference: `target/avr/` holds its CPU frontend,
  while `hw/avr/` holds MCU/board code. It is substantially more hardware than
  the proposed CHIP-8 smoke needs.

QEMU's build organization reinforces that split. A new system target needs
target configuration plus target-dependent CPU sources, and a system machine
adds `hw/` sources and device configuration. The official build documentation
describes the target `.mak`, `target/`, and `hw/` source-set roles; the TCG
documentation explains that a target frontend translates guest instructions
into host operations and that guest PC/state must be recoverable at execution
boundaries. See [QEMU's build-system architecture](https://www.qemu.org/docs/master/devel/build-system.html)
and [TCG translator internals](https://www.qemu.org/docs/master/devel/tcg.html).
The inspected version's RX frontend is also available in the official
[QEMU v10.0.13 source tree](https://gitlab.com/qemu-project/qemu/-/tree/v10.0.13/target/rx).
The linked `docs/master` pages identify themselves as QEMU 11.1.50; they are
used here for general architecture/build concepts only. The exact RX source
layout and absence check were made against the local QEMU 10.0.13 tree.

This is a **new compiled QEMU target/machine**, requiring a separately pinned
QEMU source/build identity and a binary that includes it. It is not a normal
runtime plugin that can be loaded into the existing x86 QEMU binary. QEMU's
configure target list determines which system emulators are built, and its
target and hardware source sets are compiled into those emulator binaries.
QEMU's [TCG plugin API](https://www.qemu.org/docs/master/devel/tcg-plugins.html)
instruments translations and execution of an existing target; that API does
not supply a new guest instruction decoder or CPU architecture.

## Existing fDisBull reuse and coupling boundary

Some low-level control ideas can transfer: GDB remote-protocol transport,
QMP transport, operation deadlines, immutable artifacts and generic project
storage. The current QEMU debugger integration is not architecture-neutral,
though:

- `src/fdisbull/qemu_machine.py` launches x86 `pc`/`q35` machines, admits only
  `max`/`486` CPU models, assumes PC boot devices and firmware, classifies
  stops using machine address state, and has x86-specific tracing/disassembly
  paths (`iced_x86`). `MachineDebugSession` requires a raw project with
  `arch == 'x86'` (see its constructor and `trace` methods).
- `src/fdisbull/gdb_rpc.py` discovers registers from QEMU's XML, which is a
  useful generic seam, but register serialization is little-endian and memory
  access toggles QEMU's `qqemu.PhyMemMode`; neither establishes CHIP-8's
  register model or address semantics by itself.
- `src/fdisbull/loader.py` currently admits raw `x86`, `arm64`, and `thumb`,
  while `src/fdisbull/decoder.py` dispatches those architectures. CHIP-8's
  16-bit words, 12-bit address fields, and optional longer XO instruction need
  their own loader/decoder profile if they are to enter the usual analysis
  pipeline.
- DOS task scheduling, private RAM/fetch views, PIC IRQ provenance, DOS file
  operations, frame-key ownership, frame history and DOS workspace behavior
  are implemented through Python mixins such as
  `qemu_dos_process.py`/`qemu_dos_checkpoint.py` and native code under
  `target/i386/`. They describe the DOS/x86 machine and guest protocol. They
  must not be presented as generic QEMU-CPU facilities or assumed to work for a
  CHIP-8 machine.

The useful generalization target is therefore a separate architecture-aware
machine/debugger layer that reuses only proven transport/storage primitives.
The answer to “can the machinery generalize easily?” is **partly**: GDB/QMP
transport, operation-budgeting, artifact persistence and some orchestration
ideas are candidates for reuse, but the current CPU/register/address/loader/
decoder/stop model is not generic. The DOS QEMU scheduler, PIC and frame
ownership, DOS file witness, and DOS disk/workspace layers are semantically
specific to their PC/DOS execution profiles and guest protocols, including the
implemented protected/V86 paths. The save witness has the narrower real-mode,
unpaged admission rule. A CHIP-8 implementation
would need an architecture-aware adapter and new native target code. Making the
DOS session class accept a CHIP-8 binary without replacing its machine
assumptions would be misleading; completing CHIP-8 would not complete or
generalize DOS parity by itself.

## Smallest real-TCG experiment

Add a `chip8-softmmu` target with a named minimal machine, for example
`chip8-test`:

1. Add a CPU state/QOM type with V0–VF, I, PC, a bounded call stack and the
   classic-profile identity. Implement reset and the CPU-class execution hooks.
2. Add a TCG translator and decoder for a deliberately small legal subset:
   immediate/register loads, add, conditional skip, jump, call/return and
   bounded memory transfer. Unknown or unsupported words must stop/fault
   explicitly; they must not silently become no-ops. Keep profile quirks
   explicit rather than folding them into a universal CHIP-8 definition.
3. Add CPU VMState and a GDB register description for the implemented
   architectural state. Use a minimal machine with 4 KiB RAM and a raw test
   image loaded at `0x200`. Do not add a fake DOS-like OS or claim keypad,
   screen or timers in this CPU-only pass.
4. Run an authored short binary in QEMU TCG. Verify QEMU's stopped PC, selected
   V registers, I, stack state and RAM through QEMU's actual debug interfaces;
   exercise single-step and a guest-address breakpoint; save and restore a
   stopped machine and check those values again. Keep expected values as a
   small independent golden table, rather than deriving every expectation from
   the pilot interpreter.
5. Exercise those same controls through a thin fDisBull CHIP-8 machine profile:
   explicit CHIP-8 source admission, XML registers and byte order, flat bounded
   RAM and PC/stop interpretation. Require this adapter before declaring the
   first debugger-generalization result; standalone GDB success alone proves
   the QEMU target, not reuse by fDisBull. It must not fall back to x86 parsing.

This is a real QEMU guest CPU only if QEMU itself decodes and executes those
instructions through TCG. QEMU documents system emulation as a virtual machine
model containing CPU, memory and emulated devices, with QMP and GDB as control
interfaces; a later environment stage can add those devices without changing
the meaning of the first CPU result. See [system emulation introduction](https://www.qemu.org/docs/master/system/introduction.html).

## What would prove debugger generalization

The first CPU smoke is necessary evidence, but it is not enough to say the
whole debugger is generic. Keep the architecture-specific contract explicit:
launch/reset, register names and wire byte order, program-counter identity,
memory spaces and bounds, instruction decoding, stop causes and snapshot
identity. The shared session should consume that contract without importing
the DOS segmented-address or HMP register parser for a CHIP-8 run.

| Machinery | Required non-x86 witness before claiming reuse |
| --- | --- |
| Run/step/breakpoints | An authored branch/call/return route stops at the actual CHIP-8 PC; the next instruction has not executed; a timeout remains a distinct cause |
| Checkpoints | Fresh-process restore preserves every implemented CPU field and RAM, rejects another ROM/profile/runtime identity, and continues to the same next result |
| RAM and code layers | A CHIP-8 data overlay and a separate fetch overlay have declared precedence; changing active code invalidates translated blocks; deactivation exposes the original bytes |
| Hooks | A hook at a CHIP-8 PC runs its declared action once under its hit policy, preserves a competing breakpoint and pending step state, and restores consistently |
| Histories, selected undo and trials | Selected CPU/RAM restoration changes only the chosen state; a trial restores its baseline and does not publish host effects; architectural fields are identified without x86 names |
| Frame/input/timing | Later device-stage tests compare actual framebuffer bytes, key make/release and timer phase under a declared schedule, including checkpoint restore |

These are proposed acceptance tests, not observations from this assessment.
DOS PIC/cascade IRQ and QEMM/DESQview task semantics remain DOS-profile tests;
a CHIP-8 machine should declare its own supported events and capabilities.
The later AGI CPU and LLVM executable-synthesis milestones remain separate:
executing a new TCG frontend does not itself recover UIL or emit and qualify
an executable for another architecture.

## Staged acceptance and effort bands

These are planning ranges for one experienced QEMU C developer with review
available; they are not estimates from a build or implementation trial.

| Stage | Acceptance | Rough effort range | Main dependency/risk |
|---|---|---:|---|
| Target skeleton | Configure/build a new `chip8-softmmu`; QOM CPU resets and runs a controlled stop/exception path | 2–5 engineering days | New target/build registration and machine bootstrap work may expose QEMU-version-specific glue |
| CPU/debugger smoke | Implement the bounded subset above; GDB registers/PC, memory read, step, breakpoint and stopped save/restore agree with golden cases | 3–8 additional days | Accurate TCG state restoration at branch/exception/debug boundaries; VMState and GDB register contract |
| fDisBull non-x86 adapter | The same microprogram passes run/step/breakpoint, register/RAM and fresh-process restore through fDisBull with an explicit CHIP-8 profile | 2–7 additional days | Source admission, register byte order, PC/stop identity and checkpoint binding must avoid existing x86 assumptions |
| Classic-profile extension | Expand toward all classic non-legacy instruction families; negative memory/stack/input-wait cases and independent reference comparison | 1–3 additional weeks | Quirk semantics and a separately qualified oracle are not supplied by the existing pilot |
| Environment devices | Add a documented keypad, 60 Hz timer policy and display/framebuffer interface; test deterministic input and timer schedules | 1–4 additional weeks | Device event ordering, input release, rendering, timer phase and stop semantics |
| Package closure | Extend the minimal loader/debugger profile into source mapping, evidence receipts, qualified semantic providers and reusable environment/ISA identities | 1–3 additional weeks | The ordinary source-to-UIL/target path and package qualification remain separate from basic debugging |

The stages can overlap only after their interfaces are agreed. The ranges can
grow if the initial CPU target requires broader QEMU core changes, if upstream
review constraints are included, or if full game/environment behavior becomes
part of the acceptance scope.

## Recommendation for the next slice

First settle a one-page CPU/machine contract: classic profile only, address and
PC width, stack bounds, unknown-opcode policy, GDB register names, RAM map,
image load location and VMState fields. Then implement only the target
skeleton and CPU/debugger smoke, using an authored microprogram that covers
arithmetic, a branch, a call/return, one memory round-trip and an intentional
unsupported word. Connect the thin fDisBull profile at this stage so the result
actually tests this debugger. Do not start with a game or display.

After that passes, the next meaningful milestone is an **environment** slice:
keypad make/release, explicit timer advancement and framebuffer observation,
with separate receipts for device behavior and CPU instruction behavior. Only
then does it make sense to connect a pinned public ROM, an independent mature
interpreter/spec oracle, and the proposed package-resolution/end-to-end gates.

No source implementation, build, guest run, or package qualification is
asserted by this feasibility note.
