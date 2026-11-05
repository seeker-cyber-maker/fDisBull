# NES C/Python before UIL experiment

This source-only experiment asks whether rewriting a small NES routine into
Python before UIL makes semantic block combination easier.

## Result

**Do not make general Python a mandatory IL before UIL.** Python is useful as an
executable hypothesis, reference oracle, host-service provider and build-time
transform language, but ordinary Python integers do not preserve machine widths.
A mandatory Python layer therefore needs a new restricted dialect and another
translation/proof edge.

**Use restricted typed C as the structured recovery view for pure machine-logic
regions.** C is not the UDL evidence itself. Source bytes, addresses, flags,
memory aliases, effects, timing and provenance stay attached separately. The
current bounded Clang-AST frontend can then import admitted C into UIL.

The proposed pipeline is:

```text
6502 bytes
  -> exact UDL / CFG / memory and effect facts
  -> deterministic pure-region discovery
  -> typed C or SSA recovery view
  -> bounded C frontend
  -> canonical UIL
  -> selectable UDC providers
       - Python host/reference provider
       - generated native code
       - retained native island
       - compatibility/emulation provider
```

## Authored fixture

The script builds a 32 KiB NROM image containing a 56-byte tick routine. The
routine reads one input bit, updates an 8-bit position/cooldown state, writes one
sound register when a shot is accepted, and writes one display register every
tick.

The bounded interpreter compares all:

```text
2 button states × 256 positions × 256 cooldown values = 131,072 states
```

The retained receipt records:

| Candidate | Mismatches against the 6502 routine |
| --- | ---: |
| Compiled fixed-width C | 0 |
| Python with an explicit `& 0xff` width operation | 0 |
| Ordinary unmasked Python | 3 |

The three unmasked failures are `x = 253, 254, 255` when the accepted shot adds
three. Nearly every ordinary case passes, which is precisely why friendly
high-level rewrites make such charming little traps.

The original routine contains eight machine basic blocks. A deterministic
partition at observable hardware writes finds one pure-state candidate region,
one APU boundary and one PPU boundary. The partition is visible in CFG/effect
facts before any agent rewrites the blocks into Python. Clang reduces the typed-C
shape from seven LLVM blocks at `-O0` to four at `-O2`; that is a fusion hint, not
source equivalence proof.

## Reproduce

Use a new output directory outside every Git checkout:

```sh
python examples/nes_c_python_before_uil/experiment.py \
  --clang /absolute/path/to/clang \
  --output /private/new-nes-c-python-before-uil
```

The command writes the authored ROM, tick bytes, C source, Python source, Clang
AST, LLVM IR and a fresh receipt into that private output directory. Generated
binary artifacts are intentionally not tracked.

## Evidence boundary

The fixture is structurally bootable, but this experiment executes the tick
entry through its bounded interpreter. It does not claim PPU presentation in an
established NES emulator, whole-game recovery, timing equivalence or a general
6502-to-C translator.

The committed `receipt.json` is a sanitized result from the exhaustive run. The
focused repository test checks the source shape, block partition and width-boundary
counterexample without requiring Clang or generating a ROM in the checkout.
