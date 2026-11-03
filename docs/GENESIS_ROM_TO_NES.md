# Real Genesis ROM → UIL → NES pilot

The follow-up now produces a [playable first level on NES](MINIPLANETS_NES_LEVEL.md),
with original movement/collision comparisons and a naturally completed Genesis
replay. The bounded function experiment below remains a separate positive control.

The first real-game test uses **Miniplanets REMIX Ver. REV04**, by Javier
Degirolmo (Sik). The user confirmed that no Genesis cartridge was available in
their local intake. The pilot therefore acquired the prebuilt game from its
[official upstream repository](https://github.com/sikthehedgehog/miniplanets),
into a separate private intake. It is a third-party homebrew game, not an
fDisBull-authored fixture or a commercial Civilization cartridge.

The [upstream license](https://github.com/sikthehedgehog/miniplanets/blob/0ac9c395289cc5d0837c96d45e61a27300e8eebc/LICENSE.txt)
is zlib-style, copyright 2016, 2022 Javier Degirolmo. The intake preserves the
original notice and source. The original ROM, assets, recovered UIL, generated
cartridges and byte-retaining traces remain outside the tool repository and
packages. Only authored tooling/tests and sanitized evidence are committed.

## Source identity and selected behavior

| Item | Identity |
| --- | --- |
| Upstream commit | `0ac9c395289cc5d0837c96d45e61a27300e8eebc` |
| Original filename | `Miniplanets REMIX Ver (REV04).bin` |
| Size | 524,288 bytes |
| SHA-256 | `e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7` |
| Header | Mega Drive, product `GM SIK-MINI-04`, JUE; checksum matches |
| Selected function | `RunSpringFx`, CPU/file `0x54D4` to exclusive `0x54E0` |
| Upstream attribution | `src-68k/springs.68k`, lines 10–15 |

The unchanged game ran for 600 frames in the previously qualified Genesis Plus
GX core. Its saved final frame was inspected and shows the Miniplanets REMIX
title screen. This boot observation is separate from the controlled function
test; it does not establish that ordinary gameplay activated a spring.

The selected function decrements a spring-recoil effect's eight-bit timer and
clears its object type when the result reaches zero. Its identity has three
corroborating sources: matching native code, the attributed upstream routine,
and the original ROM's object dispatcher. The handler table starts at `0x4A7C`;
entry 27 at `0x4AE8` points to `0x54D4`. `ScanObjects` at `0x4B66` loads
`A0 = 0xFF0894`, indexes handlers by type and advances four bytes per object,
over 48 slots. This corroborates `ObjectList` and the field offsets independently
of names inferred by a disassembler. It does not prove a whole-ROM source rebuild.

The declared boundary supplies A0 pointing to the first object, with type at
`0xFF0894` and timer at `0xFF0897`. The function's projected effect is a modulo
256 decrement followed by clearing the type only if the new timer is zero.
An initial timer of zero wraps to 255. Condition-code output and return-stack
mechanics are outside the UIL state projection.

## Permanent native lifter profile

`fdisbull.udl_genesis.lift_native` adds a separate real-native profile alongside
the original generated-pattern `lift` API. It reads source bytes and explicit
bindings, not supplied UIL statements:

```python
from fdisbull.udl_genesis import lift_native
from fdisbull.console_udc import compile_console_rom

recovered = lift_native(
    original_rom_bytes, logic_offset=0x54D4, logic_length=12,
    layout={
        '$object_type': {'address': 0xFF0894, 'width': 8, 'initial': 27},
        '$timer': {'address': 0xFF0897, 'width': 8, 'initial': 60},
    }, address_registers={'A0': 0xFF0894})
nes = compile_console_rom(recovered['program'], target='nes')
```

The profile supports byte/word ADDQ, SUBQ, CLR and TST on bound RAM, forward
BRA/BEQ/BNE and RTS. Addressing may be `(An)`, displacement from An, absolute
word with 68000 sign extension, or absolute long. It requires complete source
coverage and a return on every path. It rejects loops, incoming-condition-code
dependencies, unbound memory/registers, unsupported effects, unreachable bytes
and branches into instruction middles. Bounds apply to source length,
control-flow lowering and the resulting console UIL. It records source/function
hashes, mapping, bindings, address-register assumptions and native facts.

The supplied bindings are assumptions. This profile does not discover the game's
entire state, recover arbitrary C or emulate all 68000 instructions in UIL.
The existing NES compiler handles the resulting logic unchanged.

## Independent original-CPU oracle

`scripts/probe_genesis_function.py` loads the original file into the existing
Genesis Plus GX binary, then uses that core's exported CPU API. A bounded call
to its actual `m68k_run` executes each instruction. Capstone supplies trace
lengths; it does not calculate the instruction's effects.

The exact core is `v1.7.4 f27655b`, SHA-256
`27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268`.
The tool refuses another binary: its native context layout and byte-pair RAM
representation are specific to this qualified macOS arm64 build. The CPU API
and structure are documented in upstream
[m68k.h](https://github.com/ekeeke/Genesis-Plus-GX/blob/f27655b/core/m68k/m68k.h)
and [m68kcpu.c](https://github.com/ekeeke/Genesis-Plus-GX/blob/f27655b/core/m68k/m68kcpu.c).

For each case, the probe clears work RAM and registers, applies declared seeds,
masks interrupts, sets A0, and enters the original function with a controlled
return frame. It stops at the return sentinel, requiring RTS to consume exactly
four stack bytes. Instruction/cycle budgets and allowed PC ranges bound the
call. Every fetched word is checked through the core's live mapping against the
original file. Full pre/post RAM comparison rejects changes outside the declared
watches and explicitly allowed return-stack area. Registers and flags are also
recorded. Source, core, contract and probe hashes must remain unchanged.

This is controlled entry into real code in the original ROM mapping. It is not
an observation of a naturally reached game call, and these initialized states
do not reproduce a complete gameplay context or device timing.

## Results and controls, 2026-10-30

The integrated `scripts/verify_genesis_rom_route.py` experiment passed:

- **768 original-CPU input cases:** every timer value 0–255, each with object
  type 0, 27 or 255. All matched the recovered UIL and an independently derived
  arithmetic rule. This covers the full timer domain for three type values,
  not all 65,536 type/timer combinations.
- **2,307 actual 68000 instructions**, totaling 229,670 core master cycles.
  Both conditional paths ran. No undeclared RAM changes occurred; D0–D7 and
  A0–A6 were unchanged. SR/CCR, A7 and control return are excluded projections.
- **Eight generated NES sessions**, each 180 emulator frames, with **1,408
  completed transitions** checked directly against the original-CPU result
  table. Every tick also matched the UIL executor. After four startup frames,
  the counter advanced once per sampled frame.
- A deliberately wrong UIL addition in place of subtraction disagreed with
  the original CPU in **768/768 cases**, demonstrating a sensitive comparison.
- A separate negative native probe omitted the timer watch and failed on the
  undeclared write at `0xFF0897`.

Seven NES sessions repeat bare function calls from timer values 0, 1, 2, 60 and
255 and representative object types. They test the function contract, including
wrapping, rather than asserting original-game scheduling.

The eighth session adds a separately authored single-object dispatcher guard:
call the recovered body only while type is 27. A presentation variable drives
the existing NES marker from the timer. Starting at 60, the timer reaches zero,
the object is cleared, and subsequent ticks leave it removed. The original
handler-table behavior motivates this adapter, but the guard and marker are
explicitly authored, not recovered from the function's twelve bytes. No game
artwork, physics, sound or complete scene was converted.

The [sanitized receipt](evidence/genesis-rom-route-2026-10-30/verification.json)
records per-session hashes/counts/times, source identity, dispatcher facts,
the declared projection, source immutability and the negative control. Recorded
wall times include core setup, input reset, trace capture and private I/O; they
are not a controlled cross-console speed ranking. Core cycle counts are not
real-hardware timing measurements.

## Reproduce

Obtain the original ROM from the attributed, pinned upstream commit and keep it
outside the fDisBull worktree. Use the exact cores identified in the receipt and
a Python environment with the package dependencies. From the source checkout:

```sh
python scripts/verify_genesis_rom_route.py \
  --rom '/private/intake/Miniplanets REMIX Ver (REV04).bin' \
  --nes-core /private/tools/fceumm_libretro.dylib \
  --genesis-core /private/tools/genesis_plus_gx_libretro.dylib \
  --output /private/new-real-rom-route
```

The output directory must be new and outside every Git worktree. A changed
source hash or unqualified core is refused. The generic native CPU probe accepts
an explicit contract with entry/ranges, RAM/register seeds, watches and budgets;
it runs in a disposable child process and also supports explicit block exits.
The Miniplanets orchestrator is intentionally a hash-bound pilot recipe.

This demonstrates a real game's bounded machine-code behavior surviving
**original ROM → UIL → native NES execution**. Whole-game translation and
natural gameplay reachability remain unqualified.
