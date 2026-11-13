# UDC native verification examples

The [selectable Tic-Tac-Toe and Five-Dice slices](game_variants/README.md)
exercise three equivalent UIL/C module styles and per-roll implementation
selection. They are authored bounded examples, separate from the original-backed
DOS verification below.

These examples belong to a source checkout. They compare separate, fresh native
DOS runs of original-backed compiled files. They are not included in tool-only
source or wheel distributions. Private game inputs are supplied by the operator;
no game files, checkpoints, project databases, screenshots or traces belong in
Git or the published evidence.

The verifier creates a new project, captures the original executable and every
explicit resource into a stored block definition, compiles to a new private
directory, and executes the original and emitted inputs in separate DOSBox
sessions. It retains private state and captures under the output directory. It
refuses an existing output or output inside a Git checkout. Original and emitted
input inventories are checked for changes. Use a new path for every run.

From the checkout, with fDisBull dependencies and a tested native DOSBox backend:

```sh
PYTHONPATH=src python -B examples/udc/verify_native.py \
  --game zork --source /private/licensed/zork-r88 \
  --backend /private/tested/dosbox-x --output /private/new-udc-zork

PYTHONPATH=src python -B examples/udc/verify_native.py \
  --game dinopark --source /private/licensed/dinopark \
  --backend /private/tested/dosbox-x --output /private/new-udc-dinopark

PYTHONPATH=src python -B examples/udc/verify_native.py \
  --game synthetic --backend /private/tested/dosbox-x \
  --output /private/new-udc-synthetic
```

Zork requires the qualified `_ZORK1.COM`, `DATA/ZORK1.DAT`, and `SETUP.INF`.
The DOS mailbox route compares selected pre/post state and normalized first and
repeated responses. DinoPark requires the qualified `DINOPARK.EXE` and its
explicit resources; `DINOSG.*` saves are excluded. Its NEW GAME route compares
an observed selector and sampled office/bank/return frames. Both routes save
bounded traces and screenshots, and re-export screenshots after reopening each
project. Those checks do not prove whole-game equivalence.

The authored `synthetic_game.asm` is assembled by real LLVM tools. Install
`llvm-mc`, `llvm-objcopy`, `llvm-nm`, and `llvm-readobj` on PATH, or set
`FDISBULL_LLVM_DIR` to their directory. The verifier rejects relocations and
compares original, ASM-to-UIL and ASM-derived-C-to-UIL builds after a real key
press. The modeled AX effect is checked by Z3 under its stated u16 assumptions;
an intentionally wrong value must yield a counterexample and no output. The C
view shares the ASM decoder and is not independent source evidence. Five additional boundary values are tested by explicit paused AX and instruction-pointer edits from a post-completion checkpoint; these are assisted CPU/model probes, not ordinary gameplay. Compilation retains original native backing bytes; it does not generate DOS machine code.

For native pytest acceptance, set `FDISBULL_DOSBOX` to the executable backend
and run `python -B -m pytest -q --require-native tests/test_udc_native.py`.
The optional local assembly check skips if LLVM is absent; under
`--require-native`, missing native or assembler prerequisites fail acceptance.
The [sanitized receipts](../../docs/evidence/udc-2026-10-29/) contain hashes and
bounded results. Raw outputs remain private.
