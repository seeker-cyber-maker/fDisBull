# Minimal Snake conversion fixture, version 1

Newly authored local fixture, not recovered commercial-game code. The canonical
original is a reproducibly built 8086 MS-DOS MZ executable with VGA graphics,
BIOS keyboard input, INT 33h mouse input and a BIOS tick clock. No external
assets, media, sound or filesystem inputs are required during play.

The playable learner copy is `../../targets/fixture-snake/`. Keep the source,
symbols, behavior vectors and verification scripts in this separate `oracle/`
directory when running a blind recovery exercise. Source-assisted and blind
analysis are different experiments.

## Rebuild without changing an earlier output

Use an explicitly supplied Microsoft MASM 5.1/LINK toolchain and DOSBox-X:

```sh
python3 oracle/build.py --tools /absolute/path/to/compiler --dosbox /absolute/path/to/dosbox-x --output /new/private/build-directory
```

The compiler directory must contain `BIN/MASM.EXE` and `BIN/LINK.EXE`.
The script refuses an existing destination, logs assembly/linking, records
source/tool/output hashes and verifies the tools remain unchanged. Tools are
not distributed with this fixture. Two fresh builds produced identical
`SNAKE.EXE` bytes. The first failed short-branch build remains in the private
intake record; it is not a canonical inventory entry.

## Verify

`oracle/verify.py pure` executes the compiled step in Unicorn 2.1.4 against
`oracle/vectors.json`, checks preserved registers and rejects OS interrupts.
Its 17 diagnostic states are independent specification cases, not a claim that
each state was reached by ordinary play. Supply `--build`, `--report` and,
if Unicorn is outside the active environment, `--unicorn-site`.

`oracle/verify.py native` uses an installed fDisBull and a separately built
compatible native DOSBox backend. Supply `--build`, a new `--output` directory,
`--backend` and a new `--report`. It runs physical keyboard/mouse input through
the original guest, checks memory/state/graphics and stores native screenshots.
The state addresses come from the build's LINK map, so this validation is
explicitly source-assisted. No executable patch is used.

Runtime observations and the maintained-inventory receipt are in
`../../analysis/snake-intake-2026-10-31/` and
`../../receipts/snake-intake-2026-10-31.json`.

No conversion to another platform has been qualified by this intake. See
`oracle/PORTING.md` for the next experiment's boundaries and acceptance checks.

License: CC0-1.0; see `LICENSE.txt`. No third-party game source or assets used.
