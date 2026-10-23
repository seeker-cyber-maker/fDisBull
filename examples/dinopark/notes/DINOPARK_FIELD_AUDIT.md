# DinoPark field audit

Audit date: 2026-10-22. This is static evidence for `DINOPARK.EXE`, SHA-256
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
The [machine-readable evidence](../images/dinopark-field-audit.json) records
instruction bytes, source addresses, original file offsets, stored register
assumptions, memory widths/access classes, loader calls and archive checks.
No game execution or day tick was observed.

## Scope and qualification

The 0.4 baseline contains 46,294 instructions. The qualified investigation
contains 47,177 after explicitly admitting `38ff:2048`, `38ff:16fc` and
`38ff:3cc1`, with the forensic assumption `DS=4020h`. The save wrapper also
reaches serializer `38ff:0ffe`. These additions demonstrate missing reachable
regions; they do not establish automatic or complete code coverage.

Databases were opened read-only. Memory access classes were independently
decoded with iced-x86 `InstructionInfo`, then combined with stored DOS states.
Snapshot instruction bytes include MZ relocations. The original file mapping is
`linear_address - 10000h + 4800h`. `4020:6f90` and `4020:6fac` map to linear
addresses `47190h` and `471ach` respectively. Stored constants are static
assumptions, not observed runtime register values.

## Direct scalar reads

All eight accesses below read a two-byte word with the stored `DS=4020h`.

| Field | Instruction | Bytes | Operation |
| --- | --- | --- | --- |
| `6f90` | `38ff:2b0d` | `a1906f` | `mov ax,[6f90h]` |
| `6f90` | `38ff:2bdc` | `a1906f` | `mov ax,[6f90h]` |
| `6fac` | `23c5:3839` | `833eac6f03` | `cmp word [6fach],3` |
| `6fac` | `23c5:3840` | `a1ac6f` | `mov ax,[6fach]` |
| `6fac` | `38ff:22d0` | `833eac6f00` | `cmp word [6fach],0` |
| `6fac` | `38ff:22ee` | `f72eac6f` | `imul word [6fach]` |
| `6fac` | `38ff:3cd3` | `833eac6f03` | `cmp word [6fach],3` |
| `6fac` | `38ff:3e7b` | `a1ac6f` | `mov ax,[6fach]` |

The `3cd3` access is inside the newly admitted `3cc1` jump-table block.
Zero fully resolved overlapping scalar writes were found in these stored states.
That result does not exclude writers: the following indexed and bulk paths
already show why a direct-address search is insufficient.

## Indexed and bulk writers

`DS:6f88` is handled as a 12-byte block of six words. `6f90` is its fifth word
(index 4). Calling that block “staff” remains the user's role hypothesis.

| Instruction | Word update | Local index construction / condition |
| --- | --- | --- |
| `38ff:28a4` | `inc [bx+6f88h]` | `BX=2*[bf99h]`; branch requires `[bf97h]!=0` |
| `38ff:29b8` | `sub [bx+6f88h],ax` | `BX=2*SI`; subtraction uses local backup; loop bound comes from `[5e63h]` |
| `38ff:2a27` | `dec [bx+6f88h]` | `BX=2*[bf99h]`; nonzero word and `[bf97h]!=0` guards |
| `38ff:4952` | `dec [bx+6f88h]` | `BX=2*DI`; nonzero word guard |
| `38ff:4d26` | `inc [bx+6f88h]` | `BX=2*[bf99h]`; countdown `[bf97h]` reaches zero |
| `38ff:4d98` | `dec [bx+6f88h]` | `BX=2*[bp-6]`; nonzero word guard |

Each can start exactly at `6f90` when `BX=8`. Stored states do not establish
that index at those instructions. Reaching `6fac` through the same expression
would require `BX=24h` (index 18), outside the demonstrated six-word block.
This arithmetic possibility is not evidence that a valid execution does so.
The JSON also records seven conditional word writers using bases `6f94`,
`6f9a` and `6fa0`, including their exact-start alias conditions modulo 65536.
An unaligned overlapping word starts one byte before or after a field's start;
such aliases require their own index evidence.

No stored dword-or-wider operand with displacement in `6f70h..6fd0h` was
found. This does not exclude wider writes through registers or other bases.
Unknown DS/ES, pointers, indices and variable REP counts prevent a complete
negative writer result. Candidate counts in the JSON count native operands,
not proven aliases, and differ from the project's persistent memory-fact counts.

| Path | Source and effect | Native pointer / width evidence |
| --- | --- | --- |
| Initialization | `38ff:013b` zeros `4020:6fa6`, 8 bytes; `014f` zeros `4020:6f88`, 12 bytes | `1000:5000` → `4fdc`; `LES DI` loads destination, `CLD`, word count and `REP STOSW` at `4ff8`, with odd-byte handling |
| Load | `38ff:1ce7` reads 8 bytes into `6fa6`; `1d02` reads 12 into `6f88` | `295e:0187` → `1000:4591` → buffered reader `449d`; direct path `4513` → `1b73`, `LDS DX` and `INT 21h/AH=3fh` at `1b95`; buffered byte store through `ES:BX` at `4536` |
| Save | `38ff:1423` and `143a` serialize the same blocks | `295e:01cd` → `1000:4a5f` → `545d` → `6734` → `6885`; `INT 21h/AH=40h` at `68a7` reads memory as the file-write source |
| Backup copies | `2d0a:0034` copies `6f88` to `4020:b9f6`; `38ff:28c0` copies it to `SS:[BP-78h]`, both 12 bytes | `1000:4fb8`: `LES` destination, `LDS` source, `CLD`, `REP MOVSW` at `4fcb`, optional `MOVSB` |

A successful complete load overwrites both fields. Short reads/errors can
leave a partial overwrite. The two demonstrated backup calls read the field
block; the generic copy routine can write other destinations at other calls.
DOS I/O buffer direction and short-transfer behavior are documented by the
[AH=3fh read reference](https://delorie.com/djgpp/doc/rbinter/id/94/27.html)
and [AH=40h write reference](https://delorie.com/djgpp/doc/rbinter/id/02/28.html).

## Save offsets

The shorthand offsets 3878, 3880 and 3888 are **decimal**. The actual save
wrapper at `38ff:2048` opens `dinosg.%03d`, reads six bytes at `20ac`, compares
them against `DINOSG` at `20c2`, and calls body loader `17af` at `20ec` on the
success path. The save wrapper at `16fc` writes the six-byte magic at `1773`
before calling serializer `0ffe` at `1788`.

Summing the 74 constant body-read lengths gives 4,147 bytes. The first target
block starts at body offset `f1ah`; adding the six-byte prefix yields:

| Memory location | Save offset, decimal | Save offset, hex | Size |
| --- | ---: | --- | ---: |
| `4020:6fa6` | 3872 | `f20` | 8 bytes |
| `4020:6fac` | 3878 | `f26` | 2 bytes |
| `4020:6f88` | 3880 | `f28` | 12 bytes |
| `4020:6f90` | 3888 | `f30` | 2 bytes |

All eight archived `DINOSG.000`–`.007` files are 4,153 bytes
(`6 + 4147`), start with `DINOSG` and contain `V1.1` at decimal offset 37
(`6 +` the first 31-byte body read). This corroborates the static layout.
Where qualified state joins dropped stack constants, loader records explicitly
identify baseline constants at identical instruction bytes; their local push
sequences were also inspected. Save mapping establishes byte correspondence,
not live count identity or an economic formula.

## Address bookkeeping and next experiment

`38ff:2b66` starts the reviewed routine; its returns are at `31c1` and `31cd`.
`31ce` has a separate candidate entry and is not reached in this CFG slice;
that does not prove exclusive function ownership or a universal end boundary.
The `2b0d` read belongs to the preceding routine. Paired updates occur at
`3168/316c` to `DS:bad4/bad6` and `3170/3174` to `DS:5c3a/5c3c`.
The companion read at `317f` is **`DS:6fa8`**, not either audited field.
These instruction facts alone establish no economic interpretation.

A future emulator experiment could watch the two byte ranges during an
identified day transition, save/load and a controlled change to one proposed
staff category. Record CS:IP, DS/ES, effective address, width, before/after
bytes and the triggering action. That is a proposed test, not an observed
execution; an available emulator/day-tick trace is still needed.
