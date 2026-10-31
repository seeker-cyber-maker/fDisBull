# Bounded native NES and Genesis UDC

The two compiler modules consume the same declared UIL program and emit real
native cartridges: mapper-0 NES code for the RP2A03/6502, or Mega Drive/Genesis
code for the base Motorola 68000. Each cartridge has its own startup, controller,
display and application-tick code. The target program does not contain an
interpreter for the source console.

This is the first console UDC profile. It compiles unsigned variables, bounded
conditions and arithmetic. The separate Genesis byte lifter recognizes a small
straight-line function pattern from generated machine code. It requires explicit
RAM bindings and a function range. Recovering an arbitrary commercial game's
rules, graphics, sound, timing and hardware interactions remains separate work.

## Shared contract

`fdisbull.console_udc.compile_console_rom(program, target=..., display_variable=...)`
returns `rom` bytes and a `manifest`. `write_console_rom` writes the same result
as a new directory outside every Git worktree. The directory contains
`program.uil.json`, `manifest.json`, and `program.nes` or `program.md`.
Existing directories are refused. Compilation never marks a program executed.

Both backends accept `fdisbull-il-1`, role `uil`, with:

- One to 32 unsigned `u8` or `u16` variables, with declared initial values.
- `set`, `add`, `subtract`, and nested `if` statements. Arithmetic wraps to the
  destination width, as in the UIL reference executor.
- `eq`, `bit_test`, `not`, and `and` conditions. Variable operands must have the
  same width; literals must fit. Literal-only conditions use 16 bits.
- At most 256 statement/condition nodes, nesting depth eight, no resources,
  calls, external effects, unbounded loops or implicit source-console state.

`$buttons`, when declared, is a read-only `u8` controller input. Bits 0–7 mean
Right, Left, Up, Down, A, B, Start and Select. The three-button Genesis profile
has no Select button; that bit stays zero. An optional `u8` display variable
sets the horizontal position of an 8×8 marker. With no display variable, the
program still runs, without a marker.

The manifest identifies the target, ROM and canonical UIL hashes, variable RAM
bindings, architectural byte order, runtime symbols and compiler profile. All
`u16` bindings are aligned. NES variables occupy work RAM starting at `$0300`;
Genesis variables start at `$FF0000`. Reserved runtime locations hold a ready
sentinel and a completed-tick counter, outside the declared variable bindings.

Each tick waits for vertical blank, reads the pad, calls the generated logic,
increments its counter and updates the marker. To bound work, the NES compiler
rejects logic above a conservative 1,000 CPU cycles; Genesis rejects logic above
6,000. The NES calculation charges every emitted logic instruction, worst-case
branches and both condition bodies. Genesis charges 64 cycles for each decoded
instruction in its restricted emitted subset. Both reject unknown or incomplete
logic encodings. These are conservative logic bounds, not proofs of every
device wait or hardware timing interaction. Frame continuity was observed for
the test programs below in the specified cores.

## Use the interchangeable targets

The authored controller demo ships as `data/console-udc-demo.json` in the Python
package. From the source checkout, use a fresh private output directory for
each target (the parent directory must already exist):

```sh
fdisbull console-udc-targets
fdisbull console-udc src/fdisbull/data/console-udc-demo.json \
  --target nes --display-variable '$x' --output /private/new-nes-demo
fdisbull console-udc src/fdisbull/data/console-udc-demo.json \
  --target genesis --display-variable '$x' --output /private/new-genesis-demo
```

The JSON methods are `console-udc` with `path`, `target`, `output` and optional
`display_variable`, and `console-udc-targets` without parameters. They need no
analysis project or live DOS process. The same in-memory API is available from
an installed wheel:

```python
import json
from importlib.resources import files
from fdisbull.console_udc import compile_console_rom

program = json.loads(files('fdisbull').joinpath('data/console-udc-demo.json').read_text())
nes = compile_console_rom(program, target='nes', display_variable='$x')
genesis = compile_console_rom(program, target='genesis', display_variable='$x')
```

## Actual Genesis ROM → UIL → NES experiment

The source cartridge's application function increments an eight-bit value,
increments a 16-bit value across `$FFFF`, copies it, then subtracts one. The
source cartridge runs first in Genesis Plus GX. The lifter receives its actual
ROM bytes, exact logic range and explicit RAM bindings; it receives no original
UIL statements. Capstone's base-68000 decoder provides instruction facts. The
lifter recognizes supported load/arithmetic/store patterns, reconstructs UIL
and records source and function hashes. It refuses branches, unknown forms,
uncovered bytes, missing bindings or a function without a final return.

```python
from fdisbull.udl_genesis import lift

def recompile_straight_line_function(source_cartridge):
    symbols = source_cartridge['manifest']['symbols']
    recovered = lift(
        source_cartridge['rom'], logic_offset=symbols['logic_tick'],
        logic_length=symbols['logic_tick_end'] - symbols['logic_tick'],
        layout=source_cartridge['manifest']['variables'])
    return compile_console_rom(recovered['program'], target='nes')
```

This illustrates the function-range API; the full tested route uses the
straight-line source fixture in `scripts/verify_console_udc.py`. The controller
demo contains branches and is deliberately refused by this initial lifter.
Tests modify a native immediate and verify that the recovered UIL changes,
checking that recovery depends on source bytes. Variable names, initial values
and memory locations are caller-supplied assumptions, rather than recovered
whole-program knowledge.

## Emulator methodology and results, 2026-10-30

`scripts/check_console_udc.py` runs a real Libretro core in a disposable child
process, feeds scheduled controller inputs, captures RAM after each `retro_run`
and saves a final image from the video callback. It operates no GUI.
`scripts/verify_console_udc.py` compiles the fixtures and compares every completed
native application tick with the existing UIL reference executor. Three semantic
fixtures also have independently hand-calculated first-three-tick states.

The final run used 180 emulator frames per session, core defaults and these
exact macOS arm64 binaries from the official Libretro buildbot:

| Target | Core-reported version | Core SHA-256 |
| --- | --- | --- |
| NES | FCEUmm `(SVN) ac0d00a` | `5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60` |
| Genesis | Genesis Plus GX `v1.7.4 f27655b` | `27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268` |

The ten sessions passed **1,770 completed native tick/state comparisons**:

| Case | NES ticks checked | Genesis ticks checked | Boundary exercised |
| --- | ---: | ---: | --- |
| Controller marker | 176 | 178 | Right/Left, A, B, Up, Start, simultaneous buttons |
| Alias and wrapping arithmetic | 176 | 178 | Self-add, self-subtract, carry, borrow, eight/16-bit wrap |
| Nested conditions | 176 | 178 | `and`, `not`, equality, 16-bit high-bit tests, both branches |
| Literal high-bit regression | 176 | 178 | A false literal test following a nonzero high register byte |
| Genesis source / recovered NES route | 176 | 178 | Actual machine-byte recovery and cross-target generation |

After bootstrap, each sampled frame advanced the completed-tick counter exactly
once. NES startup took four frames; Genesis took two. Compare at the same
application tick, not the same host frame number. The recovered and original
UIL reference states also matched for 180 logical ticks. In the controller
case, 20 Right frames, 20 Left frames and ten later Right frames moved the marker
from x=8 to x=18 on both targets. Final frames were inspected from saved PNGs.

RAM interpretation was checked separately: NES RAM is direct little-endian
storage. For the exact tested Genesis core, raw RAM is byte-pair swapped;
architectural bytes are reconstructed at `offset ^ 1`, then interpreted as
big-endian words. A known-value native probe established that mapping before
semantic comparisons. The orchestrator refuses an unqualified core hash for
either target. Controller probes separately established button mappings; Genesis A maps
to Libretro Y, not Libretro A. The verifier predicts controller values from
scheduled inputs, rather than accepting observed RAM as its own oracle.

Single-session compile-and-write times were 1.09–3.12 ms; native subprocess
times were 0.17–0.29 seconds for 180 frames. These include private file I/O,
process launch and capture. They are descriptive observations on different
console workloads, not a controlled emulator-speed or compiler-throughput
ranking. Per-case times, core frame rates, source hashes, ROM hashes and trace
digests are in the [sanitized receipt](evidence/console-udc-2026-10-30/verification.json).
Raw ROMs, RAM, emulator states and screenshots remain outside Git and packages.

Reproduce from the source checkout with separately obtained matching cores:

```sh
python scripts/verify_console_udc.py \
  --nes-core /private/tools/fceumm_libretro.dylib \
  --genesis-core /private/tools/genesis_plus_gx_libretro.dylib \
  --frames 180 --output /private/new-console-verification
python -m pytest -q tests/test_console_udc.py tests/test_udc_nes.py \
  tests/test_udc_genesis.py tests/test_udl_genesis.py tests/test_console_udc_semantics.py
```

## Instruction-set references and remaining scope

Existing emulators provide mature CPU implementations and console-device models:
[FCEUmm](https://github.com/libretro/libretro-fceumm) and
[Genesis Plus GX](https://github.com/ekeeke/Genesis-Plus-GX). The
[Motorola M68000 reference](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf)
documents the processor family; later-family forms must still be excluded for a
base-68000 target. The compiler emits only instruction forms needed by its UIL
profile, and the emulator cores execute those bytes independently. The cores
are external test dependencies, not vendored into fDisBull.

Instruction documentation helps implement a lifter; it does not supply a game's
code/data boundary, memory map, peripheral semantics or an asset conversion.
This run qualifies authored programs and one explicit function pattern on the
two tested cores. Full-ISA lifting, arbitrary Genesis/NES game conversion,
graphics/audio conversion, mapper families, other console revisions, real
hardware timing and full semantic equivalence remain unqualified.
